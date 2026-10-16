"""Door SSOT: 설치 증거 검증, 읽기 전용 유효 상태, 직렬 상태 변경."""

import logging
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from time import time

from django.db.models import Q
from evennia.objects.models import ObjectDB

from world import rules
from world import text as ft
from world.content import ordered_directions
from world.content.doors import AUTO_CLOSE_SECONDS, DOORS
from world.door_entities.models import Door, DoorInstallation
from world.multiplayer import after_change, world_change

logger = logging.getLogger(__name__)
UNAVAILABLE = "UNAVAILABLE"


def timestamp(value):
    return isinstance(value, Real) and not isinstance(value, bool) and isfinite(value) and value >= 0


def _endpoint(exit_obj, endpoint, expected_pk):
    origin, direction, destination = endpoint
    def unique_room(room, identity):
        return list(ObjectDB.objects.filter(db_tags__db_key=identity,
                    db_tags__db_category="primal_zone_room").values_list("pk", flat=True).distinct()) == [room.pk]
    return bool(exit_obj and exit_obj.pk == expected_pk and exit_obj.is_typeclass("typeclasses.exits.Exit", exact=True)
                and exit_obj.location and exit_obj.location.db.zone_id == origin and exit_obj.key == direction
                and exit_obj.location.is_typeclass("typeclasses.zone_rooms.ZoneRoom", exact=True)
                and unique_room(exit_obj.location, origin)
                and exit_obj.destination and exit_obj.destination.db.zone_id == destination
                and exit_obj.destination.is_typeclass("typeclasses.zone_rooms.ZoneRoom", exact=True)
                and unique_room(exit_obj.destination, destination)
                and exit_obj.tags.get(category="primal_zone_exit", return_list=True) == [f"{origin}:{direction}"])


def policy_errors(door, definition):
    issues = []
    expected = definition["endpoints"]
    if (door.room_a != expected[0][0] or door.room_b != expected[1][0]
            or door.direction_a != expected[0][1] or door.direction_b != expected[1][1]
            or door.lockable != definition["lockable"] or door.key_id != definition["key_id"]
            or door.inside_room_id != definition["inside_room_id"]):
        issues.append("Door 정책/관계 불일치")
    if door.state not in ("OPEN", "CLOSED", "LOCKED") or (door.state == "LOCKED" and not door.lockable):
        issues.append("Door 상태 손상")
    if ((door.state == "OPEN" and not timestamp(door.auto_close_at))
            or (door.state != "OPEN" and door.auto_close_at is not None)):
        issues.append("Door 예약 손상")
    return issues


def installation_errors(identity):
    """정의 검사와 별개로 실제 원본 PK와 endpoint 관계를 검증한다. 복구하지 않는다."""
    definition = DOORS.get(identity)
    journal = DoorInstallation.objects.filter(door_id=identity).first()
    door = Door.objects.filter(door_id=identity).first()
    issues = []
    if not definition or not journal or not door or door.pk != journal.door_pk:
        return ["설치 이력/원본 Door 불일치"]
    endpoints = journal.endpoints
    if (not timestamp(journal.installed_at) or not isinstance(endpoints, list) or len(endpoints) != 2
            or any(not isinstance(e, dict) or set(e) != {"exit_pk", "room_pk", "target_pk"} for e in endpoints)):
        return ["설치 증거 손상"]
    for index, expected in enumerate(definition["endpoints"]):
        proof = endpoints[index]
        if any(type(proof[k]) is not int or proof[k] < 1 for k in proof):
            issues.append("설치 PK 손상")
            continue
        obj = ObjectDB.objects.filter(pk=proof["exit_pk"]).first()
        if (not _endpoint(obj, expected, proof["exit_pk"]) or obj.db_location_id != proof["room_pk"]
                or obj.db_destination_id != proof["target_pk"]):
            issues.append("원본 endpoint 관계 손상")
        if getattr(door, f"exit_{'ab'[index]}_id") != proof["exit_pk"]:
            issues.append("Door endpoint 참조 손상")
        if obj and obj.db.door_id != identity:
            issues.append("Exit Door 참조 손상")
        if Door.objects.exclude(pk=door.pk).filter(Q(exit_a_id=proof["exit_pk"]) | Q(exit_b_id=proof["exit_pk"])).exists():
            issues.append("Exit 중복 결부")
    issues.extend(policy_errors(door, definition))
    if door.key_id:
        from world.content import ITEMS
        from world.item_entities.policy import definition_errors
        key = ITEMS.get(door.key_id, {})
        if key.get("item_type") != "key" or definition_errors(door.key_id, key):
            issues.append("열쇠 정의 손상")
    return issues


