"""Phase 6에서 제거할 legacy 정의·profile 장비 호환 경계. Entity에는 쓰지 않는다."""

from world.content import ITEMS
from world.equipment import (
    EquipmentSnapshot,
    item_snapshot,
    refresh_legacy_context,
    reject,
    validate_loadout,
)

# 최종 콘텐츠 수치나 이름으로 변환하지 않고 현재 정의의 수치만 연결한다.
LEGACY_HAND_UNITS = {"spear": 2, "carbine": 2, "heavy_carbine": 2}


def definition_parts(identity, definition):
    slot = definition.get("slot")
    if slot not in ("weapon", "armor"):
        return None, definition.get("modifiers", [])
    properties = {"slot": "hands" if slot == "weapon" else "body"}
    if slot == "weapon":
        properties.update(role="weapon", weapon_type=definition.get("weapon_type", "melee"),
                          hands_required=LEGACY_HAND_UNITS.get(identity, 1),
                          weapon_attack=definition.get("attack", 0))
    raw = definition.get("modifiers", ())
    if not isinstance(raw, (list, tuple)):
        return properties, raw
    modifiers = list(raw)
    if slot != "weapon" and definition.get("attack", 0):
        modifiers.append({"target": "stat.attack", "op": "add", "value": definition["attack"], "scope": "equipped"})
    if definition.get("defense", 0):
        modifiers.append({"target": "stat.defense", "op": "add", "value": definition["defense"], "scope": "equipped"})
    for key, value in definition.get("recovery_bonus", {}).items():
        modifiers.append({"target": "recovery." + key, "op": "add", "value": value, "scope": "equipped"})
    return properties, modifiers


def snapshot(profile, items=None):
    items = ITEMS if items is None else items
    selected = []
    for sequence, identity in enumerate(profile.get("equipment", {}).values(), 1):
        if identity:
            selected.append(item_snapshot(identity, items[identity], sequence=sequence))
    # legacy에는 Entity ID가 없으므로 외부 영속 참조를 만들지 않는다.
    return EquipmentSnapshot(tuple(selected), tuple(selected), source="legacy")


def recovery_modifiers(identities, items):
    from world.modifiers import Modifier

    return tuple(Modifier("recovery." + key, "add", value, "equipped")
                 for identity in identities
                 for key, value in (items or {}).get(identity, {}).get("recovery_bonus", {}).items())


def equip(profile, identity, expected_slot=None):
    from world.item_entities.policy import can_item_operation

    definition = ITEMS[identity]
    slot = definition.get("slot")
    if slot not in ("weapon", "armor"):
        reject("장착할 수 있는 장비가 아닙니다.")
    if expected_slot is not None and slot != expected_slot:
        reject(f"{definition['name']} {'무장' if slot == 'weapon' else '착용'}을 사용하세요.")
    if profile["inventory"].get(identity, 0) < 1:
        reject("소지품에 없는 장비입니다.")
    if not can_item_operation(identity, "equip"):
        reject("이 아이템은 장착할 수 없습니다.")
    previous = profile["equipment"].get(slot)
    if previous and previous != identity:
        reject("자동 장비 교체는 하지 않습니다. 먼저 기존 장비를 해제하세요.")
    candidate = {**profile, "equipment": {**profile["equipment"], slot: identity}}
    validate_loadout(snapshot(candidate).items)
    profile["equipment"][slot] = identity
    refresh_legacy_context(profile)


def unequip(profile, identity, expected_slot):
    from world.item_entities.policy import can_item_operation

    slot = ITEMS[identity].get("slot")
    if slot != expected_slot or slot not in ("weapon", "armor"):
        reject(f"{ITEMS[identity]['name']}: {'해제' if slot == 'weapon' else '벗어'}를 사용하세요.")
    if profile["equipment"].get(slot) != identity:
        reject("현재 사용 중인 장비가 아닙니다.")
    if not can_item_operation(identity, "unequip"):
        reject("이 아이템은 해제할 수 없습니다.")
    profile["equipment"][slot] = None
    refresh_legacy_context(profile)
