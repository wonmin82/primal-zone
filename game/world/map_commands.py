"""지도 조회 대상 선택과 서버 Semantic Text 응답."""

from time import time

from world import text as ft
from world.content import REGIONS, ROOM_REGION, ROOMS
from world.map_layout import LayoutUnrepresentable, MapDeclarationInvalid, layout, render
from world.map_metadata import RESERVED_ARGUMENTS, catalog
from world.map_projection import (
    MapAccessDenied,
    ProjectionError,
    RuntimeGraphMismatch,
    logger,
    project,
    visible_rooms,
)
from world.targets import normalized

SAFE_FAILURE = "지도를 정확하게 표시할 수 없습니다. 방문 장소는 '지도 목록'으로 확인하세요."


class AmbiguousMap(Exception):
    pass


class InvalidMapQuery(Exception):
    pass


def select(matches):
    if not matches:
        raise MapAccessDenied
    if len(matches) > 1:
        raise AmbiguousMap
    return matches[0]


def visible_sheets(sheets, public):
    return [sheet for sheet in sheets if any(zone in public for zone in sheet.rooms)]


def find_sheet(sheets, name):
    return select([sheet for sheet in sheets
                   if normalized(name) in {normalized(value) for value in (sheet.name, *sheet.aliases)}])


def overview(index, public):
    by_region = {}
    for sheet in visible_sheets(index.sheets.values(), public):
        by_region.setdefault(sheet.region, []).append(sheet.name)
    for zone in public:
        if index.room_sheet[zone] is None:
            by_region.setdefault(ROOM_REGION[zone], []).append(ROOMS[zone]["name"])
    return ft.compact("지도 전체", *[
        f"{REGIONS[region]['name']} · {' · '.join(sorted(set(names)))}"
        for region, names in sorted(by_region.items())
    ] or ["표시할 방문 지도가 없습니다."])


def map_context(viewer):
    index = catalog()
    current = viewer.zone
    visited = set(viewer.profile_snapshot()["visited"])
    if current not in index.room_sheet:
        raise MapAccessDenied
    return index, current, visited


def current_sheet(index, current):
    return index.sheets.get(index.room_sheet[current])


def select_center(viewer, index, visited, place, sheet=None, *, view_check=None):
    place = normalized(place)
    candidates = {
        zone for zone in visited & index.room_sheet.keys()
        if index.room_sheet[zone] is not None
        and (sheet is None or index.room_sheet[zone] == sheet.id)
        and place in {normalized(value) for value in
                      (ROOMS[zone]["name"], *index.room_aliases.get(zone, ()))}
    }
    return select(sorted(visible_rooms(viewer, candidates, None, visited, view_check=view_check)))


def render_messages(graph, sheet, current, *, ascii_only=False):
    """터미널과 웹이 동일한 배치와 의미별 텍스트를 사용한다."""
    symbols = {"×": "x", "…": "..."} if ascii_only else {}
    if sheet is None:
        return ft.compact("지도", *[f"{name} · {symbols.get(label, label)}" for name, label in graph.notices],
                          *(["나머지 출구는 '출구'에서 확인하세요."] if graph.partial else []),
                          summary=ROOMS[current]["name"]), None
    placed = layout(graph.names, graph.edges, graph.positions, graph.routes, graph.anchors)
    result = render(placed, graph.boundaries, current=graph.current, center=graph.center,
                    ascii_only=ascii_only)
    title = ft.compact("지도", summary=sheet.name)
    if graph.center or graph.current:
        title = ft.text(title, " · ", graph.names[graph.center or graph.current])
    body = ft.text(ft.join(result.lines), kind="map")
    lines = [title, body]
    if result.partial or graph.partial:
        lines.append(ft.token("muted", "공개된 지도 일부를 표시합니다."))
    if graph.notices:
        lines.append(ft.text("기타 출구 · ", ft.join(
            [ft.text(ft.token("direction", name), " ", symbols.get(label, label)) for name, label in graph.notices], " · ")))
    for source, direction, symbol in result.omitted:
        lines.append(ft.text(graph.names[source], " · ", direction, " ", symbols.get(symbol, symbol)))
    return lines, result


def _map_text(viewer, query, now):
    query = query.strip()
    option = query.casefold()
    if option == "도움말":
        from commands.help_pages import help_page
        from commands.registry import COMMANDS

        return help_page("지도", COMMANDS)
    index, current, visited = map_context(viewer)
    sheet = current_sheet(index, current)
    center = None
    if option not in ("", "ascii", "근처"):
        if option == "전체":
            public = visible_rooms(viewer, visited & ROOMS.keys(), None, visited)
            return overview(index, public)
        head, *tail = query.split(maxsplit=1)
        if head == "중심":
            if not tail:
                raise InvalidMapQuery
            scope, separator, place = tail[0].partition("/")
            if not scope.strip() or (separator and not place.strip()) or "/" in place:
                raise InvalidMapQuery
            sheet_filter = find_sheet(index.sheets.values(), scope) if separator else None
            center = select_center(viewer, index, visited, place if separator else scope, sheet_filter)
            sheet = index.sheets[index.room_sheet[center]]
        else:
            if head.casefold() in RESERVED_ARGUMENTS:
                raise InvalidMapQuery
            sheet = find_sheet(index.sheets.values(), query)
    graph = project(viewer, index, sheet, current=current, visited=visited,
                    now=now, center=center, near=option == "근처")
    messages, _ = render_messages(graph, sheet, current, ascii_only=option == "ascii")
    return messages


def map_error(viewer, error):
    if isinstance(error, InvalidMapQuery):
        return ft.text("지도 명령의 인자를 확인하세요. 사용법은 '지도 도움말'에서 확인할 수 있습니다.")
    if isinstance(error, AmbiguousMap):
        return ft.text("공개된 이름이 여러 곳과 일치합니다. 지도명으로 범위를 한정하거나 고유한 별칭을 입력하세요.")
    if isinstance(error, MapAccessDenied):
        return ft.text("조회할 수 있는 지도가 없습니다.")
    if isinstance(error, (RuntimeGraphMismatch, MapDeclarationInvalid, LayoutUnrepresentable)):
        logger.warning("%s (zone=%s): %s", type(error).__name__, viewer.zone, error)
    else:
        failure = ProjectionError("지도 공개 결과 계산 실패")
        logger.error("%s (zone=%s): %s", type(failure).__name__, viewer.zone, failure, exc_info=error)
    return ft.text(ft.token("warning", SAFE_FAILURE))


def map_text(viewer, query, now=None):
    try:
        return _map_text(viewer, query, time() if now is None else now)
    except Exception as error:
        return map_error(viewer, error)
