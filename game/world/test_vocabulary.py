"""v8의 저장 어휘 변환과 단축어 데이터 계약."""

from copy import deepcopy
from unittest import TestCase

from commands.aliases import SHORTCUTS
from commands.shortcuts import shortcut_name
from commands.vocabulary import V7_GLOBAL_SHORTCUTS, migrate_shortcuts

from world import presentation, rules
from world.content.directions import DIRECTION_SHORTCUTS, DIRECTIONS
from world.progression import SKILLS


class VocabularyTests(TestCase):
    def test_curriculum_has_no_proficiency_and_healing_is_active(self):
        self.assertEqual(set(SKILLS), {'attack', 'defense', 'heavy', 'heal', 'shooting', 'insight', 'suppress', 'breathing'})
        profile = rules.new_profile()
        self.assertNotIn('proficiencies', profile)
        self.assertNotIn('숙련', presentation.abilities(profile))
        self.assertNotIn('숙련', presentation.experience(profile))
        self.assertIn('치료', presentation.skills(profile))
        self.assertNotIn('응급처치', presentation.skills(profile))

    def test_v7_hil_name_collision_preserves_data_and_exact_references(self):
        old = rules.new_profile()
        old.update(version=7, command_shortcuts={
            "힐": ["가방"], "힐_개인": ["장비"], "힐_개인2": ["상태"],
            "생존": ["힐", "힐 보기", "힐 말", "'힐, 회복", "치료", "heal"],
        })
        before = deepcopy(old)
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated["command_shortcuts"], {
            "힐_개인3": ["소지품"], "힐_개인": ["장비"], "힐_개인2": ["상태"],
            "생존": ["힐_개인3", "힐 보기", "힐 말", "'힐, 회복", "진료", "붕대 사용"],
        })
        self.assertEqual(old, before)
        self.assertEqual(rules.migrate_profile(migrated), migrated)

    def test_v7_global_shortcuts_are_fixed_historical_input(self):
        historical = {
            "ㅂ": "북", "ㄴ": "남", "ㄷ": "동", "ㅅ": "서",
            "상": "상태", "능": "능력", "기": "기술", "장": "장비",
        }
        self.assertEqual(V7_GLOBAL_SHORTCUTS, historical)
        old = {"기록": [*historical, "가", "가방"]}
        self.assertEqual(migrate_shortcuts(old)["기록"], [*historical.values(), "소지품", "소지품"])
        self.assertEqual(old["기록"], [*historical, "가", "가방"])

    def test_global_shortcuts_follow_direction_ssot_and_canonical_inventory(self):
        self.assertEqual(len(DIRECTION_SHORTCUTS), 8)
        self.assertEqual(len(set(data["shortcut"] for data in DIRECTIONS.values() if "shortcut" in data)), 8)
        self.assertEqual({key: SHORTCUTS[key] for key in DIRECTION_SHORTCUTS}, DIRECTION_SHORTCUTS)
        self.assertEqual(SHORTCUTS["소"], "소지품")
        self.assertNotIn("가", SHORTCUTS)

    def test_v7_migration_preserves_gameplay_and_firstaid_rank_and_queue(self):
        old = rules.new_profile()
        old.update(version=7, xp=123, credits=95, hp=31, combat_target=345, queued_action="heal", next_attack_at=456)
        old.pop("mental")  # v7에는 아직 정신력 자원이 없다.
        old.pop("recovery_effects")
        old['skills'] = {'heavy': 1, 'guard': 1, 'heal': 3}
        old["command_shortcuts"] = {"점검": ["상태", "장비", "가"], "인사": ["회복 말", "'상점, 치료"],
                                    "쇼핑": ["무기상 메뉴", "붕대 구매", "의무관에게 치료", "가방", "heal", "내리기"]}
        before = deepcopy(old)
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated["version"], rules.PROFILE_VERSION)
        self.assertEqual(set(migrated["skills"].values()), {1})
        self.assertNotIn("firstaid", migrated["skills"])
        self.assertEqual(migrated["queued_action"], "attack")
        self.assertEqual(migrated["command_shortcuts"], {
            "점검": ["상태", "장비", "소지품"], "인사": ["회복 말", "'상점, 치료"],
            "쇼핑": ["무기상 상품", "붕대 구매", "의무관에게 진료", "소지품", "붕대 사용", "내려"]})
        for key in old.keys() - {"version", "skills", "queued_action", "command_shortcuts", "skill_ready_at"}:
            self.assertEqual(migrated[key], old[key], key)
        self.assertEqual(rules.migrate_profile(migrated), migrated)
        self.assertEqual(old, before)

    def test_collision_rename_is_deterministic_valid_and_updates_exact_references_only(self):
        old = {"소지품": ["가방"], "소": ["가방"], "소_개인": ["상태"], "소_개인2": ["장비"],
               "ㅂㄷ": ["북동"], "치료": ["회복"], "heal": ["응급치료"],
               "연결": ["소지품", "소", "ㅂㄷ", "치료", "heal", "소 말", "치료 보기"]}
        new = migrate_shortcuts(old)
        self.assertEqual(len(new), len(old))
        self.assertEqual(new["소_개인3"], ["소지품"])
        self.assertEqual(new["연결"], ["소지품_개인", "소_개인3", "ㅂㄷ_개인", "치료_개인", "heal_개인", "소 말", "치료 보기"])
        for name in new:
            self.assertEqual(shortcut_name(name), name)
        self.assertEqual(migrate_shortcuts(new), new)