def effective_door_state(identity, now=None):
    now = time() if now is None else now
    issues = installation_errors(identity)
    if not timestamp(now) or issues:
        logger.warning("Door %s 이용 차단: %s", identity, issues or ["조회 시각 손상"])
        return UNAVAILABLE
    door = Door.objects.get(door_id=identity)
    return "CLOSED" if door.state == "OPEN" and now >= door.auto_close_at else door.state


def identity_for_exit(exit_obj):
    """참조가 소실돼도 고정 endpoint/설치 PK로 관리 문을 안전 차단한다."""
    for identity, data in DOORS.items():
        if any(exit_obj.location and exit_obj.location.db.zone_id == origin and exit_obj.key == direction
               for origin, direction, _ in data["endpoints"]):
            return identity
    for journal in DoorInstallation.objects.all():
        if isinstance(journal.endpoints, list) and any(isinstance(e, dict) and e.get("exit_pk") == exit_obj.pk for e in journal.endpoints):
            return journal.door_id
    return exit_obj.db.door_id or None


def state_for_exit(exit_obj, now=None):
    identity = identity_for_exit(exit_obj)
    if not identity:
        return None
    state = effective_door_state(identity, now)
    door = Door.objects.filter(door_id=identity).first()
    if not door or exit_obj.pk not in (door.exit_a_id, door.exit_b_id):
        return UNAVAILABLE
    return state


def preserved_endpoint(zone, direction):
    identities = [identity for identity, data in DOORS.items()
                  if any((origin, key) == (zone, direction) for origin, key, _ in data["endpoints"])]
    return (DoorInstallation.objects.filter(door_id__in=identities).exists()
            or Door.objects.filter(door_id__in=identities).exists())


def proven_installed_endpoint(exit_obj, managed_identity):
    """손상 속성과 별개로 원본 소속을 입증한다. 추측 편입/복구 권한은 부여하지 않는다."""
    for identity, definition in DOORS.items():
        for index, (origin, direction, _) in enumerate(definition["endpoints"]):
            if managed_identity != f"{origin}:{direction}":
                continue
            journal = DoorInstallation.objects.filter(door_id=identity).first()
            door = Door.objects.filter(door_id=identity).first()
            if not journal or not door or door.pk != journal.door_pk or not timestamp(journal.installed_at):
                return None
            proofs = journal.endpoints
            if (not isinstance(proofs, list) or len(proofs) != 2
                    or any(not isinstance(p, dict) or set(p) != {"exit_pk", "room_pk", "target_pk"}
                           or any(type(v) is not int or v < 1 for v in p.values()) for p in proofs)):
                return None
            ids = [p["exit_pk"] for p in proofs]
            if ids[index] != exit_obj.pk or len(set(ids)) != 2 or ids != [door.exit_a_id, door.exit_b_id]:
                return None
            for proof, (room, _, target) in zip(proofs, definition["endpoints"]):
                for field, zone in (("room_pk", room), ("target_pk", target)):
                    matches = list(ObjectDB.objects.filter(db_tags__db_key=zone,
                                   db_tags__db_category="primal_zone_room").distinct())
                    if (len(matches) != 1 or matches[0].pk != proof[field] or matches[0].db.zone_id != zone
                            or not matches[0].is_typeclass("typeclasses.zone_rooms.ZoneRoom", exact=True)):
                        return None
            if Door.objects.exclude(pk=door.pk).filter(Q(exit_a_id__in=ids) | Q(exit_b_id__in=ids)).exists():
                return None
            for other in DoorInstallation.objects.exclude(pk=journal.pk):
                if other.door_pk == journal.door_pk or (isinstance(other.endpoints, list) and any(
                        isinstance(p, dict) and p.get("exit_pk") in ids for p in other.endpoints)):
                    return None
            return identity
    return None


