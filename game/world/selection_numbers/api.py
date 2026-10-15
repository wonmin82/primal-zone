"""B-1 실물 참조·순수 조회 및 최종 변경 시점의 원자적 번호 확정."""

from dataclasses import dataclass, replace

from django.core.exceptions import ValidationError
from django.db.models import Q
from evennia.objects.models import ObjectDB

from world.actions.schema import ReferenceKind, TargetReference
from world.multiplayer import before_commit, pending_commit, world_change

from .mode import enabled
from .models import NumberScope, SelectionNumber


def object_definition(value):
    definition = value.db.selection_definition_id or value.db.action_provider_id
    if not definition:
        identities = value.tags.get(category="primal_interactable", return_list=True)
        if len(identities) == 1:
            definition = "interactable:" + identities[0]
    return definition


@dataclass(frozen=True)
class SelectionRecord:
    reference: TargetReference
    scope_id: str
    group_id: str
    name: str
    aliases: tuple[str, ...] = ()
    unique_names: tuple[str, ...] = ()
    number: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "unique_names", tuple(self.unique_names))
        if self.scope_id != self.reference.scope_id:
            raise ValueError("참조와 번호의 Scope가 일치해야 합니다.")


def descriptor(value):
    """현재 실물만 읽는다. 번호 생성·생명주기 정합화·권한 변경은 하지 않는다."""
    if not enabled():
        return None
    from evennia.objects.objects import DefaultRoom
    from typeclasses.enemies import Enemy
    from typeclasses.interactables import ActionObject
    from typeclasses.loot import Corpse, DroppedLoot

    from world.content import ITEMS
    from world.door_entities.models import Door
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot

    if isinstance(value, ItemEntity):
        definition = ITEMS.get(value.definition_id)
        if definition is None:
            return None
        location = value.location_kind
        kind = ReferenceKind.LOOT if location in ("corpse_loot", "world_loot") else ReferenceKind.ITEM
        if location == "inside":
            scope = f"inside:{value.parent_item_id}"
        elif location in ("inventory", "equipment"):
            scope = f"character:{value.owner_object_id}"
        elif location == "world_loot":
            if not value.owner_object.db_location_id:
                return None
            scope = f"ground:{value.owner_object.db_location_id}"
        else:
            scope = f"{location}:{value.owner_object_id}"
        group = definition.get("selection_group_id") or f"item:{value.definition_id}"
        return SelectionRecord(TargetReference(kind, str(value.pk), scope), scope, group,
                               definition["name"], tuple(definition.get("aliases", ())))
    if isinstance(value, CurrencyLoot):
        source = value.owner_object
        if isinstance(source, Corpse):
            scope = f"corpse_loot:{source.pk}"
        elif source.db_location_id:
            scope = f"ground:{source.db_location_id}"
        else:
            return None
        return SelectionRecord(TargetReference(ReferenceKind.CURRENCY, str(value.pk), scope),
                               scope, "currency:credits", "보급칩")
    if isinstance(value, DefaultRoom) and value.pk:
        scope = f"room:{value.pk}"
        group = f"room:{value.db.zone_id or value.db_typeclass_path}"
        return SelectionRecord(TargetReference(ReferenceKind.ROOM, str(value.pk), scope),
                               scope, group, value.key, tuple(value.aliases.all()))
    if not isinstance(value, ObjectDB) or not value.pk or not value.db_location_id:
        return None
    scope = f"room:{value.db_location_id}"
    aliases = tuple(value.aliases.all())
    unique_names = tuple(value.db.selection_unique_names or ())
    if isinstance(value, Enemy):
        if not value.db.enemy_id:
            return None
        kind, group, name = ReferenceKind.ENEMY, f"enemy:{value.db.enemy_id}", value.key
    elif isinstance(value, Corpse):
        kind, group, name = ReferenceKind.CORPSE, "world:corpse", "시체"
        aliases = (value.key, *aliases)
    elif isinstance(value, DroppedLoot):
        kind, group, name = ReferenceKind.OBJECT, "world:ground_source", value.key
    else:
        door = Door.objects.filter(Q(exit_a_id=value.pk) | Q(exit_b_id=value.pk)).first() if value.db_destination_id else None
        if door:
            return SelectionRecord(TargetReference(ReferenceKind.DOOR, str(value.pk), scope),
                                   scope, "world:door", "문",
                                   tuple(dict.fromkeys((door.name, value.key, *door.aliases, *aliases))),
                                   (door.name,) if value.db.legacy_singleton_suffix_1 else ())
        if not isinstance(value, ActionObject) and not value.db.action_provider_id:
            return None
        kind, name = ReferenceKind.OBJECT, value.key
        definition = object_definition(value)
        group = f"definition:{definition}" if definition else f"typeclass:{value.db_typeclass_path}"
    group = value.db.selection_group_id or group
    return SelectionRecord(TargetReference(kind, str(value.pk), scope), scope, group, name,
                           aliases, unique_names)


