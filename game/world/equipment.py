"""장비 snapshot·슬롯·정의 검증. ORM과 Evennia에 의존하지 않는 domain."""

from dataclasses import dataclass

from world.modifiers import Modifier, modifier_errors, numeric

SLOT_CAPACITY = {
    "hands": 2, "head": 1, "neck": 1, "body": 1, "gloves": 1,
    "waist": 1, "legs": 1, "feet": 1, "ring": 2, "accessory": 1,
}
SLOT_LABELS = {
    "hands": "손", "head": "머리", "neck": "목", "body": "몸", "gloves": "장갑",
    "waist": "허리", "legs": "다리", "feet": "발", "ring": "반지", "accessory": "장신구",
}
HAND_ROLES = {"weapon", "shield", "offhand"}
WEAPON_TYPES = ("melee", "firearm")


def reject(message):
    from world.rules import RuleError

    raise RuleError(message)


def definition_parts(identity, definition):
    from world.equipment_legacy import definition_parts as legacy_parts

    if "equipment_properties" in definition:
        return definition["equipment_properties"], definition.get("modifiers", [])
    return legacy_parts(identity, definition)


def definition_errors(identity, definition):
    properties, modifiers = definition_parts(identity, definition)
    errors = []
    if properties is not None:
        if not isinstance(properties, dict):
            errors.append("equipment_properties는 객체여야 합니다.")
        else:
            slot = properties.get("slot")
            if not isinstance(slot, str) or slot not in SLOT_CAPACITY:
                errors.append("알 수 없는 장비 slot입니다.")
            if definition.get("stackable"):
                errors.append("장비는 비스택이어야 합니다.")
            if slot == "hands":
                role = properties.get("role")
                if not isinstance(role, str) or role not in HAND_ROLES:
                    errors.append("손 장비의 role이 올바르지 않습니다.")
                units = properties.get("hands_required")
                if type(units) is not int or units not in (1, 2):
                    errors.append("hands_required는 1 또는 2여야 합니다.")
                if role == "weapon" and properties.get("weapon_type") not in WEAPON_TYPES:
                    errors.append("무기의 weapon_type이 올바르지 않습니다.")
                if role != "weapon" and units != 1:
                    errors.append("방패와 보조 도구는 한 손 장비여야 합니다.")
            elif any(key in properties for key in ("role", "hands_required", "weapon_type")):
                errors.append("손 이외의 장비에 hand 속성을 사용할 수 없습니다.")
            attack = properties.get("weapon_attack", 0)
            if not numeric(attack) or attack < 0:
                errors.append("weapon_attack은 유한한 0 이상의 수여야 합니다.")
            elif attack and properties.get("role") != "weapon":
                errors.append("weapon_attack base는 무기에만 사용할 수 있습니다.")
    if not isinstance(modifiers, (list, tuple)):
        errors.append("modifiers는 목록이어야 합니다.")
    else:
        for modifier in modifiers:
            errors.extend(modifier_errors(modifier))
        if modifiers and properties is None:
            errors.append("장비 modifier에는 equipment_properties가 필요합니다.")
    return [f"{identity}: {error}" for error in errors]


@dataclass(frozen=True)
class EquipmentItem:
    definition_id: str
    name: str
    aliases: tuple
    identity: str | None
    sequence: int
    quantity: int
    slot: str | None
    location: str
    role: str | None = None
    weapon_type: str | None = None
    hands_required: int = 0
    weapon_attack: float = 0
    modifiers: tuple = ()
    state_summary: str = ""
    firearm_family: str | None = None

    @property
    def equip_action(self):
        return "무장" if self.role == "weapon" else "착용"

    @property
    def remove_action(self):
        return "해제" if self.role == "weapon" else "벗어"


def item_snapshot(identity, definition, *, item_id=None, sequence=0, quantity=1, location="equipment", slot=None, state_summary=""):
    errors = definition_errors(identity, definition)
    if errors:
        reject(" / ".join(errors))
    properties, modifiers = definition_parts(identity, definition)
    properties = properties or {}
    return EquipmentItem(
        identity, definition["name"], tuple(definition.get("aliases", ())),
        str(item_id) if item_id is not None else None, sequence, quantity,
        slot or properties.get("slot"), location, properties.get("role"),
        properties.get("weapon_type"), properties.get("hands_required", 0),
        properties.get("weapon_attack", 0), tuple(Modifier(**modifier) for modifier in modifiers),
        state_summary, definition.get("firearm_family"),
    )


