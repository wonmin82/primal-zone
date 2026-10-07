"""최종 정의·획득·경제 불변조건과 deterministic V1 sanity."""

from unittest import TestCase
from unittest.mock import Mock

from world import balance_sanity, final_content, rules
from world.content import ENEMIES, ITEMS, SHOP_CATALOGS
from world.content.item_mapping import BOSS_REWARDS
from world.content.loot_v1 import LOOT
from world.content.shops import accepts
from world.firearms import magazine_resale
from world.loot_rules import boss_hp, roll_loot


class FinalContentTests(TestCase):
    def test_all_definitions_integrity_and_acquisition_paths(self):
        self.assertEqual(final_content.errors(), [])
        matrix = final_content.acquisition_matrix()
        for identity, definition in ITEMS.items():
            if "tier" in definition:
                self.assertTrue(matrix[identity], identity)
        for identity in ("regeneration_module", "mental_stability_module", "tactical_computing_module", "expedition_tag", *BOSS_REWARDS.values()):
            self.assertFalse(any(identity in data["purchase_catalog"] for data in SHOP_CATALOGS.values()))
        self.assertTrue(accepts("armor", ITEMS["regeneration_module"]))
        self.assertTrue(accepts("weapon", ITEMS["heavy_rifle"]))
        self.assertFalse(accepts("weapon", ITEMS["tracking_goggles"]))

    def test_final_prices_ammo_bundle_and_all_firearm_arbitrage(self):
        for identity, price in (("water", 3), ("field_ration", 5), ("bandage", 10), ("battery", 8), ("flashlight", 35)):
            self.assertEqual(rules.purchase_price(identity), price)
            self.assertEqual(rules.resale_price(identity), price // 2)
        for identity, purchase, resale, quantity in (("ammo_9", 24, 1, 12), ("ammo_556", 40, 1, 20), ("ammo_762", 32, 2, 8)):
            self.assertEqual(rules.purchase_price(identity), purchase)
            self.assertEqual(rules.resale_price(identity), resale)
            self.assertEqual(ITEMS[identity]["purchase_quantity"], quantity)
        for identity, definition in ITEMS.items():
            if definition.get("firearm_family"):
                cost = final_content.package_costs(identity)
                self.assertGreater(cost["package"], cost["body_resale"] + cost["magazine_resale"] + cost["ammo_resale"])
                self.assertGreaterEqual(cost["package"] - cost["body_resale"] - cost["magazine_resale"], cost["ammo_buy"])
        self.assertEqual(magazine_resale(9, ITEMS["mag_556_standard"]["resale_unit_value"], 1), 31)

    def test_exact_enemy_stats_and_boss_scaling(self):
        expected = {"scavenger": (24,5,0,22,8), "hunter": (45,9,2,38,14), "sentinel": (65,11,5,55,20), "alpha": (170,17,6,130,50),
                    "dartclaw": (58,15,2,55,18), "shellback": (105,12,10,70,24), "stalker": (110,18,4,84,29), "jungle_apex": (270,20,8,155,58)}
        for identity, stats in expected.items():
            self.assertEqual(tuple(ENEMIES[identity][key] for key in ("hp", "attack", "defense", "xp", "currency")), stats)
        for count, multiplier in enumerate((1, 1.75, 2.5, 3.25), 1):
            self.assertEqual(boss_hp(170, count), int(170 * multiplier))
        self.assertEqual(rules.xp_threshold(7), 660)

    def test_each_drop_branch_and_partial_firearm_without_two_specials(self):
        for enemy, definition in LOOT.items():
            special = definition.get("special", ())
            cumulative = 0
            for identity, probability in special:
                rng = Mock()
                rng.random.side_effect = [1, cumulative + probability / 2] if "resource" in definition else [cumulative + probability / 2]
                rng.randint.side_effect = lambda low, high: low
                entries = roll_loot(enemy, rng)
                self.assertEqual([entry["id"] for entry in entries], [identity])
                if identity in definition.get("firearms", {}):
                    magazine, low, high = definition["firearms"][identity]
                    self.assertEqual(entries[0]["acquisition"], {"mode": "partial", "magazine_definition": magazine, "rounds": low})
                    self.assertLess(high, ITEMS[magazine]["magazine"]["capacity"])
                cumulative += probability
            if "resource" in definition:
                cumulative = 0
                for identity, weight in definition["resource"][1]:
                    rng = Mock()
                    rng.random.side_effect = [0, cumulative + weight / 2, 1]
                    rng.randint.side_effect = lambda low, high: high
                    self.assertEqual([entry["id"] for entry in roll_loot(enemy, rng)], [identity])
                    cumulative += weight
            if "trophy" in definition:
                self.assertEqual(roll_loot(enemy), [{"id": definition["trophy"], "quantity": 1}])

    def test_balance_sanity_records_without_tuning(self):
        report = balance_sanity.report()
        self.assertTrue(10 <= report["ridge_basic"] <= 14)
        self.assertTrue(8 <= report["ridge_skill"] <= 11)
        self.assertLess(report["jungle_skill"], report["jungle_basic"])
        self.assertGreater(report["hands"]["2H"]["attack"], report["hands"]["1H+shield"]["attack"])
        self.assertGreater(report["hands"]["1H+shield"]["defense"], report["hands"]["2H"]["defense"])
        self.assertGreater(report["penetration"]["10"]["0.3"], report["penetration"]["10"]["0"])
        values = report["loot_ev"]
        self.assertLess(values["scavenger"], values["hunter"])
        self.assertLess(values["hunter"], values["sentinel"])
        self.assertLess(values["dartclaw"], values["shellback"])
        self.assertLess(values["shellback"], values["stalker"])


    def test_definition_reload_hp_preserves_full_idle_and_damage(self):
        from world.loot_rules import updated_enemy_hp

        for old_hp, old_max, new_max, state, combat, expected in (
            (190, 190, 270, "alive", False, 270), (150, 190, 270, "alive", False, 150),
            (270, 270, 190, "alive", False, 190), (150, 270, 190, "alive", False, 150),
            (190, 190, 270, "alive", True, 190), (150, 190, 270, "alive", True, 150),
            (0, 190, 270, "respawning", False, 0)):
            with self.subTest(old_hp=old_hp, old_max=old_max, new_max=new_max, state=state, combat=combat):
                self.assertEqual(updated_enemy_hp(old_hp, old_max, new_max, state, combat), expected)

    def test_generator_parts_are_submit_only_and_never_economic_goods(self):
        from world.item_entities.policy import TREE_OPERATION_SCOPES, can_item_operation
        from world.settlement import parse_salvage

        self.assertEqual(ITEMS["generator_repair_part"]["max_stack"], 3)
        for operation in (*TREE_OPERATION_SCOPES, "unknown"):
            self.assertEqual(can_item_operation("generator_repair_part", operation), operation == "submit")
        for name in ("정비용 회수부품", "정비부품"):
            with self.assertRaises(rules.RuleError):
                parse_salvage(name)
        self.assertEqual(final_content.acquisition_matrix()["generator_repair_part"], ["supply_cache", "migration:generator_unfixed"])
        self.assertFalse(can_item_operation("scrap", "submit"))
