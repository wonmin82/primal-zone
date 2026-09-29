"""Catalog 계약과 잘못된 구매/정적 정의의 실패 경계."""

from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from world import content, rules
from world.content import SHOP_CATALOGS
from world.content.integrity import errors, shop_errors
from world.test_headquarters import content_targets


class ShopRulesTests(TestCase):
    def test_catalogs_preserve_all_fourteen_prices_without_legacy_table(self):
        self.assertEqual(SHOP_CATALOGS, {
            "supply": {"flashlight": 30, "battery": 6, "bandage": 8, "field_ration": 4, "water": 3},
            "weapon": {"spear": 35, "blade": 60, "jungle_blade": 95, "carbine": 130, "heavy_carbine": 240},
            "armor": {"leather_suit": 35, "tactical_vest": 85, "armor": 65, "heavy_suit": 190},
        })
        self.assertFalse(hasattr(content, "SHOP"))
        self.assertFalse(hasattr(content.items, "SHOP"))
        self.assertEqual(errors(content_targets()), [])

    def test_wrong_catalog_item_and_combat_purchase_preserve_profile(self):
        for shop_id, item, combat in (("missing", "bandage", None), ("supply", "blade", None),
                                      ("weapon", "bandage", None), ("armor", "spear", None),
                                      ("weapon", "missing", None), ("supply", "bandage", 999)):
            with self.subTest(shop_id=shop_id, item=item, combat=combat):
                profile = rules.new_profile()
                profile.update(credits=1000, combat_target=combat)
                before = deepcopy(profile)
                with self.assertRaises(rules.RuleError):
                    rules.buy(profile, shop_id, item)
                self.assertEqual(profile, before)

    def test_catalog_integrity_rejects_bad_prices_items_duplicates_and_empty_catalog(self):
        for price in (0, -1, True, 8.5, "8"):
            with patch.dict(SHOP_CATALOGS["supply"], bandage=price):
                self.assertTrue(any("가격" in issue for issue in shop_errors()))
        with patch.dict(SHOP_CATALOGS["supply"], missing=1):
            self.assertTrue(any("아이템 정의" in issue for issue in shop_errors()))
        with patch.dict(SHOP_CATALOGS["weapon"], bandage=8):
            self.assertTrue(any("중복" in issue for issue in shop_errors()))
        with patch.dict(SHOP_CATALOGS["supply"], {}, clear=True):
            self.assertTrue(any("비었습니다" in issue for issue in shop_errors()))
        for field, value in (("room", "dock"), ("shop_id", "missing"), ("actions", ["구매"])):
            targets = content_targets()
            targets["supply_shopkeeper"][field] = value
            self.assertTrue(any("supply_shopkeeper" in issue for issue in errors(targets)))
