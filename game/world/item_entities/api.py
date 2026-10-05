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
    scope = TREE_OPERATION_SCOPES.get(operation)
    if scope is None:
        raise ValidationError("트리 적용 범위가 정의되지 않은 행동입니다.")
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
        ancestors = _ancestors(parent_item)
        locked = {item.pk: item for item in lock_items(ancestors)}
        item = ItemEntity(
            definition_id=definition_id,
            quantity=quantity,
            location_kind=location_kind,
            owner_object=owner_object,
            parent_item=locked.get(item_id(parent_item)) if parent_item is not None else None,
            slot=slot,
            socket=socket,
            state=deepcopy({} if state is None else state),
            sequence=_next_sequence(),
        )
        item.save(force_insert=True)
        return item


def _move(item, *, location_kind, owner_object, parent_item, slot, socket, operation, tree):
    with world_change():
        identities = _tree_ids(item)
        if not tree and len(identities) > 1:
            raise ValidationError("내부 아이템이 있는 물품은 트리 이동을 사용해야 합니다.")
        ancestors = _ancestors(parent_item)
        if item_id(item) in ancestors:
            raise ValidationError("아이템을 자신이나 자신의 하위 아이템 안으로 옮길 수 없습니다.")
        locked = {row.pk: row for row in lock_items(identities | set(ancestors))}
        root = locked[item_id(item)]
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
    )


def split_stack(item, quantity):
    with world_change():
        # inside 스택도 source를 잠근 뒤 더 작은 부모 ID를 추가로 잠그지 않는다.
        parent = (
            ItemEntity.objects.filter(pk=item_id(item))
            .values_list("parent_item_id", flat=True)
            .first()
        )
        locked = {row.pk: row for row in lock_items([item, *_ancestors(parent)])}
        source = locked[item_id(item)]
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
    """정의·위치·merge 상태를 비교한다. LootClaim 도입 시 claim identity도 비교한다."""
    fields = (
        "definition_id",
        "location_kind",
        "owner_object_id",
        "parent_item_id",
        "slot",
        "socket",
    )
    return all(
        getattr(source, field) == getattr(destination, field) for field in fields
    ) and merge_state(source) == merge_state(destination)


def merge_stack(source, destination):
    with world_change():
        if item_id(source) == item_id(destination):
            raise ValidationError("같은 스택끼리는 합칠 수 없습니다.")
        locked = {item.pk: item for item in lock_items([source, destination])}
        source, destination = locked[item_id(source)], locked[item_id(destination)]
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
        locked = lock_items([item])[0]
        _check_operation(locked, operation)
        # PROTECT가 내부 물품의 암묵적 삭제를 차단한다. 재귀 삭제는 제공하지 않는다.
        locked.delete()


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
