from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from commands import gameplay
from evennia.typeclasses.models import Attribute
from evennia.utils.test_resources import EvenniaCommandTest
from server.conf.primal_inputfuncs import pz_auth
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

    def test_draft_profile_does_not_autosave(self):
        draft = self.char1.profile()
        draft["credits"] = 999
        draft["inventory"]["bandage"] = 999
        self.assertEqual(self.char1.profile()["credits"], 20)
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 3)

    def test_kill_snapshot_is_persisted_and_personal(self):
        self.char1.location = self.rooms["grass"]
        self.char2.location = self.rooms["grass"]
        self.char1.start_combat("scavenger")
        profile = self.char1.profile()
        profile["encounter"]["hp"] = 1
        self.char1.save_profile(profile)
        self.char1.resolve_combat_round(Random(3))
        attribute = self.char1.attributes.get("profile", return_obj=True)
        saved = Attribute.objects.get(pk=attribute.pk).value
        self.assertEqual(saved["xp"], 22)
        self.assertIsNone(saved["encounter"])
        self.assertEqual(self.char2.profile()["xp"], 0)
        self.char1.resolve_combat_round(Random(3))
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
                "보급상자에서 붕대 2개를 찾았습니다.",
                caller=character,
            )
        self.call(
            gameplay.Investigate(), "보급상자", "이미 보급품을 챙겼습니다.", caller=self.char1
        )
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 5)
        self.assertEqual(self.char2.profile()["inventory"]["bandage"], 5)

    def test_korean_quest_sequence_and_reward(self):
        self.call(gameplay.Talk(), "윤대장", "윤대장:", caller=self.char1)
        self.char1.location = self.rooms["office"]
        self.call(gameplay.Investigate(), "정비기록", "정비기록:", caller=self.char1)
        self.char1.change(lambda profile: profile["inventory"].update(scrap=3))
        self.char1.location = self.rooms["generator"]
        self.call(gameplay.Repair(), "발전기", "발전기가 돌아갑니다!", caller=self.char1)
        self.char1.change(lambda profile: profile.update(boss_defeated=True))
        self.char1.location = self.rooms["dock"]
        self.call(gameplay.Talk(), "윤대장", "첫 탐사 완료!", caller=self.char1)
        before = self.char1.profile()
        self.call(gameplay.Talk(), "윤대장", "통신탑 복구 완료", caller=self.char1)
        self.assertEqual(self.char1.profile(), before)


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
