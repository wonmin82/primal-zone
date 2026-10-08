"""실제 Exit의 읽기 전용 목록과 공통 표시. 관찰 hook/lifecycle을 실행하지 않는다."""

from time import time

from world import text as ft
from world.content import DIRECTIONS, ROOMS, ordered_directions
from world.content.directions import PLANAR_DIRECTIONS


def exit_entries(viewer, room=None, observed_at=None, *, reveal_observed=True):
    """나침반·조회·지도·웹이 공유하는 공개 정보. 숨긴 목적지 ID는 반환하지 않는다."""
    from world.access import entry_message
    from world.distant_presentation import DistantViewContext
    from world.observation import can_perceive, context_for

    room = viewer.location if room is None else room
    if room is None:
        return []
    now = time() if observed_at is None else observed_at
    profile = viewer.profile_snapshot()
    context = context_for(viewer, room, now)
    definition = ROOMS.get(room.db.zone_id, {})
    actual = {obj.key: obj for obj in room.exits if can_perceive(obj, context)}
    blocked = definition.get("blocked_exits", {})
    # 특수 출구는 콘텐츠 정의 순서, 정의 밖 사용자 출구는 실제 객체 순서를 유지한다.
    names = dict.fromkeys([*definition.get("exits", {}), *actual, *blocked])
    entries = []
    for name in ordered_directions(names):
        obj = actual.get(name)
        if obj is None:
            if name in blocked:
                entries.append(dict(name=name, exists=False, can_move=False, status="폐쇄",
                                    reason=blocked[name], destination_name="—"))
            continue
        destination = obj.destination
        reason = blocked.get(name) or (entry_message(viewer, destination) if destination else "목적지가 없습니다.")
        entry_allowed = reason is None
        traversable = obj.access(viewer, "traverse")
        # Evennia parser와 같은 생성된 명령의 access()를 사용한다. CmdSet은 저장하지 않는다.
        command_allowed = any(command.access(viewer, "cmd") for command in obj.create_exit_cmdset(obj)
                              if getattr(command, "is_exit", False))
        target_data = ROOMS.get(destination.db.zone_id, {}) if destination else {}
        if reason:
            access = target_data.get("access", {})
            status = ("시설 폐쇄" if name in blocked or access.get("available") is False else
                      "출입증 필요" if access.get("credential") else "임무 조건 미충족")
            if destination is None:
                status = "시설 폐쇄"
        elif not command_allowed or not traversable:
            status, reason = "시설 폐쇄", "출구를 이용할 수 없습니다."
        elif profile.get("combat_target"):
            status, reason = "전투 중 이동 불가", "전투 중에는 이동할 수 없습니다."
        else:
            status = "이동 가능"
        disclosed = False
        if destination and destination.access(viewer, "view"):
            visited = destination.db.zone_id in profile.get("visited", ())
            disclosed = visited
            if not visited and reveal_observed and entry_allowed and command_allowed and traversable:
                observation = DistantViewContext(viewer, room, destination, obj, name, observed_at=now)
                disclosed = getattr(obj, "can_observe_through", lambda context: False)(observation)
        entries.append(dict(name=name, exists=True, can_move=status == "이동 가능", status=status,
                            reason=reason or "", destination_name=(target_data.get("name", destination.key)
                            if disclosed else "미탐사")))
    return entries


def _sentence_lines(entries, width):
    names = [entry["name"] for entry in entries if entry["exists"] and entry["can_move"]]
    if not names:
        return [ft.text("지금은 이동할 수 있는 출구가 없다.")]
    lines, parts = [], [ft.text("갈 수 있는 곳은 ")]
    for index, name in enumerate(names):
        piece = ft.text(ft.token("direction", name), "이다." if index == len(names) - 1 else ",")
        gap = " " if index else ""
        if index and ft.display_width(ft.text(*parts, gap, piece)) > width:
            lines.append(ft.text(*parts))
            parts, gap = [], ""
        parts.extend([gap, piece])
    lines.append(ft.text(*parts))
    return lines


def exit_diagram(entries, text_width=36):
    """3행×3열 ASCII. 오른쪽 문구는 중앙 행에서 시작하며 이름 사이에서만 줄바꿈한다."""
    if isinstance(entries, dict) or all(isinstance(entry, str) for entry in entries):
        entries = [dict(name=name, exists=True, can_move=True) for name in ordered_directions(entries)]
    actual = {entry["name"]: entry for entry in entries if entry["exists"]}
    cells = [[ft.token("muted", ".") for _ in range(3)] for _ in range(3)]
    glyphs = {"북": "|", "북동": "/", "동": "-", "남동": "\\", "남": "|", "남서": "/", "서": "-", "북서": "\\"}
    for name in PLANAR_DIRECTIONS:
        if name in actual:
            data = DIRECTIONS[name]
            cells[data["row"]][data["column"]] = ft.token(
                "direction" if actual[name]["can_move"] else "warning", glyphs[name])
    vertical = [actual[name] for name in ("위", "아래") if name in actual]
    center = "X" if len(vertical) == 2 else "^" if "위" in actual else "v" if vertical else "o"
    role = "object" if not vertical else "direction" if all(entry["can_move"] for entry in vertical) else "warning"
    cells[1][1] = ft.token(role, center)
    sentences = _sentence_lines(entries, text_width)
    lines = [ft.text(*cells[0])]
    for index in range(max(2, len(sentences))):
        canvas = ft.text(*cells[index + 1]) if index < 2 else "   "
        lines.append(ft.text(canvas, "  ", sentences[index]) if index < len(sentences) else canvas)
    restricted = [entry["name"] for entry in entries if entry["exists"] and not entry["can_move"]]
    closed = [entry["name"] for entry in entries if not entry["exists"]]
    for label, names in (("출입 제한: ", restricted), ("폐쇄: ", closed)):
        if names:
            lines.append(ft.text(label, ft.join([ft.token("warning", name) for name in names], ", ")))
    return ft.join(lines)


def exits_sheet(viewer, observed_at=None):
    entries = exit_entries(viewer, observed_at=observed_at)
    name_width = max((ft.display_width(entry["name"]) for entry in entries), default=0) + 2
    target_width = max((ft.display_width(entry["destination_name"]) for entry in entries), default=0) + 2
    rows = [ft.row(ft.token("direction" if entry["can_move"] else "warning", entry["name"]),
                   ft.row(entry["destination_name"], ft.token("text" if entry["can_move"] else "warning", entry["status"]),
                          width=target_width), width=name_width) for entry in entries]
    return ft.compact("출구", "", *(rows or ["보이는 출구가 없다."]),
                      summary=ROOMS.get(viewer.zone, {}).get("name", viewer.location.key if viewer.location else "위치 없음"))
