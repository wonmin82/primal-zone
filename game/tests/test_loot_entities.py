"""권리/부분 회수/실물 tree와 출처의 원자적 수명주기."""

from copy import deepcopy
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from evennia import create_object
from typeclasses.loot import Corpse, DroppedLoot, take_loot
from typeclasses.parties import invite, respond
from world import loot_service, rules
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.loot_entities.models import LootClaim
from world.state import loot_controls, loot_entries
from world.targets import parse_loot

from tests.loot_entity_fixture import NativeLootTest


class LootEntityTests(NativeLootTest):
    def test_claim_root_location_and_protected_deletion(self):
        root = self.loot_item()
        self.assertEqual(LootClaim.objects.count(), 1)
        self.assertNotIn("claim", root.state)
        with self.assertRaises(ProtectedError):
            root.delete()
        with self.assertRaises(ProtectedError):
            self.source.delete()
        with self.assertRaises(ProtectedError):
            self.char1.delete()
        with self.assertRaises(ValidationError):
            api.move_item(root, location_kind="inventory", owner_object=self.char1)
        with self.assertRaises(ValidationError):
            LootClaim(item_entity=self.create("ammo_9"), protection_until=300).save()
        with self.assertRaises((ValidationError, IntegrityError)), transaction.atomic():
            LootClaim(item_entity=root, protection_until=300).save()
        self.assertEqual(loot_service.integrity_errors(self.source), [])

    def test_stale_item_instance_cannot_create_inventory_claim(self):
        root = self.loot_item()
        stale = api._current(root)
        loot_service.pickup(self.source, self.entry(root), self.char1, 10, now=100)
        with self.assertRaises(ValidationError):
            LootClaim(item_entity=stale, protection_until=300).save()
        self.assertFalse(LootClaim.objects.exists())

    def test_full_pickup_keeps_identity_sequence_and_drops_claim(self):
        root = self.loot_item()
        identity, sequence = root.pk, root.sequence
        loot_service.pickup(self.source, self.entry(root), self.char1, 10, now=100)
        root.refresh_from_db()
        self.assertEqual((root.pk, root.sequence, root.location_kind, root.owner_object_id),
                         (identity, sequence, "inventory", self.char1.pk))
        self.assertFalse(LootClaim.objects.exists())
        self.assertEqual(dict(self.char1.profile())["inventory"], {})
        self.assertEqual(self.source.db.entries, [])

    def test_partial_pickup_source_rights_and_inventory_merge(self):
        destination = self.create("ammo_9", quantity=2)
        root = self.loot_item()
        original = (root.pk, root.sequence, LootClaim.objects.get(item_entity=root).pk)
        loot_service.pickup(self.source, self.entry(root), self.char1, 3, now=100)
        root.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(root.quantity, 7)
        self.assertEqual((root.pk, root.sequence, LootClaim.objects.get(item_entity=root).pk), original)
        self.assertEqual(destination.quantity, 5)
        self.assertEqual(ItemEntity.objects.count(), 2)
        self.assertFalse(LootClaim.objects.filter(item_entity=destination).exists())

    def test_partial_pickup_new_sequence_without_claim(self):
        root = self.loot_item()
        loot_service.pickup(self.source, self.entry(root), self.char1, 3, now=100)
        split = ItemEntity.objects.get(location_kind="inventory")
        self.assertGreater(split.sequence, root.sequence)
        self.assertEqual(split.quantity, 3)
        self.assertFalse(LootClaim.objects.filter(item_entity=split).exists())

    def test_outsider_protection_and_expiry_reconcile(self):
        root = self.loot_item(deadline=110)
        before = self.all_state()
        selected = self.entry(root)
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, selected, self.char2, 10, now=109)
        self.assertEqual(self.all_state(), before)
        self.assertFalse(loot_entries(self.source, self.char2, 109)[0]["can_take"])
        self.assertTrue(loot_entries(self.source, self.char2, 110)[0]["can_take"])
        self.assertEqual(self.all_state(), before)  # expired 조회는 read-only
        loot_service.reconcile_claims(self.source, now=110)
        root.refresh_from_db()
        self.assertEqual(root.location_kind, "corpse_loot")
        self.assertFalse(LootClaim.objects.exists())
        loot_service.pickup(self.source, self.entry(root), self.char2, 10, now=110)
        root.refresh_from_db()
        self.assertEqual(root.owner_object_id, self.char2.pk)

    def test_party_entry_is_one_unit_and_assigned_recipient(self):
        party = invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        root = self.loot_item(party=party, assigned=self.char2)
        received = loot_service.pickup(self.source, self.entry(root), self.char1, 10, now=100)
        self.assertEqual(received, [(self.char2, "ammo_9", 10)])
        root.refresh_from_db()
        self.assertEqual(root.owner_object_id, self.char2.pk)
        self.assertEqual(root.quantity, 10)
        self.assertEqual(ItemEntity.objects.count(), 1)

    def test_party_dissolution_keeps_assignment_deadline_and_currency_eligibility(self):
        party = invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        root = self.loot_item(party=party, assigned=self.char2)
        currency = loot_service.create_currency(self.source, 20, shares={self.char1: 10, self.char2: 10},
                                                reserved_party=party, protection_until=300)
        party.remove_member(self.char2)
        party.remove_member(self.char1)
        claim = LootClaim.objects.get(item_entity=root)
        currency.refresh_from_db()
        self.assertIsNone(claim.reserved_party_id)
        self.assertIsNone(currency.reserved_party_id)
        self.assertEqual((claim.assigned_player_id, claim.protection_until), (self.char2.pk, 300))
        self.assertEqual(currency.quantity, 20)
        self.assertEqual(self.entry(currency).as_entry()["eligible_players"], [self.char1.pk, self.char2.pk])
        loot_service.pickup(self.source, self.entry(root), self.char2, 10, now=100)

    def test_legacy_physical_pickup_cannot_hide_items_in_native_profile(self):
        self.source.db.loot_backend = None
        self.source.db.entries = [dict(kind="item", id="scrap", quantity=1)]
        before = self.all_state()
        with self.assertRaises(rules.RuleError):
            take_loot(self.char1, item="scrap", now=100)
        self.assertEqual(self.all_state(), before)

    def test_room_and_light_access_still_gate_native_loot_commands(self):
        self.loot_item()
        before = self.all_state()
        with patch("world.observation.can_inspect_loot", return_value=False), self.assertRaises(rules.RuleError):
            take_loot(self.char1, now=100)
        self.assertEqual(self.all_state(), before)
        selected = loot_service.loot_snapshot(self.source).entries[0]
        self.char1.location = self.room2
        before = self.all_state()
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, selected, self.char1, 10, now=100)
        self.assertEqual(self.all_state(), before)

    def test_different_allocation_units_never_merge_even_same_rights(self):
        first, second = self.loot_item(), self.loot_item()
        before = self.all_state()
        with self.assertRaises(ValidationError):
            api.merge_stack(first, second)
        self.assertEqual(self.all_state(), before)
        first_claim = LootClaim.objects.get(item_entity=first)
        old_context = loot_service.claim_context(first)
        first_claim.delete()
        replacement = loot_service.create_claim(first, reserved_player=self.char1,
                                                assigned_player=self.char1, protection_until=300)
        self.assertNotEqual(first_claim.pk, replacement.pk)
        self.assertEqual(old_context, loot_service.claim_context(first))  # DB PK가 merge 의미는 아니다.
        first = self.create("ammo_9", quantity=2)
        second = self.create("ammo_9", quantity=3)
        api.merge_stack(first, second)
        second.refresh_from_db()
        self.assertEqual(second.quantity, 5)

    def test_firearm_tree_pickup_and_child_claim_rejection(self):
        root = self.loot_item("test_pistol", 1)
        child = api.create_item("mag_9_standard", location_kind="inside", parent_item=root,
                                socket="magazine", state={"rounds": 7})
        with self.assertRaises(ValidationError):
            LootClaim(item_entity=child, protection_until=300).save()
        loot_service.pickup(self.source, self.entry(root), self.char1, 1, now=100)
        child.refresh_from_db()
        self.assertEqual((child.location_kind, child.parent_item_id, child.socket, child.state),
                         ("inside", root.pk, "magazine", {"rounds": 7}))
        self.assertFalse(LootClaim.objects.exists())

    def test_decay_preserves_tree_rights_and_sequence(self):
        root = self.loot_item("test_pistol", 1)
        child = api.create_item("mag_9_standard", location_kind="inside", parent_item=root,
                                socket="magazine", state={"rounds": 7})
        rights = list(LootClaim.objects.values())
        sequence = root.sequence
        self.source.reconcile(now=200)
        root.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(root.location_kind, "world_loot")
        self.assertIsInstance(root.owner_object, DroppedLoot)
        self.assertEqual(root.sequence, sequence)
        self.assertEqual(list(LootClaim.objects.values()), rights)
        self.assertEqual((child.parent_item_id, child.socket, child.state), (root.pk, "magazine", {"rounds": 7}))
        self.assertFalse(Corpse.objects.filter(pk=self.source.pk).exists())

    def test_move_split_merge_and_claim_removal_failures_rollback(self):
        self.create("ammo_9", quantity=2)
        root = self.loot_item()
        selected = self.entry(root)
        for target, quantity in (("world.item_entities.api.move_item_tree", 10),
                                 ("world.item_entities.api.move_item_tree", 3),
                                 ("world.item_entities.api.merge_stack", 3),
                                 ("world.item_entities.api.create_item", 3),
                                 ("django.db.models.query.QuerySet.delete", 10)):
            with self.subTest(target=target, quantity=quantity):
                before = self.all_state()
                with patch(target, side_effect=RuntimeError("fixture failure")), self.assertRaises(RuntimeError):
                    loot_service.pickup(self.source, selected, self.char1, quantity, now=100)
                self.assertEqual(self.all_state(), before)

    def test_stale_source_claim_and_double_pickup_rejected(self):
        root = self.loot_item()
        selected = self.entry(root)
        claim = LootClaim.objects.get(item_entity=root)
        claim.assigned_player = self.char2
        claim.save()
        before = self.all_state()
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, selected, self.char1, 10, now=100)
        self.assertEqual(self.all_state(), before)
        selected = self.entry(root)
        loot_service.pickup(self.source, selected, self.char1, 10, now=100)
        before = self.all_state()
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, selected, self.char1, 10, now=100)
        self.assertEqual(self.all_state(), before)

    def test_decay_stale_corpse_handle_and_failure_rollback(self):
        root = self.loot_item()
        selected = self.entry(root)
        before = self.all_state()
        with patch("world.item_entities.api.move_item_tree", side_effect=RuntimeError("decay")), self.assertRaises(RuntimeError):
            self.source.reconcile(now=200)
        self.assertEqual(self.all_state(), before)
        loot_service.decay_source(self.source, now=200)
        before = self.all_state()
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, selected, self.char1, 10, now=201)
        self.assertEqual(self.all_state(), before)

    def test_failure_after_corpse_delete_restores_container_and_all_assets(self):
        self.loot_item()
        loot_service.create_currency(self.source, 20, shares={self.char1: 10, self.char2: 10},
                                     protection_until=300)
        before = self.all_state()
        identity = self.source.pk
        original = self.source.delete

        def fail_after_delete(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("after corpse delete")

        with patch.object(self.source, "delete", fail_after_delete), self.assertRaises(RuntimeError):
            self.source.reconcile(now=200)
        self.assertEqual(self.source.pk, identity)
        self.assertTrue(Corpse.objects.filter(pk=identity).exists())
        self.assertEqual(self.all_state(), before)

    def test_command_all_pickup_currency_failure_rolls_back_prior_physical_move(self):
        self.loot_item()
        loot_service.create_currency(self.source, 20, shares={self.char1: 10, self.char2: 10},
                                     protection_until=300)
        before = self.all_state()
        with patch.object(self.char2, "save_profile", side_effect=RuntimeError("payout")), self.assertRaises(RuntimeError):
            take_loot(self.char1, now=100)
        self.assertEqual(self.all_state(), before)

    def test_native_selector_payload_and_command_uses_same_root_instances(self):
        first, second = self.loot_item("blade", 1), self.loot_item("blade", 1)
        controls = loot_controls(self.char1, 100)[self.source.pk]["loot"]
        self.assertEqual([entry["label"] for entry in controls], ["강철마체테 1", "강철마체테 2"])
        self.assertNotIn(str(first.pk), str(controls))
        self.assertNotIn(str(second.pk), str(controls))
        take_loot(self.char1, request=parse_loot("시체에서 강철마체테 2", []), now=100)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.location_kind, second.location_kind), ("corpse_loot", "inventory"))
        self.assertEqual(self.source.db.entries, [])

    def test_explicit_native_generation_reuses_round_robin_and_currency_allocation(self):
        enemy = create_object("typeclasses.enemies.Enemy", key="시험 적", location=self.char1.location)
        enemy.db.enemy_id = "scavenger"
        party = invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        groups = {f"party:{party.pk}": {self.char1.pk: 1, self.char2.pk: 1}}
        rng = Mock()
        rng.random.return_value = 0
        corpse = Corpse.from_enemy(enemy, groups, 100, rng=rng, backend="item_entities")
        snapshot = loot_service.loot_snapshot(corpse)
        self.assertEqual([entry.assigned_player for entry in snapshot.entries if entry.kind == "item"],
                         [self.char1.pk, self.char2.pk])
        self.assertEqual(party.state()["round_robin_cursor"], 2)
        self.assertEqual(sum(entry.quantity for entry in snapshot.entries if entry.kind == "currency"), 8)
        self.assertEqual(corpse.db.entries, [])
        self.assertEqual(self.char1.profile()["xp"], 0)

    def test_legacy_adapter_reads_without_generating_models(self):
        self.source.db.loot_backend = None
        self.source.db.entries = [{"kind": "item", "id": "scrap", "quantity": 1}]
        before = self.all_state()
        self.assertFalse(loot_service.loot_snapshot(self.source).native)
        self.assertEqual(loot_entries(self.source, self.char1, 100)[0]["name"], "회수부품")
        self.assertEqual(self.all_state(), before)

    def test_invalid_native_destination_backend_does_not_dual_write(self):
        root = self.loot_item()
        self.char1.db.equipment_backend = None
        before = self.all_state()
        with self.assertRaises(rules.RuleError):
            loot_service.pickup(self.source, self.entry(root), self.char1, 10, now=100)
        self.assertEqual(self.all_state(), before)

    def test_generation_failure_rolls_back_rows_and_sequence(self):
        source = create_object(Corpse, key="빈 시체", location=self.char1.location)
        source.db.decay_at = 200
        entries = [dict(kind="item", id="scrap", quantity=1), dict(kind="item", id="missing", quantity=1)]
        before = self.all_state()
        with self.assertRaises(ValidationError):
            loot_service.populate_source(source, entries)
        self.assertEqual(self.all_state(), before)
        self.assertIsNone(source.db.loot_backend)

    def test_model_invalid_reference_and_time_rejected(self):
        root = self.loot_item()
        claim = LootClaim.objects.get(item_entity=root)
        for field, value in (("reserved_party", self.char1), ("assigned_player", self.room1),
                             ("protection_until", float("nan")), ("protection_until", -1)):
            with self.subTest(field=field):
                candidate = deepcopy(claim)
                setattr(candidate, field, value)
                with self.assertRaises(ValidationError):
                    candidate.save()
