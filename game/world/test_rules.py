from copy import deepcopy
from random import Random
from unittest import TestCase

from world import rules
from world.content import ENEMIES, ROOMS


class RuleTests(TestCase):
    def test_profiles_do_not_share_inventory(self):
        first, second = rules.new_profile(), rules.new_profile()
        rules.add_item(first, "blade")
        self.assertNotIn("blade", second["inventory"])

    def test_equipping_changes_actual_damage(self):
        base = rules.new_profile()
        upgraded = deepcopy(base)
        rules.add_item(upgraded, "blade")
        rules.equip(upgraded, "blade")
        a, _ = rules.player_attack(base, "hunter", 100, 2.5, Random(4))
        b, _ = rules.player_attack(upgraded, "hunter", 100, 2.5, Random(4))
        self.assertGreater(b, a)

    def test_unowned_item_cannot_be_equipped(self):
        profile = rules.new_profile()
        with self.assertRaises(rules.RuleError):
            rules.equip(profile, "carbine")
        self.assertEqual(profile["equipment"]["weapon"], "machete")

    def test_lossless_rejection_when_currency_is_insufficient(self):
        profile = rules.new_profile()
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.buy(profile, "carbine")
        self.assertEqual(profile, before)

    def test_exchange_is_a_guaranteed_gear_path(self):
        profile = rules.new_profile()
        rules.add_item(profile, "scrap", 6)
        rules.buy(profile, "blade", exchange=True)
        self.assertEqual(profile["inventory"]["blade"], 1)
        self.assertNotIn("scrap", profile["inventory"])

    def test_heal_is_capped_and_consumes_one_bandage(self):
        profile = rules.new_profile()
        profile["hp"] -= 4
        self.assertEqual(rules.heal(profile), 4)
        self.assertEqual(profile["hp"], 60)
        self.assertEqual(profile["inventory"]["bandage"], 2)
        with self.assertRaises(rules.RuleError):
            rules.heal(profile)
        self.assertEqual(profile["inventory"]["bandage"], 2)

    def test_action_spam_and_heavy_cooldown(self):
        profile = rules.new_profile()
        profile["combat_target"] = 1
        for _ in range(30):
            rules.queue_action(profile, "heavy", now=100)
        self.assertEqual(profile["player_round"], 0)
        rules.player_attack(profile, "alpha", 100, 2.5, Random(1))
        with self.assertRaises(rules.RuleError):
            rules.queue_action(profile, "heavy", now=102.5)
        rules.queue_action(profile, "heavy", now=107.5)

    def test_guard_reduces_shared_boss_charge(self):
        plain, guarded = rules.new_profile(), rules.new_profile()
        guarded["guard_until"] = 101
        a = rules.enemy_attack(plain, "alpha", 3, 100, Random(2))
        b = rules.enemy_attack(guarded, "alpha", 3, 100, Random(2))
        self.assertTrue(a["charged"])
        self.assertLess(b["damage"], a["damage"])

    def test_combat_heal_replaces_attack(self):
        profile = rules.new_profile()
        profile.update(hp=30, combat_target=1)
        rules.queue_action(profile, "heal", now=100)
        damage, _ = rules.player_attack(profile, "scavenger", 100, 2.5, Random(1))
        self.assertEqual(damage, 0)
        self.assertEqual(profile["inventory"]["bandage"], 2)
        self.assertEqual(profile["hp"], 60)

    def test_defeat_is_structured_and_preserves_growth(self):
        profile = rules.new_profile()
        profile.update(hp=1, credits=3, xp=20)
        outcome = rules.enemy_attack(profile, "alpha", 3, 100, Random(4))
        self.assertTrue(outcome["defeated"])
        self.assertEqual((profile["credits"], profile["xp"], profile["hp"]), (0, 20, 60))

    def test_multiple_level_gains_cap_at_ten(self):
        profile = rules.new_profile()
        self.assertEqual(rules.gain_xp(profile, 100000), 9)
        self.assertEqual(rules.level_of(profile), 10)
        self.assertEqual(profile["hp"], rules.stats(profile)["max_hp"])

    def test_generator_requires_clue_and_consumes_materials_once(self):
        profile = rules.new_profile()
        profile["quest_started"] = True
        rules.add_item(profile, "scrap", 3)
        with self.assertRaises(rules.RuleError):
            rules.fix_generator(profile)
        profile["record_read"] = True
        rules.fix_generator(profile)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.fix_generator(profile)
        self.assertEqual(profile, before)

    def test_quest_reward_requires_completion_and_is_once_only(self):
        profile = rules.new_profile()
        with self.assertRaises(rules.RuleError):
            rules.claim_quest(profile)
        profile.update(quest_started=True, generator_fixed=True, boss_defeated=True)
        rules.claim_quest(profile)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.claim_quest(profile)
        self.assertEqual(profile, before)

    def test_all_locations_are_reachable_and_exits_are_valid(self):
        visited, pending = set(), ["dock"]
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            visited.add(key)
            for target in ROOMS[key]["exits"].values():
                self.assertIn(target, ROOMS)
                pending.append(target)
        self.assertEqual(visited, set(ROOMS))

    def test_prepared_solo_player_can_beat_boss_across_rng_seeds(self):
        for seed in range(20):
            profile = rules.new_profile()
            rules.gain_xp(profile, rules.xp_threshold(4))
            for item in ("carbine", "armor"):
                rules.add_item(profile, item)
                rules.equip(profile, item)
            profile["combat_target"] = 1
            rng, hp = Random(seed), ENEMIES["alpha"]["hp"]
            defeated = False
            for turn in range(1, 51):
                now = turn * 2.5
                if turn % 3 == 0:
                    rules.queue_action(profile, "guard", now)
                elif profile["hp"] < 45 and profile["inventory"].get("bandage"):
                    rules.queue_action(profile, "heal", now)
                elif now >= profile["heavy_ready_at"]:
                    rules.queue_action(profile, "heavy", now)
                damage, _ = rules.player_attack(profile, "alpha", now, 2.5, rng)
                hp -= damage
                if hp <= 0:
                    break
                defeated = rules.enemy_attack(profile, "alpha", turn, now, rng)["defeated"]
                if defeated:
                    break
            self.assertFalse(defeated, f"Solo boss failed with seed {seed}")
            self.assertLessEqual(hp, 0)

    def test_reward_distribution_preserves_pools_and_deterministic_remainders(self):
        groups = {"party:2": {4: 30, 3: 10}, "party:1": {2: 10, 1: 10}}
        result = rules.reward_shares(101, 29, groups)
        self.assertEqual(sum(value["xp"] for value in result.values()), 101)
        self.assertEqual(sum(value["credits"] for value in result.values()), 29)
        self.assertEqual(result[3]["xp"], 34)
        self.assertEqual(result[4]["xp"], 33)
        self.assertEqual(result, rules.reward_shares(101, 29, dict(reversed(list(groups.items())))))


