"""Persistent player snapshots and one server-owned combat timer per character."""

import re
import unicodedata
from time import time

from django.db import transaction
from evennia.objects.objects import DefaultCharacter
from evennia.utils import delay
from evennia.utils.dbserialize import deserialize
from world import recovery, rules
from world import text as ft
from world.content import (
    EQUIPMENT_ACTIONS,
    ITEMS,
    REGIONS,
    ROOM_REGION,
    ROOMS,
    UNEQUIP_ACTIONS,
    ordered_directions,
)
from world.content.economy import CURRENCY
from world.currency import format_currency
from world.distant_presentation import DistantPresence, DistantPresenceMixin
from world.multiplayer import after_change
from world.navigation import entry_block
from world.quests import current_hint


class _MoveRejected(Exception):
    pass


class Explorer(DistantPresenceMixin, DefaultCharacter):
    distant_visible = True

    def get_distant_presence(self, context):
        return DistantPresence("탐사자", "player", "명", "멀리 주변을 살피고 있다.")

    def return_appearance(self, looker, **kwargs):
        return ft.sheet(ft.token("player", self.key), "섬을 탐험하는 탐사자다.")

    def msg(self, text=None, from_obj=None, session=None, options=None, **kwargs):
        from evennia.utils.utils import make_iter
        from world.text import Text

        message = text[0] if isinstance(text, tuple) else text
        if not isinstance(message, Text):
            return super().msg(text, from_obj=from_obj, session=session, options=options, **kwargs)
        sessions = make_iter(session) if session else self.sessions.all()
        for target in sessions:
            if target.protocol_key in ("websocket", "webclient/websocket"):
                super().msg(
                    from_obj=from_obj,
                    session=target,
                    options={**(options or {}), "raw": True},
                    pz_log=([{"kind": message.kind, "segments": message.segments}], {}),
                    **kwargs,
                )
            else:
                from evennia.utils.ansi import parse_ansi

                super().msg(
                    parse_ansi(message.ansi()),
                    from_obj=from_obj,
                    session=target,
                    options={**(options or {}), "raw": True},
                    **kwargs,
                )

    @classmethod
    def normalize_name(cls, name):
        return unicodedata.normalize("NFKC", name).strip()

    @classmethod
    def validate_name(cls, name, account=None):
        if not re.fullmatch(r"[가-힣A-Za-z0-9_]{2,24}", name):
            return "이름은 한글·영문·숫자·밑줄 2~24자로 입력하세요."
        return super().validate_name(name, account=account)

    def at_object_creation(self):
        super().at_object_creation()
        self.db.profile = rules.new_profile()

    def profile(self):
        if self.db.profile is None:
            self.db.profile = rules.new_profile()
        profile = deserialize(self.db.profile)
        if profile.get("version", 1) < rules.PROFILE_VERSION:
            profile = rules.migrate_profile(profile)
            self.db.profile = profile
        return profile

    def profile_snapshot(self):
        """관찰용 사본만 변환한다. 구버전 profile도 저장하거나 진행하지 않는다."""
        saved = deserialize(self.db.profile)
        return rules.migrate_profile(saved) if saved is not None else rules.new_profile()

    def save_profile(self, profile):
        recovery.clamp(profile, rules.stats(profile))
        with transaction.atomic():
            self.db.profile = profile
        after_change(self.push_state)
        after_change(self.schedule_recovery)

    def change(self, operation):
        from world.multiplayer import world_change

        with world_change():
            profile = self.profile()
            self.accrue_recovery(profile)
            result = operation(profile)
            self.save_profile(profile)
            return result

    def accrue_recovery(self, profile, now=None):
        # DefaultCharacter는 마지막 unpuppet에서 location을 비우고 옛 방을 저장한다.
        room = self.location or self.db.prelogout_location
        zone = room.db.zone_id if room else None
        recovery.accrue_player(profile, rules.stats(profile), ROOMS.get(zone, {}),
                               ITEMS, time() if now is None else now)

    def checkpoint_recovery(self):
        """조건 경계만 저장한다. 이동 전 옛 Room 화면은 전송하지 않는다."""
        from world.multiplayer import world_change

        with world_change():
            profile = self.profile()
            self.accrue_recovery(profile)
            self.db.profile = profile

    def reconcile_recovery(self, now=None, *, emit_prompt=True):
        from world.multiplayer import world_change

        now = time() if now is None else now
        with world_change():
            profile = self.profile()
            self.accrue_recovery(profile, now)
            changed = recovery.commit(profile, rules.stats(profile))
            self.db.profile = profile
            if changed:
                after_change(self.push_state)
                if emit_prompt:
                    after_change(self.request_prompt)
            after_change(self.schedule_recovery)
        return changed

    def begin_command_output(self):
        depth = self.ndb.command_output_depth or 0
        self.ndb.command_output_depth = depth + 1
        if not depth:
            self.cancel_pending_prompt()
            profile = self.profile_snapshot()
            state = profile.get("recovery")
            now = time()
            # 새 경계가 없으면 조회/실패 명령으로 저장 시계를 불필요하게 쓰지 않는다.
            if (state and now >= state["boundary"] + recovery.RECOVERY_INTERVAL) or (
                not state and any(profile[key] < rules.stats(profile)["max_" + key]
                                  for key in recovery.RESOURCES)
            ):
                self.reconcile_recovery(now, emit_prompt=False)

    def end_command_output(self):
        self.ndb.command_output_depth = max(0, (self.ndb.command_output_depth or 0) - 1)
        if not self.ndb.command_output_depth:
            self.cancel_pending_prompt()
            self.push_prompt()

    def request_prompt(self):
        """같은 reactor 구간의 전투/이동 출력을 마친 뒤 한 번만 전송한다."""
        from twisted.internet import reactor

        if not self.ndb.command_output_depth and not self.ndb.prompt_task and self.sessions.count():
            self.ndb.prompt_task = reactor.callLater(0, self.flush_prompt)

    def flush_prompt(self):
        self.ndb.prompt_task = None
        if not self.ndb.command_output_depth:
            self.push_prompt()

    def cancel_pending_prompt(self):
        task = self.ndb.prompt_task
        self.ndb.prompt_task = None
        if task and task.active():
            task.cancel()

    def push_prompt(self):
        if not self.sessions.count():
            return
        from evennia.utils.ansi import parse_ansi

        profile = self.profile_snapshot()
        prompt = ft.resource_prompt(profile, rules.stats(profile))
        for session in self.sessions.all():
            if session.protocol_key in ("websocket", "webclient/websocket"):
                self.msg(prompt, session=session)
            else:
                super().msg(session=session, prompt=(parse_ansi(prompt.ansi()), {}))

    def schedule_recovery(self):
        profile = self.profile_snapshot()
        now = time()
        due = recovery.next_wakeup(profile, rules.stats(profile), ROOMS.get(self.zone, {}), ITEMS, now)
        if not self.sessions.count() or due is None:
            self.stop_recovery_timer()
        elif not self.ndb.recovery_task or self.ndb.recovery_due != due:
            self.stop_recovery_timer()
            self.ndb.recovery_due = due
            self.ndb.recovery_task = delay(max(0.05, due - now), self.recovery_tick)

    def recovery_tick(self):
        self.ndb.recovery_task = None
        self.ndb.recovery_due = None
        if self.sessions.count():
            self.reconcile_recovery()

    def stop_recovery_timer(self):
        task = self.ndb.recovery_task
        self.ndb.recovery_task = None
        self.ndb.recovery_due = None
        if task:
            task.remove()

    @property
    def zone(self):
        return self.location.db.zone_id if self.location else None

    def push_state(self, observed_at=None):
        if not self.sessions.count():
            return
        from world.environment import display
        from world.environment_state import snapshot_for
        from world.room_hints import render as room_hint
        from world.state import multiplayer_state

        from typeclasses.interactables import instructor_for

        observed_at = time() if observed_at is None else observed_at
        environment = snapshot_for(self.location, observed_at)
        profile = self.profile_snapshot()
        from world.observation import context_for
        from world.observation import display as observation_display

        observation = context_for(self, observed_at=observed_at, environment=environment)
        values = rules.stats(profile)
        zone = self.zone
        room = ROOMS.get(zone, {})
        inventory = [
            {
                "id": key,
                "name": ITEMS[key]["name"],
                "count": count,
                "slot": ITEMS[key]["slot"],
                "equip_action": EQUIPMENT_ACTIONS.get(ITEMS[key]["slot"]),
                "remove_action": UNEQUIP_ACTIONS.get(ITEMS[key]["slot"]),
                "consume_action": ITEMS[key].get("consume_action"),
                "equipped": key in profile["equipment"].values(),
                "light_source": ITEMS[key].get("light_source"),
                "power_source": ITEMS[key].get("power_source"),
            }
            for key, count in profile["inventory"].items()
        ]
        instructor = instructor_for(self, observed_at=observed_at)
        payload = {
            "growth": rules.growth_state(profile),
            "training_available": bool(instructor),
            "name": self.key,
            "hp": profile["hp"],
            "mental": profile["mental"],
            **values,
            "xp": profile["xp"],
            "xp_floor": rules.xp_threshold(values["level"]),
            "xp_next": rules.xp_threshold(values["level"] + 1),
            "credits": profile["credits"],
            "currency": {**CURRENCY, "formatted": format_currency(profile["credits"])},
            "resources": {"scrap": {"name": ITEMS["scrap"]["name"], "count": profile["inventory"].get("scrap", 0)}},
            "room": room.get("name", "탐사 준비"),
            "zone": zone,
            "environment": display(environment) if environment else None,
            "observation": observation_display(observation, profile),
            "region": ROOM_REGION.get(zone),
            "region_name": REGIONS[ROOM_REGION[zone]]["name"] if zone in ROOM_REGION else None,
            "safe": room.get("safe", False),
            "inventory": inventory,
            "equipment": {slot: ITEMS[identity]["name"] if identity else None for slot, identity in profile["equipment"].items()},
            "exits": ordered_directions(room.get("exits", {})),
            "hint": room_hint(observation),
            **multiplayer_state(self, now=observed_at),
            "player_round": profile["player_round"],
            "heavy_ready": observed_at >= profile["heavy_ready_at"],
            "queued_action": profile["queued_action"],
            "quest": self.quest_text(profile),
            "visited": [ROOMS[key]["name"] for key in profile["visited"] if key in ROOMS],
        }
        self.msg(pz_state=([payload], {}))

    @staticmethod
    def quest_text(profile):
        return current_hint(profile)

    def at_pre_puppet(self, account, session=None, **kwargs):
        # 새 authentication/puppet만 이 hook을 통과한다. Evennia 6.1 at_sync의
        # live-session reload 복원은 puppet hook 없이 기존 Object를 연결한다.
        from world.bootstrap import get_room

        # 오프라인 구간은 옛 위치로 계산한 다음 로그인 위치를 바꾼다.
        self.reconcile_recovery(emit_prompt=False)
        self.location = get_room("staging_room")
        super().at_pre_puppet(account, session=session, **kwargs)

    def at_post_puppet(self, **kwargs):
        from world.bootstrap import get_room

        dock = get_room("dock")
        if dock:
            self.home = dock
        if self.zone not in ROOMS:
            start = get_room("staging_room")
            if start:
                self.location = start
        self.begin_command_output()
        try:
            super().at_post_puppet(**kwargs)
            self.msg("|g원시구역에 오신 것을 환영합니다.|n '도움말'로 명령을 확인하세요.")
            self.leave_combat()
            self.push_state()
            self.schedule_recovery()
        finally:
            self.end_command_output()

    def at_post_unpuppet(self, account=None, session=None, **kwargs):
        self.ndb.shortcut_delete_all_request = None
        if not self.sessions.count():
            self.cancel_pending_prompt()
            self.ndb.command_output_depth = 0
            self.reconcile_lights(time(), turn_off=True)
            self.leave_combat()
            self.change(lambda profile: None)
            self.stop_recovery_timer()
        super().at_post_unpuppet(account=account, session=session, **kwargs)

    def reconcile_lights(self, observed_at, *, turn_off=False):
        from world import lighting
        from world.multiplayer import world_change

        with world_change():
            profile = self.profile_snapshot()
            if lighting.normalize(profile, observed_at, turn_off=turn_off):
                self.save_profile(profile)
                if not turn_off:
                    after_change(lambda: self.msg("광원의 전원이 다 되어 빛이 꺼졌다."))

    def at_server_shutdown(self):
        self.cancel_pending_prompt()
        self.ndb.shortcut_delete_all_request = None
        self.reconcile_lights(time(), turn_off=True)
        self.leave_combat()
        if self.sessions.count():
            self.change(lambda profile: None)
        self.stop_recovery_timer()
        super().at_server_shutdown()

    def announce_move_from(self, destination, msg=None, mapping=None, move_type="move", **kwargs):
        if msg is not None:
            return super().announce_move_from(destination, msg, mapping, move_type, **kwargs)
        if move_type == "elevator":
            from world.multiplayer import after_change

            origin = self.location
            after_change(lambda: self._announce_presence(origin, " 이곳을 떠났다."))
        else:
            self._announce_presence(self.location, " 이곳을 떠났다.")

    def announce_move_to(self, source_location, msg=None, mapping=None, move_type="move", **kwargs):
        if msg is not None:
            return super().announce_move_to(source_location, msg, mapping, move_type, **kwargs)
        if move_type == "elevator":
            from world.multiplayer import after_change

            destination = self.location
            after_change(lambda: self._announce_presence(destination, " 이곳에 도착했다."))
        else:
            self._announce_presence(self.location, " 이곳에 도착했다.")

    def _announce_presence(self, room, sentence):
        from world.observation import can_perceive, context_for

        if room:
            message = ft.text(ft.named("player", self.key, "이/가"), sentence)
            for observer in room.contents:
                if observer != self and observer.has_account and can_perceive(self, context_for(observer, room)):
                    observer.msg(message, from_obj=self)

    def at_pre_move(self, destination, move_type="move", **kwargs):
        profile = self.profile()
        if profile.get("combat_target"):
            self.msg("전투 중에는 이동할 수 없습니다. '도망'으로 교전을 끝내세요.")
            return False
        requirement = entry_block(profile, destination.db.zone_id)
        if requirement:
            self.msg(requirement["message"])
            return False
        allowed = super().at_pre_move(destination, move_type=move_type, **kwargs)
        if allowed:
            self.checkpoint_recovery()
        return allowed

    def move_to(self, destination, *args, **kwargs):
        from world.multiplayer import world_change

        try:
            with world_change():
                moved = super().move_to(destination, *args, **kwargs)
                if not moved:
                    raise _MoveRejected()
                return moved
        except _MoveRejected:
            return False

    def at_post_move(self, source_location, move_type="move", **kwargs):
        self.leave_combat()
        if self.zone in ROOMS:
            profile = self.profile()
            if self.zone not in profile["visited"]:
                profile["visited"].append(self.zone)
            self.save_profile(profile)
        # rollback 전에 도착 화면이나 내부 look을 실행하지 않는다.
        after_change(lambda: self.present_destination(source_location, move_type=move_type, **kwargs))

    def present_destination(self, source_location, **kwargs):
        # DefaultCharacter의 내부 look은 별도 사용자 입력이 아니다.
        self.ndb.command_output_depth = (self.ndb.command_output_depth or 0) + 1
        try:
            super().at_post_move(source_location, **kwargs)
        finally:
            self.ndb.command_output_depth -= 1

    def combat_target(self):
        from world.multiplayer import object_by_id

        from typeclasses.enemies import Enemy

        enemy = object_by_id(self.profile_snapshot().get("combat_target"))
        return enemy if enemy and enemy.is_typeclass(Enemy, exact=True) else None

    def combat_snapshot(self):
        enemy = self.combat_target()
        if not enemy or enemy.db.state != "alive":
            return None
        return {
            "id": enemy.id,
            "enemy": enemy.db.enemy_id,
            "name": enemy.key,
            "hp": enemy.db.hp,
            "max_hp": enemy.db.max_hp,
            "round": enemy.db.enemy_round,
            "state": enemy.db.state,
            "telegraph": rules.boss_telegraph(enemy.db.enemy_id, enemy.db.enemy_round),
        }

    def start_combat(self, enemy_id):
        from world.lifecycle import reconcile_room

        reconcile_room(self.location)
        from typeclasses.enemies import room_enemies

        enemy = enemy_id if enemy_id in room_enemies(self.location) else next(
            (obj for obj in room_enemies(self.location) if obj.db.enemy_id == enemy_id), None
        )
        if not enemy:
            raise rules.RuleError("이곳에는 공격할 수 있는 상대가 없습니다.")
        enemy.engage(self)
        self.msg(
            ft.text(
                ft.named("hostile", enemy.key, "과/와"),
                " 교전을 시작했다. 기본 공격은 2.5초마다 이어진다.",
            )
        )
        self.push_state()

    def leave_combat(self, now=None):
        from world.multiplayer import world_change

        with world_change():
            enemy = self.combat_target()
            if enemy:
                enemy.remove_combatant(self, now=now)
            after_change(self.stop_combat_timer)
            profile = self.profile()
            if profile.get("combat_target"):
                self.accrue_recovery(profile, now)
                profile.update(combat_target=None, queued_action="attack", guard_until=0)
                self.save_profile(profile)

    def schedule_combat(self):
        if (
            not self.ndb.combat_task
            and self.sessions.count()
            and self.profile().get("combat_target")
        ):
            remaining = max(0.05, self.profile()["next_attack_at"] - time())
            self.ndb.combat_task = delay(remaining, self.combat_tick)

    def stop_combat_timer(self):
        task = self.ndb.combat_task
        self.ndb.combat_task = None
        if task:
            task.remove()

    def combat_tick(self):
        self.ndb.combat_task = None
        if not self.sessions.count():
            self.leave_combat()
            return
        self.resolve_combat_round()
        self.schedule_combat()

    def resolve_combat_round(self, rng=None, now=None):
        enemy = self.combat_target()
        if enemy:
            enemy.receive_attack(self, now=now, rng=rng)
        else:
            self.leave_combat()
