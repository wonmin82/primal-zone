"""정적 월드 정의의 참조와 stable ID를 검사한다. DB를 읽지 않는다."""

from math import isfinite
from numbers import Real

from world.content import (
    ENEMIES,
    ITEMS,
    REGION_ENEMIES,
    REGIONS,
    ROOMS,
    SHOP_CATALOGS,
    spawn_id_for,
)
from world.content.directions import OPPOSITE_DIRECTIONS
from world.content.economy import SALVAGE_CREDIT_RATE
from world.content.environment import EXPOSURES, LIGHT_PROFILES, WEATHER_ZONES, WEATHERS
from world.content.facilities import FACILITIES
from world.content.headquarters import ELEVATOR_ROOM, HQ_LANDINGS, ROOF_ROOMS, ROOF_SIDES
from world.item_entities.policy import definition_errors
from world.quests import QUESTS


def positive_number(value):
    return isinstance(value, Real) and not isinstance(value, bool) and isfinite(value) and value > 0


def alias_errors(items):
    from world.targets import normalized

    seen, issues = {}, []
    for identity, definition in items.items():
        for name in (identity, definition["name"], *definition.get("aliases", ())):
            key = normalized(name)
            if key in seen and seen[key] != identity:
                issues.append(f"{identity}: 정규화 이름/alias가 {seen[key]}와 충돌합니다: {name}")
            seen[key] = identity
    return issues


def recovery_errors(identity, definition, field):
    data = definition.get(field, {})
    if not isinstance(data, dict) or any(
        key not in ("hp_per_minute", "mental_per_minute") or isinstance(value, bool)
        or not isinstance(value, Real) or not isfinite(value) or value < 0
        for key, value in data.items()
    ):
        return [f"{identity}: {field} 회복량은 유한한 0 이상의 수여야 합니다."]
    return []


