"""장기 성장·기술 수학, 저장 변환과 원자적 실패 경계."""

from copy import deepcopy
from json import dumps, loads
from random import Random
from unittest import TestCase
from unittest.mock import Mock, patch

from world import progression as pg
from world import rules
from world import text as ft


def at_level(level):
    profile = rules.new_profile()
    profile["xp"] = rules.xp_threshold(level)
    profile["hp"] = rules.stats(profile)["max_hp"]
    profile["mental"] = rules.stats(profile)["max_mental"]
    return profile


class ProgressionTests(TestCase):
    def test_numeric_particles_for_effective_healing_and_training_values(self):
        self.assertEqual(ft.particle(12, "을/를"), "를")
        self.assertEqual(ft.particle(20, "을/를"), "을")
        self.assertEqual(ft.particle(23, "으로/로"), "으로")
        self.assertEqual(ft.particle(21, "으로/로"), "로")

    def test_level_stats_and_transition(self):
        expected = {1: (60, 40, 7, 0), 10: (150, 85, 25, 4), 11: (153, 87, 25, 4),
                    20: (180, 105, 27, 6), 50: (270, 165, 35, 12), 75: (345, 215, 41, 17),
                    100: (420, 265, 47, 22), 126: (498, 317, 54, 27), 133: (519, 331, 55, 28)}
        for level, values in expected.items():
            with self.subTest(level=level):
                self.assertEqual(tuple(pg.base_stats(level).values()), values)
        self.assertEqual(rules.xp_threshold(37), 14760)
        self.assertEqual(rules.xp_threshold(133), 180840)

    def test_attribute_and_training_completion(self):
        for level, total in ((1, 4), (10, 22), (20, 27), (30, 32), (50, 42), (75, 54), (100, 67), (120, 77), (124, 79), (126, 80)):
            self.assertEqual(pg.attribute_points(level), total)
        for level in range(127, 134):
            self.assertEqual(pg.attribute_points(level), 80)
        profile = at_level(133)
        for skill, data in pg.SKILLS.items():
            for _ in range(data["max_rank"] - 1):
                rules.learn_skill(profile, skill, safe=True)
        self.assertEqual(rules.point_pools(profile)["skill_spent"], 132)
        self.assertEqual(rules.point_pools(profile)["skill_points"], 0)
        for attribute in pg.ATTRIBUTES:
            rules.allocate_attribute(profile, attribute, 20, safe=True)
        self.assertEqual(rules.stats(profile)["max_mental"], 411)
        self.assertEqual(rules.stats(profile)["max_hp"], 599)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.allocate_attribute(profile, "strength", safe=True)
        self.assertEqual(profile, before)

    def test_training_rejections_do_not_partially_apply(self):
        for level, amount in ((1, 5), (133, 21)):
            profile = at_level(level)
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.allocate_attribute(profile, "strength", amount, safe=True)
            self.assertEqual(profile, before)
        profile = at_level(1)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.learn_skill(profile, "heavy", safe=True)
        self.assertEqual(profile, before)

    def test_migration_preserves_progress_returns_training_and_is_idempotent(self):
        old = at_level(37)
        old.update(version=9, skills={"heavy": 3, "guard": 3, "firstaid": 3},
                   proficiencies={"weapon": {"xp": 999}}, guard_until=500,
                   queued_action="guard", command_shortcuts={"호흡": ["응급처치"], "점검": ["호흡", "방어", "방어 말"]})
        old["attributes"]["strength"]["allocated"] = 99
        old["attributes"]["wisdom"]["allocated"] = 99
        before = deepcopy(old)
        migrated = rules.migrate_profile(old)
        self.assertEqual(old, before)
        self.assertEqual(migrated["version"], 10)
        self.assertNotIn("proficiencies", migrated)
        self.assertNotIn("guard_until", migrated)
        self.assertEqual(set(migrated["skills"].values()), {1})
        self.assertEqual(rules.point_pools(migrated)["skill_points"], 36)
        self.assertLessEqual(rules.point_pools(migrated)["attribute_spent"], pg.attribute_points(37))
        for field in ("xp", "credits", "equipment", "inventory", "quests", "visited", "discoveries"):
            self.assertEqual(migrated[field], old[field])
        self.assertEqual(migrated["command_shortcuts"], {"호흡_개인": ["붕대 사용"], "점검": ["호흡_개인", "견제", "방어 말"]})
        self.assertEqual(rules.migrate_profile(migrated), migrated)
        broken = at_level(1)
        broken["skills"] = {"heavy": 999, "attack": -3, "heal": "bad"}
        migrated = rules.migrate_profile(broken)
        self.assertEqual(set(migrated["skills"].values()), {1})
        self.assertEqual(rules.point_pools(migrated)["skill_points"], 0)

    def test_mental_costs_ignore_wisdom(self):
        skills = ("heavy", "shooting", "insight", "suppress", "heal")
        for level, costs in ((1, (8, 6, 8, 6, 10)), (10, (8, 6, 8, 6, 10)), (50, (8, 6, 9, 8, 10)), (100, (12, 10, 14, 12, 16)), (133, (15, 12, 17, 15, 20))):
            self.assertEqual(tuple(pg.mental_cost(skill, level) for skill in skills), costs)

    def test_rank_formulas_and_penetration(self):
        self.assertAlmostEqual(pg.attack_multiplier(30), 1.145)
        self.assertAlmostEqual(pg.defense_reduction(20), 0.152)
        self.assertAlmostEqual(pg.physical_multiplier("heavy", 20), 2.37)
        self.assertAlmostEqual(pg.physical_multiplier("shooting", 20), 1.435)
        self.assertAlmostEqual(pg.combined_penetration(pg.insight_effect(10)["penetration"], pg.shooting_penetration(20)), .544)
        for rank, cd in ((1, 7.5), (7, 7.5), (8, 7), (14, 7), (15, 6.5), (20, 6.5)):
            self.assertEqual(pg.cooldown("heavy", rank), cd)
        for rank, count in ((1, 1), (3, 1), (4, 2), (6, 2), (7, 3), (9, 3), (10, 4)):
            effect = pg.suppression_effect(rank)
            self.assertEqual(effect["attacks"], count)
            self.assertAlmostEqual(pg.suppression_effect(rank, True)["reduction"], effect["reduction"] / 2)

    def test_suppression_refresh_and_one_event_consumption(self):
        stronger, status = pg.apply_suppression({}, 1, 7)
        self.assertEqual(status, "applied")
        self.assertEqual(pg.apply_suppression(stronger, 1, 2), (stronger, "preserved"))
        once = pg.consume_suppressions(stronger)
        self.assertEqual(once["1"]["attacks"], 2)
        refreshed, status = pg.apply_suppression(once, "1", 7)
        self.assertEqual((refreshed["1"]["attacks"], status), (3, "refreshed"))
        upgraded, status = pg.apply_suppression(once, 1, 10)
        self.assertEqual((upgraded["1"]["attacks"], status), (4, "upgraded"))
        for _ in range(3):
            stronger = pg.consume_suppressions(stronger)
        self.assertEqual(stronger, {})

    def test_source_suppression_stacking_boss_and_serialization_contract(self):
        for rank, reduction in ((1, .10), (5, .14), (10, .19)):
            self.assertAlmostEqual(pg.suppression_effect(rank)["reduction"], reduction)
        for boss, expected in ((False, .56953279), (True, .329198049375)):
            effects = {}
            for source in range(4):
                effects, status = pg.apply_suppression(effects, source, 10, boss)
                self.assertEqual(status, "applied")
                if source == 1 and not boss:
                    self.assertAlmostEqual(pg.combined_suppression(effects, boss), .3439)
            self.assertAlmostEqual(pg.combined_suppression(effects, boss), expected)
            self.assertEqual(loads(dumps(effects)), effects)
            before = deepcopy(effects)
            changed, _ = pg.apply_suppression(effects, 0, 7, boss)
            self.assertEqual(changed, effects)
            self.assertEqual(effects, before)
            consumed = pg.consume_suppressions(effects)
            self.assertEqual({effect["attacks"] for effect in consumed.values()}, {3})
            self.assertEqual(effects, before)
        mixed = {"A": pg.suppression_effect(10), "B": pg.suppression_effect(4), "C": pg.suppression_effect(1)}
        consumed = pg.consume_suppressions(mixed)
        self.assertEqual({key: effect["attacks"] for key, effect in consumed.items()}, {"A": 3, "B": 1})
        refreshed, status = pg.apply_suppression(consumed, "B", 4)
        self.assertEqual(status, "refreshed")
        self.assertEqual(refreshed["B"]["attacks"], 2)
        self.assertEqual(refreshed["A"], consumed["A"])
        self.assertEqual(pg.combined_suppression({}), 0)

    def test_suppression_cap_limits_reduction_not_sources_or_consumption(self):
        for boss, individual, cap in ((False, .19, .56953279), (True, .095, .329198049375)):
            with self.subTest(boss=boss):
                effects = {}
                self.assertAlmostEqual(pg.suppression_cap(boss), cap)
                for source in range(8):
                    effects, _ = pg.apply_suppression(effects, source, 10, boss)
                    self.assertEqual(len(effects), source + 1)
                    self.assertAlmostEqual(pg.combined_suppression(effects, boss),
                                           min(1 - (1 - individual) ** (source + 1), cap))
                before = deepcopy(effects)
                remaining = pg.consume_suppressions(effects)
                self.assertEqual(set(remaining), {str(source) for source in range(8)})
                self.assertEqual({effect["attacks"] for effect in remaining.values()}, {3})
                self.assertEqual(effects, before)
                for _ in range(3):
                    remaining = pg.consume_suppressions(remaining)
                self.assertEqual(remaining, {})
                # Weak sources are not individually discarded merely for exceeding four.
                weak = {str(source): pg.suppression_effect(1, boss) for source in range(5)}
                self.assertAlmostEqual(pg.combined_suppression(weak, boss),
                                       1 - (1 - pg.suppression_effect(1, boss)["reduction"]) ** 5)

    def test_suppression_boss_flag_is_independent_of_quest_metadata(self):
        for boss, quest, expected in ((True, None, .095), (False, "radio_tower", .19)):
            definition = {**rules.ENEMIES["alpha"], "boss": boss}
            definition.pop("boss_quest", None)
            if quest:
                definition["boss_quest"] = quest
            with self.subTest(boss=boss), patch.dict(rules.ENEMIES, alpha=definition):
                p = at_level(50)
                p.update(combat_target=1, queued_action="suppress")
                p["skills"]["suppress"] = 10
                _, outcome = rules.player_attack(p, "alpha", 100, 2.5, Random(1))
                self.assertAlmostEqual(outcome["suppression"]["reduction"], expected)

    def test_mental_shortage_uses_actual_cost_and_preserves_state_and_priority(self):
        for level, costs in ((1, (8, 6, 8, 6, 10)), (133, (15, 12, 17, 15, 20))):
            for action, cost in zip(("heavy", "shooting", "insight", "suppress", "heal"), costs):
                with self.subTest(level=level, action=action):
                    p = at_level(level)
                    p.update(mental=cost - 1, combat_target=1)
                    p["equipment"]["weapon"] = "carbine" if action == "shooting" else "machete"
                    target = at_level(level)
                    target["hp"] -= 10
                    before, target_before = deepcopy(p), deepcopy(target)
                    with self.assertRaises(rules.RuleError) as error:
                        rules.queue_action(p, action, 100, target)
                    self.assertIn(pg.SKILLS[action]["name"], str(error.exception))
                    self.assertIn(f"정신력이 {cost} 필요하다", str(error.exception))
                    self.assertEqual(p, before)
                    self.assertEqual(target, target_before)
                    if action == "heal":
                        with self.assertRaises(rules.RuleError):
                            rules.support_action(p, action, 100, target)
                        self.assertEqual((p, target), (before, target_before))
                    p["skill_ready_at"][action] = 110
                    before = deepcopy(p)
                    with self.assertRaisesRegex(rules.RuleError, "10초 더 기다려야"):
                        rules.queue_action(p, action, 100, target)
                    self.assertEqual(p, before)

    def test_insight_and_suppress_deadlines_survive_migration_and_retraining(self):
        for skill in ("insight", "suppress"):
            p = at_level(50)
            p.update(combat_target=1, queued_action=skill)
            rules.player_attack(p, "alpha", 100, 2.5, Random(1))
            self.assertEqual(pg.cooldown(skill, 1), 10)
            self.assertEqual(p["skill_ready_at"][skill], 110)
            for scope in ("skills", "all"):
                reloaded = rules.migrate_profile(p)
                reloaded["combat_target"] = None
                rules.retrain(reloaded, scope, safe=True)
                reloaded["combat_target"] = 1
                before = deepcopy(reloaded)
                with self.assertRaisesRegex(rules.RuleError, "7초"):
                    rules.queue_action(reloaded, skill, 103)
                self.assertEqual(reloaded, before)
                rules.queue_action(reloaded, skill, 110)

    def test_equipment_restrictions_and_atomic_cost_failure(self):
        p = at_level(20)
        p["combat_target"] = 1
        for action in ("shooting",):
            before = deepcopy(p)
            with self.assertRaises(rules.RuleError):
                rules.queue_action(p, action, 100)
            self.assertEqual(p, before)
        p["equipment"]["weapon"] = "carbine"
        before = deepcopy(p)
        with self.assertRaises(rules.RuleError):
            rules.queue_action(p, "heavy", 100)
        self.assertEqual(p, before)
        p["mental"] = 0
        with self.assertRaises(rules.RuleError):
            rules.queue_action(p, "shooting", 100)

    def test_insight_survives_support_consumes_on_hit_and_retargets(self):
        p = at_level(50)
        p.update(combat_target=1, queued_action="insight", hp=100)
        self.assertEqual(rules.player_attack(p, "alpha", 100, 2.5)[0], 0)
        original = deepcopy(p["insight"])
        p["queued_action"] = "heal"
        self.assertEqual(rules.player_attack(p, "alpha", 102.5, 2.5)[0], 0)
        self.assertEqual(p["insight"], original)
        p["queued_action"] = "heavy"
        damage, outcome = rules.player_attack(p, "alpha", 105, 2.5, Random(1))
        self.assertGreater(damage, 0)
        self.assertTrue(outcome["insight"])
        self.assertIsNone(p["insight"])
        p["insight"] = original
        p.update(combat_target=2, queued_action="insight")
        rules.player_attack(p, "alpha", 110, 2.5)
        self.assertEqual(p["insight"]["target"], 2)

    def test_support_effective_healing_bandage_breathing_and_absolute_cooldowns(self):
        p = at_level(133)
        p["attributes"]["wisdom"]["allocated"] = 20
        p["skills"]["heal"] = 20
        p["hp"] -= 2
        outcome = rules.support_action(p, "heal", 100)
        self.assertEqual((outcome["amount"], outcome["cost"]), (2, 20))
        p["hp"] -= 100
        with self.assertRaises(rules.RuleError):
            rules.support_action(rules.migrate_profile(p), "heal", 109)
        p["mental"] = 0
        p["skills"]["breathing"] = 10
        self.assertEqual(rules.support_action(p, "breathing", 200)["amount"], 57)
        self.assertEqual(p["skill_ready_at"]["breathing"], 220)
        before_mental = p["mental"]
        self.assertEqual(rules.support_action(p, "bandage", 200)["amount"], 20)
        self.assertEqual(p["mental"], before_mental)
        p["hp"] = rules.stats(p)["max_hp"]
        before = deepcopy(p)
        with self.assertRaises(rules.RuleError):
            rules.support_action(p, "bandage", 201)
        self.assertEqual(p, before)

    def test_passive_damage_final_multiplier_defense_order_and_minimum(self):
        p = at_level(133)
        plain = deepcopy(p)
        p["skills"]["attack"] = 30
        p.update(combat_target=1)
        plain.update(combat_target=1)
        a = rules.player_attack(plain, "alpha", 100, 2.5, Random(1))[0]
        b = rules.player_attack(p, "alpha", 100, 2.5, Random(1))[0]
        self.assertGreater(b, a)
        p["skills"]["defense"] = 20
        p["proficiencies"] = {"weapon": {"xp": 999999}}
        self.assertEqual(rules.stats(p), rules.stats(plain))
        self.assertEqual(rules.enemy_attack(p, "scavenger", 1, 100)["damage"], 1)

    def test_insight_shooting_and_heavy_apply_penetration_before_final_multipliers(self):
        p = at_level(133)
        p.update(combat_target=1, queued_action="insight")
        p["skills"].update(attack=30, insight=10, shooting=20, heavy=20)
        rules.player_attack(p, "alpha", 100, 2.5)
        p["equipment"]["weapon"] = "carbine"
        p["queued_action"] = "shooting"
        damage, outcome = rules.player_attack(p, "alpha", 102.5, 2.5, Mock(randint=Mock(return_value=0)))
        self.assertEqual(damage, 119)
        self.assertTrue(outcome["insight"])
        self.assertIsNone(p["insight"])
        self.assertEqual(p["mental"], 331 - 17 - 12)
        p["equipment"]["weapon"] = "machete"
        p["queued_action"] = "insight"
        rules.player_attack(p, "alpha", 110, 2.5)
        p["queued_action"] = "heavy"
        self.assertEqual(rules.player_attack(p, "alpha", 112.5, 2.5, Mock(randint=Mock(return_value=0)))[0], 174)

    def test_passive_defense_after_fixed_defense_and_charge_and_breathing_tiers(self):
        p = at_level(20)
        p["attributes"]["agility"]["allocated"] = 3
        p["skills"]["defense"] = 20
        self.assertEqual(rules.stats(p)["defense"], 8)
        self.assertEqual(rules.enemy_attack(p, "alpha", 1, 100, Mock(randint=Mock(return_value=0)))["damage"], 7)
        self.assertEqual(rules.enemy_attack(p, "alpha", 3, 103, Mock(randint=Mock(return_value=0)))["damage"], 15)
        for rank, seconds in ((1, 30), (3, 30), (4, 27), (6, 27), (7, 24), (9, 24), (10, 20)):
            self.assertEqual(pg.cooldown("breathing", rank), seconds)
