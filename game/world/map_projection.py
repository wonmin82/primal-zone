"""실제 Exit 조회와 플레이어별 지도 공개 경계."""

from collections import defaultdict
from dataclasses import dataclass
from logging import getLogger

from world.content import DIRECTIONS, ROOMS, ordered_directions

logger = getLogger(__name__)
PLANAR = frozenset(name for name, data in DIRECTIONS.items() if "row" in data)


class MapAccessDenied(Exception):
    pass


class RuntimeGraphMismatch(Exception):
    pass


class ProjectionError(Exception):
    pass


@dataclass(frozen=True)
class PublicMap:
    names: dict
    edges: tuple
    positions: dict
    routes: dict
    anchors: tuple
    boundaries: tuple
    notices: tuple
    current: str | None
    center: str | None
    partial: bool = False


def load_rooms(zones):
    """기존 월드 태그로 범위 안의 Room을 묶어서 해석한다."""
    from django.db.models import Exists, OuterRef
    from evennia.objects.models import ObjectDB
    from evennia.typeclasses.attributes import Attribute

    from world.bootstrap import CATEGORY

    if not zones:
        return {}
    links = ObjectDB.db_tags.through.objects
    extra = links.filter(objectdb_id=OuterRef("objectdb_id"), tag__db_category=CATEGORY).exclude(
        tag_id=OuterRef("tag_id"),
    )
    matching = links.filter(tag__db_category=CATEGORY, tag__db_key__in=zones).annotate(
        extra_tag=Exists(extra),
    )
    identities, invalid = {}, set()
    for pk, zone, extra_tag in matching.values_list("objectdb_id", "tag__db_key", "extra_tag"):
        if extra_tag:
            invalid.add(zone)
        else:
            identities[pk] = zone
    attrs = Attribute.objects.filter(db_key="zone_id", db_category__isnull=True)
    zone_attrs = defaultdict(list)
    memberships = ObjectDB.db_attributes.through.objects.filter(
        Exists(attrs.filter(pk=OuterRef("attribute_id"))), objectdb_id__in=identities,
    )
    for pk, value in memberships.values_list("objectdb_id", "attribute__db_value"):
        # zone_id의 권위 값은 문자열이다. 다른 Attribute 형식은 잘못된 Room으로 판정한다.
        zone_attrs[pk].append(value if isinstance(value, str) else None)
    result = {}
    for pk, room in ObjectDB.objects.in_bulk(identities).items():
        zone = identities[pk]
        if zone_attrs[pk] != [zone] or room.db_typeclass_path != "typeclasses.zone_rooms.ZoneRoom":
            invalid.add(zone)
        elif zone in result:
            invalid.add(zone)
        else:
            result[zone] = room
    if invalid:
        logger.warning("RuntimeGraphMismatch: Room 정체성 %s", sorted(invalid))
    return {zone: room for zone, room in result.items() if zone not in invalid}


def load_exits(origins, current_pk):
    """관리 Exit 식별자와 현재 Room의 추가 Exit을 요청별로 묶어서 읽는다."""
    from django.db.models import Q
    from evennia.objects.models import ObjectDB

    from world.bootstrap import EXIT_CATEGORY

    pks = [room.pk for room in origins.values()]
    tags = defaultdict(list)
    managed = ObjectDB.objects.filter(db_location_id__in=pks, db_tags__db_category=EXIT_CATEGORY)
    for pk, identity in managed.values_list("pk", "db_tags__db_key"):
        tags[pk].append(identity)
    grouped = defaultdict(list)
    remote = ObjectDB.objects.filter(pk__in=tags).exclude(db_location_id=current_pk)
    for obj in remote:
        grouped[obj.db_location_id].append((obj, tags[obj.pk]))
    if current_pk in pks:
        current = ObjectDB.objects.filter(db_location_id=current_pk).filter(
            Q(pk__in=tags) | Q(db_destination_id__isnull=False),
        ).select_related("db_location", "db_destination")
        for obj in current:
            grouped[current_pk].append((obj, tags.get(obj.pk, ())))
    return grouped


