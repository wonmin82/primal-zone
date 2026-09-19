"""Idempotent zone creation; never clears characters or player progress."""

from evennia import create_object, search_tag

from world.content import ENEMIES, OPPOSITES, ROOMS
from world.multiplayer import world_change

CATEGORY = "primal_zone_room"


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
        room.db.zone_id = zone_id
        room.db.desc = data["desc"]
        rooms[zone_id] = room
        for enemy_id in data["enemies"]:
            spawn_id = f"{zone_id}:{enemy_id}"
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
    for zone_id, data in ROOMS.items():
        room = rooms[zone_id]
        for direction, target in data["exits"].items():
            existing = next((obj for obj in room.exits if obj.key == direction), None)
            if not existing:
                create_object(
                    "typeclasses.exits.Exit",
                    key=direction,
                    aliases=[OPPOSITES[direction]],
                    location=room,
                    destination=rooms[target],
                )
    return rooms
