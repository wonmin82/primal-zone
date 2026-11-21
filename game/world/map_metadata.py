"""기존 Region·Room 선언에서 탐사 지도 표현 분류를 파생한다."""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from types import MappingProxyType

from world.content import OPPOSITE_DIRECTIONS, REGIONS, ROOM_REGION, ROOMS
from world.content.directions import PLANAR_DIRECTIONS
from world.map_layout import LayoutUnrepresentable, MapDeclarationInvalid, layout, validate_route
from world.targets import normalized

RESERVED_ARGUMENTS = frozenset({"근처", "전체", "목록", "중심", "ascii", "도움", "도움말"})


@dataclass(frozen=True, slots=True)
class Sheet:
    id: str
    name: str
    aliases: tuple[str, ...]
    region: str
    rooms: tuple[str, ...]
    anchors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Catalog:
    sheets: Mapping[str, Sheet]
    room_sheet: Mapping[str, str | None]
    room_aliases: Mapping[str, tuple[str, ...]]
    positions: Mapping[str, tuple[str, tuple[int, int]]]
    routes: Mapping[tuple[str, str], tuple[tuple[int, int], ...]]


def _fields(value, scope, allowed, required=()):
    if not isinstance(value, Mapping) or value.keys() - allowed or set(required) - value.keys():
        raise MapDeclarationInvalid(f"{scope}: 지도 선언 필드가 올바르지 않습니다.")
    return value


def _label(value, scope):
    if (not isinstance(value, str) or not value.isprintable() or not normalized(value)
            or "/" in value or value != value.strip()):
        raise MapDeclarationInvalid(f"{scope}: 지도 이름 또는 별칭이 올바르지 않습니다.")
    return value


def _aliases(value, scope):
    if not isinstance(value, (tuple, list)):
        raise MapDeclarationInvalid(f"{scope}: 지도 별칭은 문자열 목록이어야 합니다.")
    return tuple(_label(alias, scope) for alias in value)


def _point(value, scope):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(type(coordinate) is not int for coordinate in value)):
        raise MapDeclarationInvalid(f"{scope}: 지도 좌표에는 정수 두 개가 필요합니다.")
    return tuple(value)


def _sheets(regions):
    declarations, defaults, public_names = {}, {}, {}
    sheet_ids = set()
    for region_id, region in sorted(regions.items()):
        metadata = _fields(region.get("map", {}), region_id, {"sheets"})
        explicit = "sheets" in metadata
        definitions = metadata.get("sheets", {region_id: {"name": region["name"]}})
        if not isinstance(definitions, Mapping) or not definitions:
            raise MapDeclarationInvalid(f"{region_id}: Sheet 선언이 올바르지 않습니다.")
        if not explicit:
            defaults[region_id] = region_id
        elif len(definitions) == 1:
            defaults[region_id] = next(iter(definitions))

        for sheet_id, value in definitions.items():
            if (not isinstance(sheet_id, str) or not sheet_id.isprintable()
                    or any(char.isspace() for char in sheet_id)
                    or not (identity := normalized(sheet_id)) or identity in sheet_ids):
                raise MapDeclarationInvalid(f"{region_id}: Sheet ID가 잘못되었거나 중복됩니다.")
            sheet_ids.add(identity)
            definition = _fields(value, sheet_id, {"name", "aliases", "anchor"}, {"name"})
            name = _label(definition["name"], sheet_id)
            aliases = _aliases(definition.get("aliases", ()), sheet_id)
            for label in (name, *aliases):
                key = normalized(label)
                if key in RESERVED_ARGUMENTS or label.split()[0].casefold() in RESERVED_ARGUMENTS:
                    raise MapDeclarationInvalid(f"{sheet_id}: 예약된 지도 이름 또는 별칭입니다.")
                if key in public_names:
                    raise MapDeclarationInvalid(
                        f"{sheet_id}: 지도 이름/별칭이 {public_names[key]}와 충돌합니다."
                    )
                public_names[key] = sheet_id
            anchor = definition.get("anchor")
            if "anchor" in definition and (not isinstance(anchor, str) or not anchor):
                raise MapDeclarationInvalid(f"{sheet_id}: 기준 Room ID가 올바르지 않습니다.")
            declarations[sheet_id] = (region_id, name, aliases, anchor)
    return declarations, defaults


