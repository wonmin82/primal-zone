from evennia.objects.objects import DefaultRoom
from world.content import ROOMS

from typeclasses.enemies import room_enemies
from typeclasses.loot import room_loot


class ZoneRoom(DefaultRoom):
    def return_appearance(self, looker, **kwargs):
        from world.lifecycle import reconcile_room

        reconcile_room(self)
        room = ROOMS.get(self.db.zone_id)
        if not room:
            return super().return_appearance(looker, **kwargs)
        lines = [f"|g[{room['name']}]|n", room["desc"], ""]
        enemies = room_enemies(self)
        if enemies:
            lines.append("사냥 대상: " + " · ".join(enemy.key for enemy in enemies))
        for corpse in room_loot(self):
            lines.append(corpse.key + " · 시체에서 모두 가져")
        for dropped in room_loot(self, corpse=False):
            lines.append(dropped.key + " · " + dropped.key + " 가져")
        others = [obj.key for obj in self.contents if obj != looker and obj.has_account]
        if others:
            lines.append("함께 있는 탐사자: " + ", ".join(others))
        lines.extend(["출구: " + " · ".join(room["exits"]), f"|c{room['hint']}|n"])
        return "\n".join(lines)
