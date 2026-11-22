"""Phase 1의 공개 지도 결과를 미니맵에 필요한 의미별 텍스트로 변환한다."""

from collections import defaultdict
from time import time

from world import text as ft
from world.content import ROOMS, ordered_directions
from world.map_commands import (
    InvalidMapQuery,
    current_sheet,
    find_sheet,
    map_context,
    map_error,
    render_messages,
    select_center,
)
from world.map_projection import load_rooms, project
from world.targets import normalized


def _public_sheet_names(viewer, index, sheet, visited, sheet_check):
    other_rooms = visited & index.room_sheet.keys()
    if sheet is not None:
        other_rooms.difference_update(sheet.rooms)
    other_rooms = {zone for zone in other_rooms if index.room_sheet[zone] is not None}
    by_sheet = defaultdict(list)
    for zone, room in load_rooms(other_rooms).items():
        by_sheet[index.room_sheet[zone]].append(room)
    names = {index.sheets[sheet_id].name for sheet_id, rooms in by_sheet.items()
             if sheet_check(rooms, viewer)}
    if sheet is not None:
        names.add(sheet.name)
    return sorted(names)


def _summary(graph, viewport, current):
    parts = [f"현재 위치는 {ROOMS[current]['name']}입니다."]
    if viewport is None:
        parts.append("이동 연결 시설의 공개 출구는 본문의 목록에서 확인할 수 있습니다.")
        return " ".join(parts)
    visible = set(viewport.visible)
    focus = graph.center or graph.current
    if focus not in visible:
        focus = next(iter(viewport.visible), None)
    if focus is not None:
        names = [graph.names[key] for key in viewport.visible if key != graph.current]
        if names:
            places = ", ".join(names[:6])
            if len(names) > 6:
                places += f" 외 {len(names) - 6}곳"
            parts.append(f"화면에 보이는 방문 장소는 {places}입니다.")
        connections = {direction: graph.names[target] for source, direction, target in graph.edges
                       if source == focus and target in visible}
        descriptions = {"?": "목적지 미표시", "+": "다른 지도 경계", "×": "차단", "…": "화면 밖 연결"}
        for source, direction, symbol in (*graph.boundaries, *viewport.omitted):
            if source == focus:
                connections[direction] = descriptions[symbol]
        if connections:
            directions = ", ".join(f"{name} {connections[name]}" for name in ordered_directions(connections))
            parts.append(f"{graph.names[focus]}의 공개 연결은 {directions}입니다.")
    if viewport.partial or graph.partial:
        parts.append("공개 지도의 일부를 표시합니다.")
    if graph.notices:
        parts.append("기타 공개 출구는 본문의 안내에서 확인할 수 있습니다.")
    return " ".join(parts)


def _payload(messages, *, sheet="", sheets=(), centers=(), summary="", partial=False):
    if not isinstance(messages, list):
        messages = [messages]
    return {
        "messages": [{"kind": value.kind, "segments": value.segments} for value in messages],
        "sheet": sheet,
        "sheets": list(sheets),
        "centers": list(centers),
        "summary": summary,
        "partial": partial,
    }


def web_map(viewer, sheet=None, center=None, now=None, *, view_check=None, sheet_check=None):
    """공개된 이름으로 선택하고 렌더링 결과와 뷰포트 내 선택 항목만 반환한다."""
    try:
        index, current, visited = map_context(viewer)
        selected = find_sheet(index.sheets.values(), sheet) if sheet else None
        if center:
            if "/" in center or not normalized(center):
                raise InvalidMapQuery
            center = select_center(viewer, index, visited, center, selected, view_check=view_check)
            selected = index.sheets[index.room_sheet[center]]
        elif selected is None:
            selected = current_sheet(index, current)
        public_labels = {}
        graph = project(
            viewer, index, selected, current=current, visited=visited,
            now=time() if now is None else now, center=center, view_check=view_check,
            public_labels=public_labels,
        )
        messages, viewport = render_messages(graph, selected, current)
        centers = {labels[1] if len(labels) > 1 else labels[0]
                   for key in viewport.visible if (labels := public_labels.get(key))} if viewport else ()
        return _payload(
            messages,
            sheet=selected.name if selected else "",
            sheets=_public_sheet_names(viewer, index, selected, visited,
                                       sheet_check or _any_viewable_room),
            centers=sorted(centers),
            summary=_summary(graph, viewport, current),
            partial=graph.partial or bool(viewport and viewport.partial),
        )
    except Exception as error:
        message = map_error(viewer, error)
        return _payload(ft.text(message, kind="error"), summary=str(message))


def _any_viewable_room(rooms, viewer):
    return any(room.access(viewer, "view") for room in rooms)
