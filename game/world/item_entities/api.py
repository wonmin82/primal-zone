"""ItemEntity row를 직접 변경하는 원자적 API. 호출자 보안·게임 권한은 상위 서비스가 담당한다."""

from copy import deepcopy
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import F

from world.content import ITEMS
from world.item_entities.models import ItemEntity, ItemSequence
from world.item_entities.policy import TREE_OPERATION_SCOPES, can_item_operation
from world.multiplayer import world_change


def item_id(item):
    return UUID(str(item.pk if isinstance(item, ItemEntity) else item))


def ordered_item_ids(items):
    """UUID 정렬은 lock 순서에만 사용한다. 표시·selector 순서는 sequence다."""
    return tuple(sorted({item_id(item) for item in items}))


def _current(item):
    try:
        return ItemEntity.objects.get(pk=item_id(item))
    except ItemEntity.DoesNotExist:
        raise ValidationError("대상 아이템이 더 이상 존재하지 않습니다.") from None


def lock_items(items):
    """먼저 ID를 수집·정렬한 다음 동일 순서로 row lock을 얻는다."""
    if not connection.in_atomic_block:
        raise RuntimeError("아이템 lock은 transaction 안에서만 사용할 수 있습니다.")
    locked = []
    for identity in ordered_item_ids(items):
        try:
            locked.append(ItemEntity.objects.select_for_update().get(pk=identity))
        except ItemEntity.DoesNotExist:
            raise ValidationError("대상 아이템이 더 이상 존재하지 않습니다.") from None
    return locked


def _next_sequence():
    # UPDATE가 SQLite에서도 쓰기를 직렬화하고 PostgreSQL에서는 counter row를 잠근다.
    if ItemSequence.objects.filter(pk=1).update(last_value=F("last_value") + 1) != 1:
        raise RuntimeError("아이템 순번 발급기 migration이 필요합니다.")
    return ItemSequence.objects.get(pk=1).last_value


def _ancestors(parent_item):
    identities = []
    while parent_item is not None:
        identity = item_id(parent_item)
        if identity in identities:
            raise ValidationError("아이템의 부모 참조가 순환합니다.")
        identities.append(identity)
        try:
            parent_item = ItemEntity.objects.get(pk=identity).parent_item_id
        except ItemEntity.DoesNotExist:
            raise ValidationError("부모 아이템이 없습니다.") from None
    return identities


def _tree_ids(item):
    pending, found = [item_id(item)], set()
    while pending:
        identity = pending.pop()
        if identity in found:
            raise ValidationError("아이템의 부모 참조가 순환합니다.")
        found.add(identity)
        pending.extend(
            ItemEntity.objects.filter(parent_item_id=identity).values_list("pk", flat=True)
        )
    return found


def _check_operation(item, operation):
    if operation is not None and not can_item_operation(item, operation):
        raise ValidationError("이 아이템에는 해당 행동을 할 수 없습니다.")


def _check_tree_operation(root, descendants, operation):
    """root의 직접 행동과 contained child의 수동 이동 보호를 구분한다."""
    if operation is None:
        # 신뢰된 내부 배치 전용이다. 위치·순환·고유 범위 검증은 우회하지 않는다.
        return
    scope = TREE_OPERATION_SCOPES.get(operation) if isinstance(operation, str) else None
    if scope is None:
        raise ValidationError("트리 적용 범위가 정의되지 않은 행동입니다.")
    if (operation in ("sell", "burn") and ITEMS[root.definition_id].get("firearm_family")
            and root.children.filter(socket="magazine").exists()):
        raise ValidationError("탄창을 먼저 분리한 뒤 총기를 판매하거나 소각하세요.")
    _check_operation(root, operation)
    if scope == "tree":
        for descendant in descendants:
            _check_operation(descendant, operation)


def create_item(
    definition_id,
    *,
    location_kind,
    owner_object=None,
    parent_item=None,
    quantity=1,
    slot=None,
    socket=None,
    state=None,
):
    with world_change():
        from world.equipment_service import after_item_change, before_item_change

        change = before_item_change(location_kind=location_kind, owner_object=owner_object, parent_item=parent_item)
        ancestors = _ancestors(parent_item)
        locked = {item.pk: item for item in lock_items([*ancestors, *change.item_ids])}
        item = ItemEntity(
            definition_id=definition_id,
            quantity=quantity,
            location_kind=location_kind,
            owner_object=owner_object,
            parent_item=locked.get(item_id(parent_item)) if parent_item is not None else None,
            slot=slot,
            socket=socket,
            state=deepcopy(_default_state(definition_id) if state is None else state),
            sequence=_next_sequence(),
        )
        item.save(force_insert=True)
        after_item_change(change)
        return item


