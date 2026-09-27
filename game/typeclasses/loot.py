"""공유 시체와 바닥 아이템. 배정과 보호 기한은 이동해도 유지된다."""

from random import Random
from time import time

from evennia import create_object
from evennia.objects.objects import DefaultObject
from evennia.utils import delay
from evennia.utils.dbserialize import deserialize
from world import rules
from world import text as ft
from world.content import ENEMIES, ITEMS, find_id
from world.multiplayer import (
    CORPSE_TTL_SECONDS,
    LOOT_PROTECTION_SECONDS,
    after_change,
    object_by_id,
    world_change,
)
from world.targets import LootRequest, Mode, TargetSelector, ordered, select, visible


def build_entries(enemy, groups, now, rng=None):
    definition = ENEMIES[enemy.db.enemy_id]
    items = ["scrap"]
    if (rng or Random()).random() < definition["chance"]:
        items.append(definition["drop"])
    weights = {key: sum(members.values()) for key, members in groups.items()}
    total = sum(weights.values())
    entries = []
    for index, item in enumerate(items):
        # 등간격 중점을 누적 기여 비중에 배정한다. 정수 비교로 반올림 오차를 피한다.
        point = (2 * index + 1) * total
        cumulative = 0
        chosen = None
        for group in sorted(weights):
            cumulative += weights[group]
            if point < 2 * len(items) * cumulative:
                chosen = group
                break
        if not chosen:
            continue
        kind, identity = chosen.split(":")
        identity = int(identity)
        party = object_by_id(identity) if kind == "party" else None
        members = sorted(groups[chosen])
        if party:
            state = party.state()
            members = [key for key in state["members"] if key in groups[chosen]]
            assigned = members[state["round_robin_cursor"] % len(members)]
            state["round_robin_cursor"] += 1
            party.db.state = state
        else:
            assigned = members[0]
        entries.append(
            {
                "item": item,
                "quantity": 1,
                "reserved_party": party.id if party else None,
                "reserved_player": identity if kind == "player" else None,
                "assigned_player": assigned,
                "protection_until": now + LOOT_PROTECTION_SECONDS,
            }
        )
    return entries


def recipient_for(entry, caller, now):
    from typeclasses.parties import party_for

    if now >= entry["protection_until"]:
        return caller
    party = party_for(caller)
    allowed = caller.id in (entry["reserved_player"], entry["assigned_player"]) or (
        party and party.id == entry["reserved_party"]
    )
    return object_by_id(entry["assigned_player"]) if allowed else None


def room_loot(room, corpse=True):
    cls = Corpse if corpse else DroppedLoot
    return (
        ordered(
            (obj for obj in room.contents if obj.is_typeclass(cls, exact=True)),
        )
        if room
        else []
    )


def take_loot(caller, item=None, corpse=True, now=None, *, request=None):
    """선택 범위/수량만 확장한다. 지급 권한은 recipient_for 한 곳에서 판단한다."""
    from world.lifecycle import reconcile_room
    from world.target_presentation import count_word

    now = time() if now is None else now
    if request is None:
        request = LootRequest(
            TargetSelector(item or "전리품", Mode.DEFAULT if item else Mode.ALL),
            TargetSelector("시체") if corpse else None,
        )
    corpse = request.source is not None
    if request.source and request.source.mode == Mode.ALL and request.target.mode != Mode.ALL:
        raise rules.RuleError("여러 시체에서 가져올 대상에도 '모두'를 붙이세요.")
    item = None if request.target.name == "전리품" else find_id(ITEMS, request.target.name)
    if item is None and request.target.name != "전리품":
        raise rules.RuleError("가져올 아이템 이름을 확인하세요.")
    # 만료 처리는 회수 실패와 별개로 확정한다. 회수 중에는 yield하지 않는다.
    reconcile_room(caller.location, now)
    with world_change():
        sources = [obj for obj in room_loot(caller.location, corpse) if visible(obj, caller)]
        if corpse:
            sources = select(sources, request.source)
        candidates = [
            (source, index)
            for source in sources
            for index, entry in enumerate(source.db.entries)
            if item is None or entry["item"] == item
        ]
        chosen = select(candidates, request.target)
        chosen = {(source.id, index) for source, index in chosen}
        received = []
        for source in sources:
            entries = deserialize(source.db.entries)
            remaining = []
            for index, entry in enumerate(entries):
                target = recipient_for(entry, caller, now)
                if not target or (source.id, index) not in chosen:
                    remaining.append(entry)
                    continue
                quantity = entry["quantity"] if request.target.mode == Mode.ALL else 1
                profile = target.profile()
                rules.add_item(profile, entry["item"], quantity)
                target.save_profile(profile)
                received.append((target, entry["item"], quantity))
                if entry["quantity"] > quantity:
                    remaining.append({**entry, "quantity": entry["quantity"] - quantity})
            source.db.entries = remaining
            if not corpse and not remaining:
                source.delete()
    if not received:
        raise rules.RuleError("가져갈 물건이 없거나 다른 탐사자의 보호된 전리품입니다.")
    totals = {}
    for target, identity, quantity in received:
        totals[(target, identity)] = totals.get((target, identity), 0) + quantity
    own = [
        ft.text(ft.item(identity), " ", count_word(quantity), " 개")
        for (target, identity), quantity in totals.items()
        if target == caller
    ]
    if own:
        items = ft.join(own, "와 ")
        caller.msg(ft.text("시체를 뒤져 " if corpse else "바닥에서 ", items, "를 챙겼다."))
    for (target, item_id), quantity in totals.items():
        if target != caller:
            message = ft.text(
                ft.item(item_id),
                " ",
                count_word(quantity),
                " 개는 이번 순번인 ",
                ft.token("player", target.key),
                "에게 돌아갔다.",
            )
            caller.msg(message)
            target.msg(message)
    for obj in caller.location.contents:
        if hasattr(obj, "push_state"):
            obj.push_state()
    return received


