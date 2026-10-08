from time import time

from evennia.objects.objects import DefaultRoom
from world import text as ft
from world.content import ROOMS
from world.exit_presentation import exit_diagram, exit_entries

from typeclasses.enemies import room_enemies
from typeclasses.loot import room_loot


class ZoneRoom(DefaultRoom):
    def return_distant_appearance(self, context):
        from world.distant_presentation import distant_appearance

        if context.target_room != self:
            raise ValueError("관찰 context의 목적지와 Room이 다릅니다.")
        return distant_appearance(context)

    def return_appearance(self, looker, **kwargs):
        from world.environment import description
        from world.environment_state import snapshot_for
        from world.lifecycle import reconcile_room

        observed_at = kwargs.get("observed_at")
        observed_at = time() if observed_at is None else observed_at
        reconcile_room(self, observed_at)
        room = ROOMS.get(self.db.zone_id)
        if not room:
            return super().return_appearance(looker, **kwargs)
        from world.target_presentation import presence
        from world.targets import room_objects

        from typeclasses.interactables import action_objects

        environment = snapshot_for(self, observed_at)
        lines = [
            room["desc"], *room.get("blocked_exits", {}).values(),
            "", ft.token("muted", description(environment)), "",
            exit_diagram(exit_entries(looker, self, observed_at)), "",
        ]
        pool = room_objects(looker, self, observed_at)
        objects = [obj for obj in action_objects(self) if obj in pool]
        for name in dict.fromkeys(obj.key for obj in objects):
            group = [obj for obj in objects if obj.key == name]
            lines.extend(
                presence(
                    group,
                    group[0].semantic_role,
                    "명" if group[0].semantic_role == "npc" else "개",
                    group[0].presence,
                    pool=pool,
                )
            )
        enemies = [obj for obj in room_enemies(self) if obj in pool]
        for sentence in dict.fromkeys(obj.get_local_presence() for obj in enemies):
            lines.extend(
                presence(
                    [obj for obj in enemies if obj.get_local_presence() == sentence],
                    "hostile", "마리", sentence, pool=pool,
                )
            )
        lines.extend(
            presence(
                [obj for obj in room_loot(self) if obj in pool],
                "remains",
                "구",
                "바닥에 남아 있다.",
                source=True,
            )
        )
        for dropped in (obj for obj in room_loot(self, corpse=False) if obj in pool):
            from world.loot_service import source_entries

            for entry in source_entries(dropped):
                from world.loot_assets import asset_text, normalize_entry

                entry = normalize_entry(entry)
                lines.append(
                    ft.text(asset_text(entry), "이 바닥에 떨어져 있다.") if entry["kind"] == "currency"
                    else ft.text(ft.item(entry["id"]), f" {entry['quantity']}개가 바닥에 떨어져 있다.")
                )
        others = [obj for obj in pool if obj != looker and obj.has_account]
        for obj in others:
            lines.append(
                ft.text(ft.named("player", obj.key, "은/는"), " 이곳에서 주변을 살피고 있다.")
            )
        from world.observation import context_for

        sight = context_for(looker, self, observed_at, environment=environment).snapshot
        if sight.effective_visibility != "clear":
            lines.extend(["", "주변의 작은 흔적을 식별하기 어렵다. 광원을 사용하면 더 자세히 살펴볼 수 있다."])
        return ft.sheet(ft.token("title", room["name"]), *lines)
