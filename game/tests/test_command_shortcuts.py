"""실제 dispatcher와 DB를 통과하는 개인 줄임말/묶음/확인 회귀."""

from copy import deepcopy
from unittest.mock import Mock, patch

from commands.default_cmdsets import CharacterCmdSet, UnloggedinCmdSet
from commands.shortcuts import DELETE_ALL_CONFIRM_TTL_SECONDS, MAX_COMMANDS
from evennia import CmdSet, Command
from evennia.commands.cmdparser import cmdparser as default_parser
from evennia.utils.dbserialize import deserialize
from server.conf.cmdparser import cmdparser
from twisted.internet.defer import Deferred
from typeclasses.explorers import Explorer

from tests.base import WorldCommandTest


class CommandShortcutsTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = player.home = self.rooms["dock"]
            player.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def run_raw(self, raw, player=None):
        player = player or self.char1
        with patch.object(player, "msg") as message:
            completed = []
            player.execute_cmd(raw).addCallback(lambda result: completed.append(True))
            self.assertEqual(completed, [True], raw)
            return "\n".join(str(call.args[0]) for call in message.call_args_list if call.args)

    def saved(self, player=None):
        return (player or self.char1).profile_snapshot()["command_shortcuts"]

    def register(self, name="점검", definition="상태, 장비, 소지품 해", player=None):
        output = self.run_raw(f"줄임말 추가 {name} {definition}", player)
        self.assertIn("추가했습니다", output)

    def test_purchase_then_wield_and_location_specific_commands_run_sequentially(self):
        self.char1.location = self.rooms["weapon_shop"]
        self.char1.change(lambda p: p.update(credits=100))
        self.run_raw("절단마체테 구매, 탐사용 벌목도 해제, 절단마체테 무장 해")
        profile = self.char1.profile_snapshot()
        self.assertEqual(profile["inventory"]["cutting_machete"], 1)
        self.assertEqual(profile["equipment"]["weapon"], "cutting_machete")
        self.assertEqual(profile["credits"], 40)
        self.run_raw("귀환, 승강기, 3층, 동, 북 해")
        self.assertEqual(self.char1.zone, "weapon_shop")

    def test_dispatch_waits_for_engine_pre_and_post_hooks_without_sleep(self):
        for hook in ("at_pre_cmd", "at_post_cmd"):
            gate = Deferred()
            held = Command(key="대기검사", locks="cmd:all()")
            held.func = lambda: None
            setattr(held, hook, lambda: gate)
            commands = CmdSet()
            commands.add(held)
            self.char1.cmdset.add(commands)
            with patch.object(self.char1, "msg") as message:
                complete = []
                self.char1.execute_cmd("대기검사, 상태 해").addCallback(lambda result: complete.append(True))
                self.assertFalse(complete)
                self.assertFalse(message.called)
                gate.callback(None)
                self.assertEqual(complete, [True])
                self.assertIn("체력", str(message.call_args_list))
            self.char1.cmdset.remove(commands)

    def test_gameplay_failure_and_unknown_command_continue(self):
        self.char1.change(lambda p: p["inventory"].pop("bandage"))
        output = self.run_raw("붕대 사용, 없는명령, 상태 해")
        self.assertIn("대상 뒤에 행동", output)
        self.assertIn("체력", output)

    def test_malformed_or_expansion_error_executes_nothing(self):
        for raw in ("귀환 해", "귀환,, 상태 해", ", 귀환 해", "귀환, 상태, 해",
                    ", ".join(["귀환"] * (MAX_COMMANDS + 1)) + " 해"):
            before = deepcopy(self.char1.profile_snapshot())
            self.run_raw(raw)
            self.assertEqual(self.char1.zone, "dock")
            self.assertEqual(self.char1.profile_snapshot(), before)
        self.char1.change(lambda p: p.update(command_shortcuts={"순환": ["순환"]}))
        self.run_raw("귀환, 순환 해")
        self.assertEqual(self.char1.zone, "dock")

    def test_comma_chat_raw_and_shortcut_remains_one_say(self):
        for raw in ("안녕, 반가워 말", "'안녕, 반가워"):
            with patch.object(self.char2, "msg") as other:
                self.run_raw(raw)
                self.assertEqual(other.call_count, 1)
                self.assertEqual(str(other.call_args.args[0]), f"{self.char1.key}: 안녕, 반가워")
        self.register("인사", "안녕, 반가워 말")
        self.assertEqual(self.saved()["인사"], ["안녕, 반가워 말"])
        with patch.object(self.char2, "msg") as other:
            self.run_raw("인사")
            self.assertEqual(other.call_count, 1)
            self.assertEqual(str(other.call_args.args[0]), f"{self.char1.key}: 안녕, 반가워")

    def test_registration_list_nested_sequence_and_exact_matching(self):
        self.register()
        self.assertEqual(self.saved()["점검"], ["상태", "장비", "소지품"])
        self.register("출발", "점검, 귀환 해")
        output = self.run_raw("점검")
        self.assertIn("체력", output)
        self.assertIn("장비", output)
        self.assertIn("소지품", output)
        self.run_raw("출발")
        self.assertEqual(self.char1.zone, "support_roof")
        self.run_raw("점검, 승강기, 2층 해")
        self.assertEqual(self.char1.zone, "support_2f_c")
        self.assertIn("점검 = 상태, 장비, 소지품 해", self.run_raw("줄임말"))
        self.char2.location = self.char1.location
        with patch.object(self.char2, "msg") as other:
            self.run_raw("점검 말")
            self.assertEqual(str(other.call_args.args[0]), f"{self.char1.key}: 점검")

    def test_persistence_is_character_local_and_parser_read_does_not_save(self):
        self.register("장확", "장비")
        self.assertEqual(deserialize(self.char1.db.profile)["command_shortcuts"], {"장확": ["장비"]})
        self.assertEqual(self.saved(self.char2), {})
        self.assertIn("대상 뒤에 행동", self.run_raw("장확", self.char2))
        old = self.char1.profile_snapshot()
        old["version"] = 6
        self.char1.db.profile = old
        with patch.object(self.char1, "save_profile") as save, patch.object(self.char1, "push_state") as push:
            self.assertTrue(cmdparser("장확", CharacterCmdSet(), self.char1))
            save.assert_not_called()
            push.assert_not_called()
        self.assertEqual(deserialize(self.char1.db.profile)["version"], 6)

    def test_reserved_names_and_invalid_prospective_graph_do_not_replace_data(self):
        self.register("a", "b")
        for name in ("상태", "공격", "해", "줄임말", "ㅂ", "look", "quit", "connect", "n", "2층", "emit",
                     "북동", "남동", "남서", "북서", "ne", "se", "sw", "nw"):
            before = self.saved()
            self.run_raw(f"줄임말 추가 {name} 소지품")
            self.assertEqual(self.saved(), before, name)
        before = self.saved()
        for raw in ("줄임말 추가 b a", "줄임말 추가 a a", "줄임말 추가 a 상태,, 장비 해"):
            self.run_raw(raw)
            self.assertEqual(self.saved(), before)
        self.run_raw("줄임말 추가 a 장비")
        self.assertEqual(self.saved()["a"], ["장비"])

    def test_runtime_real_and_locked_command_precedence_over_personal(self):
        self.char1.change(lambda p: p.update(command_shortcuts={"점검": ["귀환"], "상태": ["귀환"], "상": ["귀환"]}))
        commands = CharacterCmdSet()
        actual = Command(key="점검", locks="cmd:all()")
        commands.add(actual)
        matches = cmdparser("점검", commands, self.char1)
        self.assertEqual(matches, default_parser("점검", commands, self.char1))
        self.assertIs(matches[0][2].func.__func__, actual.func.__func__)
        self.assertEqual(matches[0][2].key, actual.key)
        commands.add(Command(key="점검", locks="cmd:false()"))
        self.assertEqual(cmdparser("점검", commands, self.char1), [])
        self.run_raw("상태")
        self.run_raw("상")
        self.assertEqual(self.char1.zone, "dock")

    def test_flat_execution_cannot_expand_a_definition_created_mid_sequence(self):
        output = self.run_raw("소지품, 줄임말 추가 새것 상태, 새것 해")
        self.assertEqual(self.saved(), {"새것": ["상태"]})
        self.assertNotIn("체력", output)
        self.assertIn("다시 확장하지", output)
        self.assertIn("체력", self.run_raw("새것"))

    def test_engine_progressive_input_is_rejected_before_any_command(self):
        held = Command(key="입력대화", locks="cmd:all()")

        def prompt():
            yield "다음 입력"

        held.func = prompt
        commands = CmdSet()
        commands.add(held)
        self.char1.cmdset.add(commands)
        output = self.run_raw("귀환, 입력대화 해")
        self.assertIn("묶음 밖", output)
        self.assertEqual(self.char1.zone, "dock")

    def test_individual_delete_does_not_cascade_and_everybody_name_is_not_all_delete(self):
        self.register("모두", "상태")
        self.register("점검", "모두")
        self.run_raw("줄임말 삭제 모두")
        self.assertEqual(self.saved(), {"점검": ["모두"]})
        self.run_raw("줄임말 삭제 점검")
        self.assertIn("대상 뒤에 행동", self.run_raw("점검"))

    def test_confirm_alone_cannot_delete_and_valid_request_is_one_shot(self):
        self.register("a", "상태")
        self.register("b", "장비")
        before = self.saved()
        self.assertIn("먼저", self.run_raw("줄임말 모두 삭제 확인"))
        self.assertEqual(self.saved(), before)
        self.run_raw("줄임말 모두 삭제")
        self.assertEqual(self.saved(), before)
        self.assertIsNotNone(self.char1.ndb.shortcut_delete_all_request)
        self.assertIn("2개", self.run_raw("줄임말 모두 삭제 확인"))
        self.assertEqual(self.saved(), {})
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        self.register("c", "소지품")
        self.run_raw("줄임말 모두 삭제 확인")
        self.assertEqual(self.saved(), {"c": ["소지품"]})

    def test_sequence_cannot_request_and_confirm_all_deletion(self):
        self.register("a", "상태")
        self.register("b", "장비")
        before = self.char1.profile_snapshot()
        # 설정 prefix가 먼저 해석하는 입력도 삭제 경로에 들어가면 안 된다.
        output = self.run_raw("줄임말 모두 삭제, 줄임말 모두 삭제 확인 해")
        self.assertIn("줄임말 모두 삭제 확인", output)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        output = self.run_raw("상태, 줄임말 모두 삭제, 줄임말 모두 삭제 확인 해")
        self.assertIn("체력", output)
        self.assertEqual(output.count("각각 직접 입력"), 2)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)

    def test_shortcut_cannot_request_and_confirm_all_deletion(self):
        self.register("a", "상태")
        self.register("초기화", "줄임말 모두 삭제, 줄임말 모두 삭제 확인 해")
        before = self.char1.profile_snapshot()
        output = self.run_raw("초기화")
        self.assertEqual(output.count("각각 직접 입력"), 2)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIn("초기화", self.saved())
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)

    def test_indirect_request_cannot_create_or_replace_pending(self):
        self.register("삭제요청", "줄임말 모두 삭제")
        before = self.char1.profile_snapshot()
        for raw in ("삭제요청", "상태, 줄임말 모두 삭제 해"):
            self.assertIn("각각 직접 입력", self.run_raw(raw))
            self.assertEqual(self.char1.profile_snapshot(), before)
            self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        self.run_raw("줄임말 모두 삭제")
        request = deepcopy(self.char1.ndb.shortcut_delete_all_request)
        for raw in ("삭제요청", "상태, 줄임말 모두 삭제 해"):
            self.assertIn("각각 직접 입력", self.run_raw(raw))
            self.assertEqual(self.char1.profile_snapshot(), before)
            self.assertEqual(self.char1.ndb.shortcut_delete_all_request, request)

    def test_shortcut_confirmation_preserves_pending_for_direct_confirmation(self):
        self.register("a", "상태")
        self.register("확정", "줄임말 모두 삭제 확인")
        before = self.char1.profile_snapshot()
        self.assertIn("각각 직접 입력", self.run_raw("확정"))
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        self.run_raw("줄임말 모두 삭제")
        request = deepcopy(self.char1.ndb.shortcut_delete_all_request)
        self.assertIn("각각 직접 입력", self.run_raw("확정"))
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.char1.ndb.shortcut_delete_all_request, request)
        self.assertIn("2개", self.run_raw("줄임말 모두 삭제 확인"))
        self.assertEqual(self.saved(), {})
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)

    def test_sequence_confirmation_preserves_pending_for_direct_confirmation(self):
        self.register("a", "상태")
        self.register("b", "장비")
        before = self.char1.profile_snapshot()
        self.run_raw("줄임말 모두 삭제")
        request = deepcopy(self.char1.ndb.shortcut_delete_all_request)
        output = self.run_raw("상태, 줄임말 모두 삭제 확인 해")
        self.assertIn("체력", output)
        self.assertIn("각각 직접 입력", output)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.char1.ndb.shortcut_delete_all_request, request)
        self.assertIn("2개", self.run_raw("줄임말 모두 삭제 확인"))
        self.assertEqual(self.saved(), {})
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)

    def test_confirmation_mutation_invalidation_for_add_replace_and_delete(self):
        self.register("a", "상태")
        for mutation in ("줄임말 추가 b 장비", "줄임말 추가 a 소지품", "줄임말 삭제 b"):
            self.run_raw("줄임말 모두 삭제")
            self.run_raw(mutation)
            self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
            before = self.saved()
            self.run_raw("줄임말 모두 삭제 확인")
            self.assertEqual(self.saved(), before)

    def test_confirmation_expiry_fingerprint_refresh_and_empty_state(self):
        self.run_raw("줄임말 모두 삭제")
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        self.register("a", "상태")
        with patch("commands.command_shortcuts.monotonic", return_value=100):
            self.run_raw("줄임말 모두 삭제")
        with patch("commands.command_shortcuts.monotonic", return_value=100 + DELETE_ALL_CONFIRM_TTL_SECONDS):
            self.assertIn("만료", self.run_raw("줄임말 모두 삭제 확인"))
        self.assertEqual(self.saved(), {"a": ["상태"]})
        self.run_raw("줄임말 모두 삭제")
        self.char1.change(lambda p: p["command_shortcuts"].update(b=["소지품"]))
        self.assertIn("변경", self.run_raw("줄임말 모두 삭제 확인"))
        with patch("commands.command_shortcuts.monotonic", return_value=200):
            self.run_raw("줄임말 모두 삭제")
        with patch("commands.command_shortcuts.monotonic", return_value=210):
            self.run_raw("줄임말 모두 삭제")
        self.assertEqual(self.char1.ndb.shortcut_delete_all_request["requested_at"], 210)
        with patch("commands.command_shortcuts.monotonic", return_value=220):
            self.run_raw("줄임말 모두 삭제 확인")
        self.assertEqual(self.saved(), {})

    def test_confirmation_character_isolation_and_logout_shutdown_invalidation(self):
        self.register("a", "상태")
        self.register("b", "장비", self.char2)
        self.run_raw("줄임말 모두 삭제")
        self.run_raw("줄임말 모두 삭제 확인", self.char2)
        self.assertEqual(self.saved(self.char2), {"b": ["장비"]})
        self.assertIsNotNone(self.char1.ndb.shortcut_delete_all_request)
        self.run_raw("줄임말 모두 삭제 확인")
        self.assertEqual(self.saved(), {})
        for hook in ("at_post_unpuppet", "at_server_shutdown"):
            self.register("a", "상태")
            self.run_raw("줄임말 모두 삭제")
            with patch("evennia.objects.objects.DefaultCharacter." + hook), patch.object(self.char1, "leave_combat"):
                getattr(self.char1, hook)()
            self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
            self.run_raw("줄임말 모두 삭제 확인")
            self.assertEqual(self.saved(), {"a": ["상태"]})
            self.run_raw("줄임말 삭제 a")

    def test_system_shortcuts_help_engine_and_unknown_regressions(self):
        for raw in ("상", "능", "기", "장", "소"):
            self.assertNotIn("대상 뒤에 행동", self.run_raw(raw))
        self.run_raw("ㅂ")
        self.assertEqual(self.char1.zone, "grass")
        self.run_raw("ㄴ")
        self.assertEqual(self.char1.zone, "dock")
        self.run_raw("ㄷ")
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.run_raw("ㅅ")
        self.assertEqual(self.char1.zone, "dock")
        for query in ("해 도움말", "줄임말 도움말"):
            self.assertIn("사용법", self.run_raw(query))
        self.assertIn("대상 뒤에 행동", self.run_raw("없는명령"))
        commands = CharacterCmdSet()
        management = Command(key="@관리", locks="cmd:all()")
        commands.add(management)
        match = cmdparser("@관리 대상 공격", commands, self.char1)[0]
        self.assertEqual(match[0], "@관리")
        self.assertEqual(match[1].strip(), "대상 공격")
        self.assertIs(match[2].func.__func__, management.func.__func__)
        for raw in ("connect user password", "create user password"):
            commands = UnloggedinCmdSet()
            self.assertEqual(cmdparser(raw, commands, self.char1), default_parser(raw, commands, self.char1))
