"""공유 교전과 전투 정산을 실행하는 전투 참가 객체의 동작."""

from time import time

from evennia.utils import delay
from evennia.utils.dbserialize import deserialize

from world import presentation as view
from world import recovery, rules
from world import text as ft
from world.currency import format_currency
from world.multiplayer import (
    CLAIM_TIMEOUT_SECONDS,
    COMBAT_INTERVAL,
    CORPSE_TTL_SECONDS,
    ENEMY_RECOVERY_DELAY_SECONDS,
    PARTICIPATION_TIMEOUT_SECONDS,
    RESPAWN_DELAY_SECONDS,
    _run_post_commit,
    after_change,
    object_by_id,
    world_change,
)


def deliver_combat_message(recipient, message):
    from world.actions.effects import deliver_read_only

    after_change(lambda: _run_post_commit(lambda: deliver_read_only(lambda: recipient.msg(message))))


class SharedCombatMixin:
    def initialize_shared_combat(self):
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
        self.db.suppressions = {}

    def at_post_move(self, source_location, **kwargs):
        super().at_post_move(source_location, **kwargs)
        if not self.supports_shared_combat:
            return
        with world_change(isolate_callbacks=True):
            for identity in list(self.db.combatants or []):
                player = object_by_id(identity)
                if player and player.profile().get("combat_target") == self.id:
                    player.leave_combat()
            self.db.suppressions = {}
            self.reconcile()

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
        return self.shared_combat_active and (
            self.combat_profile["combat_mode"] == "public"
            or self.db.claim in (None, self.group_for(player))
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
            if self.combat_profile["combat_mode"] == "claimed" and group != self.db.claim:
                continue
            groups.setdefault(group, {})[player.id] = entry["damage"]
        return groups

    def scale_boss(self, now):
        definition = self.combat_profile
        if not definition.get("boss"):
            return
        from world.loot_rules import boss_hp

        participants = sum(len(group) for group in self.reward_groups(now).values())
        count = max(self.db.scaling_participants or 1, participants)
        maximum = boss_hp(definition["hp"], count)
        self.hp += max(0, maximum - self.max_hp)
        self.max_hp = maximum
        self.db.scaling_participants = count

    def engage(self, player, now=None):
        now = time() if now is None else now
        with world_change(isolate_callbacks=True):
            self.reconcile(now)
            if self.db.state != "alive":
                raise rules.RuleError("아직 다시 나타나지 않은 적입니다.")
            if not self.shared_combat_active or player.location != self.location or not player.sessions.count():
                raise rules.RuleError("현재 전투에 참가할 수 없습니다.")
            profile = player.profile()
            from world.observation import can_perceive, context_for

            if profile.get("combat_target") != self.id and not can_perceive(self, context_for(player, observed_at=now)):
                raise rules.RuleError("지금은 그 상대를 식별할 수 없습니다. 광원을 사용하세요.")
            if profile.get("combat_target") not in (None, self.id):
                raise rules.RuleError("현재 상대에게서 먼저 도망하세요.")
            if not self.can_attack(player):
                owner = "다른 일행" if str(self.db.claim).startswith("party:") else "다른 탐사자"
                raise rules.RuleError(
                    f"{self.key}{ft.particle(self.key, '은/는')} {owner}와 교전 중입니다."
                )
            if self.combat_profile["combat_mode"] == "claimed" and not self.db.claim:
                self.db.claim = self.group_for(player)
            if player.id not in self.db.combatants:
                player.accrue_recovery(profile, now)
                self.db.combatants = [*self.db.combatants, player.id]
                from world.combat_contracts import begin_encounter

                encounter = dict(self.db.encounter_state or {})
                if encounter.get("state") == "active":
                    encounter["participants"] = tuple(dict.fromkeys((*encounter["participants"], str(player.pk))))
                    self.db.encounter_state = encounter
                else:
                    begin_encounter(self, (self, player))
                profile.update(
                    combat_target=self.id,
                    queued_action="attack",
                    next_attack_at=max(profile["next_attack_at"], now + COMBAT_INTERVAL),
                )
                player.save_profile(profile)
                self.db.recovery_ready_at = None
                if not self.db.next_attack_at:
                    self.db.next_attack_at = now + COMBAT_INTERVAL
                    self._reserve_tick(self.db.combat_generation, self.db.next_attack_at)
            if len(self.db.combatants) == 1 and not self.db.claim_last_activity:
                self.db.claim_last_activity = now
                self.db.last_activity = now
        after_change(player.schedule_combat)
        after_change(self.schedule_combat)

    def _end_abandoned_encounter(self):
        state = self.db.encounter_state or {}
        if self.db.state != "alive" or self.hp <= 0 or state.get("state") != "active":
            return
        from world.combat_contracts import Encounter, settle_encounter

        settle_encounter(Encounter(self, state["generation"]), {"kind": "disengaged"}, lambda _: None)
        self.db.next_attack_at = 0

    def remove_combatant(self, player, now=None):
        now = time() if now is None else now
        self.db.combatants = [identity for identity in self.db.combatants if identity != player.id]
        threat = deserialize(self.db.threat)
        threat.pop(player.id, None)
        self.db.threat = threat
        contribution = deserialize(self.db.contribution)
        contribution.pop(player.id, None)
        self.db.contribution = contribution
        if not self.db.combatants:
            self._end_abandoned_encounter()
            self.db.suppressions = {}
            self.db.recovery_ready_at = now + ENEMY_RECOVERY_DELAY_SECONDS
            state = deserialize(self.db.recovery) or recovery.initialize(now)
            # 재교전 중의 시간은 회복량에 더하지 않고 앞 구간의 소수 기여는 보존한다.
            recovery.accrue(state, now, {})
            self.db.recovery = state
            self.db.claim = None
            self.db.claim_last_activity = 0
            after_change(self.stop_combat_timer)
        after_change(self.schedule_lifecycle)

    def reconcile(self, now=None):
        now = time() if now is None else now
        with world_change(isolate_callbacks=True):
            # The old unowned effect cannot be assigned to a source safely.
            self.attributes.remove("suppression")
            if self.db.claim and now - self.db.claim_last_activity >= CLAIM_TIMEOUT_SECONDS:
                for player in self.active_players():
                    player.leave_combat(now=now)
                self.db.claim = None
                self.db.claim_last_activity = 0
            active = self.active_players() if self.shared_combat_active else []
            active_ids = [player.id for player in active]
            for identity in list(self.db.combatants):
                if identity not in active_ids:
                    player = object_by_id(identity)
                    if player and player.profile().get("combat_target") == self.id:
                        player.leave_combat(now=now)
                    elif player:
                        self.remove_combatant(player, now=now)
                    else:
                        self.db.combatants = [key for key in self.db.combatants if key != identity]
            if not self.db.combatants:
                self._end_abandoned_encounter()
                self.db.suppressions = {}
                self.db.claim = None
                self.db.claim_last_activity = 0
                self.db.threat = {}
                if self.db.state == "alive" and self.db.last_activity and self.db.recovery is None:
                    self.db.recovery = recovery.initialize(self.db.last_activity)
                    self.db.recovery_ready_at = self.db.last_activity + ENEMY_RECOVERY_DELAY_SECONDS
            if (
                not self.db.combatants
                and self.db.last_activity
                and now >= (self.db.recovery_ready_at or self.db.last_activity + ENEMY_RECOVERY_DELAY_SECONDS)
            ):
                if self.db.state == "alive":
                    self.db.enemy_round = 0
                    self.db.next_attack_at = 0
                    self.db.threat = {}
                    self.db.contribution = {}
                    self.db.last_activity = 0
            if self.db.state == "alive" and not self.db.combatants and 0 < self.hp < self.max_hp:
                state = deserialize(self.db.recovery)
                ready_at = self.db.recovery_ready_at
                if state is None:
                    start = self.db.last_activity or now
                    state = recovery.initialize(start)
                    ready_at = start + ENEMY_RECOVERY_DELAY_SECONDS
                    self.db.recovery_ready_at = ready_at
                recovery.accrue(state, now, {}, [{"started_at": ready_at or now,
                    "expires_at": max(now, ready_at or now) + 1,
                    "hp_per_minute": recovery.enemy_rate(self.max_hp)}])
                resources = {"hp": self.hp, "mental": 0, "recovery": state}
                recovery.commit(resources, {"max_hp": self.max_hp, "max_mental": 0})
                self.hp = resources["hp"]
                self.db.recovery = state
            if self.db.state == "alive" and not self.db.combatants and not self.db.contribution and self.hp == self.max_hp:
                self.db.scaling_participants = 1
                self.max_hp = self.combat_profile["hp"]
                self.hp = self.max_hp
            if self.db.state == "respawning" and self.db.respawn_at <= now:
                self.db.suppressions = {}
                self.db.state = "alive"
                self.db.scaling_participants = 1
                self.max_hp = self.combat_profile["hp"]
                self.hp = self.max_hp
                self.db.respawn_at = None
                self.db.enemy_round = 0
                self.db.next_attack_at = 0
                self.db.last_activity = 0
                self.db.contribution = {}
                self.db.threat = {}
                self.db.recovery = None
                self.db.recovery_ready_at = None
        after_change(self.schedule_lifecycle)

    def receive_attack(self, player, now=None, rng=None):
        now = time() if now is None else now
        with world_change(isolate_callbacks=True):
            self.reconcile(now)
            if not self.shared_combat_active or player not in self.active_players():
                player.leave_combat()
                return
            profile = player.profile()
            if now < profile["next_attack_at"]:
                return
            player.accrue_recovery(profile, now)
            recipient = player
            recipient_profile = None
            error = None
            if profile["queued_action"] == "heal":
                from world.skill_services import heal_target

                try:
                    recipient = heal_target(player, profile.get("heal_target"))
                    if recipient is not player:
                        recipient_profile = recipient.profile()
                        recipient.accrue_recovery(recipient_profile, now)
                except rules.RuleError as failure:
                    error = str(failure)
            if error:
                profile.update(queued_action="attack", next_attack_at=now + COMBAT_INTERVAL)
                profile["player_round"] += 1
                damage, outcome = 0, {"action": "error", "message": error}
            else:
                from world.firearm_service import player_attack

                damage, outcome = player_attack(
                    player, profile, self.combat_definition_id, now, COMBAT_INTERVAL, rng, recipient_profile
                )
            profile["heal_target"] = None
            if recipient_profile is not None and outcome["action"] == "heal":
                recipient.save_profile(recipient_profile)
                outcome["recipient"] = recipient.key
                deliver_combat_message(recipient, f"{player.key}의 치료로 HP {outcome['amount']}을 회복했다.")
            # 현재 공격의 기여를 먼저 등록해 late join의 증가분도 사망 판정 전에 적용한다.
            contribution = deserialize(self.db.contribution)
            previous = contribution.get(player.id, {"damage": 0})
            contribution[player.id] = {"damage": previous["damage"] + damage,
                                       "last_action_at": now, "group": self.group_for(player)}
            self.db.contribution = contribution
            self.scale_boss(now)
            actual = min(self.hp, damage)
            contribution[player.id]["damage"] = previous["damage"] + actual
            self.db.contribution = contribution
            damage = actual
            self.hp -= damage
            if "suppression" in outcome:
                from world.progression import apply_suppression

                effects, status = apply_suppression(
                    deserialize(self.db.suppressions), player.id, outcome["suppression"]["rank"],
                    bool(self.combat_profile.get("boss")), effect=outcome["suppression"],
                )
                self.db.suppressions = effects
                outcome["suppression"] = effects[str(player.id)]
                outcome["suppression_status"] = status
            self.db.last_activity = now
            self.db.claim_last_activity = now
            threat = deserialize(self.db.threat)
            threat[player.id] = threat.get(player.id, 0) + damage
            self.db.threat = threat
            player.save_profile(profile)
            message = view.outgoing_attack(profile, self.key, outcome, damage)
            deliver_combat_message(player, message)
            if self.hp <= 0:
                self.finish_death(player, now, rng)
        after_change(self.broadcast_state)

    def finish_death(self, killer, now, rng=None):
        with world_change(isolate_callbacks=True):
            return self._finish_death(now, rng)

    def _finish_death(self, now, rng=None):
        if self.db.state != "alive" or self.hp > 0:
            return
        from world.combat_contracts import Encounter, begin_encounter, settle_encounter

        state = self.db.encounter_state or {}
        encounter = (Encounter(self, state["generation"]) if state.get("state") == "active"
                     else begin_encounter(self, (self, *self.active_players())))
        return settle_encounter(encounter, {"kind": "death"}, lambda _: self._settle_death(now, rng))

    def _settle_death(self, now, rng):
        from typeclasses.loot import Corpse

        groups = self.reward_groups(now)
        fallen = ft.text(
            ft.named("hostile", self.key, "이/가"), " 더는 버티지 못하고 바닥에 쓰러졌다."
        )
        for participant in self.active_players():
            deliver_combat_message(participant, fallen)
        self.db.state = "respawning"
        self.db.suppressions = {}
        self.db.respawn_at = now + CORPSE_TTL_SECONDS + RESPAWN_DELAY_SECONDS
        definition = self.combat_profile
        for identity, xp in rules.reward_allocation(
            definition["xp"], groups
        ).items():
            player = object_by_id(identity)
            profile = player.profile()
            player.accrue_recovery(profile, now)
            rules.gain_xp(profile, xp)
            profile["kills"] += 1
            if definition.get("boss_quest"):
                profile["quests"][definition["boss_quest"]]["boss_defeated"] = True
            player.save_profile(profile)
            message = view.reward(xp)
            deliver_combat_message(player, message)
        Corpse.from_enemy(self, groups, now, rng)
        for player in self.active_players():
            player.leave_combat(now=now)
        after_change(self.stop_combat_timer)
        after_change(self.schedule_lifecycle)

    def enemy_tick(self, now=None, rng=None):
        now = time() if now is None else now
        with world_change(isolate_callbacks=True):
            self.reconcile(now)
            players = self.active_players()
            if not self.shared_combat_active or not players or now < self.db.next_attack_at:
                return
            target = min(players, key=lambda player: (-self.db.threat.get(player.id, 0), player.id))
            from typeclasses.parties import party_for
            party = party_for(target)
            if party:
                target = party.defense_target(self, target, players)
            self.db.enemy_round += 1
            self.db.next_attack_at = now + COMBAT_INTERVAL
            result_profile = target.profile()
            target.accrue_recovery(result_profile, now)
            from world.progression import combined_suppression, consume_suppressions

            effects = deserialize(self.db.suppressions)
            reduction = combined_suppression(effects, bool(self.combat_profile.get("boss")))
            self.db.suppressions = consume_suppressions(effects)
            result = rules.enemy_attack(
                result_profile, self.combat_definition_id, self.db.enemy_round, now, rng, reduction
            )
            lost = rules.apply_defeat(result_profile) if result["defeated"] else 0
            target.save_profile(result_profile)
            message = ft.text(
                ft.named("hostile", self.key, "이/가"),
                f" {self.combat_profile.get('special_verb', '거세게 돌진해')} "
                if result["charged"] else " 달려들어 ",
                f"{result['damage']}의 피해를 입혔다.",
            )
            deliver_combat_message(target, message)
            if result["defeated"]:
                from world.bootstrap import get_room

                target.leave_combat(now=now)
                destination = get_room("infirmary")
                rescue = (
                    "탐사대가 본부 3층 의무실로 구조했습니다.\n"
                    + (f"{format_currency(lost)}을 잃었습니다.\n" if lost else "")
                    + f"응급 처치로 체력 {rules.DEFEAT_RECOVERY_HP}을 회복했습니다. 추가 회복이 필요합니다."
                )
                deliver_combat_message(target, rescue)
                if destination is None or not target.move_to(destination, quiet=True, move_type="defeat"):
                    raise RuntimeError("패배 후 의무실 이동을 완료하지 못했습니다.")
                after_change(target.request_prompt)
            if rules.boss_telegraph(self.combat_definition_id, self.db.enemy_round):
                for player in self.active_players():
                    message = ft.text(
                        ft.token("warning", "! "),
                        ft.named("hostile", self.key, "이/가"),
                        " ",
                        self.combat_profile.get("telegraph", "몸을 낮추고 돌진할 자세를 취한다."),
                    )
                    deliver_combat_message(player, message)
        after_change(self.broadcast_state)

    def schedule_combat(self):
        if not self.shared_combat_active or not self.active_players() or self.ndb.combat_task:
            return
        generation = self.db.combat_generation
        if generation is None:
            return
        from world.combat_contracts import Encounter

        encounter = Encounter(self, generation)
        pending = encounter.state.get("pending")
        if pending and not pending["completed"]:
            self._schedule_reserved_tick(encounter, pending["operation_id"], pending["due_at"])

    def _reserve_tick(self, generation, due_at):
        from world.combat_contracts import Encounter, plan_tick

        plan_tick(Encounter(self, generation), operation_id=f"tick:{due_at}", due_at=due_at,
                  trigger=self._schedule_reserved_tick)

    def _schedule_reserved_tick(self, encounter, operation_id, due_at):
        state = self.db.encounter_state or {}
        pending = state.get("pending") or {}
        if (state.get("state") == "active" and state.get("generation") == encounter.generation
                and pending.get("operation_id") == operation_id and not pending.get("completed")
                and pending.get("due_at") == due_at == self.db.next_attack_at
                and self.shared_combat_active and not self.ndb.combat_task):
            self._schedule_tick(encounter.generation, due_at)

    def _schedule_tick(self, generation, due_at):
        self.ndb.combat_task = delay(max(0.05, due_at - time()), self.combat_tick, generation, due_at)

    def combat_tick(self, generation, due_at):
        if generation is None or generation != self.db.combat_generation or due_at != self.db.next_attack_at:
            return
        self.ndb.combat_task = None
        now = time()
        if now >= due_at:
            from world.combat_contracts import Encounter, apply_tick
            from world.domain_context import combat_timer_context

            encounter = Encounter(self, generation)
            context = combat_timer_context(
                self, operation_id=f"tick:{due_at}", domain_scope=encounter.identity,
                generation=generation, clock=lambda: now,
            )
            with world_change(isolate_callbacks=True):
                apply_tick(encounter, context, lambda _: self.enemy_tick(now=now))
                deadline = self.db.next_attack_at
                if self.shared_combat_active and self.active_players() and deadline > now:
                    self._reserve_tick(generation, deadline)
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
            else recovery.next_boundary(max(time(), self.db.recovery_ready_at or time()))
            if not self.db.combatants and self.db.state == "alive" and 0 < self.hp < self.max_hp
            and self.location and any(getattr(obj, "push_state", None) and obj.sessions.count()
                                      for obj in self.location.contents)
            else None
        )
        reservation = (self.db.combat_generation, deadline) if deadline else None
        if self.ndb.lifecycle_task and self.ndb.lifecycle_reservation != reservation:
            self.ndb.lifecycle_task.remove()
            self.ndb.lifecycle_task = None
            self.ndb.lifecycle_reservation = None
        if reservation and not self.ndb.lifecycle_task:
            self.ndb.lifecycle_reservation = reservation
            self.ndb.lifecycle_task = delay(
                max(0.05, deadline - time()), self.lifecycle_tick, *reservation,
            )

    def lifecycle_tick(self, generation, deadline):
        if self.ndb.lifecycle_reservation != (generation, deadline):
            return
        self.ndb.lifecycle_task = None
        self.ndb.lifecycle_reservation = None
        if self.db.combat_generation != generation:
            self.schedule_lifecycle()
            return
        self.reconcile()
        self.broadcast_state()

    def broadcast_state(self):
        if self.location:
            for obj in self.location.contents:
                if hasattr(obj, "push_state"):
                    _run_post_commit(obj.push_state)


def room_enemies(room, alive_only=True):
    from typeclasses.actors import Actor

    from world.targets import ordered

    if not room:
        return []
    return ordered(
        [
            obj
            for obj in room.contents
            if isinstance(obj, Actor) and obj.supports_shared_combat and (not alive_only or obj.shared_combat_active)
        ]
    )
