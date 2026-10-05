"""장비 영속 경계. Entity와 legacy는 명시적으로 선택한 한 저장소에만 쓴다."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from evennia.objects.models import ObjectDB

from world import equipment as eq
from world import recovery, rules
from world.content import ITEMS
from world.item_entities.models import ItemEntity
from world.multiplayer import world_change


def entity_runtime(character):
    return character.db.equipment_backend == "item_entities"


def use_item_entities(character):
    """빈 신규/fixture 캐릭터의 명시적 선택. 변환 작업이나 사용자 명령이 아니다."""
    with world_change():
        profile = character.profile()
        if profile["inventory"] or any(profile["equipment"].values()):
            raise rules.RuleError("legacy 소지품·장비가 있는 캐릭터는 Phase 6 변환이 필요합니다.")
        character.db.equipment_backend = "item_entities"
        reconcile_references(character)


def equipped_items(character):
    return ItemEntity.objects.filter(owner_object=character, location_kind="equipment").order_by("sequence")


def entity_snapshot(character):
    from world.item_entities.api import items_owned_by

    carried = tuple(
        eq.item_snapshot(row.definition_id, ITEMS[row.definition_id], item_id=row.pk,
                         sequence=row.sequence, quantity=row.quantity, location=row.location_kind,
                         slot=row.slot, state_summary=state_summary(row))
        for row in items_owned_by(character)
        if row.root().location_kind in ("inventory", "equipment")
    )
    return eq.EquipmentSnapshot(tuple(item for item in carried if item.location == "equipment"),
                                carried, character.db.active_weapon_item_id)


def state_summary(row):
    definition = ITEMS[row.definition_id]
    if definition.get("magazine"):
        return f"{row.state['rounds']}/{definition['magazine']['capacity']}"
    if definition.get("firearm_family"):
        from world.firearm_service import loaded_magazine

        magazine = loaded_magazine(row)
        return (f"{ITEMS[magazine.definition_id]['name']} {magazine.rounds}/{magazine.capacity}"
                if magazine else "탄창 없음")
    if definition.get("light_source"):
        from math import ceil
        from time import time

        from world.lighting import project_power

        state = project_power(row.state, time())
        capacity = definition['light_source'].get('max_power_seconds', 1800)
        return f"{'켜짐' if state['enabled'] else '꺼짐'} · {ceil(state['remaining_power'] / capacity * 100)}%"
    return ""


def equipment_snapshot(character, profile=None):
    if entity_runtime(character):
        return entity_snapshot(character)
    from world.equipment_legacy import snapshot

    return snapshot(profile if profile is not None else character.profile_snapshot())


def bind_profile(character, profile):
    return eq.EquipmentProfile(profile, equipment_snapshot(character, profile))


def active_weapon(character, profile=None):
    """backend-neutral gameplay 정보. Entity/legacy 모두 EquipmentItem 또는 None이다."""
    return equipment_snapshot(character, profile).active


def active_weapon_item(character):
    """영속 작업용 Entity row 조회. legacy에는 대응 row가 없으므로 None이다."""
    if not entity_runtime(character):
        return None
    active = active_weapon(character)
    return ItemEntity.objects.get(pk=active.identity) if active else None


def hand_usage(character, profile=None):
    return equipment_snapshot(character, profile).hand_usage


def reconcile_references(character):
    """공통 위치 변경/삭제 안에서 active weapon 참조를 정리한다."""
    snapshot = entity_snapshot(character)
    eligible = [item for item in snapshot.items if item.role == "weapon"]
    identity = snapshot.active.identity if snapshot.active else (eligible[0].identity if eligible else None)
    character.db.active_weapon_item_id = identity


@dataclass
class ItemChange:
    owners: tuple
    profiles: dict
    item_ids: tuple
    light_ids: dict


def before_item_change(old_item=None, *, location_kind=None, owner_object=None, parent_item=None):
    """owner lock으로 빈 슬롯 경쟁도 직렬화하고 모든 장비 ID를 기존 lock 집합에 합친다."""
    ids, equipment_ids = set(), set()
    if old_item is not None and old_item.location_kind == "equipment":
        equipment_ids.add(old_item.owner_object_id)
    if location_kind == "equipment" and owner_object is not None:
        equipment_ids.add(owner_object.pk)
    from typeclasses.explorers import Explorer

    for row in (old_item, parent_item):
        if row is not None:
            if not isinstance(row, ItemEntity):
                from world.item_entities.api import _current

                row = _current(row)
            root = row.root()
            if isinstance(root.owner_object, Explorer):
                ids.add(root.owner_object_id)
    if isinstance(owner_object, Explorer):
        ids.add(owner_object.pk)
    ids.update(equipment_ids)
    owners = tuple(ObjectDB.objects.select_for_update().get(pk=identity) for identity in sorted(ids))
    profiles = {}
    for owner in owners:
        if owner.pk in equipment_ids and entity_runtime(owner):
            profile = owner.profile()
            owner.accrue_recovery(profile)
            recovery.commit(profile, rules.stats(profile))
            profiles[owner.pk] = profile
    from world.item_entities.api import items_owned_by

    item_ids = tuple(identity for owner in owners
                     for identity in items_owned_by(owner).values_list("pk", flat=True))
    light_ids = {}
    for owner in owners:
        reference = owner.db.active_light_item_id
        if reference:
            from world.lighting_service import reference_row

            row = reference_row(reference)
            if row and row.owner_object_id == owner.pk and row.location_kind == "inventory":
                light_ids[owner.pk] = str(row.pk)
    return ItemChange(owners, profiles, item_ids, light_ids)


def after_item_change(change):
    for owner in change.owners:
        eq.validate_loadout(entity_snapshot(owner).items)
        reconcile_references(owner)
        if entity_runtime(owner):
            from world.lighting_service import reconcile_locked

            reconcile_locked(owner, previous_owned_id=change.light_ids.get(owner.pk))
        if owner.pk in change.profiles:
            profile = change.profiles[owner.pk]
            profile.equipment_context = entity_snapshot(owner)
            recovery.clamp(profile, rules.stats(profile))
            owner.save_profile(profile)


def validate_equipment_row(row):
    candidate = eq.item_snapshot(row.definition_id, ITEMS[row.definition_id], item_id=row.pk,
                                 sequence=row.sequence, quantity=row.quantity)
    if row.slot != candidate.slot:
        raise ValidationError({"slot": "아이템 정의의 장비 slot과 다릅니다."})
    others = [eq.item_snapshot(item.definition_id, ITEMS[item.definition_id], item_id=item.pk,
                              sequence=item.sequence, quantity=item.quantity, slot=item.slot)
              for item in equipped_items(row.owner_object).exclude(pk=row.pk)]
    try:
        eq.validate_loadout([*others, candidate])
    except rules.RuleError as error:
        raise ValidationError({"slot": str(error)}) from error


def resolve_item(character, value, action):
    from world.targets import item_selector, matching, parse_selector, require_single, select

    if not entity_runtime(character):
        return item_selector(value, ITEMS, action)
    candidates = entity_snapshot(character).carried

    def name_values(item):
        return (item.definition_id, item.name, *item.aliases)

    selector = parse_selector(value, [name for item in candidates for name in name_values(item)])
    require_single(selector, action)
    selected = select(matching(candidates, selector, name_values), selector)
    return ItemEntity.objects.get(pk=selected[0].identity)


def selector_label(character, item):
    if not isinstance(item, ItemEntity):
        return ITEMS[item]["name"]
    snapshot = entity_snapshot(character)
    selected = next(entry for entry in snapshot.carried if entry.identity == str(item.pk))
    return snapshot.label(selected)


def _change_equipment(character, item, *, remove=False, expected_slot=None):
    from world.item_entities import api

    with world_change():
        profile = character.profile()
        rules.require_peace(profile)
        if not entity_runtime(character):
            character.accrue_recovery(profile)
            recovery.commit(profile, rules.stats(profile))
            (rules.unequip if remove else rules.equip)(profile, item, expected_slot)
            character.save_profile(profile)
            return item
        row = ItemEntity.objects.get(pk=api.item_id(item))
        if row.owner_object_id != character.pk or row.location_kind != ("equipment" if remove else "inventory"):
            raise rules.RuleError("자신의 장착 장비 또는 소지 장비만 선택하세요.")
        data = eq.item_snapshot(row.definition_id, ITEMS[row.definition_id])
        kind = "weapon" if data.role == "weapon" else "armor"
        if expected_slot is not None and expected_slot != kind:
            raise rules.RuleError(f"이 장비에는 {data.remove_action if remove else data.equip_action}를 사용하세요.")
        return api.move_item_tree(row, location_kind="inventory" if remove else "equipment",
                                  owner_object=character, slot=None if remove else data.slot,
                                  operation="unequip" if remove else "equip",
                                  expected_source=("equipment" if remove else "inventory", character.pk))


def equip_item(character, item, expected_slot=None):
    try:
        return _change_equipment(character, item, expected_slot=expected_slot)
    except ValidationError as error:
        raise rules.RuleError(" / ".join(error.messages)) from error


def unequip_item(character, item, expected_slot=None):
    try:
        return _change_equipment(character, item, remove=True, expected_slot=expected_slot)
    except ValidationError as error:
        raise rules.RuleError(" / ".join(error.messages)) from error


def set_active_weapon(character, item):
    from world.item_entities.api import item_id, lock_items

    with world_change():
        rules.require_peace(character.profile())
        if not entity_runtime(character):
            active = eq.context(character.profile()).active
            if active is None or active.definition_id != item:
                raise rules.RuleError("현재 무장한 무기만 주무기로 지정할 수 있습니다.")
            return
        change = before_item_change(location_kind="equipment", owner_object=character)
        row = {row.pk: row for row in lock_items([item, *change.item_ids])}[item_id(item)]
        if row.owner_object_id != character.pk or row.location_kind != "equipment" or eq.item_snapshot(row.definition_id, ITEMS[row.definition_id]).role != "weapon":
            raise rules.RuleError("자신이 장착한 무기만 주무기로 지정할 수 있습니다.")
        character.db.active_weapon_item_id = str(row.pk)
        after_item_change(change)
