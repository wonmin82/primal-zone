"""Idempotent zone creation; never clears characters or player progress."""

from evennia import create_object, search_tag

from world.content import ENEMIES, OPPOSITES, ROOMS, spawn_id_for
from world.multiplayer import world_change

CATEGORY = "primal_zone_room"
EXIT_CATEGORY = "primal_zone_exit"


def get_room(zone_id):
    return next(iter(search_tag(zone_id, category=CATEGORY)), None)


def build_world():
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
        rooms[zone_id] = room
        for enemy_id in data["enemies"]:
            spawn_id = spawn_id_for(zone_id, enemy_id)
            enemy = next(iter(search_tag(spawn_id, category="primal_spawn")), None)
            if not enemy:
                definition = ENEMIES[enemy_id]
                enemy = create_object(
                    "typeclasses.enemies.Enemy", key=definition["name"], location=room
                )
                enemy.tags.add(spawn_id, category="primal_spawn")
                enemy.db.spawn_id = spawn_id
                enemy.db.enemy_id = enemy_id
                enemy.db.max_hp = definition["hp"]
                enemy.db.hp = definition["hp"]
            elif not enemy.db.combatants:
                # Spawn의 정적 위치만 동기화한다. 현재 HP/respawn/claim은 그대로 둔다.
                enemy.key = ENEMIES[enemy_id]["name"]
                if enemy.location != room:
                    enemy.location = room
    for zone_id, data in ROOMS.items():
        room = rooms[zone_id]
        for direction, target in data["exits"].items():
            identity = f"{zone_id}:{direction}"
            existing = next(iter(search_tag(identity, category=EXIT_CATEGORY)), None)
            if not existing:
                existing = next((obj for obj in room.exits if obj.key == direction), None)
            if not existing:
                existing = create_object(
                    "typeclasses.exits.Exit",
                    key=direction,
                    aliases=[OPPOSITES[direction]] if direction in OPPOSITES else [],
                    location=room,
                    destination=rooms[target],
                )
            existing.tags.add(identity, category=EXIT_CATEGORY)
            existing.key = direction
            existing.location = room
            existing.destination = rooms[target]
            existing.aliases.clear()
            if direction in OPPOSITES:
                existing.aliases.add(OPPOSITES[direction])
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
            obj.aliases.add(*data["aliases"])
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
        from evennia.typeclasses.tags import Tag

        for tag in Tag.objects.filter(db_category=category):
            if tag.db_key not in identities:
                result.append((category, tag.db_key))
    return sorted(result)
