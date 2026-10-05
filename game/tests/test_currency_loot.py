"""지급 요청 자격과 잔여 지분의 분리, 다중 recipient 원자성."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from typeclasses.loot import Corpse, take_loot
from world import loot_service, rules
from world.item_entities.models import ItemEntity
from world.loot_entities.models import CurrencyLoot, CurrencyLootShare
from world.multiplayer import object_by_id, world_change
from world.state import loot_controls
from world.targets import parse_loot

from tests.loot_entity_fixture import NativeLootTest


class CurrencyLootTests(NativeLootTest):
    def currency(self, quantity=20, *, shares=None, deadline=300):
        return loot_service.create_currency(self.source, quantity,
                                             shares={self.char1: 10, self.char2: 10} if shares is None else shares,
                                             reserved_player=self.char1, protection_until=deadline)

    def balances(self):
        return [character.profile()["credits"] for character in (self.char1, self.char2)]

    def test_models_eligibility_share_uniqueness_and_protect(self):
        row = self.currency()
        self.assertEqual(CurrencyLootShare.objects.count(), 2)
        self.assertEqual(self.entry(row).as_entry()["eligible_players"], [self.char1.pk, self.char2.pk])
        self.assertNotIn("eligible_players", {field.name for field in row._meta.fields})
        self.assertFalse(ItemEntity.objects.exists())
        with self.assertRaises(ProtectedError):
            row.delete()
        with self.assertRaises(ProtectedError), world_change():
            self.source.delete()
        with self.assertRaises((ValidationError, IntegrityError)), transaction.atomic():
            CurrencyLootShare(currency_loot=row, player=self.char1, remaining_amount=0).save()
        self.assertEqual(loot_service.integrity_errors(self.source), [])

    def test_partial_payout_uses_existing_weighted_split(self):
        row = self.currency()
        received = loot_service.pickup(self.source, self.entry(row), self.char1, 5, now=100)
        row.refresh_from_db()
        self.assertEqual(row.quantity, 15)
        self.assertEqual([amount for _, _, amount in received], [3, 2])
        self.assertEqual(self.balances(), [23, 22])
        self.assertEqual(list(row.shares.values_list("remaining_amount", flat=True)), [7, 8])

    def test_zero_share_original_eligible_can_trigger_remaining_payout(self):
        row = self.currency(shares={self.char1: 0, self.char2: 20})
        selected = self.entry(row)
        self.assertEqual(selected.as_entry()["eligible_players"], [self.char1.pk, self.char2.pk])
        loot_service.pickup(self.source, selected, self.char1, 5, now=100)
        self.assertEqual(self.balances(), [20, 25])
        self.assertEqual(row.shares.get(player=self.char1).remaining_amount, 0)
        loot_service.pickup(self.source, self.entry(row), self.char1, 15, now=100)
        self.assertEqual(self.balances(), [20, 40])
        self.assertFalse(CurrencyLoot.objects.exists())
        self.assertFalse(CurrencyLootShare.objects.exists())

    def test_partial_payout_exhausted_share_still_has_trigger_right(self):
        row = self.currency(3, shares={self.char1: 1, self.char2: 2})
        loot_service.pickup(self.source, self.entry(row), self.char1, 2, now=100)
        self.assertEqual(row.shares.get(player=self.char1).remaining_amount, 0)
        self.assertIn(self.char1.pk, self.entry(row).as_entry()["eligible_players"])
        loot_service.pickup(self.source, self.entry(row), self.char1, 1, now=100)
        self.assertEqual(self.balances(), [21, 22])

    def test_protected_outsider_reject_then_expiry_free_payout(self):
        row = self.currency(20, shares={self.char1: 20}, deadline=110)
        before = self.all_state()
        self.assertFalse(loot_controls(self.char2, 109)[self.source.pk]["loot"][0]["can_take"])
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, self.entry(row), self.char2, 5, now=109)
        self.assertEqual(self.all_state(), before)
        loot_service.pickup(self.source, self.entry(row), self.char2, 5, now=110)
        row.refresh_from_db()
        self.assertEqual(self.balances(), [20, 25])
        self.assertEqual(row.quantity, 15)
        self.assertEqual(row.shares.get(player=self.char1).remaining_amount, 0)
        loot_service.pickup(self.source, self.entry(row), self.char2, 15, now=111)
        self.assertEqual(self.balances(), [20, 40])
        self.assertFalse(CurrencyLoot.objects.exists())

    def test_offline_recipient_receives_persistent_credits(self):
        row = self.currency()
        with patch.object(self.char2.sessions, "count", return_value=0):
            loot_service.pickup(self.source, self.entry(row), self.char1, 20, now=100)
        self.assertEqual(self.balances(), [30, 30])

    def test_missing_second_recipient_rolls_back_first_credit(self):
        row = self.currency()
        selected, before = self.entry(row), self.all_state()
        with patch("world.loot_service.object_by_id",
                   side_effect=lambda identity: None if identity == self.char2.pk else object_by_id(identity)):
            with self.assertRaises(rules.RuleError):
                loot_service.pickup(self.source, selected, self.char1, 20, now=100)
        self.assertEqual(self.all_state(), before)

    def test_second_recipient_save_failure_rolls_back_all_credits(self):
        row = self.currency()
        selected, before = self.entry(row), self.all_state()
        with patch.object(self.char2, "save_profile", side_effect=RuntimeError("recipient")), self.assertRaises(RuntimeError):
            loot_service.pickup(self.source, selected, self.char1, 20, now=100)
        self.assertEqual(self.all_state(), before)

    def test_share_update_and_currency_save_failure_roll_back_all_payouts(self):
        row = self.currency()
        for target in ("world.loot_entities.models.CurrencyLootShare.save", "world.loot_entities.models.CurrencyLoot.save"):
            with self.subTest(target=target):
                before = self.all_state()
                with patch(target, side_effect=RuntimeError("update")), self.assertRaises(RuntimeError):
                    loot_service.pickup(self.source, self.entry(row), self.char1, 5, now=100)
                self.assertEqual(self.all_state(), before)

    def test_currency_decay_preserves_owner_independent_rights_shares_and_quantity(self):
        row = self.currency()
        shares = list(CurrencyLootShare.objects.values())
        rights = (row.quantity, row.reserved_player_id, row.reserved_party_id, row.protection_until)
        self.source.reconcile(now=200)
        row.refresh_from_db()
        self.assertNotEqual(row.owner_object_id, self.source.pk)
        self.assertEqual((row.quantity, row.reserved_player_id, row.reserved_party_id, row.protection_until), rights)
        self.assertEqual(list(CurrencyLootShare.objects.values()), shares)
        self.assertFalse(Corpse.objects.filter(pk=self.source.pk).exists())

    def test_currency_decay_failure_restores_already_transferred_physical_loot(self):
        self.loot_item()
        self.currency()
        before = self.all_state()
        with patch("world.loot_entities.models.CurrencyLoot.save", side_effect=RuntimeError("decay")), self.assertRaises(RuntimeError):
            self.source.reconcile(now=200)
        self.assertEqual(self.all_state(), before)

    def test_stale_quantity_and_complete_double_pickup_rejected(self):
        row = self.currency()
        selected = self.entry(row)
        loot_service.pickup(self.source, selected, self.char1, 5, now=100)
        before = self.all_state()
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, selected, self.char1, 5, now=100)
        self.assertEqual(self.all_state(), before)
        selected = self.entry(row)
        loot_service.pickup(self.source, selected, self.char1, 15, now=100)
        before = self.all_state()
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, selected, self.char1, 15, now=100)
        self.assertEqual(self.all_state(), before)

    def test_native_partial_and_indexed_chip_command_payload_no_ids(self):
        first = self.currency()
        second = self.currency(4, shares={self.char1: 4})
        controls = loot_controls(self.char1, 100)[self.source.pk]["loot"]
        self.assertEqual([entry["take_target"] for entry in controls], ["칩 1", "칩 2"])
        self.assertNotIn("currency_id", str(controls))
        take_loot(self.char1, request=parse_loot("시체에서 5칩", ["칩"]), now=100)
        take_loot(self.char1, request=parse_loot("시체에서 칩 2", ["칩"]), now=100)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.quantity, second.quantity), (15, 3))
        self.assertEqual(self.balances(), [24, 22])
        take_loot(self.char1, request=parse_loot("시체에서 칩 모두", ["칩"]), now=100)
        self.assertFalse(CurrencyLoot.objects.exists())
        self.assertFalse(CurrencyLootShare.objects.exists())

    def test_validation_quantity_owner_refs_and_sum(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                loot_service.create_currency(self.source, value)
        with self.assertRaises(ValidationError):
            loot_service.create_currency(self.char1, 10)
        with self.assertRaises(ValidationError):
            self.currency(20, shares={self.char1: 19})
        row = self.currency()
        for value in (-1, True, 1.5, 21):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                CurrencyLootShare(currency_loot=row, player=self.char1, remaining_amount=value).save()
        row.quantity = 19
        with self.assertRaises(ValidationError):
            row.save()

    def test_creation_failure_rolls_back_currency_and_shares(self):
        before = self.all_state()
        original = CurrencyLootShare.save

        def fail_second(share, *args, **kwargs):
            if share.player_id == self.char2.pk:
                raise RuntimeError("second share")
            return original(share, *args, **kwargs)

        with patch.object(CurrencyLootShare, "save", fail_second), self.assertRaises(RuntimeError):
            self.currency()
        self.assertEqual(self.all_state(), before)

    def test_legacy_currency_path_never_creates_native_rows(self):
        self.source.db.loot_backend = None
        self.source.db.entries = [dict(kind="currency", id="credits", quantity=20, protection_until=300,
                                       eligible_players=[self.char1.pk, self.char2.pk],
                                       remaining_shares={self.char1.pk: 10, self.char2.pk: 10})]
        take_loot(self.char1, request=parse_loot("시체에서 5칩", ["칩"]), now=100)
        self.assertEqual(self.balances(), [23, 22])
        self.assertEqual(self.source.db.entries[0]["quantity"], 15)
        self.assertFalse(CurrencyLoot.objects.exists())
        self.assertFalse(CurrencyLootShare.objects.exists())
