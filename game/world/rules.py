"""Pure gameplay rules: no database, networking or Evennia imports."""

from copy import deepcopy
from random import Random

from world import equipment, modifiers, recovery
from world import progression as pg
from world import text as ft
from world.content import (
    ENEMIES,
    ITEMS,
    SALVAGE_CREDIT_RATE,
    SHOP_CATALOGS,
)
from world.progression import ATTRIBUTES, SKILLS
from world.quests import progress_defaults

MAX_LEVEL = pg.MAX_LEVEL
PROFILE_VERSION = 10
DEFEAT_RECOVERY_HP = 1


class RuleError(ValueError):
    """A player-facing rejection that must not change saved state."""


def new_profile():
    return {
        "version": PROFILE_VERSION,
        **growth_defaults(),
        "xp": 0,
        "hp": 60,
        "mental": 40,
        "recovery_effects": [],
        "credits": 20,
        "inventory": {"machete": 1, "vest": 1, "bandage": 3},
        "equipment": {"weapon": "machete", "armor": "vest"},
        "storage": {},
        "command_shortcuts": {},
        "light_sources": {},
        "kills": 0,
        "quests": progress_defaults(),
        "discoveries": {},
        "visited": ["staging_room"],
        "combat_target": None,
        "queued_action": "attack",
        "next_attack_at": 0,
        "heavy_ready_at": 0,
        "skill_ready_at": {},
        "insight": None,
        "heal_target": None,
        "player_round": 0,
    }


def xp_threshold(level):
    return 10 * (level - 1) ** 2 + 50 * (level - 1)


def level_of(profile):
    return max(level for level in range(1, MAX_LEVEL + 1) if profile["xp"] >= xp_threshold(level))


