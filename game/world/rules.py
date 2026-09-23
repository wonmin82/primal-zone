"""Pure gameplay rules: no database, networking or Evennia imports."""

from copy import deepcopy
from random import Random

from world.content import ENEMIES, EQUIPMENT_ACTIONS, EXCHANGE, ITEMS, SHOP
from world.progression import (
    ATTRIBUTES,
    PROFICIENCIES,
    PROFICIENCY_MAX_RANK,
    PROFICIENCY_XP_PER_RANK,
    SAFE_HEAL_TRAINING_CAP,
    SKILLS,
)
from world.quests import progress_defaults

MAX_LEVEL = 10
PROFILE_VERSION = 4


class RuleError(ValueError):
    """A player-facing rejection that must not change saved state."""


def new_profile():
    return {
        "version": PROFILE_VERSION,
        **growth_defaults(),
        "xp": 0,
        "hp": 60,
        "credits": 20,
        "inventory": {"machete": 1, "vest": 1, "bandage": 3},
        "equipment": {"weapon": "machete", "armor": "vest"},
        "kills": 0,
        "quests": progress_defaults(),
        "discoveries": {},
        "visited": ["dock"],
        "combat_target": None,
        "queued_action": "attack",
        "next_attack_at": 0,
        "heavy_ready_at": 0,
        "guard_until": 0,
        "player_round": 0,
    }


def xp_threshold(level):
    return sum(40 + step * 20 for step in range(1, level))


def level_of(profile):
    return max(level for level in range(1, MAX_LEVEL + 1) if profile["xp"] >= xp_threshold(level))


def stats(profile):
    level = level_of(profile)
    equipped = [ITEMS[item] for item in profile["equipment"].values()]
    return {
        "level": level,
        "max_hp": 60 + (level - 1) * 10 + allocated(profile, "constitution") * 4,
        "attack": (
            7
            + (level - 1) * 2
            + sum(item.get("attack", 0) for item in equipped)
            + allocated(profile, "strength") // 2
            + proficiency_rank(profile, "weapon") // 3
        ),
        "defense": (
            (level - 1) // 2
            + sum(item.get("defense", 0) for item in equipped)
            + allocated(profile, "agility") // 3
        ),
    }


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
    return after["level"] - before["level"]


def require_peace(profile):
    if profile.get("combat_target"):
        raise RuleError("전투 중입니다. 먼저 승리하거나 도주하세요.")


def equip(profile, item_id, expected_slot=None):
    require_peace(profile)
    if profile["inventory"].get(item_id, 0) < 1:
        raise RuleError("가방에 없는 장비입니다.")
    slot = ITEMS[item_id]["slot"]
    if slot not in EQUIPMENT_ACTIONS:
        raise RuleError("무기와 방어구만 장착할 수 있습니다.")
    if expected_slot is not None and slot != expected_slot:
        name = ITEMS[item_id]["name"]
        kind = "무기" if slot == "weapon" else "방어구"
        raise RuleError(f"{name}: {kind}입니다. '{name} {EQUIPMENT_ACTIONS[slot]}'을 사용하세요.")
    profile["equipment"][slot] = item_id


def buy(profile, item_id, exchange=False):
    require_peace(profile)
    prices = EXCHANGE if exchange else SHOP
    if item_id not in prices:
        raise RuleError("취급하지 않는 물건입니다.")
    price = prices[item_id]
    if exchange:
        consume(profile, "scrap", price)
    elif profile["credits"] < price:
        raise RuleError("크레딧이 부족합니다.")
    else:
        profile["credits"] -= price
    add_item(profile, item_id)


def heal(profile, training_cap=SAFE_HEAL_TRAINING_CAP):
    maximum = stats(profile)["max_hp"]
    if profile["hp"] >= maximum:
        raise RuleError("이미 체력이 가득합니다.")
    consume(profile, "bandage")
    amount = min(
        ITEMS["bandage"]["heal"]
        + allocated(profile, "wisdom") * 2
        + (skill_rank(profile, "heal") - 1) * 5
        + proficiency_rank(profile, "medicine") // 2,
        maximum - profile["hp"],
    )
    profile["hp"] += amount
    train_proficiency(profile, "medicine", amount, training_cap)
    return amount