def _move(item, *, location_kind, owner_object, parent_item, slot, socket, operation, tree, expected_source=None):
    with world_change():
        from world.equipment_service import after_item_change, before_item_change

        current = _current(item)
        change = before_item_change(current, location_kind=location_kind, owner_object=owner_object, parent_item=parent_item)
        identities = _tree_ids(item)
        if not tree and len(identities) > 1:
            raise ValidationError("내부 아이템이 있는 물품은 트리 이동을 사용해야 합니다.")
        ancestors = _ancestors(parent_item)
        if item_id(item) in ancestors:
            raise ValidationError("아이템을 자신이나 자신의 하위 아이템 안으로 옮길 수 없습니다.")
        locked = {row.pk: row for row in lock_items(identities | set(ancestors) | set(change.item_ids))}
        root = locked[item_id(item)]
        source = (root.location_kind, root.owner_object_id)
        if (source != (current.location_kind, current.owner_object_id)
                or root.parent_item_id != current.parent_item_id) or (
            expected_source is not None and source != expected_source
        ):
            raise ValidationError("아이템의 위치나 소유자가 바뀌었습니다. 다시 선택하세요.")
        _check_tree_operation(
            root, (locked[identity] for identity in identities if identity != root.pk), operation
        )
        root.location_kind = location_kind
        root.owner_object = owner_object
        root.parent_item = locked[item_id(parent_item)] if parent_item is not None else None
        root.slot, root.socket = slot, socket
        root.save()
        # 내부 위치는 유지하되 소유자별 uniqueness는 새 루트 소유자와 함께 갱신한다.
        for row in sorted(
            (locked[identity] for identity in identities if identity != root.pk),
            key=lambda row: row.sequence,
        ):
            row.refresh_from_db()
            row.save()
        after_item_change(change)
        return root


def move_item(
    item,
    *,
    location_kind,
    owner_object=None,
    parent_item=None,
    slot=None,
    socket=None,
    operation=None,
):
    return _move(
        item,
        location_kind=location_kind,
        owner_object=owner_object,
        parent_item=parent_item,
        slot=slot,
        socket=socket,
        operation=operation,
        tree=False,
    )


def move_item_tree(
    item,
    *,
    location_kind,
    owner_object=None,
    parent_item=None,
    slot=None,
    socket=None,
    operation=None,
    expected_source=None,
):
    return _move(
        item,
        location_kind=location_kind,
        owner_object=owner_object,
        parent_item=parent_item,
        slot=slot,
        socket=socket,
        operation=operation,
        tree=True,
        expected_source=expected_source,
    )


def split_stack(item, quantity, *, allow_claimed=False):
    """claimed 분할 허용은 loot pickup의 즉시 이동/rollback transaction 전용이다."""
    with world_change():
        from world.equipment_service import before_item_change
        from world.loot_entities.models import LootClaim

        current = _current(item)
        change = before_item_change(current)
        # inside 스택도 source를 잠근 뒤 더 작은 부모 ID를 추가로 잠그지 않는다.
        parent = current.parent_item_id
        locked = {row.pk: row for row in lock_items([item, *_ancestors(parent), *change.item_ids])}
        source = locked[item_id(item)]
        if (source.location_kind, source.owner_object_id, source.parent_item_id) != (
                current.location_kind, current.owner_object_id, current.parent_item_id):
            raise ValidationError("아이템의 위치나 소유자가 바뀌었습니다. 다시 선택하세요.")
        if not allow_claimed and LootClaim.objects.filter(item_entity_id=source.pk).exists():
            raise ValidationError("권리가 있는 전리품 스택은 부분 회수 경로에서만 나눌 수 있습니다.")
        if not ITEMS[source.definition_id]["stackable"] or source.children.exists():
            raise ValidationError("이 아이템은 나눌 수 없습니다.")
        if type(quantity) is not int or not 0 < quantity < source.quantity:
            raise ValidationError("분할 수량은 현재 수량보다 작은 양의 정수여야 합니다.")
        source.quantity -= quantity
        source.save()
        return create_item(
            source.definition_id,
            quantity=quantity,
            location_kind=source.location_kind,
            owner_object=source.owner_object,
            parent_item=source.parent_item,
            slot=source.slot,
            socket=source.socket,
            state=source.state,
        )


