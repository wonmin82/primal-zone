"""실제 dispatcher/transport의 완료·실패·비동기 출력 순서와 중복 회귀."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import CmdSet, Command
from evennia.commands import cmdhandler
from evennia.objects.objects import DefaultCharacter
from evennia.utils.ansi import strip_ansi
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from world import recovery, rules
from world import text as ft

from tests.base import WorldCommandTest


class PromptTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["infirmary"]
        self.clock = self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.enterContext(patch("typeclasses.enemies.time", side_effect=lambda: self.clock.return_value))
        for module in ("explorers", "enemies", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
        self.output = self.enterContext(patch.object(self.char1, "msg"))
        self.char1.push_state = Mock()
        self.char1.push_prompt = Mock(side_effect=lambda: self.char1.msg(
            ft.resource_prompt(self.char1.profile_snapshot(), rules.stats(self.char1.profile_snapshot()))))
        self.char1.change(lambda p: p.update(hp=10, mental=10, recovery=recovery.initialize(100)))

    def messages(self):
        return [call.args[0] for call in self.output.call_args_list if call.args]

    def one_final_prompt(self, raw):
        self.output.reset_mock()
        self.char1.push_prompt.reset_mock()
        done = []
        self.char1.execute_cmd(raw, session=self.session).addCallback(lambda result: done.append(True))
        self.assertEqual(done, [True], raw)
        self.char1.push_prompt.assert_called_once()
        messages = self.messages()
        self.assertEqual(getattr(messages[-1], "kind", None), "prompt", raw)
        self.assertEqual(sum(getattr(m, "kind", None) == "prompt" for m in messages), 1)
        return messages

    def test_commands_errors_exits_and_sequence_finish_once(self):
        for raw in ("상태", "의무관 진료", "침대 휴식", "응급처치", "없는대상 보기", "날아"):
            with self.subTest(raw=raw):
                self.char1.change(lambda p: p.update(hp=10, mental=10))
                self.assertGreater(len(self.one_final_prompt(raw)), 1)
        self.char1.location = self.rooms["support_roof"]
        self.one_final_prompt("북동")
        self.assertEqual(self.char1.zone, "support_roof_ne")
        self.one_final_prompt("남서, 상태 해")
        self.assertEqual(self.char1.zone, "support_roof")
        self.char1.location = self.rooms["grass"]
        self.one_final_prompt("어린청소룡 공격")
        self.assertIsNotNone(self.char1.profile()["combat_target"])

    def test_blank_inputs_reconcile_boundary_once_and_do_not_save_command(self):
        self.clock.return_value = 112
        for raw in ("", " ", "    ", "", ""):
            self.assertEqual(len(self.one_final_prompt(raw)), 1)
            self.assertEqual((self.char1.profile()["hp"], self.char1.profile()["mental"]), (11, 11))
            self.assertIsNone(self.char1.ndb.last_cmd)
            self.assertIsNone(self.char1.profile()["combat_target"])

    def test_actual_text_input_blank_bypasses_progressive_cmdset(self):
        from server.conf.primal_inputfuncs import text

        session = self.session
        session.puppet = self.char1
        for raw in ("", " ", "    "):
            self.output.reset_mock()
            self.char1.push_prompt.reset_mock()
            with patch("evennia.server.inputfuncs.text") as default:
                text(session, raw)
            default.assert_not_called()
            self.char1.push_prompt.assert_called_once()
            self.assertEqual(len(self.messages()), 1)
            self.assertIsNone(self.char1.ndb.last_cmd)

    def test_command_boundary_recovery_has_no_early_or_duplicate_prompt(self):
        self.clock.return_value = 120
        messages = self.one_final_prompt("상태")
        self.assertIn("체력 13/60", str(messages[0]))
        self.assertEqual(str(messages[-1]), "[ 13/60 · 12/40 ] >")

    def test_silent_checkpoint_and_failed_movement_preserve_state(self):
        self.clock.return_value = 109
        self.output.reset_mock()
        self.char1.push_state.reset_mock()
        self.char1.push_prompt.reset_mock()
        self.char1.checkpoint_recovery()
        self.output.assert_not_called()
        self.char1.push_state.assert_not_called()
        self.char1.push_prompt.assert_not_called()

    def test_destination_hook_rejection_rolls_back_without_outer_transaction(self):
        self.char1.push_state.reset_mock()
        before = deepcopy(self.char1.profile_snapshot())
        self.clock.return_value = 109
        destination = self.rooms["support_2f_w1"]
        with patch.object(destination, "at_pre_object_receive", return_value=False):
            self.assertFalse(self.char1.move_to(destination, quiet=True))
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.char1.zone, "infirmary")
        self.char1.push_prompt.assert_not_called()
        before = deepcopy(self.char1.profile_snapshot())
        from world.multiplayer import world_change

        with self.assertRaises(RuntimeError), world_change():
            self.char1.move_to(self.rooms["support_2f_w1"], quiet=True)
            raise RuntimeError("rollback")
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.char1.zone, "infirmary")
        self.char1.push_state.assert_not_called()

    def test_save_and_async_combat_no_prompt_but_defeat_has_final_prompt(self):
        self.char1.push_prompt.reset_mock()
        self.char1.save_profile(self.char1.profile())
        self.char1.push_prompt.assert_not_called()
        self.char1.location = self.rooms["grass"]
        enemy = room_enemies(self.char1.location)[0]
        enemy.engage(self.char1, now=100)
        self.output.reset_mock()
        self.char1.resolve_combat_round(now=103, rng=Random(1))
        enemy.enemy_tick(now=103, rng=Random(1))
        self.assertTrue(self.messages())
        self.char1.push_prompt.assert_not_called()
        self.char1.change(lambda p: p.update(hp=1))
        with patch("twisted.internet.reactor.callLater") as queued:
            enemy.enemy_tick(now=106, rng=Random(1))
        self.assertEqual(self.char1.zone, "infirmary")
        self.char1.push_prompt.assert_not_called()
        self.assertEqual(queued.call_count, 1)
        queued.call_args.args[1]()
        messages = self.messages()
        self.assertIn("의무실", str(messages[-2]))
        self.assertEqual(str(messages[-1]), "[ 1/60 · 10/40 ] >")
        self.char1.push_prompt.assert_called_once()

    def test_async_recovery_defers_after_combat_and_no_change_is_silent(self):
        self.enterContext(patch.object(self.char1.sessions, "count", return_value=1))
        with patch("twisted.internet.reactor.callLater") as queued:
            self.assertTrue(self.char1.reconcile_recovery(120))
            self.char1.msg(ft.text("적의 자동 공격 결과"))
            queued.call_args.args[1]()
        self.assertEqual([str(m) for m in self.messages()][-2:],
                         ["적의 자동 공격 결과", "[ 13/60 · 12/40 ] >"])
        self.char1.push_prompt.reset_mock()
        self.assertFalse(self.char1.reconcile_recovery(120))
        self.char1.push_prompt.assert_not_called()

    def test_login_outputs_once_and_logout_shutdown_are_silent(self):
        self.output.reset_mock()
        self.char1.at_post_puppet(session=self.session)
        self.char1.push_prompt.assert_called_once()
        self.assertEqual(getattr(self.messages()[-1], "kind", None), "prompt")
        self.char1.push_prompt.reset_mock()
        self.char1.at_post_unpuppet(account=self.account, session=self.session)
        self.char1.at_server_shutdown()
        self.char1.push_prompt.assert_not_called()

    def test_account_command_and_real_relogin_clear_output_context(self):
        self.account.puppet_object(self.session, self.char1)
        # 실제 MuxAccountCommand.parse는 caller를 Character에서 Account로 바꾼다.
        self.one_final_prompt("접속자")
        self.assertEqual(self.char1.ndb.command_output_depth, 0)
        self.char1.ndb.command_output_depth = 1  # logout으로 중단된 progressive 입력
        self.char1.push_prompt.reset_mock()
        self.account.unpuppet_object(self.session)
        self.assertEqual(self.char1.ndb.command_output_depth, 0)
        self.char1.push_prompt.assert_not_called()
        self.output.reset_mock()
        self.account.puppet_object(self.session, self.char1)
        self.char1.push_prompt.assert_called_once()
        self.assertEqual(getattr(self.messages()[-1], "kind", None), "prompt")
        self.one_final_prompt("상태")

    def test_engine_progressive_prompt_waits_for_actual_post_hook(self):
        class Progressive(Command):
            key = "대기시험"

            def func(self):
                answer = yield "선택하세요"
                self.caller.msg("완료: " + answer)

        class Extra(CmdSet):
            def at_cmdset_creation(self):
                self.add(Progressive())

        self.char1.cmdset.add(Extra())
        captured = {}

        def input_request(caller, prompt, callback, **kwargs):
            captured.update(kwargs)

        with patch.object(cmdhandler, "_GET_INPUT", input_request):
            self.char1.execute_cmd("대기시험", session=self.session)
        self.char1.push_prompt.assert_not_called()
        cmdhandler._progressive_cmd_run(captured["cmd"], captured["generator"], response="예")
        self.char1.push_prompt.assert_called_once()
        self.assertEqual(str(self.messages()[-2]), "완료: 예")

    def test_web_semantic_and_telnet_prompt_share_order_and_values(self):
        telnet, web = Mock(protocol_key="telnet"), Mock(protocol_key="websocket")
        with patch.object(self.char1.sessions, "count", return_value=2), patch.object(
            self.char1.sessions, "all", return_value=[telnet, web]
        ), patch.object(DefaultCharacter, "msg") as transport:
            self.char1.msg = Explorer.msg.__get__(self.char1)
            self.char1.push_prompt = Explorer.push_prompt.__get__(self.char1)
            self.char1.execute_cmd("상태", session=self.session)
        events = transport.call_args_list
        prompt_calls = [c for c in events if "prompt" in c.kwargs]
        semantic_calls = [c for c in events if "pz_log" in c.kwargs]
        self.assertEqual(len(prompt_calls), 1)
        self.assertEqual(semantic_calls[-1].kwargs["pz_log"][0][0]["kind"], "prompt")
        self.assertEqual(strip_ansi(prompt_calls[0].kwargs["prompt"][0]), "[ 10/60 · 10/40 ] >")
        self.assertEqual("".join(p["text"] for p in semantic_calls[-1].kwargs["pz_log"][0][0]["segments"]),
                         "[ 10/60 · 10/40 ] >")
