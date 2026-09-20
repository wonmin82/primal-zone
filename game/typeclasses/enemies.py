"""장소별로 하나씩 존재하는 영속 적 spawn."""

from time import time

from evennia.objects.objects import DefaultObject
from evennia.utils import delay
from evennia.utils.dbserialize import deserialize
from world import rules
from world.content import ENEMIES
from world.multiplayer import (
    CLAIM_TIMEOUT_SECONDS,
    COMBAT_INTERVAL,
    CORPSE_TTL_SECONDS,
    ENEMY_RESET_SECONDS,
    PARTICIPATION_TIMEOUT_SECONDS,
    RESPAWN_DELAY_SECONDS,
    after_change,
    object_by_id,
    world_change,
)


class Enemy(DefaultObject):
    def at_object_creation(self):
        self.locks.add("get:false();puppet:false();delete:false()")
        self.db.state = "alive"
        self.db.respawn_at = None
        self.db.claim = None
        self.db.claim_last_activity = 0
        self.db.combatants = []
        self.db.contribution = {}
        self.db.threat = {}
        self.db.enemy_round = 0
        self.db.next_attack_at = 0
        self.db.last_activity = 0

    def active_players(self):
        return [
            player
            for identity in self.db.combatants
            if (player := object_by_id(identity))
            and player.location == self.location
            and player.sessions.count()
            and player.profile().get("combat_target") == self.id
        ]

    @staticmethod
    def group_for(player):
        from typeclasses.parties import party_for

        party = party_for(player)
        return f"party:{party.id}" if party else f"player:{player.id}"

    def can_attack(self, player):
        return ENEMIES[self.db.enemy_id]["combat_mode"] == "public" or self.db.claim in (
            None,
            self.group_for(player),
        )

    def reward_groups(self, now):
        groups = {}
        for player in self.active_players():
            entry = self.db.contribution.get(player.id)
            group = self.group_for(player)
            if (
                not entry
                or entry["damage"] <= 0
                or now - entry["last_action_at"] > PARTICIPATION_TIMEOUT_SECONDS
            ):
                continue
            if entry["group"] != group:
                continue
            if ENEMIES[self.db.enemy_id]["combat_mode"] == "claimed" and group != self.db.claim:
                continue
            groups.setdefault(group, {})[player.id] = entry["damage"]
        return groups

    def engage(self, player, now=None):
        now = time() if now is None else now
        with world_change():
            self.reconcile(now)
            if self.db.state != "alive":
                raise rules.RuleError("아직 다시 나타나지 않은 적입니다.")
            profile = player.profile()
            if profile.get("combat_target") not in (None, self.id):
                raise rules.RuleError("현재 상대에게서 먼저 도주하세요.")
            if not self.can_attack(player):
                owner = "다른 파티" if str(self.db.claim).startswith("party:") else "다른 탐사자"
                raise rules.RuleError(f"{self.key}은(는) {owner}와 교전 중입니다.")
            if ENEMIES[self.db.enemy_id]["combat_mode"] == "claimed" and not self.db.claim:
                self.db.claim = self.group_for(player)
            if player.id not in self.db.combatants:
                self.db.combatants = [*self.db.combatants, player.id]
                profile.update(
                    combat_target=self.id,
                    queued_action="attack",
                    next_attack_at=max(profile["next_attack_at"], now + COMBAT_INTERVAL),
                )
                player.save_profile(profile)
                if not self.db.next_attack_at:
                    self.db.next_attack_at = now + COMBAT_INTERVAL
            if len(self.db.combatants) == 1 and not self.db.claim_last_activity:
                self.db.claim_last_activity = now
                self.db.last_activity = now
        player.schedule_combat()
        self.schedule_combat()

    def remove_combatant(self, player):
        self.db.combatants = [identity for identity in self.db.combatants if identity != player.id]
        threat = deserialize(self.db.threat)
        threat.pop(player.id, None)
        self.db.threat = threat
        contribution = deserialize(self.db.contribution)
        contribution.pop(player.id, None)
        self.db.contribution = contribution
        if not self.db.combatants:
            self.db.claim = None
            self.db.claim_last_activity = 0
            after_change(self.stop_combat_timer)
        after_change(self.schedule_lifecycle)

    def reconcile(self, now=None):
        now = time() if now is None else now
        with world_change():
            if self.db.claim and now - self.db.claim_last_activity >= CLAIM_TIMEOUT_SECONDS:
                for player in self.active_players():
                    player.leave_combat()
                self.db.claim = None
                self.db.claim_last_activity = 0
            active = self.active_players()
            active_ids = [player.id for player in active]
            for identity in list(self.db.combatants):
                if identity not in active_ids:
                    player = object_by_id(identity)
                    if player and player.profile().get("combat_target") == self.id:
                        player.leave_combat()
                    elif player:
                        self.remove_combatant(player)
                    else:
                        self.db.combatants = [key for key in self.db.combatants if key != identity]
            if not self.db.combatants:
                self.db.claim = None
                self.db.claim_last_activity = 0
                self.db.threat = {}
            if (
                not self.db.combatants
                and self.db.last_activity
                and now >= self.db.last_activity + ENEMY_RESET_SECONDS
            ):
                if self.db.state == "alive":
                    self.db.hp = self.db.max_hp
                    self.db.enemy_round = 0
                    self.db.next_attack_at = 0
                    self.db.threat = {}
                    self.db.contribution = {}
                    self.db.last_activity = 0
            if self.db.state == "respawning" and self.db.respawn_at <= now:
                self.db.state = "alive"
                self.db.hp = self.db.max_hp
                self.db.respawn_at = None
                self.db.enemy_round = 0
                self.db.next_attack_at = 0
                self.db.last_activity = 0
                self.db.contribution = {}
                self.db.threat = {}
        after_change(self.schedule_lifecycle)

    def receive_attack(self, player, now=None, rng=None):
        now = time() if now is None else now
        with world_change():
            self.reconcile(now)
            if self.db.state != "alive" or player not in self.active_players():
                player.leave_combat()
                return
            profile = player.profile()
            if now < profile["next_attack_at"]:
                return
            damage, message = rules.player_attack(
                profile, self.db.enemy_id, now, COMBAT_INTERVAL, rng
            )
            damage = min(self.db.hp, damage)
            self.db.hp -= damage
            rules.train_proficiency(
                profile, "weapon", damage, ENEMIES[self.db.enemy_id]["training_cap"]
            )
            self.db.last_activity = now
            self.db.claim_last_activity = now
            threat = deserialize(self.db.threat)
            threat[player.id] = threat.get(player.id, 0) + damage
            self.db.threat = threat
            contribution = deserialize(self.db.contribution)
            previous = contribution.get(player.id, {"damage": 0})
            contribution[player.id] = {
                "damage": previous["damage"] + damage,
                "last_action_at": now,
                "group": self.group_for(player),
            }
            self.db.contribution = contribution
            player.save_profile(profile)
            after_change(lambda: player.msg(message))
            if self.db.hp <= 0:
                self.finish_death(player, now, rng)
        self.broadcast_state()

    def finish_death(self, killer, now, rng=None):
        with world_change():
            return self._finish_death(now, rng)

    def _finish_death(self, now, rng=None):
        from typeclasses.loot import Corpse

        if self.db.state != "alive" or self.db.hp > 0:
            return
        groups = self.reward_groups(now)
        self.db.state = "respawning"
        self.db.respawn_at = now + CORPSE_TTL_SECONDS + RESPAWN_DELAY_SECONDS
        definition = ENEMIES[self.db.enemy_id]
        for identity, share in rules.reward_shares(
            definition["xp"], definition["credits"], groups
        ).items():
            player = object_by_id(identity)
            profile = player.profile()
            rules.gain_xp(profile, share["xp"])
            profile["credits"] += share["credits"]
            profile["kills"] += 1
            if definition.get("boss"):
                profile["boss_defeated"] = True
            player.save_profile(profile)
            message = f"처치 보상: 경험치 +{share['xp']} · 크레딧 +{share['credits']}"
            after_change(lambda player=player, message=message: player.msg(message))
        Corpse.from_enemy(self, groups, now, rng)
        for player in self.active_players():
            player.leave_combat()
        after_change(self.stop_combat_timer)
        after_change(self.schedule_lifecycle)

    def enemy_tick(self, now=None, rng=None):
        now = time() if now is None else now
        with world_change():
            self.reconcile(now)
            players = self.active_players()
            if self.db.state != "alive" or not players or now < self.db.next_attack_at:
                return
            target = min(players, key=lambda player: (-self.db.threat.get(player.id, 0), player.id))
            self.db.enemy_round += 1
            self.db.next_attack_at = now + COMBAT_INTERVAL
            result_profile = target.profile()
            result = rules.enemy_attack(
                result_profile, self.db.enemy_id, self.db.enemy_round, now, rng
            )
            target.save_profile(result_profile)
            target.msg(
                f"{self.key}{'의 돌진' if result['charged'] else ''}: {result['damage']} 피해."
            )
            if result["defeated"]:
                target.leave_combat()
                target.move_to(target.home, quiet=True)
                target.msg("탐사대가 부두로 구조했습니다. 최대 10크레딧을 잃었습니다.")
            if ENEMIES[self.db.enemy_id].get("boss") and self.db.enemy_round % 3 == 2:
                for player in self.active_players():
                    player.msg("우두머리가 몸을 낮춘다. 다음 돌진에 대비하세요!")
        self.broadcast_state()

    def schedule_combat(self):
        if self.db.state == "alive" and self.active_players() and not self.ndb.combat_task:
            self.ndb.combat_task = delay(
                max(0.05, self.db.next_attack_at - time()), self.combat_tick
            )

    def combat_tick(self):
        self.ndb.combat_task = None
        self.enemy_tick()
        self.schedule_combat()

    def stop_combat_timer(self):
        task = self.ndb.combat_task
        self.ndb.combat_task = None
        if task:
            task.remove()

    def schedule_lifecycle(self):
        deadline = (
            self.db.respawn_at
            if self.db.state == "respawning"
            else self.db.last_activity + ENEMY_RESET_SECONDS
            if not self.db.combatants and self.db.last_activity
            else None
        )
        if deadline and not self.ndb.lifecycle_task:
            self.ndb.lifecycle_task = delay(max(0.05, deadline - time()), self.lifecycle_tick)

    def lifecycle_tick(self):
        self.ndb.lifecycle_task = None
        self.reconcile()
        self.broadcast_state()

    def broadcast_state(self):
        if self.location:
            for obj in self.location.contents:
                if hasattr(obj, "push_state"):
                    obj.push_state()


def room_enemies(room, alive_only=True):
    if not room:
        return []
    return [
        obj
        for obj in room.contents
        if obj.is_typeclass(Enemy, exact=True) and (not alive_only or obj.db.state == "alive")
    ]