def install_doors(now=None):
    """최초 설치만 상태를 생성. 이후에는 유일한 원본 증거로 무손실 참조만 복원한다."""
    from world.bootstrap import EXIT_CATEGORY

    now = time() if now is None else now
    if not timestamp(now):
        raise ValueError("Door 설치 시각이 유효하지 않습니다.")
    with world_change():
        for identity, definition in DOORS.items():
            journal = DoorInstallation.objects.filter(door_id=identity).first()
            door = Door.objects.filter(door_id=identity).first()
            if not journal:
                if door:
                    logger.error("Door %s 설치 이력 없는 기존 레코드; 초기화 금지", identity)
                    continue
                endpoints = []
                for endpoint in definition["endpoints"]:
                    origin, direction, _ = endpoint
                    candidates = list(ObjectDB.objects.filter(db_tags__db_key=f"{origin}:{direction}",
                                      db_tags__db_category=EXIT_CATEGORY).distinct())
                    if len(candidates) != 1 or not _endpoint(candidates[0], endpoint, candidates[0].pk):
                        raise ValueError(f"Door {identity} 신규 endpoint 불일치")
                    obj = candidates[0]
                    if obj.db.door_id or Door.objects.filter(Q(exit_a=obj) | Q(exit_b=obj)).exists():
                        raise ValueError(f"Door {identity} endpoint 기존 결부")
                    endpoints.append(obj)
                a, b = endpoints
                door = Door.objects.create(door_id=identity, name=definition["name"], aliases=definition["aliases"],
                    room_a=definition["endpoints"][0][0], room_b=definition["endpoints"][1][0], exit_a=a, exit_b=b,
                    direction_a=a.key, direction_b=b.key, state=definition["initial_state"], lockable=definition["lockable"],
                    key_id=definition["key_id"], inside_room_id=definition["inside_room_id"],
                    auto_close_at=now + AUTO_CLOSE_SECONDS if definition["initial_state"] == "OPEN" else None)
                DoorInstallation.objects.create(door_id=identity, door_pk=door.pk, installed_at=now,
                    endpoints=[dict(exit_pk=obj.pk, room_pk=obj.db_location_id, target_pk=obj.db_destination_id) for obj in endpoints])
                for obj in endpoints:
                    obj.db.door_id = identity
                continue
            # 원본 PK와 관계가 모두 일치하는 경우에만 참조를 복원한다.
            if (door and door.pk == journal.door_pk and not policy_errors(door, definition)
                    and timestamp(journal.installed_at) and isinstance(journal.endpoints, list)
                    and len(journal.endpoints) == 2):
                originals = []
                for proof, expected in zip(journal.endpoints, definition["endpoints"]):
                    if (not isinstance(proof, dict) or set(proof) != {"exit_pk", "room_pk", "target_pk"}
                            or any(type(value) is not int or value < 1 for value in proof.values())):
                        break
                    obj = ObjectDB.objects.filter(pk=proof.get("exit_pk")).first() if isinstance(proof, dict) else None
                    if (not obj or not _endpoint(obj, expected, obj.pk) or obj.db_location_id != proof.get("room_pk")
                            or obj.db_destination_id != proof.get("target_pk") or obj.db.door_id not in (None, identity)
                            or Door.objects.exclude(pk=door.pk).filter(Q(exit_a=obj) | Q(exit_b=obj)).exists()):
                        break
                    originals.append(obj)
                if len(originals) == 2:
                    # 저장 상태/정책이 정상인 경우의 참조 복원만 허용한다.
                    saved_ids = door.exit_a_id, door.exit_b_id
                    if saved_ids != tuple(obj.pk for obj in originals) and any(
                            pk not in (obj.pk for obj in originals) for pk in saved_ids):
                        logger.error("Door %s 다른 Exit에 결부된 참조; 추측 복구 금지", identity)
                    else:
                        for obj in originals:
                            obj.db.door_id = identity
                        door.exit_a, door.exit_b = originals
                        door.save(update_fields=["exit_a", "exit_b"])
            if not installation_errors(identity):
                door.name, door.aliases = definition["name"], definition["aliases"]
                door.save(update_fields=["name", "aliases"])
            else:
                logger.error("Door %s 손상 보존: %s", identity, installation_errors(identity))


