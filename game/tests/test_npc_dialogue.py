"""Issue #47 공개 대화·트랜잭션·원래 NPC 선택 계약의 기능 회귀."""

import re
from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_object
from evennia.utils.ansi import parse_ansi, strip_raw_ansi
from world import npc_dialogue as dialogue
from world import rules
from world import text as ft
from world.bootstrap import build_world
from world.content.integrity import errors
from world.dialogue_intents import intents_for
from world.item_entities import api
from world.multiplayer import world_change

from tests.item_entity_fixture import NativeItemTest


class NPCDialogueTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        self.char1.location = self.char2.location = self.rooms["dock"]
        self.npc = next(obj for obj in self.char1.location.contents if obj.key == "윤대장")
        self.enterContext(patch("world.npc_dialogue.time", return_value=100))
        self.char1.msg = Mock()
        self.char2.msg = Mock()
        self.session1 = self.session_for(self.char1)
        self.session2 = self.session_for(self.char2)
        self.enterContext(patch.object(self.char1.sessions, "all", return_value=[self.session1]))
        self.enterContext(patch.object(self.char2.sessions, "all", return_value=[self.session2]))

    def session_for(self, character):
        session = Mock(logged_in=True)
        session.account = character.account
        session.get_puppet.return_value = character
        session.get_account.return_value = character.account
        return session

    def messages(self, character):
        return [call.args[0] for call in character.msg.call_args_list if call.args]

    def shared_npc_group(self):
        from world.selection_numbers.api import descriptor

        return [("selection_group_id", descriptor(self.npc).group_id)]

    def command(self, raw):
        completed = []
        self.char1.execute_cmd(raw).addCallback(lambda _: completed.append(True))
        self.assertEqual(completed, [True])
        return "\n".join(map(str, self.messages(self.char1)))

    def npc_messages(self, character, npc=None):
        return [value for value in self.messages(character) if str(value).startswith((npc or self.npc).key + ":")]

    def guides(self, character):
        return [str(value) for value in self.messages(character) if str(value).startswith("현재 사용 가능:")]

    def test_unknown_followup_public_readonly_and_failure_reset(self):
        dialogue.say(self.char1, "윤대장에게 임무")
        state = deepcopy(self.atomic_state())
        context = deepcopy(dialogue.current_context(self.char1))
        self.char1.msg.reset_mock()
        self.char2.msg.reset_mock()
        dialogue.say(self.char1, "그건 어디서 찾나요?")
        self.assertEqual(len(self.npc_messages(self.char1)), 1)
        self.assertEqual(str(self.npc_messages(self.char1)[0]), str(self.npc_messages(self.char2)[0]))
        self.assertIn("잘 모르겠군", str(self.npc_messages(self.char1)[0]))
        self.assertEqual(len(self.guides(self.char1)), 1)
        self.assertEqual(self.guides(self.char2), [])
        self.assertEqual(state, self.atomic_state())
        self.assertEqual(dialogue.current_context(self.char1)["at"], context["at"])
        self.assertEqual(dialogue.current_context(self.char1)["intent_id"], context["intent_id"])
        self.assertIsNone(dialogue.current_context(self.char2))
        dialogue.say(self.char1, "그건 어떤 뜻인가요?")
        self.assertEqual(len(self.npc_messages(self.char1)), 1)
        self.assertEqual(dialogue.current_context(self.char1)["failures"], 2)
        dialogue.say(self.char1, "진행")
        self.assertEqual(dialogue.current_context(self.char1)["failures"], 0)
        dialogue.say(self.char1, "그건 어디서 찾나요?")
        self.assertEqual(len(self.npc_messages(self.char1)), 3)

    def test_explicit_unknown_and_general_chat_context_boundaries(self):
        for _ in range(2):
            dialogue.say(self.char1, "윤대장에게 잘 모르겠어요")
        self.assertEqual(len(self.npc_messages(self.char1)), 2)
        dialogue.say(self.char1, "윤대장에게 임무")
        self.char1.msg.reset_mock()
        for body in ("오늘 저녁 뭐 먹나요?", "철수에게 그건 어디서 찾나요?", "그 사람은 오나요?"):
            dialogue.say(self.char1, body)
        self.assertEqual(self.npc_messages(self.char1), [])
        with patch("world.npc_dialogue.time", return_value=280):
            dialogue.say(self.char1, "그건 어디서 찾나요?")
        self.assertEqual(self.npc_messages(self.char1), [])
        self.assertIsNone(dialogue.current_context(self.char1))
        self.assertNotIn(self.npc.id, self.char1.ndb.npc_dialogue_guides or {})

    def test_other_npc_topic_wins_and_resets_failures(self):
        doctor = create_object("typeclasses.interactables.Doctor", key="의무관", location=self.char1.location)
        dialogue.say(self.char1, "윤대장에게 임무")
        dialogue.say(self.char1, "그건 어디서 찾나요?")
        self.char1.msg.reset_mock()
        dialogue.say(self.char1, "의료")
        self.assertEqual(self.npc_messages(self.char1), [])
        self.assertEqual(len(self.npc_messages(self.char1, doctor)), 1)
        self.assertEqual(dialogue.current_context(self.char1)["npc_id"], doctor.id)
        self.assertEqual(dialogue.current_context(self.char1)["failures"], 0)

    def test_guides_deduplicate_per_listener_and_update_on_state_change(self):
        dialogue.say(self.char1, "윤대장에게 안녕")
        self.assertEqual(len(self.guides(self.char1)), 1)
        self.assertEqual(len(self.guides(self.char2)), 1)
        self.assertIn("'윤대장에게 수락", self.guides(self.char1)[0])
        self.assertNotIn("보고", self.guides(self.char1)[0])
        listener_context = deepcopy(self.char1.ndb.npc_dialogue_context)
        dialogue.say(self.char2, "윤대장에게 임무")
        self.assertEqual(len(self.guides(self.char1)), 1)
        self.assertEqual(len(self.guides(self.char2)), 1)
        self.assertEqual(self.char1.ndb.npc_dialogue_context, listener_context)
        dialogue.say(self.char2, "윤대장에게 화제 안내")
        self.assertEqual(len(self.guides(self.char1)), 1)
        self.assertEqual(len(self.guides(self.char2)), 2)
        dialogue.say(self.char1, "윤대장에게 수락")
        self.assertEqual(len(self.guides(self.char1)), 2)
        self.assertEqual(len(self.guides(self.char2)), 2)
        self.assertNotIn("수락", self.guides(self.char1)[-1])
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(generator_fixed=True, boss_defeated=True))
        dialogue.say(self.char2, "윤대장에게 임무")
        self.assertEqual(len(self.guides(self.char1)), 3)
        self.assertIn("'윤대장에게 보고", self.guides(self.char1)[-1])
        self.assertEqual(len(self.guides(self.char2)), 2)
        self.assertEqual([str(v) for v in self.npc_messages(self.char1)],
                         [str(v) for v in self.npc_messages(self.char2)])

    def test_guide_expiry_npc_independence_and_lifecycle(self):
        doctor = create_object("typeclasses.interactables.Doctor", key="의무관", location=self.char1.location)
        dialogue.say(self.char1, "윤대장에게 안녕")
        dialogue.say(self.char1, "의무관에게 안녕")
        dialogue.say(self.char1, "윤대장에게 안녕")
        self.assertEqual(len(self.guides(self.char1)), 2)
        self.assertEqual(set(self.char1.ndb.npc_dialogue_guides), {self.npc.id, doctor.id})
        with patch("world.npc_dialogue.time", return_value=280):
            dialogue.say(self.char1, "윤대장에게 안녕")
        self.assertEqual(len(self.guides(self.char1)), 3)
        self.npc.location = self.rooms["grass"]
        dialogue.say(self.char1, "의무관에게 안녕")
        self.assertNotIn(self.npc.id, self.char1.ndb.npc_dialogue_guides)
        self.char1.move_to(self.rooms["hq_concourse"], quiet=True)
        self.assertFalse(self.char1.ndb.npc_dialogue_guides)
        self.char1.move_to(self.rooms["dock"], quiet=True)
        dialogue.say(self.char1, "의무관에게 안녕")
        self.char1.at_post_unpuppet()
        self.assertFalse(self.char1.ndb.npc_dialogue_guides)
        dialogue.say(self.char1, "의무관에게 안녕")
        self.char1.at_server_shutdown()
        self.assertFalse(self.char1.ndb.npc_dialogue_guides)

    def test_guides_inactive_topics_and_bounded_cache(self):
        self.char2.change(lambda p: p.update(combat_target=123))
        dialogue.say(self.char1, "윤대장에게 임무")
        dialogue.say(self.char1, "윤대장에게 임무")
        self.assertEqual(len(self.guides(self.char2)), 1)
        self.assertIn("없음", self.guides(self.char2)[0])
        empty = next(value for value in self.messages(self.char2) if str(value).startswith("현재 사용 가능:"))
        self.assertIsInstance(empty, ft.Text)
        self.assertEqual(empty.kind, "event")
        self.assertEqual(empty.segments, [{"role": "muted", "text": self.guides(self.char2)[0]}])
        self.assertEqual(strip_raw_ansi(parse_ansi(empty.ansi())), str(empty))
        self.assertEqual(dialogue.available_dialogue_topics(self.char2, self.npc), ())
        self.assertTrue(all(segment["role"] == "text" for value in self.npc_messages(self.char2)
                            for segment in value.segments if segment["text"].startswith("〈")))
        self.char2.change(lambda p: p.update(combat_target=None))
        dialogue.say(self.char1, "윤대장에게 임무")
        self.assertEqual(len(self.guides(self.char2)), 2)
        with patch("world.npc_dialogue.GUIDE_LIMIT", 1):
            doctor = create_object("typeclasses.interactables.Doctor", key="의무관", location=self.char1.location)
            dialogue.say(self.char1, "의무관에게 안녕")
            self.assertEqual(set(self.char1.ndb.npc_dialogue_guides), {doctor.id})

    def test_all_npc_output_keywords_belong_to_ssot(self):
        from typeclasses.interactables import INTERACTABLES

        for identity, row in INTERACTABLES.items():
            intents = intents_for(row["typeclass"])
            if not intents:
                continue
            npc = next(obj for obj in self.rooms[row["room"]].contents if obj.tags.has(identity, category="primal_interactable"))
            self.char1.location = self.char2.location = npc.location
            words = {item.keyword for item in intents}
            for intent in intents:
                if not intent.mutates_state:
                    raw = dialogue.response(self.char1, npc, intent)
                    self.assertTrue(set(re.findall(r"〈([^〉]+)〉", raw)) <= words, (identity, raw))
            self.char1.msg.reset_mock()
            dialogue.say(self.char1, npc.key + "에게 잘 모르겠어요")
            raw = str(self.npc_messages(self.char1, npc)[0])
            offered = re.findall(r"〈([^〉]+)〉", raw)
            expected = [item.keyword for item in dialogue.available_dialogue_topics(self.char1, npc)]
            self.assertEqual(offered, expected, identity)
            self.assertEqual(len(offered), len(set(offered)))
            self.assertLessEqual(len(offered), 3)
            self.assertNotIn("〈키워드〉", raw)

    def test_help_guide_request_matches_say_alias(self):
        first = self.command("말 도움")
        self.char1.msg.reset_mock()
        self.assertEqual(self.command("say 도움"), first)
        self.assertIn("화제 안내 말", first)
        self.char1.msg.reset_mock()
        self.command("윤대장에게 화제 안내 말")
        self.assertEqual(len(self.guides(self.char1)), 1)

    def test_say_help_describes_private_progress_and_session_prompt_boundaries(self):
        before = deepcopy(self.atomic_state())
        help_text = self.command("말 도움")
        self.char1.msg.reset_mock()
        self.assertEqual(self.command("say 도움"), help_text)
        for rule in ("플레이어 발화와 NPC의 공공 대사는 같은 방 전체에 공개됩니다.",
                     "개인 임무 진행 안내는 요청한 플레이어만 받으며, 질문한 발화 자체는 공개됩니다.",
                     "NPC의 공공 대사 원문은 모두에게 같고",
                     "보상 시스템 알림은 해당 플레이어만 받습니다.",
                     "발급받은 원래 접속 세션에서만 선택할 수 있으며",
                     "추가 입력 중에는 먼저 답을 입력해야 합니다."):
            self.assertIn(rule, help_text)
        self.assertNotIn("플레이어 발화와 NPC 대사는 같은 방 전체에 공개됩니다.", help_text)
        self.assertEqual(self.atomic_state(), before)

    def test_numbered_guide_refresh_and_empty_topic_response(self):
        dialogue.say(self.char1, "윤대장에게 안녕")
        create_object("typeclasses.interactables.Commander", key="윤대장", location=self.char1.location,
                      attributes=self.shared_npc_group())
        dialogue.say(self.char1, "윤대장 1에게 임무")
        self.assertEqual(len(self.guides(self.char1)), 2)
        self.assertIn("'윤대장 1에게 임무", self.guides(self.char1)[-1])
        with patch("world.npc_dialogue.available_intents", return_value=()):
            self.char1.msg.reset_mock()
            dialogue.say(self.char1, "윤대장 1에게 잘 모르겠어요")
            reply = str(self.npc_messages(self.char1)[0])
            self.assertIn("더 안내할 내용이 없습니다", reply)
            self.assertNotIn("〈", reply)

    def test_say_quote_equivalence_and_original(self):
        saved = deepcopy(dict(self.char1.db.profile))
        for first, second in (("안녕 말", "'안녕"), ("윤대장에게 임무 말", "'윤대장에게 임무"), ("임무 말", "'임무")):
            outputs = []
            for raw in (first, second):
                dialogue.clear_context(self.char1)
                self.char1.msg.reset_mock()
                self.command(raw)
                outputs.append([str(value) for value in self.messages(self.char1) if getattr(value, "kind", None) == "chat"])
            self.assertEqual(*outputs)
        self.assertIn("윤대장에게 임무", outputs[0][0] if "윤대장" in outputs[0][0] else self.command("'윤대장에게 임무"))
        self.assertEqual(saved, dict(self.char1.db.profile))
        for body in ("수락해도 되나요", "수락하지 않겠습니다", "보고할 수도 있다"):
            dialogue.say(self.char1, "윤대장에게 " + body)
        self.assertFalse(self.char1.profile_snapshot()["quests"]["radio_tower"]["started"])

    def test_fallback_ambiguity_and_numbers(self):
        for raw in ("철수에게 이 소식을 알려야 해", "없는NPC에게 안녕", self.char2.key + "에게 임무"):
            self.char1.msg.reset_mock()
            dialogue.say(self.char1, raw)
            self.assertEqual(str(self.messages(self.char1)[0]), self.char1.key + ": " + raw)
        other = create_object("typeclasses.interactables.Commander", key="윤대장", location=self.char1.location,
                              attributes=self.shared_npc_group())
        for body in ("윤대장에게 임무", "윤대장 3에게 임무", "윤대장 0에게 임무", "윤대장 -1에게 임무", "윤대장 모두에게 임무"):
            self.char1.msg.reset_mock()
            with self.assertRaises(rules.RuleError):
                dialogue.say(self.char1, body)
            self.assertEqual(self.messages(self.char1), [])
        dialogue.say(self.char1, "윤대장 2에게 임무")
        self.assertEqual(dialogue.current_context(self.char1)["npc_id"], other.id)
        self.assertTrue(any("'윤대장 2에게 수락" in str(value) for value in self.messages(self.char1)))
        self.npc.location = other.location = self.rooms["grass"]
        self.char1.msg.reset_mock()
        dialogue.say(self.char1, "윤대장에게 임무")
        self.assertEqual(len(self.messages(self.char1)), 1)

    def test_followup_and_sentence_middle_are_read_only(self):
        dialogue.say(self.char1, "윤대장에게 임무")
        state = deepcopy(self.atomic_state())
        dialogue.say(self.char1, "그다음은요")
        self.assertEqual(dialogue.current_context(self.char1)["intent_id"], "progress")
        self.assertEqual(state, self.atomic_state())
        self.char1.msg.reset_mock()
        dialogue.say(self.char1, "오늘은 윤대장에게 임무를 물어보고 싶다")
        self.assertEqual(len(self.messages(self.char1)), 1)
        self.assertIn("오늘은 윤대장에게 임무를 물어보고 싶다", str(self.messages(self.char1)[0]))

    def test_hint_and_web_start_use_npc_only_numbering(self):
        from world.observation import context_for
        from world.room_hints import render
        from world.state import multiplayer_state

        shared = self.shared_npc_group()
        create_object("typeclasses.interactables.ActionObject", key="윤대장", location=self.char1.location, attributes=shared)
        self.assertEqual(render(context_for(self.char1)), "'윤대장에게 안녕")
        state = multiplayer_state(self.char1)
        actions = [action["command"] for obj in state["interactables"] for action in obj["actions"]
                   if action["label"] == "말 걸기"]
        self.assertEqual(actions, ["'윤대장에게 안녕"])
        second = create_object("typeclasses.interactables.Commander", key="윤대장", location=self.char1.location, attributes=shared)
        state = multiplayer_state(self.char1)
        actions = [action["command"] for obj in state["interactables"] for action in obj["actions"]
                   if action["label"] == "말 걸기"]
        self.assertEqual(actions, ["'윤대장 1에게 안녕", "'윤대장 2에게 안녕"])
        dialogue.say(self.char1, actions[1][1:])
        self.assertEqual(dialogue.current_context(self.char1)["npc_id"], second.id)

    def test_public_same_raw_independent_highlights_and_context(self):
        self.char2.change(lambda p: p["quests"]["radio_tower"].update(started=True))
        self.char2.msg.reset_mock()
        dialogue.say(self.char1, "윤대장에게 임무")
        a = next(value for value in self.messages(self.char1) if str(value).startswith("윤대장:"))
        b = next(value for value in self.messages(self.char2) if str(value).startswith("윤대장:"))
        self.assertEqual(str(a), str(b))
        original = "윤대장에게 임무"
        mission = next(item for item in intents_for("Commander") if item.intent_id == "mission")
        expected_npc_body = dialogue.response(self.char1, self.npc, mission)
        for character, spoken in ((self.char1, a), (self.char2, b)):
            player = next(value for value in self.messages(character)
                          if str(value).startswith(self.char1.key + ":"))
            self.assertEqual(str(player), self.char1.key + ": " + original)
            self.assertEqual(str(spoken), self.npc.key + ": " + expected_npc_body)
            for message, role, name in ((player, "player", self.char1.key), (spoken, "npc", self.npc.key)):
                self.assertIsInstance(message, ft.Text)
                self.assertEqual(message.kind, "chat")
                self.assertEqual(message.segments[0], {"role": role, "text": name})
                self.assertEqual(message.segments[1], {"role": "text", "text": ": "})
                self.assertEqual(strip_raw_ansi(parse_ansi(message.ansi())), str(message))
            self.assertEqual(player.segments[2:], [{"role": "text", "text": original}])
            self.assertTrue(player.ansi().startswith("|g" + self.char1.key + "|n"))
            self.assertTrue(spoken.ansi().startswith("|c" + self.npc.key + "|n"))
        def accept_segment(value):
            return next(segment for segment in value.segments if segment["text"] == "〈수락〉")
        self.assertEqual(accept_segment(a)["role"], "dialogue_action")
        self.assertEqual(accept_segment(b)["role"], "text")
        self.assertNotIn("dialogue_selection", accept_segment(b))
        self.assertIsNot(accept_segment(a), accept_segment(b))
        self.assertIsNone(dialogue.current_context(self.char2))
        self.assertIsNotNone(dialogue.current_context(self.char1))
        with patch("world.npc_dialogue.time", return_value=280):
            self.assertIsNone(dialogue.current_context(self.char1))

    def test_personal_progress_is_private_in_public_command_and_web_selection(self):
        from server.conf.primal_inputfuncs import pz_dialogue

        cases = ((self.npc, "radio_tower"),
                 (next(obj for obj in self.rooms["jungle_edge"].contents
                       if dialogue.type_name(obj) == "Pathfinder"), "deep_jungle"))
        for npc, quest_id in cases:
            self.char1.location = self.char2.location = npc.location
            self.char1.change(lambda p: p["quests"][quest_id].update(started=True))
            intent = next(item for item in intents_for(dialogue.type_name(npc)) if item.intent_id == "progress")
            expected = dialogue.response(self.char1, npc, intent)
            self.assertNotEqual(expected, dialogue.response(self.char2, npc, intent))
            for route in ("command", "web"):
                with self.subTest(npc=dialogue.type_name(npc), route=route):
                    dialogue.clear_context(self.char1)
                    self.char1.msg.reset_mock()
                    self.char2.msg.reset_mock()
                    before = deepcopy(self.atomic_state())
                    if route == "command":
                        self.command(npc.key + "에게 진행 말")
                    else:
                        session = self.session_for(self.char1)
                        token = dialogue.issue_token(self.char1, npc, intent, session=session)
                        with patch.object(self.char1.sessions, "all", return_value=[session]):
                            pz_dialogue(session, token)
                    self.assertEqual([str(value) for value in self.npc_messages(self.char1, npc)],
                                     [npc.key + ": " + expected])
                    self.assertEqual(self.npc_messages(self.char2, npc), [])
                    self.assertTrue(any(str(value) == self.char1.key + ": " + npc.key + "에게 진행"
                                        for value in self.messages(self.char2)))
                    self.assertFalse(any(expected in str(value) for value in self.messages(self.char2)))
                    self.assertEqual(self.atomic_state(), before)

    def test_web_dialogue_token_is_bound_to_original_session(self):
        from server.conf.primal_inputfuncs import pz_dialogue

        intent = next(item for item in intents_for("Commander") if item.intent_id == "mission")
        sessions = [Mock(logged_in=True), Mock(logged_in=True)]
        for number, session in enumerate(sessions):
            session.account = self.char1.account
            session.sessid = number + 1
            session.get_puppet.return_value = self.char1
            session.get_account.return_value = self.char1.account
        with patch.object(self.char1.sessions, "all", return_value=[sessions[0]]):
            token = dialogue.issue_token(self.char1, self.npc, intent)
        before = deepcopy(self.atomic_state())
        with patch.object(self.char1.sessions, "all", return_value=sessions):
            pz_dialogue(sessions[1], token)
        self.assertEqual(self.npc_messages(self.char1), [])
        self.assertTrue(any(getattr(value, "kind", None) == "error" for value in self.messages(self.char1)))
        self.assertEqual(self.atomic_state(), before)

    def test_rendered_dialogue_tokens_are_separate_for_each_session_and_character(self):
        from server.conf.primal_inputfuncs import pz_dialogue

        second_session = self.session_for(self.char1)
        sessions = [self.session1, second_session]
        with patch.object(self.char1.sessions, "all", return_value=sessions):
            self.command("윤대장에게 임무 말")
            spoken = [call for call in self.char1.msg.call_args_list
                      if call.args and str(call.args[0]).startswith(self.npc.key + ":")]
            self.assertEqual(len(spoken), 2)
            self.assertEqual(str(spoken[0].args[0]), str(spoken[1].args[0]))
            tokens = [next(part["dialogue_selection"] for part in call.args[0].segments
                           if part["text"] == "〈수락〉") for call in spoken]
            self.assertNotEqual(*tokens)
            for call, session, token in zip(spoken, sessions, tokens):
                self.assertIs(call.kwargs["session"], session)
                self.assertIs(dialogue.token_store(self.char1)[token]["session"], session)
            before = deepcopy(self.atomic_state())
            for session, token in ((second_session, tokens[0]), (self.session2, tokens[0])):
                with self.subTest(recipient="other character" if session is self.session2 else "other session"):
                    self.char1.msg.reset_mock()
                    self.char2.msg.reset_mock()
                    pz_dialogue(session, token)
                    self.assertEqual(self.npc_messages(self.char1), [])
                    self.assertEqual(self.npc_messages(self.char2), [])
                    self.assertEqual(self.atomic_state(), before)
            with patch.object(self.char1.sessions, "all", return_value=[second_session]):
                self.char1.msg.reset_mock()
                pz_dialogue(self.session1, tokens[0])
                self.assertEqual(self.npc_messages(self.char1), [])
                self.assertEqual(self.atomic_state(), before)
            pz_dialogue(self.session1, tokens[0])
            self.assertTrue(self.char1.profile_snapshot()["quests"]["radio_tower"]["started"])
            self.assertEqual(len(self.npc_messages(self.char2)), 1)
            pz_dialogue(self.session1, tokens[0])
            self.assertEqual(len(self.npc_messages(self.char2)), 1)

    def test_web_dialogue_waits_for_prompt_input(self):
        from evennia.utils.evmenu import get_input
        from server.conf.primal_inputfuncs import pz_dialogue

        session = Mock(logged_in=True)
        session.account = self.char1.account
        session.get_puppet.return_value = self.char1
        session.get_account.return_value = self.char1.account
        intent = next(item for item in intents_for("Commander") if item.intent_id == "accept")
        with patch.object(self.char1.sessions, "all", return_value=[session]):
            token = dialogue.issue_token(self.char1, self.npc, intent)
            get_input(self.char1, "답을 입력하세요.", lambda *args: None)
            self.char1.msg.reset_mock()
            self.char2.msg.reset_mock()
            before = deepcopy(self.atomic_state())
            pz_dialogue(session, token)
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(self.npc_messages(self.char1), [])
        self.assertEqual(self.messages(self.char2), [])
        self.assertTrue(any("추가 입력" in str(value) for value in self.messages(self.char1)))

    def test_personal_guides_semantics_keep_plain_text_and_separate_chat(self):
        dialogue.say(self.char1, "윤대장에게 임무")
        guide = next(value for value in self.messages(self.char1) if str(value).startswith("현재 사용 가능:"))
        self.assertIsInstance(guide, ft.Text)
        self.assertEqual(guide.kind, "event")
        self.assertEqual(guide.segments[0], {"role": "muted", "text": "현재 사용 가능: "})
        commands = [part["text"] for part in guide.segments if part["role"] == "command"]
        self.assertEqual(commands, ["'윤대장에게 " + word for word in ("임무", "진행", "지역", "출입증", "수락")])
        self.assertEqual(str(guide), "현재 사용 가능: " + " · ".join(commands))
        self.assertEqual([part for part in guide.segments if part["role"] == "text"],
                         [{"role": "text", "text": " · "}] * (len(commands) - 1))
        self.assertEqual(strip_raw_ansi(parse_ansi(guide.ansi())), str(guide))
        self.assertFalse(any(part["role"] in ("npc", "player", "dialogue_topic", "dialogue_action")
                             for part in guide.segments))
        usage = next(value for value in self.messages(self.char1) if str(value).startswith("대사의 꺾쇠"))
        self.assertIsInstance(usage, ft.Text)
        self.assertEqual(usage.kind, "event")
        self.assertEqual([part["text"] for part in usage.segments if part["role"] == "command"],
                         ["화제 안내 말", "대화"])
        self.assertTrue(all(part["role"] in ("muted", "command") for part in usage.segments))
        self.assertEqual(str(usage), "대사의 꺾쇠 안 단어로 NPC에게 말할 수 있습니다. 화제 안내 말로 현재 입력을 다시 확인하세요. 개인 메시지는 대화를 사용하세요.")
        self.assertEqual(strip_raw_ansi(parse_ansi(usage.ansi())), str(usage))
        dialogue.say(self.char1, "윤대장에게 임무")
        self.assertEqual(len(self.guides(self.char1)), 1)
        self.assertEqual(sum(str(value).startswith("대사의 꺾쇠") for value in self.messages(self.char1)), 1)
        self.assertEqual(len(self.npc_messages(self.char1)), 2)

    def test_exact_transitions_private_reward_and_rollback(self):
        dialogue.say(self.char1, "윤대장에게 수락")
        self.assertTrue(self.char1.profile_snapshot()["quests"]["radio_tower"]["started"])
        with self.assertRaises(rules.RuleError):
            dialogue.say(self.char1, "윤대장에게 보고")
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(generator_fixed=True, boss_defeated=True))
        state = deepcopy(self.atomic_state())
        self.char1.msg.reset_mock()
        self.char2.msg.reset_mock()
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("storage failure")):
            with self.assertRaises(RuntimeError):
                dialogue.say(self.char1, "윤대장에게 보고")
        self.assertEqual(state, self.atomic_state())
        self.assertFalse(any("탐사를 마쳤" in str(value) or "경험치" in str(value) for value in self.messages(self.char2)))
        dialogue.say(self.char1, "윤대장에게 보고")
        completed = deepcopy(self.atomic_state())
        self.assertEqual(sum("탐사를 마쳤" in str(value) for value in self.messages(self.char2)), 1)
        self.assertTrue(any("경험치" in str(value) for value in self.messages(self.char1)))
        self.assertFalse(any("경험치" in str(value) or "붕대 3개" in str(value) for value in self.messages(self.char2)))
        with self.assertRaises(rules.RuleError):
            dialogue.say(self.char1, "윤대장에게 보고")
        self.assertEqual(completed, self.atomic_state())
        credential = next(row for row in api.items_owned_by(self.char1) if row.definition_id == "outpost_supply_pass")
        credential.delete()
        dialogue.say(self.char1, "윤대장에게 재발급")
        self.assertTrue(any(row.definition_id == "outpost_supply_pass" for row in api.items_owned_by(self.char1)))

    def test_outer_rollback_and_access_conditions(self):
        intent = next(item for item in intents_for("Commander") if item.intent_id == "accept")
        with self.assertRaises(RuntimeError):
            with world_change():
                dialogue.execute(self.char1, self.npc, intent)
                raise RuntimeError("outer rollback")
        self.assertFalse(self.char1.profile_snapshot()["quests"]["radio_tower"]["started"])
        self.assertEqual(self.messages(self.char1), [])
        self.char1.change(lambda p: p.update(combat_target=123))
        with self.assertRaises(rules.RuleError):
            dialogue.execute(self.char1, self.npc, intent)
        self.char1.change(lambda p: p.update(combat_target=None))
        with patch("world.observation.can_perceive", return_value=False):
            self.char1.msg.reset_mock()
            dialogue.say(self.char1, "윤대장에게 수락")
            self.assertEqual(len(self.messages(self.char1)), 1)

    def test_stale_action_tokens_cannot_report_twice_before_commit(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(started=True, generator_fixed=True, boss_defeated=True))
        intent = next(item for item in intents_for("Commander") if item.intent_id == "report")
        sessions = [self.session_for(self.char1), self.session_for(self.char1)]
        tokens = [dialogue.issue_token(self.char1, self.npc, intent, session=session) for session in sessions]
        before = self.char1.profile_snapshot()
        self.char2.msg.reset_mock()
        with patch.object(self.char1.sessions, "all", return_value=sessions), world_change():
            dialogue.select_keyword(self.char1, tokens[0], sessions[0])
            self.assertFalse(any("탐사를 마쳤" in str(value) for value in self.messages(self.char2)))
            with self.assertRaises(rules.RuleError):
                dialogue.select_keyword(self.char1, tokens[1], sessions[1])
        after = self.char1.profile_snapshot()
        self.assertEqual(after["xp"] - before["xp"], 100)
        self.assertEqual(after["credits"] - before["credits"], 100)
        self.assertEqual(sum("탐사를 마쳤" in str(value) for value in self.messages(self.char2)), 1)
        self.assertFalse(any("경험치" in str(value) for value in self.messages(self.char2)))

    def test_selection_tokens_bound_and_single_use(self):
        intent = next(item for item in intents_for("Commander") if item.intent_id == "accept")
        session = self.session_for(self.char1)
        token = dialogue.issue_token(self.char1, self.npc, intent, session=session)
        with patch.object(self.char1.sessions, "all", return_value=[session]):
            for invalid in ("tampered", token + "x"):
                with self.assertRaises(rules.RuleError):
                    dialogue.select_keyword(self.char1, invalid, session)
            with patch("world.npc_dialogue.time", return_value=280):
                with self.assertRaises(rules.RuleError):
                    dialogue.select_keyword(self.char1, token, session)
            token = dialogue.issue_token(self.char1, self.npc, intent, session=session)
            self.npc.location = self.rooms["grass"]
            with self.assertRaises(rules.RuleError):
                dialogue.select_keyword(self.char1, token, session)
            self.npc.location = self.rooms["dock"]
            dialogue.select_keyword(self.char1, token, session)
            with self.assertRaises(rules.RuleError):
                dialogue.select_keyword(self.char1, token, session)
        self.assertTrue(self.char1.profile_snapshot()["quests"]["radio_tower"]["started"])

    def test_content_22_discovery_and_no_legacy_action(self):
        from typeclasses.interactables import INTERACTABLES
        from world.observation import context_for
        from world.room_hints import render

        definitions = {key: row for key, row in INTERACTABLES.items() if intents_for(row["typeclass"])}
        self.assertEqual(len(definitions), 22)
        from world.content import ITEMS

        with patch.dict(ITEMS, {key: value for key, value in ITEMS.items() if key != "test_pistol"}, clear=True):
            self.assertEqual(errors(INTERACTABLES), [])
        self.assertEqual(render(context_for(self.char1)), "'윤대장에게 안녕")
        for identity, row in definitions.items():
            npc = next(obj for obj in self.rooms[row["room"]].contents if obj.tags.has(identity, category="primal_interactable"))
            self.char1.location = npc.location
            self.assertNotIn("대화", npc.actions)
            self.assertNotIn("말", npc.actions)
            self.assertIn("말 걸기", str(npc.return_appearance(self.char1)))
            for intent in intents_for(row["typeclass"]):
                if not intent.mutates_state:
                    before = deepcopy(self.atomic_state())
                    dialogue.execute(self.char1, npc, intent)
                    self.assertEqual(before, self.atomic_state())

    def test_jungle_prerequisite_accept_and_report(self):
        self.char1.location = self.rooms["jungle_edge"]
        with self.assertRaises(rules.RuleError):
            dialogue.say(self.char1, "선발대 길잡이에게 수락")
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(claimed=True))
        dialogue.say(self.char1, "선발대 길잡이에게 수락")
        before = deepcopy(self.atomic_state())
        for body in ("임무", "진행", "출입증", "지역"):
            dialogue.say(self.char1, "선발대 길잡이에게 " + body)
        self.assertEqual(before, self.atomic_state())
        self.char1.change(lambda p: p["quests"]["deep_jungle"].update(boss_defeated=True))
        before = self.char1.profile_snapshot()
        dialogue.say(self.char1, "선발대 길잡이에게 보고")
        after = self.char1.profile_snapshot()
        self.assertEqual(after["credits"] - before["credits"], 120)
        self.assertEqual(after["xp"] - before["xp"], 120)
        self.assertTrue(after["quests"]["deep_jungle"]["claimed"])

    def test_structured_input_checks_puppet_and_readonly_tokens(self):
        from server.conf.primal_inputfuncs import pz_dialogue

        intent = next(item for item in intents_for("Commander") if item.intent_id == "mission")
        session = self.session_for(self.char1)
        token = dialogue.issue_token(self.char1, self.npc, intent, session=session)
        before = deepcopy(self.atomic_state())
        with patch.object(self.char1.sessions, "all", return_value=[session]):
            pz_dialogue(session, token)
            pz_dialogue(session, token)
            self.assertEqual(before, self.atomic_state())
            session.account = Mock()
            self.char1.msg.reset_mock()
            pz_dialogue(session, token)
            self.assertIn("세션", str(self.messages(self.char1)[0]))
        with patch("world.observation.can_perceive", return_value=False):
            self.assertIsNone(dialogue.current_context(self.char1))
        dialogue.say(self.char1, "윤대장에게 임무")
        self.char1.move_to(self.rooms["hq_concourse"], quiet=True)
        self.char1.move_to(self.rooms["dock"], quiet=True)
        self.assertIsNone(dialogue.current_context(self.char1))
        self.assertFalse(self.char1.ndb.npc_dialogue_tokens)
