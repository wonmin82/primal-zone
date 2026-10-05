from copy import deepcopy
from random import Random
from unittest import TestCase
from unittest.mock import patch

from world import rules
from world.content import (
    ENEMIES,
    EQUIPMENT_ACTIONS,
    ITEMS,
    ROOMS,
    SALVAGE_CREDIT_RATE,
    SHOP_CATALOGS,
    find_id,
)
from world.content.headquarters import ROOF_ROOMS
from world.navigation import entry_block
from world.quests import QUESTS, current_hint


class ObservationContentRulesTests(TestCase):
    def test_navigation_requirements_are_pure_and_keep_existing_messages(self):
        for zone, room in ROOMS.items():
            profile = rules.new_profile()
            before = deepcopy(profile)
            block = entry_block(profile, zone)
            self.assertEqual(block, room.get("requires"))
            self.assertEqual(profile, before)
            if block:
                self.assertTrue(block["message"])
                profile["quests"][block["quest"]][block["flag"]] = True
                self.assertIsNone(entry_block(profile, zone))
        self.assertIsNone(entry_block({}, "not_a_zone"))

    def test_content_separates_static_traces_and_enemy_presentations(self):
        for definition in ENEMIES.values():
            self.assertTrue(definition["presence"])
            self.assertTrue(definition["distant_presence"])
            for room in ROOMS.values():
                self.assertNotIn(definition["presence"], room["desc"])
                self.assertNotIn(definition["distant_presence"], room["desc"])
        for zone, trace in (("trail", "발톱 자국"), ("ridge", "철골"), ("jungle_road", "노면"), ("jungle_watch", "난간"), ("jungle_fen", "나무뿌리"), ("jungle_grove", "문틀"), ("jungle_gate", "외벽")):
            self.assertIn(trace, ROOMS[zone]["desc"])
        self.assertNotIn("신호 장치", ROOMS["jungle_grove"]["desc"])
        self.assertNotIn("보급 주머니", ROOMS["jungle_fen"]["desc"])
        self.assertNotIn("탐사 표식", ROOMS["jungle_watch"]["desc"])


