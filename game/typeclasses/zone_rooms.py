from evennia.objects.objects import DefaultRoom
from world import text as ft
from world.content import ROOMS

from typeclasses.enemies import room_enemies
from typeclasses.loot import room_loot


def exit_diagram(exits):
    """한글 2칸, 선/공백 1칸인 고정폭 텍스트로 실제 출구만 표시한다."""
    directions = set(exits)
    left = ft.text(ft.token("direction", "서"), " ─ ") if "서" in directions else ""
    offset = " " * (5 if left else 0)
    lines = []
    if "북" in directions:
        lines.extend([ft.text(offset, "  ", ft.token("direction", "북")), offset + "   │"])
    lines.append(
        ft.text(
            left,
            "[현재]",
            ft.text(" ─ ", ft.token("direction", "동")) if "동" in directions else "",
        )
    )
    if "남" in directions:
        lines.extend([offset + "   │", ft.text(offset, "  ", ft.token("direction", "남"))])
    other = [direction for direction in exits if direction not in {"북", "남", "동", "서"}]
    if other:
        lines.append(
            ft.text("기타 출구: ", ft.join([ft.token("direction", d) for d in other], " · "))
        )
    return ft.join(lines)


class ZoneRoom(DefaultRoom):
    def return_appearance(self, looker, **kwargs):
        from world.lifecycle import reconcile_room

        reconcile_room(self)
        room = ROOMS.get(self.db.zone_id)
        if not room:
            return super().return_appearance(looker, **kwargs)
        from typeclasses.interactables import action_objects

        lines = [room["desc"], "", exit_diagram(room["exits"]), ""]
        for obj in action_objects(self):
            lines.append(ft.text(ft.named(obj.semantic_role, obj.key, "은/는"), " ", obj.presence))
        for enemy in room_enemies(self):
            lines.append(
                ft.text(ft.named("hostile", enemy.key, "이/가"), " 주변을 경계하며 서성이고 있다.")
            )
        for corpse in room_loot(self):
            lines.append(ft.text(ft.named("remains", corpse.key, "이/가"), " 바닥에 남아 있다."))
        for dropped in room_loot(self, corpse=False):
            for entry in dropped.db.entries:
                lines.append(
                    ft.text(ft.item(entry["item"]), f" {entry['quantity']}개가 바닥에 떨어져 있다.")
                )
        others = [obj for obj in self.contents if obj != looker and obj.has_account]
        for obj in others:
            lines.append(
                ft.text(ft.named("player", obj.key, "은/는"), " 이곳에서 주변을 살피고 있다.")
            )
        return ft.sheet(ft.token("title", room["name"]), *lines)
