"""대련의 독점권, 격리 정산과 영속 기한을 실제 Actor와 SQLite에서 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from random import Random
from threading import Barrier
from unittest.mock import patch

from django.db import connections
from django.test import TransactionTestCase
from evennia import create_object
from evennia.objects.objects import DefaultRoom
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse, DroppedLoot
from world import duel, equipment_service, firearm_service, rules
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.global_actions import DUEL_SKILLS
from world.actions.manifest import get_index
from world.actions.presentation import action_controls, reference_json
from world.actions.registry import compile_manifest
from world.actions.resolver import dispatch_text
from world.actions.schema import PackageManifest
from world.actors import content
from world.bootstrap import CATEGORY
from world.multiplayer import COMBAT_INTERVAL
from world.selection_numbers.api import descriptor, number_for

from tests.base import clear_test_caches
from tests.duel_fixture import (
    GUARD_ID,
    INSTRUCTOR_ID,
    INTERACTION,
    INTERACTION_ID,
    PACKAGE,
    registry_overlay,
    spawn_fixture,
)
from tests.item_entity_fixture import NativeItemTest


class ExclusiveDuelTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.enterContext(registry_overlay())
        self.enterContext(patch.object(content, "CAPABILITIES", {**content.CAPABILITIES, "interaction": INTERACTION}))
        self.room1.db.zone_id = "training_room"
        self.room1.tags.add("training_room", category=CATEGORY)
        self.actor = spawn_fixture(INSTRUCTOR_ID, self.room1)
        self.sessions = {player.pk: self.connect_character(player) for player in (self.char1, self.char2)}
        self.enterContext(patch("world.duel.delay"))
        self.enterContext(patch("world.shared_combat.delay"))

    def projection(self, now=100, viewer=None):
        return duel.projection(self.actor, viewer or self.char1, now=now)

    def start(self, now=100):
        return duel.start(self.actor, self.char1, now=now)

    def step(self, identity, due_at, *, now=None, seed=1):
        return duel.tick(self.actor, identity, due_at, now=due_at if now is None else now, rng=Random(seed))

    def test_exclusive_start_observation_scope_and_public_npc_policy(self):
        with patch.object(self.char1, "msg") as output:
            identity = self.start()
        self.assertIn("대련을 시작합니다. 최대 10분이며, 자동 공격과 별도로 60초마다 전투 행동을 입력해야 합니다.",
                      [call.args[0] for call in output.call_args_list if call.args])
        self.assertTrue(duel.active_on(self.actor))
        self.assertEqual(self.projection()["identity"], identity)
        self.assertEqual(self.projection()["ends_at"], 700)
        self.assertEqual(self.projection()["idle_at"], 160)
        observer = self.projection(viewer=self.char2)
        self.assertFalse(observer["participant"])
        for action in (
            lambda: duel.start(self.actor, self.char2, now=101),
            lambda: duel.act(self.actor, self.char2, identity, now=101),
            lambda: duel.surrender(self.actor, self.char2, identity, now=101),
            lambda: self.actor.engage(self.char2, now=101),
        ):
            with self.assertRaises(rules.RuleError):
                action()
        self.assertTrue(duel.active_on(self.actor))
        self.char1.location = self.room2
        with self.assertRaises(rules.RuleError):
            duel.act(self.actor, self.char1, identity, now=102)
        self.assertTrue(all("duel" not in definition.capabilities for actor_id, definition in content.ACTORS.items()
                            if actor_id not in {INSTRUCTOR_ID, GUARD_ID}))

    def test_declared_combat_profile_supports_shared_rounds(self):
        guard = spawn_fixture(GUARD_ID, self.room1)
        for actor in (self.actor, guard):
            with self.subTest(actor=actor.key):
                actor.engage(self.char1, now=100)
                actor.receive_attack(self.char1, now=103, rng=Random(1))
                actor.enemy_tick(now=103, rng=Random(1))
                self.assertEqual(actor.db.enemy_round, 1)
                self.assertEqual(self.char1.combat_snapshot()["enemy"], actor.actor_id)
                self.char1.leave_combat(now=104)

    def test_shared_encounter_excludes_duel(self):
        self.actor.engage(self.char1, now=100)
        before = deepcopy(dict(self.actor.db.encounter_state))
        with self.assertRaises(rules.RuleError):
            duel.start(self.actor, self.char2, now=101)
        self.assertEqual(dict(self.actor.db.encounter_state), before)
        self.assertFalse(duel.active_on(self.actor))

    def test_nonlethal_combat_does_not_write_shared_hp_or_rewards(self):
        previous_actor_hp = self.actor.hp
        before = deepcopy(self.char1.profile())
        corpses = Corpse.objects.count()
        loot = DroppedLoot.objects.count()
        identity = self.start()
        for turn in range(1, 16):
            self.step(identity, 100 + COMBAT_INTERVAL * turn)
            if not duel.active_on(self.actor):
                break
        self.assertFalse(duel.active_on(self.actor))
        result = self.projection(150)["final_result"]
        self.assertIn(result["kind"], {"victory", "defeat"})
        self.assertEqual(self.actor.hp, previous_actor_hp)
        self.assertEqual(Corpse.objects.count(), corpses)
        self.assertEqual(DroppedLoot.objects.count(), loot)
        after = self.char1.profile()
        for field in ("hp", "credits", "xp", "kills", "quests"):
            self.assertEqual(after[field], before[field], field)
        self.assertIsNone(self.actor.db.encounter_state)
        self.assertIsNone(self.char1.combat_target())
        self.step(identity, 100 + COMBAT_INTERVAL, now=151)
        self.assertEqual(self.projection(151)["final_result"], result)

    def test_lethal_duel_round_commits_victory_and_defeat_with_typed_result(self):
        for index, (hp_field, kind) in enumerate((("actor_hp", "victory"), ("player_hp", "defeat"))):
            with self.subTest(kind=kind):
                now = 100 + index * 40
                identity = self.start(now)
                self.actor.db.duel_state = {**self.actor.db.duel_state, hp_field: 1}
                due_at = now + COMBAT_INTERVAL
                with patch.object(self.char1, "msg") as deliver:
                    self.assertTrue(self.step(identity, due_at))
                messages = [call.args[0] for call in deliver.call_args_list if call.args]
                self.assertIn(f"대련이 끝났습니다. {'승리' if kind == 'victory' else '패배'}.", messages)
                if kind == "victory":
                    self.assertTrue(any("상대의 대련 체력에 1 피해를 입혔다." in str(msg) for msg in messages))
                else:
                    self.assertTrue(any("대련 체력이 1 감소했다." in str(msg) for msg in messages))
                state = dict(self.actor.db.duel_state)
                self.assertEqual(state["final_result"], {"kind": kind, "reason": None, "finished_at": due_at})
                self.assertTrue(state["settled"])
                self.assertIsNone(state["pending"])
                self.assertFalse(self.step(identity, due_at))
                self.assertEqual(dict(self.actor.db.duel_state), state)

    def test_equipment_and_normal_costs_are_not_reverted(self):
        gun = firearm_service.create_firearm("test_pistol", owner_object=self.char1, mode="full_standard")
        equipment_service.equip_item(self.char1, gun)
        equipment_service.set_active_weapon(self.char1, gun)
        rounds = firearm_service.loaded_magazine_item(gun).state["rounds"]
        identity = self.start()
        duel.act(self.actor, self.char1, identity, skill="shooting", now=101)
        self.step(identity, 100 + COMBAT_INTERVAL)
        self.assertLess(firearm_service.loaded_magazine_item(gun).state["rounds"], rounds)
        mental = self.char1.profile()["mental"]
        self.assertLess(mental, 20)
        if duel.active_on(self.actor):
            duel.surrender(self.actor, self.char1, identity, now=103)
        self.assertEqual(firearm_service.loaded_magazine_item(gun).state["rounds"], rounds - 1)
        self.assertEqual(self.char1.profile()["mental"], mental)

    def test_general_support_and_native_bandage_refused_without_duel_changes(self):
        bandage = self.create("bandage", quantity=2)
        index = get_index()
        button = next(control["action"] for control in action_controls(self.char1, index)
                      if control["action"]["action_id"] == "item.bandage.use"
                      and control["action"]["roles"]["provider"][0]["identity"] == str(bandage.pk))
        self.char1.change(lambda profile: profile.update(mental=12))
        self.start()
        before = self.atomic_state()
        encounter = deepcopy(dict(self.actor.db.duel_state))
        with (patch("world.skill_services.time", return_value=101),
              patch.object(self.char1, "msg") as output):
            for command in ("호흡", "치료", "붕대 사용"):
                with self.subTest(command=command):
                    output.reset_mock()
                    self.char1.execute_cmd(command)
                    self.assertIn("대련", str(output.call_args_list))
                    self.assertEqual(self.atomic_state(), before)
                    self.assertEqual(dict(self.actor.db.duel_state), encounter)
            invocation = from_web({**button, "request_id": "ordinary-bandage-in-duel"}, index)
            result = execute(self.char1, self.sessions[self.char1.pk], invocation, index)
        self.assertEqual(result.status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(dict(self.actor.db.duel_state), encounter)

    def test_duel_bandage_refused_by_domain_text_and_web(self):
        self.assertEqual(set(duel.SKILLS), set(DUEL_SKILLS.values()))
        bandage = self.create("bandage", quantity=2)
        identity = self.start()
        before = self.atomic_state()
        encounter = deepcopy(dict(self.actor.db.duel_state))
        with self.assertRaisesRegex(rules.RuleError, "지원하지 않는 대련 행동"):
            duel.act(self.actor, self.char1, identity, skill="bandage", now=101)
        with patch.object(self.char1, "msg") as output, patch("world.duel.time", return_value=101):
            self.char1.execute_cmd(f"{self.actor.key} / 붕대 대련행동")
        self.assertIn("행동 인자", str(output.call_args_list))
        with self.assertRaises(rules.RuleError):
            from_web({
                "action_id": "global.duel_act",
                "variant": "adapter",
                "roles": {"subject": [reference_json(descriptor(self.actor).reference)]},
                "arguments": {"encounter_id": identity, "skill": "bandage"},
                "request_id": "duel-bandage-unsupported",
            }, get_index())
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(dict(self.actor.db.duel_state), encounter)
        duel.surrender(self.actor, self.char1, identity, now=102)
        bandage.refresh_from_db()
        self.assertEqual(bandage.quantity, 2)

    def test_duel_support_uses_a_round_and_commits_cost_once(self):
        self.char1.change(lambda profile: profile.update(mental=12))
        identity = self.start()
        self.actor.db.duel_state = {**self.actor.db.duel_state, "player_hp": 30}
        public_hp = self.char1.profile()["hp"]
        actor_hp = self.projection()["actor_hp"]
        with patch("world.duel.time", return_value=101):
            self.char1.execute_cmd(f"{self.actor.key} / 치료 대련행동")
        self.assertEqual(self.projection(101)["idle_at"], 161)
        self.assertEqual(self.char1.profile()["mental"], 12)
        due = 100 + COMBAT_INTERVAL
        with patch.object(self.char1, "msg") as output:
            self.assertTrue(self.step(identity, due))
        segments = [segment for call in output.call_args_list if call.args
                    for segment in getattr(call.args[0], "segments", ())]
        healed = next(int(segment["text"]) for segment in segments if segment["role"] == "hp_recovered")
        damage = next(int(segment["text"]) for segment in segments if segment["role"] == "damage_taken")
        self.assertGreater(healed, 0)
        self.assertEqual(self.projection(due)["player_hp"], 30 + healed - damage)
        self.assertEqual(self.char1.profile()["hp"], public_hp)
        self.assertEqual(self.char1.profile()["mental"], 2)
        self.assertEqual(self.char1.profile()["skill_ready_at"]["heal"], due + 10)
        self.assertEqual(self.projection(due)["actor_hp"], actor_hp)
        self.assertEqual(self.projection(due)["idle_at"], 161)
        before = self.atomic_state()
        encounter = deepcopy(dict(self.actor.db.duel_state))
        self.assertFalse(self.step(identity, due))
        with self.assertRaises(rules.RuleError):
            duel.act(self.actor, self.char1, identity, skill="heal", now=103)
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(dict(self.actor.db.duel_state), encounter)

        index = get_index()
        invocation = from_web({
            "action_id": "global.duel_act",
            "variant": "adapter",
            "roles": {"subject": [reference_json(descriptor(self.actor).reference)]},
            "arguments": {"encounter_id": identity, "skill": "breathing"},
            "request_id": "duel-breathing",
        }, index)
        with patch("world.duel.time", return_value=103):
            self.assertEqual(execute(self.char1, self.sessions[self.char2.pk], invocation, index).status,
                             ResultStatus.REFUSED)
            self.assertEqual(self.atomic_state(), before)
            self.assertEqual(dict(self.actor.db.duel_state), encounter)
            self.assertEqual(execute(self.char1, self.sessions[self.char1.pk], invocation, index).status,
                             ResultStatus.SUCCESS)
        self.assertEqual(self.char1.profile()["mental"], 2)
        self.assertEqual(self.projection(103)["idle_at"], 163)
        self.assertTrue(self.step(identity, due + COMBAT_INTERVAL))
        self.assertGreater(self.char1.profile()["mental"], 2)
        self.assertEqual(self.char1.profile()["skill_ready_at"]["breathing"], due + COMBAT_INTERVAL + 30)
        self.assertEqual(self.projection(due + COMBAT_INTERVAL)["idle_at"], 163)
        self.assertEqual(self.projection(due + COMBAT_INTERVAL)["actor_hp"], actor_hp)

    def test_explicit_action_updates_idle_deadline_but_tick_does_not(self):
        identity = self.start()
        self.step(identity, 100 + COMBAT_INTERVAL)
        self.assertEqual(self.projection(103)["idle_at"], 160)
        duel.act(self.actor, self.char1, identity, now=120)
        self.assertEqual(self.projection(120)["idle_at"], 180)
        with self.assertRaises(rules.RuleError):
            duel.act(self.actor, self.char2, identity, now=140)
        self.assertEqual(self.projection(140)["idle_at"], 180)
        duel.reconcile(self.actor, now=179.999)
        self.assertTrue(duel.active_on(self.actor))
        duel.reconcile(self.actor, now=180)
        self.assertEqual(self.projection(180)["final_result"]["kind"], "timeout")

    def test_hard_deadline_is_not_extended_by_explicit_activity(self):
        identity = self.start()
        for now in range(150, 700, 50):
            duel.act(self.actor, self.char1, identity, now=now)
        self.assertEqual(self.projection(699.999)["ends_at"], 700)
        with patch.object(self.char1, "msg") as output:
            duel.reconcile(self.actor, now=700)
        self.assertIn("대련이 끝났습니다. 시간 초과.", [call.args[0] for call in output.call_args_list if call.args])
        self.assertEqual(self.projection(700)["final_result"]["kind"], "timeout")

    def test_surrender_cooldown_and_stale_request_or_tick(self):
        identity = self.start()
        with patch.object(self.char1, "msg") as output:
            duel.surrender(self.actor, self.char1, identity, now=101)
        self.assertIn("대련이 끝났습니다. 기권.", [call.args[0] for call in output.call_args_list if call.args])
        self.assertEqual(self.projection(101)["final_result"]["kind"], "surrender")
        with self.assertRaises(rules.RuleError):
            self.start(130.999)
        following = self.start(131)
        self.assertNotEqual(following, identity)
        before = deepcopy(dict(self.actor.db.duel_state))
        for action in (duel.act, duel.surrender):
            with self.assertRaises(rules.RuleError):
                action(self.actor, self.char1, identity, now=132)
        self.step(identity, 100 + COMBAT_INTERVAL, now=134)
        self.assertEqual(dict(self.actor.db.duel_state), before)

    def test_disconnect_reconnect_and_expiration_at_exact_deadline(self):
        identity = self.start()
        duel.connection_changed(self.char1, now=105, online=False)
        self.assertEqual(self.projection(105)["reconnect_until"], 135)
        duel.connection_changed(self.char1, now=134.999, online=True)
        self.assertTrue(duel.active_on(self.actor))
        self.assertIsNone(self.projection(134.999)["reconnect_until"])
        self.assertEqual(self.projection(134.999)["idle_at"], 160)
        duel.act(self.actor, self.char1, identity, now=134.999)
        duel.connection_changed(self.char1, now=135, online=False)
        with patch.object(self.char1, "msg") as output:
            duel.connection_changed(self.char1, now=165, online=True)
        self.assertIn("대련이 끝났습니다. 연결 유예 만료.", [call.args[0] for call in output.call_args_list if call.args])
        self.assertFalse(duel.active_on(self.actor))
        result = self.projection(165)["final_result"]
        self.assertEqual(result["kind"], "disconnect")
        self.assertEqual(self.projection(166)["identity"], identity)

    def test_stored_character_keeps_duel_during_reconnect_grace(self):
        identity = self.start()
        room = self.actor.location
        duel.connection_changed(self.char1, now=105, online=False)
        self.char1.db.prelogout_location = room
        self.char1.location = None
        with patch.object(self.char1.sessions, "count", return_value=0):
            duel.reconcile(self.actor, now=110, restart=True)
            self.assertEqual(duel.reconnect_room(self.char1, now=110), room)
        self.char1.location = room
        duel.connection_changed(self.char1, now=112, online=True)
        self.assertEqual(self.projection(112)["identity"], identity)
        self.assertIsNone(self.projection(112)["reconnect_until"])

    def test_recovery_without_runtime_timer_leaves_one_effect_and_stable_result(self):
        identity = self.start()
        self.actor.nattributes.clear()
        self.actor.attributes.reset_cache()
        duel.reconcile(self.actor, now=100 + COMBAT_INTERVAL)
        before = deepcopy(dict(self.actor.db.duel_state))
        self.step(identity, 100 + COMBAT_INTERVAL)
        self.assertEqual(dict(self.actor.db.duel_state), before)
        duel.reconcile(self.actor, now=160)
        result = self.projection(160)["final_result"]
        self.actor.nattributes.clear()
        self.actor.attributes.reset_cache()
        duel.reconcile(self.actor, now=161)
        self.assertEqual(self.projection(161)["final_result"], result)

    def test_missing_registration_and_delivery_failure_preserve_committed_start(self):
        with (patch("world.duel._schedule_current", side_effect=RuntimeError("예약 등록 실패")),
              patch.object(self.char1, "msg", side_effect=RuntimeError("전달 실패")),
              patch("world.multiplayer.logger.log_err") as log):
            identity = self.start()
        self.assertGreaterEqual(log.call_count, 2)
        self.assertEqual(self.projection()["identity"], identity)
        self.assertIsNone(self.actor.ndb.duel_task)
        self.actor.attributes.reset_cache()
        duel.reconcile(self.actor, now=101)
        self.assertEqual(self.actor.ndb.duel_task[:2], (identity, 100 + COMBAT_INTERVAL))

    def test_attack_and_result_delivery_failure_does_not_repeat_duel_cost(self):
        identity = self.start()
        duel.act(self.actor, self.char1, identity, skill="heavy", now=101)
        self.actor.db.duel_state = {**self.actor.db.duel_state, "actor_hp": 1}
        before = self.char1.profile()["mental"]
        due = 100 + COMBAT_INTERVAL
        with (patch.object(self.char1, "msg", side_effect=RuntimeError("전달 실패")) as output,
              patch("world.multiplayer.logger.log_err")):
            self.assertTrue(self.step(identity, due))
            self.assertFalse(self.step(identity, due))
        messages = [str(call.args[0]) for call in output.call_args_list if call.args]
        self.assertEqual(sum("상대의 대련 체력에 1 피해" in msg for msg in messages), 1)
        self.assertEqual(messages.count("대련이 끝났습니다. 승리."), 1)
        self.assertLess(self.char1.profile()["mental"], before)
        self.assertEqual(self.char1.profile()["skill_ready_at"]["heavy"], due + 7.5)
        self.assertEqual(self.projection(due)["final_result"]["kind"], "victory")

    def test_restored_numeric_round_renders_without_losing_pending_tick(self):
        identity = self.start()
        self.actor.db.duel_state = {**self.actor.db.duel_state, "enemy_round": 0.0}
        with patch.object(self.char1, "msg") as output:
            self.assertTrue(self.step(identity, 100 + COMBAT_INTERVAL))
        roles = {segment["role"] for call in output.call_args_list if call.args
                 for segment in getattr(call.args[0], "segments", ())}
        self.assertTrue({"damage_dealt", "damage_taken"}.issubset(roles))
        self.assertEqual(self.actor.db.duel_state["enemy_round"], 1.0)

    def test_incomplete_pending_state_aborts_without_resetting_actor(self):
        identity = self.start()
        self.actor.db.fixture_other_domain = "preserved"
        self.actor.db.duel_state = {**self.actor.db.duel_state, "pending": None}
        duel.reconcile(self.actor, now=101)
        before = deepcopy(dict(self.actor.db.duel_state))
        self.assertEqual(before["identity"], identity)
        self.assertTrue(before["settled"])
        self.assertEqual(before["final_result"]["kind"], "abort")
        self.assertFalse(duel.active_for(self.char1))
        self.assertEqual(self.actor.db.fixture_other_domain, "preserved")
        self.assertEqual(self.actor.hp, 24)
        duel.reconcile(self.actor, now=102)
        self.assertEqual(dict(self.actor.db.duel_state), before)

    def test_startup_aborts_offline_duel_without_persisted_disconnect_time(self):
        self.start()
        with patch.object(self.char1.sessions, "count", return_value=0):
            duel.reconcile(self.actor, now=120, restart=True)
        self.assertEqual(self.actor.db.duel_state["final_result"]["reason"], "unknown_disconnect")
        self.assertFalse(duel.active_for(self.char1))

    def test_missing_policy_aborts_and_releases_participant(self):
        self.start()
        state = dict(self.actor.db.duel_state)
        del state["policy"]
        self.actor.db.duel_state = state
        duel.reconcile(self.actor, now=161, restart=True)
        self.assertEqual(self.actor.db.duel_state["final_result"]["kind"], "abort")
        self.assertIsNone(self.char1.db.active_duel_actor)

    def test_missing_reconnect_deadline_aborts_without_breaking_projection(self):
        self.start()
        state = dict(self.actor.db.duel_state)
        del state["reconnect_until"]
        self.actor.db.duel_state = state
        self.assertIsNone(duel.projection(self.actor, self.char1, now=101))
        duel.reconcile(self.actor, now=101)
        self.assertEqual(self.actor.db.duel_state["final_result"]["kind"], "abort")
        self.assertFalse(duel.active_for(self.char1))

    def test_training_and_dialogue_are_available_without_replacing_actor(self):
        name = self.actor.key
        self.char1.change(lambda profile: profile.update(xp=rules.xp_threshold(20)))
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd(f"{name}에게 훈련 말")
            self.char1.execute_cmd(f"{name}에게 강타 배워")
        self.assertTrue(output.call_args_list)
        self.assertEqual(self.char1.profile()["skills"]["heavy"], 2)
        identity = self.start()
        self.actor.db.fixture_other_domain = "preserved"
        duel.surrender(self.actor, self.char1, identity, now=101)
        self.actor.attributes.reset_cache()
        self.assertEqual(self.actor.db.fixture_other_domain, "preserved")
        self.assertTrue(self.actor.capability_active("dialogue"))
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd(f"{name}에게 훈련 말")
            self.char1.execute_cmd(f"{name}에게 강타 배워")
        self.assertTrue(output.call_args_list)
        self.assertEqual(self.char1.profile()["skills"]["heavy"], 3)

    def test_disabled_combat_capability_aborts_existing_duel(self):
        index = compile_manifest(PackageManifest((PACKAGE,)))
        guard = spawn_fixture(GUARD_ID, self.room1)
        self.assertTrue(guard.capability_active("interaction"))
        duel.start(guard, self.char1, now=100)
        guard.set_capability_active("combat", False)
        duel.reconcile(guard, now=101)
        self.assertTrue(guard.capability_active("interaction"))
        self.assertFalse(duel.active_on(guard))
        invocation = dispatch_text(self.char1, index, INTERACTION_ID + ".verb", guard.key, "경비진단")
        result = execute(self.char1, self.sessions[self.char1.pk], invocation, index)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn("외부 진단 단자가 응답한다", str(result.messages))
        with self.assertRaises(rules.RuleError):
            duel.start(guard, self.char1, now=102)

    def test_text_and_web_share_actor_generation_scope_and_authenticated_caller(self):
        index = get_index()
        ref = descriptor(self.actor).reference
        number = number_for(ref)

        def web(action_id, arguments, request_id):
            return from_web({
                "action_id": "global." + action_id,
                "variant": "adapter",
                "roles": {"subject": [reference_json(ref)]},
                "arguments": arguments,
                "request_id": request_id,
            }, index)

        with patch("world.duel.time", return_value=100):
            refused = execute(self.char1, self.sessions[self.char2.pk],
                              web("duel_start", {"generation": 0}, "wrong-session"), index)
            self.assertEqual(refused.status, ResultStatus.REFUSED)
            self.assertFalse(duel.active_on(self.actor))
            with patch.object(self.char1, "msg") as output:
                self.char1.execute_cmd(f"{self.actor.key} 대련")
            self.assertTrue(duel.active_on(self.actor), output.call_args_list)
            encounter_id = self.projection()["identity"]
        invocation = web("duel_act", {"encounter_id": encounter_id}, "actor-action")
        with patch("world.duel.time", return_value=105):
            self.assertEqual(execute(self.char2, self.sessions[self.char2.pk], invocation, index).status,
                             ResultStatus.REFUSED)
            self.assertEqual(execute(self.char1, self.sessions[self.char1.pk], invocation, index).status,
                             ResultStatus.SUCCESS)
        self.assertEqual(self.projection(105)["idle_at"], 165)
        self.assertEqual(number_for(descriptor(self.actor).reference), number)
        self.char1.location = self.room2
        with patch("world.duel.time", return_value=106):
            self.assertEqual(execute(self.char1, self.sessions[self.char1.pk], invocation, index).status,
                             ResultStatus.REFUSED)
        self.assertIsNone(self.projection(106))
        self.assertEqual(self.projection(106, viewer=self.char2)["idle_at"], 165)
        self.char1.location = self.room1
        with patch("world.duel.time", return_value=110):
            result = execute(self.char1, self.sessions[self.char1.pk],
                             web("duel_surrender", {"encounter_id": encounter_id}, "surrender"), index)
            self.assertEqual(result.status, ResultStatus.SUCCESS)
        with patch("world.duel.time", return_value=140):
            stale = web("duel_start", {"generation": 0}, "stale-start")
            current = web("duel_start", {"generation": 1}, "current-start")
            self.assertEqual(execute(self.char1, self.sessions[self.char1.pk], stale, index).status,
                             ResultStatus.REFUSED)
            self.assertEqual(execute(self.char1, self.sessions[self.char1.pk], current, index).status,
                             ResultStatus.SUCCESS)
        self.assertEqual(self.projection(140)["generation"], 2)


class DuelConcurrencyTests(TransactionTestCase):
    def tearDown(self):
        clear_test_caches()
        super().tearDown()

    def test_contended_start_and_finish_leave_one_persistent_result(self):
        room = create_object(DefaultRoom, key="대련 경합 방")
        room.db.zone_id = "training_room"
        room.tags.add("training_room", category=CATEGORY)
        players = [create_object(Explorer, key=name, location=room) for name in ("경합 갑", "경합 을")]

        def race(first, second):
            shared = connections["default"]
            shared.inc_thread_sharing()
            barrier = Barrier(2)

            def attempt(action):
                connections["default"] = shared
                barrier.wait(timeout=10)
                try:
                    return action()
                except rules.RuleError:
                    return None

            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(attempt, action) for action in (first, second)]
                    return [future.result(timeout=20) for future in futures]
            finally:
                shared.dec_thread_sharing()

        with (registry_overlay(),
              patch.object(content, "CAPABILITIES", {**content.CAPABILITIES, "interaction": INTERACTION}),
              patch.object(players[0].sessions, "count", return_value=1),
              patch.object(players[1].sessions, "count", return_value=1),
              patch("world.duel.delay"), patch("world.duel._publish")):
            actor = spawn_fixture(INSTRUCTOR_ID, room)
            attempts = race(*(lambda player=player: duel.start(actor, player, now=100) for player in players))
            self.assertEqual(sum(identity is not None for identity in attempts), 1)
            winner = next(player for player, result in zip(players, attempts, strict=True) if result is not None)
            self.assertEqual(actor.db.duel_state["participant_id"], winner.pk)
            identity = actor.db.duel_state["identity"]
            self.assertIn(identity, attempts)
            self.assertTrue(duel.active_for(winner))
            race(lambda: duel.surrender(actor, winner, identity, now=159.999),
                 lambda: duel.reconcile(actor, now=160))
            actor.attributes.reset_cache()
            result = deepcopy(dict(actor.db.duel_state["final_result"]))
            self.assertIn(result["kind"], {"surrender", "timeout"})
            self.assertTrue(actor.db.duel_state["settled"])
            self.assertFalse(duel.active_for(winner))
            self.assertFalse(duel.reconcile(actor, now=161))
            self.assertEqual(dict(actor.db.duel_state["final_result"]), result)