@dataclass(frozen=True)
class DoorTarget:
    identity: str
    direction: str
    exit_pk: int

    @property
    def name(self):
        return DOORS[self.identity]["name"]

    @property
    def names(self):
        return [self.name, *DOORS[self.identity]["aliases"], "문", self.direction + " 문"]


def current_doors(caller, now=None):
    from world.observation import context_for, perceives
    room = caller.location
    if not room or not perceives(context_for(caller, room, now).snapshot, "normal"):
        return []
    result = []
    for obj in room.exits:
        identity = identity_for_exit(obj)
        if identity in DOORS and obj.access(caller, "view"):
            result.append(DoorTarget(identity, obj.key, obj.pk))
    order = list(ordered_directions([t.direction for t in result]))
    return sorted(result, key=lambda t: (order.index(t.direction), t.identity))


def resolve_door(caller, value, action, now=None):
    from world.actions.resolver import select_role
    from world.actions.schema import ReferenceKind, RoleDefinition
    from world.selection_numbers.api import descriptor
    if not value.strip():
        raise rules.RuleError(f"대상 이름 뒤에 {action}를 입력하세요. 예: 관리실 문 {action}")
    candidates = current_doors(caller, now)
    from evennia.objects.models import ObjectDB

    references = {descriptor(ObjectDB.objects.get(pk=target.exit_pk)).reference for target in candidates}
    reference = select_role(caller, RoleDefinition("provider", (ReferenceKind.DOOR,)), value, candidates=references)[0]
    return next(target for target in candidates if str(target.exit_pk) == reference.identity)


def description(target, now=None):
    state = effective_door_state(target.identity, now)
    if state == UNAVAILABLE:
        return "그 방향은 지금 이용할 수 없다."
    return f"{target.direction}쪽 {target.name}" + {"OPEN": "이 열려 있다.", "CLOSED": "은 닫혀 있다.", "LOCKED": "은 잠겨 있다."}[state]


def actions_for(caller, target, now=None):
    if caller.profile_snapshot().get("combat_target"):
        return []
    state = effective_door_state(target.identity, now)
    if state == UNAVAILABLE:
        return []
    data = DOORS[target.identity]
    key = False
    if data["lockable"]:
        from world.door_keys import owned_key
        try:
            key = owned_key(caller) is not None
        except rules.RuleError:
            pass  # 손상된 소지품에서 조작 권한을 추측하지 않는다.
    actions = {"OPEN": ["닫아"], "CLOSED": ["열어"], "LOCKED": []}[state]
    if data["lockable"] and state == "CLOSED" and key:
        actions.append("잠궈")
    if data["lockable"] and state == "LOCKED" and (key or caller.zone == data["inside_room_id"]):
        actions.append("풀어")
    return [{"label": action, "command": target.direction + " 문 " + action} for action in actions]


def web_controls(caller, now=None, *, action_rows=None):
    from world.actions.manifest import get_index
    from world.actions.presentation import action_controls
    from world.selection_numbers.api import number_for

    rows = action_controls(caller, get_index(), now) if action_rows is None else action_rows
    return [dict(name=target.name, label=target.direction + " " + target.name, role="object",
                 look_command=f"문 {number_for('door', target.exit_pk)} 봐",
                 actions=[row for row in rows if row["action"]["roles"].get("provider", [{}])[0].get("kind") == "door"
                          and row["action"]["roles"]["provider"][0]["identity"] == str(target.exit_pk)])
            for target in current_doors(caller, now)]


