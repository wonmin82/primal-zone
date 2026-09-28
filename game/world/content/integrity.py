"""정적 월드 정의의 참조와 stable ID를 검사한다. DB를 읽지 않는다."""

from math import isfinite
from numbers import Real

from world.content import (
    ENEMIES,
    EXCHANGE,
    ITEMS,
    REGION_ENEMIES,
    REGIONS,
    ROOMS,
    SHOP,
    spawn_id_for,
)
from world.content.environment import EXPOSURES, LIGHT_PROFILES, WEATHER_ZONES, WEATHERS
from world.content.facilities import FACILITIES
from world.quests import QUESTS

OPPOSITE = {"북": "남", "남": "북", "동": "서", "서": "동"}


def positive_number(value):
    return isinstance(value, Real) and not isinstance(value, bool) and isfinite(value) and value > 0


def headquarters_errors():
    """본부 1단계의 고정 동선과 시설 위치를 검사한다. 층간 출구는 아직 없다."""
    expected = {
        "staging_room": {"남": "hq_concourse"},
        "hq_concourse": {"북": "staging_room", "서": "dock", "동": "support_1f_c"},
        "dock": {"북": "grass", "동": "hq_concourse"},
        "support_roof": {},
    }
    positions = ("w2", "w1", "c", "e1", "e2")
    corridors = []
    for floor in (1, 2, 3):
        row = [f"support_{floor}f_{position}" for position in positions]
        corridors.extend(row)
        for index, zone in enumerate(row):
            expected[zone] = {}
            if index:
                expected[zone]["서"] = row[index - 1]
            if index < len(row) - 1:
                expected[zone]["동"] = row[index + 1]
    expected["support_1f_c"]["남"] = "hq_concourse"
    facilities = (
        ("salvage_office", "support_1f_w2"),
        ("storage_room", "support_1f_w1"),
        ("supply_shop", "support_1f_e1"),
        ("infirmary", "support_2f_w1"),
        ("training_room", "support_2f_e1"),
        ("armor_shop", "support_3f_w1"),
        ("weapon_shop", "support_3f_e1"),
    )
    for facility, corridor in facilities:
        expected[facility] = {"남": corridor}
        expected[corridor]["북"] = facility
    issues = []
    for zone, exits in expected.items():
        if ROOMS.get(zone, {}).get("exits") != exits:
            issues.append(f"{zone}: 본부 1단계 출구 배치가 올바르지 않습니다.")
    for zone in corridors:
        blocked = ROOMS.get(zone, {}).get("blocked_exits", {})
        if not isinstance(blocked, dict) or set(blocked) != {"북", "남"} - set(expected[zone]):
            issues.append(f"{zone}: 지원동 폐쇄 출입구 배치가 올바르지 않습니다.")
    for facility, corridor in facilities:
        incoming = [(zone, direction) for zone, room in ROOMS.items()
                    for direction, target in room["exits"].items() if target == facility]
        if incoming != [(corridor, "북")]:
            issues.append(f"{facility}: 시설 Room은 지정 복도에서만 연결되어야 합니다.")
    return issues


