"""공개된 평면 그래프의 배치와 문자 렌더링. 게임 객체나 저장소에 접근하지 않는다."""

from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush

from world.content.directions import DIRECTIONS, OPPOSITE_DIRECTIONS, PLANAR_DIRECTIONS
from world.text import Text, display_width, text, token

VECTORS = {
    name: (DIRECTIONS[name]["column"] - 1, DIRECTIONS[name]["row"] - 1)
    for name in PLANAR_DIRECTIONS
}
_DIRECTION_INDEX = {name: index for index, name in enumerate(VECTORS)}
_WIDTH, _HEIGHT = 60, 24
_BOUNDARY_ROLES = {"?": "muted", "+": "npc", "×": "warning"}


class LayoutUnrepresentable(ValueError):
    """공개 구조의 정확한 문자 배치를 구성할 수 없다."""


class MapDeclarationInvalid(ValueError):
    """명시한 배치 선언이 지도 계약을 위반한다."""


@dataclass(frozen=True)
class Path:
    source: str
    direction: str
    target: str
    points: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Layout:
    rooms: dict[str, tuple[int, int]]
    paths: tuple[Path, ...]
    exit_directions: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class RenderedMap:
    lines: tuple[Text, ...]
    partial: bool
    omitted: tuple[tuple[str, str, str], ...]
    visible: tuple[str, ...] = ()


def _add(a, b):
    return a[0] + b[0], a[1] + b[1]


def _subtract(a, b):
    return a[0] - b[0], a[1] - b[1]