def look_door(caller, value, now):
    """일반 객체와 정확한 문 이름이 충돌하면 임의 우선순위를 주지 않는다."""
    from world.content import ITEMS
    from world.targets import matching, names, normalized, parse_selector, room_objects

    # 기존 방향/객체 봐는 Door 감지 조회 전에 원래 경로로 보낸다.
    # 특히 Quest 차단 출구에서는 환경/목적지 조회보다 기존 거절이 우선한다.
    known = ["문", *[name for data in DOORS.values() for name in [data["name"], *data["aliases"]]]]
    known += [direction + " 문" for data in DOORS.values() for _, direction, _ in data["endpoints"]]
    selector = parse_selector(value, known)
    if normalized(selector.name) not in {normalized(name) for name in known}:
        return None
    objects = room_objects(caller, observed_at=now)
    inventory = caller.profile_snapshot()["inventory"]
    if (matching(objects, selector, names) or any(quantity and normalized(selector.name) in
            {normalized(identity), normalized(ITEMS[identity]["name"])} for identity, quantity in inventory.items())):
        if matching(current_doors(caller, now), selector, lambda target: target.names):
            raise rules.RuleError("대상이 모호합니다. 문 방향 또는 다른 대상의 정확한 이름을 지정하세요.")
        return None  # 실제 Door 후보가 없다면 같은 이름의 기존 객체/소지품만 조회한다.
    target = resolve_door(caller, value, "봐", now)
    examples = [ft.token("command", action["command"]) for action in actions_for(caller, target, now)]
    return ft.compact(ft.token("object", target.name), description(target, now),
                      *([ft.text("조작: ", ft.join(examples, " · "))] if examples else []))


def exit_block(exit_obj, caller, now=None):
    state = state_for_exit(exit_obj, now)
    if state in (None, "OPEN"):
        return None
    target = next((t for t in current_doors(caller, now) if t.exit_pk == exit_obj.pk), None)
    if not target or state == UNAVAILABLE:
        return "출구를 이용할 수 없습니다."
    return "문이 잠겨 있습니다. 먼저 풀어 주세요." if state == "LOCKED" else "문이 닫혀 있습니다. 먼저 열어 주세요."


def _push_endpoints(identity):
    from world.bootstrap import get_room
    for zone, _, _ in DOORS[identity]["endpoints"]:
        room = get_room(zone)
        for obj in room.contents if room else ():
            if hasattr(obj, "push_state") and obj.sessions.count():
                try:
                    obj.push_state()
                except Exception:
                    logger.exception("Door %s 커밋 후 상태 전송 실패: #%s", identity, obj.pk)


def publish(identity, caller=None, message=None):
    if caller and message:
        def deliver():
            try:
                caller.msg(message)
            except Exception:
                logger.exception("Door 커밋 후 메시지 전송 실패: #%s", caller.pk)
        after_change(deliver)
    after_change(lambda: _push_endpoints(identity))


def operate(caller, value, action, now=None):
    """문 관찰/도메인 호환 호출. 공개 실행은 Action의 안정 Endpoint를 사용한다."""
    target = resolve_door(caller, value, action, now)
    from evennia.objects.models import ObjectDB

    return operate_endpoint(caller, ObjectDB.objects.get(pk=target.exit_pk), action, now)


