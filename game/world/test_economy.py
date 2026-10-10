"""금액·가격·할당의 보존 계약과 legacy 전리품 읽기 호환."""

from copy import deepcopy
from unittest import TestCase

from world import presentation, rules
from world.content import ENEMIES, ITEMS, SHOP_CATALOGS
from world.currency import currency_names, currency_request, format_currency, spend_currency
from world.loot_assets import currency_payouts, normalize_entry
from world.targets import parse_loot, parse_selector


class EconomyRulesTests(TestCase):
    def test_wallet_display_with_and_without_inventory(self):
        self.assertEqual(format_currency(1), "1칩")
        self.assertEqual(format_currency(127), "127칩")
        profile = rules.new_profile()
        profile["credits"] = 127
        self.assertIn("[가진거] 127칩", presentation.inventory(profile))
        profile["inventory"] = {}
        self.assertIn("[가진거] 127칩", presentation.inventory(profile))
        self.assertIn("비어 있다.", presentation.inventory(profile))
        self.assertNotIn("chip", ITEMS)
        self.assertEqual(rules.PROFILE_VERSION, 13)

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

    def test_purchase_quantity_package_and_resale_metadata(self):
        for catalog in SHOP_CATALOGS.values():
            self.assertIsInstance(catalog["purchase_catalog"], tuple)
            for item in catalog["purchase_catalog"]:
                self.assertEqual(rules.purchase_price(item), ITEMS[item].get("purchase_unit_value", ITEMS[item]["value"]) * ITEMS[item].get("purchase_quantity", 1))
                self.assertEqual(rules.resale_price(item), ITEMS[item].get("resale_unit_value", ITEMS[item]["value"] // 2))
        for item in ("scrap", "jungle_cell", "ridge_predator_mark"):
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
        profile["inventory"]["cutting_machete"] = 2
        profile["equipment"]["weapon"] = "cutting_machete"
        self.assertEqual(rules.sell(profile, "weapon", "cutting_machete", all_items=True), (1, 27))
        self.assertEqual((profile["credits"], profile["inventory"]["cutting_machete"]), (47, 1))
        before = deepcopy(profile)
        for shop, item in (("weapon", "cutting_machete"), ("supply", "cutting_machete"), ("weapon", "scrap")):
            with self.assertRaises(rules.RuleError):
                rules.sell(profile, shop, item)
            self.assertEqual(profile, before)

    def test_old_currency_normalization_separates_rights_without_writes(self):
        old = {"kind": "currency", "id": "credits", "quantity": 21,
               "shares": {"1": 11, "2": 10}, "protection_until": 220}
        original = deepcopy(old)
        canonical = normalize_entry(old)
        self.assertEqual(canonical["eligible_players"], [1, 2])
        self.assertEqual(canonical["remaining_shares"], {1: 11, 2: 10})
        self.assertNotIn("shares", canonical)
        self.assertEqual(old, original)
        self.assertEqual(normalize_entry(canonical), canonical)
        canonical["remaining_shares"] = {2: 1}
        canonical["quantity"] = 1
        self.assertEqual(normalize_entry(canonical)["eligible_players"], [1, 2])

    def test_sale_discards_only_last_owned_device_and_rebuy_has_no_power(self):
        from world import lighting

        profile = rules.new_profile()
        profile["credits"] = 100
        profile["inventory"].update(flashlight=2, battery=1)
        lighting.insert_power(profile, "flashlight", "battery", 100)
        device = deepcopy(profile["light_sources"]["flashlight"])
        rules.sell(profile, "supply", "flashlight")
        self.assertEqual(profile["inventory"]["flashlight"], 1)
        self.assertEqual(profile["light_sources"]["flashlight"], device)
        rules.sell(profile, "supply", "flashlight")
        self.assertNotIn("flashlight", profile["inventory"])
        self.assertNotIn("flashlight", profile["light_sources"])
        rules.buy(profile, "supply", "flashlight")
        self.assertIsNone(lighting.projected(profile, "flashlight", 101)["power_source"])
        self.assertEqual(lighting.projected(profile, "flashlight", 101)["charge_seconds"], 0)

    def test_currency_payout_uses_only_remaining_obligations_until_expiry(self):
        entry = {"kind": "currency", "id": "credits", "quantity": 1,
                 "eligible_players": [1, 2, 3, 4], "remaining_shares": {4: 1}, "protection_until": 220}
        before = deepcopy(entry)
        self.assertEqual(currency_payouts(entry, 1, 1, 219), {4: 1})
        self.assertEqual(currency_payouts(entry, 1, 5, 220), {5: 1})
        self.assertEqual(entry, before)
