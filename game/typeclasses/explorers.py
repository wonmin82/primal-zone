"""Persistent player snapshots and one server-owned combat timer per character."""

import re
import unicodedata
from time import time

from django.db import transaction
from evennia.objects.objects import DefaultCharacter
from evennia.utils import delay
from evennia.utils.dbserialize import deserialize
from world import rules
from world.content import ENEMIES, ITEMS, ROOMS
from world.multiplayer import after_change


class Explorer(DefaultCharacter):
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
        if profile.get("version", 1) < 2:
            profile.pop("encounter", None)
            for key in (
                "combat_target",
                "queued_action",
                "next_attack_at",
                "heavy_ready_at",
                "guard_until",
                "player_round",
            ):
                profile[key] = rules.new_profile()[key]
            profile["version"] = 2
            self.db.profile = profile
        return profile

    def save_profile(self, profile):
        with transaction.atomic():
            self.db.profile = profile
        after_change(self.push_state)

    def change(self, operation):
        profile = self.profile()
        result = operation(profile)
        self.save_profile(profile)
        return result

    @property
    def zone(self):
        return self.location.db.zone_id if self.location else None

    def push_state(self):
        if not self.sessions.count():
            return
        from world.state import multiplayer_state

        profile = self.profile()
        values = rules.stats(profile)
        zone = self.zone
        room = ROOMS.get(zone, {})
        inventory = [
            {
                "id": key,
                "name": ITEMS[key]["name"],
                "count": count,
                "slot": ITEMS[key]["slot"],
                "equipped": key in profile["equipment"].values(),
            }
            for key, count in profile["inventory"].items()
        ]
        payload = {
            "name": self.key,
            "hp": profile["hp"],
            **values,
            "xp": profile["xp"],
            "xp_floor": rules.xp_threshold(values["level"]),
            "xp_next": rules.xp_threshold(values["level"] + 1),
            "credits": profile["credits"],
            "room": room.get("name", "탐사 준비"),
            "zone": zone,
            "safe": room.get("safe", False),
            "inventory": inventory,
            "exits": list(room.get("exits", {})),
            "hint": room.get("hint", ""),
            **multiplayer_state(self),
            "player_round": profile["player_round"],
            "heavy_ready": time() >= profile["heavy_ready_at"],
            "queued_action": profile["queued_action"],
            "quest": self.quest_text(profile),
            "visited": [ROOMS[key]["name"] for key in profile["visited"] if key in ROOMS],
        }
        self.msg(pz_state=([payload], {}))

    @staticmethod
    def quest_text(profile):
        if profile["quest_claimed"]:
            return "통신탑 복구 완료 · 첫 탐사를 완수했습니다."
        if not profile["quest_started"]:
            return "부두에서 '윤대장 대화'으로 임무를 받으세요."
        if not profile["record_read"]:
            return "관리동에서 '정비기록 조사'. 사냥으로 장비와 회수부품 3개를 준비하세요."
        if not profile["generator_fixed"]:
            return "회수부품 3개를 모아 발전실에서 '발전기 수리'."
        if not profile["boss_defeated"]:
            return "능선의 우두머리를 처치하세요. 강화 장비와 붕대를 권장합니다."
        return "부두로 귀환하여 '윤대장 대화'으로 보상을 받으세요."

    def at_post_puppet(self, **kwargs):
        from world.bootstrap import get_room

        dock = get_room("dock")
        if dock:
            self.home = dock
            if self.zone not in ROOMS:
                self.location = dock
        super().at_post_puppet(**kwargs)
        self.msg("|g원시구역에 오신 것을 환영합니다.|n '도움말'로 명령을 확인하세요.")
        self.leave_combat()
        self.push_state()

    def at_post_unpuppet(self, account=None, session=None, **kwargs):
        if not self.sessions.count():
            self.leave_combat()
        super().at_post_unpuppet(account=account, session=session, **kwargs)

    def at_pre_move(self, destination, move_type="move", **kwargs):
        if self.profile().get("combat_target"):
            self.msg("전투 중에는 이동할 수 없습니다. '도주'로 교전을 끝내세요.")
            return False
        if destination.db.zone_id == "ridge" and not self.profile()["generator_fixed"]:
            self.msg("통신탑 진입문이 잠겨 있습니다. 정비기록을 읽고 발전기를 수리하세요.")
            return False
        return super().at_pre_move(destination, move_type=move_type, **kwargs)

    def at_post_move(self, source_location, move_type="move", **kwargs):
        self.leave_combat()
        if self.zone in ROOMS:
            profile = self.profile()
            if self.zone not in profile["visited"]:
                profile["visited"].append(self.zone)
            self.save_profile(profile)
        super().at_post_move(source_location, move_type=move_type, **kwargs)

    def combat_target(self):
        from world.multiplayer import object_by_id

        from typeclasses.enemies import Enemy

        enemy = object_by_id(self.profile().get("combat_target"))
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
            "telegraph": bool(
                ENEMIES[enemy.db.enemy_id].get("boss") and enemy.db.enemy_round % 3 == 2
            ),
        }

    def start_combat(self, enemy_id):
        from world.lifecycle import reconcile_room

        reconcile_room(self.location)
        from typeclasses.enemies import room_enemies

        enemy = next(
            (obj for obj in room_enemies(self.location) if obj.db.enemy_id == enemy_id), None
        )
        if not enemy:
            raise rules.RuleError("이곳에는 공격할 수 있는 상대가 없습니다.")
        enemy.engage(self)
        self.msg(f"{enemy.key}과(와) 교전합니다. 기본 공격은 2.5초마다 자동 진행됩니다.")
        self.push_state()

    def leave_combat(self):
        from world.multiplayer import world_change

        with world_change():
            enemy = self.combat_target()
            if enemy:
                enemy.remove_combatant(self)
            after_change(self.stop_combat_timer)
            profile = self.profile()
            if profile.get("combat_target"):
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