def operate_endpoint(caller, endpoint, action, now=None):
    with world_change():
        rules.require_peace(caller.profile_snapshot())
        now = time() if now is None else now
        target = next((target for target in current_doors(caller, now) if target.exit_pk == endpoint.pk), None)
        if target is None or endpoint.location != caller.location or not endpoint.access(caller, "call"):
            raise rules.RuleError("원래 문이 없어졌거나 위치·권한이 바뀌었습니다.")
        state = effective_door_state(target.identity, now)
        if state == UNAVAILABLE:
            raise rules.RuleError("그 문은 지금 이용할 수 없습니다.")
        door = Door.objects.get(door_id=target.identity)
        if action in ("잠궈", "풀어"):
            if not door.lockable:
                raise rules.RuleError("잠글 수 없는 문입니다.")
            if action == "잠궈" or caller.zone != door.inside_room_id:
                from world.door_keys import owned_key
                if owned_key(caller) is None:
                    raise rules.RuleError("관리실 열쇠가 없어 잠금을 조작할 수 없습니다.")
        expected, following = {"열어": ("CLOSED", "OPEN"), "닫아": ("OPEN", "CLOSED"),
                               "잠궈": ("CLOSED", "LOCKED"), "풀어": ("LOCKED", "CLOSED")}[action]
        if state == following:
            after_change(lambda: caller.msg(ft.text("이미 " + {"OPEN": "열려", "CLOSED": "닫혀" if action == "닫아" else "잠금이 풀려", "LOCKED": "잠겨"}[state] + " 있다.")))
            return False
        if state != expected:
            raise rules.RuleError("먼저 잠금을 풀어 주세요." if state == "LOCKED" else "먼저 문을 닫아 주세요.")
        door.state = following
        door.auto_close_at = now + AUTO_CLOSE_SECONDS if following == "OPEN" else None
        door.save(update_fields=["state", "auto_close_at"])
        message = ft.text(ft.token("object", target.name), {"열어": "을 열었다.", "닫아": "을 닫았다.", "잠궈": "을 잠갔다.", "풀어": "의 잠금을 풀었다."}[action])
        publish(target.identity, caller, message)
        return True


def reconcile_doors(now=None):
    now = time() if now is None else now
    with world_change():
        for identity in DOORS:
            if effective_door_state(identity, now) != "CLOSED":
                continue
            door = Door.objects.get(door_id=identity)
            if door.state == "OPEN" and now >= door.auto_close_at:
                door.state, door.auto_close_at = "CLOSED", None
                door.save(update_fields=["state", "auto_close_at"])
                publish(identity)


def traverse(exit_obj, caller, destination):
    """실제 Exit 이동·방문 기록·통과 완료 시각의 예약을 함께 커밋한다."""
    from world.access import can_enter, entry_message
    from world.navigation import blocked_exit_message

    with world_change():
        rules.require_peace(caller.profile_snapshot())
        origin = caller.location
        if origin != exit_obj.location or destination != exit_obj.destination:
            raise rules.RuleError("출구를 이용할 수 없습니다.")
        if (not exit_obj.access(caller, "traverse") or not any(command.access(caller, "cmd")
                for command in exit_obj.create_exit_cmdset(exit_obj) if getattr(command, "is_exit", False))):
            raise rules.RuleError("출구를 이용할 수 없습니다.")
        message = blocked_exit_message(origin.db.zone_id, exit_obj.key)
        if message or not can_enter(caller, destination):
            raise rules.RuleError(message or str(entry_message(caller, destination)))
        message = exit_block(exit_obj, caller)
        if message:
            raise rules.RuleError(message)
        identity = identity_for_exit(exit_obj)
        if not caller.move_to(destination, move_type="traverse", exit_obj=exit_obj):
            raise rules.RuleError("이동하지 못했습니다.")
        # Hook이 목적지를 바꾸거나 이동 중 만료 경계에 진입한 경우 모두 롤백한다.
        completed_at = time()
        if (caller.location != destination or exit_obj.location != origin or exit_obj.destination != destination
                or state_for_exit(exit_obj, completed_at) != "OPEN"):
            raise rules.RuleError("출구를 이용할 수 없습니다.")
        door = Door.objects.get(door_id=identity)
        door.auto_close_at = completed_at + AUTO_CLOSE_SECONDS
        door.save(update_fields=["auto_close_at"])
        exit_obj.at_post_traverse(caller, origin)
        publish(identity)
    return True