def _direction(a, b):
    dx, dy = _subtract(b, a)
    if dx and dy and abs(dx) != abs(dy):
        return None
    return ((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _bounds(a, b):
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


def _on_segment(p, a, b):
    x0, y0, x1, y1 = _bounds(a, b)
    return x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and not _cross(
        _subtract(p, a), _subtract(b, a)
    )


def _segments_conflict(a, b, c, d, shared=None):
    """정수 외적으로 반 셀 교차도 잡고 유일한 허용 끝점만 통과시킨다."""
    x0, y0, x1, y1 = _bounds(a, b)
    u0, v0, u1, v1 = _bounds(c, d)
    if x1 < u0 or u1 < x0 or y1 < v0 or v1 < y0:
        return False
    ab, cd = _subtract(b, a), _subtract(d, c)
    ac = _subtract(c, a)
    determinant = _cross(ab, cd)
    if not determinant:
        if _cross(ac, ab):
            return False
        return shared is None or (
            min(x1, u1) > max(x0, u0) or min(y1, v1) > max(y0, v0)
        )
    if shared is not None:
        return False
    ab_fraction = _cross(ac, cd)
    cd_fraction = _cross(ac, ab)
    lo, hi = sorted((0, determinant))
    return lo <= ab_fraction <= hi and lo <= cd_fraction <= hi


def validate_route(direction, via):
    """도착 Room의 좌표 없이 검증할 수 있는 상대 경유점 계약."""
    locations = ((0, 0), *via)
    segments = tuple(zip(locations, locations[1:]))
    if not segments or _direction(*segments[0]) != VECTORS[direction]:
        raise MapDeclarationInvalid(f"{direction} 경유점의 첫 선분이 실제 방향과 다릅니다.")
    for index, (a, b) in enumerate(segments):
        if not _direction(a, b) or a == b:
            raise MapDeclarationInvalid(f"{direction} 경유점에 0길이 또는 비격자 선분이 있습니다.")
        for prev_index, (c, d) in enumerate(segments[:index]):
            joint = a if prev_index == index - 1 else None
            if _segments_conflict(a, b, c, d, joint):
                raise MapDeclarationInvalid(f"{direction} 경유 경로가 자체 교차합니다.")
    last = locations[-1]
    next_cell = _add(last, VECTORS[direction])
    if any(
        _segments_conflict(last, next_cell, a, b, last if index == len(segments) - 1 else None)
        for index, (a, b) in enumerate(segments)
    ):
        raise MapDeclarationInvalid(f"{direction} 진입 선분이 경유 경로와 자체 교차합니다.")


def _position_groups(nodes, positions, adjacent):
    relations = defaultdict(list)
    for room, (reference, offset) in positions.items():
        if room not in nodes or reference not in nodes or reference not in adjacent[room]:
            raise MapDeclarationInvalid(f"위치 기준 Room이 실제 인접 장소가 아닙니다. {room!r}")
        if offset == (0, 0):
            raise MapDeclarationInvalid(f"위치 오프셋이 0입니다. {room!r}")
        relations[room].append((reference, (-offset[0], -offset[1])))
        relations[reference].append((room, offset))

    # 선언당 기준이 하나이므로 같은 그룹에서 이미 확인한 관계를 만나면 참조 순환이다.
    by_room, groups = {}, {}
    for root in sorted(nodes):
        if root in by_room:
            continue
        local = {root: (0, 0)}
        seen_positions = {(0, 0)}
        queue = [(root, None)]
        for source, parent in queue:
            by_room[source] = root
            for target, offset in relations[source]:
                if target == parent:
                    continue
                if target in local:
                    raise MapDeclarationInvalid(f"위치 기준 참조가 순환합니다. {target!r}")
                point = _add(local[source], offset)
                if point in seen_positions:
                    raise MapDeclarationInvalid(f"위치 선언이 같은 좌표에 겹칩니다. {target!r}")
                seen_positions.add(point)
                local[target] = point
                queue.append((target, source))
        groups[root] = local
    return by_room, groups


def _logical_edges(edges):
    remaining = set(edges)
    for source, direction, target in sorted(
        remaining, key=lambda edge: (edge[0], _DIRECTION_INDEX[edge[1]], edge[2])
    ):
        if (source, direction, target) in remaining:
            yield source, direction, target
            remaining.discard((target, OPPOSITE_DIRECTIONS[direction], source))


def _fit_ray(point, step, constraints):
    """이미 배치된 이웃 모두에 맞는 최소 간격을 결정한다."""
    minimum, maximum = 0, None
    for start, vector in constraints:
        offset = _subtract(start, point)
        denominator = _cross(step, vector)
        if denominator:
            distance, remainder = divmod(_cross(offset, vector), denominator)
            if remainder or _cross(offset, step) * denominator < 0:
                return point
            limit_min = limit_max = distance
        elif _cross(offset, step):
            return point
        else:
            distance = offset[0] * step[0] if step[0] else offset[1] * step[1]
            if step == vector:
                limit_min, limit_max = distance, None
            else:
                limit_min, limit_max = 0, distance
        minimum = max(minimum, limit_min)
        if limit_max is not None:
            maximum = limit_max if maximum is None else min(maximum, limit_max)
    if maximum is not None and minimum > maximum:
        return point
    return _add(point, (step[0] * minimum, step[1] * minimum))


def _segment_rooms(path, index):
    # 경유점까지의 선분은 출발점에 고정된다. 마지막 선분은 도착점도 사용한다.
    return (path.source,) if index < len(path.points) - 2 else (path.source, path.target)


def _find_conflicts(placed, paths):
    """Room과 경로 선분을 표시 격자 대신 경계 구간으로 비교한다."""
    occupied = {}
    for room, point in placed.items():
        if point in occupied:
            return (room, occupied[point]), False
        occupied[point] = room

    segments = []
    for path in paths:
        pieces = tuple(zip(path.points, path.points[1:]))
        for index, (a, b) in enumerate(pieces):
            segments.append((a, b, path, index))
    segments.extend((point, point, room, -1) for room, point in placed.items())
    if not segments:
        return (), False

    # 길게 뻗은 수직·수평 복도에서 활성 선분이 전체 그래프로 증가하지 않게 한다.
    extremes = tuple(zip(*placed.values()))
    axis = int(max(extremes[1]) - min(extremes[1]) > max(extremes[0]) - min(extremes[0]))
    segments.sort(key=lambda part: min(part[0][axis], part[1][axis]))
    active = []
    for a, b, owner, index in segments:
        start = min(a[axis], b[axis])
        active = [part for part in active if max(part[0][axis], part[1][axis]) >= start]
        for c, d, other, prev_index in active:
            if index == prev_index == -1:
                continue
            if index == -1 or prev_index == -1:
                point, room, line_a, line_b, path, segment_index = (
                    (a, owner, c, d, other, prev_index) if index == -1
                    else (c, other, a, b, owner, index)
                )
                if _on_segment(point, line_a, line_b) and (
                    room not in (path.source, path.target) or point not in (line_a, line_b)
                ):
                    dependencies = _segment_rooms(path, segment_index)
                    return (room, *dependencies), len(dependencies) == 1
                continue
            shared = None
            if owner is other and abs(index - prev_index) == 1:
                shared = owner.points[max(index, prev_index)]
            elif owner is not other:
                endpoints = {owner.source, owner.target} & {other.source, other.target}
                joint = next(
                    (point for point in (a, b) if point in (c, d) and occupied.get(point) in endpoints),
                    None,
                )
                shared = joint
            if _segments_conflict(a, b, c, d, shared):
                first = _segment_rooms(owner, index)
                second = _segment_rooms(other, prev_index)
                return (*first, *second), len(first) == 1 or len(second) == 1
        active.append((a, b, owner, index))
    return (), False


def layout(nodes, edges, positions, routes, anchors):
    """공개 노드와 통로만 사용하여 연결 성분별 좌표와 경로를 만든다."""
    nodes = set(nodes)
    edges = set(edges)
    exit_directions = frozenset((source, direction) for source, direction, _ in edges)
    adjacency = defaultdict(list)
    adjacent = defaultdict(set)
    for source, direction, target in _logical_edges(edges):
        vector = VECTORS[direction]
        via = routes.get((source, direction))
        reverse_direction = OPPOSITE_DIRECTIONS[direction]
        if (target, reverse_direction) in routes:
            if via is not None:
                raise MapDeclarationInvalid(f"양쪽 이동이 같은 경유 경로를 선언합니다. {source!r}")
            # 공개 역방향 하나만 남은 경우에도 선언은 원래 출발점을 기준으로 검증한다.
            reverse_via = routes[target, reverse_direction]
            validate_route(reverse_direction, reverse_via)
            offset = _subtract(vector, reverse_via[-1])
            hinted = True
        elif via is not None:
            validate_route(direction, via)
            offset = _add(via[-1], vector)
            hinted = True
        else:
            offset, hinted = vector, False
        adjacent[source].add(target)
        adjacent[target].add(source)
        adjacency[source].append((target, direction, offset, hinted))
        adjacency[target].append(
            (source, reverse_direction, (-offset[0], -offset[1]), hinted)
        )

    by_room, groups = _position_groups(nodes, positions, adjacent)
    placed, all_paths = {}, []
    next_x = 0
    anchors = dict.fromkeys([*anchors, *sorted(nodes)])
    for root in anchors:
        if root in placed or root not in nodes:
            continue
        local, queue = {}, []

        def place(room, at, depth):
            members = groups[by_room[room]]
            origin = _subtract(at, members[room])
            for member, displacement in members.items():
                local[member] = _add(origin, displacement)
                for target, direction, offset, route_hint in adjacency[member]:
                    heappush(queue, (
                        not route_hint, depth, member, _DIRECTION_INDEX[direction], target, offset
                    ))

        place(root, (0, 0), 0)
        while queue:
            _, depth, source, direction_index, target, offset = heappop(queue)
            if target not in local:
                members = groups[by_room[target]]
                constraints = []
                for member, member_point in members.items():
                    relative = _subtract(member_point, members[target])
                    for neighbor, direction, reverse_offset, _ in adjacency[member]:
                        if neighbor in local:
                            start = _subtract(_subtract(local[neighbor], reverse_offset), relative)
                            dx, dy = VECTORS[direction]
                            constraints.append((start, (-dx, -dy)))
                point = _add(local[source], offset)
                step = VECTORS[PLANAR_DIRECTIONS[direction_index]]
                fitted = _fit_ray(point, step, constraints)
                place(target, fitted, depth + 1)

        paths = []
        for source in local:
            for target, direction, _, _ in adjacency[source]:
                if (target, OPPOSITE_DIRECTIONS[direction], source) < (source, direction, target):
                    continue
                if (target, OPPOSITE_DIRECTIONS[direction]) in routes:
                    source_key, target_key = target, source
                    heading = OPPOSITE_DIRECTIONS[direction]
                else:
                    source_key, target_key, heading = source, target, direction
                a, b = local[source_key], local[target_key]
                via = routes.get((source_key, heading), ())
                points = (a, *(_add(a, point) for point in via), b)
                expected = VECTORS[heading]
                if _direction(points[-2], points[-1]) != expected:
                    fixed = source_key != target_key and by_room[source_key] == by_room[target_key]
                    error = MapDeclarationInvalid if fixed else LayoutUnrepresentable
                    raise error(f"이동 방향을 보존할 수 없습니다. {source_key!r} {heading} {target_key!r}")
                paths.append(Path(source_key, heading, target_key, points))

        rooms, fixed_route = _find_conflicts(local, paths)
        if rooms:
            # 서로의 위치가 명시적으로 고정된 구조에서만 선언 충돌이 확정된다.
            fixed = (fixed_route or len(set(rooms)) > 1) and len({by_room[room] for room in rooms}) == 1
            error = MapDeclarationInvalid if fixed else LayoutUnrepresentable
            raise error(f"지도 위치 또는 통로가 겹칩니다. {rooms!r}")

        points = [*local.values(), *(p for path in paths for p in path.points)]
        left = min(p[0] for p in points)
        top = min(p[1] for p in points)
        shift = (next_x - left, -top)
        placed.update((room, _add(point, shift)) for room, point in local.items())
        all_paths.extend(
            Path(path.source, path.direction, path.target,
                 tuple(_add(point, shift) for point in path.points))
            for path in paths
        )
        next_x += max(p[0] for p in points) - left + 3
    return Layout(placed, tuple(all_paths), exit_directions)


def _crop(lo, hi, center, limit):
    if hi - lo + 1 <= limit:
        return lo, hi
    start = min(max(lo, center - limit // 2), hi - limit + 1)
    end = start + limit - 1
    # 잘림 지점에서 Room이나 경유점 대신 통로 셀을 경계 표식으로 바꾼다.
    if start > lo and start % 2 == 0:
        start += 1
    if end < hi and end % 2 == 0:
        end -= 1
    return start, end


def _scale(p):
    return p[0] * 2, p[1] * 2


def _visible_segment(a, b, crop):
    """보이는 셀의 거리 범위만 순회한다. 아주 긴 Hint도 격자를 만들지 않는다."""
    dx, dy = _direction(a, b)
    length = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
    lo, hi = 0, length
    for start, delta, (left, right) in zip(a, (dx, dy), crop):
        if not delta:
            if not left <= start <= right:
                return (), ()
            continue
        t0, t1 = sorted(((left - start) * delta, (right - start) * delta))
        lo, hi = max(lo, t0), min(hi, t1)
    if lo > hi:
        return (), ()
    points = tuple((a[0] + dx * t, a[1] + dy * t) for t in range(lo, hi + 1))
    cuts = []
    if lo:
        cuts.append((points[0], (-dx, -dy)))
    if hi < length:
        cuts.append((points[-1], (dx, dy)))
    return points, cuts


def _stroke(vector, ascii_only):
    dx, dy = vector
    if not dx:
        return "|" if ascii_only else "│"
    if not dy:
        return "-" if ascii_only else "─"
    if dx == dy:
        return "\\" if ascii_only else "╲"
    return "/" if ascii_only else "╱"


def _diagonal_cell(a, b):
    """한 셀 정사각형 안에서 선분을 식별해 반 셀 교차를 검사한다."""
    dx, dy = _subtract(b, a)
    return min(a[0], b[0]), min(a[1], b[1]), dx * dy


def _cut_marker(cells, point, vector, crop, ascii_only):
    x, y = point
    if point in cells and cells[point][0] != "direction":
        return False
    if not ascii_only:
        cells[point] = ("muted", "…")
        return True
    xmin, xmax = crop[0]
    ymin, ymax = crop[1]
    # ASCII 경계 표식도 독립된 세 셀을 차지한다. 인접 Room이나 통로를 덮지 않는다.
    dx, dy = vector
    lead = []
    for distance in range(4) if dy else (0,):
        cut_x, cut_y = x + distance * dx, y + distance * dy
        if not (xmin <= cut_x <= xmax and ymin <= cut_y <= ymax):
            break
        if distance and (cut_x, cut_y) in cells:
            break
        offsets = {-1: (-2, -1, 0), 0: (-1, 0, -2), 1: (0, -1, -2)}[dx]
        for offset in offsets:
            start = cut_x + offset
            places = tuple((start + index, cut_y) for index in range(3))
            if xmin <= start <= xmax - 2 and all(p == point or p not in cells for p in places):
                cells.update((p, ("direction", _stroke(vector, True))) for p in lead)
                cells.update((p, ("muted", ".")) for p in places)
                return True
        lead.append((cut_x, cut_y))
    return False


def render(layout_result, boundaries=(), *, current=None, center=None, ascii_only=False):
    """공개 배치의 잘린 부분만 의미별 텍스트로 변환한다."""
    rooms = {key: _scale(point) for key, point in layout_result.rooms.items()}
    if not rooms:
        return RenderedMap((), False, ())
    scaled_paths = tuple(
        (path, tuple(_scale(point) for point in path.points)) for path in layout_result.paths
    )
    bounds = sorted(
        boundaries, key=lambda entry: (entry[0], _DIRECTION_INDEX[entry[1]], entry[2])
    )
    markers = []
    for entry in bounds:
        source, direction, symbol = entry
        start, vector = rooms[source], VECTORS[direction]
        stroke = _add(start, vector)
        blocked_path = symbol == "×" and (source, direction) in layout_result.exit_directions
        end = stroke if blocked_path else _add(stroke, vector)
        markers.append((entry, start, stroke, end, vector))
    points = [*rooms.values(), *(p for _, path in scaled_paths for p in path),
              *(end for _, _, _, end, _ in markers)]
    focus = rooms.get(center, rooms.get(current, next(iter(rooms.values()))))
    all_axes = tuple(zip(*points))
    raw_bounds = tuple((min(axis), max(axis)) for axis in all_axes)
    limits = (_WIDTH, _HEIGHT)
    needs_cut = any(hi - lo + 1 > limit for (lo, hi), limit in zip(raw_bounds, limits))
    margins = (2, 3) if needs_cut and ascii_only else (0, 0)
    crop = tuple(
        _crop(lo, hi, at, limit - 2 * margin)
        for (lo, hi), at, limit, margin in zip(raw_bounds, focus, limits, margins)
    )
    output_crop = tuple((lo - margin, hi + margin) for (lo, hi), margin in zip(crop, margins))
    x_range, y_range = output_crop
    partial = any(
        min(axis) < left or max(axis) > right for axis, (left, right) in zip(all_axes, crop)
    )

    def inside(point):
        return crop[0][0] <= point[0] <= crop[0][1] and crop[1][0] <= point[1] <= crop[1][1]

    cells = {}
    diagonals = set()
    cut_cells = []
    visible_rooms = []
    for path, locations in scaled_paths:
        for a, b in zip(locations, locations[1:]):
            visible, cuts = _visible_segment(a, b, crop)
            vector = _direction(a, b)
            line = _stroke(vector, ascii_only)
            cells.update((p, ("direction", line)) for p in visible)
            if markers and all(vector):
                diagonals.update(_diagonal_cell(p, q) for p, q in zip(visible, visible[1:]))
            cut_cells.extend((point, vector, path) for point, vector in cuts)
        for point in locations[1:-1]:
            if inside(point):
                cells[point] = ("direction", "." if ascii_only else "·")
    for key, point in rooms.items():
        if inside(point):
            visible_rooms.append(key)
            cells[point] = ("player", "@") if key == current else ("text", "o")

    omitted = []
    independent = []
    for entry, start, stroke, end, vector in markers:
        if not inside(start):
            continue
        if stroke != end:
            independent.append((entry, start, stroke, end, vector))
        elif stroke in cells and cells[stroke][0] == "direction":
            cells[stroke] = ("warning", "x" if ascii_only else "×")
        else:
            omitted.append(entry)

    for point, vector, path in cut_cells:
        if not _cut_marker(cells, point, vector, output_crop, ascii_only):
            omitted.append((path.source, path.direction, "…"))

    for entry, start, stroke, end, vector in independent:
        halves = (_diagonal_cell(start, stroke), _diagonal_cell(stroke, end)) if all(vector) else ()
        if (not inside(end) or stroke in cells or end in cells
                or any((x, y, -slope) in diagonals for x, y, slope in halves)):
            omitted.append(entry)
            continue
        symbol = entry[2]
        displayed = "x" if ascii_only and symbol == "×" else symbol
        cells[stroke] = ("direction", _stroke(vector, ascii_only))
        cells[end] = (_BOUNDARY_ROLES[symbol], displayed)
        diagonals.update(halves)

    lines = []
    for row in range(y_range[0], y_range[1] + 1):
        parts = []
        active_role, active_content = "text", ""
        for column in range(x_range[0], x_range[1] + 1):
            role, char = cells.get((column, row), ("text", " "))
            if role != active_role and active_content:
                parts.append(token(active_role, active_content))
                active_content = ""
            active_role = role
            active_content += char
        if active_content.rstrip():
            parts.append(token(active_role, active_content.rstrip()))
        result = text(*parts)
        if display_width(result) > _WIDTH:
            raise LayoutUnrepresentable("지도 표시 셀 한도를 초과했습니다.")
        lines.append(result)
    return RenderedMap(tuple(lines), partial, tuple(omitted), tuple(visible_rooms))
