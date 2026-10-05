"""실제 DB에서 아이템 위치·순번·트리·rollback 경계를 검사한다."""

from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.db.models.deletion import ProtectedError
from django.test.utils import CaptureQueriesContext
from evennia import create_object
from typeclasses.explorers import Explorer
from typeclasses.interactables import Container, PersonalLocker
from typeclasses.loot import Corpse, DroppedLoot
from world.content import ITEMS
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence
from world.item_entities.policy import can_item_operation
from world.multiplayer import after_change, world_change

from tests.base import GameCommandTest


class ItemEntityTests(GameCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.enterContext(patch("typeclasses.explorers.delay"))
        self.char1.push_state = Mock()
        self.char2.push_state = Mock()

    def create(self, definition="bandage", **kwargs):
        return api.create_item(
            definition,
            **{
                "location_kind": "inventory",
                "owner_object": self.char1,
                **kwargs,
            },
        )

    def raw(self, **kwargs):
        return ItemEntity(
            **{
                "id": uuid4(),
                "definition_id": "bandage",
                "quantity": 1,
                "location_kind": "inventory",
                "owner_object": self.char1,
                "sequence": 10000 + ItemEntity.objects.count(),
                **kwargs,
            }
        )

    def unique_definition(self):
        definition = {**deepcopy(ITEMS["machete"]), "unique_per_owner": True}
        self.enterContext(patch.dict(ITEMS, {"unique_test": definition}))

    def test_creation_persists_opaque_identity_and_definition_state(self):
        state = {"condition": 4}
        item = self.create(quantity=3, state=state)
        state["condition"] = 0
        item.refresh_from_db()
        self.assertIsInstance(item.pk, UUID)
        self.assertEqual(
            (item.definition_id, item.quantity, item.state), ("bandage", 3, {"condition": 4})
        )
        self.assertGreater(item.sequence, 0)
        self.assertIsNone(item.unique_scope_key)

    def test_definition_and_quantity_are_validated_without_partial_creation(self):
        for definition, quantity in (
            ("missing", 1),
            ("bandage", 0),
            ("bandage", -1),
            ("bandage", True),
            ("bandage", 1.5),
            ("bandage", "2"),
            ("machete", 2),
        ):
            before = ItemSequence.objects.get(pk=1).last_value
            with (
                self.subTest(definition=definition, quantity=quantity),
                self.assertRaises(ValidationError),
            ):
                self.create(definition, quantity=quantity)
            self.assertEqual(ItemEntity.objects.count(), 0)
            self.assertEqual(ItemSequence.objects.get(pk=1).last_value, before)

    def test_database_rejects_invalid_canonical_locations_and_quantities(self):
        parent = self.create("machete")
        invalid = [
            {"quantity": 0},
            {"sequence": 0},
            {"location_kind": "unknown"},
            {"owner_object": None},
            {"slot": "body"},
            {"socket": "magazine"},
            {"parent_item": parent},
            {"location_kind": "equipment"},
            {"location_kind": "equipment", "slot": ""},
            {"location_kind": "equipment", "slot": "hands", "socket": "magazine"},
            {"location_kind": "inside", "owner_object": None, "parent_item": parent},
            {"location_kind": "inside", "parent_item": parent, "socket": "magazine"},
            {"location_kind": "inside", "owner_object": None, "socket": "magazine"},
            {"location_kind": "inside", "owner_object": None, "parent_item": parent, "socket": ""},
        ]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), world_change():
                ItemEntity.objects.bulk_create([self.raw(**fields)])
        identity = uuid4()
        with self.assertRaises(IntegrityError), world_change():
            ItemEntity.objects.bulk_create(
                [
                    self.raw(
                        id=identity,
                        location_kind="inside",
                        owner_object=None,
                        parent_item_id=identity,
                        socket="part",
                    )
                ]
            )

    def test_all_supported_locations_accept_their_owner_and_field_shape(self):
        box = create_object(Container, key="검증상자")
        corpse = create_object(Corpse, key="검증시체")
        ground = create_object(DroppedLoot, key="검증전리품")
        parent = self.create("machete")
        for location, owner, fields in (
            ("inventory", self.char1, {}),
            ("equipment", self.char1, {"slot": "hands"}),
            ("personal_storage", self.char1, {}),
            ("shared_storage", box, {}),
            ("world_loot", ground, {}),
            ("corpse_loot", corpse, {}),
            ("inside", None, {"parent_item": parent, "socket": "part"}),
        ):
            with self.subTest(location=location):
                item = self.create("machete" if location == "equipment" else "bandage", location_kind=location, owner_object=owner, **fields)
                item.refresh_from_db()
                self.assertEqual(item.location_kind, location)

    def test_personal_storage_belongs_to_explorer_and_shared_storage_to_public_container(self):
        locker = create_object(PersonalLocker, key="검증개인보관함")
        for location, owner in (
            ("personal_storage", locker),
            ("personal_storage", self.room1),
            ("shared_storage", locker),
            ("inventory", self.room1),
            ("corpse_loot", self.char1),
            ("world_loot", self.char1),
        ):
            with self.subTest(location=location), self.assertRaises(ValidationError):
                self.create(location_kind=location, owner_object=owner)
        self.assertEqual(self.create(location_kind="personal_storage").owner_object, self.char1)

    def test_nonstack_model_save_and_stack_limit_reject_invalid_quantity(self):
        item = self.create("machete")
        item.quantity = 2
        with self.assertRaises(ValidationError):
            item.save()
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)
        with patch.dict(ITEMS["bandage"], {"max_stack": 3}):
            self.create(quantity=3)
            with self.assertRaises(ValidationError):
                self.create(quantity=4)

    def test_split_conserves_quantity_state_and_assigns_new_sequence(self):
        source = self.create(quantity=9, state={"batch": 3})
        fragment = api.split_stack(source, 4)
        source.refresh_from_db()
        self.assertEqual((source.quantity, fragment.quantity), (5, 4))
        self.assertEqual(source.state, fragment.state)
        self.assertGreater(fragment.sequence, source.sequence)
        self.assertEqual(fragment.owner_object_id, source.owner_object_id)
        for quantity in (0, -1, True, 5, 6):
            with self.assertRaises(ValidationError):
                api.split_stack(source, quantity)
        self.assertEqual(ItemEntity.objects.count(), 2)

    def test_merge_keeps_destination_identity_sequence_and_total(self):
        source = self.create(quantity=3)
        destination = self.create(quantity=2)
        identity, sequence = destination.pk, destination.sequence
        source.quantity, destination.quantity = 99, 99  # stale 입력 대신 잠근 DB row를 사용한다.
        result = api.merge_stack(source, destination)
        self.assertEqual((result.pk, result.sequence, result.quantity), (identity, sequence, 5))
        self.assertFalse(ItemEntity.objects.filter(pk=source.pk).exists())

    def test_inside_split_preserves_parent_and_locks_source_with_ancestors(self):
        parent = self.create("machete")
        source = self.create(
            quantity=7,
            location_kind="inside",
            owner_object=None,
            parent_item=parent,
            socket="supplies",
        )
        with patch("world.item_entities.api.lock_items", wraps=api.lock_items) as locks:
            fragment = api.split_stack(source, 3)
        self.assertEqual(
            set(api.ordered_item_ids(locks.call_args_list[0].args[0])), {source.pk, parent.pk}
        )
        source.refresh_from_db()
        self.assertEqual((source.quantity, fragment.quantity), (4, 3))
        self.assertEqual(fragment.parent_item_id, parent.pk)
        self.assertEqual(fragment.socket, source.socket)
        self.assertGreater(fragment.sequence, source.sequence)

    def test_merge_rejects_different_location_state_definition_and_capacity(self):
        destination = self.create(quantity=2)
        sources = [
            self.create("scrap"),
            self.create(owner_object=self.char2),
            self.create(location_kind="personal_storage"),
            self.create(state={"batch": 1}),
        ]
        for source in [destination, *sources]:
            with self.assertRaises(ValidationError):
                api.merge_stack(source, destination)
        source = self.create(quantity=2)
        with patch.dict(ITEMS["bandage"], {"max_stack": 3}), self.assertRaises(ValidationError):
            api.merge_stack(source, destination)
        destination.refresh_from_db()
        self.assertEqual(destination.quantity, 2)
        self.assertTrue(ItemEntity.objects.filter(pk=source.pk).exists())

    def test_sequence_order_survives_move_delete_split_and_merge(self):
        first, second = self.create(), self.create()
        original = first.sequence
        moved = api.move_item(first, location_kind="personal_storage", owner_object=self.char1)
        self.assertEqual(moved.sequence, original)
        api.move_item(first, location_kind="inventory", owner_object=self.char1)
        self.assertEqual(
            list(api.items_in_location("inventory", owner_object=self.char1)), [first, second]
        )
        last = second.sequence
        api.delete_item(second)
        third = self.create()
        self.assertGreater(third.sequence, last)
        with self.assertRaises(ValidationError):
            moved.sequence += 100
            moved.save()

    def test_parent_cycles_are_rejected_and_tree_move_preserves_inside(self):
        root = self.create("machete")
        child = self.create(
            "flashlight", location_kind="inside", owner_object=None, parent_item=root, socket="tool"
        )
        grandchild = self.create(
            "battery", location_kind="inside", owner_object=None, parent_item=child, socket="power"
        )
        for parent in (root, child, grandchild):
            with self.assertRaises(ValidationError):
                api.move_item_tree(root, location_kind="inside", parent_item=parent, socket="part")
        with self.assertRaises(ValidationError):
            api.move_item(root, location_kind="inventory", owner_object=self.char2)
        api.move_item_tree(root, location_kind="personal_storage", owner_object=self.char2)
        child.refresh_from_db()
        self.assertEqual(
            (child.location_kind, child.parent_item_id, child.socket), ("inside", root.pk, "tool")
        )
        self.assertEqual(list(api.items_owned_by(self.char1)), [])
        self.assertEqual(list(api.items_owned_by(self.char2)), [root, child, grandchild])
        self.assertEqual(list(api.children_of(root)), [child])

    def test_model_parent_cycle_and_parent_owner_deletion_are_protected(self):
        root = self.create("machete")
        child = self.create(
            location_kind="inside", owner_object=None, parent_item=root, socket="part"
        )
        root.location_kind, root.owner_object, root.parent_item, root.socket = (
            "inside",
            None,
            child,
            "part",
        )
        with self.assertRaises(ValidationError):
            root.save()
        with self.assertRaises(ProtectedError):
            api.delete_item(root)
        # 실제 FK collector에서도 소유자의 암묵적 삭제를 차단한다.
        with self.assertRaises(ProtectedError):
            type(self.char1).objects.filter(pk=self.char1.pk).delete()
        api.delete_item(child)
        api.delete_item(root)
        self.assertEqual(ItemEntity.objects.count(), 0)

    def test_outer_failure_restores_items_counter_profile_cache_and_callbacks(self):
        item = self.create(quantity=6)
        before = deepcopy(self.char1.profile())
        sequence = ItemSequence.objects.get(pk=1).last_value
        callback = Mock()
        with self.assertRaises(RuntimeError), world_change():
            api.move_item(item, location_kind="personal_storage", owner_object=self.char1)
            api.split_stack(item, 2)
            self.char1.change(lambda profile: profile.update(credits=999))
            after_change(callback)
            raise RuntimeError("의도한 transaction 실패")
        item.refresh_from_db()
        self.assertEqual((item.location_kind, item.quantity), ("inventory", 6))
        self.assertEqual(ItemEntity.objects.count(), 1)
        self.assertEqual(ItemSequence.objects.get(pk=1).last_value, sequence)
        self.assertEqual(self.char1.profile(), before)
        callback.assert_not_called()
        self.char1.push_state.assert_not_called()

    def test_row_lock_order_is_deterministic_for_reversed_and_duplicate_ids(self):
        first, second = self.create(), self.create()
        with world_change(), CaptureQueriesContext(connection) as queries:
            locked = api.lock_items([second, first.pk, str(second.pk)])
        expected = sorted([first.pk, second.pk])
        self.assertEqual([item.pk for item in locked], expected)
        self.assertEqual(len(queries), 2)
        for query, identity in zip(queries, expected):
            self.assertIn(identity.hex, query["sql"])
        self.assertEqual(api.ordered_item_ids([first, second]), tuple(expected))

    def test_stack_mutations_lock_owners_before_item_rows(self):
        from world import equipment_service

        source, destination = self.create(quantity=4), self.create(quantity=2)
        events = []
        original_owner, original_items = equipment_service.before_item_change, api.lock_items

        def owners(*args, **kwargs):
            events.append("owners")
            return original_owner(*args, **kwargs)

        def items(*args, **kwargs):
            events.append("items")
            return original_items(*args, **kwargs)

        with patch.object(equipment_service, "before_item_change", side_effect=owners), patch.object(api, "lock_items", side_effect=items):
            fragment = api.split_stack(source, 1)
            self.assertEqual(events[0], "owners")
            events.clear()
            api.merge_stack(fragment, destination)
            self.assertEqual(events[0], "owners")

    def test_database_unique_scope_allows_null_but_rejects_duplicates(self):
        ItemEntity.objects.bulk_create([self.raw()])
        ItemEntity.objects.bulk_create([self.raw()])
        ItemEntity.objects.bulk_create([self.raw(unique_scope_key="test:scope")])
        with self.assertRaises(IntegrityError), world_change():
            ItemEntity.objects.bulk_create([self.raw(unique_scope_key="test:scope")])

    def test_unique_owner_scope_includes_personal_storage_and_nested_items(self):
        self.unique_definition()
        first = self.create("unique_test")
        with self.assertRaises(ValidationError):
            self.create("unique_test", location_kind="personal_storage")
        other = self.create("unique_test", owner_object=self.char2)
        parent = self.create("machete")
        api.move_item(first, location_kind="inside", parent_item=parent, socket="part")
        with self.assertRaises(ValidationError):
            api.move_item_tree(parent, location_kind="inventory", owner_object=self.char2)
        parent.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(parent.owner_object_id, self.char1.id)
        self.assertEqual(first.unique_scope_key, f"{self.char1.id}:unique_test")
        api.delete_item(other)
        api.move_item_tree(parent, location_kind="inventory", owner_object=self.char2)
        first.refresh_from_db()
        self.assertEqual(first.unique_scope_key, f"{self.char2.id}:unique_test")

    def test_policy_denies_unknown_operation_and_tree_move_checks_children(self):
        self.assertTrue(can_item_operation("bandage", "give"))
        self.assertFalse(can_item_operation("bandage", "unknown"))
        self.assertFalse(can_item_operation("jungle_cell", "give"))
        root = self.create("machete")
        self.create(
            "jungle_cell",
            location_kind="inside",
            owner_object=None,
            parent_item=root,
            socket="part",
        )
        with self.assertRaises(ValidationError):
            api.move_item_tree(
                root, location_kind="inventory", owner_object=self.char2, operation="give"
            )
        root.refresh_from_db()
        self.assertEqual(root.owner_object_id, self.char1.id)

    def test_tree_equip_checks_root_only_and_preserves_passive_child(self):
        root_definition = deepcopy(ITEMS["machete"])
        root_definition.update(weapon_type="firearm", firearm_family="pistol_9mm")
        child_definition = deepcopy(ITEMS["mag_9_standard"])
        child_definition["operation_policy"]["equip"] = False
        with patch.dict(
            ITEMS, {"equip_root_test": root_definition, "socket_child_test": child_definition}
        ):
            root = self.create("equip_root_test")
            child = self.create(
                "socket_child_test",
                location_kind="inside",
                owner_object=None,
                parent_item=root,
                socket="magazine",
            )
            sequences = (root.sequence, child.sequence)
            self.assertFalse(can_item_operation(child, "equip"))
            api.move_item_tree(
                root,
                location_kind="equipment",
                owner_object=self.char1,
                slot="hands",
                operation="equip",
            )
            root.refresh_from_db()
            child.refresh_from_db()
            self.assertEqual((root.location_kind, root.slot), ("equipment", "hands"))
            self.assertEqual(root.owner_object_id, self.char1.pk)
            self.assertEqual(
                (child.location_kind, child.parent_item_id, child.socket, child.owner_object_id),
                ("inside", root.pk, "magazine", None),
            )
            self.assertEqual((root.sequence, child.sequence), sequences)
            with patch.dict(root_definition["operation_policy"], {"equip": False}):
                with self.assertRaises(ValidationError):
                    api.move_item_tree(
                        root, location_kind="inventory", owner_object=self.char1, operation="equip"
                    )
            root.refresh_from_db()
            self.assertEqual((root.location_kind, root.slot), ("equipment", "hands"))

    def test_tree_transfer_restriction_preserves_all_rows_and_unique_scopes(self):
        operations = ("give", "drop", "store", "sell", "burn", "loot", "consume")
        root_definition = {**deepcopy(ITEMS["machete"]), "unique_per_owner": True}
        root_definition["operation_policy"].update(dict.fromkeys(operations, True))
        child_definition = {
            **deepcopy(ITEMS["jungle_cell"]),
            "stackable": False,
            "unique_per_owner": True,
        }
        child_definition["operation_policy"].update(dict.fromkeys(operations, False))
        with patch.dict(
            ITEMS,
            {"transfer_root_test": root_definition, "restricted_child_test": child_definition},
        ):
            root = self.create("transfer_root_test")
            child = self.create(
                "restricted_child_test",
                location_kind="inside",
                owner_object=None,
                parent_item=root,
                socket="power",
            )
            ground = create_object(DroppedLoot, key="검증바닥")
            self.assertEqual(child.unique_scope_key, f"{self.char1.pk}:restricted_child_test")
            before = list(ItemEntity.objects.order_by("sequence").values())
            counter = ItemSequence.objects.get(pk=1).last_value
            for operation in operations:
                location, owner = {
                    "drop": ("world_loot", ground),
                    "store": ("personal_storage", self.char1),
                }.get(operation, ("inventory", self.char2))
                with self.subTest(operation=operation):
                    self.assertTrue(can_item_operation(root, operation))
                    with self.assertRaises(ValidationError):
                        api.move_item_tree(
                            root, location_kind=location, owner_object=owner, operation=operation
                        )
                    self.assertEqual(list(ItemEntity.objects.order_by("sequence").values()), before)
                    self.assertEqual(ItemSequence.objects.get(pk=1).last_value, counter)

    def test_tree_unknown_operation_fails_closed_and_none_is_trusted_internal(self):
        root = self.create("machete")
        child = self.create(
            "jungle_cell",
            location_kind="inside",
            owner_object=None,
            parent_item=root,
            socket="power",
        )
        with self.assertRaises(ValidationError):
            api.move_item_tree(
                root, location_kind="inventory", owner_object=self.char2, operation="unknown"
            )
        with patch.dict(ITEMS["machete"]["operation_policy"], {"unknown": True}):
            self.assertFalse(can_item_operation(root, "unknown"))
            with self.assertRaises(ValidationError):
                api.delete_item(root, operation="unknown")
        root.refresh_from_db()
        self.assertEqual(root.owner_object_id, self.char1.pk)
        api.move_item_tree(root, location_kind="inventory", owner_object=self.char2, operation=None)
        root.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(root.owner_object_id, self.char2.pk)
        self.assertEqual(
            (child.location_kind, child.parent_item_id, child.socket), ("inside", root.pk, "power")
        )

    def test_default_merge_state_requires_complete_state_equality(self):
        state = {"batch": 1, "metadata": {"origin": "test"}}
        destination = self.create(quantity=2, state=state)
        different = self.create(quantity=3, state={**state, "metadata": {"origin": "other"}})
        with self.assertRaises(ValidationError):
            api.merge_stack(different, destination)
        self.assertTrue(ItemEntity.objects.filter(pk=different.pk).exists())
        destination.refresh_from_db()
        self.assertEqual(destination.quantity, 2)
        source = self.create(quantity=3, state=deepcopy(state))
        self.assertEqual(api.merge_stack(source, destination).quantity, 5)

    def test_merge_state_contract_can_select_relevant_state(self):
        destination = self.create(quantity=2, state={"batch": 1, "metadata": "destination"})
        source = self.create(quantity=3, state={"batch": 1, "metadata": "source"})
        different = self.create(quantity=4, state={"batch": 2, "metadata": "source"})
        # 테스트 안에서만 향후 정의별 계약을 재현한다. 영속 state schema는 추가하지 않는다.
        with patch(
            "world.item_entities.api.merge_state",
            side_effect=lambda item: {"batch": item.state["batch"]},
        ) as contract:
            with self.assertRaises(ValidationError):
                api.merge_stack(different, destination)
            self.assertTrue(ItemEntity.objects.filter(pk=different.pk).exists())
            result = api.merge_stack(source, destination)
            self.assertEqual(result.quantity, 5)
            self.assertEqual(result.state, destination.state)
            self.assertEqual(contract.call_count, 4)

    def test_sequence_initialization_is_idempotent_and_does_not_reset_used_counter(self):
        initialize = import_module(
            "world.item_entities.migrations.0002_initialize_sequence"
        ).initialize_sequence
        item = self.create()
        for _ in range(2):
            initialize(apps, SimpleNamespace(connection=connection))
        self.assertEqual(ItemSequence.objects.get(pk=1).last_value, item.sequence)
        self.assertGreater(self.create().sequence, item.sequence)

    def test_stale_or_nonstack_operations_fail_without_changing_rows(self):
        first, second = self.create("machete"), self.create("machete")
        with self.assertRaises(ValidationError):
            api.split_stack(first, 1)
        with self.assertRaises(ValidationError):
            api.merge_stack(first, second)
        identity = second.pk
        api.delete_item(second)
        for operation in (
            lambda: api.split_stack(identity, 1),
            lambda: api.move_item(identity, location_kind="inventory", owner_object=self.char1),
            lambda: api.move_item(second, location_kind="inventory", owner_object=self.char1),
            lambda: api.create_item(
                "bandage", location_kind="inside", parent_item=identity, socket="part"
            ),
        ):
            with self.assertRaises(ValidationError):
                operation()
        self.assertEqual(ItemEntity.objects.count(), 1)
