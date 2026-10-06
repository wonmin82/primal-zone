"""드롭 선택과 encounter HP 곡선. DB와 무관한 계산이다."""

from random import Random

from world.content.loot_v1 import LOOT


def updated_enemy_hp(old_hp, old_max, maximum, state, has_combatants):
    """정의 갱신 때 full/idle만 새 최대 체력 기준 full로 보존한다."""
    if state == "alive" and not has_combatants and old_hp >= old_max:
        return maximum
    return min(old_hp, maximum)


def choice(options, value):
    total = 0
    for identity, weight in options:
        total += weight
        if value < total:
            return identity
    return None


def roll_loot(enemy_id, rng=None):
    rng = rng or Random()
    definition = LOOT[enemy_id]
    result = []
    if "resource" in definition:
        chance, options = definition["resource"]
        if rng.random() < chance:
            identity = choice(options, rng.random())
            low, high = definition.get("quantities", {}).get(identity, (1, 1))
            result.append({"id": identity, "quantity": rng.randint(low, high)})
    if "special" in definition:
        identity = choice(definition["special"], rng.random())
        if identity:
            entry = {"id": identity, "quantity": 1}
            if identity in definition.get("firearms", {}):
                magazine, low, high = definition["firearms"][identity]
                entry["acquisition"] = {"mode": "partial", "magazine_definition": magazine, "rounds": rng.randint(low, high)}
            result.append(entry)
    if "trophy" in definition:
        result.append({"id": definition["trophy"], "quantity": 1})
    return result


def boss_hp(base, participants):
    return int(base * (1 + .75 * (max(1, participants) - 1)))
