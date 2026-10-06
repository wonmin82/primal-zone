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
from world.content.economy import CURRENCY
from world.currency import currency_request, format_currency
from world.distant_presentation import DistantPresenceMixin
from world.loot_assets import asset_name, asset_text, currency_payouts, normalize_entry
from world.multiplayer import (
    CORPSE_TTL_SECONDS,
    LOOT_PROTECTION_SECONDS,
    after_change,
    object_by_id,
    world_change,
)
from world.targets import LootRequest, Mode, TargetSelector, ordered, select


def build_entries(enemy, groups, now, rng=None):
    definition = ENEMIES[enemy.db.enemy_id]
    from world.loot_rules import roll_loot

    items = roll_loot(enemy.db.enemy_id, rng or Random())
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
                "kind": "item",
                **item,
                "reserved_party": party.id if party else None,
                "reserved_player": identity if kind == "player" else None,
                "assigned_player": assigned,
                "protection_until": now + LOOT_PROTECTION_SECONDS,
            }
        )
    allocation = rules.reward_allocation(definition["currency"], groups)
    for group, members in sorted(groups.items()):
        shares = {identity: allocation[identity] for identity in members if allocation[identity] > 0}
        quantity = sum(shares.values())
        if not quantity:
            continue
        kind, identity = group.split(":")
        entries.append({
            "kind": "currency", "id": CURRENCY["id"], "quantity": quantity,
            "eligible_players": sorted(members), "remaining_shares": shares,
            "reserved_party": int(identity) if kind == "party" else None,
            "reserved_player": int(identity) if kind == "player" else None,
            "assigned_player": None, "protection_until": now + LOOT_PROTECTION_SECONDS,
        })
    return entries


def recipient_for_item(entry, caller, now):
    """item 순번 배정의 지급 대상. currency의 트리거 권한과 구분한다."""
    from typeclasses.parties import party_for

    entry = normalize_entry(entry)
    if now >= entry["protection_until"]:
        return caller
    party = party_for(caller)
    allowed = caller.id in (entry["reserved_player"], entry["assigned_player"]) or (
        party and party.id == entry["reserved_party"]
    )
    return object_by_id(entry["assigned_player"]) if allowed else None


def can_take_entry(entry, caller, now):
    entry = normalize_entry(entry)
    if entry["kind"] == "currency":
        return now >= entry["protection_until"] or caller.id in entry["eligible_players"]
    return recipient_for_item(entry, caller, now) is not None


def room_loot(room, corpse=True):
    cls = Corpse if corpse else DroppedLoot
    return (
        ordered(
            (obj for obj in room.contents if obj.is_typeclass(cls, exact=True)),
        )
        if room
        else []
    )


def create_dropped_loot(room, entries, source_spawn=None):
    """직접 버리기와 시체 decay가 같은 바닥 물건 표현을 사용한다."""
    dropped = create_object(DroppedLoot, key=asset_name(normalize_entry(entries[0])), location=room)
    from world.item_runtime import native_runtime, require_runtime

    require_runtime()
    if native_runtime():
        from world.loot_service import populate_source

        populate_source(dropped, entries)
    else:
        dropped.db.entries = [normalize_entry(entry) for entry in entries]
    dropped.db.source_spawn = source_spawn
    return dropped