def visible_rooms(viewer, zones, current, visited):
    rooms = load_rooms(set(zones) & (visited | {current}))
    return {zone: room for zone, room in rooms.items()
            if zone == current or room.access(viewer, "view")}


def _exit_mismatch(zone, direction, pk, problem, visible):
    if visible:
        raise RuntimeGraphMismatch(f"{problem}: {zone}/{direction} (Exit #{pk})")
    logger.warning("RuntimeGraphMismatch: %s: %s/%s (Exit #%s)", problem, zone, direction, pk)


def _diagnose_missing_exits(missing):
    """공개 권한의 근거가 없는 누락과 실제 출발지 이탈을 서버에서만 구별한다."""
    from evennia.objects.models import ObjectDB

    from world.bootstrap import EXIT_CATEGORY

    rows = ObjectDB.objects.filter(db_tags__db_category=EXIT_CATEGORY, db_tags__db_key__in=missing)
    located = defaultdict(list)
    for identity, pk, location in rows.values_list("db_tags__db_key", "pk", "db_location_id"):
        located[identity].append((pk, location))
    for identity, (zone, direction) in missing.items():
        if displaced := located.get(identity):
            logger.warning("RuntimeGraphMismatch: 관리 Exit 출발 위치 불일치 %s/%s: %s",
                           zone, direction, displaced)
        else:
            _exit_mismatch(zone, direction, None, "관리 Exit 누락", False)


