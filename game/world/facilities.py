"""개인 임무와 독립된 공용 시설 전력. WorldLifecycle attribute를 원자적으로 저장한다."""

from evennia.utils.dbserialize import deserialize

from world.content import ROOMS
from world.environment_state import lifecycle_script
from world.facility_state import new_facility_state as new_facility_state
from world.facility_state import normalize_facility_state
from world.multiplayer import after_change, world_change


def light_for(zone):
    script = lifecycle_script()
    state = normalize_facility_state(deserialize(script.db.facilities) if script else None)["states"]
    return max((entry["strength"] for entry in ROOMS[zone].get("facility_lights", [])
                if entry.get("always_on") or state.get(entry.get("power"), False)), default=0)


def reconcile_facilities():
    """명시적인 lifecycle transaction에서만 기존 형식을 저장한다."""
    script = lifecycle_script()
    if script:
        with world_change():
            before = deserialize(script.db.facilities)
            after = normalize_facility_state(before)
            if before != after:
                script.db.facilities = after


def restore_outpost_power(caller):
    from world import rules

    script = lifecycle_script()
    try:
        with world_change():
            if not script:
                from evennia import create_script
                from typeclasses.scripts import WorldLifecycle

                script = create_script(WorldLifecycle, autostart=False)
            state = normalize_facility_state(deserialize(script.db.facilities))
            previous = state["states"]["outpost_power"]
            profile = caller.profile()
            rules.require_peace(profile)
            if profile["quests"]["radio_tower"]["generator_fixed"]:
                # 이전 버전에서 개인 복구를 마친 캐릭터도 새 공용 조명을 가동할 수 있다.
                # 개인 보상/부품/flag를 다시 처리하지 않는다.
                if previous:
                    raise rules.RuleError("이미 발전기를 복구했습니다.")
            else:
                caller.change(rules.fix_generator)
            state["states"]["outpost_power"] = True
            script.db.facilities = state
            after_change(lambda: push_lighting("outpost_power" if not previous else None))
    except Exception:
        if script:
            script.attributes.reset_cache()
        raise


def push_lighting(activated=None):
    from typeclasses.explorers import Explorer

    from world import text as ft

    for player in Explorer.objects.all():
        if player.sessions.count():
            if activated and any(entry.get("power") == activated for entry in ROOMS.get(player.zone, {}).get("facility_lights", [])):
                player.msg(ft.token("muted", "주변의 오래된 시설 조명이 하나둘 켜진다."))
            player.push_state()