def validate_loadout(items):
    """해당 슬롯에 들어갈 수 있는 정의·수량·수용량·손 조합을 한 번에 검사한다."""
    for item in items:
        if item.slot not in SLOT_CAPACITY or item.quantity != 1:
            reject("장비 slot과 개별 수량을 확인하세요.")
    for slot, capacity in SLOT_CAPACITY.items():
        selected = [item for item in items if item.slot == slot]
        usage = sum(item.hands_required for item in selected) if slot == "hands" else len(selected)
        if usage > capacity:
            reject(f"{SLOT_LABELS[slot]} 장비 공간이 부족합니다. 먼저 기존 장비를 해제하세요.")
        if slot == "hands" and len(selected) > 1 and not any(item.role == "weapon" for item in selected):
            reject("두 손 장비 조합에는 최소 하나의 무기가 필요합니다.")


@dataclass(frozen=True)
class EquipmentSnapshot:
    items: tuple = ()
    carried: tuple = ()
    active_id: str | None = None
    source: str = "item_entities"

    @property
    def active(self):
        if self.source == "legacy":
            # legacy의 단일 weapon slot은 곧 주무기다. 영속 UUID를 만들지 않는다.
            return next((item for item in self.items if item.role == "weapon"), None)
        return next((item for item in self.items if item.role == "weapon" and item.identity == self.active_id), None)

    @property
    def modifiers(self):
        return tuple(
            modifier for item in self.items for modifier in item.modifiers
            if modifier.scope == "equipped" or item is self.active
        )

    @property
    def hand_usage(self):
        return sum(item.hands_required for item in self.items if item.slot == "hands")

    def label(self, item):
        candidates = [entry for entry in self.carried if entry.definition_id == item.definition_id]
        index = candidates.index(item) + 1 if item in candidates else 1
        return item.name if index == 1 else f"{item.name} {index}"


class EquipmentProfile(dict):
    """계산용 일시 context. 저장할 때 일반 dict로 바꾸어 profile schema를 유지한다."""

    def __init__(self, profile, equipment_context):
        super().__init__(profile)
        self.equipment_context = equipment_context


def context(profile, snapshot=None):
    if snapshot is not None:
        return snapshot
    attached = getattr(profile, "equipment_context", None)
    if attached is not None:
        return attached
    from world.equipment_legacy import snapshot as legacy_snapshot

    return legacy_snapshot(profile)


def recovery_context(profile, items):
    """순수 fixture의 별도 registry도 legacy adapter에서만 해석한다."""
    attached = getattr(profile, "equipment_context", None)
    if attached is not None:
        return attached
    from world.equipment_legacy import snapshot

    return snapshot(profile, items)


def refresh_legacy_context(profile):
    if isinstance(profile, EquipmentProfile):
        from world.equipment_legacy import snapshot as legacy_snapshot

        profile.equipment_context = legacy_snapshot(profile)


def inventory_rows(profile):
    """텍스트와 Web에서 동일한 snapshot의 selector·착용·주무기 정보를 사용한다."""
    from world.content import ITEMS

    selected = context(profile)
    if selected.source == "item_entities":
        candidates = selected.carried
    else:
        candidates = tuple(item_snapshot(identity, ITEMS[identity],
                                         quantity=count, location="inventory")
                           for identity, count in profile["inventory"].items() if count > 0)
    rows = []
    for item in candidates:
        data = ITEMS[item.definition_id]
        equipped = item.location == "equipment" if selected.source == "item_entities" else any(
            entry.definition_id == item.definition_id for entry in selected.items)
        active = selected.active is not None and (
            selected.active.identity == item.identity if selected.source == "item_entities"
            else selected.active.definition_id == item.definition_id)
        rows.append({"id": item.definition_id, "name": item.name, "selector": selected.label(item),
                     "count": item.quantity, "slot": item.slot or data.get("slot"),
                     "equip_action": item.equip_action if item.slot else None,
                     "remove_action": item.remove_action if item.slot else None,
                     "consume_action": data.get("consume_action"), "equipped": equipped,
                     "active_weapon": active, "weapon": item.role == "weapon",
                     "light_source": data.get("light_source"), "power_source": data.get("power_source"),
                     "state_summary": item.state_summary, "location": item.location})
        if selected.source == "item_entities":
            rows[-1]["firearm"] = bool(data.get("firearm_family"))
            rows[-1]["magazine"] = bool(data.get("magazine"))
            ammo_type = data.get("magazine", {}).get("ammo_type")
            rows[-1]["ammo_name"] = next((entry["name"] for entry in ITEMS.values()
                                          if ammo_type and entry.get("ammo_type") == ammo_type), None)
    return rows


def equipment_rows(profile):
    selected = context(profile)
    return {slot: " · ".join(selected.label(item) + (" [주무기]" if item is selected.active else "")
                             + (f" · {item.state_summary}" if item.state_summary else "")
                             for item in selected.items if item.slot == slot) or None
            for slot in SLOT_CAPACITY}
