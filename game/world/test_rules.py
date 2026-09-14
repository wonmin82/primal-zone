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
        for profile in (base, upgraded):
            rules.start_encounter(profile, "hunter")
        a, _ = rules.combat_round(base, Random(4))
        b, _ = rules.combat_round(upgraded, Random(4))
        self.assertLess(b["encounter"]["hp"], a["encounter"]["hp"])

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

    def test_action_spam_does_not_advance_combat(self):
        profile = rules.new_profile()
        rules.start_encounter(profile, "scavenger")
        for _ in range(30):
            rules.queue_action(profile, "heavy")
        self.assertEqual(profile["encounter"]["round"], 0)
        self.assertEqual(profile["encounter"]["hp"], ENEMIES["scavenger"]["hp"])

    def test_restarting_attack_keeps_enemy_health(self):
        profile = rules.new_profile()
        rules.start_encounter(profile, "hunter")
        profile, _ = rules.combat_round(profile, Random(2))
        before = deepcopy(profile["encounter"])
        rules.start_encounter(profile, "hunter")
        self.assertEqual(profile["encounter"], before)

    def test_heavy_attack_has_a_real_cooldown(self):
        profile = rules.new_profile()
        rules.start_encounter(profile, "alpha")
        rules.queue_action(profile, "heavy")
        profile, _ = rules.combat_round(profile, Random(1))
        with self.assertRaises(rules.RuleError):
            rules.queue_action(profile, "heavy")

    def test_guard_reduces_telegraphed_boss_attack(self):
        profile = rules.new_profile()
        rules.start_encounter(profile, "alpha")
        profile["encounter"]["round"] = 2
        guarded = deepcopy(profile)
        rules.queue_action(guarded, "guard")
        a, _ = rules.combat_round(profile, Random(2))
        b, _ = rules.combat_round(guarded, Random(2))
        self.assertGreater(b["hp"], a["hp"])

    def test_combat_heal_replaces_attack(self):
        profile = rules.new_profile()
        profile["hp"] = 30
        rules.start_encounter(profile, "scavenger")
        rules.queue_action(profile, "heal")
        updated, _ = rules.combat_round(profile, Random(1))
        self.assertEqual(updated["encounter"]["hp"], ENEMIES["scavenger"]["hp"])
        self.assertEqual(updated["inventory"]["bandage"], 2)
        self.assertGreater(updated["hp"], 30)

    def test_kill_reward_is_not_repeatable(self):
        profile = rules.new_profile()
        rules.start_encounter(profile, "scavenger")
        profile["encounter"]["hp"] = 1
        updated, _ = rules.combat_round(profile, Random(4))
        repeated, messages = rules.combat_round(updated, Random(4))
        self.assertIsNone(updated["encounter"])
        self.assertEqual(updated["xp"], 22)
        self.assertEqual(updated["inventory"]["scrap"], 1)
        self.assertEqual(repeated, updated)
        self.assertEqual(messages, [])
        self.assertEqual(profile["xp"], 0)

    def test_defeat_keeps_gear_and_xp_without_negative_currency(self):
        profile = rules.new_profile()
        profile.update(hp=1, credits=3, xp=20)
        rules.start_encounter(profile, "alpha")
        updated, messages = rules.combat_round(profile, Random(4))
        self.assertEqual(updated["credits"], 0)
        self.assertEqual(updated["xp"], 20)
        self.assertEqual(updated["equipment"], profile["equipment"])
        self.assertEqual(updated["hp"], 60)
        self.assertIn("__return_home__", messages)

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
            rules.start_encounter(profile, "alpha")
            rng = Random(seed)
            for _ in range(50):
                encounter = profile["encounter"]
                if not encounter:
                    break
                if encounter["round"] % 3 == 2:
                    rules.queue_action(profile, "guard")
                elif profile["hp"] < 45 and profile["inventory"].get("bandage"):
                    rules.queue_action(profile, "heal")
                elif encounter["round"] + 1 >= encounter["heavy_ready"]:
                    rules.queue_action(profile, "heavy")
                profile, _ = rules.combat_round(profile, rng)
            self.assertTrue(profile["boss_defeated"], f"Solo boss failed with seed {seed}")
