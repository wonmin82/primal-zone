"""WorldLifecycle가 소유하는 환경 저장/발행 경계. 조회는 상태를 저장하지 않는다."""

from copy import deepcopy
from random import Random
from time import time

from evennia.utils.dbserialize import deserialize

from world import environment as model
from world import text as ft
from world.content import REGIONS, ROOM_REGION, ROOMS
from world.multiplayer import after_change, world_change


def lifecycle_script():
    from typeclasses.scripts import WorldLifecycle

    return WorldLifecycle.objects.filter(db_key="primal_world_lifecycle").first()


def snapshot_for(room, observed_at=None):
    observed_at = time() if observed_at is None else observed_at
    zone = room.db.zone_id if room else None
    if zone not in ROOMS:
        return None
    script = lifecycle_script()
    state = deserialize(script.db.environment) if script else None
    # 아직 서버 bootstrap 전인 fixture/비게임 Room 조회도 쓰기 없이 처리한다.
    state = state or model.new_environment(observed_at, Random(0))
    return model.snapshot(state, zone, observed_at)


def reconcile_environment(now, restart=False):
    script = lifecycle_script()
    if not script:
        return
    try:
        with world_change():
            before = deserialize(script.db.environment)
            state = deepcopy(before) if before else model.new_environment(now)
            missing = set(model.WEATHER_ZONES) - set(state["zones"])
            if missing:
                initial = model.new_environment(now)
                state["zones"].update({zone: initial["zones"][zone] for zone in missing})
            after = model.reconcile(state, now)
            if before != after:
                script.db.environment = after
            if before and not restart:
                changed = {
                    zone
                    for zone, data in after["zones"].items()
                    if zone in before["zones"]
                    and (
                        data["weather"] != before["zones"][zone]["weather"]
                        or after["period"] != before["period"]
                    )
                }
                if changed:
                    after_change(lambda: publish_changes(after, changed, now))
    except Exception:
        script.attributes.reset_cache()
        raise


def publish_changes(state, zones, observed_at):
    from typeclasses.explorers import Explorer

    for player in Explorer.objects.all():
        region = ROOM_REGION.get(player.zone)
        if player.sessions.count() and region and REGIONS[region]["weather_zone"] in zones:
            environment = model.snapshot(state, player.zone, observed_at)
            player.msg(ft.token("muted", model.description(environment)))
    # 웹 상태는 같은 reconcile_world() sweep의 기존 push_state 경로로 갱신한다.
