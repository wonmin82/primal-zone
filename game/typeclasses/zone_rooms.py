from evennia.objects.objects import DefaultRoom
from world.content import ROOMS

from typeclasses.enemies import room_enemies


class ZoneRoom(DefaultRoom):
    def return_appearance(self, looker, **kwargs):
        room = ROOMS.get(self.db.zone_id)
        if not room:
            return super().return_appearance(looker, **kwargs)
        lines = [f"|g[{room['name']}]|n", room["desc"], ""]
        enemies = room_enemies(self)
        if enemies:
            lines.append("사냥 대상: " + " · ".join(enemy.key for enemy in enemies))
        others = [obj.key for obj in self.contents if obj != looker and obj.has_account]
        if others:
            lines.append("함께 있는 탐사자: " + ", ".join(others))
        lines.extend(["출구: " + " · ".join(room["exits"]), f"|c{room['hint']}|n"])
        return "\n".join(lines)
