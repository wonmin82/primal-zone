"""대화 SSOT의 정확 입력·자연어 오탐·충돌 경계."""

import unittest
from dataclasses import replace

from world import text as ft
from world.dialogue_intents import MISSION, SERVICE_INTENTS, intent_errors, recognize


class IntentTests(unittest.TestCase):
    def test_exact_and_readonly_patterns(self):
        self.assertEqual(recognize(MISSION, "수락").intent_id, "accept")
        self.assertEqual(recognize(MISSION, "수락하겠습니다").intent_id, "accept")
        self.assertEqual(recognize(MISSION, "임무에 대해 알려주세요").intent_id, "mission")
        for body in ("수락해도 되나요", "수락하지 않겠습니다", "보고할 수도 있다", "재발급은 나중에", "네", "아니요", "임무처럼 보이네"):
            self.assertIsNone(recognize(MISSION, body), body)

    def test_ssot_conflicts_and_followups(self):
        for name in SERVICE_INTENTS:
            self.assertEqual(intent_errors(name), [])
        self.assertTrue(intent_errors("Commander", (MISSION[0], replace(MISSION[1], keyword="안녕"))))
        self.assertTrue(intent_errors("Commander", (replace(MISSION[0], next_topics=("missing",)),)))

    def test_independent_keyword_segments(self):
        active = ft.dialogue_keyword("수락", "action", "opaque")
        inactive = ft.dialogue_keyword("수락", "action")
        self.assertEqual(str(active), str(inactive))
        self.assertEqual(active.segments[0]["role"], "dialogue_action")
        self.assertNotIn("dialogue_selection", inactive.segments[0])
        self.assertIsNot(active.segments[0], inactive.segments[0])