def stats(profile, equipment_context=None):
    level = level_of(profile)
    base = pg.base_stats(level)
    snapshot = equipment.context(profile, equipment_context)
    selected = snapshot.modifiers
    character_attack = modifiers.apply("stat.attack", base["attack"] + allocated(profile, "strength") // 2, selected)
    weapon_attack = modifiers.apply("weapon.attack", snapshot.active.weapon_attack if snapshot.active else 0, selected)
    return {
        "level": level,
        "base_max_mental": base["base_max_mental"],
        "max_hp": int(modifiers.apply("stat.max_hp", base["max_hp"] + allocated(profile, "constitution") * 4, selected)),
        "max_mental": int(modifiers.apply("stat.max_mental", base["base_max_mental"] + allocated(profile, "wisdom") * 4, selected)),
        "character_attack": character_attack,
        "weapon_attack": weapon_attack,
        "attack": character_attack + weapon_attack,
        "defense": modifiers.apply("stat.defense", base["defense"] + allocated(profile, "agility") // 3, selected),
    }


def modified(profile, target, base):
    return modifiers.apply(target, base, equipment.context(profile).modifiers)


def apply_defense(raw_damage, defense, penetration=0, defense_skill_reduction=0):
    """양방향 공통 곡선. 모든 float 계산 후 int로 버림하고 최소 피해 1을 적용한다."""
    effective = max(0, defense) * (1 - min(1, max(0, penetration)))
    damage = raw_damage * 20 / (20 + effective) * (1 - min(1, max(0, defense_skill_reduction)))
    return max(1, int(damage))


def add_item(profile, item_id, quantity=1):
    inventory = profile["inventory"]
    inventory[item_id] = inventory.get(item_id, 0) + quantity


def consume(profile, item_id, quantity=1):
    if profile["inventory"].get(item_id, 0) < quantity:
        raise RuleError(f"{ITEMS[item_id]['name']}이(가) 부족합니다.")
    profile["inventory"][item_id] -= quantity
    if not profile["inventory"][item_id]:
        del profile["inventory"][item_id]


def gain_xp(profile, amount):
    before = stats(profile)
    profile["xp"] += amount
    after = stats(profile)
    profile["hp"] = min(after["max_hp"], profile["hp"] + after["max_hp"] - before["max_hp"])
    profile["mental"] = min(after["max_mental"], profile["mental"] + after["max_mental"] - before["max_mental"])
    recovery.clamp(profile, after)
    return after["level"] - before["level"]


def require_peace(profile):
    if profile.get("combat_target"):
        raise RuleError("전투 중입니다. 먼저 승리하거나 도망하세요.")


def equip(profile, item_id, expected_slot=None):
    from world.equipment_legacy import equip as legacy_equip

    require_peace(profile)
    legacy_equip(profile, item_id, expected_slot)
    recovery.clamp(profile, stats(profile))


def buy(profile, shop_id, item_id):
    require_peace(profile)
    if shop_id not in SHOP_CATALOGS:
        raise RuleError("상점 판매 목록을 확인할 수 없습니다.")
    catalog = SHOP_CATALOGS[shop_id]["purchase_catalog"]
    if item_id not in catalog:
        raise RuleError("취급하지 않는 물건입니다.")
    price = purchase_price(item_id)
    if profile["credits"] < price:
        raise RuleError("보급칩이 부족합니다.")
    profile["credits"] -= price
    add_item(profile, item_id)


def purchase_price(item_id):
    definition = ITEMS.get(item_id, {})
    value = definition.get("purchase_unit_value", definition.get("value"))
    if type(value) is not int or value <= 0:
        raise RuleError("일반 상인이 매매할 수 없는 물건입니다.")
    return value


def resale_price(item_id):
    return max(1, purchase_price(item_id) // 2)


def sell(profile, shop_id, item_id, *, all_items=False, quantity=1):
    from world.content.shops import accepts
    from world.item_entities.policy import can_item_operation
    from world.lighting import discard_device_state_if_unowned

    require_peace(profile)
    if not accepts(shop_id, ITEMS.get(item_id, {})):
        raise RuleError("취급하지 않는 물건입니다.")
    if not can_item_operation(item_id, "sell"):
        raise RuleError("이 물건은 판매할 수 없습니다.")
    price = resale_price(item_id)
    reserved = sum(item_id == identity for identity in profile["equipment"].values())
    available = profile["inventory"].get(item_id, 0) - reserved
    amount = available if all_items else quantity
    if type(amount) is not int or amount <= 0 or amount > available:
        raise RuleError("판매할 수량이 부족합니다. 사용 중인 장비는 먼저 해제하세요.")
    consume(profile, item_id, amount)
    discard_device_state_if_unowned(profile, item_id)
    proceeds = amount * price
    profile["credits"] += proceeds
    return amount, proceeds


def settle_salvage(profile, quantity):
    """소지품의 회수부품만 정산한다. 모든 검증 후 자원과 보급칩을 함께 변경한다."""
    require_peace(profile)
    if type(quantity) is not int or quantity <= 0:
        raise RuleError("정산 수량은 1개 이상의 정수로 지정하세요.")
    if profile["inventory"].get("scrap", 0) < quantity:
        raise RuleError("회수부품이 부족합니다.")
    earned = quantity * SALVAGE_CREDIT_RATE
    consume(profile, "scrap", quantity)
    profile["credits"] += earned
    return earned


def move_item(source, destination, item_id, *, all_items=False, equipment=None):
    """스택 간 이동. 모든 검증 뒤 한 번에 변경하며 장착된 복사본만 남긴다."""
    definition = ITEMS.get(item_id)
    if not definition or not definition["transferable"]:
        raise RuleError("임무에 필요한 물건은 버리거나 전달하거나 보관할 수 없습니다.")
    if source is destination:
        raise RuleError("같은 보관 공간으로 옮길 수 없습니다.")
    reserved = sum(identity == item_id for identity in (equipment or {}).values())
    available = source.get(item_id, 0) - reserved
    if available < 1:
        if reserved:
            raise RuleError("현재 사용 중인 장비입니다. 무기는 먼저 해제하고 방어구는 벗으세요.")
        raise RuleError(f"{definition['name']}이 없습니다.")
    quantity = available if all_items else 1
    remaining = source[item_id] - quantity
    destination[item_id] = destination.get(item_id, 0) + quantity
    if remaining:
        source[item_id] = remaining
    else:
        del source[item_id]
    return quantity


def unequip(profile, item_id, expected_slot):
    from world.equipment_legacy import unequip as legacy_unequip

    require_peace(profile)
    legacy_unequip(profile, item_id, expected_slot)
    recovery.clamp(profile, stats(profile))


def eat_or_drink(profile, item_id, action):
    require_peace(profile)
    definition = ITEMS[item_id]
    supported = definition.get("consume_action")
    if supported != action:
        hint = (
            f"'{definition['name']} {supported}'를 사용하세요."
            if supported
            else "먹거나 마실 수 없는 물건입니다."
        )
        raise RuleError(hint)
    missing = stats(profile)["max_hp"] - profile["hp"]
    if missing <= 0:
        raise RuleError("이미 체력이 가득합니다.")
    consume(profile, item_id)
    restored = min(missing, definition["heal"])
    profile["hp"] += restored
    recovery.clamp(profile, stats(profile))
    return restored


def use_bandage(profile):
    maximum = stats(profile)["max_hp"]
    if profile["hp"] >= maximum:
        raise RuleError("이미 체력이 가득합니다.")
    consume(profile, "bandage")
    amount = min(ITEMS["bandage"]["heal"], maximum - profile["hp"])
    profile["hp"] += amount
    recovery.clamp(profile, stats(profile))
    return amount


def validate_skill_action(profile, action, now, target_profile=None):
    if action not in ("heavy", "shooting", "insight", "suppress", "heal", "breathing", "bandage"):
        raise RuleError("알 수 없는 전투 행동입니다.")
    active = equipment.context(profile).active
    firearm = active is not None and active.weapon_type == "firearm"
    if action == "heavy" and firearm:
        raise RuleError("총기를 들고는 강타를 사용할 수 없다.")
    if action == "shooting" and not firearm:
        raise RuleError("총기를 장착해야 사격할 수 있다.")
    ready = profile.get("skill_ready_at", {}).get(action, 0)
    if action == "heavy":
        ready = max(ready, profile.get("heavy_ready_at", 0))
    if now < ready:
        name = SKILLS[action]["name"]
        raise RuleError(f"{name}{ft.particle(name, '을/를')} 다시 사용하려면 {pg.remaining_seconds(ready, now)}초 더 기다려야 한다.")
    cost = pg.mental_cost(action, level_of(profile))
    if profile["mental"] < cost:
        name = SKILLS[action]["name"]
        raise RuleError(f"{name}{ft.particle(name, '을/를')} 사용하려면 정신력이 {cost} 필요하다.")
    target = profile if target_profile is None else target_profile
    if action in ("heal", "bandage") and target["hp"] >= stats(target)["max_hp"]:
        raise RuleError("이미 체력이 가득합니다.")
    if action == "bandage" and not profile["inventory"].get("bandage"):
        raise RuleError("붕대가 없습니다.")
    if action == "breathing" and profile["mental"] >= stats(profile)["max_mental"]:
        raise RuleError("이미 정신력이 가득합니다.")


def commit_skill_cost(profile, action, now):
    cost = pg.mental_cost(action, level_of(profile))
    profile["mental"] -= cost
    deadline = now + pg.cooldown(action, skill_rank(profile, action))
    profile.setdefault("skill_ready_at", {})[action] = deadline
    if action == "heavy":
        profile["heavy_ready_at"] = deadline
    recovery.clamp(profile, stats(profile))
    return cost


def support_action(profile, action, now, target_profile=None):
    validate_skill_action(profile, action, now, target_profile)
    if action == "bandage":
        return {"action": action, "amount": use_bandage(profile), "cost": 0}
    cost = commit_skill_cost(profile, action, now)
    if action == "heal":
        target = profile if target_profile is None else target_profile
        amount = min(stats(target)["max_hp"] - target["hp"], int(modified(profile, "skill.heal.amount", pg.healing_amount(stats(profile)["max_hp"], skill_rank(profile, action), allocated(profile, "wisdom")))))
        target["hp"] += amount
        recovery.clamp(target, stats(target))
    else:
        amount = min(stats(profile)["max_mental"] - profile["mental"], int(modified(profile, "skill.breathing.amount", pg.breathing_amount(stats(profile)["max_mental"], skill_rank(profile, action)))))
        profile["mental"] += amount
        recovery.clamp(profile, stats(profile))
    return {"action": action, "amount": amount, "cost": cost}


def queue_action(profile, action, now=None, target_profile=None):
    from time import time

    now = time() if now is None else now
    if not profile.get("combat_target"):
        raise RuleError("진행 중인 교전이 없습니다.")
    validate_skill_action(profile, action, now, target_profile)
    profile["queued_action"] = action


def consume_combat_opportunity(profile, now, interval):
    profile["queued_action"] = "attack"
    profile["player_round"] += 1
    profile["next_attack_at"] = now + interval


def player_attack(profile, enemy_id, now, interval, rng=None, target_profile=None, *, shot_available=True):
    """One opportunity, regardless of whether it attacks or prepares/supports."""
    rng = rng or Random()
    action = profile["queued_action"]
    consume_combat_opportunity(profile, now, interval)
    from world.firearms import needs_shot

    active = equipment.context(profile).active
    shot = needs_shot(action, active.weapon_type if active else None)
    if shot and not shot_available:
        return 0, {"action": "error", "message": "총기에 발사할 탄약이 없다. 재장전하세요.", "shot_fired": False}
    if action in ("heal", "breathing", "bandage"):
        try:
            return 0, {**support_action(profile, action, now, target_profile), "shot_fired": False}
        except RuleError as error:
            return 0, {"action": "error", "message": str(error), "shot_fired": False}
    if action != "attack":
        try:
            validate_skill_action(profile, action, now)
        except RuleError as error:
            return 0, {"action": "error", "message": str(error), "shot_fired": False}
        commit_skill_cost(profile, action, now)
    rank = skill_rank(profile, action) if action in SKILLS else 1
    if action == "insight":
        effect = pg.insight_effect(rank)
        effect["penetration"] = modified(profile, "skill.insight.penetration", effect["penetration"])
        effect["bonus"] = modified(profile, "skill.insight.damage", 1 + effect["bonus"]) - 1
        profile["insight"] = {"target": profile["combat_target"], **effect}
        return 0, {"action": action, **effect, "shot_fired": False}
    insight = profile.get("insight")
    if insight and insight["target"] != profile["combat_target"]:
        profile["insight"] = insight = None
    penetration = modified(profile, "skill.shooting.penetration", pg.shooting_penetration(rank)) if action == "shooting" else 0
    bonus = 1.0
    if insight:
        penetration = pg.combined_penetration(insight["penetration"], penetration)
        bonus += insight["bonus"]
        profile["insight"] = None
    multiplier = pg.physical_multiplier(action, rank)
    raw = (stats(profile)["attack"] + rng.randint(-1, 2)) * multiplier
    if action in ("heavy", "shooting"):
        raw = modified(profile, f"skill.{action}.damage", raw)
    raw *= bonus * pg.attack_multiplier(skill_rank(profile, "attack"))
    damage = apply_defense(raw, ENEMIES[enemy_id]["defense"], penetration)
    outcome = {"action": action, "insight": bool(insight), "shot_fired": shot}
    if action == "suppress":
        outcome["suppression"] = pg.suppression_effect(rank, bool(ENEMIES[enemy_id].get("boss")))
        outcome["suppression"]["reduction"] = modified(profile, "skill.suppress.reduction", outcome["suppression"]["reduction"])
    return damage, outcome


def enemy_attack(profile, enemy_id, enemy_round, now, rng=None, suppression=0):
    rng = rng or Random()
    enemy = ENEMIES[enemy_id]
    charged = bool(enemy.get("special_period") and enemy_round % enemy["special_period"] == 0)
    raw = (enemy["attack"] + rng.randint(-1, 1)) * (1 - suppression)
    if charged:
        raw *= 2
    damage = apply_defense(raw, stats(profile)["defense"], enemy.get("penetration", 0),
                           pg.defense_reduction(skill_rank(profile, "defense")))
    profile["hp"] -= damage
    return {"damage": damage, "charged": charged, "defeated": profile["hp"] <= 0}


def apply_defeat(profile):
    """패배의 최소 생존 회복과 기존 보급칩 패널티. 일반 의료와 독립이다."""
    if profile["hp"] > 0:
        raise RuleError("패배한 상태가 아닙니다.")
    lost = min(profile["credits"], 10)
    profile["credits"] -= lost
    profile["hp"] = DEFEAT_RECOVERY_HP
    return lost


def _medical_maximum(profile, safe):
    require_peace(profile)
    if not safe:
        raise RuleError("안전한 곳에서만 의료 서비스를 이용할 수 있습니다.")
    maximum = stats(profile)["max_hp"]
    if profile["hp"] >= maximum:
        raise RuleError("이미 체력이 가득합니다.")
    return maximum


def treat(profile, *, safe=False):
    maximum = _medical_maximum(profile, safe)
    restored = maximum - profile["hp"]
    profile["hp"] = maximum
    recovery.clamp(profile, stats(profile))
    return restored


def rest(profile, *, safe=False):
    require_peace(profile)
    if not safe:
        raise RuleError("안전한 곳에서만 의료 서비스를 이용할 수 있습니다.")
    values = stats(profile)
    maximum = values["max_hp"]
    if profile["hp"] >= maximum and profile["mental"] >= values["max_mental"]:
        raise RuleError("이미 체력과 정신력이 가득합니다.")
    restored = maximum - profile["hp"]
    profile["hp"] = maximum
    profile["mental"] = values["max_mental"]
    recovery.clamp(profile, values)
    return restored


def boss_telegraph(enemy_id, enemy_round):
    period = ENEMIES[enemy_id].get("special_period")
    return bool(period and enemy_round % period == period - 1)


def fix_generator(profile):
    require_peace(profile)
    progress = profile["quests"]["radio_tower"]
    if not progress["started"]:
        raise RuleError("먼저 부두에서 윤대장에게 임무를 받으세요.")
    if progress["generator_fixed"]:
        raise RuleError("이미 발전기를 복구했습니다.")
    if not progress["record_read"]:
        raise RuleError("관리동의 정비기록을 먼저 조사하세요.")
    consume(profile, "scrap", 3)
    progress["generator_fixed"] = True
    gain_xp(profile, 50)


def claim_quest(profile):
    require_peace(profile)
    progress = profile["quests"]["radio_tower"]
    if progress["claimed"]:
        raise RuleError("이미 임무 보상을 받았습니다.")
    if not (progress["started"] and progress["generator_fixed"] and progress["boss_defeated"]):
        raise RuleError("발전기 복구와 능선의 우두머리 처치가 필요합니다.")
    progress["claimed"] = True
    profile["credits"] += 100
    gain_xp(profile, 100)
    add_item(profile, "bandage", 3)


def weighted_split(pool, weights):
    """최대 나머지법. 같은 나머지는 키 순서로 결정하여 총량을 보존한다."""
    weights = {key: weight for key, weight in weights.items() if weight > 0}
    total = sum(weights.values())
    if not total:
        return {}
    result = {key: pool * weight // total for key, weight in weights.items()}
    order = sorted(weights, key=lambda key: (-(pool * weights[key] % total), key))
    for key in order[: pool - sum(result.values())]:
        result[key] += 1
    return result


def reward_allocation(amount, groups):
    """그룹 기여 비례 → 그룹 안에서는 참여자에게 균등 배분한다."""
    weights = {key: sum(members.values()) for key, members in groups.items()}
    pools = weighted_split(amount, weights)
    result = {}
    for key, members in groups.items():
        equal = {identity: 1 for identity in members}
        result.update(weighted_split(pools.get(key, 0), equal))
    return result


def reward_shares(xp, credits, groups):
    """기존 규칙 호출자의 호환 형태. 실제 지급 시 XP와 화폐 경로는 분리한다."""
    xp_shares = reward_allocation(xp, groups)
    currency_shares = reward_allocation(credits, groups)
    return {identity: {"xp": amount, "credits": currency_shares[identity]}
            for identity, amount in xp_shares.items()}


def growth_defaults():
    return {
        "attributes": {key: {"base": 10, "allocated": 0} for key in ATTRIBUTES},
        "skills": {key: value["base_rank"] for key, value in SKILLS.items()},
    }


def migrate_profile(profile):
    result = deepcopy(profile)
    version = result.get("version", 1)
    if version < 2:
        result.pop("encounter", None)
        defaults = new_profile()
        for key in (
            "combat_target",
            "queued_action",
            "next_attack_at",
            "heavy_ready_at",
            "player_round",
        ):
            result.setdefault(key, defaults[key])
    if version < 3:
        for key, value in growth_defaults().items():
            result.setdefault(key, value)
    if version < 4:
        progress = progress_defaults()
        legacy = {
            "quest_started": "started", "record_read": "record_read",
            "generator_fixed": "generator_fixed", "boss_defeated": "boss_defeated",
            "quest_claimed": "claimed",
        }
        for old, flag in legacy.items():
            progress["radio_tower"][flag] = bool(result.pop(old, False))
        result["quests"] = progress
        result["discoveries"] = {"supply_cache": bool(result.pop("cache_claimed", False))}
    if version < 8:
        from commands.vocabulary import migrate_shortcuts

        skills = result.get("skills", {})
        if "heal" in skills:
            skills["firstaid"] = skills.pop("heal")
        if result.get("queued_action") == "heal":
            result["queued_action"] = "firstaid"
        result["command_shortcuts"] = migrate_shortcuts(result.get("command_shortcuts", {}))
    if version < PROFILE_VERSION:
        result.setdefault("storage", {})
        result.setdefault("light_sources", {})
        result.setdefault("command_shortcuts", {})
        result["version"] = PROFILE_VERSION
    if version < 9:
        result["mental"] = stats(result)["max_mental"]
        result.setdefault("recovery_effects", [])
    if version < 10:
        # Old curricula are not scaled into new ranks: all earned training is returned.
        result["skills"] = growth_defaults()["skills"]
        result["queued_action"] = "attack"
        result.setdefault("skill_ready_at", {})
        if result.get("heavy_ready_at", 0) > 0:
            result["skill_ready_at"]["heavy"] = max(result["heavy_ready_at"], result["skill_ready_at"].get("heavy", 0))
        result["insight"] = None
        result["heal_target"] = None
        result.pop("guard_until", None)
        result.pop("proficiencies", None)
        from commands.vocabulary import migrate_progression_shortcuts

        result["command_shortcuts"] = migrate_progression_shortcuts(result.get("command_shortcuts", {}))
    normalize_growth(result)
    recovery.clamp(result, stats(result))
    return result


def allocated(profile, attribute):
    return profile.get("attributes", {}).get(attribute, {}).get("allocated", 0)


def skill_rank(profile, skill):
    value = profile.get("skills", {}).get(skill, 1)
    return min(SKILLS[skill]["max_rank"], max(1, value)) if type(value) is int else 1


def normalize_growth(profile):
    # Canonical order makes malformed over-budget records deterministic and idempotent.
    budget = pg.attribute_points(level_of(profile))
    source = profile.get("attributes", {})
    profile["attributes"] = {}
    for key in ATTRIBUTES:
        value = source.get(key, {}).get("allocated", 0)
        value = min(pg.ATTRIBUTE_CAP, budget, max(0, value)) if type(value) is int else 0
        profile["attributes"][key] = {"base": 10, "allocated": value}
        budget -= value
    budget = level_of(profile) - 1
    source = profile.get("skills", {})
    profile["skills"] = {}
    for key, data in SKILLS.items():
        rank = source.get(key, 1)
        rank = min(data["max_rank"], budget + 1, max(1, rank)) if type(rank) is int else 1
        profile["skills"][key] = rank
        budget -= rank - 1
    profile.pop("proficiencies", None)
    profile.pop("guard_until", None)


def point_pools(profile):
    attribute_total = pg.attribute_points(level_of(profile))
    skill_total = level_of(profile) - 1
    attribute_spent = sum(allocated(profile, key) for key in ATTRIBUTES)
    skill_spent = sum(skill_rank(profile, key) - 1 for key in SKILLS)
    return {"attribute_total": attribute_total, "attribute_spent": attribute_spent,
            "attribute_points": max(0, attribute_total - attribute_spent),
            "skill_total": skill_total, "skill_spent": skill_spent,
            "skill_points": max(0, skill_total - skill_spent)}


def require_training(profile, safe):
    require_peace(profile)
    if not safe:
        raise RuleError("안전한 장소의 탐사대 훈련관에게서만 훈련할 수 있습니다.")


def allocate_attribute(profile, attribute, amount=1, *, safe=False):
    require_training(profile, safe)
    if attribute not in ATTRIBUTES or type(amount) is not int or amount <= 0:
        raise RuleError("특성과 양의 정수 포인트를 지정하세요. 예: 힘 1 배분")
    if point_pools(profile)["attribute_points"] < amount:
        raise RuleError("특성 포인트가 부족합니다.")
    if allocated(profile, attribute) + amount > pg.ATTRIBUTE_CAP:
        raise RuleError("특성 추가 투자는 20점이 상한입니다.")
    profile["attributes"][attribute]["allocated"] += amount
    profile["hp"] = min(profile["hp"], stats(profile)["max_hp"])
    profile["mental"] = min(profile["mental"], stats(profile)["max_mental"])
    recovery.clamp(profile, stats(profile))


def learn_skill(profile, skill, *, safe=False):
    require_training(profile, safe)
    if skill not in SKILLS:
        raise RuleError("배울 기술을 지정하세요.")
    data = SKILLS[skill]
    rank = skill_rank(profile, skill) + 1
    if rank > data["max_rank"]:
        raise RuleError("이미 최고 Rank입니다.")
    if point_pools(profile)["skill_points"] < 1:
        raise RuleError("남은 기술 훈련이 없습니다.")
    profile["skills"][skill] = rank


def retrain(profile, scope, *, safe=False):
    require_training(profile, safe)
    if scope not in ("attributes", "skills", "all"):
        raise RuleError("특성 재분배 · 기술 재분배 · 전체 재훈련")
    draft = deepcopy(profile)
    if scope in ("attributes", "all"):
        for entry in draft["attributes"].values():
            entry["allocated"] = 0
    if scope in ("skills", "all"):
        draft["skills"] = growth_defaults()["skills"]
    draft["hp"] = min(profile["hp"], stats(draft)["max_hp"])
    draft["mental"] = min(profile["mental"], stats(draft)["max_mental"])
    recovery.clamp(draft, stats(draft))
    profile.clear()
    profile.update(draft)
    pools = point_pools(profile)
    return {"scope": scope, "attribute_points": pools["attribute_points"], "skill_training": pools["skill_points"]}


def commander_talk(profile):
    require_peace(profile)
    progress = profile["quests"]["radio_tower"]
    if not progress["started"]:
        progress["started"] = True
        return "start"
    if progress["boss_defeated"] and not progress["claimed"]:
        claim_quest(profile)
        return "complete"
    return "progress"


def read_record(profile):
    require_peace(profile)
    profile["quests"]["radio_tower"]["record_read"] = True


def claim_cache(profile):
    require_peace(profile)
    if profile["discoveries"].get("supply_cache"):
        raise RuleError("이미 보급품을 챙겼습니다.")
    add_item(profile, "bandage", 2)
    profile["discoveries"]["supply_cache"] = True


def jungle_talk(profile):
    require_peace(profile)
    if not profile["quests"]["radio_tower"]["claimed"]:
        raise RuleError("먼저 통신탑 복구 임무를 마치세요.")
    progress = profile["quests"]["deep_jungle"]
    if not progress["started"]:
        progress["started"] = True
        return "start"
    if progress["boss_defeated"] and not progress["claimed"]:
        progress["claimed"] = True
        profile["credits"] += 120
        gain_xp(profile, 120)
        add_item(profile, "bandage", 3)
        return "complete"
    return "progress"


def jungle_mark(profile, flag):
    require_peace(profile)
    progress = profile["quests"]["deep_jungle"]
    if not progress["started"]:
        raise RuleError("먼저 밀림 입구에서 선발대 길잡이에게 의뢰를 받으세요.")
    if flag not in ("watch_marked", "road_marked"):
        raise RuleError("조사할 수 없는 표식입니다.")
    newly_marked = not progress[flag]
    cell_acquired = (
        flag == "road_marked"
        and not progress["gate_open"]
        and profile["inventory"].get("jungle_cell", 0) < 1
    )
    if cell_acquired:
        add_item(profile, "jungle_cell")
    progress[flag] = True
    return cell_acquired if flag == "road_marked" else newly_marked


def open_jungle_gate(profile):
    require_peace(profile)
    progress = profile["quests"]["deep_jungle"]
    if progress["gate_open"]:
        raise RuleError("이미 연구구역 문이 열렸습니다.")
    if not (progress["watch_marked"] and progress["road_marked"]):
        raise RuleError("관측소와 수몰 도로의 표식을 모두 확인하세요.")
    if profile["inventory"].get("jungle_cell", 0) < 1:
        raise RuleError("수몰 도로에서 밀림 신호전지를 확보하세요.")
    consume(profile, "jungle_cell")
    progress["gate_open"] = True


def claim_jungle_cache(profile):
    require_peace(profile)
    if profile["discoveries"].get("jungle_cache"):
        raise RuleError("이미 늪지의 보급품을 챙겼습니다.")
    add_item(profile, "bandage", 2)
    add_item(profile, "battery", 2)
    profile["discoveries"]["jungle_cache"] = True


def claim_emergency_light_cache(profile):
    require_peace(profile)
    if profile["discoveries"].get("emergency_light_cache"):
        raise RuleError("이미 비상장비함의 탐사 장비를 챙겼습니다.")
    add_item(profile, "flashlight")
    add_item(profile, "battery", 2)
    profile["discoveries"]["emergency_light_cache"] = True


def growth_state(profile):
    """화면과 정보 명령에서 재사용할 직렬화 가능한 성장 정보."""
    pools = point_pools(profile)
    return {
        **pools,
        "attributes": [
            {
                "id": key,
                **data,
                **profile["attributes"][key],
                "value": profile["attributes"][key]["base"] + allocated(profile, key),
            }
            for key, data in ATTRIBUTES.items()
        ],
        "skills": [skill_state(profile, key) for key in SKILLS],
    }


def skill_state(profile, key):
    data = SKILLS[key]
    rank = skill_rank(profile, key)
    return {"id": key, **data, "rank": rank,
            "can_learn": rank < data["max_rank"] and point_pools(profile)["skill_points"] > 0}
