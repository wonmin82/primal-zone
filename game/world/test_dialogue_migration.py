"""v13 방법 B의 원본·참조·실제 명령 우선권·신규 의미 보존."""

from copy import deepcopy
from unittest import TestCase

from commands.shortcuts import parse_definition
from commands.vocabulary import migrate_dialogue_shortcuts

from world import rules


class DialogueMigrationTests(TestCase):
    def test_legacy_actions_sequence_and_transitive_refs_disabled(self):
        old = {"시작": "윤대장 대화", "교관": "전투교관 대화", "상인": "보급관 대화",
               "변수": "$1 대화", "동사": "$*", "묶음": "점수, 시작 해", "상위": "묶음",
               "안전": "윤대장에게 임무 말", "채팅": "'윤대장 대화", "사격": "쏴"}
        before = deepcopy(old)
        migrated = migrate_dialogue_shortcuts(old)
        for key in ("시작", "교관", "상인", "변수", "동사", "묶음", "상위"):
            self.assertEqual(migrated[key]["원본"], old[key])
            self.assertIn("문제", migrated[key])
            with self.assertRaises(rules.RuleError):
                parse_definition(migrated[key])
        for key in ("안전", "채팅", "사격"):
            self.assertEqual(migrated[key], old[key])
        self.assertEqual(old, before)
        self.assertEqual(migrate_dialogue_shortcuts(migrated), migrated)

    def test_collision_and_actual_priority(self):
        migrated = migrate_dialogue_shortcuts({"대답": "점수", "대화거부": "장비", "대화": "봐",
                                               "참조": "대답", "인자": "$1 대화거부", "구형": "윤대장 대화",
                                               "점수": "윤대장 대화", "실제": "점수"})
        self.assertEqual(migrated["대답_개인"], "점수")
        self.assertEqual(migrated["참조"], "대답_개인")
        self.assertEqual(migrated["인자"], "$1 대화거부_개인")
        self.assertIn("문제", migrated["구형"])
        self.assertEqual(migrated["실제"], "점수")
        self.assertNotIn("대답", migrated)

    def test_v13_idempotence_and_new_private_meaning(self):
        old = rules.new_profile()
        old.update(version=12, command_shortcuts={"이전": "윤대장 대화", "읽기": "점수"})
        before = deepcopy(old)
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated["version"], 13)
        for key in before:
            if key not in ("version", "command_shortcuts"):
                self.assertEqual(migrated[key], before[key], key)
        self.assertEqual(rules.migrate_profile(migrated), migrated)
        fresh = rules.new_profile()
        fresh["command_shortcuts"] = {"메시지": "철수 안녕 대화"}
        self.assertEqual(rules.migrate_profile(fresh)["command_shortcuts"], fresh["command_shortcuts"])
        self.assertEqual(old, before)

    def test_existing_disabled_and_cycle_propagation(self):
        original = {"원본": ["윤대장 대화"], "문제": "이전 사유"}
        result = migrate_dialogue_shortcuts({"이전": original, "참조": "이전", "a": "b", "b": "a, 이전 해",
                                            "손상": {"변환 확인": "원본 확인 필요"}, "상위": "손상"})
        self.assertEqual(result["이전"], original)
        self.assertEqual(result["손상"], {"변환 확인": "원본 확인 필요"})
        for key in ("참조", "a", "b", "상위"):
            self.assertIn("문제", result[key])
