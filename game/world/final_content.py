"""최종 콘텐츠의 획득·가격·드롭 불변조건. 값 tuning은 하지 않는다."""

from world.content import ENEMIES, ITEMS, SHOP_CATALOGS
from world.content.integrity import alias_errors
from world.content.item_mapping import BOSS_REWARDS, STARTER_EQUIPMENT
from world.content.loot_v1 import LOOT
from world.firearms import STANDARD_MAGAZINES
from world.item_entities.policy import can_item_operation, definition_errors

FIXED = {"expedition_tag": "supply_cache", "generator_repair_part": "supply_cache", "mental_stability_module": "jungle_cache"}


def acquisition_matrix():
    result = {identity: [] for identity in ITEMS}
    for identity in STARTER_EQUIPMENT:
        result[identity].append("starter")
    for shop, data in SHOP_CATALOGS.items():
        for identity in data["purchase_catalog"]:
            if identity in result:
                result[identity].append(shop)
    for identity, source in FIXED.items():
        result[identity].append(source)
    result["generator_repair_part"].append("migration:generator_unfixed")
    for quest, identity in BOSS_REWARDS.items():
        result[identity].append(quest + ":final_report")
    for enemy, data in LOOT.items():
        options = [*data.get("resource", (0, ()))[1], *data.get("special", ())]
        for identity, _ in options:
            if identity in result:
                result[identity].append(enemy + ":drop")
    return result


def package_costs(identity):
    magazine = ITEMS[STANDARD_MAGAZINES[ITEMS[identity]["firearm_family"]]]
    ammo = next(data for data in ITEMS.values() if data.get("ammo_type") == magazine["magazine"]["ammo_type"])
    return {"package": ITEMS[identity]["purchase_unit_value"], "body_resale": ITEMS[identity]["resale_unit_value"],
            "magazine_resale": magazine["resale_unit_value"], "ammo_resale": magazine["magazine"]["capacity"] * ammo["resale_unit_value"],
            "ammo_buy": magazine["magazine"]["capacity"] * ammo["purchase_unit_value"]}


def errors():
    issues = alias_errors(ITEMS)
    matrix = acquisition_matrix()
    repair = ITEMS.get("generator_repair_part", {})
    if (repair.get("stackable") is not True or repair.get("max_stack") != 3
            or repair.get("transferable") is not False or repair.get("unique_per_owner") is not False
            or any(can_item_operation("generator_repair_part", operation) != (operation == "submit")
                   for operation in ("submit", "drop", "give", "store", "sell", "burn", "consume", "equip", "unequip", "loot", "load", "unload"))
            or any("generator_repair_part" in shop["purchase_catalog"] for shop in SHOP_CATALOGS.values())
            or any("generator_repair_part" in dict(data.get(key, (0, ()))[1] if key == "resource" else data.get(key, ()))
                   for data in LOOT.values() for key in ("resource", "special"))):
        issues.append("generator_repair_part: submit-only 진행 자원 정의/획득 경계 위반")
    for identity, definition in ITEMS.items():
        issues.extend(definition_errors(identity, definition))
        for key in ("value", "purchase_unit_value", "resale_unit_value"):
            if key in definition and (type(definition[key]) is not int or definition[key] < 0):
                issues.append(f"{identity}: 가격이 올바르지 않습니다.")
        if definition.get("tier") in (0, 1, 2) and identity not in BOSS_REWARDS.values() and not matrix[identity]:
            issues.append(f"{identity}: 획득 경로가 없습니다.")
        if definition.get("field_only") and any(identity in shop["purchase_catalog"] for shop in SHOP_CATALOGS.values()):
            issues.append(f"{identity}: field-only 아이템이 구매 목록에 있습니다.")
        if definition.get("firearm_family"):
            cost = package_costs(identity)
            if (cost["package"] <= cost["body_resale"] + cost["magazine_resale"] + cost["ammo_resale"]
                    or cost["package"] - cost["body_resale"] - cost["magazine_resale"] < cost["ammo_buy"]):
                issues.append(f"{identity}: package arbitrage 불변조건 위반")
    for identity in BOSS_REWARDS.values():
        definition = ITEMS[identity]
        if not definition["unique_per_owner"] or any(key in definition for key in ("value", "resale_unit_value", "purchase_unit_value")):
            issues.append(f"{identity}: Boss unique 정의가 올바르지 않습니다.")
        for operation in ("equip", "unequip", "store", "drop", "give", "sell", "burn", "consume", "loot", "load", "unload"):
            if can_item_operation(identity, operation) != (operation in ("equip", "unequip", "store")):
                issues.append(f"{identity}: Boss unique operation policy 위반")
    if set(LOOT) != set(ENEMIES):
        issues.append("enemy/drop 정의 집합이 다릅니다.")
    for enemy, loot in LOOT.items():
        resource = loot.get("resource", (0, ()))
        if not 0 <= resource[0] <= 1 or resource[1] and abs(sum(weight for _, weight in resource[1]) - 1) > 1e-9:
            issues.append(f"{enemy}: 자원 roll 확률/weight 오류")
        special = loot.get("special", ())
        if sum(weight for _, weight in special) > 1 or any(identity not in ITEMS or not 0 < weight <= 1 for identity, weight in (*resource[1], *special)):
            issues.append(f"{enemy}: special/drop 확률 오류")
        if ENEMIES[enemy].get("boss") and special:
            issues.append(f"{enemy}: Boss random equipment drop 금지")
    return issues
