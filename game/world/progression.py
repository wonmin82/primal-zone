"""장기 성장과 기술 수치의 단일 정의. 저장·네트워크에 의존하지 않는다."""

from math import ceil, prod

ATTRIBUTE_CAP = 20
ATTRIBUTES = {
    "strength": {"name": "힘", "description": "투자 2점마다 공격 +1"},
    "agility": {"name": "민첩", "description": "투자 3점마다 방어 +1"},
    "constitution": {"name": "체질", "description": "투자 1점마다 최대 HP +4"},
    "wisdom": {"name": "지혜", "description": "투자 1점마다 최대 정신력 +4 · 치료량 +1"},
}
SKILLS = {
    "attack": {"name": "공격", "max_rank": 30, "type": "passive", "group": "기초", "description": "최종 물리 피해 증가"},
    "defense": {"name": "방어", "max_rank": 20, "type": "passive", "group": "기초", "description": "고정 방어 후 피해 비율 감소"},
    "heavy": {"name": "강타", "max_rank": 20, "type": "active", "group": "공격", "description": "총기 외 무기로 다음 공격 강화"},
    "shooting": {"name": "사격", "max_rank": 20, "type": "active", "group": "공격", "description": "총기로 방어를 관통하는 공격"},
    "insight": {"name": "간파", "max_rank": 10, "type": "preparation", "group": "공격", "description": "공격 한 차례를 포기하고 대상의 약점 분석"},
    "suppress": {"name": "견제", "max_rank": 10, "type": "active", "group": "전술·지원", "description": "다음 공격으로 대상의 공격력 감소"},
    "heal": {"name": "치료", "max_rank": 20, "type": "active", "group": "전술·지원", "description": "정신력으로 자신 또는 같은 방 파티원 치료"},
    "breathing": {"name": "호흡", "max_rank": 10, "type": "preparation", "group": "전술·지원", "description": "공격 한 차례를 포기하고 정신력 회복"},
}
for identity, data in SKILLS.items():
    data.update(id=identity, base_rank=1, action_type=identity)

TOTAL_SKILL_TRAINING = sum(data["max_rank"] - 1 for data in SKILLS.values())
# The cap follows the current basic curriculum, not an eternal level rule.
MAX_LEVEL = TOTAL_SKILL_TRAINING + 1
MENTAL_COSTS = {"heavy": (8, 45), "shooting": (6, 35), "insight": (8, 50), "suppress": (6, 45), "heal": (10, 60)}


def base_stats(level):
    level = max(1, min(MAX_LEVEL, level))
    # Preserve the opening ten levels, then slow growth for a long progression.
    if level <= 10:
        return {"max_hp": 60 + (level - 1) * 10, "base_max_mental": 40 + (level - 1) * 5,
                "attack": 7 + (level - 1) * 2, "defense": (level - 1) // 2}
    return {"max_hp": 150 + (level - 10) * 3, "base_max_mental": 85 + (level - 10) * 2,
            "attack": 25 + (level - 10) // 4, "defense": 4 + (level - 10) // 5}


def attribute_points(level):
    return level * 2 + 2 if level <= 10 else min(ATTRIBUTE_CAP * len(ATTRIBUTES), 22 + (level - 10) // 2)


def mental_cost(skill, level):
    if skill not in MENTAL_COSTS:
        return 0
    minimum, per_thousand = MENTAL_COSTS[skill]
    # Wisdom increases the usable reserve; it must not increase the cost too.
    return max(minimum, (base_stats(level)["base_max_mental"] * per_thousand + 999) // 1000)


def cooldown(skill, rank):
    if skill == "heavy":
        return 7.5 if rank <= 7 else 7.0 if rank <= 14 else 6.5
    if skill == "breathing":
        return 30 if rank <= 3 else 27 if rank <= 6 else 24 if rank <= 9 else 20
    return {"shooting": 5, "heal": 10, "insight": 10, "suppress": 10}.get(skill, 0)


def attack_multiplier(rank):
    return 1 + (rank - 1) * 0.005


def defense_reduction(rank):
    return (rank - 1) * 0.008


def physical_multiplier(skill, rank):
    return 1.80 + (rank - 1) * 0.03 if skill == "heavy" else 1.15 + (rank - 1) * 0.015 if skill == "shooting" else 0.90 if skill == "suppress" else 1.0


def shooting_penetration(rank):
    return 0.05 + (rank - 1) * (0.15 / 19)


def insight_effect(rank):
    return {"penetration": 0.25 + (rank - 1) * 0.02, "bonus": 0.05 + (rank - 1) * 0.01}


def combined_penetration(first, second):
    # Independent penetration leaves the product of the two unpierced fractions.
    return 1 - (1 - first) * (1 - second)


def suppression_effect(rank, boss=False):
    return {"rank": rank, "reduction": (0.10 + (rank - 1) * 0.01) * (0.5 if boss else 1), "attacks": 1 + (rank - 1) // 3}


def apply_suppression(effects, source_id, rank, boss=False):
    """Replace only this source's effect; IDs remain strings across serialization."""
    updated = {str(source): dict(effect) for source, effect in (effects or {}).items()}
    source = str(source_id)
    current = updated.get(source)
    if not current:
        status = "applied"
        updated[source] = suppression_effect(rank, boss)
    elif rank > current["rank"]:
        status = "upgraded"
        updated[source] = suppression_effect(rank, boss)
    elif rank == current["rank"]:
        status = "refreshed"
        updated[source] = {**current, "attacks": suppression_effect(rank, boss)["attacks"]}
    else:
        status = "preserved"
    return updated, status


def combined_suppression(effects):
    return 1 - prod(1 - effect["reduction"] for effect in (effects or {}).values() if effect["attacks"] > 0)


def consume_suppressions(effects):
    """Call once per attack event, never once per hit or AoE recipient."""
    return {str(source): {**effect, "attacks": effect["attacks"] - 1}
            for source, effect in (effects or {}).items() if effect["attacks"] > 1}


def healing_amount(maximum, rank, wisdom):
    return maximum * (80 + (rank - 1) * 5) // 1000 + wisdom


def breathing_amount(maximum, rank):
    return maximum * (72 + (rank - 1) * 6) // 900


def remaining_seconds(deadline, now):
    return max(0, ceil(deadline - now))
