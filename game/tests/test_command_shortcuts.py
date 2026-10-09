"""실제 dispatcher와 DB를 통과하는 개인 줄임말/묶음/확인 회귀."""

from copy import deepcopy
from unittest.mock import Mock, patch

from commands.default_cmdsets import CharacterCmdSet, UnloggedinCmdSet
from commands.shortcuts import DELETE_ALL_CONFIRM_TTL_SECONDS
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
        self.enterContext(patch("typeclasses.explorers.time",
                                return_value=self.char1.profile_snapshot()["recovery"]["updated_at"]))
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
        output = self.run_raw(f"{name} {definition} 줄임말", player)
        self.assertIn("추가했습니다", output)

    def test_purchase_then_wield_and_location_specific_commands_run_sequentially(self):
        self.char1.location = self.rooms["weapon_shop"]
        self.char1.change(lambda p: p.update(credits=100))
        self.run_raw("절단마체테 구매, 탐사용 벌목도 해제, 절단마체테 무장 해")
        profile = self.char1.profile_snapshot()
        self.assertEqual(profile["inventory"]["cutting_machete"], 1)
        self.assertEqual(profile["equipment"]["weapon"], "cutting_machete")
        self.assertEqual(profile["credits"], 45)
        self.run_raw("귀환, 승강기, 5층, 동, 북 해")
        self.assertEqual(self.char1.zone, "weapon_shop")

    def test_large_variable_segments_stop_lazily_without_parser_amplification(self):
        from commands.shortcuts import MAX_INTERMEDIATE_CHARACTERS
        from server.conf.cmdparser import select_command

        self.register("증폭", "$*" * 1000)
        before = deepcopy(self.char1.profile_snapshot())
        with patch("server.conf.cmdparser.select_command", wraps=select_command) as selected:
            self.assertIn("허용 크기", self.run_raw("x" * 2000 + " 증폭"))
        self.assertLessEqual(max(len(call.args[0]) for call in selected.call_args_list),
                             MAX_INTERMEDIATE_CHARACTERS)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.register("부분", "귀환, $*$* 해")
        self.assertIn("허용 크기", self.run_raw("x" * 2000 + " 부분"))
        self.assertEqual(self.char1.zone, "support_roof")
        self.assertIsNone(self.char1.ndb.shortcut_execution)

    def test_nested_and_global_substitutions_share_bounded_rendering(self):
        from commands.aliases import ARGUMENT_SHORTCUTS

        self.register("말검", "$* 말")
        self.register("중간", "$*$* 말검")
        self.assertIn("허용 크기", self.run_raw("x" * 1100 + " 중간"))
        self.assertIn("1,000", self.run_raw("x" * 1001 + " 말검"))
        with patch.dict(ARGUMENT_SHORTCUTS, {"gsize": "$*" * 1000}):
            self.assertIn("허용 크기", self.run_raw("x" * 2000 + " gsize"))
        self.char1.change(lambda p: p.update(command_shortcuts={
            **{f"a{i}": "$* a" + str(i+1) for i in range(4)}, "a4": "$* 말"}))
        with patch.object(self.char2, "msg") as observer:
            self.run_raw("짧은인자 a0")
        self.assertIn("짧은인자", str(observer.call_args_list))

    def ambiguity_cmdset(self, handler=None):
        from commands.command_shortcuts import Sequence

        calls = []
        class Regular(Command):
            key = "일반후보"
            aliases = ("겹침",)
            input_style = "target"
            def func(self):
                calls.append("regular")
        class Bundle(Sequence):
            key = "묶음후보"
            aliases = ("겹침",)
        commands = CmdSet(key="AmbiguityReview")
        commands.priority = 100
        commands.duplicates = True
        commands.add(Regular(locks="cmd:all()"))
        commands.add(Bundle(locks="cmd:all()"), allow_duplicates=True)
        if handler:
            commands.add(handler)
        return commands, calls

    def test_custom_multimatch_cannot_select_or_wait_inside_execution(self):
        from evennia.commands.cmdhandler import CMD_MULTIMATCH

        for progressive in (False, True):
            called = []
            handler = Command(key=CMD_MULTIMATCH, locks="cmd:all()")
            def choose():
                called.append(True)  # 안전 확인 없이 후보 실행을 시작할 수 있는 지점
            def wait():
                called.append(True)
                yield "선택?"
            handler.func = wait if progressive else choose
            commands, calls = self.ambiguity_cmdset(handler)
            self.char1.cmdset.add(commands)
            self.char1.change(lambda p: p.update(command_shortcuts={"점검": "겹침, 귀환 해"}))
            self.run_raw("점검")
            self.assertEqual(called, [])
            self.assertEqual(calls, [])
            self.assertEqual(self.char1.zone, "dock")
            self.assertIsNone(self.char1.ndb.shortcut_execution)
            self.char1.cmdset.remove(commands.key)

    def test_default_multimatch_only_lists_candidates_then_continues(self):
        commands, calls = self.ambiguity_cmdset()
        self.char1.cmdset.add(commands)
        self.char1.change(lambda p: p.update(command_shortcuts={"점검": "겹침, 귀환 해"}))
        output = self.run_raw("점검")
        self.assertIn("겹침-1", output)
        self.assertIn("겹침-2", output)
        self.assertEqual(calls, [])
        self.assertEqual(self.char1.zone, "support_roof")
        self.char1.location = self.rooms["dock"]
        self.run_raw("일반후보, 귀환 해")  # 최종 단일 일반 후보는 묶음 후보와 독립
        self.assertEqual(calls, ["regular"])
        self.char1.location = self.rooms["dock"]
        self.char1.change(lambda p: p.update(command_shortcuts={"선택": "묶음후보, 귀환 해"}))
        self.assertIn("새 묶음", self.run_raw("선택"))
        self.assertEqual(self.char1.zone, "dock")

    def test_dynamic_multimatch_appears_only_after_previous_command_finishes(self):
        commands, calls = self.ambiguity_cmdset()
        add = Command(key="후보추가", locks="cmd:all()")
        add.func = lambda: self.char1.cmdset.add(commands)
        setup = CmdSet(key="DynamicAmbiguityReview")
        setup.add(add)
        self.char1.cmdset.add(setup)
        output = self.run_raw("후보추가, 겹침, 귀환 해")
        self.assertIn("겹침-1", output)
        self.assertIn("겹침-2", output)
        self.assertEqual(calls, [])
        self.assertEqual(self.char1.zone, "support_roof")

    def test_async_helper_with_explicit_contract_is_rejected_before_side_effects(self):
        work = []
        gate = Deferred()
        def helper():
            work.append("started")
            return gate
        command = Command(key="도우미검사", locks="cmd:all()")
        command.shortcut_completion_guaranteed = False
        command.func = lambda: helper()
        commands = CmdSet(key="AsyncHelperReview")
        commands.add(command)
        self.char1.cmdset.add(commands)
        output = self.run_raw("도우미검사, 귀환 해")
        self.assertIn("완료", output)
        self.assertEqual(work, [])
        self.assertFalse(gate.called)
        self.assertEqual(self.char1.zone, "dock")

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
            self.char1.cmdset.remove(commands.key)

    def test_gameplay_failure_and_unknown_command_continue(self):
        self.char1.change(lambda p: p["inventory"].pop("bandage"))
        output = self.run_raw("붕대 사용, 없는명령, 상태 해")
        self.assertIn("대상 뒤에 행동", output)
        self.assertIn("체력", output)

    def test_malformed_or_expansion_error_executes_nothing(self):
        fixed_now = self.char1.profile_snapshot()["recovery"]["updated_at"]
        # 명령 거절과 무관한 자연회복 경계가 profile 불변 비교에 섞이지 않게 한다.
        self.enterContext(patch("typeclasses.explorers.time", return_value=fixed_now))
        for raw in ("귀환 해", "귀환,, 상태 해", ", 귀환 해", "귀환, 상태, 해"):
            before = deepcopy(self.char1.profile_snapshot())
            self.run_raw(raw)
            self.assertEqual(self.char1.zone, "dock")
            self.assertEqual(self.char1.profile_snapshot(), before)
        self.char1.change(lambda p: p.update(command_shortcuts={"순환": "순환"}))
        self.assertIn("순환", self.run_raw("귀환, 순환 해"))
        self.assertEqual(self.char1.zone, "support_roof")

    def test_comma_chat_raw_and_shortcut_remains_one_say(self):
        for raw in ("안녕, 반가워 말", "'안녕, 반가워"):
            with patch.object(self.char2, "msg") as other:
                self.run_raw(raw)
                self.assertEqual(other.call_count, 1)
                self.assertEqual(str(other.call_args.args[0]), f"{self.char1.key}: 안녕, 반가워")
        self.register("인사", "안녕, 반가워 말")
        self.assertEqual(self.saved()["인사"], "안녕, 반가워 말")
        with patch.object(self.char2, "msg") as other:
            self.run_raw("인사")
            self.assertEqual(other.call_count, 1)
            self.assertEqual(str(other.call_args.args[0]), f"{self.char1.key}: 안녕, 반가워")

    def test_registration_list_nested_sequence_and_exact_matching(self):
        self.register()
        self.assertEqual(self.saved()["점검"], "상태, 장비, 소지품 해")
        self.register("출발", "점검, 귀환 해")
        output = self.run_raw("점검")
        self.assertIn("체력", output)
        self.assertIn("장비", output)
        self.assertIn("소지품", output)
        self.run_raw("출발")
        self.assertEqual(self.char1.zone, "support_roof")
        self.run_raw("점검, 승강기, 2층 해")
        self.assertEqual(self.char1.zone, "support_2f_c")
        self.assertIn("점검 [활성] = 상태, 장비, 소지품 해", self.run_raw("줄임말"))
        self.char2.location = self.char1.location
        with patch.object(self.char2, "msg") as other:
            self.run_raw("점검 말")
            self.assertEqual(str(other.call_args.args[0]), f"{self.char1.key}: 점검")

    def test_persistence_is_character_local_and_parser_read_does_not_save(self):
        self.register("장확", "장비")
        self.assertEqual(deserialize(self.char1.db.profile)["command_shortcuts"], {"장확": "장비"})
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

    def test_reserved_names_and_invalid_local_syntax_do_not_replace_data(self):
        self.register("a", "b")
        for name in ("상태", "공격", "해", "줄임말", "ㅂ", "look", "quit", "connect", "n", "2층", "4층", "5층", "계단", "emit",
                     "북동", "남동", "남서", "북서", "ne", "se", "sw", "nw"):
            before = self.saved()
            self.run_raw(f"{name} 소지품 줄임말")
            self.assertEqual(self.saved(), before, name)
        before = self.saved()
        for raw in ("a $10 줄임말", "a 상태,, 장비 해 줄임말"):
            self.run_raw(raw)
            self.assertEqual(self.saved(), before)
        self.run_raw("a 장비 줄임말")
        self.assertEqual(self.saved()["a"], "장비")

    def test_runtime_real_and_locked_command_precedence_over_personal(self):
        self.char1.change(lambda p: p.update(command_shortcuts={"점검": "귀환", "상태": "귀환", "상": "귀환"}))
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

    def test_snapshot_does_not_expand_a_definition_created_mid_sequence(self):
        output = self.run_raw("소지품, 새것 상태 줄임말, 새것 해")
        self.assertEqual(self.saved(), {"새것": "상태"})
        self.assertNotIn("체력", output)
        self.assertIn("대상 뒤에 행동", output)
        self.assertIn("체력", self.run_raw("새것"))

    def test_engine_progressive_input_is_rejected_when_selected_after_move(self):
        held = Command(key="입력대화", locks="cmd:all()")

        def prompt():
            yield "다음 입력"

        held.func = prompt
        commands = CmdSet()
        commands.add(held)
        self.char1.cmdset.add(commands)
        output = self.run_raw("귀환, 입력대화 해")
        self.assertIn("밖에서 실행", output)
        self.assertEqual(self.char1.zone, "support_roof")

    def test_individual_delete_does_not_cascade_and_everybody_name_is_not_all_delete(self):
        self.register("모두", "상태")
        self.register("점검", "모두")
        self.run_raw("모두 해지")
        self.assertEqual(self.saved(), {"점검": "모두"})
        self.run_raw("점검 해지")
        self.assertIn("대상 뒤에 행동", self.run_raw("점검"))

    def test_confirm_alone_cannot_delete_and_valid_request_is_one_shot(self):
        self.register("a", "상태")
        self.register("b", "장비")
        before = self.saved()
        self.assertIn("먼저", self.run_raw("모두 삭제 확인 줄임말"))
        self.assertEqual(self.saved(), before)
        self.run_raw("모두 삭제 줄임말")
        self.assertEqual(self.saved(), before)
        self.assertIsNotNone(self.char1.ndb.shortcut_delete_all_request)
        self.assertIn("2개", self.run_raw("모두 삭제 확인 줄임말"))
        self.assertEqual(self.saved(), {})
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        self.register("c", "소지품")
        self.run_raw("모두 삭제 확인 줄임말")
        self.assertEqual(self.saved(), {"c": "소지품"})

    def test_sequence_cannot_request_and_confirm_all_deletion(self):
        self.register("a", "상태")
        self.register("b", "장비")
        before = self.char1.profile_snapshot()
        # 두 요청 모두 간접 입력이다. 전체 profile 불변을 유지한다.
        output = self.run_raw("모두 삭제 줄임말, 모두 삭제 확인 줄임말 해")
        self.assertIn("각각 직접 입력", output)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        output = self.run_raw("상태, 모두 삭제 줄임말, 모두 삭제 확인 줄임말 해")
        self.assertIn("체력", output)
        self.assertEqual(output.count("각각 직접 입력"), 2)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)

    def test_shortcut_cannot_request_and_confirm_all_deletion(self):
        self.register("a", "상태")
        self.register("초기화", "모두 삭제 줄임말, 모두 삭제 확인 줄임말 해")
        before = self.char1.profile_snapshot()
        output = self.run_raw("초기화")
        self.assertEqual(output.count("각각 직접 입력"), 2)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIn("초기화", self.saved())
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)

    def test_indirect_request_cannot_create_or_replace_pending(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.register("삭제요청", "모두 삭제 줄임말")
        before = self.char1.profile_snapshot()
        for raw in ("삭제요청", "상태, 모두 삭제 줄임말 해"):
            self.assertIn("각각 직접 입력", self.run_raw(raw))
            self.assertEqual(self.char1.profile_snapshot(), before)
            self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        self.run_raw("모두 삭제 줄임말")
        request = deepcopy(self.char1.ndb.shortcut_delete_all_request)
        for raw in ("삭제요청", "상태, 모두 삭제 줄임말 해"):
            self.assertIn("각각 직접 입력", self.run_raw(raw))
            self.assertEqual(self.char1.profile_snapshot(), before)
            self.assertEqual(self.char1.ndb.shortcut_delete_all_request, request)

    def test_shortcut_confirmation_preserves_pending_for_direct_confirmation(self):
        # 확인 입력의 무변경 계약을 실제 시각의 recovery 경계와 분리한다.
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.register("a", "상태")
        self.register("확정", "모두 삭제 확인 줄임말")
        before = self.char1.profile_snapshot()
        self.assertIn("각각 직접 입력", self.run_raw("확정"))
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        self.run_raw("모두 삭제 줄임말")
        request = deepcopy(self.char1.ndb.shortcut_delete_all_request)
        self.assertIn("각각 직접 입력", self.run_raw("확정"))
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.char1.ndb.shortcut_delete_all_request, request)
        self.assertIn("2개", self.run_raw("모두 삭제 확인 줄임말"))
        self.assertEqual(self.saved(), {})
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)

    def test_sequence_confirmation_preserves_pending_for_direct_confirmation(self):
        self.register("a", "상태")
        self.register("b", "장비")
        before = self.char1.profile_snapshot()
        self.run_raw("모두 삭제 줄임말")
        request = deepcopy(self.char1.ndb.shortcut_delete_all_request)
        output = self.run_raw("상태, 모두 삭제 확인 줄임말 해")
        self.assertIn("체력", output)
        self.assertIn("각각 직접 입력", output)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.char1.ndb.shortcut_delete_all_request, request)
        self.assertIn("2개", self.run_raw("모두 삭제 확인 줄임말"))
        self.assertEqual(self.saved(), {})
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)

    def test_confirmation_mutation_invalidation_for_add_replace_and_delete(self):
        self.register("a", "상태")
        for mutation in ("b 장비 줄임말", "a 소지품 줄임말", "b 해지"):
            self.run_raw("모두 삭제 줄임말")
            self.run_raw(mutation)
            self.assertIsNotNone(self.char1.ndb.shortcut_delete_all_request)
            before = self.saved()
            self.assertIn("변경", self.run_raw("모두 삭제 확인 줄임말"))
            self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
            self.assertEqual(self.saved(), before)

    def test_confirmation_expiry_fingerprint_refresh_and_empty_state(self):
        self.run_raw("모두 삭제 줄임말")
        self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
        self.register("a", "상태")
        with patch("commands.command_shortcuts.monotonic", return_value=100):
            self.run_raw("모두 삭제 줄임말")
        with patch("commands.command_shortcuts.monotonic", return_value=100 + DELETE_ALL_CONFIRM_TTL_SECONDS):
            self.assertIn("만료", self.run_raw("모두 삭제 확인 줄임말"))
        self.assertEqual(self.saved(), {"a": "상태"})
        self.run_raw("모두 삭제 줄임말")
        self.char1.change(lambda p: p["command_shortcuts"].update(b="소지품"))
        self.assertIn("변경", self.run_raw("모두 삭제 확인 줄임말"))
        with patch("commands.command_shortcuts.monotonic", return_value=200):
            self.run_raw("모두 삭제 줄임말")
        with patch("commands.command_shortcuts.monotonic", return_value=210):
            self.run_raw("모두 삭제 줄임말")
        self.assertEqual(self.char1.ndb.shortcut_delete_all_request["requested_at"], 210)
        with patch("commands.command_shortcuts.monotonic", return_value=220):
            self.run_raw("모두 삭제 확인 줄임말")
        self.assertEqual(self.saved(), {})

    def test_confirmation_character_isolation_and_logout_shutdown_invalidation(self):
        self.register("a", "상태")
        self.register("b", "장비", self.char2)
        self.run_raw("모두 삭제 줄임말")
        self.run_raw("모두 삭제 확인 줄임말", self.char2)
        self.assertEqual(self.saved(self.char2), {"b": "장비"})
        self.assertIsNotNone(self.char1.ndb.shortcut_delete_all_request)
        self.run_raw("모두 삭제 확인 줄임말")
        self.assertEqual(self.saved(), {})
        for hook in ("at_post_unpuppet", "at_server_shutdown"):
            self.register("a", "상태")
            self.run_raw("모두 삭제 줄임말")
            with patch("evennia.objects.objects.DefaultCharacter." + hook), patch.object(self.char1, "leave_combat"):
                getattr(self.char1, hook)()
            self.assertIsNone(self.char1.ndb.shortcut_delete_all_request)
            self.run_raw("모두 삭제 확인 줄임말")
            self.assertEqual(self.saved(), {"a": "상태"})
            self.run_raw("a 해지")

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


    def test_postfix_management_preserves_original_and_help_priority(self):
        self.run_raw("정찰   $1 보기,  상태 해   줄임말")
        self.assertEqual(self.saved(), {"정찰": "$1 보기,  상태 해"})
        self.assertIn("$1 보기,  상태 해", self.run_raw("정찰 줄임말"))
        self.run_raw("정찰 장비 줄임말")
        self.assertEqual(self.saved(), {"정찰": "장비"})
        for raw in ("줄임말 도움말", "해지 도움말"):
            self.assertIn("사용법", self.run_raw(raw))
        self.assertEqual(self.run_raw("전역 줄임말"), self.run_raw("단축어"))
        self.run_raw("정찰 해지")
        self.assertEqual(self.saved(), {})

    def test_store_count_length_and_atomic_replacement_boundaries(self):
        self.char1.change(lambda p: p.update(command_shortcuts={f"a{i}": None for i in range(99)}))
        self.register("last", "a" * 2000)
        before = self.saved()
        self.assertIn("100개", self.run_raw("extra 상태 줄임말"))
        self.assertEqual(self.saved(), before)
        self.assertIn("2,000", self.run_raw("last " + "a" * 2001 + " 줄임말"))
        self.assertEqual(self.saved(), before)
        self.run_raw("last 상태 줄임말")
        self.assertEqual(self.saved()["last"], "상태")
        self.char1.change(lambda p: p["command_shortcuts"].update(over=None))
        self.run_raw("last 장비 줄임말")
        self.assertEqual(len(self.saved()), 101)
        self.run_raw("last 해지")
        self.assertEqual(len(self.saved()), 100)

    def test_unique_casefold_replacement_and_collisions_preserve_originals(self):
        self.char1.change(lambda p: p.update(command_shortcuts={"Gear": ["장비"]}))
        self.run_raw("gear $10 줄임말")
        self.assertEqual(self.saved(), {"Gear": ["장비"]})
        self.run_raw("gear 상태 줄임말")
        self.assertEqual(self.saved(), {"gear": "상태"})
        self.char1.change(lambda p: p.update(command_shortcuts={"Gear": ["장비"], "gear": "상태", "ok": "장비"}))
        before = self.saved()
        for raw in ("gear", "Gear 상태 줄임말", "gear 줄임말", "GEAR 해지"):
            self.assertIn("정규화", self.run_raw(raw))
            self.assertEqual(self.saved(), before)
        self.assertIn("정규화 충돌", self.run_raw("줄임말"))
        self.assertIn("장비", self.run_raw("ok"))

    def test_unsupported_legacy_store_does_not_break_real_commands_or_save_on_read(self):
        for store in (None, [], "damaged", {1: "상태"}):
            profile = self.char1.profile_snapshot()
            profile.update(version=7, command_shortcuts=store)
            self.char1.db.profile = profile
            before = deserialize(self.char1.db.profile)
            with patch.object(self.char1, "save_profile") as save:
                self.assertIn("오류", self.run_raw("줄임말"))
                self.assertIn("오류", self.run_raw("x 상태 줄임말"))
                save.assert_not_called()
            self.assertEqual(deserialize(self.char1.db.profile), before)
            self.assertIn("체력", self.run_raw("상태"))
            self.assertEqual(self.saved(), store)

    def test_legacy_preview_is_bounded_without_changing_stored_data(self):
        self.char1.change(lambda p: p.update(command_shortcuts={
            **{f"a{i}": ["x" * 9000] for i in range(103)}, "bad name": None}))
        before = deserialize(self.char1.db.profile)
        with patch.object(self.char1, "save_profile") as save:
            listing = self.run_raw("줄임말")
            detail = self.run_raw("a0 줄임말")
            save.assert_not_called()
        self.assertIn("비활성", listing)
        self.assertIn("4개 항목을 생략", listing)
        self.assertNotIn("x" * 121, listing)
        self.assertNotIn("x" * 2001, detail)
        self.assertIn("생략", detail)
        self.assertEqual(deserialize(self.char1.db.profile), before)
        self.assertIn("비활성", self.run_raw("a0"))

    def test_snapshot_queries_and_clear_preserve_entire_other_profile(self):
        self.char1.change(lambda p: p.update(command_shortcuts={"string": "장비", "list": ["상태"], "off": None}))
        before = deepcopy(self.char1.profile_snapshot())
        self.run_raw("모두 삭제 줄임말")
        self.run_raw("모두 삭제 확인 줄임말")
        self.assertEqual(self.char1.profile_snapshot(), {**before, "command_shortcuts": {}})

    def test_variable_derived_deletion_cannot_consume_or_replace_pending(self):
        self.register("실행", "$*")
        self.run_raw("모두 삭제 줄임말")
        pending = deepcopy(self.char1.ndb.shortcut_delete_all_request)
        before = self.saved()
        for raw in ("모두 삭제 줄임말 실행", "모두 삭제 확인 줄임말 실행"):
            self.assertIn("직접 입력", self.run_raw(raw))
            self.assertEqual(self.char1.ndb.shortcut_delete_all_request, pending)
            self.assertEqual(self.saved(), before)
        self.run_raw("모두 삭제 확인 줄임말")
        self.assertEqual(self.saved(), {})

    def test_cycles_register_and_sibling_calls_do_not_share_reference_paths(self):
        self.register("A", "B")
        self.register("B", "A")
        self.assertIn("순환", self.run_raw("a"))
        self.run_raw("b 상태 줄임말")
        self.run_raw("a b, b 해 줄임말")
        self.assertEqual(self.run_raw("a").count("체력"), 2)
        self.run_raw("a 상태, a 해 줄임말")
        result = self.run_raw("a")
        self.assertIn("체력", result)
        self.assertIn("순환", result)
        self.assertIsNone(self.char1.ndb.shortcut_execution)

    def test_variable_action_changes_literals_chat_and_no_new_sequence(self):
        self.register("동작", "북 $1")
        self.register("실행", "$*")
        self.register("채팅", "$* 말")
        self.register("혼합", "$1에게 $* 말")
        self.register("달러", "$$You() $$1 $$* 말")
        self.assertIn("체력", self.run_raw("상태 실행"))
        self.assertNotIn("대상 뒤에 행동", self.run_raw("보기 동작"))
        self.assertEqual(self.char1.zone, "dock")
        before = deepcopy(self.char1.profile_snapshot())
        self.assertIn("새 묶음", self.run_raw("귀환, 상태 해 실행"))
        self.assertEqual(self.char1.profile_snapshot(), before)
        for raw, expected in (("상태, 장비 해 채팅", "상태, 장비 해"),
                              ("철수 20칩 혼합", "철수에게 철수 20칩"),
                              ("$1 $* 채팅", "$1 $*"), ("달러", "$You() $1 $*")):
            with patch.object(self.char2, "msg") as other:
                self.run_raw(raw)
                self.assertIn(expected, str(other.call_args_list))

    def test_argument_errors_abort_remainder_but_prior_effects_remain(self):
        self.register("인자", "$1 보기")
        self.register("없음", "상태")
        for raw in ("인자", "a b 인자", "a 없음", "x" * 2001 + " 인자"):
            before = deepcopy(self.char1.profile_snapshot())
            self.run_raw(raw)
            self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIn("부족", self.run_raw("귀환, 인자, 승강기 해"))
        self.assertEqual(self.char1.zone, "support_roof")
        self.assertIsNone(self.char1.ndb.shortcut_execution)

    def test_snapshot_survives_modify_and_delete_until_next_top_input(self):
        self.register("keep", "상태")
        output = self.run_raw("keep 장비 줄임말, keep, keep 해지, keep 해")
        self.assertEqual(output.count("체력"), 2)
        self.assertEqual(self.saved(), {})
        self.assertIn("대상 뒤에 행동", self.run_raw("keep"))
        self.assertIn("체력", self.run_raw("상태, bad $10 줄임말, 상태 해"))
        self.assertNotIn("bad", self.saved())

    def test_dynamic_room_cmdsets_override_snapshot_only_when_actually_selected(self):
        calls = []
        commands = CmdSet()
        real = Command(key="현장검사", locks="cmd:all()")
        real.func = lambda: calls.append("real")
        commands.add(real)
        self.rooms["grass"].cmdset.add(commands)
        self.register("현장검사", "장비")
        self.register("점검", "북, 현장검사, 남, 현장검사 해")
        output = self.run_raw("점검")
        self.assertEqual(calls, ["real"])
        self.assertIn("장비", output)
        self.assertEqual(self.char1.zone, "dock")
        # 선택되지 않는 잘못된/순환 정의는 새 Room의 실제 명령에 영향을 주지 않는다.
        self.run_raw("현장검사 현장검사 줄임말")
        self.run_raw("북, 현장검사 해")
        self.assertEqual(calls, ["real", "real"])

    def test_locked_actual_commands_never_fall_back_to_personal(self):
        from commands.base import GameCommand

        class Locked(GameCommand):
            key = "잠금"
            input_style = "target"
            aliases = ["여러 단어"]
            locks = "cmd:false()"

            def run(self):
                self.caller.location = self.rooms["grass"]

        commands = CmdSet()
        commands.add(Locked())
        self.char1.cmdset.add(commands)
        self.char1.change(lambda p: p.update(command_shortcuts={"잠금": "귀환", "단어": "$* 말"}))
        for raw in ("잠금", "철수 잠금", "여러 단어", "철수 여러 단어", "잠금, 상태 해", "철수 잠금, 상태 해"):
            with patch.object(self.char2, "msg") as other:
                self.run_raw(raw)
            other.assert_not_called()
            self.assertEqual(self.char1.zone, "dock")
        engine = Command(key="@잠금엔진", locks="cmd:false()")
        commands.add(engine)
        self.char1.cmdset.add(commands)
        self.char1.change(lambda p: p["command_shortcuts"].update(잠금엔진="귀환"))
        self.run_raw("@잠금엔진")
        self.assertEqual(self.char1.zone, "dock")

    def test_dynamic_locked_and_progressive_commands_block_chosen_path(self):
        commands = CmdSet()
        locked = Command(key="현장검사", locks="cmd:false()")
        commands.add(locked)
        self.rooms["grass"].cmdset.add(commands)
        self.register("현장검사", "귀환")
        self.run_raw("북, 현장검사, 상태 해")
        self.assertEqual(self.char1.zone, "grass")
        self.char1.location = self.rooms["dock"]
        progressive = Command(key="현장검사", locks="cmd:all()")
        def wait():
            yield "다음 입력"
        progressive.func = wait
        self.rooms["grass"].cmdset.remove(commands.key)
        # 새 동적 CmdSet의 구조 identity도 갱신한다(6.1 merge cache의 공식 fingerprint).
        commands = CmdSet(key="ProgressiveFixture", cmdsetobj=self.rooms["grass"])
        commands.add(progressive)
        self.rooms["grass"].cmdset.add(commands)
        output = self.run_raw("북, 현장검사, 남 해")
        self.assertIn("밖에서 실행", output)
        self.assertEqual(self.char1.zone, "grass")

    def test_exact_multiword_action_alias_uses_real_command_with_empty_arguments(self):
        from commands.base import GameCommand

        calls = []
        class Actual(GameCommand):
            key = "실제검사"
            aliases = ["여러 단어"]
            input_style = "target"
            def run(self):
                calls.append(self.args)
        commands = CmdSet(key="ExactMultiwordFixture")
        commands.add(Actual())
        self.char1.cmdset.add(commands)
        self.char1.change(lambda p: p.update(command_shortcuts={"단어": "$* 말"}))
        with patch.object(self.char2, "msg") as other:
            self.run_raw("여러 단어")
            self.run_raw("철수 여러 단어")
            self.run_raw("여러 단어, 상태 해")
        other.assert_not_called()
        self.assertEqual(calls, ["", "철수", ""])

    def test_depth_five_and_six_are_checked_on_actual_selected_path(self):
        self.char1.change(lambda p: p.update(command_shortcuts={
            **{f"a{i}": f"a{i+1}" for i in range(4)}, "a4": "상태"}))
        self.assertIn("체력", self.run_raw("a0"))
        self.char1.change(lambda p: p["command_shortcuts"].update(a4="a5", a5="상태"))
        output = self.run_raw("a0")
        self.assertIn("5단계", output)
        self.assertNotIn("체력", output)
        self.assertIsNone(self.char1.ndb.shortcut_execution)

    def test_attempts_include_every_leaf_and_stop_before_eleventh(self):
        calls = []
        command = Command(key="계수검사", locks="cmd:all()")
        command.func = lambda: calls.append("engine")
        commands = CmdSet()
        commands.add(command)
        self.char1.cmdset.add(commands)
        self.register("점검", ", ".join(["계수검사"] * 11) + " 해")
        self.assertIn("11번째", self.run_raw("점검"))
        self.assertEqual(len(calls), 10)
        self.char1.location = self.rooms["hq_concourse"]
        self.char1.change(lambda p: p.update(command_shortcuts={"분기": "계수검사"}))
        leaves = ["계단", "나가기", "'안녕", "줄임말", "분기", "없는명령", "bad $10 줄임말",
                  "상", "장", "상태", "귀환"]
        self.assertIn("11번째", self.run_raw(", ".join(leaves) + " 해"))
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.assertEqual(len(calls), 11)

    def test_final_character_sum_and_direct_bundle_input_length_boundaries(self):
        calls = []
        class Record(Command):
            key = "기록검사"
            def func(self):
                calls.append(self.raw_string)
        commands = CmdSet()
        commands.add(Record())
        self.char1.cmdset.add(commands)
        size = 1000 - len("기록검사 ")
        self.run_raw("기록검사 " + "x" * size + ", 상태 해")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 1000)
        self.assertIn("1,000", self.run_raw("기록검사 " + "x" * (size+1) + ", 상태 해"))
        self.assertEqual(len(calls), 1)
        self.assertIn("2,000", self.run_raw("x" * 2001 + ", 상태 해"))
        self.assertNotIn("2,000", self.run_raw("x" * 1995 + ", 상 해"))  # 접미 해 포함 2,000자
        self.assertIn("2,000", self.run_raw("x" * 1996 + ", 상 해"))
        # 일반 게임 채팅 전체에 새 2,000자 정책을 씌우지 않는다.
        self.assertNotIn("2,000", self.run_raw("x" * 2001 + " 말"))

    def test_global_aliases_apply_once_and_parametric_definitions_do_not_nest(self):
        from commands.aliases import ARGUMENT_SHORTCUTS, SHORTCUTS

        self.register("점검", "상, 장 해")
        output = self.run_raw("점검")
        self.assertIn("체력", output)
        self.assertIn("장비", output)
        with patch.dict(ARGUMENT_SHORTCUTS, {"gvar": "$* 말"}):
            with patch.object(self.char2, "msg") as other:
                self.run_raw("안녕, 상태 해 gvar")
            self.assertIn("안녕, 상태 해", str(other.call_args_list))
        with patch.dict(SHORTCUTS, {"once": "상"}):
            output = self.run_raw("once, 상태 해")
            self.assertEqual(output.count("체력"), 1)
        with patch.dict(ARGUMENT_SHORTCUTS, {"gvar": "$*"}):
            self.assertNotIn("장비", self.run_raw("점검 gvar, 상태 해"))


    def hold_context(self, hook="at_post_cmd"):
        gate = Deferred()
        command = Command(key="지연검사", locks="cmd:all()")
        command.func = lambda: None
        setattr(command, hook, lambda: gate)
        commands = CmdSet()
        commands.add(command)
        self.char1.cmdset.add(commands)
        return gate

    def test_same_character_duplicate_context_rejected_and_normal_input_remains_allowed(self):
        gate = self.hold_context()
        with patch.object(self.char1, "msg") as message:
            done = []
            self.char1.execute_cmd("지연검사, 귀환 해").addCallback(lambda result: done.append(True))
            active = self.char1.ndb.shortcut_execution
            self.assertEqual(active.state, active.ACTIVE)
            self.assertIn("이미", self.run_raw("상태, 장비 해"))
            self.register("개인검사", "상태")
            self.assertIn("이미", self.run_raw("개인검사"))
            self.assertIs(self.char1.ndb.shortcut_execution, active)
            self.assertIn("체력", self.run_raw("상태"))
            self.assertFalse(done)
            gate.callback(None)
            self.assertEqual(done, [True])
            self.assertEqual(self.char1.zone, "support_roof")
            self.assertIsNone(self.char1.ndb.shortcut_execution)
            self.assertEqual(active.state, active.FINISHED)
            self.assertEqual(self.char1.ndb.command_output_depth, 0)
            self.assertNotIn("실행기 오류", str(message.call_args_list))

    def test_two_sessions_share_context_and_logout_does_not_resume_in_another(self):
        from evennia import SESSION_HANDLER
        from evennia.server.serversession import ServerSession

        self.account.puppet_object(self.session, self.char1)
        other = ServerSession()
        other.init_session("telnet", ("localhost", "testmode"), SESSION_HANDLER)
        other.sessid = 901
        SESSION_HANDLER.portal_connect(other.get_sync_data())
        other = SESSION_HANDLER.get(901)
        # 두 실제 세션의 동일 캐릭터 제어를 테스트하는 격리 fixture다.
        other.account, other.puppet = self.account, self.char1
        self.addCleanup(lambda: SESSION_HANDLER.pop(901, None))
        gate = self.hold_context()
        with patch.object(self.char1, "push_prompt") as prompt, patch.object(self.char1, "msg"):
            done = []
            self.char1.execute_cmd("지연검사, 귀환 해", session=self.session).addCallback(lambda r: done.append(True))
            active = self.char1.ndb.shortcut_execution
            with patch.object(self.char1, "msg") as message:
                self.char1.execute_cmd("상태, 장비 해", session=other)
                self.assertIn("이미", str(message.call_args_list))
            self.account.unpuppet_object(self.session)
            self.assertEqual(active.state, active.FINISHED)
            self.assertIsNone(self.char1.ndb.shortcut_execution)
            prompt.reset_mock()
            gate.callback(None)
            self.assertEqual(done, [True])
            self.assertNotEqual(self.char1.zone, "support_roof")
            prompt.assert_not_called()
            self.assertEqual(self.char1.ndb.command_output_depth, 0)

    def test_session_loss_and_late_async_pre_hook_never_execute_or_prompt(self):
        from evennia import SESSION_HANDLER

        for hook in ("at_pre_cmd", "at_post_cmd"):
            self.account.puppet_object(self.session, self.char1)
            self.char1.location = self.rooms["dock"]
            gate = self.hold_context(hook)
            with patch.object(self.char1, "push_prompt") as prompt, patch.object(self.char1, "msg"):
                done = []
                self.char1.execute_cmd("지연검사, 귀환 해", session=self.session).addCallback(lambda r: done.append(True))
                session = SESSION_HANDLER.pop(self.session.sessid)
                try:
                    gate.callback(None)
                    self.assertEqual(done, [True])
                    self.assertEqual(self.char1.zone, "dock")
                    self.assertEqual(self.char1.ndb.command_output_depth, 0)
                    self.assertIsNone(self.char1.ndb.shortcut_execution)
                    prompt.assert_not_called()
                finally:
                    SESSION_HANDLER[self.session.sessid] = session

    def test_actual_logout_in_sequence_cancels_remaining_commands(self):
        from evennia import SESSION_HANDLER

        self.account.puppet_object(self.session, self.char1)
        real_disconnect = self.backups[1]  # Evennia 기본 test fixture는 disconnect를 Mock한다.
        def disconnect(session, reason):
            return real_disconnect(session, reason, sync_portal=False)
        try:
            with patch.object(SESSION_HANDLER, "disconnect", side_effect=disconnect), patch.object(
                    self.char1, "msg"), patch.object(self.char1, "push_prompt") as prompt:
                self.char1.execute_cmd("종료, 귀환 해", session=self.session)
            self.assertNotEqual(self.char1.zone, "support_roof")
            self.assertIsNone(self.char1.ndb.shortcut_execution)
            self.assertEqual(self.char1.ndb.command_output_depth, 0)
            prompt.assert_not_called()
        finally:
            SESSION_HANDLER[self.session.sessid] = self.session  # 기본 fixture teardown이 소유한다.

    def test_selected_coroutine_and_nonawaited_deferred_func_are_rejected(self):
        async def coroutine():
            raise AssertionError("coroutine must not start")
        gate = Deferred()
        calls = []
        def detached():
            calls.append("started")
            return gate
        for function in (coroutine, detached):
            command = Command(key="비동기검사", locks="cmd:all()")
            command.func = function
            commands = CmdSet()
            commands.add(command)
            self.char1.cmdset.add(commands)
            self.char1.location = self.rooms["dock"]
            self.assertIn("완료", self.run_raw("귀환, 비동기검사, 승강기 해"))
            self.assertEqual(self.char1.zone, "support_roof")
            self.assertEqual(calls, [])
            self.assertIsNone(self.char1.ndb.shortcut_execution)
            self.assertEqual(self.char1.ndb.command_output_depth, 0)

    def test_prompt_once_on_success_engine_error_and_async_completion(self):
        for raw in ("상태, 장비 해", "없는명령, 상태 해"):
            with patch.object(self.char1, "push_prompt") as prompt:
                self.run_raw(raw)
                prompt.assert_called_once()
                self.assertEqual(self.char1.ndb.command_output_depth, 0)
        self.register("순환", "상태, 순환 해")
        with patch.object(self.char1, "push_prompt") as prompt:
            self.assertIn("순환", self.run_raw("순환"))
            prompt.assert_called_once()
        gate = self.hold_context()
        with patch.object(self.char1, "push_prompt") as prompt, patch.object(self.char1, "msg"):
            self.char1.execute_cmd("지연검사, 상태 해")
            prompt.assert_not_called()
            gate.callback(None)
            prompt.assert_called_once()
        self.assertEqual(self.char1.ndb.command_output_depth, 0)

    def test_selected_authoritative_command_is_not_reparsed_for_dispatch(self):
        from server.conf import cmdparser as parser_module

        calls = []
        command = Command(key="정확선택", locks="cmd:all()")
        command.func = lambda: calls.append("chosen")
        commands = CmdSet()
        commands.add(command)
        self.char1.cmdset.add(commands)
        with patch.object(parser_module, "select_command", wraps=parser_module.select_command) as select:
            self.run_raw("정확선택, 상태 해")
        self.assertEqual(calls, ["chosen"])
        self.assertEqual(select.call_count, 3)  # 최상위 wrapper + 실제 두 세그먼트. 재선택 없음.

    def test_recoverable_command_errors_continue_but_dispatch_errors_stop_and_cleanup(self):
        self.assertIn("체력", self.run_raw("없는대상 보기, 상태 해"))
        calls = []
        class Broken(Command):
            key = "오류검사"
            def func(self):
                calls.append("started")
                raise RuntimeError("fixture dispatcher failure")
        commands = CmdSet()
        commands.add(Broken())
        self.char1.cmdset.add(commands)
        with patch("evennia.commands.cmdhandler._msg_err"), patch("evennia.commands.cmdhandler.logger.log_err"):
            self.run_raw("오류검사, 귀환 해")
        self.assertEqual(calls, ["started"])
        self.assertEqual(self.char1.zone, "dock")
        self.assertIsNone(self.char1.ndb.shortcut_execution)
        self.assertEqual(self.char1.ndb.command_output_depth, 0)


    def test_normal_input_during_wait_changes_next_segments_current_cmdset(self):
        gate = self.hold_context()
        calls = []
        command = Command(key="현장검사", locks="cmd:all()")
        command.func = lambda: calls.append(self.char1.zone)
        commands = CmdSet()
        commands.add(command)
        self.rooms["grass"].cmdset.add(commands)
        self.char1.execute_cmd("지연검사, 현장검사 해")
        self.run_raw("북")
        gate.callback(None)
        self.assertEqual(calls, ["grass"])
        self.assertEqual(self.char1.ndb.command_output_depth, 0)

    def test_owner_changed_without_hook_stops_late_callback(self):
        self.account.puppet_object(self.session, self.char1)
        self.char1.location = self.rooms["dock"]
        gate = self.hold_context("at_pre_cmd")
        with patch.object(self.char1, "push_prompt") as prompt, patch.object(self.char1, "msg"):
            self.char1.execute_cmd("지연검사, 귀환 해", session=self.session)
            self.session.puppet = self.char2
            try:
                gate.callback(None)
                self.assertEqual(self.char1.zone, "dock")
                self.assertIsNone(self.char1.ndb.shortcut_execution)
                self.assertEqual(self.char1.ndb.command_output_depth, 0)
                prompt.assert_not_called()
            finally:
                self.session.puppet = self.char1

    def test_unsafe_progressive_helper_and_explicit_completion_contract_block_before_func(self):
        calls = []
        def progressive():
            yield "추가 입력"
        for function, guaranteed in ((lambda: progressive(), True), (lambda: calls.append("unsafe"), False)):
            command = Command(key="위험검사", locks="cmd:all()")
            command.func = function
            command.shortcut_completion_guaranteed = guaranteed
            commands = CmdSet()
            commands.add(command)
            self.char1.cmdset.add(commands)
            self.assertIn("완료", self.run_raw("위험검사, 귀환 해"))
            self.assertEqual(calls, [])
            self.assertEqual(self.char1.zone, "dock")
            self.char1.cmdset.remove(commands.key)

    def test_failed_pre_and_post_deferreds_stop_queue_and_release_outputs(self):
        for hook in ("at_pre_cmd", "at_post_cmd"):
            gate = self.hold_context(hook)
            with patch("evennia.commands.cmdhandler._msg_err"), patch("evennia.commands.cmdhandler.logger.log_err"):
                self.char1.execute_cmd("지연검사, 귀환 해")
                gate.errback(RuntimeError("fixture hook failure"))
            self.assertEqual(self.char1.zone, "dock")
            self.assertIsNone(self.char1.ndb.shortcut_execution)
            self.assertEqual(self.char1.ndb.command_output_depth, 0)
            self.char1.cmdset.remove("DefaultCmdSet")

    def test_overlong_saved_string_and_inactive_value_abort_only_when_selected(self):
        self.char1.change(lambda p: p.update(command_shortcuts={"over": "x" * 2001, "off": None, "ok": "장비"}))
        self.assertIn("장비", self.run_raw("ok"))
        self.assertIn("2,000", self.run_raw("상태, over, 귀환 해"))
        self.assertEqual(self.char1.zone, "dock")
        self.assertIn("비활성", self.run_raw("상태, off, 귀환 해"))
        self.assertEqual(self.char1.zone, "dock")

    def test_argument_global_limits_and_no_nesting_have_same_execution_context(self):
        from commands.aliases import ARGUMENT_SHORTCUTS

        with patch.dict(ARGUMENT_SHORTCUTS, {"gvar": "$*"}):
            self.register("personal", "장비")
            self.assertIn("재확장", self.run_raw("personal gvar"))
            self.assertIn("새 묶음", self.run_raw("상태, 장비 해 gvar"))
            self.assertIn("1,000", self.run_raw("x" * 1001 + " gvar"))
            self.assertIn("2,000", self.run_raw("x" * 2001 + " gvar"))
            self.assertIsNone(self.char1.ndb.shortcut_execution)

    def test_direct_sequence_does_not_reinterpret_variable_like_user_text(self):
        with patch.object(self.char2, "msg") as message:
            self.run_raw("$1 $* 말, 상태 해")
        self.assertIn("$1 $*", str(message.call_args_list))

    def test_internal_comma_registration_rejected_without_changing_snapshot_or_store(self):
        self.register("등록기", "$* 줄임말")
        before = self.saved()
        self.assertIn("직접 입력", self.run_raw("새것 상태, 장비 해 등록기"))
        self.assertEqual(self.saved(), before)
        self.run_raw("상태, 새것 장비 줄임말 해")
        self.assertEqual(self.saved()["새것"], "장비")

    def test_engine_help_waiting_for_pages_is_selected_but_never_started(self):
        from evennia.commands.default.help import CmdHelp

        self.register("도움", "@help $1")
        with patch.object(CmdHelp, "help_more", True), patch.object(CmdHelp, "func") as function:
            self.assertIn("직접 실행", self.run_raw("장비 도움"))
            function.assert_not_called()
        with patch.object(CmdHelp, "help_more", False), patch.object(CmdHelp, "func") as function:
            self.run_raw("장비 도움")
            function.assert_called_once()
        self.assertIsNone(self.char1.ndb.shortcut_execution)
        self.assertEqual(self.char1.ndb.command_output_depth, 0)

    def test_dispatcher_reentry_in_helper_cannot_gain_direct_deletion_authority(self):
        self.register("보존", "장비")
        self.run_raw("모두 삭제 줄임말")
        pending, before = self.char1.ndb.shortcut_delete_all_request, self.saved()

        def helper(caller):
            caller.execute_cmd("모두 삭제 확인 줄임말")

        class Reentry(Command):
            key = "내부검사"
            def func(self):
                helper(self.caller)

        commands = CmdSet()
        commands.add(Reentry())
        self.char1.cmdset.add(commands)
        self.assertIn("각각 직접 입력", self.run_raw("내부검사, 상태 해"))
        self.assertEqual(self.saved(), before)
        self.assertEqual(self.char1.ndb.shortcut_delete_all_request, pending)

    def test_independent_direct_input_during_async_wait_does_not_inherit_origin(self):
        self.register("보존", "장비")
        self.run_raw("모두 삭제 줄임말")
        gate = self.hold_context("at_pre_cmd")
        self.char1.execute_cmd("지연검사, 보존 해")
        self.assertIn("모두 삭제했습니다", self.run_raw("모두 삭제 확인 줄임말"))
        self.assertEqual(self.saved(), {})
        with patch.object(self.char1, "msg") as output:
            gate.callback(None)
        self.assertIn("장비", str(output.call_args_list))
        self.assertIsNone(self.char1.ndb.shortcut_execution)
        self.assertEqual(self.char1.ndb.command_output_depth, 0)

    def test_instance_bound_hooks_use_exact_dispatched_command_not_cmdset_template(self):
        from types import MethodType

        events = []
        command = Command(key="인스턴스검사")
        def hook(instance):
            events.append((instance, instance.caller, instance.raw_string))
        for name in ("at_pre_cmd", "parse", "at_post_cmd"):
            setattr(command, name, MethodType(hook, command))
        command.func = lambda: None
        commands = CmdSet()
        commands.add(command)
        self.char1.cmdset.add(commands)
        for raw in ("인스턴스검사", "인스턴스검사, 상태 해"):
            events.clear()
            self.run_raw(raw)
            self.assertEqual(len(events), 3)
            self.assertIsNot(events[0][0], command)
            self.assertTrue(all(instance is events[0][0] and caller is self.char1 and text == "인스턴스검사"
                                for instance, caller, text in events))
            self.assertEqual(self.char1.ndb.command_output_depth, 0)

    def test_original_input_control_characters_are_not_hidden_by_engine_trim(self):
        self.register("실행", "$*")
        before = deepcopy(self.char1.profile_snapshot())
        for raw in ("상태 실행\n", "\n상태 실행", "새것\n장비 줄임말", "실행 해지\n", "상태, 장비 해\n"):
            with self.subTest(raw=raw):
                self.assertIn("제어문자", self.run_raw(raw))
                self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertIn("2,000", self.run_raw(" " * 2000 + "상태 실행"))
        self.assertEqual(self.char1.profile_snapshot(), before)

    def test_bare_async_hooks_are_rejected_even_when_prompt_wrapped(self):
        from commands.prompt import with_prompt

        calls = []
        async def coroutine():
            calls.append("unsafe")
        def generator():
            calls.append("unsafe")
            yield None
        for hook in ("at_pre_cmd", "parse", "at_post_cmd"):
            for function in (coroutine, generator):
                command = Command(key="준비검사")
                command.func = lambda: calls.append("func")
                setattr(command, hook, function)
                commands = CmdSet(key=hook + function.__name__)
                commands.add(with_prompt(command))
                self.char1.cmdset.add(commands)
                self.assertIn("직접 실행", self.run_raw("준비검사, 귀환 해"))
                self.assertEqual(calls, [])
                self.assertEqual(self.char1.zone, "dock")
                self.char1.cmdset.remove(commands.key)

    def test_parametric_global_names_are_reserved_for_personal_registration(self):
        from commands.aliases import ARGUMENT_SHORTCUTS

        with patch.dict(ARGUMENT_SHORTCUTS, {"gvar": "$*"}):
            self.assertIn("이름으로 사용할 수 없습니다", self.run_raw("gvar 장비 줄임말"))
        self.assertEqual(self.saved(), {})

    def test_engine_batch_control_is_rejected_before_loading_or_executing_file(self):
        from evennia.commands.default.batchprocess import CmdBatchCode, CmdBatchCommands

        for cls in (CmdBatchCommands, CmdBatchCode):
            command = cls(locks="cmd:all()")
            commands = CmdSet(key=cls.__name__)
            commands.add(command)
            self.char1.cmdset.add(commands)
            self.assertIn("묶음·줄임말 밖에서 실행", self.run_raw(f"{command.key} fixture_file, 귀환 해"))
            self.assertEqual(self.char1.zone, "dock")
            self.char1.cmdset.remove(commands.key)

    def test_special_management_whitespace_does_not_register_everybody_accidentally(self):
        self.register("모두", "장비")
        self.assertIn("계속하려면", self.run_raw("모두   삭제 줄임말"))
        self.assertEqual(self.saved(), {"모두": "장비"})
        self.assertIn("모두 삭제했습니다", self.run_raw("모두  삭제  확인 줄임말"))
        self.assertEqual(self.saved(), {})

    def test_direction_argument_shortcut_is_not_mistaken_for_exit_with_arguments(self):
        self.register("정찰", "$1 보기, 상태 해")
        before = deepcopy(self.char1.profile_snapshot())
        for argument in ("북", "n"):
            output = self.run_raw(argument + " 정찰")
            self.assertIn("상태", output)
            self.assertEqual(self.char1.zone, "dock")
            self.assertEqual(self.char1.profile_snapshot(), before)
        self.register("방향실행", "$*")
        self.run_raw("북 방향실행")
        self.assertEqual(self.char1.zone, "grass")
        self.char1.location = self.rooms["dock"]
        exit_object = next(obj for obj in self.char1.location.exits if obj.key == "북")
        exit_object.locks.add("traverse:false()")  # live 객체 진입 권한; cmdset template 캐시 갱신은 별도 엔진 계약
        before = deepcopy(self.char1.profile_snapshot())
        self.run_raw("북 방향실행")
        self.assertEqual(self.char1.zone, "dock")
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.run_raw("북 잘못된인자")
        self.assertEqual(self.char1.profile_snapshot(), before)
