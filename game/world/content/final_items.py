"""확정된 V1 장비·가격. modifier는 표시 문구 대신 구조화된 수치를 사용한다."""


def add(target, value):
    return {"target": target, "op": "add", "value": value, "scope": "equipped"}


def multiply(target, value):
    return {"target": target, "op": "multiply", "value": value, "scope": "equipped"}


def gear(name, slot, price, *modifiers, role=None, hands=1, attack=0, family=None, tier=1, field=False):
    properties = {"slot": slot}
    if slot == "hands":
        properties.update(role=role, hands_required=hands)
        if role == "weapon":
            properties.update(weapon_type="firearm" if family else "melee", weapon_attack=attack)
    definition = {"name": name, "slot": "weapon" if role == "weapon" else "armor",
                  "item_type": "weapon" if role == "weapon" else ("hand_equipment" if slot == "hands" else "equipment"), "stackable": False,
                  "equipment_properties": properties, "modifiers": list(modifiers), "tier": tier,
                  "value": price, "resale_unit_value": price // 2, "field_only": field}
    if role == "weapon":
        definition["modifiers"] = [{**modifier, "scope": "active_weapon"} for modifier in modifiers]
    if family:
        definition["firearm_family"] = family
        definition["weapon_type"] = "firearm"
    return definition


FINAL_ITEMS = {
    "explorer_machete": gear("탐사용 벌목도", "hands", 10, role="weapon", attack=2, tier=0),
    "expedition_workwear": gear("탐사대 작업복", "body", 10, add("stat.defense", 1), tier=0),
    "cutting_machete": gear("절단마체테", "hands", 55, multiply("skill.heavy.damage", 1.02), role="weapon", attack=4),
    "pioneer_spear": gear("개척창", "hands", 70, multiply("skill.heavy.damage", 1.03), role="weapon", hands=2, attack=6),
    "scout_pistol": gear("정찰권총", "hands", 60, role="weapon", attack=5, family="pistol_9mm"),
    "guard_carbine": gear("경비카빈", "hands", 95, multiply("skill.shooting.damage", 1.02), role="weapon", hands=2, attack=8, family="carbine_556"),
    "folding_shield": gear("접이식방패", "hands", 45, add("stat.defense", 2), role="shield"),
    "portable_analyzer": gear("휴대분석기", "hands", 35, add("skill.insight.penetration", .02), role="offhand"),
    "security_goggles": gear("보안고글", "head", 30, add("stat.max_mental", 4), multiply("skill.insight.damage", 1.01)),
    "expedition_tag": gear("탐사인식표", "neck", 25, add("stat.max_hp", 6), field=True),
    "light_protective_suit": gear("경량방호복", "body", 45, add("stat.defense", 2)),
    "reinforced_vest": gear("강화방호조끼", "body", 70, add("stat.defense", 3), add("stat.max_hp", 6)),
    "shock_absorbing_gloves": gear("충격흡수장갑", "gloves", 30, multiply("skill.heavy.damage", 1.02)),
    "emergency_belt": gear("응급벨트", "waist", 35, add("skill.heal.amount", 3)),
    "reinforced_explorer_pants": gear("보강탐사바지", "legs", 35, add("stat.max_hp", 8)),
    "non_slip_boots": gear("미끄럼방지탐사화", "feet", 30, add("stat.defense", 1)),
    "focus_ring": gear("집중링", "ring", 30, add("stat.max_mental", 4)),
    "protection_ring": gear("방호링", "ring", 35, add("stat.defense", 1)),
    "survival_module": gear("생존모듈", "accessory", 45, add("recovery.hp_per_minute", 1)),
    "jungle_longblade": gear("정글장도", "hands", 110, multiply("skill.heavy.damage", 1.03), role="weapon", attack=7, tier=2),
    "shattering_spear": gear("파쇄창", "hands", 145, multiply("skill.heavy.damage", 1.04), add("skill.suppress.reduction", .01), role="weapon", hands=2, attack=9, tier=2),
    "tactical_pistol": gear("전술권총", "hands", 95, add("skill.shooting.penetration", .01), role="weapon", attack=7, family="pistol_9mm", tier=2),
    "exploration_carbine": gear("탐사카빈", "hands", 140, multiply("skill.shooting.damage", 1.03), role="weapon", hands=2, attack=10, family="carbine_556", tier=2),
    "heavy_rifle": gear("중량소총", "hands", 175, add("skill.shooting.penetration", .03), role="weapon", hands=2, attack=12, family="rifle_762", tier=2),
    "composite_shield": gear("합성방패", "hands", 105, add("stat.defense", 4), add("stat.max_hp", 8), role="shield", tier=2),
    "tactical_analyzer": gear("전술분석단말", "hands", 80, add("skill.insight.penetration", .03), multiply("skill.insight.damage", 1.02), role="offhand", tier=2),
    "emergency_injector": gear("응급주입기", "hands", 80, add("skill.heal.amount", 5), role="offhand", tier=2),
    "tracking_goggles": gear("추적고글", "head", 75, add("stat.max_mental", 6), add("skill.insight.penetration", .03), tier=2),
    "breathing_mask": gear("호흡보조마스크", "head", 95, add("stat.max_mental", 12), add("skill.breathing.amount", 3), tier=2),
    "biomonitor": gear("생체감시장치", "neck", 65, add("stat.max_hp", 10), tier=2),
    "neural_stabilizing_collar": gear("신경안정칼라", "neck", 90, add("stat.max_mental", 8), add("recovery.mental_per_minute", 1), tier=2),
    "tactical_protective_suit": gear("전술방호복", "body", 120, add("stat.defense", 4), add("stat.max_hp", 10), tier=2),
    "heavy_protective_suit": gear("중장방호복", "body", 165, add("stat.defense", 5), add("stat.max_hp", 20), tier=2),
    "strike_assist_gloves": gear("타격보조장갑", "gloves", 65, multiply("skill.heavy.damage", 1.04), tier=2),
    "shooting_stability_gloves": gear("사격안정장갑", "gloves", 60, add("skill.shooting.penetration", .02), tier=2),
    "medical_tactical_belt": gear("의무전술벨트", "waist", 95, add("skill.heal.amount", 5), add("recovery.hp_per_minute", 1), tier=2),
    "suppression_tactical_belt": gear("제압전술벨트", "waist", 60, add("skill.suppress.reduction", .01), tier=2),
    "marsh_protective_pants": gear("습지방호바지", "legs", 85, add("stat.max_hp", 12), add("stat.defense", 1), tier=2),
    "stabilizing_boots": gear("안정화전투화", "feet", 70, add("stat.defense", 1), add("skill.suppress.reduction", .01), tier=2),
    "bio_stability_ring": gear("생체안정링", "ring", 50, add("stat.max_hp", 6), tier=2),
    "mental_focus_ring": gear("정신집중링", "ring", 55, add("stat.max_mental", 6), tier=2),
    "suppression_ring": gear("제압보조링", "ring", 50, add("skill.suppress.reduction", .01), tier=2),
    "medical_ring": gear("의술보조링", "ring", 50, add("skill.heal.amount", 2), tier=2),
    "regeneration_module": gear("재생모듈", "accessory", 75, add("recovery.hp_per_minute", 1), tier=2, field=True),
    "mental_stability_module": gear("정신안정모듈", "accessory", 75, add("recovery.mental_per_minute", 1), tier=2, field=True),
    "tactical_computing_module": gear("전술연산모듈", "accessory", 80, multiply("skill.insight.damage", 1.02), add("skill.suppress.reduction", .01), tier=2, field=True),
    "ridge_predator_mark": gear("능선포식자표식", "neck", 0, add("stat.attack", 1), multiply("skill.heavy.damage", 1.02), tier=2),
    "predator_scale_charm": gear("포식자비늘장식", "accessory", 0, add("stat.defense", 1), add("stat.max_hp", 12), add("stat.max_mental", 8), tier=2),
}

for identity, package in {"scout_pistol": 108, "tactical_pistol": 143, "guard_carbine": 200,
                          "exploration_carbine": 245, "heavy_rifle": 257}.items():
    FINAL_ITEMS[identity]["purchase_unit_value"] = package

for identity in ("ridge_predator_mark", "predator_scale_charm"):
    definition = FINAL_ITEMS[identity]
    definition.pop("value")
    definition.pop("resale_unit_value")
    definition.update(unique_per_owner=True, max_stack=1, transferable=False,
                      operation_policy={key: key in ("equip", "unequip", "store") for key in (
                          "equip", "unequip", "store", "drop", "give", "sell", "burn", "consume", "loot", "load", "unload")})
