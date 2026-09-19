"""Pure gameplay rules: no database, networking or Evennia imports."""

from random import Random

from world.content import ENEMIES, EXCHANGE, ITEMS, SHOP

MAX_LEVEL = 10


class RuleError(ValueError):
    """A player-facing rejection that must not change saved state."""


def new_profile():
    return {
        "version": 2,
        "xp": 0,
        "hp": 60,
        "credits": 20,
        "inventory": {"machete": 1, "vest": 1, "bandage": 3},
        "equipment": {"weapon": "machete", "armor": "vest"},
        "kills": 0,
        "quest_started": False,
        "record_read": False,
        "generator_fixed": False,
        "boss_defeated": False,
        "quest_claimed": False,
        "cache_claimed": False,
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
        "max_hp": 60 + (level - 1) * 10,
        "attack": 7 + (level - 1) * 2 + sum(item.get("attack", 0) for item in equipped),
        "defense": (level - 1) // 2 + sum(item.get("defense", 0) for item in equipped),
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


def equip(profile, item_id):
    require_peace(profile)
    if profile["inventory"].get(item_id, 0) < 1:
        raise RuleError("가방에 없는 장비입니다.")
    slot = ITEMS[item_id]["slot"]
    if slot not in ("weapon", "armor"):
        raise RuleError("무기와 방어구만 착용할 수 있습니다.")
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


def heal(profile):
    maximum = stats(profile)["max_hp"]
    if profile["hp"] >= maximum:
        raise RuleError("이미 체력이 가득합니다.")
    consume(profile, "bandage")
    amount = min(ITEMS["bandage"]["heal"], maximum - profile["hp"])
    profile["hp"] += amount
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
            amount = heal(profile)
            return 0, f"붕대로 체력 {amount} 회복."
        except RuleError as error:
            return 0, str(error)
    multiplier = 1.0
    if action == "heavy" and now >= profile["heavy_ready_at"]:
        multiplier = 1.8
        profile["heavy_ready_at"] = now + interval * 3
    if action == "guard":
        profile["guard_until"] = now + interval * 1.1
    damage = max(
        1,
        int((stats(profile)["attack"] + rng.randint(-1, 2)) * multiplier)
        - ENEMIES[enemy_id]["defense"],
    )
    return damage, f"{ENEMIES[enemy_id]['name']}에게 {damage} 피해."


def enemy_attack(profile, enemy_id, enemy_round, now, rng=None):
    """독립된 적 차례의 피해와 구조 여부를 구조화된 값으로 반환한다."""
    rng = rng or Random()
    enemy = ENEMIES[enemy_id]
    damage = max(1, enemy["attack"] + rng.randint(-1, 1) - stats(profile)["defense"])
    charged = bool(enemy.get("boss") and enemy_round % 3 == 0)
    if charged:
        damage *= 2
    if profile["guard_until"] > now:
        damage = max(1, damage // 3)
    profile["hp"] -= damage
    defeated = profile["hp"] <= 0
    if defeated:
        profile["credits"] -= min(profile["credits"], 10)
        profile["hp"] = stats(profile)["max_hp"]
    return {"damage": damage, "charged": charged, "defeated": defeated}


def fix_generator(profile):
    require_peace(profile)
    if not profile["quest_started"]:
        raise RuleError("먼저 부두에서 윤대장에게 임무를 받으세요.")
    if profile["generator_fixed"]:
        raise RuleError("이미 발전기를 복구했습니다.")
    if not profile["record_read"]:
        raise RuleError("관리동의 정비기록을 먼저 조사하세요.")
    consume(profile, "scrap", 3)
    profile["generator_fixed"] = True
    gain_xp(profile, 50)


def claim_quest(profile):
    require_peace(profile)
    if profile["quest_claimed"]:
        raise RuleError("이미 임무 보상을 받았습니다.")
    if not (profile["quest_started"] and profile["generator_fixed"] and profile["boss_defeated"]):
        raise RuleError("발전기 복구와 능선의 우두머리 처치가 필요합니다.")
    profile["quest_claimed"] = True
    profile["credits"] += 100
    gain_xp(profile, 100)
    add_item(profile, "bandage", 3)