def queue_action(profile, action, now=None):
    from time import time

    now = time() if now is None else now
    if not profile.get("combat_target"):
        raise RuleError("진행 중인 교전이 없습니다.")
    if action not in ("heavy", "guard", "heal"):
        raise RuleError("알 수 없는 전투 행동입니다.")
    if action == "heavy" and now < profile["heavy_ready_at"]:
        raise RuleError("강타가 아직 준비되지 않았습니다.")
    if action == "heal":
        if not profile["inventory"].get("bandage", 0):
            raise RuleError("붕대가 없습니다.")
        if profile["hp"] >= stats(profile)["max_hp"]:
            raise RuleError("체력이 가득합니다.")
    profile["queued_action"] = action


def player_attack(profile, enemy_id, now, interval, rng=None):
    """플레이어 입력만 계산한다. 적 HP, 반격, 보상은 소유하지 않는다."""
    rng = rng or Random()
    action = profile["queued_action"]
    profile["queued_action"] = "attack"
    profile["player_round"] += 1
    profile["next_attack_at"] = now + interval
    if action == "heal":
        try:
            amount = heal(profile, ENEMIES[enemy_id]["training_cap"])
            return 0, {"action": "heal", "amount": amount}
        except RuleError as error:
            return 0, {"action": "error", "message": str(error)}
    multiplier = 1.0
    if action == "heavy" and now >= profile["heavy_ready_at"]:
        multiplier = 1.8 + (skill_rank(profile, "heavy") - 1) * 0.2
        profile["heavy_ready_at"] = now + SKILLS["heavy"]["cooldown"]
    if action == "guard":
        profile["guard_until"] = now + interval * 1.1
    damage = max(
        1,
        int((stats(profile)["attack"] + rng.randint(-1, 2)) * multiplier)
        - ENEMIES[enemy_id]["defense"],
    )
    return damage, {"action": "heavy" if multiplier > 1 else "guard" if action == "guard" else "attack"}


def enemy_attack(profile, enemy_id, enemy_round, now, rng=None):
    """독립된 적 차례의 피해와 구조 여부를 구조화된 값으로 반환한다."""
    rng = rng or Random()
    enemy = ENEMIES[enemy_id]
    damage = max(1, enemy["attack"] + rng.randint(-1, 1) - stats(profile)["defense"])
    charged = bool(enemy.get("special_period") and enemy_round % enemy["special_period"] == 0)
    if charged:
        damage *= 2
    unguarded = damage
    if profile["guard_until"] > now:
        damage = max(
            1,
            damage // (2 + skill_rank(profile, "guard"))
            - proficiency_rank(profile, "defense") // 3,
        )
    prevented = unguarded - damage
    train_proficiency(profile, "defense", prevented, enemy["training_cap"])
    profile["hp"] -= damage
    defeated = profile["hp"] <= 0
    if defeated:
        profile["credits"] -= min(profile["credits"], 10)
        profile["hp"] = stats(profile)["max_hp"]
    return {"damage": damage, "charged": charged, "defeated": defeated, "prevented": prevented}


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


def reward_shares(xp, credits, groups):
    """그룹 기여 비례 → 그룹 안에서는 참여자에게 균등 배분한다."""
    weights = {key: sum(members.values()) for key, members in groups.items()}
    pools = [weighted_split(amount, weights) for amount in (xp, credits)]
    result = {}
    for key, members in groups.items():
        equal = {identity: 1 for identity in members}
        shares = [weighted_split(pool[key], equal) for pool in pools]
        for identity in members:
            result[identity] = {"xp": shares[0][identity], "credits": shares[1][identity]}
    return result