def errors(interactables):
    issues = headquarters_errors()
    for identity, definition in FACILITIES.items():
        if not isinstance(identity, str) or not identity.strip() or not isinstance(definition, dict):
            issues.append(f"{identity}: 시설 상태 정의가 유효하지 않습니다.")
        elif type(definition.get("default")) is not bool:
            issues.append(f"{identity}: 시설 기본 상태는 참/거짓이어야 합니다.")
    if len(ENEMIES) != sum(len(enemies) for enemies in REGION_ENEMIES.values()):
        issues.append("Enemy type ID가 지역 사이에서 중복되었습니다.")
    membership = [zone for region in REGIONS.values() for zone in region["rooms"]]
    if len(membership) != len(set(membership)) or set(membership) != set(ROOMS):
        issues.append("모든 Room은 정확히 하나의 Region에 속해야 합니다.")
    if len(ROOMS) != sum(len(region["rooms"]) for region in REGIONS.values()):
        issues.append("Room ID가 중복되었습니다.")
    for region_id, region in REGIONS.items():
        if region.get("weather_zone") not in WEATHER_ZONES:
            issues.append(f"{region_id}: Weather Zone이 없습니다.")
        if region["entry"] not in region["rooms"]:
            issues.append(f"{region_id}: 진입 Room이 Region에 없습니다.")
    spawns = []
    for zone, room in ROOMS.items():
        for light in room.get("facility_lights", []):
            always_on = light.get("always_on") is True
            powered = light.get("power") in FACILITIES
            if not positive_number(light.get("strength")) or not (
                (always_on and "power" not in light) or (powered and "always_on" not in light)
            ):
                issues.append(f"{zone}: 시설 조명 정의가 유효하지 않습니다.")
        for hint in room.get("hints", []):
            if not isinstance(hint, dict):
                issues.append(f"{zone}: 안내는 target/action 또는 text여야 합니다.")
                continue
            if set(hint) == {"text"}:
                if not isinstance(hint["text"], str) or not hint["text"].strip():
                    issues.append(f"{zone}: 일반 안내는 비어 있지 않은 문자열이어야 합니다.")
            elif set(hint) == {"target", "action"}:
                definition = interactables.get(hint["target"], {})
                if definition.get("room") != zone or hint["action"] not in definition.get("actions", ()):
                    issues.append(f"{zone}: 안내 대상의 장소 또는 행동이 유효하지 않습니다.")
            else:
                issues.append(f"{zone}: 안내는 target/action 또는 text여야 합니다.")
        if room.get("exposure") not in EXPOSURES:
            issues.append(f"{zone}: exposure가 유효하지 않습니다.")
        if room.get("light_profile") not in LIGHT_PROFILES:
            issues.append(f"{zone}: light_profile이 유효하지 않습니다.")
        if set(room.get("spawn_ids", {})) - set(room["enemies"]):
            issues.append(f"{zone}: 사용되지 않는 spawn ID 지정이 있습니다.")
        blocked = room.get("blocked_exits", {})
        if not isinstance(blocked, dict):
            issues.append(f"{zone}: blocked_exits는 방향과 문구의 dict여야 합니다.")
            blocked = {}
        for direction, message in blocked.items():
            if direction not in OPPOSITE:
                issues.append(f"{zone}: 폐쇄 출입구 방향이 유효하지 않습니다.")
            if direction in room["exits"]:
                issues.append(f"{zone}:{direction}: 실제 출구와 폐쇄 출입구가 겹칩니다.")
            if not isinstance(message, str) or not message.strip():
                issues.append(f"{zone}:{direction}: 폐쇄 출입구 문구는 비어 있지 않은 문자열이어야 합니다.")
        returns = room.get("return_directions", {})
        if not isinstance(returns, dict):
            issues.append(f"{zone}: 복귀 방향 정의는 dict여야 합니다.")
            returns = {}
        for direction, reverse in returns.items():
            if direction not in room["exits"] or not isinstance(reverse, str) or reverse not in OPPOSITE:
                issues.append(f"{zone}:{direction}: 복귀 방향이 유효하지 않습니다.")
        returns = {direction: reverse for direction, reverse in returns.items()
                   if isinstance(reverse, str) and reverse in OPPOSITE}
        for direction, target in room["exits"].items():
            if target not in ROOMS:
                issues.append(f"{zone}:{direction}: 대상 Room이 없습니다.")
            elif direction in OPPOSITE and ROOMS[target]["exits"].get(returns.get(direction, OPPOSITE[direction])) != zone:
                issues.append(f"{zone}:{direction}: 되돌아오는 출구가 없습니다.")
        for enemy in room["enemies"]:
            if enemy not in ENEMIES:
                issues.append(f"{zone}: {enemy} 정의가 없습니다.")
            spawns.append(spawn_id_for(zone, enemy))
        requirement = room.get("requires")
        if requirement and (
            requirement["quest"] not in QUESTS
            or requirement["flag"]
            not in {flag for flag, *_ in QUESTS[requirement["quest"]]["steps"]}
        ):
            issues.append(f"{zone}: Gate 진행 필드가 없습니다.")
        if requirement and "observe_message" in requirement:
            message = requirement["observe_message"]
            if not isinstance(message, str) or not message.strip():
                issues.append(f"{zone}: 관찰 차단 문구는 비어 있지 않은 문자열이어야 합니다.")
    if len(spawns) != len(set(spawns)):
        issues.append("Enemy spawn ID가 중복되었습니다.")
    for enemy, data in ENEMIES.items():
        if not data.get("presence") or not data.get("distant_presence"):
            issues.append(f"{enemy}: 현재/원거리 존재 묘사가 없습니다.")
        if data["drop"] not in ITEMS:
            issues.append(f"{enemy}: 전리품 정의가 없습니다.")
        if data.get("boss_quest") and data["boss_quest"] not in QUESTS:
            issues.append(f"{enemy}: 임무 정의가 없습니다.")
    for key in SHOP.keys() | EXCHANGE.keys():
        if key not in ITEMS:
            issues.append(f"{key}: 상점 아이템 정의가 없습니다.")
    for key, data in ITEMS.items():
        source = data.get("power_source")
        if source and (not isinstance(source.get("type"), str) or not source["type"].strip() or not positive_number(source.get("capacity_seconds"))):
            issues.append(f"{key}: 전원 정의가 유효하지 않습니다.")
        light = data.get("light_source")
        if light and (not positive_number(light.get("strength")) or type(light.get("range")) is not int or light["range"] < 0 or not isinstance(light.get("power_type"), str) or not light["power_type"].strip()):
            issues.append(f"{key}: 광원 정의가 유효하지 않습니다.")
    for identity, data in interactables.items():
        if data["room"] not in ROOMS:
            issues.append(f"{identity}: 대상 Room이 없습니다.")
    for quest_id, data in QUESTS.items():
        requirement = data.get("requires")
        if requirement and (
            requirement[0] not in QUESTS
            or requirement[1] not in {flag for flag, *_ in QUESTS[requirement[0]]["steps"]}
        ):
            issues.append(f"{quest_id}: 선행 임무 필드가 없습니다.")
        flags = [step[0] for step in data["steps"]]
        if len(flags) != len(set(flags)) or not flags or flags[-1] != "claimed":
            issues.append(f"{quest_id}: 임무 단계가 잘못되었습니다.")
        if len(data["hints"]) != len(flags) + 1:
            issues.append(f"{quest_id}: 안내 단계 수가 맞지 않습니다.")
        for _, target, role, _ in data["steps"]:
            if target not in (ENEMIES if role == "hostile" else interactables):
                issues.append(f"{quest_id}: 단계 대상 {target} 정의가 없습니다.")
    for zone, data in WEATHER_ZONES.items():
        if data.get("initial") not in WEATHERS:
            issues.append(f"{zone}: 초기 날씨가 없습니다.")
    for weather, data in WEATHERS.items():
        duration = data.get("duration", ())
        if (
            not isinstance(duration, (tuple, list))
            or len(duration) != 2
            or not all(positive_number(value) for value in duration)
            or duration[0] > duration[1]
        ):
            issues.append(f"{weather}: 날씨 지속 시간이 유효하지 않습니다.")
        transitions = data.get("transitions", {})
        if not transitions or any(
            key not in WEATHERS or not positive_number(weight)
            for key, weight in transitions.items()
        ):
            issues.append(f"{weather}: 날씨 전이 대상/가중치가 유효하지 않습니다.")
        if set(data.get("presence", {})) != EXPOSURES:
            issues.append(f"{weather}: exposure별 환경 문장이 없습니다.")
    return issues
