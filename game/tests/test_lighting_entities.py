"""손전등 독립 상태·참조·배터리·legacy 경계를 격리 DB에서 검증한다."""

from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import connection
from evennia.utils.create import create_object
from typeclasses.explorers import Explorer
from typeclasses.loot import DroppedLoot
from world import lighting_service as service
from world import observation, recovery, rules
from world.content import ITEMS
from world.environment import EnvironmentSnapshot
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.selection_numbers.api import number_for
from world.selection_numbers.models import SelectionNumber

from tests.item_entity_fixture import NativeItemTest


class LightingEntityTests(NativeItemTest):
    def charged(self):
        row = self.create("flashlight")
        battery = self.create("battery")
        service.insert_power(self.char1, row, battery, 100)
        return row

    def test_independent_states_and_sequence_selectors(self):
        first, second = self.charged(), self.charged()
        service.switch(self.char1, second, True, 100)
        service.switch(self.char1, second, False, 400)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.state["remaining_power"], 1800)
        self.assertEqual(second.state["remaining_power"], 1500)
        self.assertEqual(service.resolve_light(self.char1, "손전등 2", "켜")[0].pk, second.pk)
        self.assertEqual(service.resolve_light(self.char1, "손전등", "켜")[0].pk, first.pk)
        with self.assertRaises(rules.RuleError):
            service.resolve_light(self.char1, str(second.pk), "켜")
        self.assertNotIn(str(second.pk), service.status(self.char1, second, 400))

    def test_only_one_on_switch_settles_old_power(self):
        first, second = self.charged(), self.charged()
        service.switch(self.char1, first, True, 100)
        service.switch(self.char1, second, True, 220)
        first.refresh_from_db()
        self.assertEqual((first.state["remaining_power"], first.state["enabled"]), (1680, False))
        self.assertEqual(self.char1.db.active_light_item_id, str(second.pk))
        self.assertEqual(ItemEntity.objects.filter(state__enabled=True).count(), 1)
        self.assertEqual(service.lighting_snapshot(self.char1, now=280).active.remaining_power, 1740)

    def test_light_commands_reconcile_elapsed_recovery_boundary(self):
        row = self.charged()
        for index, action in enumerate(("켜", "꺼"), start=1):
            now = 100 + index * (6 * recovery.RECOVERY_INTERVAL + 1)
            before = self.char1.profile_snapshot()
            with patch("typeclasses.explorers.time", return_value=now), patch("world.lighting_service.time", return_value=now):
                self.char1.execute_cmd("손전등 " + action)
            after = self.char1.profile_snapshot()
            for resource in recovery.RESOURCES:
                self.assertGreater(after[resource], before[resource])
            self.assertEqual(after["recovery"]["updated_at"], now)
            row.refresh_from_db()
            self.assertEqual(row.state["enabled"], action == "켜")

    def test_invalid_or_missing_reference_settles_owned_orphan_off(self):
        for reference in ("stale-not-uuid", str(uuid4()), None):
            with self.subTest(reference=reference):
                row = self.charged()
                service.switch(self.char1, row, True, 100)
                self.char1.db.active_light_item_id = reference
                before = self.atomic_state()
                self.assertIsNone(service.lighting_snapshot(self.char1, now=200).active)
                self.assertEqual(before, self.atomic_state())
                service.reconcile(self.char1, 200)
                row.refresh_from_db()
                self.assertEqual(row.state["remaining_power"], 1700)
                self.assertFalse(row.state["enabled"])
                self.assertIsNone(row.state["started_at"])
                self.assertIsNone(self.char1.db.active_light_item_id)

    def test_valid_reference_kept_while_extra_inventory_orphan_turns_off(self):
        active, orphan, stored = self.charged(), self.charged(), self.charged()
        api.move_item(stored, location_kind="personal_storage", owner_object=self.char1, operation="store")
        for row in (orphan, stored):
            row.refresh_from_db()
            api.update_item_state(row, {**row.state, "enabled": True, "started_at": 100})
        active.refresh_from_db()
        api.update_item_state(active, {**active.state, "enabled": True, "started_at": 100})
        self.char1.db.active_light_item_id = str(active.pk)
        stored.refresh_from_db()
        before = dict(stored.state)
        service.reconcile(self.char1, 200)
        active.refresh_from_db()
        orphan.refresh_from_db()
        stored.refresh_from_db()
        self.assertTrue(active.state["enabled"])
        self.assertEqual(active.state["remaining_power"], 1800)
        self.assertEqual(self.char1.db.active_light_item_id, str(active.pk))
        self.assertEqual((orphan.state["remaining_power"], orphan.state["enabled"], orphan.state["started_at"]),
                         (1700, False, None))
        self.assertEqual(stored.state, before)

    def test_lazy_read_exhaustion_and_domain_reconciliation(self):
        row = self.charged()
        service.switch(self.char1, row, True, 100)
        before = self.atomic_state()
        service.reconcile(self.char1, 101)
        self.assertEqual(before, self.atomic_state())
        self.assertIsNone(service.lighting_snapshot(self.char1, now=2000).active)
        self.assertEqual(before, self.atomic_state())
        service.reconcile(self.char1, 2000)
        row.refresh_from_db()
        self.assertEqual(row.state["remaining_power"], 0)
        self.assertFalse(row.state["enabled"])
        self.assertIsNone(self.char1.db.active_light_item_id)

    def test_battery_stack_decrement_delete_and_reject_usable(self):
        row, battery = self.create("flashlight"), self.create("battery", quantity=2)
        service.insert_power(self.char1, row, battery, 100)
        battery.refresh_from_db()
        self.assertEqual(battery.quantity, 1)
        before = self.atomic_state()
        with self.assertRaises(rules.RuleError):
            service.insert_power(self.char1, row, battery, 101)
        self.assertEqual(before, self.atomic_state())
        service.switch(self.char1, row, True, 100)
        service.insert_power(self.char1, row, battery, 1900)
        self.assertFalse(ItemEntity.objects.filter(pk=battery.pk).exists())
        row.refresh_from_db()
        self.assertEqual((row.state["remaining_power"], row.state["enabled"]), (1800, False))

    def test_battery_and_switch_failures_roll_back_everything(self):
        row, battery = self.create("flashlight"), self.create("battery")
        before = self.atomic_state()
        with patch.object(api, "update_item_state", side_effect=ValidationError("시험 실패")):
            with self.assertRaises(rules.RuleError):
                service.insert_power(self.char1, row, battery, 100)
        self.assertEqual(before, self.atomic_state())
        first, second = self.charged(), self.charged()
        service.switch(self.char1, first, True, 100)
        before = self.atomic_state()
        original = api.update_item_state

        def fail_new(item, state):
            if item.pk == second.pk:
                raise ValidationError("새 광원 실패")
            return original(item, state)

        with patch.object(api, "update_item_state", side_effect=fail_new):
            with self.assertRaises(rules.RuleError):
                service.switch(self.char1, second, True, 220)
        self.assertEqual(before, self.atomic_state())

    def test_external_move_give_store_delete_reference_atomicity(self):
        loot = create_object(DroppedLoot, key="시험 전리품", location=self.room1)
        for kind, owner, operation in (("world_loot", loot, "drop"),
                                        ("inventory", self.char2, "give"),
                                        ("personal_storage", self.char1, "store"),
                                        (None, None, "burn")):
            with self.subTest(operation=operation):
                row = self.charged()
                service.switch(self.char1, row, True, 100)
                if kind:
                    api.move_item_tree(row, location_kind=kind, owner_object=owner, operation=operation)
                    row.refresh_from_db()
                    self.assertFalse(row.state["enabled"])
                else:
                    api.delete_item(row, operation=operation)
                self.assertIsNone(self.char1.db.active_light_item_id)
        row = self.charged()
        service.switch(self.char1, row, True, 100)
        before = self.atomic_state()
        with patch.object(service, "reconcile_locked", side_effect=RuntimeError("참조 실패")):
            with self.assertRaises(RuntimeError):
                api.move_item_tree(row, location_kind="world_loot", owner_object=loot, operation="drop")
            with self.assertRaises(RuntimeError):
                api.delete_item(row, operation="burn")
        self.assertEqual(before, self.atomic_state())

    def test_logout_and_shutdown_settle_off(self):
        for lifecycle in (self.char1.at_post_unpuppet, self.char1.at_server_shutdown):
            with self.subTest(lifecycle=lifecycle.__name__):
                row = self.charged()
                service.switch(self.char1, row, True, 40)
                with patch.object(self.char1.sessions, "count", return_value=0):
                    lifecycle()
                row.refresh_from_db()
                self.assertEqual((row.state["remaining_power"], row.state["enabled"]), (1740, False))
                self.assertIsNone(self.char1.db.active_light_item_id)

    def test_observation_uses_entity_light_and_stale_reference_is_read_only(self):
        row = self.charged()
        service.switch(self.char1, row, True, 100)
        lights = service.lighting_snapshot(self.char1, now=101)
        environment = EnvironmentSnapshot.__new__(EnvironmentSnapshot)
        object.__setattr__(environment, "ambient_light", "dark")
        object.__setattr__(environment, "visibility", "poor")
        sight = observation.observe(environment, self.char1.profile_snapshot(), 101, lights=lights)
        self.assertEqual((sight.effective_light, sight.effective_visibility), ("normal", "clear"))
        self.char1.db.active_light_item_id = "stale-not-uuid"
        self.assertIsNone(service.lighting_snapshot(self.char1, now=101).active)
        service.reconcile(self.char1, 101)
        self.assertIsNone(self.char1.db.active_light_item_id)

    def test_web_light_status_uses_same_labels_as_inventory(self):
        self.connect_character(self.char1)
        first, removed, active = self.create("flashlight"), self.create("flashlight"), self.charged()
        api.delete_item(removed)
        service.switch(self.char1, active, True, 100)
        name = ITEMS["flashlight"]["name"]

        def payload():
            with patch.object(self.char1, "msg") as output, patch("time.time", return_value=280):
                Explorer.push_state(self.char1, observed_at=161)
            return output.call_args.kwargs["pz_state"][0][0]

        state = payload()
        labels = {row["identity"]: row["selector"] for row in state["inventory"] if row["light_source"]}
        self.assertEqual(labels, {str(first.pk): f"{name} 1", str(active.pk): f"{name} 3"})
        light = state["observation"]["light_source"]
        self.assertEqual(light["name"], labels[str(active.pk)])
        self.assertTrue(light["active"])
        self.assertEqual(light["remaining_minutes"], 29)
        active_row = next(row for row in state["inventory"] if row["identity"] == str(active.pk))
        self.assertEqual(active_row["state_summary"], "켜짐 · 90%")
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd("손전등 3 확인")
        self.assertTrue(any(f"{labels[str(active.pk)]}\n상태 켜짐" in str(call.args[0])
                            for call in output.call_args_list if call.args))

        api.delete_item(first)
        state = payload()
        self.assertEqual(state["observation"]["light_source"]["name"], name)
        remaining = next(row for row in state["inventory"] if row["identity"] == str(active.pk))
        self.assertEqual(remaining["selector"], name)
        self.assertEqual(self.char1.db.active_light_item_id, str(active.pk))
        self.assertEqual(number_for("item", active.pk), 3)

    def test_nested_lights_do_not_add_snapshot_queries(self):
        spare, active = self.create("flashlight"), self.charged()
        service.switch(self.char1, active, True, 100)
        root = self.create("guard_carbine")
        middle = api.create_item("guard_carbine", location_kind="inside", parent_item=root, socket="compartment")
        stored = self.create("flashlight")
        api.move_item(stored, location_kind="personal_storage", owner_object=self.char1, operation="store")
        api.create_item("flashlight", location_kind="inventory", owner_object=self.char2)

        def read(profile=None):
            statements = []

            def capture(execute, sql, params, many, context):
                statements.append(sql.lstrip().upper())
                return execute(sql, params, many, context)

            with connection.execute_wrapper(capture):
                snapshot = service.lighting_snapshot(self.char1, profile, now=101)
            self.assertTrue(all(sql.startswith("SELECT") for sql in statements))
            return snapshot, sum(ItemEntity._meta.db_table.upper() in sql for sql in statements), sum(
                SelectionNumber._meta.db_table.upper() in sql for sql in statements)

        api.create_item("flashlight", location_kind="inside", parent_item=middle, socket="first")
        baseline, selects, number_selects = read()
        for index in range(8):
            api.create_item("flashlight", location_kind="inside", parent_item=middle, socket=f"item_{index}")
        updated, updated_selects, updated_number_selects = read()
        self.assertEqual(updated, baseline)
        self.assertEqual(updated_selects, selects)
        self.assertEqual((number_selects, updated_number_selects), (1, 1))
        self.assertEqual([row.identity for row in updated.items], [str(spare.pk), str(active.pk)])
        self.assertEqual((updated.active.identity, updated.active.remaining_power), (str(active.pk), 1799))
        more_lights = [self.create("flashlight") for _ in range(8)]
        updated, updated_selects, updated_number_selects = read()
        self.assertEqual([row.identity for row in updated.items], [str(row.pk) for row in (spare, active, *more_lights)])
        self.assertEqual((updated_selects, updated_number_selects), (selects, 1))
        profile = self.char1.profile_snapshot(with_equipment_display=True, observed_at=101)
        self.assertEqual(read(profile), (updated, selects, 0))

    def test_invalid_flashlight_state_rejected(self):
        row = self.create("flashlight")
        for changes in ({"remaining_power": -1}, {"remaining_power": 1801}, {"enabled": 1},
                        {"enabled": True}, {"power_type": "wrong"}, {"remaining_power": float("nan")}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                api.update_item_state(row, {**row.state, **changes})

    def test_foreign_stale_reference_does_not_switch_off_other_owners_light(self):
        row = self.charged()
        service.switch(self.char1, row, True, 100)
        self.char2.db.active_light_item_id = str(row.pk)
        service.reconcile(self.char2, 200)
        row.refresh_from_db()
        self.assertTrue(row.state["enabled"])
        self.assertEqual(row.state["remaining_power"], 1800)
        self.assertEqual(self.char1.db.active_light_item_id, str(row.pk))
        self.assertIsNone(self.char2.db.active_light_item_id)

    def test_native_commands_resolve_duplicate_light_and_battery(self):
        self.connect_character(self.char1)
        self.create("flashlight")
        second = self.create("flashlight")
        self.create("battery")
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd("손전등 2에 건전지 넣어")
            self.assertIn("광원에 전원 하나를 넣었다.", str(output.call_args_list))
        self.char1.execute_cmd("손전등 2 켜")
        self.assertEqual(self.char1.db.active_light_item_id, str(second.pk))
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd("손전등 2 확인")
            self.assertIn("상태 켜짐", str(output.call_args_list))
        self.char1.execute_cmd("손전등 2 꺼")
        self.assertIsNone(self.char1.db.active_light_item_id)

    def test_legacy_facade_retains_storage_and_never_creates_entities(self):
        self.char1.db.equipment_backend = None
        profile = rules.new_profile()
        profile["inventory"].update(flashlight=1, battery=2)
        self.char1.db.profile = profile
        before = ItemEntity.objects.count()
        service.insert_power(self.char1, "flashlight", "battery", 100)
        service.switch(self.char1, "flashlight", True, 100)
        lights = service.lighting_snapshot(self.char1, now=160)
        self.assertEqual((lights.source, lights.active.remaining_power), ("legacy", 1740))
        self.assertIsNone(lights.active.identity)
        service.switch(self.char1, "flashlight", False, 160)
        self.assertIn("29분", service.status(self.char1, "flashlight", 160))
        self.assertEqual(before, ItemEntity.objects.count())
        self.assertIsNone(self.char1.db.active_light_item_id)
        self.assertEqual(self.char1.profile()["inventory"]["battery"], 1)
        self.assertEqual(ITEMS["battery"]["power_source"]["capacity_seconds"], 1800)