def headquarters_errors():
    """본부 평면 동선·시설·수직 이동을 검사한다."""
    expected = {
        "staging_room": {"남": "hq_concourse"},
        "hq_concourse": {"북": "staging_room", "서": "dock", "동": "hq_admin_office", "남": "hq_lounge"},
        "hq_admin_office": {"서": "hq_concourse"}, "hq_lounge": {"북": "hq_concourse"},
        "dock": {"북": "grass", "동": "hq_concourse"},
        "support_roof": dict(ROOF_SIDES),
    }
    for direction, zone in ROOF_SIDES.items():
        expected[zone] = {OPPOSITE_DIRECTIONS[direction]: "support_roof"}
    corridors = []
    for floor in (2, 3, 4, 5):
        positions = ("w2", "w1", "c", "e1", "e2") if floor == 5 else ("w1", "c", "e1")
        row = [f"support_{floor}f_{position}" for position in positions]
        corridors.extend(row)
        for index, zone in enumerate(row):
            expected[zone] = {}
            if index:
                expected[zone]["서"] = row[index - 1]
            if index + 1 < len(row):
                expected[zone]["동"] = row[index + 1]
    facilities = (
        ("storage_room", "support_2f_w1", "북"), ("supply_shop", "support_2f_c", "북"),
        ("salvage_office", "support_2f_e1", "북"),
        ("medical_waiting", "support_3f_w1", "북"), ("infirmary", "support_3f_c", "북"),
        ("recovery_room", "support_3f_e1", "북"),
        ("training_room", "support_4f_w1", "북"), ("survival_training_room", "support_4f_w1", "남"),
        ("training_office", "support_4f_c", "북"), ("tactics_room", "support_4f_c", "남"),
        ("shooting_range", "support_4f_e1", "북"), ("medical_training_room", "support_4f_e1", "남"),
        ("armor_shop", "support_5f_w1", "북"), ("weapon_shop", "support_5f_e1", "북"),
        ("outpost_equipment", "support_5f_w2", "북"), ("outpost_weapon", "support_5f_e2", "북"),
        ("reserved_equipment", "support_5f_w2", "남"), ("reserved_weapon", "support_5f_e2", "남"),
    )
    for facility, corridor, direction in facilities:
        expected[facility] = {OPPOSITE_DIRECTIONS[direction]: corridor}
        expected[corridor][direction] = facility
    for index, (_, landing, stairs) in enumerate(HQ_LANDINGS):
        expected[landing].update({"계단": stairs, "승강기": ELEVATOR_ROOM})
        expected[stairs] = {"나가기": landing}
        if index + 1 < len(HQ_LANDINGS):
            expected[stairs]["위"] = HQ_LANDINGS[index + 1][2]
        if index:
            expected[stairs]["아래"] = HQ_LANDINGS[index - 1][2]
    issues = []
    for zone in ROOF_ROOMS:
        room = ROOMS.get(zone, {})
        if zone not in REGIONS["headquarters"]["rooms"] or room.get("safe") is not True or room.get("enemies") != []:
            issues.append(f"{zone}: 옥상은 headquarters의 안전한 비전투 Room이어야 합니다.")
        if room.get("exposure") != "outdoor" or room.get("light_profile") != "natural":
            issues.append(f"{zone}: 옥상 환경은 outdoor/natural이어야 합니다.")
        for field in ("hints", "requires", "quest", "items", "rewards"):
            if room.get(field):
                issues.append(f"{zone}: 옥상 검증 Room에는 {field}를 둘 수 없습니다.")
    for zone, exits in expected.items():
        if ROOMS.get(zone, {}).get("exits") != exits:
            issues.append(f"{zone}: 본부 5층 출구 배치가 올바르지 않습니다.")
    for zone in corridors:
        blocked = ROOMS.get(zone, {}).get("blocked_exits", {})
        if not isinstance(blocked, dict) or set(blocked) != {"북", "남"} - set(expected[zone]):
            issues.append(f"{zone}: 본부 폐쇄 출입구 배치가 올바르지 않습니다.")
    for facility, corridor, direction in facilities:
        incoming = [(zone, direction) for zone, room in ROOMS.items()
                    for direction, target in room["exits"].items() if target == facility]
        if incoming != [(corridor, direction)]:
            issues.append(f"{facility}: 시설 Room은 지정 복도에서만 연결되어야 합니다.")
    return issues


def elevator_errors():
    issues, region = [], REGIONS.get("headquarters", {}).get("rooms", ())
    if ROOMS.get(ELEVATOR_ROOM, {}).get("exits") != {label: landing for label, landing, _ in HQ_LANDINGS}:
        issues.append("승강기 Room은 여섯 층별 실제 출구만 가져야 합니다.")
    if ELEVATOR_ROOM not in region:
        issues.append("승강기 Room은 headquarters Region에 속해야 합니다.")
    for _, landing, stairs in HQ_LANDINGS:
        if ROOMS.get(landing, {}).get("exits", {}).get("승강기") != ELEVATOR_ROOM:
            issues.append(f"{landing}: 승강기 진입 출구가 올바르지 않습니다.")
        room = ROOMS.get(stairs, {})
        if (stairs not in region or not room.get("safe") or room.get("enemies") != []
                or room.get("exposure") != "indoor" or room.get("light_profile") != "artificial"
                or room.get("recovery") or room.get("hints")):
            issues.append(f"{stairs}: 안전한 실내 계단 Room이며 추가 서비스/회복이 없어야 합니다.")
    incoming = {(zone, direction) for zone, room in ROOMS.items() for direction, target in room["exits"].items()
                if target == ELEVATOR_ROOM}
    if incoming != {(landing, "승강기") for _, landing, _ in HQ_LANDINGS}:
        issues.append("승강기 진입은 여섯 중앙 공간의 실제 승강기 출구만 허용합니다.")
    return issues


