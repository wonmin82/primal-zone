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
    from evennia.objects.models import ObjectDB

    from world.bootstrap import CATEGORY

    if not zones:
        return {}
    tags = defaultdict(list)
    matching = ObjectDB.objects.filter(db_tags__db_category=CATEGORY, db_tags__db_key__in=zones)
    scoped = ObjectDB.objects.filter(pk__in=matching.values("pk"), db_tags__db_category=CATEGORY)
    for pk, zone in scoped.values_list("pk", "db_tags__db_key"):
        tags[pk].append(zone)
    if not tags:
        return {}
    zone_attrs = defaultdict(list)
    memberships = ObjectDB.db_attributes.through.objects.filter(
        objectdb_id__in=tags, attribute__db_key="zone_id", attribute__db_category__isnull=True,
    ).select_related("attribute")
    for membership in memberships:
        # Use the stored value rather than attaching request data to Evennia's shared model.
        zone_attrs[membership.objectdb_id].append(membership.attribute.value)
    result, invalid = {}, set()
    for pk, room in ObjectDB.objects.in_bulk(tags).items():
        identities = tags[pk]
        if (len(identities) != 1 or zone_attrs[pk] != identities
                or room.db_typeclass_path != "typeclasses.zone_rooms.ZoneRoom"):
            invalid.update(identities)
        else:
            zone = identities[0]
            if zone in result:
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


def project(viewer, catalog, sheet, *, current, visited, now, center=None, near=False):
    from world.doors import current_door_overlays
    from world.observation import can_perceive, context_for

    candidates = ({current} if near or sheet is None else set(sheet.rooms)) & (visited | {current})
    origins = visible_rooms(viewer, candidates, current, visited)
    if current in candidates and (current not in origins or origins[current].pk != viewer.location.pk):
        raise RuntimeGraphMismatch(f"현재 Room 정체성 {current}")
    if not origins or (center is not None and center not in origins):
        raise MapAccessDenied

    grouped = load_exits(origins, viewer.location.pk)
    context = context_for(viewer, observed_at=now) if current in origins else None

    public_exits, bounds, notices = {}, [], []
    for zone, room in sorted(origins.items()):
        here = zone == current
        declared = ROOMS[zone]["exits"]
        blocked = ROOMS[zone].get("blocked_exits", {})
        exits, observed_static = defaultdict(list), set()
        for obj, identities in grouped[room.pk]:
            static = bool(identities)
            if static:
                observed_static.add(obj.key)
                if not obj.db_destination_id:
                    logger.warning("RuntimeGraphMismatch: 목적지 누락 %s/%s #%s", zone, obj.key, obj.pk)
                    continue
            visible = can_perceive(obj, context) if here else obj.access(viewer, "view")
            if not visible:
                continue
            if static:
                if (identities != [f"{zone}:{obj.key}"]
                        or obj.db_typeclass_path != "typeclasses.exits.Exit"
                        or obj.key not in declared):
                    raise RuntimeGraphMismatch(f"관리 Exit 정체성 {zone}/{obj.key} #{obj.pk}")
                exits[obj.key].append(obj)
            elif here and obj.db_destination_id:
                notices.append((obj.key, "지도에 배치되지 않은 출구"))
        for direction in ordered_directions(dict.fromkeys([*declared, *blocked, *sorted(exits)])):
            objects = exits[direction]
            if direction in blocked:
                if objects:
                    raise RuntimeGraphMismatch(f"폐쇄 방향에 실제 출구 {zone}/{direction}")
                if sheet is not None and direction in PLANAR:
                    bounds.append((zone, direction, "×"))
                else:
                    name = direction if here else f"{ROOMS[zone]['name']} {direction}"
                    notices.append((name, "×"))
            elif len(objects) > 1:
                raise RuntimeGraphMismatch(f"공개 Exit 중복 {zone}/{direction}")
            elif objects:
                public_exits[zone, direction] = (objects[0], declared[direction])
            elif direction not in observed_static:
                logger.warning("RuntimeGraphMismatch: Exit 누락 %s/%s", zone, direction)

    current_exits = {direction: obj for (zone, direction), (obj, _) in public_exits.items() if zone == current}
    public_doors = current_door_overlays(context, current, current_exits) if context else set()
    targets = {target for _, target in public_exits.values()}
    actual_rooms = origins | load_rooms(targets - origins.keys())
    disclosed = origins.keys() | {zone for zone in targets & visited if zone in actual_rooms
                                  and actual_rooms[zone].access(viewer, "view")}
    nodes, edges = set(origins), set()
    for (zone, direction), (obj, target) in public_exits.items():
        destination = actual_rooms.get(target)
        known = target in disclosed
        if destination is None or obj.db_destination_id != destination.pk:
            logger.warning("RuntimeGraphMismatch: %s/%s → %s (Exit #%s)", zone, direction, target, obj.pk)
            if known:
                raise RuntimeGraphMismatch(f"{zone}/{direction} → {target}")
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