def project(viewer, catalog, sheet, *, current, visited, now, center=None, near=False):
    from world.doors import current_door_overlays
    from world.observation import can_perceive, can_view_in_room, context_for

    candidates = ({current} if near or sheet is None else set(sheet.rooms)) & (visited | {current})
    candidate_rooms = load_rooms(candidates)
    origins = {zone: room for zone, room in candidate_rooms.items()
               if zone == current or room.access(viewer, "view")}
    if current in candidates and (current not in origins or origins[current].pk != viewer.location.pk):
        raise RuntimeGraphMismatch(f"현재 Room 정체성 {current}")
    if not origins or (center is not None and center not in origins):
        raise MapAccessDenied

    grouped = load_exits(origins, viewer.location.pk)
    context = context_for(viewer, observed_at=now) if current in origins else None

    public_exits, managed_exits, bounds, notices = {}, [], [], []
    missing = {}
    for zone, room in sorted(origins.items()):
        here = zone == current
        declared = ROOMS[zone]["exits"]
        blocked = ROOMS[zone].get("blocked_exits", {})
        managed_counts, exits = defaultdict(int), defaultdict(list)
        for obj, identities in grouped[room.pk]:
            if not identities:
                if here and obj.db_destination_id and can_perceive(obj, context):
                    notices.append((obj.key, "지도에 배치되지 않은 출구"))
                continue
            direction = obj.key
            managed_counts[direction] += 1
            target = declared.get(direction)
            invalid_identity = (identities != [f"{zone}:{direction}"] or target is None
                                or obj.db_typeclass_path != "typeclasses.exits.Exit")
            if not here:
                visible = (obj.db_destination_id or not invalid_identity) and obj.access(viewer, "view")
            elif not invalid_identity and not obj.db_destination_id:
                # 목적지가 손상된 정상 정체성의 Exit도 방향의 view 정책을 적용한다.
                visible = can_view_in_room(obj, context)
            else:
                visible = can_perceive(obj, context)
            problem = None
            if invalid_identity:
                problem = "관리 Exit 정체성 불일치"
            elif not obj.db_destination_id:
                problem = "관리 Exit 목적지 없음"
            if problem:
                _exit_mismatch(zone, direction, obj.pk, problem, visible)
                continue
            managed_exits.append((zone, direction, obj, target, visible))
            if visible:
                exits[direction].append(obj)
        for direction in ordered_directions(dict.fromkeys([*declared, *blocked, *sorted(exits)])):
            objects = exits[direction]
            if managed_counts.get(direction, 0) > 1:
                _exit_mismatch(zone, direction, None, "관리 Exit 중복", len(objects) > 1)
            if direction in blocked:
                if sheet is not None and direction in PLANAR:
                    bounds.append((zone, direction, "×"))
                else:
                    name = direction if here else f"{ROOMS[zone]['name']} {direction}"
                    notices.append((name, "×"))
            elif objects:
                public_exits[zone, direction] = (objects[0], declared[direction])
            elif direction not in managed_counts:
                missing[f"{zone}:{direction}"] = (zone, direction)

    if missing:
        _diagnose_missing_exits(missing)
    targets = {target for _, _, _, target, _ in managed_exits}
    actual_rooms = candidate_rooms | load_rooms(targets - candidates)
    for zone, direction, obj, target, visible in managed_exits:
        destination = actual_rooms.get(target)
        if destination is None or obj.db_destination_id != destination.pk:
            _exit_mismatch(zone, direction, obj.pk, f"관리 Exit 목적지 불일치 → {target}", visible)

    current_exits = {direction: obj for (zone, direction), (obj, _) in public_exits.items() if zone == current}
    public_doors = current_door_overlays(context, current, current_exits) if context else set()
    public_targets = {target for _, target in public_exits.values()}
    disclosed = origins.keys() | {zone for zone in (public_targets & visited) - candidates
                                  if zone in actual_rooms and actual_rooms[zone].access(viewer, "view")}
    nodes, edges = set(origins), set()
    for (zone, direction), (obj, target) in public_exits.items():
        known = target in disclosed
        closed = obj.pk in public_doors
        directional = sheet is not None and direction in PLANAR
        if not known:
            if directional:
                bounds.append((zone, direction, "×" if closed else "?"))
            else:
                name = direction if zone == current else f"{ROOMS[zone]['name']} {direction}"
                notices.append((name, "×" if closed else "?"))
        elif not directional or catalog.room_sheet[target] is None:
            name = direction if zone == current else f"{ROOMS[zone]['name']} {direction}"
            notices.append((name, "×" if closed else ROOMS[target]["name"]))
        elif catalog.room_sheet[target] != sheet.id:
            bounds.append((zone, direction, "×" if closed else "+"))
        elif target in origins or near:
            nodes.add(target)
            edges.add((zone, direction, target))
            if closed:
                bounds.append((zone, direction, "×"))

    # 안정 ID 순서를 보존하는 요청별 임시 키. 내부 ID는 결과에 남기지 않는다.
    keys = {zone: str(index).zfill(len(str(len(nodes)))) for index, zone in enumerate(sorted(nodes))}
    edge_pairs = {(source, target) for source, _, target in edges}
    visible_edges = {(source, direction) for source, direction, _ in edges}
    positions = {keys[zone]: (keys[ref], offset) for zone, (ref, offset) in catalog.positions.items()
                 if zone in keys and ref in keys and ((zone, ref) in edge_pairs or (ref, zone) in edge_pairs)}
    routes = {(keys[source], direction): points for (source, direction), points in catalog.routes.items()
              if (source, direction) in visible_edges}
    # 비방향 출구는 목록에서 한도를 적용한다. 정식 8방향은 배치에서 제한된다.
    ordered = {name: index for index, name in enumerate(ordered_directions(sorted({name for name, _ in notices})))}
    notices.sort(key=lambda entry: ordered[entry[0]])
    omitted = len(notices) > 12
    return PublicMap(
        {keys[zone]: ROOMS[zone]["name"] for zone in sorted(nodes)},
        tuple(sorted((keys[src], direction, keys[dest]) for src, direction, dest in edges)),
        positions, routes,
        tuple(keys[zone] for zone in (sheet.anchors if sheet else ()) if zone in keys),
        tuple((keys[zone], direction, symbol) for zone, direction, symbol in bounds if direction in PLANAR),
        tuple(notices[:12]), keys.get(current), keys.get(center), omitted,
    )
