"""Phase 2의 장비 instance·참조·자원 경계를 격리 DB에서 검증한다."""

from copy import deepcopy
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from typeclasses.explorers import Explorer
from world import equipment as eq
from world import equipment_service as service
from world import presentation, recovery, rules
from world.content import ITEMS
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence
from world.multiplayer import world_change

from tests.base import GameCommandTest


class EquipmentEntityTests(GameCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.clock = self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.enterContext(patch("typeclasses.explorers.delay"))
        for character in (self.char1, self.char2):
            character.push_state = Mock()
            profile = rules.new_profile()
            profile.update(inventory={}, equipment={"weapon": None, "armor": None},
                           hp=30, mental=20, recovery=recovery.initialize(100))
            character.db.profile = profile
            service.use_item_entities(character)

    def definition(self, identity, slot="hands", role="weapon", hands=1, modifiers=(), **extra):
        properties = {"slot": slot}
        if slot == "hands":
            properties.update(role=role, hands_required=hands)
            if role == "weapon":
                properties.update(weapon_type="melee", weapon_attack=4)
        properties.update(extra)
        definition = {**deepcopy(ITEMS["explorer_machete"]), "name": identity, "aliases": [],
                      "equipment_properties": properties, "modifiers": list(modifiers)}
        self.enterContext(patch.dict(ITEMS, {identity: definition}))
        return definition

    def create(self, identity, **kwargs):
        return api.create_item(identity, location_kind="inventory", owner_object=self.char1, **kwargs)

    def state(self):
        return (list(ItemEntity.objects.order_by("sequence").values()),
                self.char1.db.active_weapon_item_id, dict(self.char1.profile()),
                ItemSequence.objects.get(pk=1).last_value)

    def test_all_final_slots_and_ring_capacity(self):
        for slot in eq.SLOT_CAPACITY:
            self.definition(slot, slot)
            service.equip_item(self.char1, self.create(slot))
        self.assertEqual(service.hand_usage(self.char1), 1)
        second = self.create("ring")
        service.equip_item(self.char1, second)
        third = self.create("ring")
        before = self.state()
        with self.assertRaises(rules.RuleError):
            service.equip_item(self.char1, third)
        self.assertEqual(before, self.state())
        self.assertEqual(service.equipped_items(self.char1).filter(slot="ring").count(), 2)

    def test_hand_combinations_and_no_replacement(self):
        cases = [("weapon", "weapon", 1, True), ("weapon", "shield", 1, True),
                 ("weapon", "offhand", 1, True), ("shield", "shield", 1, False),
                 ("offhand", "offhand", 1, False), ("shield", "offhand", 1, False),
                 ("weapon", "weapon", 2, False), ("weapon", "shield", 2, False),
                 ("weapon", "offhand", 2, False)]
        for index, (first_role, second_role, hands, allowed) in enumerate(cases):
            with self.subTest(case=index), world_change():
                for row in list(service.equipped_items(self.char1)):
                    service.unequip_item(self.char1, row)
                self.definition(f"first{index}", role=first_role, hands=hands)
                self.definition(f"second{index}", role=second_role)
                first, second = self.create(f"first{index}"), self.create(f"second{index}")
                service.equip_item(self.char1, first)
                before = self.state()
                if allowed:
                    service.equip_item(self.char1, second)
                    self.assertEqual(service.hand_usage(self.char1), 2)
                else:
                    with self.assertRaises(rules.RuleError):
                        service.equip_item(self.char1, second)
                    self.assertEqual(before, self.state())
                first.refresh_from_db()
                self.assertEqual(first.location_kind, "equipment")

    def test_active_weapon_uuid_selection_and_successor(self):
        self.definition("weapon")
        first, second = self.create("weapon"), self.create("weapon")
        service.equip_item(self.char1, first)
        self.assertEqual(self.char1.db.active_weapon_item_id, str(first.pk))
        service.equip_item(self.char1, second)
        self.assertEqual(service.active_weapon_item(self.char1).pk, first.pk)
        self.assertEqual(rules.stats(self.char1.profile())["weapon_attack"], 4)
        service.set_active_weapon(self.char1, second)
        self.assertEqual(service.active_weapon_item(self.char1).pk, second.pk)
        active = service.active_weapon(self.char1)
        self.assertIsInstance(active, eq.EquipmentItem)
        self.assertEqual(active.identity, str(second.pk))
        self.assertEqual(active.weapon_type, "melee")
        self.assertEqual(service.hand_usage(self.char1), 2)
        service.unequip_item(self.char1, second)
        self.assertEqual(service.active_weapon_item(self.char1).pk, first.pk)
        service.unequip_item(self.char1, first)
        self.assertIsNone(service.active_weapon(self.char1))
        self.assertIsNone(service.active_weapon_item(self.char1))
        self.assertIsNone(self.char1.db.active_weapon_item_id)

    def test_duplicate_selector_is_stable_across_equipment_location(self):
        self.definition("ring", "ring")
        first, second = self.create("ring"), self.create("ring")
        for row, selector in ((first, "ring"), (second, "ring 2")):
            self.assertEqual(service.resolve_item(self.char1, selector, "착용").pk, row.pk)
            service.equip_item(self.char1, row)
        self.assertEqual(service.resolve_item(self.char1, "ring 2", "벗어").pk, second.pk)
        rows = eq.inventory_rows(self.char1.profile())
        self.assertEqual([row["selector"] for row in rows], ["ring", "ring 2"])
        with self.assertRaises(rules.RuleError):
            service.resolve_item(self.char1, str(first.pk), "벗어")
        self.assertNotIn(str(first.pk), str(rows))
        self.assertEqual(ItemEntity.objects.count(), 2)

    def test_nested_equip_and_unequip_keep_passive_child(self):
        self.definition("root", weapon_type="firearm")
        ITEMS["root"]["firearm_family"] = "pistol_9mm"
        self.enterContext(patch.dict(ITEMS, {"child": deepcopy(ITEMS["mag_9_standard"])}))
        ITEMS["child"]["operation_policy"].update(equip=False, unequip=False)
        root = self.create("root")
        child = api.create_item("child", location_kind="inside", parent_item=root, socket="magazine")
        original = (child.parent_item_id, child.socket, child.sequence)
        for operation in (service.equip_item, service.unequip_item):
            operation(self.char1, root)
            child.refresh_from_db()
            self.assertEqual((child.location_kind, child.parent_item_id, child.socket, child.sequence),
                             ("inside", *original))

    def test_equipment_modifiers_scopes_and_secondary_passive(self):
        self.definition("weapon", modifiers=[
            {"target": "stat.attack", "op": "add", "value": 2, "scope": "equipped"},
            {"target": "weapon.attack", "op": "multiply", "value": 2, "scope": "active_weapon"}])
        for _ in range(2):
            service.equip_item(self.char1, self.create("weapon"))
        values = rules.stats(self.char1.profile())
        self.assertEqual(values["character_attack"], 11)
        self.assertEqual(values["weapon_attack"], 8)
        self.assertEqual(values["attack"], 19)

    def test_max_resources_do_not_heal_and_removal_clamps(self):
        self.definition("cap", "head", modifiers=[
            {"target": "stat.max_hp", "op": "add", "value": 20, "scope": "equipped"},
            {"target": "stat.max_mental", "op": "add", "value": 20, "scope": "equipped"}])
        item = self.create("cap")
        service.equip_item(self.char1, item)
        profile = self.char1.profile()
        self.assertEqual((profile["hp"], profile["mental"]), (30, 20))
        self.assertEqual((rules.stats(profile)["max_hp"], rules.stats(profile)["max_mental"]), (80, 60))
        profile.update(hp=75, mental=55)
        self.char1.save_profile(profile)
        service.unequip_item(self.char1, item)
        self.assertEqual((self.char1.profile()["hp"], self.char1.profile()["mental"]), (60, 40))

    def test_recovery_boundary_uses_old_rate_then_new_rate(self):
        self.definition("recovery", "neck", modifiers=[
            {"target": "recovery.hp_per_minute", "op": "add", "value": 60, "scope": "equipped"},
            {"target": "recovery.mental_per_minute", "op": "add", "value": 60, "scope": "equipped"}])
        self.clock.return_value = 130
        item = self.create("recovery")
        service.equip_item(self.char1, item)
        profile = self.char1.profile()
        self.assertEqual((profile["hp"], profile["mental"]), (31, 23))
        self.clock.return_value = 140
        self.char1.reconcile_recovery(140)
        profile = self.char1.profile()
        self.assertEqual((profile["hp"], profile["mental"]), (42, 34))
        self.assertEqual(recovery.player_rates(rules.stats(profile), snapshot=eq.context(profile)),
                         {"hp": 63, "mental": 66})

    def test_external_move_and_delete_reconcile_in_same_transaction(self):
        self.definition("weapon")
        first, second = self.create("weapon"), self.create("weapon")
        for row in (first, second):
            service.equip_item(self.char1, row)
        api.move_item_tree(first, location_kind="inventory", owner_object=self.char1, operation="unequip")
        self.assertEqual(self.char1.db.active_weapon_item_id, str(second.pk))
        api.delete_item(second, operation="burn")
        self.assertIsNone(self.char1.db.active_weapon_item_id)

    def test_reconcile_failure_rolls_back_move_delete_and_resources(self):
        self.definition("weapon")
        item = self.create("weapon")
        service.equip_item(self.char1, item)
        self.clock.return_value = 130
        for action in (lambda: api.move_item_tree(item, location_kind="inventory", owner_object=self.char1, operation="unequip"),
                       lambda: api.delete_item(item, operation="burn")):
            before = self.state()
            with patch.object(service, "reconcile_references", side_effect=RuntimeError("fixture")):
                with self.assertRaises(RuntimeError):
                    action()
            self.assertEqual(before, self.state())

    def test_invalid_active_ownership_and_modifier_are_atomic(self):
        self.definition("weapon")
        item = self.create("weapon")
        for action in (lambda: service.set_active_weapon(self.char1, item),
                       lambda: service.equip_item(self.char2, item)):
            before = self.state()
            with self.assertRaises(rules.RuleError):
                action()
            self.assertEqual(before, self.state())
        ITEMS["weapon"]["modifiers"] = [{"target": "unknown", "op": "add", "value": 1, "scope": "equipped"}]
        with self.assertRaises((rules.RuleError, ValidationError)):
            service.equip_item(self.char1, item)
        self.assertEqual(item.location_kind, "inventory")

    def test_stale_active_reference_is_not_treated_as_equipped_weapon(self):
        self.definition("weapon")
        item = self.create("weapon")
        self.char1.db.active_weapon_item_id = str(item.pk)
        self.assertIsNone(service.active_weapon(self.char1))
        self.assertIsNone(service.active_weapon_item(self.char1))
        self.assertEqual(rules.stats(self.char1.profile())["weapon_attack"], 0)
        service.equip_item(self.char1, item)
        self.assertEqual(service.active_weapon_item(self.char1).pk, item.pk)

    def test_legacy_mapping_and_single_write_boundary(self):
        self.char2.db.equipment_backend = None
        self.char2.db.profile = rules.new_profile()
        before_rows = list(ItemEntity.objects.values())
        before_profile = dict(self.char2.profile())
        active = service.active_weapon(self.char2)
        self.assertIsInstance(active, eq.EquipmentItem)
        self.assertEqual(active.definition_id, "explorer_machete")
        self.assertEqual(active.weapon_type, "melee")
        self.assertIsNone(active.identity)
        self.assertIsNone(service.active_weapon_item(self.char2))
        self.assertEqual(service.hand_usage(self.char2), 1)
        self.assertEqual(service.active_weapon(self.char2, before_profile), active)
        self.assertEqual(service.hand_usage(self.char2, before_profile), 1)
        self.assertEqual(before_profile, dict(self.char2.profile()))
        self.assertIsNone(self.char2.db.active_weapon_item_id)
        self.assertIn("탐사용 벌목도 [주무기]", presentation.status(self.char2.key, self.char2.profile()))
        service.unequip_item(self.char2, "explorer_machete", "weapon")
        self.assertIsNone(service.active_weapon(self.char2))
        self.assertEqual(service.hand_usage(self.char2), 0)
        service.equip_item(self.char2, "explorer_machete", "weapon")
        snapshot = eq.context(self.char2.profile())
        self.assertEqual([(item.slot, item.role) for item in snapshot.items], [("hands", "weapon"), ("body", None)])
        self.assertEqual(before_rows, list(ItemEntity.objects.values()))
        self.definition("weapon")
        legacy_fields = deepcopy(self.char1.profile()["equipment"])
        service.equip_item(self.char1, self.create("weapon"))
        self.assertEqual(self.char1.profile()["equipment"], legacy_fields)
        with self.assertRaises(rules.RuleError):
            service.use_item_entities(self.char2)

    def test_command_selector_and_presentation_agree_with_web(self):
        self.definition("weapon")
        first, second = self.create("weapon"), self.create("weapon")
        self.char1.execute_cmd("weapon 무장")
        self.char1.execute_cmd("weapon 2 무장")
        self.char1.execute_cmd("weapon 2 주무기")
        self.assertEqual(service.active_weapon_item(self.char1).pk, second.pk)
        profile = self.char1.profile()
        for output in (presentation.status(self.char1.key, profile),
                       presentation.equipment(profile), presentation.inventory(profile)):
            self.assertIn("weapon 2", output)
            self.assertNotIn("weapon [주무기]", output)
            self.assertEqual(output.count("[주무기]"), 1)
            self.assertNotIn(str(second.pk), output)
        self.assertIn("weapon 2 [주무기]", presentation.status(self.char1.key, profile))
        self.assertIn("weapon 2 [주무기]", presentation.equipment(profile))
        self.assertIn("weapon 2×1 [착용] [주무기]", presentation.inventory(profile))
        self.char1.execute_cmd("weapon 2 해제")
        self.assertEqual(service.active_weapon_item(self.char1).pk, first.pk)
        self.assertIn("weapon [주무기]", str(eq.equipment_rows(self.char1.profile())))

    def test_outer_world_change_rollback_includes_reference(self):
        self.definition("weapon")
        item = self.create("weapon")
        before = self.state()
        with self.assertRaises(RuntimeError), world_change():
            service.equip_item(self.char1, item)
            raise RuntimeError("fixture")
        self.assertEqual(before, self.state())
        with self.assertRaises(ValidationError):
            api.move_item_tree(item, location_kind="equipment", owner_object=self.char1, slot="hands",
                               operation="equip", expected_source=("inventory", self.char2.pk))
        self.assertEqual(before, self.state())

    def test_external_give_drop_store_keep_source_reference_consistent(self):
        from evennia import create_object
        from typeclasses.loot import DroppedLoot

        self.definition("weapon")
        ground = create_object(DroppedLoot, key="격리 바닥")
        for operation, location, owner in (("give", "inventory", self.char2),
                                          ("store", "personal_storage", self.char1),
                                          ("drop", "world_loot", ground)):
            with self.subTest(operation=operation):
                row = self.create("weapon")
                service.equip_item(self.char1, row)
                api.move_item_tree(row, location_kind=location, owner_object=owner, operation=operation)
                self.assertIsNone(self.char1.db.active_weapon_item_id)

    def test_failed_command_at_recovery_boundary_has_no_partial_resource_change(self):
        self.definition("weapon")
        for _ in range(2):
            service.equip_item(self.char1, self.create("weapon"))
        self.create("weapon")
        self.clock.return_value = 130
        before = self.state()
        self.char1.execute_cmd("weapon 3 무장")
        self.assertEqual(before, self.state())

    def test_plain_profile_save_and_read_keep_equipment_max_and_schema(self):
        from evennia.utils.dbserialize import deserialize

        self.definition("cap", "head", modifiers=[
            {"target": "stat.max_hp", "op": "add", "value": 20, "scope": "equipped"}])
        service.equip_item(self.char1, self.create("cap"))
        profile = dict(self.char1.profile())
        profile["hp"] = 75
        self.char1.save_profile(profile)
        self.assertEqual(self.char1.profile_snapshot()["hp"], 75)
        saved = deserialize(self.char1.db.profile)
        self.assertNotIsInstance(saved, eq.EquipmentProfile)
        self.assertNotIn("equipment_context", saved)
        self.assertEqual(saved["version"], 11)

    def test_web_payload_uses_instance_labels_and_active_snapshot(self):
        self.definition("weapon")
        for _ in range(2):
            service.equip_item(self.char1, self.create("weapon"))
        second = service.resolve_item(self.char1, "weapon 2", "주무기")
        service.set_active_weapon(self.char1, second)
        with patch.object(self.char1.sessions, "count", return_value=1), patch.object(self.char1, "msg") as message:
            Explorer.push_state(self.char1)
        state = message.call_args.kwargs["pz_state"][0][0]
        self.assertEqual([row["selector"] for row in state["inventory"]], ["weapon", "weapon 2"])
        self.assertEqual(state["equipment"]["hands"], "weapon · weapon 2 [주무기]")
        self.assertEqual([row["active_weapon"] for row in state["inventory"]], [False, True])
