"""구매/매입 분리와 공통 수량 parser의 순수 계약."""

from copy import deepcopy
from unittest import TestCase

from world import rules
from world.content import ITEMS, SHOP_CATALOGS
from world.content.shops import accepts
from world.stack_quantity import parse_stack_quantity


class ShopV2RulesTests(TestCase):
    def test_category_resale_is_independent_of_purchase_and_progression(self):
        for shop, identity in (("weapon", "jungle_blade"), ("armor", "tactical_vest")):
            self.assertNotIn(identity, SHOP_CATALOGS[shop]["purchase_catalog"])
            self.assertTrue(accepts(shop, ITEMS[identity]))
            profile = rules.new_profile()
            profile["inventory"][identity] = 1
            self.assertGreater(rules.sell(profile, shop, identity)[1], 0)
            before = deepcopy(profile)
            with self.assertRaises(rules.RuleError):
                rules.buy(profile, shop, identity)
            self.assertEqual(profile, before)

    def test_quantity_suffix_preserves_numeric_names_and_instance_selectors(self):
        for value, result in (("붕대", ("붕대", 1)), ("붕대 3개", ("붕대", 3)),
                              ("붕대 모두", ("붕대", None)), ("강철마체테 2", ("강철마체테 2", 1)),
                              ("9mm 권총탄 12개", ("9mm 권총탄", 12)),
                              ("5.56mm 표준탄창", ("5.56mm 표준탄창", 1))):
            self.assertEqual(parse_stack_quantity(value), result)
        for value in ("붕대 0개", "붕대 -1개", "붕대 abc개", "붕대 3개 모두", "붕대 모두 3개", ""):
            with self.subTest(value=value), self.assertRaises(rules.RuleError):
                parse_stack_quantity(value)
