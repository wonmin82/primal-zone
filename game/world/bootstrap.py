"""Idempotent zone creation; never clears characters or player progress."""

from evennia import create_object, search_tag
from evennia.typeclasses.tags import Tag

from world.content import DIRECTION_ALIASES, ENEMIES, ROOMS, spawn_id_for
from world.content.elevator import ELEVATOR_ROOM
from world.elevator import normalized_stop
from world.multiplayer import world_change

CATEGORY = "primal_zone_room"
EXIT_CATEGORY = "primal_zone_exit"


def get_room(zone_id):
    return next(iter(search_tag(zone_id, category=CATEGORY)), None)


def build_world():
    from world.item_runtime import initialize_fresh, maintenance

    if not maintenance.get():
        initialize_fresh()
    with world_change():
        return _build_world()


def _build_world():
    rooms = {}
    for zone_id, data in ROOMS.items():
        room = get_room(zone_id)
        if not room:
            room = create_object("typeclasses.zone_rooms.ZoneRoom", key=data["name"])
            room.tags.add(zone_id, category=CATEGORY)
        room.key = data["name"]
        room.db.zone_id = zone_id
        room.db.desc = data["desc"]
        if zone_id == ELEVATOR_ROOM:
            current = room.db.current_stop
            if current != normalized_stop(current):
                room.db.current_stop = normalized_stop(current)
        rooms[zone_id] = room
        for enemy_id in data["enemies"]:
            spawn_id = spawn_id_for(zone_id, enemy_id)
            definition = ENEMIES[enemy_id]
            enemy = next(iter(search_tag(spawn_id, category="primal_spawn")), None)
            if not enemy:
                enemy = create_object(
                    "typeclasses.enemies.Enemy", key=definition["name"], location=room
                )
                enemy.tags.add(spawn_id, category="primal_spawn")
                enemy.db.spawn_id = spawn_id
                enemy.db.enemy_id = enemy_id
                enemy.db.max_hp = definition["hp"]
                enemy.db.hp = definition["hp"]
            else:
                # 정의가 소유하는 값만 갱신하고 현재 피해·교전·재생성 상태는 보존한다.
                enemy.key = definition["name"]
                enemy.db.enemy_id = enemy_id
                from world.loot_rules import boss_hp, updated_enemy_hp

                maximum = boss_hp(definition["hp"], enemy.db.scaling_participants or 1) if definition.get("boss") else definition["hp"]
                enemy.db.hp = updated_enemy_hp(enemy.db.hp, enemy.db.max_hp, maximum,
                                               enemy.db.state, bool(enemy.db.combatants))
                enemy.db.max_hp = maximum
                if not enemy.db.combatants and enemy.location != room:
                    enemy.location = room
            enemy.attributes.remove("suppression")
            if enemy.db.suppressions is None or not enemy.db.combatants:
                enemy.db.suppressions = {}
    # 이전 본부 배치의 두 관리 출구를 새 방향으로 재사용한다. 다른 stale 객체는 보존한다.
    for zone, old_direction, new_direction, target in (
        ("hq_concourse", "동", "남", "support_1f_c"),
        ("support_1f_c", "남", "북", "hq_concourse"),
    ):
        old_identity, new_identity = f"{zone}:{old_direction}", f"{zone}:{new_direction}"
        for existing in search_tag(old_identity, category=EXIT_CATEGORY):
            if existing.location == rooms[zone] and existing.destination == rooms[target]:
                if search_tag(new_identity, category=EXIT_CATEGORY):
                    existing.delete()
                else:
                    existing.tags.remove(old_identity, category=EXIT_CATEGORY)
                    existing.tags.add(new_identity, category=EXIT_CATEGORY)
        if not search_tag(old_identity, category=EXIT_CATEGORY):
            Tag.objects.filter(db_key=old_identity, db_category=EXIT_CATEGORY).delete()
    for zone_id, data in ROOMS.items():
        room = rooms[zone_id]
        # 명시적으로 폐쇄된 방향의 기존 관리 출구만 제거한다. 일반 stale 객체는 보존한다.
        for direction in data.get("blocked_exits", {}):
            for existing in search_tag(f"{zone_id}:{direction}", category=EXIT_CATEGORY):
                existing.delete()
        for direction, target in data["exits"].items():
            identity = f"{zone_id}:{direction}"
            existing = next(iter(search_tag(identity, category=EXIT_CATEGORY)), None)
            if not existing:
                existing = next((obj for obj in room.exits if obj.key == direction), None)
            if not existing:
                existing = create_object(
                    "typeclasses.exits.Exit",
                    key=direction,
                    aliases=[DIRECTION_ALIASES[direction]] if direction in DIRECTION_ALIASES else [],
                    location=room,
                    destination=rooms[target],
                )
            existing.tags.add(identity, category=EXIT_CATEGORY)
            existing.key = direction
            existing.location = room
            existing.destination = rooms[target]
            existing.aliases.clear()
            if direction in DIRECTION_ALIASES:
                existing.aliases.add(DIRECTION_ALIASES[direction])
    from typeclasses.interactables import INTERACTABLES

    for identity, data in INTERACTABLES.items():
        obj = next(iter(search_tag(identity, category="primal_interactable")), None)
        if not obj:
            obj = create_object(
                f"typeclasses.interactables.{data['typeclass']}",
                key=data["name"],
                aliases=data["aliases"],
                location=rooms[data["room"]],
            )
            obj.tags.add(identity, category="primal_interactable")
        else:
            obj.key = data["name"]
            obj.location = rooms[data["room"]]
            obj.aliases.clear()
            obj.aliases.add(data["aliases"])
        expected_type = f"typeclasses.interactables.{data['typeclass']}"
        if obj.typeclass_path != expected_type:
            obj.swap_typeclass(expected_type, clean_attributes=False, run_start_hooks="at_object_creation")
        for field in ("shop_id", "skill_id", "attribute_id", "presence", "description", "dialogue"):
            if field in data:
                obj.attributes.add(field, data[field])
    return rooms


def stale_definitions():
    """정의에서 사라진 관리 객체를 보고만 한다. 플레이 중인 객체는 지우지 않는다."""
    from typeclasses.interactables import INTERACTABLES

    expected = {
        CATEGORY: set(ROOMS),
        EXIT_CATEGORY: {f"{zone}:{direction}" for zone, data in ROOMS.items() for direction in data["exits"]},
        "primal_spawn": {spawn_id_for(zone, enemy) for zone, data in ROOMS.items() for enemy in data["enemies"]},
        "primal_interactable": set(INTERACTABLES),
    }
    result = []
    for category, identities in expected.items():
        for tag in Tag.objects.filter(db_category=category):
            if tag.db_key not in identities:
                result.append((category, tag.db_key))
    return sorted(result)
