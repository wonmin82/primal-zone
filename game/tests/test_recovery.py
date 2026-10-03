"""실제 저장·이동·전투·puppet과 관찰 예약의 시간 경계 회귀."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia.objects.objects import DefaultCharacter
from evennia.utils.ansi import strip_ansi
from evennia.utils.dbserialize import deserialize
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from world import recovery, rules
from world.content import ITEMS
from world.lifecycle import reconcile_world
from world.multiplayer import world_change

from tests.base import WorldCommandTest


class RecoveryTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.clock = self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.enterContext(patch("typeclasses.enemies.time", side_effect=lambda: self.clock.return_value))
        self.tasks = self.enterContext(patch("typeclasses.explorers.delay"))
        self.enterContext(patch("typeclasses.enemies.delay"))
        for p in (self.char1, self.char2):
            p.location = self.rooms["infirmary"]
            p.push_state = Mock()
        self.enterContext(patch.object(self.char1.sessions, "count", return_value=1))
        self.char1.change(lambda p: p.update(hp=10, mental=10, recovery=recovery.initialize(100)))

    def test_movement_accrues_old_location_without_payment(self):
        self.clock.return_value = 109
        self.assertTrue(self.char1.move_to(self.rooms["support_2f_w1"], quiet=True))
        p = self.char1.profile_snapshot()
        self.assertEqual((p["hp"], p["mental"]), (10, 10))
        self.assertAlmostEqual(p["recovery"]["credit"]["hp"], 1.35)
        self.clock.return_value = 120
        self.char1.reconcile_recovery(120)
        self.assertEqual((self.char1.profile()["hp"], self.char1.profile()["mental"]), (11, 12))

    def test_movement_failure_rolls_back_location_and_recovery(self):
        before = deepcopy(self.char1.profile_snapshot())
        self.clock.return_value = 109
        with self.assertRaises(RuntimeError), world_change():
            self.char1.move_to(self.rooms["support_2f_w1"], quiet=True)
            raise RuntimeError("rollback")
        self.assertEqual(self.char1.zone, "infirmary")
        self.assertEqual(self.char1.profile_snapshot(), before)

    def test_combat_transition_and_timer_needs(self):
        self.char1.location = self.rooms["grass"]
        enemy = room_enemies(self.char1.location)[0]
        self.clock.return_value = 109
        enemy.engage(self.char1, now=109)
        self.assertEqual(self.char1.profile()["hp"], 10)
        self.clock.return_value = 120
        self.char1.reconcile_recovery(120)
        p = self.char1.profile()
        self.assertEqual((p["hp"], p["mental"]), (10, 12))
        self.char1.change(lambda p: p.update(mental=rules.stats(p)["max_mental"]))
        self.assertIsNone(self.char1.ndb.recovery_task)
        self.char1.leave_combat(now=120)
        self.assertIsNotNone(self.char1.ndb.recovery_task)

    def test_equipment_transition_applies_only_future_time(self):
        self.char1.location = self.rooms["staging_room"]
        self.char1.change(lambda p: p["equipment"].update(weapon=None))
        definition = {**ITEMS["machete"], "recovery_bonus": {"mental_per_minute": 6}}
        with patch.dict(ITEMS, machete=definition):
            self.clock.return_value = 109
            self.char1.execute_cmd("낡은마체테 무장")
            self.assertEqual(self.char1.profile()["mental"], 10)
            self.clock.return_value = 120
            self.char1.reconcile_recovery(120)
            self.assertEqual(self.char1.profile()["mental"], 13)

    def test_offline_logout_location_then_new_login_staging(self):
        self.char1.change(lambda p: p.update(credits=127, command_shortcuts={"점검": ["상태"]}))
        self.clock.return_value = 109
        with patch.object(self.char1.sessions, "count", return_value=0):
            self.char1.at_post_unpuppet(account=self.account, session=self.session)
        self.assertIsNone(self.char1.ndb.recovery_task)
        self.clock.return_value = 160
        self.char1.at_pre_puppet(self.account, session=self.session)
        p = self.char1.profile()
        self.assertEqual(self.char1.zone, "staging_room")
        self.assertEqual((p["hp"], p["mental"]), (19, 18))
        self.assertEqual((p["credits"], p["command_shortcuts"]), (127, {"점검": ["상태"]}))
        self.clock.return_value = 220
        self.char1.reconcile_recovery(220)
        self.assertEqual((self.char1.profile()["hp"], self.char1.profile()["mental"]), (22, 24))

    def test_snapshot_v8_migration_does_not_write_or_initialize_clock(self):
        p = rules.new_profile()
        p.update(version=8, xp=rules.xp_threshold(5))
        p.pop("mental")
        p.pop("recovery_effects")
        self.char1.db.profile = p
        before = deepcopy(deserialize(self.char1.db.profile))
        snapshot = self.char1.profile_snapshot()
        self.assertEqual((snapshot["version"], snapshot["mental"]), (9, 60))
        self.assertNotIn("recovery", snapshot)
        self.assertEqual(deserialize(self.char1.db.profile), before)
        self.assertEqual(self.char1.profile()["version"], 9)
        self.assertEqual(deserialize(self.char1.db.profile)["mental"], 60)

    def test_real_account_logout_login_and_reload_recovery(self):
        self.account.puppet_object(self.session, self.char1)
        self.char1.move_to(self.rooms["infirmary"], quiet=True)
        # Account API가 sessions를 실제로 제거/연결하고 ServerSession이 Object를 복원한다.
        self.char1.change(lambda p: p.update(recovery_effects=[{
            "started_at": 100, "expires_at": 130, "mental_per_minute": 6}]))
        self.clock.return_value = 109
        with patch.object(self.char1.sessions, "count", wraps=self.char1.sessions.count) as connected:
            # 다른 테스트의 관찰용 count=1 override 대신 실제 session 수를 사용한다.
            connected.side_effect = lambda: len(self.char1.sessions.all())
            self.account.unpuppet_object(self.session)
        self.assertIsNone(self.char1.location)
        self.assertEqual(self.char1.db.prelogout_location, self.rooms["infirmary"])
        self.clock.return_value = 160
        self.account.puppet_object(self.session, self.char1)
        p = self.char1.profile_snapshot()
        self.assertEqual((p["hp"], p["mental"]), (19, 21))
        self.assertEqual(self.char1.zone, "staging_room")
        self.char1.move_to(self.rooms["support_roof"], quiet=True)
        before = self.char1.profile_snapshot()
        self.session.puid = self.char1.id
        self.session.at_sync()
        self.assertEqual(self.session.puppet.zone, "support_roof")
        self.assertEqual(self.char1.profile_snapshot(), before)

    def test_medical_full_hp_rest_mental_and_credit_reset(self):
        self.clock.return_value = 109
        self.char1.execute_cmd("의무관 진료")
        p = self.char1.profile()
        self.assertEqual((p["hp"], p["mental"]), (60, 10))
        self.assertEqual(p["recovery"]["credit"]["hp"], 0)
        self.char1.execute_cmd("침대 휴식")
        self.assertEqual((self.char1.profile()["hp"], self.char1.profile()["mental"]), (60, 40))
        self.assertIsNone(self.char1.ndb.recovery_task)

    def test_enemy_delay_partial_reengage_dead_respawn_and_lazy(self):
        enemy = room_enemies(self.rooms["grass"])[0]
        enemy.db.hp = 5
        enemy.db.last_activity = 100
        enemy.reconcile(114)
        self.assertEqual(enemy.db.hp, 5)
        enemy.reconcile(115)
        self.assertEqual(enemy.db.hp, 5)
        enemy.reconcile(130)
        self.assertEqual(enemy.db.hp, 7)
        self.char1.location = self.rooms["grass"]
        enemy.engage(self.char1, now=130)
        self.assertEqual(enemy.db.hp, 7)
        self.char1.leave_combat(now=130)
        enemy.reconcile(400)
        self.assertEqual(enemy.db.hp, 24)
        enemy.db.state = "respawning"
        enemy.db.hp = 0
        enemy.db.respawn_at = 500
        enemy.reconcile(450)
        self.assertEqual(enemy.db.hp, 0)
        enemy.reconcile(500)
        self.assertEqual(enemy.db.hp, 24)

    def test_enemy_empty_room_no_timer_and_observed_single_timer(self):
        enemy = room_enemies(self.rooms["grass"])[0]
        enemy.db.hp = 5
        enemy.db.last_activity = 100
        enemy.reconcile(100)
        self.assertIsNone(enemy.ndb.lifecycle_task)
        self.char1.location = enemy.location
        enemy.reconcile(100)
        task = enemy.ndb.lifecycle_task
        self.assertIsNotNone(task)
        enemy.schedule_lifecycle()
        self.assertIs(enemy.ndb.lifecycle_task, task)

    def test_enemy_reengage_preserves_fraction_without_combat_recovery(self):
        enemy = room_enemies(self.rooms["grass"])[0]
        enemy.db.hp = 5
        enemy.db.last_activity = 100
        enemy.reconcile(120)
        self.char1.location = enemy.location
        enemy.engage(self.char1, now=120)
        self.char1.leave_combat(now=150)
        enemy.reconcile(170)
        # 115..120과 165..170의 비전투 회복 0.8+0.8만 합산, 교전 시간은 제외.
        self.assertEqual(enemy.db.hp, 6)

    def test_restart_online_reconcile_and_offline_remains_lazy(self):
        before = deepcopy(self.char2.profile_snapshot())
        self.clock.return_value = 160
        reconcile_world(160, restart=True)
        self.assertEqual(self.char1.zone, "infirmary")
        self.assertEqual((self.char1.profile()["hp"], self.char1.profile()["mental"]), (19, 18))
        self.assertEqual(self.char2.profile_snapshot(), before)

    def test_web_payload_has_server_resources_and_prompt_without_log(self):
        self.char1.push_state = Explorer.push_state.__get__(self.char1)
        with patch.object(self.char1, "msg") as output:
            self.char1.push_state(observed_at=100)
        state = next(call.kwargs["pz_state"][0][0] for call in output.call_args_list if "pz_state" in call.kwargs)
        self.assertEqual([state[key] for key in ("hp", "max_hp", "mental", "max_mental")], [10, 60, 10, 40])
        self.assertEqual("".join(part["text"] for part in state["resource_prompt"]), "[ 10/60 · 10/40 ] >")
        self.assertFalse(any("pz_log" in call.kwargs for call in output.call_args_list))

    def test_telnet_prompt_uses_prompt_channel_and_skips_web_log(self):
        self.char1.change(lambda p: p.update(hp=0, mental=20))
        telnet = Mock(protocol_key="telnet")
        web = Mock(protocol_key="websocket")
        before = self.char1.profile_snapshot()
        with patch.object(self.char1.sessions, "all", return_value=[telnet, web]), patch.object(
            DefaultCharacter, "msg"
        ) as output:
            self.char1.push_prompt()
        output.assert_called_once()
        self.assertIs(output.call_args.kwargs["session"], telnet)
        prompt, options = output.call_args.kwargs["prompt"]
        self.assertEqual(strip_ansi(prompt), "[ 0/60 · 20/40 ] >")
        self.assertIn("\x1b[1m", prompt)
        self.assertEqual(options, {})
        self.assertNotIn("text", output.call_args.kwargs)
        self.assertEqual(self.char1.profile_snapshot(), before)
