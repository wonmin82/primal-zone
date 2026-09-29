"""승강기 표시·정류 층 규칙과 공용 Room 이동. DB 접근은 동작 시에만 한다."""

from world import rules
from world import text as ft
from world.content.elevator import ELEVATOR_DEFAULT_STOP, ELEVATOR_ROOM, ELEVATOR_STOPS


def normalized_stop(value):
    return value if isinstance(value, str) and value in ELEVATOR_STOPS else ELEVATOR_DEFAULT_STOP


def stop_for_room(zone):
    return next((key for key, stop in ELEVATOR_STOPS.items() if stop["room"] == zone), None)


def controls(zone, current=None):
    """텍스트·웹이 함께 사용하는 현재 장소의 동작. 방향 출구와 독립적이다."""
    if zone == ELEVATOR_ROOM:
        current = normalized_stop(current)
        return {
            "inside": True,
            "current_stop": current,
            "current_floor": ELEVATOR_STOPS[current]["label"],
            "actions": [
                {"label": stop["label"], "command": stop["label"]}
                for stop in ELEVATOR_STOPS.values()
            ] + [{"label": "내려", "command": "내려"}],
        }
    if stop_for_room(zone):
        return {"inside": False, "actions": [{"label": "승강기", "command": "승강기"}]}
    return None


def snapshot(room):
    if room is None:
        return None
    zone = room.db.zone_id
    return controls(zone, room.db.current_stop if zone == ELEVATOR_ROOM else None)


def presentation(room):
    state = snapshot(room)
    if not state:
        return []
    if not state["inside"]:
        return [ft.text("승강기 문이 있다. ", ft.token("command", "승강기"), "로 호출하고 탑승할 수 있다.")]
    return [
        ft.text("현재 위치: ", ft.token("object", state["current_floor"])),
        ft.actions([action["command"] for action in state["actions"]]),
    ]


def arrival_message(previous, target):
    order = list(ELEVATOR_STOPS)
    motion = "위로" if order.index(target) > order.index(previous) else "아래로"
    return ft.text(
        "문이 닫히고 승강기가 ", motion, " 움직인다. 잠시 후 ",
        ft.token("object", ELEVATOR_STOPS[target]["label"]), "에 멈추고 문이 열린다.",
    )


def elevator_room():
    from world.bootstrap import get_room

    room = get_room(ELEVATOR_ROOM)
    if room is None:
        raise rules.RuleError("승강기를 이용할 수 없습니다.")
    return room


def set_stop(room, stop):
    """같은 층은 저장하지 않고, 기존 승객은 Room 안에 그대로 둔다."""
    from world.multiplayer import after_change

    previous = normalized_stop(room.db.current_stop)
    if previous == stop:
        return False
    passengers = [obj for obj in room.contents if hasattr(obj, "push_state")]
    room.db.current_stop = stop
    message = arrival_message(previous, stop)
    for passenger in passengers:
        after_change(lambda player=passenger: player.msg(message))
    return True


def board(player):
    from world.multiplayer import after_change, world_change

    with world_change():
        stop = stop_for_room(player.zone)
        if stop is None:
            raise rules.RuleError("승강기는 지원동 중앙 복도와 옥상에서 이용할 수 있습니다.")
        rules.require_peace(player.profile())
        room = elevator_room()
        moved = set_stop(room, stop)
        if not player.move_to(room, move_type="elevator"):
            raise rules.RuleError("승강기에 탑승하지 못했습니다.")
        message = "승강기를 호출했다. 문이 열리고 안으로 들어갔다." if moved else "승강기 문이 열리고 안으로 들어갔다."
        after_change(lambda: player.msg(ft.text(message)))


def select_stop(player, stop):
    from world.multiplayer import after_change, world_change

    with world_change():
        if player.zone != ELEVATOR_ROOM or stop not in ELEVATOR_STOPS:
            raise rules.RuleError("승강기 안에서 조작반을 사용하세요.")
        rules.require_peace(player.profile())
        if not set_stop(player.location, stop):
            after_change(lambda: player.msg(ft.text(
                "승강기는 이미 ", ft.token("object", ELEVATOR_STOPS[stop]["label"]),
                "에 있다. 문이 열려 있다.",
            )))

        _disembark(player, stop)


def _disembark(player, stop):
    from world.bootstrap import get_room

    destination = get_room(ELEVATOR_STOPS[stop]["room"])
    if destination is None:
        raise rules.RuleError("이 층에 내릴 수 없습니다.")
    if not player.move_to(destination, move_type="elevator"):
        raise rules.RuleError("승강기에서 내리지 못했습니다.")


def disembark(player):
    from world.multiplayer import world_change

    with world_change():
        if player.zone != ELEVATOR_ROOM:
            raise rules.RuleError("승강기 안에서 내릴 수 있습니다.")
        rules.require_peace(player.profile())
        stop = normalized_stop(player.location.db.current_stop)
        _disembark(player, stop)
