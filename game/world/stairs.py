"""중앙 공간의 인접 층 이동. 승강기 층 목록을 공유하며 방향 Exit는 만들지 않는다."""

from world import rules
from world.content.elevator import ELEVATOR_STOPS
from world.elevator import stop_for_room


def controls(zone):
    stop = stop_for_room(zone)
    if stop is None:
        return []
    order = list(ELEVATOR_STOPS)
    index = order.index(stop)
    return [
        {
            "label": f"계단 {action}",
            "command": f"계단 {action}",
            "destination": ELEVATOR_STOPS[order[index + step]]["room"],
        }
        for action, step in (("올라", 1), ("내려", -1))
        if 0 <= index + step < len(order)
    ]


def move(player, action):
    from world.bootstrap import get_room
    from world.multiplayer import world_change

    with world_change():
        rules.require_peace(player.profile())
        target = next(
            (value for value in controls(player.zone) if value["command"] == f"계단 {action}"), None
        )
        if target is None:
            raise rules.RuleError(
                "이곳에서는 그 방향으로 계단을 이용할 수 없습니다. '계단 올라' 또는 '계단 내려'를 입력하세요."
            )
        room = get_room(target["destination"])
        if room is None or not player.move_to(room, move_type="stairs"):
            raise rules.RuleError("계단으로 이동하지 못했습니다.")