def _room_sheets(rooms, regions, room_region, declarations, defaults):
    if set(rooms) != set(room_region):
        raise MapDeclarationInvalid("지도 분류에 Room이 누락되었거나 추가되어 있습니다.")
    room_sheet, sheet_rooms, metadata = {}, defaultdict(list), {}
    for room_id, room in sorted(rooms.items()):
        region_id = room_region[room_id]
        if region_id not in regions:
            raise MapDeclarationInvalid(f"{room_id}: 지도 Region이 없습니다.")
        value = _fields(room.get("map", {}), room_id, {"sheet", "presentation", "aliases", "layout"})
        metadata[room_id] = value
        presentation = value.get("presentation", "planar")
        if presentation == "connector":
            if "sheet" in value or "layout" in value:
                raise MapDeclarationInvalid(f"{room_id}: Connector에는 Sheet와 Hint를 지정할 수 없습니다.")
            room_sheet[room_id] = None
            continue
        if presentation != "planar":
            raise MapDeclarationInvalid(f"{room_id}: 지도 표현 유형이 올바르지 않습니다.")
        sheet_id = value.get("sheet", defaults.get(region_id))
        if (not isinstance(sheet_id, str) or sheet_id not in declarations
                or declarations[sheet_id][0] != region_id):
            raise MapDeclarationInvalid(f"{room_id}: 소속 Region의 Sheet가 필요합니다.")
        room_sheet[room_id] = sheet_id
        sheet_rooms[sheet_id].append(room_id)
    return room_sheet, sheet_rooms, metadata


def _room_aliases(rooms, room_region, room_sheet, metadata):
    aliases = {}
    names = defaultdict(set)
    lookup = defaultdict(dict)
    for room_id, room in sorted(rooms.items()):
        scope = (room_region[room_id], room_sheet[room_id])
        names[scope, normalized(room["name"])].add(room_id)
        values = _aliases(metadata[room_id].get("aliases", ()), room_id)
        if values:
            aliases[room_id] = values
        for value in values:
            key = normalized(value)
            if key in lookup[scope]:
                raise MapDeclarationInvalid(f"{room_id}: 지도 장소 별칭이 중복됩니다.")
            lookup[scope][key] = room_id
    for (scope, name), identities in names.items():
        alias_owner = lookup[scope].get(name)
        if alias_owner is not None and (
            len(identities) > 1 or alias_owner not in identities
        ):
            raise MapDeclarationInvalid(f"{alias_owner}: 지도 장소 별칭이 기존 이름과 충돌합니다.")
        if scope[1] is not None and len(identities) > 1 and identities - aliases.keys():
            raise MapDeclarationInvalid(
                f"{scope[1]}: 동명 Room에 고유 지도 별칭이 필요합니다. {sorted(identities)}"
            )
    return aliases


def _position_hint(room_id, value, rooms, room_sheet):
    hint = _fields(value, room_id, {"relative_to", "offset"}, {"relative_to", "offset"})
    reference = hint["relative_to"]
    offset = _point(hint["offset"], room_id)
    adjacent = any(
        rooms[room_id]["exits"].get(direction) == reference for direction in PLANAR_DIRECTIONS
    )
    if (not isinstance(reference, str) or reference == room_id or not adjacent
            or room_sheet.get(reference) != room_sheet[room_id] or offset == (0, 0)):
        raise MapDeclarationInvalid(f"{room_id}: Position Hint의 기준 Room 또는 오프셋이 올바르지 않습니다.")
    return reference, offset


def _route_hints(room_id, value, rooms, room_sheet):
    if not isinstance(value, Mapping):
        raise MapDeclarationInvalid(f"{room_id}: Route Hint에는 방향별 선언이 필요합니다.")
    for direction, value in value.items():
        scope = f"{room_id}:{direction}"
        destination = rooms[room_id]["exits"].get(direction)
        if direction not in PLANAR_DIRECTIONS or room_sheet.get(destination) != room_sheet[room_id]:
            raise MapDeclarationInvalid(f"{scope}: Route Hint는 같은 Sheet의 정적 방향 출구가 필요합니다.")
        reverse = OPPOSITE_DIRECTIONS[direction]
        if destination < room_id and rooms[destination]["exits"].get(reverse) == room_id:
            raise MapDeclarationInvalid(f"{scope}: Route Hint는 정렬상 앞선 출발 Room에 선언해야 합니다.")
        hint = _fields(value, scope, {"via"}, {"via"})
        if not isinstance(hint["via"], (tuple, list)) or not hint["via"]:
            raise MapDeclarationInvalid(f"{scope}: Route Hint 경유점이 필요합니다.")
        via = tuple(_point(point, scope) for point in hint["via"])
        try:
            validate_route(direction, via)
        except MapDeclarationInvalid as error:
            raise MapDeclarationInvalid(f"{scope}: {error}") from error
        yield (room_id, direction), via


