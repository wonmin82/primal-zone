"""소유 ItemEntity의 공개 정보. 정의와 읽기 전용 상태 snapshot만 표시한다."""

from time import time

from world import equipment as eq
from world import rules
from world import text as ft
from world.content import ITEMS
from world.currency import format_currency
from world.equipment_service import entity_runtime, resolve_item, selector_label, state_summary
from world.item_entities.policy import can_item_operation

TYPE_LABELS = {"weapon": "무기", "equipment": "방어구", "hand_equipment": "손 장비",
               "credential": "출입증", "consumable": "소모품", "tool": "도구",
               "magazine": "탄창", "ammo": "탄약", "resource": "자원", "quest": "임무 물품"}
MODIFIER_LABELS = {
    "weapon.attack": "무기 공격", "stat.attack": "공격", "stat.defense": "방어",
    "stat.max_hp": "최대 HP", "stat.max_mental": "최대 정신력",
    "recovery.hp_per_minute": "분당 HP 회복", "recovery.mental_per_minute": "분당 정신력 회복",
    "skill.heavy.damage": "강타 피해", "skill.shooting.damage": "쏴 피해",
    "skill.shooting.penetration": "쏴 관통", "skill.insight.penetration": "간파 관통",
    "skill.insight.damage": "간파 피해", "skill.suppress.reduction": "견제 감소",
    "skill.heal.amount": "치료 회복량", "skill.breathing.amount": "호흡 회복량",
}
OPERATION_LABELS = {"consume": "사용", "equip": "장착", "unequip": "해제",
                    "drop": "바닥 이동", "store": "보관", "give": "양도", "sell": "판매", "burn": "소각"}


def item_information(character, value, observed_at=None):
    if not entity_runtime(character):
        raise rules.RuleError("아이템 정보는 변환된 ItemEntity 소지품에서 조회합니다. 관리자에게 변환 상태를 확인하세요.")
    item = resolve_item(character, value, "정보")
    definition = ITEMS[item.definition_id]
    label = selector_label(character, item)
    lines = [ft.token("item", definition["name"])]
    if definition.get("aliases"):
        lines.append("별칭: " + " · ".join(definition["aliases"]))
    if definition.get("description"):
        lines.append(definition["description"])
    kind = definition.get("item_type")
    if kind in TYPE_LABELS:
        lines.append("종류: " + TYPE_LABELS[kind])
    lines.append(f"수량 {item.quantity} · {'장착 중' if item.location_kind == 'equipment' else '장전 중' if item.location_kind == 'inside' else '소지 중'}")
    quantity = definition.get("purchase_quantity", 1)
    try:
        purchase = rules.purchase_price(item.definition_id)
    except rules.RuleError:
        purchase = None
    if purchase is not None:
        if quantity > 1:
            unit = "발" if definition.get("ammo_type") else "개"
            # 개당 값은 정의에서 읽고 묶음 총액은 공통 거래 규칙에 맡긴다.
            unit_value = definition.get("purchase_unit_value", definition.get("value"))
            lines.extend(["개당 구매 기준가: " + format_currency(unit_value),
                          f"상점 판매 묶음: {quantity}{unit}",
                          "묶음 구매 기준가: " + format_currency(purchase)])
        else:
            lines.append("기준 구매가: " + format_currency(purchase))
    try:
        resale = rules.resale_price(item.definition_id)
    except rules.RuleError:
        resale = None
    if resale is not None:
        lines.append(("개당 매입 기준가: " if quantity > 1 else "기준 매입가: ") + format_currency(resale))
    properties, modifiers = eq.definition_parts(item.definition_id, definition)
    if properties:
        lines.append("장착 슬롯: " + eq.SLOT_LABELS[properties["slot"]])
        if "hands_required" in properties:
            lines.append(f"필요한 손: {properties['hands_required']}개")
        if "weapon_attack" in properties:
            lines.append(f"무기 기본 공격: {properties['weapon_attack']:g}")
        lines.append("장착 조건: 비전투 상태 · 빈 슬롯과 손 공간 필요 · 자동 교체 없음")
    for modifier in modifiers:
        target = MODIFIER_LABELS[modifier["target"]]
        amount = (f"+{modifier['value']:g}" if modifier["op"] == "add" else f"×{modifier['value']:g}")
        scope = "주무기일 때" if modifier["scope"] == "active_weapon" else "장착 시"
        active = item.location_kind == "equipment" and (modifier["scope"] != "active_weapon" or character.db.active_weapon_item_id == str(item.pk))
        lines.append(f"{target} {amount} ({scope} · {'적용 중' if active else '미적용'})")
    if definition.get("firearm_family"):
        from world.firearm_service import loaded_magazine
        from world.item_states import FIREARM_FAMILIES

        family = definition["firearm_family"]
        lines.append("호환 탄종: " + FIREARM_FAMILIES[family])
        lines.append("호환 탄창: " + " · ".join(data["name"] for data in ITEMS.values() if data.get("magazine", {}).get("family") == family))
        magazine = loaded_magazine(item)
        lines.append("현재 탄창: " + (state_summary(item) if magazine else "없음"))
    if definition.get("magazine"):
        data = definition["magazine"]
        lines.append(f"탄종 {data['ammo_type']} · 용량 {data['capacity']}발 · 잔탄 {item.state['rounds']}발")
        lines.append("호환 총기: " + " · ".join(data['name'] for data in ITEMS.values() if data.get('firearm_family') == definition['magazine']['family']))
    if definition.get("ammo_type"):
        lines.append("탄종: " + definition["ammo_type"])
    if definition.get("light_source"):
        from world.lighting_service import status

        lines.append(status(character, item, time() if observed_at is None else observed_at))
    if definition.get("power_source"):
        data = definition["power_source"]
        lines.append(f"전원 사용 시간: {data['capacity_seconds'] / 60:g}분")
    policy = definition.get("operation_policy", {})
    for operation, text in OPERATION_LABELS.items():
        if operation in policy:
            lines.append(f"{text}: {'허용' if can_item_operation(item, operation) else '제한'}")
    if item.location_kind == "equipment":
        lines.append("이동·양도·판매·소각은 먼저 장비를 해제한 뒤 현재 장소의 규칙을 따릅니다.")
    if definition.get("unique_per_owner"):
        lines.append("소유자별 하나만 보유할 수 있습니다.")
    if kind == "credential":
        lines.append("출입증은 소각 확정이 필요하며 원래 발급자에게 재발급을 요청할 수 있습니다.")
    lines.extend(["", "정의된 기준 가격이며 상인의 취급·매매 가능성을 보장하지 않습니다. 실제 견적은 가치·얼마로 확인하세요."])
    return ft.compact(ft.token("command", "정보"), ft.token("item", label), *lines)
