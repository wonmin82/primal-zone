"""Idempotent zone creation; never clears characters or player progress."""

from evennia import create_object, search_tag

from world.content import OPPOSITES, ROOMS

CATEGORY = "primal_zone_room"


def get_room(zone_id):
    return next(iter(search_tag(zone_id, category=CATEGORY)), None)


def build_world():
    rooms = {}
    for zone_id, data in ROOMS.items():
        room = get_room(zone_id)
        if not room:
            room = create_object("typeclasses.zone_rooms.ZoneRoom", key=data["name"])
            room.tags.add(zone_id, category=CATEGORY)
        room.db.zone_id = zone_id
        room.db.desc = data["desc"]
        rooms[zone_id] = room
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