def _entity(kind, identity):
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot

    kind = ReferenceKind(kind)
    model = ItemEntity if kind in (ReferenceKind.ITEM, ReferenceKind.LOOT) else (
        CurrencyLoot if kind == ReferenceKind.CURRENCY else ObjectDB)
    try:
        return model.objects.filter(pk=identity).first()
    except (ValueError, ValidationError, TypeError):
        return None


def resolve_reference(reference):
    """동일 typed ID의 현재 실물과 Scope를 검증한다. 다른 대상으로 대체하지 않는다."""
    entity = _entity(reference.kind, reference.identity)
    if reference.kind == ReferenceKind.ROOM:
        from evennia.objects.objects import DefaultRoom

        return entity if isinstance(entity, DefaultRoom) and reference.scope_id == f"room:{entity.pk}" else None
    current = descriptor(entity) if entity else None
    return entity if current and current.reference == reference else None


def number_for(reference_or_kind, identity=None):
    reference = reference_or_kind if isinstance(reference_or_kind, TargetReference) else None
    kind = reference.kind if reference else ReferenceKind(reference_or_kind)
    identity = reference.identity if reference else str(identity)
    query = SelectionNumber.objects.filter(kind=kind, identity=identity)
    if reference:
        query = query.filter(scope__scope_id=reference.scope_id)
    return query.values_list("number", flat=True).first()


def label(record, unique_group_count=1):
    # 1도 항상 표시한다. 숨은 그룹원의 존재/제공 상태가 label을 바꾸지 않는다.
    if record.number is None:
        return record.name
    return f"{record.name} {record.number}"


def _visible(caller, entity):
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot
    from world.observation import can_inspect_loot, can_perceive, context_for

    if isinstance(entity, ItemEntity):
        root = entity.root()
        if root.location_kind in ("inventory", "equipment", "personal_storage"):
            return root.owner_object_id == caller.pk
        source = root.owner_object
        context = context_for(caller)
        return can_perceive(source, context) and (
            root.location_kind == "shared_storage" or can_inspect_loot(context))
    if isinstance(entity, CurrencyLoot):
        context = context_for(caller)
        return can_perceive(entity.owner_object, context) and can_inspect_loot(context)
    return can_perceive(entity, context_for(caller))


def current_scopes(caller, kind=None):
    scopes = {f"character:{caller.pk}"}
    if caller.location:
        room = f"room:{caller.location.pk}"
        scopes.add(room)
        if kind in (None, ReferenceKind.LOOT, ReferenceKind.CURRENCY):
            scopes.add(f"ground:{caller.location.pk}")
            corpses = SelectionNumber.objects.filter(scope__scope_id=room, kind=ReferenceKind.CORPSE)
            scopes.update(f"corpse_loot:{identity}" for identity in corpses.values_list("identity", flat=True))
    return scopes


def records_for(caller, kind=None, scope_id=None, *, scope_ids=None):
    """이미 발급된 번호만 관찰한다. 권한으로 재번호하지 않는다."""
    scopes = set(scope_ids) if scope_ids is not None else current_scopes(caller, kind)
    if scope_id is not None:
        scopes.intersection_update((scope_id,))
    query = SelectionNumber.objects.filter(scope__scope_id__in=scopes).select_related("scope").order_by("scope__scope_id", "scope__group_id", "number")
    if kind is not None:
        query = query.filter(kind=ReferenceKind(kind))
    result = []
    if kind in (None, ReferenceKind.ROOM) and caller.location:
        room = descriptor(caller.location)
        if room and room.scope_id in scopes:
            result.append(room)
    for row in query:
        ref = TargetReference(ReferenceKind(row.kind), row.identity, row.scope.scope_id)
        entity = resolve_reference(ref)
        if entity is not None and _visible(caller, entity):
            record = descriptor(entity)
            if record.group_id == row.scope.group_id:
                result.append(replace(record, number=row.number))
    return tuple(result)


