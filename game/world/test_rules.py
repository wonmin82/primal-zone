from copy import deepcopy
from random import Random
from unittest import TestCase
from unittest.mock import patch

from world import rules
from world.content import ENEMIES, EQUIPMENT_ACTIONS, EXCHANGE, ITEMS, ROOMS, SHOP, find_id
from world.quests import QUESTS, current_hint


class QuestHintTests(TestCase):
    def test_hint_follows_quest_definitions_and_prerequisites(self):
        profile = rules.new_profile()
        self.assertEqual(current_hint(profile), QUESTS["radio_tower"]["hints"][0])
        profile["quests"]["radio_tower"]["claimed"] = True
        self.assertEqual(current_hint(profile), QUESTS["deep_jungle"]["hints"][0])
        profile["quests"]["deep_jungle"]["claimed"] = True

        third = {
            "name": "다음 지역",
            "requires": ("deep_jungle", "claimed"),
            "steps": (("started", "guide", "npc", "에게 임무 수령"), ("claimed", "guide", "npc", "에게 보고")),
            "hints": ("새 지역에서 임무를 받으세요.", "결과를 보고하세요.", "새 지역 완료."),
        }
        with patch.dict(QUESTS, {"third": third}):
            profile["quests"]["third"] = {"started": False, "claimed": False}
            self.assertEqual(current_hint(profile), third["hints"][0])
            profile["quests"]["third"]["claimed"] = True
            self.assertEqual(current_hint(profile), third["hints"][-1])


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

    def test_equipment_catalog_integrity_and_acquisition(self):
        self.assertEqual(len({item["name"] for item in ITEMS.values()}), len(ITEMS))
        for identity, data in ITEMS.items():
            self.assertEqual(find_id(ITEMS, identity), identity)
            self.assertEqual(find_id(ITEMS, data["name"]), identity)
            self.assertIn(data["slot"], {"weapon", "armor", "consumable", "material", "trophy"})
            if data["slot"] in EQUIPMENT_ACTIONS:
                self.assertTrue(
                    all(isinstance(data[k], int) and data[k] >= 0 for k in ("attack", "defense"))
                )
                sources = set(SHOP) | set(EXCHANGE) | {e["drop"] for e in ENEMIES.values()}
                sources |= set(rules.new_profile()["inventory"])
                self.assertIn(identity, sources)
        for catalog in (SHOP, EXCHANGE):
            for identity, price in catalog.items():
                self.assertIn(identity, ITEMS)
                self.assertGreater(price, 0)
        for enemy in ENEMIES.values():
            self.assertIn(enemy["drop"], ITEMS)
            self.assertTrue(0 <= enemy["chance"] <= 1)

    def test_all_equipment_preserves_inventory_other_slot_and_stats(self):
        for identity, data in ITEMS.items():
            if data["slot"] not in EQUIPMENT_ACTIONS:
                continue
            with self.subTest(item=identity):
                profile = rules.new_profile()
                rules.add_item(profile, identity)
                before = deepcopy(profile)
                rules.equip(profile, identity, expected_slot=data["slot"])
                expected = deepcopy(before)
                expected["equipment"][data["slot"]] = identity
                self.assertEqual(profile, expected)
                equipped = [ITEMS[i] for i in profile["equipment"].values()]
                self.assertEqual(
                    rules.stats(profile)["attack"], 7 + sum(i["attack"] for i in equipped)
                )
                self.assertEqual(
                    rules.stats(profile)["defense"], sum(i["defense"] for i in equipped)
                )
        profile = rules.new_profile()
        for identity in ("spear", "tactical_vest"):
            rules.add_item(profile, identity)
            rules.equip(profile, identity, ITEMS[identity]["slot"])
        self.assertEqual((rules.stats(profile)["attack"], rules.stats(profile)["defense"]), (12, 4))

    def test_wrong_slot_unowned_and_combat_rejections_are_lossless(self):
        for identity, data in ITEMS.items():
            for slot in EQUIPMENT_ACTIONS:
                with self.subTest(item=identity, action_slot=slot):
                    profile = rules.new_profile()
                    rules.add_item(profile, identity)
                    if data["slot"] != slot:
                        before = deepcopy(profile)
                        with self.assertRaises(rules.RuleError):
                            rules.equip(profile, identity, slot)
                        self.assertEqual(profile, before)
                    profile["combat_target"] = 123
                    before = deepcopy(profile)
                    with self.assertRaises(rules.RuleError):
                        rules.equip(profile, identity, slot)
                    self.assertEqual(profile, before)
        for identity in ("heavy_carbine", "heavy_suit"):
            profile = rules.new_profile()
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.equip(profile, identity, ITEMS[identity]["slot"])
            self.assertEqual(profile, before)

    def test_every_purchase_and_exchange_exact_cost_and_lossless_failure(self):
        for exchange, prices in ((False, SHOP), (True, EXCHANGE)):
            for identity, price in prices.items():
                with self.subTest(item=identity, exchange=exchange):
                    profile = rules.new_profile()
                    profile["credits"] = price - 1
                    profile["inventory"]["scrap"] = price - 1
                    before = deepcopy(profile)
                    with self.assertRaises(rules.RuleError):
                        rules.buy(profile, identity, exchange=exchange)
                    self.assertEqual(profile, before)
                    if exchange:
                        profile["inventory"]["scrap"] = price
                    else:
                        profile["credits"] = price
                    expected = deepcopy(profile)
                    if exchange:
                        del expected["inventory"]["scrap"]
                    else:
                        expected["credits"] = 0
                    expected["inventory"][identity] = expected["inventory"].get(identity, 0) + 1
                    rules.buy(profile, identity, exchange=exchange)
                    self.assertEqual(profile, expected)

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
        profile["quests"]["radio_tower"]["started"] = True
        rules.add_item(profile, "scrap", 3)
        with self.assertRaises(rules.RuleError):
            rules.fix_generator(profile)
        profile["quests"]["radio_tower"]["record_read"] = True
        rules.fix_generator(profile)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.fix_generator(profile)
        self.assertEqual(profile, before)

    def test_quest_reward_requires_completion_and_is_once_only(self):
        profile = rules.new_profile()
        with self.assertRaises(rules.RuleError):
            rules.claim_quest(profile)
        profile["quests"]["radio_tower"].update(started=True, generator_fixed=True, boss_defeated=True)
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

    def test_prepared_solo_player_can_beat_jungle_boss(self):
        for seed in range(10):
            profile = rules.new_profile()
            rules.gain_xp(profile, rules.xp_threshold(5))
            profile["inventory"]["bandage"] = 8
            for item in ("carbine", "heavy_suit"):
                rules.add_item(profile, item)
                rules.equip(profile, item)
            profile["combat_target"] = 1
            rng, hp = Random(seed), ENEMIES["jungle_apex"]["hp"]
            for turn in range(1, 51):
                now = turn * 2.5
                if rules.boss_telegraph("jungle_apex", turn - 1):
                    rules.queue_action(profile, "guard", now)
                elif profile["hp"] < 55 and profile["inventory"].get("bandage"):
                    rules.queue_action(profile, "heal", now)
                elif now >= profile["heavy_ready_at"]:
                    rules.queue_action(profile, "heavy", now)
                damage, _ = rules.player_attack(profile, "jungle_apex", now, 2.5, rng)
                hp -= damage
                if hp <= 0:
                    break
                if rules.enemy_attack(profile, "jungle_apex", turn, now, rng)["defeated"]:
                    break
            self.assertLessEqual(hp, 0, f"Solo jungle boss failed with seed {seed}")

    def test_reward_distribution_preserves_pools_and_deterministic_remainders(self):
        groups = {"party:2": {4: 30, 3: 10}, "party:1": {2: 10, 1: 10}}
        result = rules.reward_shares(101, 29, groups)
        self.assertEqual(sum(value["xp"] for value in result.values()), 101)
        self.assertEqual(sum(value["credits"] for value in result.values()), 29)
        self.assertEqual(result[3]["xp"], 34)
        self.assertEqual(result[4]["xp"], 33)
        self.assertEqual(result, rules.reward_shares(101, 29, dict(reversed(list(groups.items())))))