def take_loot(caller, item=None, corpse=True, now=None, *, request=None):
    """선택과 트리거 권한을 검증한 뒤 item 배정 또는 currency 잔여 몫을 지급한다."""
    from world import loot_service
    from world.lifecycle import reconcile_room
    from world.observation import can_inspect_loot, can_perceive, context_for
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
    currency = currency_request(request.target)
    item = None if request.target.name == "전리품" or currency else find_id(ITEMS, request.target.name)
    if item is None and request.target.name != "전리품" and not currency:
        raise rules.RuleError("가져올 아이템 이름을 확인하세요.")
    # 만료는 회수와 별개로 확정한다. 실제 지급은 한 transaction에서 처리한다.
    reconcile_room(caller.location, now)
    with world_change():
        if currency:
            rules.require_peace(caller.profile())
        context = context_for(caller, observed_at=now)
        if not can_inspect_loot(context):
            raise rules.RuleError("지금은 작은 전리품을 식별할 수 없습니다. 광원을 사용하세요.")
        sources = [obj for obj in room_loot(caller.location, corpse) if can_perceive(obj, context)]
        if corpse:
            sources = select(sources, request.source)
        if any(loot_service.native_source(source) for source in sources):
            loot_service.lock_sources(sources, caller)
        snapshots = {source.id: loot_service.loot_snapshot(source) for source in sources}
        entries_by_source = {identity: [entry.as_entry() for entry in snapshot.entries]
                             for identity, snapshot in snapshots.items()}
        candidates = [
            (source, index)
            for source in sources
            for index, entry in enumerate(entries_by_source[source.id])
            if ((currency and entry["kind"] == "currency" and can_take_entry(entry, caller, now))
                or (not currency and (item is None or entry["kind"] == "item" and entry["id"] == item)))
        ]
        chosen = {(source.id, index) for source, index in select(candidates, request.target)}
        received = []
        recovered_currency = 0
        for source in sources:
            if not any(identity == source.id for identity, _ in chosen):
                continue
            remaining = []
            changed = False
            for index, entry in enumerate(entries_by_source[source.id]):
                if (source.id, index) not in chosen or not can_take_entry(entry, caller, now):
                    remaining.append(entry)
                    continue
                changed = True
                quantity = (entry["quantity"] if request.target.mode == Mode.ALL
                            else currency[0] if currency else 1)
                if quantity > entry["quantity"]:
                    raise rules.RuleError("선택한 전리품의 보급칩이 부족합니다.")
                if snapshots[source.id].native:
                    received.extend(loot_service.pickup(source, snapshots[source.id].entries[index],
                                                       caller, quantity, now=now))
                    if entry["kind"] == "currency":
                        recovered_currency += quantity
                    continue
                if entry["kind"] == "currency":
                    rules.require_peace(caller.profile())
                    protected = now < entry["protection_until"]
                    shares = entry["remaining_shares"] if protected else {}
                    payouts = currency_payouts(entry, quantity, caller.id, now)
                    for identity, amount in payouts.items():
                        if not amount:
                            continue
                        recipient = object_by_id(identity)
                        if recipient is None:
                            raise rules.RuleError("보급칩을 받을 탐사자를 확인할 수 없습니다.")
                        profile = recipient.profile()
                        profile["credits"] += amount
                        recipient.save_profile(profile)
                        received.append((recipient, CURRENCY["id"], amount))
                    entry["remaining_shares"] = {identity: amount - payouts.get(identity, 0)
                                       for identity, amount in shares.items() if amount > payouts.get(identity, 0)}
                    recovered_currency += quantity
                else:
                    target = recipient_for_item(entry, caller, now)
                    from world.equipment_service import entity_runtime

                    if entity_runtime(target):
                        raise rules.RuleError("legacy 실물 전리품은 Phase 6 변환 전 native 소지품으로 회수할 수 없습니다.")
                    profile = target.profile()
                    rules.add_item(profile, entry["id"], quantity)
                    target.save_profile(profile)
                    received.append((target, entry["id"], quantity))
                if entry["quantity"] > quantity:
                    remaining.append({**entry, "quantity": entry["quantity"] - quantity})
            if changed and not snapshots[source.id].native:
                source.db.entries = remaining
            empty = not loot_service.loot_snapshot(source).entries if snapshots[source.id].native else not remaining
            if changed and not corpse and empty:
                source.delete()
        if not received:
            raise rules.RuleError("가져갈 물건이 없거나 다른 탐사자의 보호된 전리품입니다.")
    totals = {}
    for target, identity, quantity in received:
        totals[(target, identity)] = totals.get((target, identity), 0) + quantity
    own = [ft.text(ft.item(identity), " ", count_word(quantity), " 개")
           for (target, identity), quantity in totals.items() if target == caller and identity != CURRENCY["id"]]
    if own:
        caller.msg(ft.text("시체를 뒤져 " if corpse else "바닥에서 ", ft.join(own, "와 "), "를 챙겼다."))
    if recovered_currency:
        caller.msg(ft.text("시체에서 " if corpse else "바닥에서 ", ft.token("reward", format_currency(recovered_currency)), "을 회수했다."))
        caller.msg(ft.join([ft.text(ft.token("player", target.key), " ", ft.token("reward", format_currency(amount)))
                           for (target, identity), amount in totals.items() if identity == CURRENCY["id"]], " · "))
    for (target, identity), quantity in totals.items():
        if target != caller:
            if identity == CURRENCY["id"]:
                message = ft.text("전리품 분배로 ", ft.token("reward", format_currency(quantity)), "을 받았다.")
            else:
                message = ft.text(ft.item(identity), " ", count_word(quantity), " 개는 이번 순번인 ",
                                  ft.token("player", target.key), "에게 돌아갔다.")
                caller.msg(message)
            target.msg(message)
            target.push_state()
    for obj in caller.location.contents:
        if hasattr(obj, "push_state"):
            obj.push_state()
    return received


