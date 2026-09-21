from evennia.objects.objects import DefaultRoom
from world.content import ROOMS

from typeclasses.enemies import room_enemies
from typeclasses.loot import room_loot


def exit_diagram(exits):
    """한글 2칸, 선/공백 1칸인 고정폭 텍스트로 실제 출구만 표시한다."""
    directions = set(exits)
    left = "서 ─ " if "서" in directions else ""
    offset = " " * (5 if left else 0)
    lines = []
    if "북" in directions:
        lines.extend([offset + "  북", offset + "   │"])
    lines.append(left + "[현재]" + (" ─ 동" if "동" in directions else ""))
    if "남" in directions:
        lines.extend([offset + "   │", offset + "  남"])
    other = [direction for direction in exits if direction not in {"북", "남", "동", "서"}]
    if other:
        lines.append("기타 출구: " + " · ".join(other))
    return "\n".join(lines)


class ZoneRoom(DefaultRoom):
    def return_appearance(self, looker, **kwargs):
        from world.lifecycle import reconcile_room

        reconcile_room(self)
        room = ROOMS.get(self.db.zone_id)
        if not room:
            return super().return_appearance(looker, **kwargs)
        lines = [f"|g[{room['name']}]|n", room["desc"], ""]
        from typeclasses.interactables import action_objects

        targets = action_objects(self)
        if targets:
            lines.append("주변 대상: " + " · ".join(obj.key for obj in targets))
        enemies = room_enemies(self)
        if enemies:
            lines.append("사냥 대상: " + " · ".join(enemy.key for enemy in enemies))
        for corpse in room_loot(self):
            lines.append(corpse.key)
        for dropped in room_loot(self, corpse=False):
            lines.append(dropped.key)
        others = [obj.key for obj in self.contents if obj != looker and obj.has_account]
        if others:
            lines.append("함께 있는 탐사자: " + ", ".join(others))
        lines.extend([exit_diagram(room["exits"]), f"|c{room['hint']}|n"])
        return "\n".join(lines)
