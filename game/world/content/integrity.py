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


def errors(interactables):
    issues = []
    for identity, definition in FACILITIES.items():
        if not isinstance(identity, str) or not identity.strip() or type(definition.get("default")) is not bool:
            issues.append(f"{identity}: 시설 상태 정의가 유효하지 않습니다.")
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
        for direction, target in room["exits"].items():
            if target not in ROOMS:
                issues.append(f"{zone}:{direction}: 대상 Room이 없습니다.")
            elif direction in OPPOSITE and ROOMS[target]["exits"].get(OPPOSITE[direction]) != zone:
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
