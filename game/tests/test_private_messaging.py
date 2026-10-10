"""개인 메시지 수락·영속 차단·실제 CmdSet 우회 경계."""

from copy import deepcopy
from unittest.mock import Mock, patch

from commands.default_cmdsets import AccountCmdSet, CharacterCmdSet
from commands.help_pages import help_page
from commands.registry import COMMANDS
from evennia import create_object
from world import private_messaging as messaging
from world import rules
from world.npc_dialogue import say

from tests.item_entity_fixture import NativeItemTest


class PrivateMessagingTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.char1.msg = Mock()
        self.char2.msg = Mock()
        self.enterContext(patch.object(self.char2.sessions, "count", return_value=1))

    def test_private_accept_reply_and_public_does_not_change_peer(self):
        self.char2.location = self.room2
        listener = create_object("typeclasses.explorers.Explorer", key="청자", location=self.char1.location)
        listener.msg = Mock()
        saved = deepcopy(dict(self.char1.db.profile))
        recipient, body = messaging.split_message(self.char2.key + " 안녕하세요  여러분")
        self.assertEqual(recipient, self.char2)
        self.assertEqual(body, "안녕하세요  여러분")
        messaging.send(self.char1, recipient, body)
        self.assertEqual(messaging.state(self.char1)["last_private_peer_id"], self.char2.id)
        self.assertEqual(messaging.state(self.char2)["last_private_peer_id"], self.char1.id)
        listener.msg.assert_not_called()
        self.assertIn("[개인]", str(self.char2.msg.call_args.args[0]))
        self.assertNotIn(body, str(messaging.state(self.char1)))
        with patch.object(self.char1.sessions, "count", return_value=1):
            messaging.reply(self.char2, "알겠습니다")
        own = messaging.state(self.char1)
        say(self.char1, "일반 채팅")
        self.assertEqual(own, messaging.state(self.char1))
        self.assertEqual(saved, dict(self.char1.db.profile))

    def test_offline_block_persistent_and_failed_send_unchanged(self):
        with patch.object(self.char2.sessions, "count", return_value=0):
            messaging.toggle_block(self.char1, self.char2.key)
        self.char1.attributes.reset_cache()
        self.assertEqual(messaging.state(self.char1)["blocked_character_ids"], [self.char2.id])
        self.assertIn(self.char2.key, messaging.blocked_list(self.char1))
        own, other = messaging.state(self.char1), messaging.state(self.char2)
        with patch.object(self.char1.sessions, "count", return_value=1):
            with self.assertRaises(rules.RuleError):
                messaging.send(self.char2, self.char1, "수신 차단")
        self.assertEqual(own, messaging.state(self.char1))
        self.assertEqual(other, messaging.state(self.char2))
        messaging.toggle_block(self.char1, self.char2.key)
        self.assertEqual(messaging.state(self.char1)["blocked_character_ids"], [])

    def test_input_offline_ambiguity_and_limits(self):
        for value in ("", "x" * 301, "개행\n문장", "\x1b[31m색", "\u202e방향"):
            with self.assertRaises(rules.RuleError):
                messaging.send(self.char1, self.char2, value)
        for target in (self.char1, self.obj1):
            with self.assertRaises(rules.RuleError):
                messaging.send(self.char1, target, "안녕")
        with patch.object(self.char2.sessions, "count", return_value=0):
            with self.assertRaises(rules.RuleError):
                messaging.send(self.char1, self.char2, "안녕")
        duplicate = create_object("typeclasses.explorers.Explorer", key=self.char2.key, location=self.room2)
        with self.assertRaises(rules.RuleError):
            messaging.split_message(self.char2.key + " 안녕하세요")
        target, _ = messaging.split_message(self.char2.key + " 2 안녕하세요")
        self.assertEqual(target, duplicate)
        with self.assertRaises(rules.RuleError):
            messaging.split_message(self.char2.key + " 3 안녕하세요")
        self.char1.attributes.add(messaging.ATTRIBUTE, {"version": 1, "last_private_peer_id": None, "blocked_character_ids": list(range(10000, 10100))})
        with self.assertRaises(rules.RuleError):
            messaging.toggle_block(self.char1, self.char2.key)

    def test_transaction_failure_sends_nothing(self):
        before = messaging.state(self.char1), messaging.state(self.char2)
        with patch.object(self.char2.attributes, "add", side_effect=RuntimeError("storage failure")):
            with self.assertRaises(RuntimeError):
                messaging.send(self.char1, self.char2, "보관하지 않는 내용")
        self.assertEqual(before, (messaging.state(self.char1), messaging.state(self.char2)))
        self.char1.msg.assert_not_called()
        self.char2.msg.assert_not_called()

    def test_actual_cmdset_no_page_alias_and_help_dispatch(self):
        keys = {name for command in AccountCmdSet().commands for name in (command.key, *command.aliases)}
        self.assertNotIn("page", keys)
        self.assertNotIn("tell", keys)
        character_keys = {name for command in CharacterCmdSet().commands for name in (command.key, *command.aliases)}
        self.assertNotIn("whisper", character_keys)
        for key in ("말", "대화", "대답", "대화거부"):
            text = str(help_page(key, COMMANDS))
            for title in ("사용법", "예시", "실행 규칙", "제한", "관련 도움말"):
                self.assertIn(title, text)
        self.assertEqual(help_page("say", COMMANDS), help_page("말", COMMANDS))
        completed = []
        self.char1.execute_cmd(self.char2.key + " 직접 명령 대화").addCallback(lambda _: completed.append(True))
        self.assertEqual(completed, [True])
        self.assertIn("직접 명령", str(self.char2.msg.call_args.args[0]))
