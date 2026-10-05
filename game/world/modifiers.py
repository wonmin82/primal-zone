"""장비 modifier의 순수 계산 계약. 저장·화면 문자열에 의존하지 않는다."""

from dataclasses import dataclass
from math import isfinite, prod
from numbers import Real

TARGETS = {
    "weapon.attack": (0, None),
    "stat.attack": (0, None),
    "stat.defense": (0, None),
    "stat.max_hp": (1, None),
    "stat.max_mental": (1, None),
    "recovery.hp_per_minute": (0, None),
    "recovery.mental_per_minute": (0, None),
    "skill.heavy.damage": (0, None),
    "skill.shooting.damage": (0, None),
    "skill.shooting.penetration": (0, 1),
    "skill.insight.penetration": (0, 1),
    "skill.insight.damage": (0, None),
    "skill.suppress.reduction": (0, 1),
    "skill.heal.amount": (0, None),
    "skill.breathing.amount": (0, None),
}
OPERATIONS = ("add", "multiply")
SCOPES = ("equipped", "active_weapon")


@dataclass(frozen=True)
class Modifier:
    target: str
    op: str
    value: float
    scope: str


def numeric(value):
    return isinstance(value, Real) and not isinstance(value, bool) and isfinite(value)


def modifier_errors(data):
    if not isinstance(data, dict):
        return ["modifier는 구조화된 객체여야 합니다."]
    errors = []
    if set(data) != {"target", "op", "value", "scope"}:
        errors.append("modifier는 target/op/value/scope 필드로 작성해야 합니다.")
    if not isinstance(data.get("target"), str) or data["target"] not in TARGETS:
        errors.append("알 수 없는 modifier target입니다.")
    if data.get("op") not in OPERATIONS:
        errors.append("알 수 없는 modifier op입니다.")
    if data.get("scope") not in SCOPES:
        errors.append("알 수 없는 modifier scope입니다.")
    value = data.get("value")
    if not numeric(value) or (data.get("op") == "multiply" and value < 0):
        errors.append("modifier value는 유한한 수이며 multiply는 0 이상이어야 합니다.")
    return errors


def apply(target, base, modifiers=()):
    """add를 합산한 뒤 모든 multiply를 곱하고 target의 경계에서 한 번 clamp한다."""
    minimum, maximum = TARGETS[target]
    selected = [modifier for modifier in modifiers if modifier.target == target]
    value = (base + sum(m.value for m in selected if m.op == "add")) * prod(
        m.value for m in selected if m.op == "multiply"
    )
    return max(minimum, value) if maximum is None else min(maximum, max(minimum, value))