class Corpse(DistantPresenceMixin, DefaultObject):
    distant_visible = True
    distant_role = "remains"
    distant_unit = "구"
    distant_sentence = "바닥에 남아 있다."

    def is_distant_visible(self, context):
        return (
            self.db.decay_at is not None
            and context.observed_at < self.db.decay_at
            and super().is_distant_visible(context)
        )

    def return_appearance(self, looker, **kwargs):
        from world.state import loot_controls, loot_entries

        now = kwargs.get("observed_at", time())
        control = loot_controls(looker, now).get(self.id)
        entries = control["loot"] if control else loot_entries(self, looker, now)
        lines = ["남아 있는 물건을 살펴본다.", ""]
        for entry in entries:
            rights = (
                ft.text(" · 배정: ", ft.token("player", entry["assigned_name"]))
                if entry["protected"]
                else " · 자유 획득"
            )
            lines.append(
                ft.text(
                    asset_text(entry),
                    rights,
                    " (회수 가능)" if entry["can_take"] else " (보호 중)",
                )
            )
        if not entries:
            from world.observation import can_inspect_loot, context_for

            lines.append("작은 전리품을 식별하기 어렵다. 광원을 사용하세요." if not can_inspect_loot(context_for(looker, observed_at=now)) else "남은 전리품이 없다.")
        if control:
            lines.extend(["", ft.text("지정: ", ft.token("remains", control["label"]))])
            if entries:
                lines.append(ft.text("회수: ", ft.usage(control["take_command"], {"가져"})))
        return ft.sheet(ft.token("remains", self.key), *lines)

    def at_object_creation(self):
        self.locks.add("get:false();puppet:false();delete:false()")
        self.db.entries = []

    @classmethod
    def from_enemy(cls, enemy, groups, now, rng=None, *, backend="legacy"):
        """native generation은 명시적으로 선택한다. 기존 사냥의 backend는 바꾸지 않는다."""
        with world_change():
            from world.item_runtime import native_runtime, require_runtime

            require_runtime()
            if native_runtime():
                backend = "item_entities"
            return cls._from_enemy(enemy, groups, now, rng, backend=backend)

    @classmethod
    def _from_enemy(cls, enemy, groups, now, rng, *, backend):
        if backend not in ("legacy", "item_entities"):
            raise rules.RuleError("알 수 없는 전리품 저장 방식입니다.")
        corpse = create_object(cls, key=f"{enemy.key}의 시체", location=enemy.location)
        corpse.db.source_spawn = enemy.db.spawn_id
        corpse.db.source_enemy = enemy.db.enemy_id
        corpse.db.created_at = now
        corpse.db.decay_at = now + CORPSE_TTL_SECONDS
        if backend == "item_entities":
            from world.loot_service import lock_sources

            owners = {identity for members in groups.values() for identity in members}
            owners.update(int(group.split(":")[1]) for group in groups if group.startswith("party:"))
            lock_sources([corpse], extra_owners=owners)
        entries = build_entries(enemy, groups, now, rng)
        if backend == "item_entities":
            from world.loot_service import populate_source

            populate_source(corpse, entries)
        else:
            corpse.db.entries = entries
        after_change(corpse.schedule_lifecycle)
        return corpse

    def reconcile(self, now=None):
        now = time() if now is None else now
        with world_change():
            if not self.pk or not object_by_id(self.pk):
                return
            from world.item_runtime import native_runtime
            from world.loot_service import decay_source, native_source, reconcile_claims

            if native_runtime() and not native_source(self):
                raise rules.RuleError("Item runtime migration required: corpse backend")
            reconcile_claims(self, now=now)
            if now < self.db.decay_at:
                return
            room = self.location
            if native_source(self):
                decay_source(self, now=now)
            else:
                for entry in deserialize(self.db.entries):
                    create_dropped_loot(room, [entry], self.db.source_spawn)
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


class DroppedLoot(DistantPresenceMixin, DefaultObject):
    detectability = "subtle"

    def reconcile(self, now=None):
        from world.loot_service import reconcile_claims

        reconcile_claims(self, now=time() if now is None else now)

    def return_appearance(self, looker, **kwargs):
        from world.state import loot_controls, loot_entries

        now = kwargs.get("observed_at", time())
        control = loot_controls(looker, now).get(self.id)
        entries = control["loot"] if control else loot_entries(self, looker, now)
        lines = ["남아 있는 물건을 살펴본다.", ""]
        for entry in entries:
            rights = (
                ft.text(" · 배정: ", ft.token("player", entry["assigned_name"]))
                if entry["protected"]
                else " · 자유 획득"
            )
            lines.append(
                ft.text(
                    asset_text(entry),
                    rights,
                    " (회수 가능)" if entry["can_take"] else " (보호 중)",
                )
            )
        if not entries:
            lines.append("남은 전리품이 없다.")
        if control and entries:
            lines.extend(
                [
                    "",
                    ft.text(
                        "회수: ",
                        ft.usage(" · ".join(entry["take_command"] for entry in entries), {"가져"}),
                    ),
                ]
            )
        return ft.sheet(ft.token("item", self.key), *lines)

    def at_object_creation(self):
        self.locks.add("get:false();puppet:false();delete:false()")
        self.db.entries = []