def shop_errors():
    issues = []
    if set(SHOP_CATALOGS) != {"supply", "weapon", "armor", "outpost_weapon", "outpost_equipment"}:
        issues.append("상점 catalog ID가 올바르지 않습니다.")
    items = []
    for shop_id, definition in SHOP_CATALOGS.items():
        if not isinstance(definition, dict) or set(definition) != {"purchase_catalog", "accepts"}:
            issues.append(f"{shop_id}: purchase_catalog와 accepts가 필요합니다.")
            continue
        catalog = definition["purchase_catalog"]
        if not definition["accepts"] or any(category not in {"weapon", "hand_equipment", "armor", "equipment", "tool", "consumable", "magazine", "ammo"}
                                            for category in definition["accepts"]):
            issues.append(f"{shop_id}: 매입 category가 올바르지 않습니다.")
        if not catalog:
            issues.append(f"{shop_id}: 상점 판매 목록이 비었습니다.")
        if not isinstance(catalog, (tuple, list)):
            issues.append(f"{shop_id}: catalog는 가격 없이 item ID 목록만 가져야 합니다.")
        for item in catalog:
            items.append(item)
            if item not in ITEMS:
                issues.append(f"{item}: 상점 아이템 정의가 없습니다.")
            price = ITEMS.get(item, {}).get("value")
            if type(price) is not int or price <= 0:
                issues.append(f"{shop_id}/{item}: 가격은 양의 정수여야 합니다.")
        if len(catalog) != len(set(catalog)):
            issues.append(f"{shop_id}: 같은 catalog에서 아이템이 중복되었습니다.")
    return issues