def _check_position_cycles(positions):
    checked = set()
    for room_id in positions:
        trail = set()
        while room_id in positions and room_id not in checked:
            if room_id in trail:
                raise MapDeclarationInvalid(f"{room_id}: Position Hint 기준 Room이 순환합니다.")
            trail.add(room_id)
            room_id = positions[room_id][0]
        checked.update(trail)


def build_catalog(rooms, regions, room_region):
    """정적 분류를 검증해 읽기 전용 파생 데이터로 만든다."""
    declarations, defaults = _sheets(regions)
    room_sheet, sheet_rooms, metadata = _room_sheets(
        rooms, regions, room_region, declarations, defaults
    )
    room_aliases = _room_aliases(rooms, room_region, room_sheet, metadata)
    sheets = {}
    for sheet_id, (region, name, aliases, anchor) in sorted(declarations.items()):
        if anchor is not None and room_sheet.get(anchor) != sheet_id:
            raise MapDeclarationInvalid(f"{sheet_id}: 기준 Room은 이 Sheet의 평면 Room이어야 합니다.")
        entry = regions[region]["entry"]
        anchors = tuple(dict.fromkeys(
            candidate for candidate in (anchor, entry) if room_sheet.get(candidate) == sheet_id
        ))
        sheets[sheet_id] = Sheet(sheet_id, name, aliases, region, tuple(sheet_rooms[sheet_id]), anchors)
    positions, routes = {}, {}
    for room_id, value in metadata.items():
        if "layout" not in value:
            continue
        hints = _fields(value["layout"], room_id, {"position", "routes"})
        if "position" in hints:
            positions[room_id] = _position_hint(room_id, hints["position"], rooms, room_sheet)
        routes.update(_route_hints(room_id, hints.get("routes", {}), rooms, room_sheet))
    _check_position_cycles(positions)
    return Catalog(*(MappingProxyType(value) for value in (
        sheets, room_sheet, room_aliases, positions, routes
    )))


@cache
def catalog():
    """배포와 함께 바뀌는 정적 콘텐츠의 분류만 프로세스에서 재사용한다."""
    return build_catalog(ROOMS, REGIONS, ROOM_REGION)


def validate_geometry(rooms, metadata):
    """전체 정적 Hint를 검사한다. 좌표는 플레이어 지도에 재사용하지 않는다."""
    hinted = set(metadata.positions) | {room for room, _ in metadata.routes}
    for sheet in metadata.sheets.values():
        hint_origins = hinted.intersection(sheet.rooms)
        if not hint_origins:
            continue
        adjacency = defaultdict(set)
        departures = defaultdict(list)
        for room in sheet.rooms:
            for direction, destination in rooms[room]["exits"].items():
                if direction in PLANAR_DIRECTIONS and metadata.room_sheet.get(destination) == sheet.id:
                    adjacency[room].add(destination)
                    adjacency[destination].add(room)
                    departures[room].append((room, direction, destination))
        checked = set()
        for origin in sorted(hint_origins):
            if origin in checked:
                continue
            component = {origin}
            pending = [origin]
            for room in pending:
                additions = adjacency[room] - component
                component.update(additions)
                pending.extend(additions)
            checked.update(component)
            edges = [edge for room in component for edge in departures[room]]
            positions = {
                room: metadata.positions[room]
                for room in sorted(component & metadata.positions.keys())
            }
            routes = {
                (room, direction): metadata.routes[room, direction]
                for room, direction, _ in edges if (room, direction) in metadata.routes
            }
            try:
                layout(component, edges, positions, routes, sheet.anchors)
            except LayoutUnrepresentable:
                # 정상 이동 구조의 표현 가능성은 콘텐츠 무결성 조건이 아니다.
                continue