def growth_defaults():
    return {
        "attributes": {key: {"base": 10, "allocated": 0} for key in ATTRIBUTES},
        "proficiencies": {key: {"xp": 0} for key in PROFICIENCIES},
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
            "guard_until",
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
    if version < PROFILE_VERSION:
        result["version"] = PROFILE_VERSION
    return result


def allocated(profile, attribute):
    return profile.get("attributes", {}).get(attribute, {}).get("allocated", 0)


def skill_rank(profile, skill):
    return profile.get("skills", {}).get(skill, SKILLS[skill]["base_rank"])


def proficiency_rank(profile, proficiency):
    xp = profile.get("proficiencies", {}).get(proficiency, {}).get("xp", 0)
    return min(PROFICIENCY_MAX_RANK, xp // PROFICIENCY_XP_PER_RANK)


def train_proficiency(profile, proficiency, effect, cap):
    if effect <= 0:
        return
    entry = profile["proficiencies"][proficiency]
    ceiling = min(PROFICIENCY_MAX_RANK, cap) * PROFICIENCY_XP_PER_RANK
    if entry["xp"] < ceiling:
        entry["xp"] += 1


def point_pools(profile):
    attribute_total = level_of(profile) * 2 + 2
    skill_total = level_of(profile) + 1
    attribute_spent = sum(allocated(profile, key) for key in ATTRIBUTES)
    skill_spent = sum(
        sum(
            data["point_cost"][rank]
            for rank in range(data["base_rank"] + 1, skill_rank(profile, key) + 1)
        )
        for key, data in SKILLS.items()
    )
    return {
        "attribute_total": attribute_total,
        "attribute_spent": attribute_spent,
        "attribute_points": attribute_total - attribute_spent,
        "skill_total": skill_total,
        "skill_spent": skill_spent,
        "skill_points": skill_total - skill_spent,
    }


def require_training(profile, safe):
    require_peace(profile)
    if not safe:
        raise RuleError("안전한 부두의 탐사대 훈련관에게서만 훈련할 수 있습니다.")


def allocate_attribute(profile, attribute, amount=1, *, safe=False):
    require_training(profile, safe)
    if attribute not in ATTRIBUTES or type(amount) is not int or amount <= 0:
        raise RuleError("특성과 양의 정수 포인트를 지정하세요. 예: 힘 1 배분")
    if point_pools(profile)["attribute_points"] < amount:
        raise RuleError("특성 포인트가 부족합니다.")
    profile["attributes"][attribute]["allocated"] += amount
    profile["hp"] = min(profile["hp"], stats(profile)["max_hp"])


def learn_skill(profile, skill, *, safe=False):
    require_training(profile, safe)
    if skill not in SKILLS:
        raise RuleError("배울 기술을 지정하세요.")
    data = SKILLS[skill]
    rank = skill_rank(profile, skill) + 1
    if rank > data["max_rank"]:
        raise RuleError("이미 최고 Rank입니다.")
    if level_of(profile) < data["requirements"][rank]:
        raise RuleError(f"레벨 {data['requirements'][rank]}부터 배울 수 있습니다.")
    if point_pools(profile)["skill_points"] < data["point_cost"][rank]:
        raise RuleError("기술점수가 부족합니다.")
    if profile["credits"] < data["credit_cost"][rank]:
        raise RuleError("크레딧이 부족합니다.")
    profile["credits"] -= data["credit_cost"][rank]
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
    profile.clear()
    profile.update(draft)


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
    profile["discoveries"]["jungle_cache"] = True


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
        "proficiencies": [
            {
                "id": key,
                "name": name,
                "xp": profile["proficiencies"][key]["xp"],
                "rank": proficiency_rank(profile, key),
                "max_rank": PROFICIENCY_MAX_RANK,
            }
            for key, name in PROFICIENCIES.items()
        ],
        "skills": [skill_state(profile, key) for key in SKILLS],
    }


def skill_state(profile, key):
    data = SKILLS[key]
    rank = skill_rank(profile, key)
    next_rank = rank + 1
    maximum = rank == data["max_rank"]
    points = 0 if maximum else data["point_cost"][next_rank]
    credits = 0 if maximum else data["credit_cost"][next_rank]
    level = 0 if maximum else data["requirements"][next_rank]
    return {
        "id": key,
        "name": data["name"],
        "description": data["description"],
        "rank": rank,
        "max_rank": data["max_rank"],
        "next_points": points,
        "next_credits": credits,
        "required_level": level,
        "can_learn": not maximum
        and level_of(profile) >= level
        and point_pools(profile)["skill_points"] >= points
        and profile["credits"] >= credits,
    }
