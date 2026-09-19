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