_PENDING = "selection-numbers"


def schedule(kind, identity, *, skip_unchanged=False):
    """예약은 불변 집합이며 중첩 rollback은 world_change의 사전 복원으로 되돌린다."""
    if not enabled():
        return
    previous = pending_commit(_PENDING)
    touched = getattr(previous, "identities", ())
    migrations = getattr(previous, "migrations", ())
    key = (str(ReferenceKind(kind)), str(identity))
    if skip_unchanged:
        record = descriptor(_entity(*key))
        if record and str(record.reference.kind) != key[0]:
            record = None
        row = SelectionNumber.objects.select_related("scope").filter(kind=key[0], identity=key[1]).first()
        if row is None and record is None or row is not None and record is not None and (
                row.scope.scope_id, row.scope.group_id, row.name) == (record.scope_id, record.group_id, record.name):
            return
    if key not in touched:
        touched = (*touched, key)

    def finalize():
        _flush(touched, migrations)

    finalize.identities = touched
    finalize.migrations = migrations
    before_commit(_PENDING, finalize)


def authorize_item_definition_conversion(identity, old_definition, new_definition):
    """기존 승인된 Legacy maintenance 매핑만 명시적 번호 그룹 변환으로 연결한다."""
    from world.content.item_mapping import LEGACY_ITEM_MAPPING
    from world.item_runtime import maintenance

    if not maintenance.get() or LEGACY_ITEM_MAPPING.get(old_definition) != new_definition:
        raise ValidationError("승인된 명시적 아이템 정의 변환이 아닙니다.")
    schedule(ReferenceKind.ITEM, identity)
    schedule(ReferenceKind.LOOT, identity)
    previous = pending_commit(_PENDING)
    if previous is None:
        return
    touched = previous.identities
    migrations = (*previous.migrations, (str(identity), f"item:{old_definition}", f"item:{new_definition}"))

    def finalize():
        _flush(touched, migrations)

    finalize.identities = touched
    finalize.migrations = migrations
    before_commit(_PENDING, finalize)


def schedule_object(identity):
    if not enabled():
        return
    entity = ObjectDB.objects.filter(pk=identity).first()
    record = descriptor(entity) if entity else None
    kinds = set(SelectionNumber.objects.filter(identity=str(identity), kind__in=(
        ReferenceKind.OBJECT, ReferenceKind.ENEMY, ReferenceKind.CORPSE, ReferenceKind.DOOR)).values_list("kind", flat=True))
    if record and record.reference.kind != ReferenceKind.ROOM:
        kinds.add(record.reference.kind)
    for kind in kinds:
        schedule(kind, identity, skip_unchanged=True)
    # 개별 Ground Source의 ID는 유지하며 항목 번호 Scope만 Room을 따른다.
    from typeclasses.loot import DroppedLoot

    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot
    if not isinstance(entity, DroppedLoot):
        return

    for item in ItemEntity.objects.filter(owner_object_id=identity, location_kind="world_loot"):
        schedule_item(item.pk)
    for currency in CurrencyLoot.objects.filter(owner_object_id=identity):
        schedule(ReferenceKind.CURRENCY, currency.pk)


def schedule_item(identity):
    schedule(ReferenceKind.ITEM, identity, skip_unchanged=True)
    schedule(ReferenceKind.LOOT, identity, skip_unchanged=True)