def errors(interactables):
    issues = headquarters_errors() + elevator_errors() + shop_errors()
    from world.final_content import errors as final_errors

    issues.extend(final_errors())
    from world.progression import ATTRIBUTES, SKILLS

    for identity, definition in interactables.items():
        kind = definition.get("typeclass")
        if kind not in ("SkillTrainer", "AttributeTrainer", "TrainingManager"):
            continue
        for field in ("presence", "description", "dialogue"):
            if not isinstance(definition.get(field), str) or not definition[field].strip():
                issues.append(f"{identity}: 성장 교관의 {field}는 비어 있지 않은 문자열이어야 합니다.")
        if kind == "SkillTrainer" and definition.get("skill_id") not in SKILLS:
            issues.append(f"{identity}: 담당 기술이 유효하지 않습니다.")
        if kind == "AttributeTrainer" and definition.get("attribute_id") not in ATTRIBUTES:
            issues.append(f"{identity}: 담당 특성이 유효하지 않습니다.")
    if type(SALVAGE_CREDIT_RATE) is not int or SALVAGE_CREDIT_RATE <= 0:
        issues.append("회수부품 정산율은 양의 정수여야 합니다.")
    for identity, room in (
        ("shared_container", "storage_room"), ("personal_locker", "storage_room"),
        ("instructor", "training_office"),
        ("doctor", "infirmary"), ("infirmary_bed", "infirmary"),
        ("salvage_officer", "salvage_office"),
        ("supply_shopkeeper", "supply_shop"), ("weapon_shopkeeper", "weapon_shop"),
        ("armor_shopkeeper", "armor_shop"),
    ):
        if interactables.get(identity, {}).get("room") != room:
            issues.append(f"{identity}: 본부 서비스는 {room}에 배치해야 합니다.")
    for identity, definition in FACILITIES.items():
        if not isinstance(identity, str) or not identity.strip() or not isinstance(definition, dict):
            issues.append(f"{identity}: 시설 점수 정의가 유효하지 않습니다.")
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
        issues.extend(recovery_errors(zone, room, "recovery"))
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
            if direction not in OPPOSITE_DIRECTIONS:
                issues.append(f"{zone}: 폐쇄 출입구 방향이 유효하지 않습니다.")
            if direction in room["exits"]:
                issues.append(f"{zone}:{direction}: 실제 출구와 폐쇄 출입구가 겹칩니다.")
            if not isinstance(message, str) or not message.strip():
                issues.append(f"{zone}:{direction}: 폐쇄 출입구 문구는 비어 있지 않은 문자열이어야 합니다.")
        for direction, target in room["exits"].items():
            if target not in ROOMS:
                issues.append(f"{zone}:{direction}: 대상 Room이 없습니다.")
            elif direction in OPPOSITE_DIRECTIONS and ROOMS[target]["exits"].get(OPPOSITE_DIRECTIONS[direction]) != zone:
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
        if type(data.get("currency")) is not int or data["currency"] <= 0:
            issues.append(f"{enemy}: 시체 보급칩은 양의 정수여야 합니다.")
        if not data.get("presence") or not data.get("distant_presence"):
            issues.append(f"{enemy}: 현재/원거리 존재 묘사가 없습니다.")
        from world.content.loot_v1 import LOOT

        loot = LOOT.get(enemy, {})
        for group in ("resource", "special"):
            options = loot.get(group, ()) if group == "special" else loot.get(group, (0, ()))[1]
            if any(identity not in ITEMS or not 0 < weight <= 1 for identity, weight in options) or sum(weight for _, weight in options) > 1.000001:
                issues.append(f"{enemy}: 드롭 definition/확률이 올바르지 않습니다.")
        if loot.get("trophy") and loot["trophy"] not in ITEMS:
            issues.append(f"{enemy}: trophy 정의가 없습니다.")
        if data.get("boss_quest") and data["boss_quest"] not in QUESTS:
            issues.append(f"{enemy}: 임무 정의가 없습니다.")
    for key, data in ITEMS.items():
        issues.extend(definition_errors(key, data))
        issues.extend(recovery_errors(key, data, "recovery_bonus"))
        source = data.get("power_source")
        if source and (not isinstance(source.get("type"), str) or not source["type"].strip() or not positive_number(source.get("capacity_seconds"))):
            issues.append(f"{key}: 전원 정의가 유효하지 않습니다.")
        light = data.get("light_source")
        if light and (not positive_number(light.get("strength")) or type(light.get("range")) is not int or light["range"] < 0 or not isinstance(light.get("power_type"), str) or not light["power_type"].strip()):
            issues.append(f"{key}: 광원 정의가 유효하지 않습니다.")
    issues.extend(alias_errors(ITEMS))
    for zone, room in ROOMS.items():
        access = room.get("access")
        if access is not None and (not isinstance(access, dict) or type(access.get("available")) is not bool
                or ITEMS.get(access.get("credential"), {}).get("item_type") != "credential"):
            issues.append(f"{zone}: 접근 가용성/출입증 정의가 올바르지 않습니다.")
    for identity, data in interactables.items():
        if data.get("room") in ROOF_ROOMS:
            issues.append(f"{identity}: 옥상 검증 Room {data['room']}에는 interactable/NPC를 배치할 수 없습니다.")
        if data["room"] not in ROOMS:
            issues.append(f"{identity}: 대상 Room이 없습니다.")
        if data.get("typeclass") == "Shopkeeper" and data.get("shop_id") not in SHOP_CATALOGS:
            issues.append(f"{identity}: 상점 catalog가 없습니다.")
    for identity, shop_id in (("supply_shopkeeper", "supply"), ("weapon_shopkeeper", "weapon"), ("armor_shopkeeper", "armor"), ("outpost_weapon_shopkeeper", "outpost_weapon"), ("outpost_equipment_shopkeeper", "outpost_equipment")):
        data = interactables.get(identity, {})
        if data.get("shop_id") != shop_id or tuple(data.get("actions", ())) != ("대화", "목록", "사", "가치", "팔아"):
            issues.append(f"{identity}: 상점 catalog/행동 정의가 올바르지 않습니다.")
    for identity, action in (("doctor", "진료"), ("infirmary_bed", "휴식")):
        if tuple(interactables.get(identity, {}).get("actions", ())) != (action,):
            issues.append(f"{identity}: 의료 행동 정의가 올바르지 않습니다.")
    if tuple(interactables.get("salvage_officer", {}).get("actions", ())) != ("환율", "교환"):
        issues.append("salvage_officer: 정산 행동 정의가 올바르지 않습니다.")
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
