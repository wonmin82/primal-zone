"""단일 화폐·정산 입력과 실패 시 상태 보존."""

from copy import deepcopy
from inspect import signature
from unittest import TestCase
from unittest.mock import patch

from world import content, rules
from world.content import ITEMS, SALVAGE_CREDIT_RATE
from world.content.integrity import errors
from world.settlement import parse_salvage
from world.test_headquarters import content_targets


class SettlementRulesTests(TestCase):
    def test_conversion_contract_and_credit_catalog_are_preserved(self):
        self.assertEqual(SALVAGE_CREDIT_RATE, 10)
        self.assertFalse(hasattr(content, "EXCHANGE"))
        self.assertFalse(hasattr(content.items, "EXCHANGE"))
        self.assertEqual(tuple(signature(rules.buy).parameters), ("profile", "shop_id", "item_id"))
        self.assertEqual(ITEMS["scrap"]["slot"], "material")
        self.assertTrue(ITEMS["scrap"]["transferable"])
        self.assertFalse(hasattr(content, "SHOP"))
        self.assertEqual(rules.purchase_price("bandage"), 10)
        self.assertEqual(rules.purchase_price("ammo_556"), 60)

    def test_one_and_all_quantities_preserve_every_other_field(self):
        for quantity in (1, 5):
            profile = rules.new_profile()
            profile["inventory"]["scrap"] = 5
            profile["storage"]["scrap"] = 9
            before = deepcopy(profile)
            earned = rules.settle_salvage(profile, quantity)
            self.assertEqual(earned, quantity * SALVAGE_CREDIT_RATE)
            before["credits"] += earned
            if quantity == 5:
                del before["inventory"]["scrap"]
            else:
                before["inventory"]["scrap"] -= quantity
            self.assertEqual(profile, before)

    def test_invalid_insufficient_and_combat_requests_do_not_mutate(self):
        for quantity, target in ((0, None), (-1, None), (3, None), (True, None), (1.5, None),
                                 ("1", None), (None, None), (1, 999)):
            profile = rules.new_profile()
            profile.update(combat_target=target)
            profile["inventory"]["scrap"] = 2
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.settle_salvage(profile, quantity)
            self.assertEqual(profile, before)

    def test_settlement_parser_keeps_numeric_quantities_local(self):
        for value, expected in (("회수부품", 1), ("회수 부품", 1), ("회수부품 3개", 3),
                                ("회수부품 모두", None), ("회수 부품 모두", None)):
            self.assertEqual(parse_salvage(value), expected)
        for value in ("회수부품 0개", "회수부품 -1개", "회수부품 abc개", "회수부품 3",
                      "회수부품 모두 1개", "회수부품 3개 모두", "강화방호조끼", "절단마체테", ""):
            with self.subTest(value=value), self.assertRaises(rules.RuleError):
                parse_salvage(value)
        from world.targets import stack_selector

        with self.assertRaises(rules.RuleError):
            stack_selector("회수부품 3개", ITEMS, "넣어")

    def test_resource_transfer_does_not_convert_to_money(self):
        profile = rules.new_profile()
        profile["inventory"]["scrap"] = 3
        recipient = {}
        rules.move_item(profile["inventory"], recipient, "scrap", all_items=True)
        self.assertEqual(recipient, {"scrap": 3})
        self.assertNotIn("scrap", profile["inventory"])
        self.assertEqual(profile["credits"], rules.new_profile()["credits"])

    def test_rate_and_service_definitions_have_integrity(self):
        targets = content_targets()
        self.assertEqual(errors(targets), [])
        for rate in (0, -1, True, 1.5, "10", None):
            with patch("world.content.integrity.SALVAGE_CREDIT_RATE", rate):
                self.assertTrue(any("정산율" in issue for issue in errors(targets)))
        for change in ({"room": "dock"}, {"actions": ["대화"]}):
            with patch.dict(targets["salvage_officer"], change):
                self.assertTrue(any("salvage_officer" in issue for issue in errors(targets)))
