"""새 아이템 정의와 기존 이동 정책의 순수 호환 경계."""

import unittest

from world.content import ITEMS
from world.item_entities.policy import can_item_operation, definition_errors


class ItemDefinitionTests(unittest.TestCase):
    def test_existing_definitions_supply_valid_metadata_and_legacy_transfer_policy(self):
        for identity, definition in ITEMS.items():
            with self.subTest(identity=identity):
                self.assertEqual(definition_errors(identity, definition), [])
                if identity in ("ridge_predator_mark", "predator_scale_charm"):
                    self.assertEqual(definition["max_stack"], 1)
                    self.assertTrue(definition["unique_per_owner"])
                    self.assertTrue(can_item_operation(identity, "store"))
                    self.assertFalse(can_item_operation(identity, "burn"))
                elif definition["item_type"] == "credential":
                    self.assertEqual(definition["max_stack"], 1)
                    self.assertFalse(definition["stackable"])
                    self.assertTrue(definition["unique_per_owner"])
                    self.assertTrue(can_item_operation(identity, "burn"))
                else:
                    self.assertIsNone(definition["max_stack"])
                for operation in ("drop", "give", "store", "sell"):
                    self.assertEqual(
                        can_item_operation(identity, operation), definition["operation_policy"][operation]
                    )
        self.assertFalse(ITEMS["flashlight"]["stackable"])
        self.assertFalse(ITEMS["explorer_machete"]["stackable"])
        self.assertTrue(ITEMS["bandage"]["stackable"])

    def test_malformed_metadata_and_unknown_operations_fail_closed(self):
        base = ITEMS["bandage"]
        for overrides in (
            {"stackable": 1},
            {"max_stack": 0},
            {"max_stack": True},
            {"unique_per_owner": True},
            {"item_type": ""},
            {"operation_policy": {"give": "yes"}},
        ):
            with self.subTest(overrides=overrides):
                self.assertTrue(definition_errors("test", {**base, **overrides}))
        self.assertFalse(can_item_operation("missing", "give"))
        self.assertFalse(can_item_operation("bandage", "craft"))