class ItemInteractionRulesTests(TestCase):
    def test_transfer_reserves_only_equipped_copies_and_removes_zero_stack(self):
        profile = rules.new_profile()
        profile["inventory"]["machete"] = 3
        destination = {}
        self.assertEqual(rules.move_item(profile["inventory"], destination, "machete", equipment=profile["equipment"]), 1)
        self.assertEqual(rules.move_item(profile["inventory"], destination, "machete", equipment=profile["equipment"], all_items=True), 1)
        self.assertEqual(profile["inventory"]["machete"], 1)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.move_item(profile["inventory"], destination, "machete", equipment=profile["equipment"])
        self.assertEqual(profile, before)
        rules.move_item(profile["inventory"], destination, "bandage", all_items=True)
        self.assertNotIn("bandage", profile["inventory"])
        self.assertEqual(destination, {"machete": 2, "bandage": 3})

    def test_quest_key_cannot_be_moved_and_reacquisition_does_not_duplicate(self):
        profile = rules.new_profile()
        profile["quests"]["radio_tower"]["claimed"] = True
        rules.jungle_talk(profile)
        rules.jungle_mark(profile, "watch_marked")
        rules.jungle_mark(profile, "road_marked")
        before = deepcopy(profile)
        destination = {}
        with self.assertRaises(rules.RuleError):
            rules.move_item(profile["inventory"], destination, "jungle_cell", all_items=True)
        self.assertEqual(profile, before)
        self.assertEqual(destination, {})
        self.assertFalse(rules.jungle_mark(profile, "road_marked"))
        self.assertEqual(profile["inventory"]["jungle_cell"], 1)
        rules.open_jungle_gate(profile)
        self.assertNotIn("jungle_cell", profile["inventory"])

    def test_consumption_uses_metadata_without_training_and_preserves_failure(self):
        for identity, action in (("field_ration", "먹어"), ("water", "마셔")):
            with self.subTest(identity=identity):
                profile = rules.new_profile()
                rules.buy(profile, "supply", identity)
                profile["hp"] = 20
                before = deepcopy(profile["skills"])
                self.assertEqual(rules.eat_or_drink(profile, identity, action), ITEMS[identity]["heal"])
                self.assertEqual(profile["hp"], 20 + ITEMS[identity]["heal"])
                self.assertEqual(profile["skills"], before)
                self.assertNotIn(identity, profile["inventory"])
                self.assertEqual(ITEMS["bandage"]["heal"], 20)
        for identity, action, hp, combat in (
            ("field_ration", "마셔", 20, None), ("water", "먹어", 20, None),
            ("bandage", "먹어", 20, None), ("water", "마셔", 60, None),
            ("field_ration", "먹어", 20, 123),
        ):
            profile = rules.new_profile()
            profile["inventory"][identity] = 1
            profile.update(hp=hp, combat_target=combat)
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.eat_or_drink(profile, identity, action)
            self.assertEqual(profile, before)

    def test_empty_slots_stats_unequip_errors_and_migration_preserve_data(self):
        profile = rules.new_profile()
        before = rules.stats(profile)
        rules.unequip(profile, "machete", "weapon")
        rules.unequip(profile, "vest", "armor")
        after = rules.stats(profile)
        self.assertEqual((before["attack"] - after["attack"], before["defense"] - after["defense"]), (2, 1))
        for identity, slot in (("machete", "weapon"), ("machete", "armor"), ("vest", "weapon")):
            snapshot = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.unequip(profile, identity, slot)
            self.assertEqual(profile, snapshot)
        old = deepcopy(profile)
        old.update(version=4, xp=333, credits=88)
        old.pop("storage")
        old.pop("mental")
        old.pop("recovery_effects")
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated, {**old, "version": rules.PROFILE_VERSION, "storage": {},
                                    "mental": rules.stats(old)["max_mental"], "recovery_effects": []})
        migrated["storage"]["bandage"] = 2
        self.assertEqual(rules.migrate_profile(migrated), migrated)


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
        rules.unequip(upgraded, "machete", "weapon")
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
            rules.buy(profile, "weapon", "carbine")
        self.assertEqual(profile, before)

    def test_salvage_settlement_funds_a_credit_gear_purchase(self):
        profile = rules.new_profile()
        rules.add_item(profile, "scrap", 6)
        self.assertEqual(rules.settle_salvage(profile, 6), 6 * SALVAGE_CREDIT_RATE)
        rules.buy(profile, "weapon", "blade")
        self.assertEqual(profile["inventory"]["blade"], 1)
        self.assertNotIn("scrap", profile["inventory"])

    def test_equipment_catalog_integrity_and_acquisition(self):
        self.assertEqual(len({item["name"] for item in ITEMS.values()}), len(ITEMS))
        for identity, data in ITEMS.items():
            self.assertEqual(find_id(ITEMS, identity), identity)
            self.assertEqual(find_id(ITEMS, data["name"]), identity)
            self.assertIn(data["slot"], {"weapon", "armor", "consumable", "material", "trophy", "tool", "magazine", "ammo"})
            if data["slot"] in EQUIPMENT_ACTIONS:
                self.assertTrue(
                    all(isinstance(data[k], int) and data[k] >= 0 for k in ("attack", "defense"))
                )
                sources = {item for catalog in SHOP_CATALOGS.values() for item in catalog} | {e["drop"] for e in ENEMIES.values()}
                sources |= set(rules.new_profile()["inventory"])
                self.assertIn(identity, sources)
        for catalog in SHOP_CATALOGS.values():
            for identity in catalog:
                price = ITEMS[identity]["value"]
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
                rules.unequip(profile, profile["equipment"][data["slot"]], data["slot"])
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
            slot = ITEMS[identity]["slot"]
            rules.unequip(profile, profile["equipment"][slot], slot)
            rules.equip(profile, identity, slot)
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

    def test_every_credit_purchase_exact_cost_and_lossless_failure(self):
        for shop_id, catalog in SHOP_CATALOGS.items():
            for identity in catalog:
                price = ITEMS[identity]["value"]
                with self.subTest(item=identity):
                    profile = rules.new_profile()
                    profile["credits"] = price - 1
                    profile["inventory"]["scrap"] = price
                    before = deepcopy(profile)
                    with self.assertRaises(rules.RuleError):
                        rules.buy(profile, shop_id, identity)
                    self.assertEqual(profile, before)
                    profile["credits"] = price
                    expected = deepcopy(profile)
                    expected["credits"] = 0
                    expected["inventory"][identity] = expected["inventory"].get(identity, 0) + 1
                    rules.buy(profile, shop_id, identity)
                    self.assertEqual(profile, expected)

    def test_heal_is_capped_and_consumes_one_bandage(self):
        profile = rules.new_profile()
        profile["hp"] -= 4
        self.assertEqual(rules.use_bandage(profile), 4)
        self.assertEqual(profile["hp"], 60)
        self.assertEqual(profile["inventory"]["bandage"], 2)
        with self.assertRaises(rules.RuleError):
            rules.use_bandage(profile)
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

    def test_passive_defense_reduces_boss_charge(self):
        plain, trained = rules.new_profile(), rules.new_profile()
        trained['skills']['defense'] = 20
        a = rules.enemy_attack(plain, 'alpha', 3, 100, Random(2))
        b = rules.enemy_attack(trained, 'alpha', 3, 100, Random(2))
        self.assertTrue(a['charged'])
        self.assertLess(b['damage'], a['damage'])

    def test_combat_heal_replaces_attack(self):
        profile = rules.new_profile()
        profile.update(hp=30, combat_target=1)
        rules.queue_action(profile, "bandage", now=100)
        damage, _ = rules.player_attack(profile, "scavenger", 100, 2.5, Random(1))
        self.assertEqual(damage, 0)
        self.assertEqual(profile["inventory"]["bandage"], 2)
        self.assertEqual(profile["hp"], 50)

    def test_defeat_is_structured_and_preserves_growth(self):
        profile = rules.new_profile()
        profile.update(hp=1, credits=3, xp=20)
        outcome = rules.enemy_attack(profile, "alpha", 3, 100, Random(4))
        self.assertTrue(outcome["defeated"])
        self.assertEqual((profile["credits"], profile["xp"]), (3, 20))
        self.assertEqual(rules.apply_defeat(profile), 3)
        self.assertEqual((profile["credits"], profile["xp"], profile["hp"]), (0, 20, rules.DEFEAT_RECOVERY_HP))

    def test_multiple_level_gains_cap_at_curriculum_completion(self):
        profile = rules.new_profile()
        self.assertEqual(rules.gain_xp(profile, rules.xp_threshold(133) + 10000), 132)
        self.assertEqual(rules.level_of(profile), 133)
        self.assertEqual(profile['hp'], rules.stats(profile)['max_hp'])

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

    def test_direction_graph_keeps_upper_floors_roof_and_elevator_separate(self):
        visited, pending = set(), ["dock"]
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            visited.add(key)
            for target in ROOMS[key]["exits"].values():
                self.assertIn(target, ROOMS)
                pending.append(target)
        prepared = {zone for zone in ROOMS if zone.startswith(("support_2f_", "support_3f_"))}
        prepared.update({"infirmary", "training_room", "armor_shop", "weapon_shop", "support_elevator", "tactics_room", "training_office", "shooting_range"})
        prepared.update(ROOF_ROOMS)
        self.assertEqual(len(prepared), 27)
        self.assertEqual(visited, set(ROOMS) - prepared)

    def test_prepared_solo_player_can_beat_boss_across_rng_seeds(self):
        for seed in range(20):
            profile = rules.new_profile()
            rules.gain_xp(profile, rules.xp_threshold(4))
            # 새 방어 곡선에서도 이미 획득한 성장 포인트로 솔로 준비를 검증한다.
            while rules.point_pools(profile)["attribute_points"]:
                rules.allocate_attribute(profile, "constitution", safe=True)
            rules.treat(profile, safe=True)
            for item in ("carbine", "armor"):
                rules.add_item(profile, item)
                slot = ITEMS[item]["slot"]
                old = profile["equipment"].get(slot)
                if old:
                    rules.unequip(profile, old, slot)
                rules.equip(profile, item)
            profile["combat_target"] = 1
            suppressions = {}
            rng, hp = Random(seed), ENEMIES["alpha"]["hp"]
            defeated = False
            for turn in range(1, 51):
                now = turn * 2.5
                if turn % 3 == 0 and profile["mental"] >= 6 and now >= profile["skill_ready_at"].get("suppress", 0):
                    rules.queue_action(profile, "suppress", now)
                elif profile["hp"] < 45 and profile["inventory"].get("bandage"):
                    rules.queue_action(profile, "bandage", now)
                elif now >= profile["skill_ready_at"].get("shooting", 0) and profile["mental"] >= 6:
                    rules.queue_action(profile, "shooting", now)
                damage, outcome = rules.player_attack(profile, "alpha", now, 2.5, rng)
                from world import progression as pg
                if "suppression" in outcome:
                    suppressions, _ = pg.apply_suppression(suppressions, "solo", outcome["suppression"]["rank"], True)
                reduction = pg.combined_suppression(suppressions, boss=True)
                suppressions = pg.consume_suppressions(suppressions)
                hp -= damage
                if hp <= 0:
                    break
                defeated = rules.enemy_attack(profile, "alpha", turn, now, rng, reduction)["defeated"]
                if defeated:
                    break
            self.assertFalse(defeated, f"Solo boss failed with seed {seed}")
            self.assertLessEqual(hp, 0)

    def test_prepared_solo_player_can_beat_jungle_boss(self):
        for seed in range(10):
            profile = rules.new_profile()
            rules.gain_xp(profile, rules.xp_threshold(5))
            while rules.point_pools(profile)["attribute_points"]:
                rules.allocate_attribute(profile, "constitution", safe=True)
            rules.treat(profile, safe=True)
            profile["inventory"]["bandage"] = 8
            for item in ("carbine", "heavy_suit"):
                rules.add_item(profile, item)
                slot = ITEMS[item]["slot"]
                old = profile["equipment"].get(slot)
                if old:
                    rules.unequip(profile, old, slot)
                rules.equip(profile, item)
            profile["combat_target"] = 1
            suppressions = {}
            rng, hp = Random(seed), ENEMIES["jungle_apex"]["hp"]
            for turn in range(1, 51):
                now = turn * 2.5
                if rules.boss_telegraph("jungle_apex", turn - 1) and profile["mental"] >= 6 and now >= profile["skill_ready_at"].get("suppress", 0):
                    rules.queue_action(profile, "suppress", now)
                elif profile["hp"] < 55 and profile["inventory"].get("bandage"):
                    rules.queue_action(profile, "bandage", now)
                elif now >= profile["skill_ready_at"].get("shooting", 0) and profile["mental"] >= 6:
                    rules.queue_action(profile, "shooting", now)
                damage, outcome = rules.player_attack(profile, "jungle_apex", now, 2.5, rng)
                from world import progression as pg
                if "suppression" in outcome:
                    suppressions, _ = pg.apply_suppression(suppressions, "solo", outcome["suppression"]["rank"], True)
                reduction = pg.combined_suppression(suppressions, boss=True)
                suppressions = pg.consume_suppressions(suppressions)
                hp -= damage
                if hp <= 0:
                    break
                if rules.enemy_attack(profile, "jungle_apex", turn, now, rng, reduction)["defeated"]:
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
        self.assertEqual(migrated["version"], rules.PROFILE_VERSION)
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
            old.pop("mental")
            old.pop("recovery_effects")
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
                if key not in ("version", "record_read", "cache_claimed", "guard_until", "queued_action", "skill_ready_at"):
                    self.assertEqual(migrated[key], value)
            self.assertTrue(migrated["quests"]["radio_tower"]["record_read"])
            self.assertTrue(migrated["discoveries"]["supply_cache"])
            self.assertEqual(migrated["version"], rules.PROFILE_VERSION)
            self.assertEqual(migrated["mental"], rules.stats(migrated)["max_mental"])
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
        for _ in range(2):
            rules.learn_skill(profile, 'heavy', safe=True)
        self.assertEqual((profile['skills']['heavy'], profile['credits']), (3, 100))
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.learn_skill(profile, 'defense', safe=True)
        self.assertEqual(profile, before)

    def test_retraining_preserves_history_and_separate_pools(self):
        profile = rules.new_profile()
        profile.update(
            xp=140,
            credits=1000,
            hp=47,
            heavy_ready_at=100,
            next_attack_at=90,
            queued_action="suppress",
            visited=["dock", "grass"],
        )
        profile["quests"]["radio_tower"]["started"] = True
        profile["skill_ready_at"]["breathing"] = 123
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

    def test_combat_and_bandages_do_not_train_skills_implicitly(self):
        profile = rules.new_profile()
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.use_bandage(profile)
        self.assertEqual(profile, before)
        profile['hp'] = 30
        rules.use_bandage(profile)
        profile['combat_target'] = 1
        rules.enemy_attack(profile, 'alpha', 1, 105, Random(1))
        self.assertNotIn('proficiencies', profile)
        self.assertEqual(profile['skills'], before['skills'])

    def test_each_attribute_and_skill_rank_changes_effect(self):
        profile = rules.new_profile()
        profile['xp'] = rules.xp_threshold(20)
        base = rules.stats(profile)
        rules.allocate_attribute(profile, 'strength', 2, safe=True)
        rules.allocate_attribute(profile, 'agility', 3, safe=True)
        rules.allocate_attribute(profile, 'wisdom', 2, safe=True)
        self.assertEqual(rules.stats(profile)['attack'], base['attack'] + 1)
        self.assertEqual(rules.stats(profile)['defense'], base['defense'] + 1)
        profile['hp'] = 1
        healing = rules.support_action(profile, 'heal', 100)['amount']
        rules.learn_skill(profile, 'heal', safe=True)
        profile['hp'] = 1
        self.assertGreater(rules.support_action(profile, 'heal', 110)['amount'], healing)
        normal, improved = deepcopy(profile), deepcopy(profile)
        for _ in range(10):
            rules.learn_skill(improved, 'heavy', safe=True)
        for data in (normal, improved):
            data.update(combat_target=1, queued_action='heavy')
        self.assertGreater(rules.player_attack(improved, 'alpha', 120, 2.5, Random(1))[0], rules.player_attack(normal, 'alpha', 120, 2.5, Random(1))[0])

    def test_invalid_allocations_and_rank_requirement_are_lossless(self):
        profile = rules.new_profile()
        for amount in (0, -1, True, 1.5, 999):
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.allocate_attribute(profile, "strength", amount, safe=True)
            self.assertEqual(profile, before)
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.learn_skill(profile, "heavy", safe=True)
        self.assertEqual(profile, before)
