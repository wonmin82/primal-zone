"""시간 구간의 회복 기여와 정기 지급을 분리하는 DB 비의존 계산."""

from math import floor

from world import equipment as eq
from world import modifiers

RECOVERY_INTERVAL = 10
RESOURCES = ("hp", "mental")


def player_rates(values, combat=False, room=None, equipment=(), items=None, snapshot=None):
    bonus = (room or {}).get("recovery", {}) if not combat else {}
    rates = {
        "hp": (0 if combat else 2 + values["max_hp"] / 60) + bonus.get("hp_per_minute", 0),
        "mental": 4 + values["max_mental"] / 20 + bonus.get("mental_per_minute", 0),
    }
    from world.equipment_legacy import recovery_modifiers

    selected = snapshot.modifiers if snapshot is not None else recovery_modifiers(equipment, items)
    return {key: modifiers.apply("recovery." + key + "_per_minute", value, selected)
            for key, value in rates.items()}


def enemy_rate(max_hp):
    return 8 + max_hp / 15


def initialize(now):
    return {"updated_at": now, "boundary": floor(now / RECOVERY_INTERVAL) * RECOVERY_INTERVAL,
            "ready": {key: 0.0 for key in RESOURCES},
            "credit": {key: 0.0 for key in RESOURCES}}


def accrue(state, now, rates, effects=()):
    """경계 이전은 ready, 마지막 경계 이후는 credit. 실제 자원은 바꾸지 않는다."""
    start = state["updated_at"]
    if now <= start:
        return
    boundary = floor(now / RECOVERY_INTERVAL) * RECOVERY_INTERVAL
    points = {start, now}
    if start < boundary < now:
        points.add(boundary)
    for effect in effects:
        for key in ("started_at", "expires_at"):
            if start < effect[key] < now:
                points.add(effect[key])
    if boundary > state["boundary"]:
        for resource in RESOURCES:
            state["ready"][resource] += state["credit"][resource]
            state["credit"][resource] = 0.0
    ordered = sorted(points)
    for left, right in zip(ordered, ordered[1:]):
        bucket = "ready" if right <= boundary else "credit"
        for resource in RESOURCES:
            rate = rates.get(resource, 0) + sum(
                effect.get(resource + "_per_minute", 0) for effect in effects
                if effect["started_at"] <= left < effect["expires_at"]
            )
            state[bucket][resource] += (right - left) * rate / 60
    state["updated_at"] = now
    state["boundary"] = boundary


def clamp(profile, values):
    state = profile.get("recovery")
    for resource in RESOURCES:
        maximum = values["max_" + resource]
        profile[resource] = min(maximum, max(0, profile[resource]))
        if state and profile[resource] == maximum:
            state["ready"][resource] = state["credit"][resource] = 0.0


def commit(profile, values):
    """accrue로 이미 경계를 통과한 기여만 정수 자원으로 지급한다."""
    state = profile["recovery"]
    before = tuple(profile[key] for key in RESOURCES)
    for resource in RESOURCES:
        amount = floor(state["ready"][resource] + 1e-9)
        profile[resource] += amount
        state["ready"][resource] = max(0.0, state["ready"][resource] - amount)
    clamp(profile, values)
    return before != tuple(profile[key] for key in RESOURCES)


def accrue_player(profile, values, room, items, now):
    state = profile.setdefault("recovery", initialize(now))
    rates = player_rates(values, bool(profile.get("combat_target")), room,
                         snapshot=eq.recovery_context(profile, items))
    # 가득 찬 동안의 기여는 미래 피해를 미리 회복할 수 없다.
    full = [key for key in RESOURCES if profile[key] >= values["max_" + key]]
    accrue(state, now, rates, profile.get("recovery_effects", ()))
    # 만료까지의 기여가 ready/credit에 반영된 뒤에만 제거한다.
    profile["recovery_effects"] = [effect for effect in profile.get("recovery_effects", ())
                                   if effect["expires_at"] > min(now, state["updated_at"])]
    for key in full:
        state["ready"][key] = state["credit"][key] = 0.0
    clamp(profile, values)


def needs_tick(profile, values, room, items, now):
    rates = player_rates(values, bool(profile.get("combat_target")), room,
                         snapshot=eq.recovery_context(profile, items))
    effects = profile.get("recovery_effects", ())
    for key in RESOURCES:
        if profile[key] < values["max_" + key] and (
            rates[key] > 0 or profile.get("recovery", {}).get("ready", {}).get(key, 0) >= 1
            or any(effect["started_at"] <= now < effect["expires_at"] and effect.get(key + "_per_minute", 0) > 0
                   for effect in effects)
        ):
            return True
    return False


def next_wakeup(profile, values, room, items, now):
    if needs_tick(profile, values, room, items, now):
        return next_boundary(now)
    starts = [effect["started_at"] for effect in profile.get("recovery_effects", ())
              if now < effect["started_at"] < effect["expires_at"] and any(
                  profile[key] < values["max_" + key] and effect.get(key + "_per_minute", 0) > 0
                  for key in RESOURCES)]
    return min(starts, default=None)


def next_boundary(now):
    return (floor(now / RECOVERY_INTERVAL) + 1) * RECOVERY_INTERVAL
