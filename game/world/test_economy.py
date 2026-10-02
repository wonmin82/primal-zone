"""금액·가격·할당의 보존 계약과 legacy 전리품 읽기 호환."""

from copy import deepcopy
from unittest import TestCase

from world import presentation, rules
from world.content import ENEMIES, ITEMS, SHOP_CATALOGS
from world.currency import currency_names, currency_request, format_currency, spend_currency
from world.loot_assets import normalize_entry
from world.targets import parse_loot, parse_selector


class EconomyRulesTests(TestCase):
    def test_wallet_display_with_and_without_inventory(self):
        self.assertEqual(format_currency(1), "1칩")
        self.assertEqual(format_currency(127), "127칩")
        profile = rules.new_profile()
        profile["credits"] = 127
        self.assertIn("[소지품] 127칩", presentation.inventory(profile))
        profile["inventory"] = {}
        self.assertIn("[소지품] 127칩", presentation.inventory(profile))
        self.assertIn("비어 있다.", presentation.inventory(profile))
        self.assertNotIn("chip", ITEMS)
        self.assertEqual(rules.PROFILE_VERSION, 8)

    def test_amount_and_common_selector_are_distinct(self):
        for raw, amount, index in (("칩", 1, None), ("20칩", 20, None),
                                   ("칩 2", 1, 2), ("칩 모두", None, None)):
            result = currency_request(parse_selector(raw, currency_names()))
            self.assertEqual((result[0], result[1].index), (amount, index))
        for raw in ("0칩", "-1칩", "1.5칩", "20칩 2", "20칩 모두"):
            with self.subTest(raw=raw), self.assertRaises(rules.RuleError):
                currency_request(parse_selector(raw, currency_names()))
        with self.assertRaises(rules.RuleError):
            parse_loot("모든 시체에서 20칩", currency_names())
        self.assertIsNone(currency_request(parse_selector("붕대")))

    def test_spend_validates_before_mutating(self):
        for amount in (0, -1, 1.5, True, 21):
            profile = rules.new_profile()
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                spend_currency(profile, amount)
            self.assertEqual(profile, before)
        profile = rules.new_profile()
        self.assertEqual(spend_currency(profile), 20)
        self.assertEqual(profile["credits"], 0)

    def test_item_value_is_the_only_price_source(self):
        for catalog in SHOP_CATALOGS.values():
            self.assertIsInstance(catalog, tuple)
            for item in catalog:
                self.assertEqual(rules.purchase_price(item), ITEMS[item]["value"])
                self.assertEqual(rules.resale_price(item), max(1, ITEMS[item]["value"] // 2))
        for item in ("scrap", "jungle_cell", "machete"):
            with self.assertRaises(rules.RuleError):
                rules.purchase_price(item)

    def test_allocation_keeps_group_contribution_and_equal_party_shares(self):
        groups = {"party:10": {1: 30, 2: 10}, "player:3": {3: 10}}
        allocation = rules.reward_allocation(58, groups)
        self.assertEqual(allocation, {1: 23, 2: 23, 3: 12})
        self.assertEqual(sum(allocation.values()), 58)
        shares = {1: 11, 2: 10}
        first = rules.weighted_split(10, shares)
        self.assertEqual(first, {1: 5, 2: 5})
        remaining = {key: value - first[key] for key, value in shares.items()}
        self.assertEqual(remaining, {1: 6, 2: 5})
        self.assertEqual(rules.weighted_split(11, remaining), remaining)
        self.assertEqual(sorted(e["currency"] for e in ENEMIES.values()), [8, 14, 18, 20, 24, 29, 50, 58])

    def test_legacy_entry_is_normalized_without_touching_original(self):
        entry = {"item": "bandage", "quantity": 2, "protection_until": 120}
        before = deepcopy(entry)
        normalized = normalize_entry(entry)
        self.assertEqual((normalized["kind"], normalized["id"]), ("item", "bandage"))
        self.assertEqual(entry, before)
        self.assertEqual(normalize_entry(normalized), normalized)

    def test_sale_excludes_equipped_copy_and_failure_keeps_profile(self):
        profile = rules.new_profile()
        profile["inventory"]["blade"] = 2
        profile["equipment"]["weapon"] = "blade"
        self.assertEqual(rules.sell(profile, "weapon", "blade", all_items=True), (1, 30))
        self.assertEqual((profile["credits"], profile["inventory"]["blade"]), (50, 1))
        before = deepcopy(profile)
        for shop, item in (("weapon", "blade"), ("supply", "blade"), ("weapon", "scrap")):
            with self.assertRaises(rules.RuleError):
                rules.sell(profile, shop, item)
            self.assertEqual(profile, before)