class GrowthRuleTests(TestCase):
    def test_migrations_preserve_history_combat_and_baseline(self):
        for version in (1, 2, 3):
            old = rules.new_profile()
            old.update(
                version=version,
                xp=140,
                hp=37,
                credits=81,
                record_read=True,
                combat_target=123,
                next_attack_at=44,
                heavy_ready_at=99,
                guard_until=55,
                player_round=7,
                queued_action="guard",
            )
            if version < 3:
                for key in rules.growth_defaults():
                    old.pop(key)
            before = deepcopy(old)
            migrated = rules.migrate_profile(old)
            for key, value in before.items():
                if key != "version":
                    self.assertEqual(migrated[key], value)
            self.assertEqual(migrated["version"], 3)
            self.assertEqual(rules.migrate_profile(migrated), migrated)
            self.assertEqual(old, before)
            self.assertEqual(rules.stats(old), rules.stats(migrated))

    def test_attribute_budget_and_hp_never_heals(self):
        profile = rules.new_profile()
        profile["hp"] = 40
        for _ in range(10):
            rules.allocate_attribute(profile, "constitution", 4, safe=True)
            self.assertEqual(rules.stats(profile)["max_hp"], 76)
            self.assertEqual(profile["hp"], 40)
            self.assertEqual(rules.point_pools(profile)["attribute_points"], 0)
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.allocate_attribute(profile, "strength", safe=True)
            self.assertEqual(profile, before)
            rules.retrain(profile, "attributes", safe=True)
            self.assertEqual(rules.point_pools(profile)["attribute_points"], 4)
            self.assertEqual(profile["hp"], 40)
        rules.allocate_attribute(profile, "constitution", 4, safe=True)
        profile["hp"] = 75
        rules.retrain(profile, "attributes", safe=True)
        self.assertEqual(profile["hp"], 60)

    def test_skill_costs_limits_and_failure_atomicity(self):
        profile = rules.new_profile()
        profile.update(xp=140, credits=100)
        rules.learn_skill(profile, "heavy", safe=True)
        self.assertEqual((profile["skills"]["heavy"], profile["credits"]), (2, 96))
        rules.learn_skill(profile, "heavy", safe=True)
        self.assertEqual((profile["skills"]["heavy"], profile["credits"]), (3, 88))
        for skill, credits in (("heavy", 88), ("guard", 0)):
            profile["credits"] = credits
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.learn_skill(profile, skill, safe=True)
            self.assertEqual(profile, before)
        profile["credits"] = 100
        rules.learn_skill(profile, "guard", safe=True)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.learn_skill(profile, "heal", safe=True)
        self.assertEqual(profile, before)

    def test_retraining_preserves_history_and_separate_pools(self):
        profile = rules.new_profile()
        profile.update(
            xp=140,
            credits=1000,
            hp=47,
            heavy_ready_at=100,
            next_attack_at=90,
            guard_until=80,
            queued_action="guard",
            quest_started=True,
            visited=["dock", "grass"],
        )
        profile["proficiencies"]["weapon"]["xp"] = 45
        baseline = deepcopy(profile)
        for scope in ("attributes", "skills", "all"):
            for _ in range(4):
                profile = deepcopy(baseline)
                rules.allocate_attribute(profile, "strength", 2, safe=True)
                rules.learn_skill(profile, "heavy", safe=True)
                before = deepcopy(profile)
                rules.retrain(profile, scope, safe=True)
                for key in baseline:
                    if key not in ("attributes", "skills"):
                        self.assertEqual(profile[key], before[key])
                self.assertEqual(
                    profile["attributes"]["strength"]["allocated"], 2 if scope == "skills" else 0
                )
                self.assertEqual(profile["skills"]["heavy"], 2 if scope == "attributes" else 1)
                first = deepcopy(profile)
                rules.retrain(profile, scope, safe=True)
                self.assertEqual(profile, first)
                pools = rules.point_pools(profile)
                for kind in ("attribute", "skill"):
                    self.assertEqual(
                        pools[kind + "_total"], pools[kind + "_spent"] + pools[kind + "_points"]
                    )

    def test_training_restrictions_do_not_mutate(self):
        for combat, safe in ((None, False), (123, True)):
            profile = rules.new_profile()
            profile["combat_target"] = combat
            before = deepcopy(profile)
            for operation in (
                lambda: rules.allocate_attribute(profile, "strength", safe=safe),
                lambda: rules.learn_skill(profile, "heavy", safe=safe),
                lambda: rules.retrain(profile, "all", safe=safe),
            ):
                with self.assertRaises(rules.RuleError):
                    operation()
                self.assertEqual(profile, before)

    def test_proficiency_effects_caps_and_failed_healing(self):
        profile = rules.new_profile()
        for _ in range(250):
            rules.train_proficiency(profile, "weapon", 0, 10)
        self.assertEqual(profile["proficiencies"]["weapon"]["xp"], 0)
        for _ in range(250):
            rules.train_proficiency(profile, "weapon", 1, 2)
        self.assertEqual(rules.proficiency_rank(profile, "weapon"), 2)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.heal(profile)
        self.assertEqual(profile, before)
        profile["hp"] = 30
        rules.heal(profile)
        self.assertEqual(profile["proficiencies"]["medicine"]["xp"], 1)
        profile["combat_target"] = 1
        rules.queue_action(profile, "guard", now=100)
        self.assertEqual(profile["proficiencies"]["defense"]["xp"], 0)
        profile["guard_until"] = 110
        rules.enemy_attack(profile, "alpha", 1, 105, Random(1))
        self.assertEqual(profile["proficiencies"]["defense"]["xp"], 1)

    def test_each_attribute_and_skill_rank_changes_effect(self):
        profile = rules.new_profile()
        profile.update(xp=rules.xp_threshold(10), credits=100)
        base = rules.stats(profile)
        rules.allocate_attribute(profile, "strength", 2, safe=True)
        rules.allocate_attribute(profile, "agility", 3, safe=True)
        rules.allocate_attribute(profile, "wisdom", 2, safe=True)
        self.assertEqual(rules.stats(profile)["attack"], base["attack"] + 1)
        self.assertEqual(rules.stats(profile)["defense"], base["defense"] + 1)
        profile["hp"] = 1
        self.assertEqual(rules.heal(profile), 39)
        rules.learn_skill(profile, "heal", safe=True)
        profile["hp"] = 1
        self.assertEqual(rules.heal(profile), 44)
        normal = deepcopy(profile)
        improved = deepcopy(profile)
        rules.learn_skill(improved, "heavy", safe=True)
        for data in (normal, improved):
            data.update(combat_target=1, queued_action="heavy")
        a, _ = rules.player_attack(normal, "alpha", 100, 2.5, Random(1))
        b, _ = rules.player_attack(improved, "alpha", 100, 2.5, Random(1))
        self.assertGreater(b, a)
        improved["combat_target"] = None
        rules.learn_skill(improved, "guard", safe=True)
        for data in (normal, improved):
            data.update(hp=100, guard_until=110)
        a = rules.enemy_attack(normal, "alpha", 3, 105, Random(1))
        b = rules.enemy_attack(improved, "alpha", 3, 105, Random(1))
        self.assertLess(b["damage"], a["damage"])

    def test_invalid_allocations_and_rank_requirement_are_lossless(self):
        profile = rules.new_profile()
        for amount in (0, -1, True, 1.5, 999):
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.allocate_attribute(profile, "strength", amount, safe=True)
            self.assertEqual(profile, before)
        rules.learn_skill(profile, "heavy", safe=True)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.learn_skill(profile, "heavy", safe=True)
        self.assertEqual(profile, before)