def _flush(identities, migrations=()):
    if not identities:
        return
    current = {}
    for kind, identity in identities:
        entity = _entity(kind, identity)
        record = descriptor(entity) if entity else None
        if record and record.reference.kind == kind:
            current[(kind, identity)] = record
    rows = list(SelectionNumber.objects.select_related("scope").select_for_update().filter(
        Q(*[Q(kind=kind, identity=identity) for kind, identity in identities], _connector=Q.OR)))
    scopes = {(row.scope.scope_id, row.scope.group_id) for row in rows}
    scopes.update((record.scope_id, record.group_id) for record in current.values())
    locked = {}
    # 세계 RLock → 기존 Object/Item/Currency → 번호 Scope 사전순. 번호에서 도메인 lock으로 되돌아가지 않는다.
    for scope, group in sorted(scopes):
        row, _ = NumberScope.objects.get_or_create(scope_id=scope, group_id=group)
        locked[(scope, group)] = NumberScope.objects.select_for_update().get(pk=row.pk)
    retained = {}
    for row in rows:
        record = current.get((row.kind, row.identity))
        if record and record.scope_id == row.scope.scope_id and record.group_id == row.scope.group_id:
            retained[(row.kind, row.identity)] = row
        else:
            if record and record.group_id != row.scope.group_id:
                conversion = (row.identity, row.scope.group_id, record.group_id)
                if row.kind not in (ReferenceKind.ITEM, ReferenceKind.LOOT) or conversion not in migrations:
                    raise ValidationError("선택 그룹 변경에는 명시적인 마이그레이션이 필요합니다.")
            row.delete()
    # 중간 임시 집합 대신 최종 실물 집합이 비었을 때만 reset한다.
    occupied = {(record.scope_id, record.group_id) for record in current.values()}
    for key, scope in locked.items():
        if key not in occupied and not scope.members.exists():
            scope.next_number = 1
            scope.save(update_fields=["next_number"])
    for key, record in current.items():
        scope = locked[(record.scope_id, record.group_id)]
        from world.targets import normalized

        other_names = SelectionNumber.objects.filter(scope__scope_id=record.scope_id).exclude(scope=scope).values_list("name", flat=True)
        if any(normalized(name) == normalized(record.name) for name in other_names):
            raise ValidationError("같은 범위의 동일 선택 이름은 하나의 안정 그룹을 사용해야 합니다.")
        existing = retained.get(key)
        if existing:
            if existing.name != record.name:
                existing.name = record.name
                existing.save(update_fields=["name"])
        else:
            SelectionNumber.objects.create(scope=scope, kind=key[0], identity=key[1],
                                           number=scope.next_number, name=record.name)
            scope.next_number += 1
            scope.save(update_fields=["next_number"])


def verify():
    """DB 번호·현재 실물·counter의 일치를 읽기만으로 감사한다."""
    issues = []
    for row in SelectionNumber.objects.select_related("scope"):
        record = descriptor(_entity(row.kind, row.identity))
        if not record or record.reference.kind != row.kind or record.name != row.name or (record.scope_id, record.group_id) != (row.scope.scope_id, row.scope.group_id):
            issues.append((row.kind, row.identity, "stale"))
    for scope in NumberScope.objects.all():
        last = scope.members.order_by("-number").values_list("number", flat=True).first()
        if last is None and scope.next_number != 1 or last is not None and scope.next_number <= last:
            issues.append((scope.scope_id, scope.group_id, "counter"))
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot

    existing = set(SelectionNumber.objects.values_list("kind", "identity"))
    for model in (ObjectDB, ItemEntity, CurrencyLoot):
        for entity in model.objects.all():
            record = descriptor(entity)
            if record and record.reference.kind != ReferenceKind.ROOM:
                key = (record.reference.kind, record.reference.identity)
                if key not in existing:
                    issues.append((*key, "missing"))
    return tuple(issues)


def backfill(*, dry_run=True, backup_path=None):
    """명시 maintenance. 쓰기 전 SQLite backup을 생성하고 기존 번호를 유지하며 최종 확정한다."""
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot

    identities = []
    for model in (ObjectDB, ItemEntity, CurrencyLoot):
        for entity in model.objects.all().order_by("pk"):
            record = descriptor(entity)
            if record and record.reference.kind != ReferenceKind.ROOM:
                identities.append((record.reference.kind, record.reference.identity))
    if dry_run:
        return {"candidates": len(identities), "issues": verify(), "written": False}
    if backup_path is None:
        raise ValidationError("번호 초기화 전에 명시적인 백업 경로가 필요합니다.")
    from .maintenance import backup_database

    backup_database(backup_path)
    with world_change():
        for kind, identity in identities:
            schedule(kind, identity)
        def audit():
            if verify():
                raise ValidationError("번호 적용 최종 검증에 실패했습니다. 변경을 롤백합니다.")
        before_commit("selection-number-audit", audit)
    return {"candidates": len(identities), "issues": verify(), "written": True}


seed = backfill