def merge_state(item):
    """merge 관련 상태의 계약. 현재는 전체 state이며 향후 정의별로 선택할 수 있다."""
    return deepcopy(item.state)


def same_merge_context(source, destination):
    """정의·위치·merge 상태와 권리/배정 단위를 비교한다."""
    fields = (
        "definition_id",
        "location_kind",
        "owner_object_id",
        "parent_item_id",
        "slot",
        "socket",
    )
    from world.loot_claims import same_claim_context
    from world.loot_service import claim_context

    return same_claim_context(claim_context(source), claim_context(destination)) and all(
        getattr(source, field) == getattr(destination, field) for field in fields
    ) and merge_state(source) == merge_state(destination)


def merge_stack(source, destination):
    with world_change():
        from world.equipment_service import before_item_change

        if item_id(source) == item_id(destination):
            raise ValidationError("같은 스택끼리는 합칠 수 없습니다.")
        current_source, current_destination = _current(source), _current(destination)
        change = before_item_change(current_source, parent_item=current_destination)
        locked = {item.pk: item for item in lock_items([source, destination, *change.item_ids])}
        source, destination = locked[item_id(source)], locked[item_id(destination)]
        for row, current in ((source, current_source), (destination, current_destination)):
            if (row.location_kind, row.owner_object_id, row.parent_item_id) != (
                    current.location_kind, current.owner_object_id, current.parent_item_id):
                raise ValidationError("아이템의 위치나 소유자가 바뀌었습니다. 다시 선택하세요.")
        if (
            not ITEMS[source.definition_id]["stackable"]
            or not same_merge_context(source, destination)
            or source.children.exists()
            or destination.children.exists()
        ):
            raise ValidationError("정의·위치·상태가 같은 일반 스택만 합칠 수 있습니다.")
        destination.quantity += source.quantity
        destination.save()
        source.delete()
        return destination


def delete_item(item, *, operation=None):
    with world_change():
        from world.equipment_service import after_item_change, before_item_change

        current = _current(item)
        change = before_item_change(current)
        locked = {row.pk: row for row in lock_items([item, *change.item_ids])}[item_id(item)]
        if (locked.location_kind, locked.owner_object_id, locked.parent_item_id) != (
                current.location_kind, current.owner_object_id, current.parent_item_id):
            raise ValidationError("아이템의 위치나 소유자가 바뀌었습니다. 다시 선택하세요.")
        _check_tree_operation(locked, (), operation)
        # PROTECT가 내부 물품의 암묵적 삭제를 차단한다. 재귀 삭제는 제공하지 않는다.
        locked.delete()
        after_item_change(change)


def _default_state(definition_id):
    from world.item_entities.policy import definition_errors
    from world.item_states import default_state

    definition = ITEMS.get(definition_id)
    if definition is None:
        return {}
    issues = definition_errors(definition_id, definition)
    if issues:
        raise ValidationError({"definition_id": issues})
    return default_state(definition)


def update_item_state(item, state):
    """상위 domain이 권한과 결합 lock 집합을 확보한 뒤 사용하는 상태 변경 경계."""
    with world_change():
        row = lock_items([item])[0]
        row.state = deepcopy(state)
        row.save()
        return row


def items_in_location(location_kind, *, owner_object=None, parent_item=None):
    return ItemEntity.objects.filter(
        location_kind=location_kind, owner_object=owner_object, parent_item=parent_item
    ).order_by("sequence")


def children_of(item):
    return ItemEntity.objects.filter(parent_item_id=item_id(item)).order_by("sequence")


def items_owned_by(owner_object):
    """직접 위치와 inside 후손을 함께 조회한다. 개인 보관의 owner는 탐사자다."""
    identities = set(
        ItemEntity.objects.filter(owner_object=owner_object).values_list("pk", flat=True)
    )
    pending = identities
    while pending:
        pending = (
            set(ItemEntity.objects.filter(parent_item_id__in=pending).values_list("pk", flat=True))
            - identities
        )
        identities.update(pending)
    return ItemEntity.objects.filter(pk__in=identities).order_by("sequence")
