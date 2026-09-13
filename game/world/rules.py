"""Pure gameplay rules: no database, networking or Evennia imports."""

from copy import deepcopy
from random import Random

from world.content import ENEMIES, EXCHANGE, ITEMS, SHOP

MAX_LEVEL = 10


class RuleError(ValueError):
    """A player-facing rejection that must not change saved state."""


def new_profile():
    return {
        "version": 1,
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
        "encounter": None,
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
    if profile["encounter"]:
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


def start_encounter(profile, enemy_id):
    if profile["encounter"]:
        if profile["encounter"]["enemy"] != enemy_id:
            raise RuleError("현재 상대부터 처리하세요.")
        return
    profile["encounter"] = {
        "enemy": enemy_id,
        "hp": ENEMIES[enemy_id]["hp"],
        "round": 0,
        "heavy_ready": 1,
        "action": "attack",
    }


def queue_action(profile, action):
    encounter = profile["encounter"]
    if not encounter:
        raise RuleError("먼저 공격할 대상을 선택하세요.")
    if action not in ("heavy", "guard", "heal"):
        raise RuleError("알 수 없는 전투 행동입니다.")
    if action == "heavy" and encounter["round"] + 1 < encounter["heavy_ready"]:
        raise RuleError("강타는 아직 준비되지 않았습니다.")
    if action == "heal":
        if not profile["inventory"].get("bandage", 0):
            raise RuleError("붕대가 없습니다.")
        if profile["hp"] >= stats(profile)["max_hp"]:
            raise RuleError("이미 체력이 가득합니다.")
    encounter["action"] = action


def combat_round(original, rng=None):
    """Resolve exactly one round and return a new snapshot plus its messages.

    Rewards and encounter clearing happen in the same snapshot. Calling again
    on a completed encounter cannot grant a second reward.
    """
    profile = deepcopy(original)
    encounter = profile["encounter"]
    if not encounter:
        return profile, []
    rng = rng or Random()
    enemy = ENEMIES[encounter["enemy"]]
    player = stats(profile)
    encounter["round"] += 1
    turn = encounter["round"]
    action = encounter.pop("action", "attack")
    encounter["action"] = "attack"
    messages = []
    if action == "heal":
        try:
            messages.append(f"붕대로 체력 {heal(profile)} 회복. 이번 공격은 쉽니다.")
        except RuleError as error:
            messages.append(str(error))
    else:
        attack = player["attack"]
        if action == "heavy" and turn >= encounter["heavy_ready"]:
            attack = int(attack * 1.8)
            encounter["heavy_ready"] = turn + 3
        damage = max(1, attack + rng.randint(-1, 2) - enemy["defense"])
        encounter["hp"] = max(0, encounter["hp"] - damage)
        label = "강타" if action == "heavy" else "공격"
        messages.append(
            f"{label}! {enemy['name']}에게 {damage} 피해. [적 {encounter['hp']}/{enemy['hp']}]"
        )
    if encounter["hp"] <= 0:
        profile["encounter"] = None
        profile["kills"] += 1
        profile["credits"] += enemy["credits"]
        levels = gain_xp(profile, enemy["xp"])
        add_item(profile, "scrap")
        messages.append(f"승리! 경험치 +{enemy['xp']} · 크레딧 +{enemy['credits']} · 회수부품 +1")
        if rng.random() < enemy["chance"]:
            add_item(profile, enemy["drop"])
            messages.append(f"전리품 발견: {ITEMS[enemy['drop']]['name']}! 가방에서 확인하세요.")
        if enemy.get("boss"):
            profile["boss_defeated"] = True
            messages.append("능선이 조용해졌다. 부두로 귀환하여 윤대장에게 보고하자.")
        if levels:
            messages.append(f"레벨 상승! Lv.{level_of(profile)}")
        return profile, messages
    damage = max(1, enemy["attack"] + rng.randint(-1, 1) - player["defense"])
    if enemy.get("boss") and turn % 3 == 0:
        damage *= 2
        messages.append("우두머리가 돌진한다!")
    if action == "guard":
        damage = max(1, damage // 3)
        messages.append("방어 자세로 피해를 줄였다.")
    profile["hp"] = max(0, profile["hp"] - damage)
    messages.append(
        f"{enemy['name']}의 공격: {damage} 피해. [체력 {profile['hp']}/{player['max_hp']}]"
    )
    if profile["hp"] <= 0:
        loss = min(profile["credits"], 10)
        profile["credits"] -= loss
        profile["hp"] = player["max_hp"]
        profile["encounter"] = None
        messages.append(
            f"탐사대가 구조했습니다. 복구 비용 {loss} 크레딧. 장비와 경험치는 유지됩니다."
        )
        return profile, messages + ["__return_home__"]
    if enemy.get("boss") and turn % 3 == 2:
        messages.append("우두머리가 몸을 낮춘다. 다음 공격은 돌진! 지금 '방어'하세요.")
    return profile, messages


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
