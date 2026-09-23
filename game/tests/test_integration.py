from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from commands import gameplay
from commands.default_cmdsets import CharacterCmdSet, UnloggedinCmdSet
from evennia import CmdSet, Command
from evennia.commands.cmdparser import cmdparser as default_parser
from evennia.typeclasses.models import Attribute
from evennia.utils.test_resources import EvenniaCommandTest
from server.conf.cmdparser import cmdparser
from server.conf.primal_inputfuncs import pz_auth
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from world.bootstrap import build_world
from world.content import ROOMS


class GameplayIntegrationTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        for character in (self.char1, self.char2):
            character.location = self.rooms["dock"]
            character.home = self.rooms["dock"]
            character.push_state = Mock()

    def test_world_bootstrap_is_idempotent(self):
        first = {key: room.id for key, room in self.rooms.items()}
        second = build_world()
        self.assertEqual(first, {key: room.id for key, room in second.items()})
        self.assertEqual(
            sum(len(room.exits) for room in second.values()),
            sum(len(room["exits"]) for room in ROOMS.values()),
        )

    def test_korean_character_creation_preserves_name(self):
        character, errors = Explorer.create(
            "한글탐사자", self.account, location=self.rooms["dock"], home=self.rooms["dock"]
        )
        self.assertFalse(errors)
        self.assertEqual(character.key, "한글탐사자")

    def test_ui_snapshot_survives_protocol_encoding(self):
        import evennia

        with patch.object(self.char1, "msg") as message:
            with patch.object(self.char1.sessions, "count", return_value=1):
                Explorer.push_state(self.char1)
        wire = evennia.SESSION_HANDLER.clean_senddata(self.session, message.call_args.kwargs)
        self.assertEqual(wire["pz_state"][0][0]["hp"], 60)
        self.assertEqual(wire["pz_state"][0][0]["name"], self.char1.key)

    def test_exit_state_and_text_follow_room_data(self):
        from typeclasses.zone_rooms import exit_diagram

        for zone, definition in ROOMS.items():
            with self.subTest(zone=zone):
                self.char1.location = self.rooms[zone]
                with patch.object(self.char1, "msg") as message:
                    with patch.object(self.char1.sessions, "count", return_value=1):
                        Explorer.push_state(self.char1)
                state = message.call_args.kwargs["pz_state"][0][0]
                self.assertEqual(state["exits"], list(definition["exits"]))
                self.assertIn(
                    exit_diagram(definition["exits"]),
                    self.rooms[zone].return_appearance(self.char1),
                )

    def test_direction_text_omits_missing_branches_and_supports_other_exits(self):
        from typeclasses.zone_rooms import exit_diagram

        self.assertEqual(exit_diagram(["북"]), "  북\n   │\n[현재]")
        self.assertEqual(exit_diagram(["남"]), "[현재]\n   │\n  남")
        self.assertEqual(exit_diagram(["동"]), "[현재] ─ 동")
        self.assertEqual(exit_diagram(["서"]), "서 ─ [현재]")
        self.assertEqual(exit_diagram(["서", "동"]), "서 ─ [현재] ─ 동")
        self.assertEqual(exit_diagram([]), "[현재]")
        for count in range(1, 5):
            exits = ["북", "남", "동", "서"][:count]
            diagram = exit_diagram(exits)
            for direction in ("북", "남", "동", "서"):
                self.assertEqual(direction in diagram, direction in exits)
            self.assertEqual(diagram.count("│"), len(set(exits) & {"북", "남"}))
            self.assertEqual(diagram.count("─"), len(set(exits) & {"동", "서"}))
        self.assertEqual(exit_diagram(["위", "북동"]), "[현재]\n기타 출구: 위 · 북동")

    def test_movement_immediately_emits_new_exits_and_appearance(self):
        with patch.object(self.char1, "push_state", wraps=lambda: Explorer.push_state(self.char1)):
            with patch.object(self.char1.sessions, "count", return_value=1):
                with patch.object(self.char1, "msg") as message:
                    self.assertTrue(self.char1.move_to(self.rooms["grass"]))
                    self.assertTrue(self.char1.move_to(self.rooms["wreck"]))
        states = [
            call.kwargs["pz_state"][0][0]
            for call in message.call_args_list
            if "pz_state" in call.kwargs
        ]
        self.assertEqual(states[-1]["exits"], ["서"])
        self.assertTrue(any(state["exits"] == list(ROOMS["grass"]["exits"]) for state in states))
        self.assertTrue(any("서 ─ [현재]" in str(call) for call in message.call_args_list))

    def test_draft_profile_does_not_autosave(self):
        draft = self.char1.profile()
        draft["credits"] = 999
        draft["inventory"]["bandage"] = 999
        self.assertEqual(self.char1.profile()["credits"], 20)
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 3)

    def test_shared_kill_persists_once(self):
        self.char1.location = self.rooms["grass"]
        with patch.object(self.char1.sessions, "count", return_value=1):
            self.char1.start_combat("scavenger")
            enemy = room_enemies(self.char1.location)[0]
            enemy.db.hp = 1
            now = self.char1.profile()["next_attack_at"]
            self.char1.resolve_combat_round(Random(3), now=now)
            attribute = self.char1.attributes.get("profile", return_obj=True)
            saved = Attribute.objects.get(pk=attribute.pk).value
            self.assertEqual(saved["xp"], 22)
            self.assertIsNone(saved["combat_target"])
            self.assertEqual(self.char2.profile()["xp"], 0)
            self.char1.resolve_combat_round(Random(3), now=now)
            self.assertEqual(self.char1.profile()["xp"], 22)

    def test_attack_spam_creates_only_one_timer(self):
        self.char1.location = self.rooms["grass"]
        with patch.object(self.char1.sessions, "count", return_value=1):
            with patch("typeclasses.explorers.delay") as delay:
                for _ in range(5):
                    self.char1.start_combat("scavenger")
                self.assertEqual(delay.call_count, 1)
                self.char1.stop_combat_timer()
                delay.return_value.remove.assert_called_once()

    def test_combat_and_quest_gates_block_movement(self):
        self.char1.location = self.rooms["grass"]
        self.char1.start_combat("scavenger")
        self.assertFalse(self.char1.move_to(self.rooms["trail"]))
        self.call(gameplay.Flee(), "", "교전을 끝냈습니다.", caller=self.char1)
        self.assertFalse(self.char1.move_to(self.rooms["ridge"]))
        self.char1.change(lambda profile: profile.update(generator_fixed=True))
        self.assertTrue(self.char1.move_to(self.rooms["ridge"]))

    def test_failed_purchase_does_not_change_saved_data(self):
        before = deepcopy(self.char1.profile())
        self.call(gameplay.Buy(), "탐사카빈", "크레딧이 부족합니다.", caller=self.char1)
        self.assertEqual(self.char1.profile(), before)

    def test_cache_reward_is_personal_and_once_only(self):
        for character in (self.char1, self.char2):
            character.location = self.rooms["wreck"]
            self.call(
                gameplay.Investigate(),
                "보급상자",
                "보급상자에서 붕대 2개를 찾아 챙겼다.",
                caller=character,
            )
        self.call(
            gameplay.Investigate(), "보급상자", "이미 보급품을 챙겼습니다.", caller=self.char1
        )
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 5)
        self.assertEqual(self.char2.profile()["inventory"]["bandage"], 5)

    def test_korean_quest_sequence_and_reward(self):
        self.call(gameplay.Talk(), "윤대장", "윤대장", caller=self.char1)
        self.char1.location = self.rooms["office"]
        self.call(gameplay.Investigate(), "정비기록", "정비기록을 펼쳐", caller=self.char1)
        self.char1.change(lambda profile: profile["inventory"].update(scrap=3))
        self.char1.location = self.rooms["generator"]
        self.call(
            gameplay.Repair(), "발전기", "발전기가 다시 돌아가기 시작했다.", caller=self.char1
        )
        self.char1.change(lambda profile: profile.update(boss_defeated=True))
        self.char1.location = self.rooms["dock"]
        self.call(gameplay.Talk(), "윤대장", "윤대장", caller=self.char1)
        before = self.char1.profile()
        self.call(gameplay.Talk(), "윤대장", "윤대장", caller=self.char1)
        self.assertEqual(self.char1.profile(), before)

    def test_raw_commands_purchase_equip_and_quest(self):
        self.char1.change(lambda data: data.update(credits=200))
        self.char1.execute_cmd("  강철 마체테   구매  ")
        self.assertEqual(self.char1.profile()["inventory"]["blade"], 1)
        self.char1.execute_cmd("강철 마체테 WIELD")
        self.assertEqual(self.char1.profile()["equipment"]["weapon"], "blade")
        self.char1.execute_cmd("윤대장 대화")
        self.assertTrue(self.char1.profile()["quest_started"])
        self.char1.location = self.rooms["office"]
        self.char1.execute_cmd("정비 기록 조사")
        self.assertTrue(self.char1.profile()["record_read"])
        self.char1.location = self.rooms["generator"]
        self.char1.change(lambda data: data["inventory"].update(scrap=9))
        self.char1.execute_cmd("발전 기 수리")
        self.assertTrue(self.char1.profile()["generator_fixed"])
        self.char1.execute_cmd("귀환")
        self.assertEqual(self.char1.location, self.rooms["dock"])
        self.char1.execute_cmd("강화조끼 교환")
        self.assertEqual(self.char1.profile()["inventory"]["armor"], 1)

    def test_raw_attack_resume_and_movement(self):
        self.char1.execute_cmd("북")
        self.assertEqual(self.char1.location, self.rooms["grass"])
        self.char1.execute_cmd("어린 청소룡 사냥")
        before = self.char1.profile()["combat_target"]
        self.assertEqual(self.char1.combat_target().db.enemy_id, "scavenger")
        with patch.object(self.char1.sessions, "count", return_value=1):
            self.char1.execute_cmd("공격")
        self.assertEqual(self.char1.profile()["combat_target"], before)
        self.char1.execute_cmd("강타")
        self.assertEqual(self.char1.profile()["queued_action"], "heavy")

    def test_old_prefix_commands_never_execute(self):
        for raw in (
            "공격 어린청소룡",
            "attack scavenger",
            "구매 붕대",
            "buy bandage",
            "착용 낡은칼",
            "대화 윤대장",
            "말 안녕하세요",
            "say hello",
            "어린청소룡공격",
            "어린청소룡 강타",
            "상태 추가인자",
            "@say hello",
        ):
            with self.subTest(raw=raw), patch.object(self.char2, "msg") as other:
                before = deepcopy(self.char1.profile())
                with patch.object(self.char1, "msg") as message:
                    self.char1.execute_cmd(raw)
                self.assertIn("대상 뒤에 행동", str(message.call_args_list))
                self.assertEqual(self.char1.profile(), before)
                other.assert_not_called()

    def test_raw_chat_preserves_content_and_does_not_execute_actions(self):
        for raw, expected in (
            ("  안녕  여러분! 말  ", "안녕  여러분!"),
            ("'어린청소룡 공격", "어린청소룡 공격"),
            ("'안녕하세요 말", "안녕하세요 말"),
            ("할 말이 있어요 말", "할 말이 있어요"),
            ("'it's fine", "it's fine"),
            ("hello say", "hello"),
            ("connect 서버 안내 말", "connect 서버 안내"),
            ("'{you} { $You()", "{you} { $You()"),
        ):
            with self.subTest(raw=raw), patch.object(self.char2, "msg") as other:
                before = deepcopy(self.char1.profile())
                self.char1.execute_cmd(raw)
                self.assertEqual(other.call_args.args[0], f"{self.char1.key}: {expected}")
                self.assertEqual(self.char1.profile(), before)
        self.char2.location = self.rooms["grass"]
        with patch.object(self.char2, "msg") as other:
            self.char1.execute_cmd("다른 방에는 들리지 않아요 말")
            other.assert_not_called()

    def test_raw_chat_empty_and_length_boundaries(self):
        for raw in ("말", "'", "'   ", "   말   ", "'" + "가" * 301, "가" * 301 + " 말"):
            with self.subTest(raw=raw), patch.object(self.char2, "msg") as other:
                with patch.object(self.char1, "msg") as message:
                    self.char1.execute_cmd(raw)
                self.assertTrue(message.called)
                other.assert_not_called()
        for raw in ("'" + "가" * 300, "가" * 300 + " 말"):
            with self.subTest(raw=raw), patch.object(self.char2, "msg") as other:
                self.char1.execute_cmd(raw)
                self.assertEqual(other.call_args.args[0], f"{self.char1.key}: " + "가" * 300)

    def test_parser_preserves_locks_and_management_syntax(self):
        commands = CharacterCmdSet()
        locked = gameplay.Attack(locks="cmd:false()")
        commands.add(locked)
        self.assertEqual(cmdparser("어린청소룡 공격", commands, self.char1), [])
        management = Command(key="@관리", locks="cmd:all()")
        commands.add(management)
        for args in ("대상", "대상 공격"):
            matches = cmdparser(f"@관리 {args}", commands, self.char1)
            self.assertIs(matches[0][2], management)
            self.assertEqual(matches[0][1].strip(), args)
        # 캐릭터가 없는 인증·메뉴용 명령 집합은 기본 파서 그대로 사용한다.
        for commands in (UnloggedinCmdSet(), CmdSet()):
            for raw in ("connect explorer password", "create explorer password", ""):
                self.assertEqual(
                    cmdparser(raw, commands, self.char1),
                    default_parser(raw, commands, self.char1),
                )


class AuthenticationTests(EvenniaCommandTest):
    def test_structured_registration_does_not_echo_password(self):
        session = Mock(account=None, address="127.0.0.1")
        account_class = Mock()
        account_class.create.return_value = (Mock(), [])
        with patch("server.conf.primal_inputfuncs._class_from_module", return_value=account_class):
            pz_auth(
                session, {"username": "탐사자", "password": "example-pass-092", "mode": "register"}
            )
        session.sessionhandler.login.assert_called_once()
        self.assertNotIn("example-pass-092", str(session.msg.call_args_list))

    def test_bad_payload_never_reaches_authenticator(self):
        session = Mock(account=None)
        with patch("server.conf.primal_inputfuncs._class_from_module") as account_class:
            pz_auth(session, {"username": "bad name", "password": "123", "mode": "register"})
            pz_auth(session, ["malformed"])
            account_class.assert_not_called()
        session.sessionhandler.login.assert_not_called()