class GrowthRuleTests(TestCase):
    def test_quest_migration_preserves_completion_and_one_time_cache(self):
        old = rules.new_profile()
        old.update(version=3, xp=333, credits=111, visited=["dock", "ridge"])
        old.pop("quests")
        old.pop("discoveries")
        old.update(
            quest_started=True, record_read=True, generator_fixed=True,
            boss_defeated=True, quest_claimed=True, cache_claimed=True,
        )
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated["version"], 4)
        self.assertEqual(migrated["quests"]["radio_tower"], {
            "started": True, "record_read": True, "generator_fixed": True,
            "boss_defeated": True, "claimed": True,
        })
        self.assertTrue(migrated["discoveries"]["supply_cache"])
        self.assertEqual((migrated["xp"], migrated["credits"], migrated["visited"]), (333, 111, ["dock", "ridge"]))
        self.assertEqual(rules.migrate_profile(migrated), migrated)
        for operation in (rules.claim_quest, rules.claim_cache):
            with self.assertRaises(rules.RuleError):
                operation(migrated)

    def test_jungle_objective_requires_both_clues_and_rewards_once(self):
        profile = rules.new_profile()
        profile["quests"]["radio_tower"]["claimed"] = True
        with self.assertRaises(rules.RuleError):
            rules.jungle_mark(profile, "watch_marked")
        self.assertEqual(rules.jungle_talk(profile), "start")
        rules.jungle_mark(profile, "watch_marked")
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.open_jungle_gate(profile)
        self.assertEqual(profile, before)
        self.assertNotIn("jungle_cell", profile["inventory"])
        self.assertTrue(rules.jungle_mark(profile, "road_marked"))
        self.assertEqual(profile["inventory"]["jungle_cell"], 1)
        self.assertFalse(rules.jungle_mark(profile, "road_marked"))
        self.assertEqual(profile["inventory"]["jungle_cell"], 1)
        profile["inventory"].pop("jungle_cell")
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.open_jungle_gate(profile)
        self.assertEqual(profile, before)
        self.assertTrue(rules.jungle_mark(profile, "road_marked"))
        self.assertEqual(profile["inventory"]["jungle_cell"], 1)
        self.assertFalse(rules.jungle_mark(profile, "road_marked"))
        rules.open_jungle_gate(profile)
        self.assertNotIn("jungle_cell", profile["inventory"])
        self.assertTrue(profile["quests"]["deep_jungle"]["gate_open"])
        self.assertFalse(rules.jungle_mark(profile, "road_marked"))
        self.assertNotIn("jungle_cell", profile["inventory"])
        with self.assertRaises(rules.RuleError):
            rules.open_jungle_gate(profile)
        profile["quests"]["deep_jungle"]["boss_defeated"] = True
        before = (profile["xp"], profile["credits"])
        self.assertEqual(rules.jungle_talk(profile), "complete")
        self.assertEqual((profile["xp"] - before[0], profile["credits"] - before[1]), (120, 120))
        self.assertEqual(rules.jungle_talk(profile), "progress")

    def test_migrations_preserve_history_combat_and_baseline(self):
        for version in (1, 2, 3):
            old = rules.new_profile()
            old.update(
                version=version,
                xp=140,
                hp=37,
                credits=81,
                combat_target=123,
                next_attack_at=44,
                heavy_ready_at=99,
                guard_until=55,
                player_round=7,
                queued_action="guard",
            )
            old["quests"]["radio_tower"]["record_read"] = True
            if version < 4:
                old.pop("quests")
                old.pop("discoveries")
                old["record_read"] = True
                old["cache_claimed"] = True
            if version < 3:
                for key in rules.growth_defaults():
                    old.pop(key)
            before = deepcopy(old)
            migrated = rules.migrate_profile(old)
            for key, value in before.items():
                if key not in ("version", "record_read", "cache_claimed"):
                    self.assertEqual(migrated[key], value)
            self.assertTrue(migrated["quests"]["radio_tower"]["record_read"])
            self.assertTrue(migrated["discoveries"]["supply_cache"])
            self.assertEqual(migrated["version"], 4)
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
            visited=["dock", "grass"],
        )
        profile["quests"]["radio_tower"]["started"] = True
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
