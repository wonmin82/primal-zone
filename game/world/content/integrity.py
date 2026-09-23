"""정적 월드 정의의 참조와 stable ID를 검사한다. DB를 읽지 않는다."""

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
from world.quests import QUESTS

OPPOSITE = {"북": "남", "남": "북", "동": "서", "서": "동"}


def errors(interactables):
    issues = []
    if len(ENEMIES) != sum(len(enemies) for enemies in REGION_ENEMIES.values()):
        issues.append("Enemy type ID가 지역 사이에서 중복되었습니다.")
    membership = [zone for region in REGIONS.values() for zone in region["rooms"]]
    if len(membership) != len(set(membership)) or set(membership) != set(ROOMS):
        issues.append("모든 Room은 정확히 하나의 Region에 속해야 합니다.")
    if len(ROOMS) != sum(len(region["rooms"]) for region in REGIONS.values()):
        issues.append("Room ID가 중복되었습니다.")
    for region_id, region in REGIONS.items():
        if region["entry"] not in region["rooms"]:
            issues.append(f"{region_id}: 진입 Room이 Region에 없습니다.")
    spawns = []
    for zone, room in ROOMS.items():
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
    if len(spawns) != len(set(spawns)):
        issues.append("Enemy spawn ID가 중복되었습니다.")
    for enemy, data in ENEMIES.items():
        if data["drop"] not in ITEMS:
            issues.append(f"{enemy}: 전리품 정의가 없습니다.")
        if data.get("boss_quest") and data["boss_quest"] not in QUESTS:
            issues.append(f"{enemy}: 임무 정의가 없습니다.")
    for key in SHOP.keys() | EXCHANGE.keys():
        if key not in ITEMS:
            issues.append(f"{key}: 상점 아이템 정의가 없습니다.")
    for identity, data in interactables.items():
        if data["room"] not in ROOMS:
            issues.append(f"{identity}: 대상 Room이 없습니다.")
    for quest_id, data in QUESTS.items():
        flags = [step[0] for step in data["steps"]]
        if len(flags) != len(set(flags)) or not flags or flags[-1] != "claimed":
            issues.append(f"{quest_id}: 임무 단계가 잘못되었습니다.")
        if len(data["hints"]) != len(flags) + 1:
            issues.append(f"{quest_id}: 안내 단계 수가 맞지 않습니다.")
        for _, target, role, _ in data["steps"]:
            if target not in (ENEMIES if role == "hostile" else interactables):
                issues.append(f"{quest_id}: 단계 대상 {target} 정의가 없습니다.")
    return issues