class Corpse(DefaultObject):
    def return_appearance(self, looker, **kwargs):
        from world.state import loot_entries

        entries = loot_entries(self, looker, time())
        lines = ["남아 있는 물건을 살펴본다.", ""]
        for entry in entries:
            rights = (
                ft.text(" · 배정: ", ft.token("player", entry["assigned_name"]))
                if entry["protected"]
                else " · 자유 획득"
            )
            lines.append(
                ft.text(
                    ft.item(entry["item"]),
                    f" ×{entry['quantity']}",
                    rights,
                    " (회수 가능)" if entry["can_take"] else " (보호 중)",
                )
            )
        if not entries:
            lines.append("남은 전리품이 없다.")
        lines.extend(["", ft.actions(["가져"] if entries else [])])
        return ft.sheet(ft.token("remains", self.key), *lines)

    def at_object_creation(self):
        self.locks.add("get:false();puppet:false();delete:false()")
        self.db.entries = []

    @classmethod
    def from_enemy(cls, enemy, groups, now, rng=None):
        corpse = create_object(cls, key=f"{enemy.key}의 시체", location=enemy.location)
        corpse.db.source_spawn = enemy.db.spawn_id
        corpse.db.source_enemy = enemy.db.enemy_id
        corpse.db.created_at = now
        corpse.db.decay_at = now + CORPSE_TTL_SECONDS
        corpse.db.entries = build_entries(enemy, groups, now, rng)
        after_change(corpse.schedule_lifecycle)
        return corpse

    def reconcile(self, now=None):
        now = time() if now is None else now
        with world_change():
            if not self.pk or not object_by_id(self.pk) or now < self.db.decay_at:
                return
            room = self.location
            for entry in deserialize(self.db.entries):
                dropped = create_object(
                    DroppedLoot, key=ITEMS[entry["item"]]["name"], location=room
                )
                dropped.db.entries = [entry]
                dropped.db.source_spawn = self.db.source_spawn
            self.db.entries = []
            task = self.ndb.lifecycle_task
            self.ndb.lifecycle_task = None
            if task:
                task.remove()
            self.delete()

    def schedule_lifecycle(self):
        if self.pk and not self.ndb.lifecycle_task:
            self.ndb.lifecycle_task = delay(
                max(0.05, self.db.decay_at - time()), self.lifecycle_tick
            )

    def lifecycle_tick(self):
        self.ndb.lifecycle_task = None
        room = self.location
        self.reconcile()
        if self.pk:
            self.schedule_lifecycle()
        if room:
            for obj in room.contents:
                if hasattr(obj, "push_state"):
                    obj.push_state()


class DroppedLoot(DefaultObject):
    def return_appearance(self, looker, **kwargs):
        from world.state import loot_entries

        entries = loot_entries(self, looker, time())
        lines = ["남아 있는 물건을 살펴본다.", ""]
        for entry in entries:
            rights = (
                ft.text(" · 배정: ", ft.token("player", entry["assigned_name"]))
                if entry["protected"]
                else " · 자유 획득"
            )
            lines.append(
                ft.text(
                    ft.item(entry["item"]),
                    f" ×{entry['quantity']}",
                    rights,
                    " (회수 가능)" if entry["can_take"] else " (보호 중)",
                )
            )
        if not entries:
            lines.append("남은 전리품이 없다.")
        lines.extend(["", ft.actions(["가져"] if entries else [])])
        return ft.sheet(ft.token("item", self.key), *lines)

    def at_object_creation(self):
        self.locks.add("get:false();puppet:false();delete:false()")
        self.db.entries = []
