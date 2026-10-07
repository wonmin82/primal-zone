"""격리 legacy world 변환과 cutover 후 native runtime 회귀."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from unittest.mock import Mock, patch

from django.test import override_settings
from evennia import create_object
from evennia.utils.dbserialize import deserialize
from typeclasses.explorers import Explorer
from typeclasses.interactables import Container
from typeclasses.loot import Corpse, DroppedLoot
from world import item_migration, rules
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemMigrationLedger, ItemRuntime, ItemSequence
from world.item_migration.convert import convert_source
from world.item_migration.scan import json_state, raw_source
from world.item_migration.workflow import migration_context
from world.loot_entities.models import CurrencyLoot, LootClaim

from tests.base import GameCommandTest


class MigrationOfflineGuardTests(GameCommandTest):
    def test_real_session_handler_checks_logged_in_and_unlogged_sessions(self):
        from evennia.server.sessionhandler import SESSIONS
        from world.item_migration.workflow import require_offline

        with TemporaryDirectory() as directory, override_settings(
                ITEM_MIGRATION_TEST_OVERRIDE=False, ITEM_MAINTENANCE=True, GAME_DIR=directory):
            (Path(directory) / "server").mkdir()
            with patch.object(SESSIONS, "get_sessions", return_value=[]) as sessions:
                require_offline()
                sessions.assert_called_once_with(include_unloggedin=True)
            with patch.object(SESSIONS, "get_sessions", return_value=[Mock()]) as sessions:
                with self.assertRaisesRegex(ValueError, "온라인 세션"):
                    require_offline()
                sessions.assert_called_once_with(include_unloggedin=True)


class ItemMigrationTests(GameCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        for character in (self.char1, self.char2):
            character.push_state = Mock()
            character.schedule_recovery = Mock()
        self.enterContext(patch("typeclasses.explorers.delay"))
        self.profile = rules.new_profile()
        self.profile.update(inventory={"blade": 2, "vest": 1, "carbine": 2, "flashlight": 2, "bandage": 4},
                            equipment={"weapon": "blade", "armor": "vest"}, storage={"spear": 1, "battery": 2})
        self.profile["light_sources"] = {"flashlight": {"on": True, "charge_seconds": 1800, "power_source": "battery", "started_at": time() - 120}}
        self.profile["quests"]["radio_tower"]["claimed"] = True
        self.char1.db.profile = deepcopy(self.profile)
        self.container = create_object(Container, key="보관함", location=self.room1)
        self.container.db.items = {"armor": 1, "bandage": 5}
        self.corpse = create_object(Corpse, key="시체", location=self.room1)
        self.corpse.db.entries = [{"kind": "item", "id": "carbine", "quantity": 1, "reserved_player": self.char1.pk,
                                   "assigned_player": self.char1.pk, "protection_until": time() + 120}]
        self.dropped = create_object(DroppedLoot, key="칩", location=self.room1)
        self.dropped.db.entries = [{"kind": "currency", "id": "chips", "quantity": 20, "reserved_player": self.char1.pk,
                                    "eligible_players": [self.char1.pk, self.char2.pk], "remaining_shares": {self.char1.pk: 0, self.char2.pk: 20},
                                    "protection_until": time() + 120}]

    def assert_applied(self):
        report = item_migration.apply()
        self.assertEqual(report["errors"], [])
        self.assertEqual(item_migration.verify()["errors"], [])

    @override_settings(ITEM_MIGRATION_TEST_OVERRIDE=False, ITEM_MAINTENANCE=False)
    def test_apply_and_cutover_require_offline_maintenance(self):
        before = (ItemEntity.objects.count(), ItemMigrationLedger.objects.count(),
                  ItemSequence.objects.get(pk=1).last_value, deserialize(self.char1.db.profile))
        for action in (item_migration.apply, item_migration.cutover):
            with self.subTest(action=action.__name__):
                with self.assertRaisesRegex(ValueError, "ITEM_MAINTENANCE"):
                    action()
                self.assertEqual(before, (ItemEntity.objects.count(), ItemMigrationLedger.objects.count(),
                                          ItemSequence.objects.get(pk=1).last_value, deserialize(self.char1.db.profile)))
                self.assertFalse(ItemRuntime.objects.exists())

    def test_dry_run_is_read_only_and_reports_unknown_and_mismatch(self):
        before = (deserialize(self.char1.db.profile), ItemSequence.objects.get(pk=1).last_value,
                  ItemEntity.objects.count(), ItemMigrationLedger.objects.count(), self.char1.db.equipment_backend)
        report = item_migration.dry_run()
        self.assertEqual(report["errors"], [])
        self.assertEqual(before, (deserialize(self.char1.db.profile), ItemSequence.objects.get(pk=1).last_value,
                                 ItemEntity.objects.count(), ItemMigrationLedger.objects.count(), self.char1.db.equipment_backend))
        self.container.db.items = {"unknown": 1}
        self.assertIn("unknown legacy item", str(item_migration.dry_run()["errors"]))
        api.create_item("bandage", owner_object=self.corpse, location_kind="corpse_loot")
        self.assertIn("marker", str(item_migration.dry_run()["errors"]))

    def test_invalid_flashlight_preflight_is_read_only(self):
        for field, value in (("charge_seconds", -1), ("charge_seconds", float("nan")), ("on", "yes"), ("started_at", -1)):
            profile = deepcopy(self.profile)
            profile["light_sources"]["flashlight"][field] = value
            self.char1.db.profile = profile
            sequence = ItemSequence.objects.get(pk=1).last_value
            with self.subTest(field=field, value=value):
                self.assertIn("invalid legacy flashlight state", str(item_migration.dry_run()["errors"]))
                self.assertEqual(ItemSequence.objects.get(pk=1).last_value, sequence)
                self.assertEqual(ItemMigrationLedger.objects.count(), 0)

    def test_full_world_quantity_tree_light_entitlement_and_retry(self):
        self.assert_applied()
        rows = list(api.items_owned_by(self.char1))
        copies = [row for row in rows if row.definition_id == "cutting_machete"]
        self.assertEqual(len(copies), 2)
        self.assertEqual([row.location_kind for row in copies], ["equipment", "inventory"])
        self.assertEqual(str(copies[0].pk), self.char1.db.active_weapon_item_id)
        firearms = [row for row in rows if row.definition_id == "guard_carbine"]
        self.assertEqual(len(firearms), 2)
        for row in firearms:
            self.assertEqual(row.children.get().state, {"rounds": 20})
        lights = [row for row in rows if row.definition_id == "flashlight"]
        self.assertEqual([row.state["enabled"] for row in lights], [True, False])
        self.assertAlmostEqual(lights[0].state["remaining_power"], 1680, delta=10)
        self.assertEqual(self.char1.db.active_light_item_id, str(lights[0].pk))
        self.assertIn("ridge_predator_mark", {row.definition_id for row in rows})
        self.assertIn("outpost_supply_pass", {row.definition_id for row in rows})
        stored = api.items_in_location("personal_storage", owner_object=self.char1)
        self.assertEqual({row.definition_id for row in stored}, {"pioneer_spear", "battery"})
        self.assertEqual(api.items_in_location("shared_storage", owner_object=self.container).count(), 2)
        loot = api.items_owned_by(self.corpse).get(location_kind="corpse_loot")
        self.assertEqual(loot.children.get().state["rounds"], 20)
        self.assertEqual(LootClaim.objects.get(item_entity=loot).assigned_player_id, self.char1.pk)
        currency = CurrencyLoot.objects.get(owner_object=self.dropped)
        self.assertEqual(list(currency.shares.values_list("remaining_amount", flat=True)), [0, 20])
        before = (json_state(self.char1), ItemSequence.objects.get(pk=1).last_value, ItemMigrationLedger.objects.count())
        self.assertEqual(item_migration.apply()["errors"], [])
        self.assertEqual(before, (json_state(self.char1), ItemSequence.objects.get(pk=1).last_value, ItemMigrationLedger.objects.count()))
        self.assertIsNone(ItemRuntime.objects.filter(version=1).first())
        self.assertEqual(deserialize(self.char1.db.profile), self.profile)

    def test_missing_equipment_recovery_and_source_atomic_failure(self):
        self.profile["inventory"]["blade"] = 0
        self.char1.db.profile = deepcopy(self.profile)
        before = ItemSequence.objects.get(pk=1).last_value
        original = api.create_item
        calls = []

        def fail(*args, **kwargs):
            calls.append(args)
            if len(calls) == 3:
                raise RuntimeError("injected create failure")
            return original(*args, **kwargs)

        with migration_context(), patch.object(api, "create_item", side_effect=fail), self.assertRaises(RuntimeError):
            convert_source("explorer", self.char1, time())
        self.assertEqual(api.items_owned_by(self.char1).count(), 0)
        self.assertEqual(ItemSequence.objects.get(pk=1).last_value, before)
        self.assertEqual(ItemMigrationLedger.objects.count(), 0)
        self.assertIsNone(self.char1.db.equipment_backend)
        self.assert_applied()
        self.assertEqual(api.items_owned_by(self.char1).filter(definition_id="cutting_machete").count(), 1)
        self.assertTrue(ItemMigrationLedger.objects.get(source_kind="explorer", source_identity=self.char1.pk).warnings)
        with self.assertRaises(ValueError):
            item_migration.cutover()
        item_migration.cutover(accept_warnings=True)

    def test_verify_blocks_missing_or_corrupted_completed_source(self):
        self.assertTrue(item_migration.verify()["errors"])
        with self.assertRaises(ValueError):
            item_migration.cutover()
        self.assert_applied()
        item = api.items_owned_by(self.char1).get(definition_id="bandage")
        item.quantity -= 1
        item.save()
        self.assertTrue(item_migration.verify()["errors"])
        self.assertTrue(item_migration.apply()["errors"])
        with self.assertRaises(ValueError):
            item_migration.cutover()

    def test_cutover_native_consumption_storage_discovery_and_archived_blob_unchanged(self):
        self.assert_applied()
        item_migration.cutover()
        from world.item_transfer_native import transfer
        with override_settings(ITEM_MIGRATION_AUDIT=False):
            profile = self.char1.profile()
            self.assertNotIn("blade", profile["inventory"])
            self.assertEqual(profile["inventory"]["cutting_machete"], 2)
            self.char1.change(rules.claim_cache)
            self.assertEqual(api.items_owned_by(self.char1).filter(definition_id="expedition_tag").count(), 1)
            transfer(self.char1, "붕대", container=self.container)
            transfer(self.char1, "붕대", container=self.container, withdraw=True)
            self.char1.change(lambda value: rules.consume(value, "bandage"))
            archived = deserialize(self.char1.db.profile)
            for field in ("inventory", "equipment", "storage", "light_sources"):
                self.assertEqual(archived[field], self.profile[field])
            self.assertEqual(deserialize(self.container.db.items), {"armor": 1, "bandage": 5})
            self.char2.db.equipment_backend = None
            with self.assertRaises(rules.RuleError):
                self.char2.profile()

    def test_native_entitlements_preserve_uuid_and_no_extra_firearm_magazine(self):
        from world.credential_service import grant_credential
        credential = grant_credential(self.char1, "outpost_supply_pass")
        self.assert_applied()
        self.assertEqual(api.items_owned_by(self.char1).get(definition_id="outpost_supply_pass").pk, credential.pk)
        self.assertEqual(api.items_owned_by(self.char1).filter(definition_id="mag_556_standard").count(), 2)

    def test_loot_failure_rolls_back_blob_rights_allocator_and_retry(self):
        original = deserialize(self.corpse.db.entries)
        sequence = ItemSequence.objects.get(pk=1).last_value
        with migration_context(), patch("world.loot_service.LootClaim.save", side_effect=RuntimeError("claim")), self.assertRaises(RuntimeError):
            convert_source("corpse", self.corpse, time())
        self.assertEqual(deserialize(self.corpse.db.entries), original)
        self.assertIsNone(self.corpse.db.loot_backend)
        self.assertFalse(api.items_owned_by(self.corpse).exists())
        self.assertEqual(ItemSequence.objects.get(pk=1).last_value, sequence)
        self.assertFalse(ItemMigrationLedger.objects.exists())
        with migration_context():
            convert_source("corpse", self.corpse, time())
        self.assertTrue(LootClaim.objects.exists())

    def test_currency_failure_is_source_atomic_and_retry_preserves_zero_eligibility(self):
        from world.loot_entities.models import CurrencyLootShare

        original = deserialize(self.dropped.db.entries)
        with migration_context(), patch.object(CurrencyLootShare, "save", side_effect=RuntimeError("share")), self.assertRaises(RuntimeError):
            convert_source("dropped", self.dropped, time())
        self.assertEqual(deserialize(self.dropped.db.entries), original)
        self.assertIsNone(self.dropped.db.loot_backend)
        self.assertFalse(CurrencyLoot.objects.exists())
        with migration_context():
            convert_source("dropped", self.dropped, time())
        self.assertEqual(list(CurrencyLootShare.objects.order_by("player_id").values_list("remaining_amount", flat=True)), [0, 20])

    def test_existing_native_firearm_light_unique_identity_and_state_survive(self):
        from world.firearm_service import create_firearm
        from world.lighting_service import switch

        self.char2.db.profile = {**rules.new_profile(), "inventory": {}, "equipment": {}, "storage": {}, "light_sources": {}}
        self.char2.db.equipment_backend = "item_entities"
        firearm = create_firearm("guard_carbine", owner_object=self.char2, mode="partial", rounds=3)
        magazine = firearm.children.get()
        light = api.create_item("flashlight", owner_object=self.char2, location_kind="inventory",
                                state={"power_type": "flashlight_battery", "remaining_power": 600, "enabled": False, "started_at": None})
        switch(self.char2, light, True, now=time())
        light.refresh_from_db()
        identity = (firearm.pk, firearm.sequence, magazine.pk, magazine.sequence, light.pk, light.state.copy())
        self.assert_applied()
        firearm.refresh_from_db()
        light.refresh_from_db()
        self.assertEqual(identity, (firearm.pk, firearm.sequence, firearm.children.get().pk, magazine.sequence, light.pk, light.state))
        self.assertEqual(firearm.children.get().state, {"rounds": 3})

    def test_both_claimed_entitlements_and_old_flat_quest_flags(self):
        self.profile["quests"]["deep_jungle"]["claimed"] = True
        self.char1.db.profile = self.profile
        second = rules.new_profile()
        second.pop("quests")
        second.update(version=3, quest_claimed=True)
        self.char2.db.profile = second
        self.assert_applied()
        self.assertTrue({"ridge_predator_mark", "predator_scale_charm", "outpost_supply_pass", "special_supply_pass"} <= set(api.items_owned_by(self.char1).values_list("definition_id", flat=True)))
        self.assertTrue(api.items_owned_by(self.char2).filter(definition_id="ridge_predator_mark").exists())

    def test_pre_v4_cache_claimed_entitlement_is_read_only_and_retry_safe(self):
        old = rules.new_profile()
        old.pop("quests")
        old.pop("discoveries")
        old.update(version=3, cache_claimed=True, quest_started=True, record_read=True,
                   generator_fixed=True, boss_defeated=True, quest_claimed=True)
        self.char2.db.profile = deepcopy(old)
        normalized = rules.migrate_profile(old)
        raw = raw_source("explorer", self.char2)
        self.assertEqual(raw["quests"], normalized["quests"])
        self.assertEqual(raw["discoveries"], normalized["discoveries"])
        before = (deserialize(self.char2.db.profile), json_state(self.char2),
                  ItemSequence.objects.get(pk=1).last_value, list(ItemMigrationLedger.objects.values()))
        report = item_migration.dry_run()
        self.assertEqual(report["errors"], [])
        source = next(row for row in report["sources"] if row["identity"] == self.char2.pk)
        self.assertEqual(source["entitlement_grants"], {"expedition_tag": 1})
        self.assertEqual(before, (deserialize(self.char2.db.profile), json_state(self.char2),
                                 ItemSequence.objects.get(pk=1).last_value, list(ItemMigrationLedger.objects.values())))
        self.assert_applied()
        tag = api.items_owned_by(self.char2).get(definition_id="expedition_tag")
        self.assertEqual(tag.quantity, 1)
        self.assertEqual(deserialize(self.char2.db.profile), old)
        state = (json_state(self.char2), ItemSequence.objects.get(pk=1).last_value,
                 list(ItemMigrationLedger.objects.order_by("pk").values()))
        self.assertEqual(item_migration.apply()["errors"], [])
        self.assertEqual(state, (json_state(self.char2), ItemSequence.objects.get(pk=1).last_value,
                                list(ItemMigrationLedger.objects.order_by("pk").values())))
        old["cache_claimed"] = False
        self.char2.db.profile = old
        self.assertIn("digest", str(item_migration.verify()["errors"]))

    def test_pre_v4_cache_preserves_other_discoveries_and_existing_tag(self):
        old = rules.new_profile()
        old.pop("quests")
        old.update(version=3, cache_claimed=True, discoveries={"jungle_cache": True})
        self.char2.db.profile = deepcopy(old)
        tag = api.create_item("expedition_tag", owner_object=self.char2, location_kind="inventory")
        identity = (tag.pk, tag.sequence)
        raw = raw_source("explorer", self.char2)
        self.assertEqual(raw["discoveries"], {"supply_cache": True, "jungle_cache": True})
        self.assertEqual(raw["discoveries"], rules.migrate_profile(old)["discoveries"])
        source = next(row for row in item_migration.dry_run()["sources"] if row["identity"] == self.char2.pk)
        self.assertNotIn("expedition_tag", source["entitlement_grants"])
        self.assert_applied()
        current = api.items_owned_by(self.char2).get(definition_id="expedition_tag")
        self.assertEqual((current.pk, current.sequence), identity)
        self.assertEqual(api.items_owned_by(self.char2).filter(definition_id="mental_stability_module").count(), 1)

    def test_pre_v4_unclaimed_cache_does_not_grant_tag(self):
        old = rules.new_profile()
        old.pop("quests")
        old.pop("discoveries")
        old.update(version=3, cache_claimed=False)
        self.char2.db.profile = old
        source = next(row for row in item_migration.dry_run()["sources"] if row["identity"] == self.char2.pk)
        self.assertNotIn("expedition_tag", source["entitlement_grants"])
        self.assert_applied()
        self.assertFalse(api.items_owned_by(self.char2).filter(definition_id="expedition_tag").exists())

    def test_independent_quantity_audit_rejects_matching_but_wrong_snapshot(self):
        self.assert_applied()
        row = api.items_owned_by(self.char1).get(definition_id="bandage")
        row.quantity += 1
        row.save()
        record = ItemMigrationLedger.objects.get(source_kind="explorer", source_identity=self.char1.pk)
        record.expected_state = json_state(self.char1)
        record.save()
        self.assertIn("root 수량", str(item_migration.verify()["errors"]))

    def test_fresh_player_is_native_without_legacy_item_fields(self):
        self.assert_applied()
        item_migration.cutover()
        with override_settings(ITEM_MIGRATION_AUDIT=False):
            fresh = create_object(Explorer, key="신규 탐사자", location=self.room1)
            fresh.push_state = Mock()
            saved = deserialize(fresh.db.profile)
            self.assertFalse({"inventory", "equipment", "storage", "light_sources"} & saved.keys())
            self.assertEqual(fresh.db.equipment_backend, "item_entities")
            rows = list(api.items_owned_by(fresh))
            self.assertEqual([(row.definition_id, row.location_kind, row.quantity) for row in rows],
                             [("explorer_machete", "equipment", 1), ("expedition_workwear", "equipment", 1), ("bandage", "inventory", 3)])
            self.assertIsNotNone(fresh.db.active_weapon_item_id)

    def test_precutover_fail_fast_and_maintenance_guard(self):
        from world.item_migration.workflow import require_offline

        with override_settings(ITEM_MIGRATION_AUDIT=False), self.assertRaises(rules.RuleError):
            self.char1.profile()
        with override_settings(ITEM_MIGRATION_TEST_OVERRIDE=False, ITEM_MAINTENANCE=False), self.assertRaises(ValueError):
            require_offline()
        self.assertIsNone(ItemRuntime.objects.filter(version=1).first())

    def test_existing_phase2_native_ids_are_mapped_without_reissuing_identity(self):
        from world.content import ITEMS

        self.char2.db.profile = {**rules.new_profile(), "inventory": {}, "equipment": {}, "storage": {}, "light_sources": {}}
        self.char2.db.equipment_backend = "item_entities"
        with patch.dict(ITEMS, {"machete": {**ITEMS["explorer_machete"], "name": "낡은마체테"}, "vest": {**ITEMS["expedition_workwear"], "name": "탐사조끼"}}):
            weapon = api.create_item("machete", owner_object=self.char2, location_kind="equipment", slot="hands")
            armor = api.create_item("vest", owner_object=self.char2, location_kind="equipment", slot="body")
        ids = (weapon.pk, weapon.sequence, armor.pk, armor.sequence)
        self.assert_applied()
        weapon.refresh_from_db()
        armor.refresh_from_db()
        self.assertEqual(ids, (weapon.pk, weapon.sequence, armor.pk, armor.sequence))
        self.assertEqual((weapon.definition_id, armor.definition_id), ("explorer_machete", "expedition_workwear"))

    def test_multiple_legacy_on_lights_choose_first_and_preserve_other_power(self):
        from world.content import ITEMS

        profile = deepcopy(self.profile)
        profile["inventory"]["backup_light"] = 1
        profile["light_sources"]["backup_light"] = {"on": True, "charge_seconds": 1800,
                                                   "power_source": "battery", "started_at": time() - 60}
        self.char1.db.profile = profile
        with patch.dict(ITEMS, {"backup_light": {**ITEMS["flashlight"], "name": "예비광원", "aliases": []}}):
            self.assertIn("복수 ON", str(item_migration.dry_run()["sources"]))
            self.assert_applied()
            row = api.items_owned_by(self.char1).get(definition_id="backup_light")
            self.assertFalse(row.state["enabled"])
            self.assertIsNone(row.state["started_at"])
            self.assertAlmostEqual(row.state["remaining_power"], 1740, delta=10)
            self.assertEqual(api.items_owned_by(self.char1).get(pk=self.char1.db.active_light_item_id).definition_id, "flashlight")

    def test_existing_boss_unique_in_legacy_owner_scope_is_preserved(self):
        row = api.create_item("ridge_predator_mark", owner_object=self.char1, location_kind="personal_storage")
        identity, sequence = row.pk, row.sequence
        self.assert_applied()
        row.refresh_from_db()
        self.assertEqual((row.pk, row.sequence, row.location_kind), (identity, sequence, "personal_storage"))
        self.assertEqual(api.items_owned_by(self.char1).filter(definition_id="ridge_predator_mark").count(), 1)


    def test_repair_entitlement_fills_owner_tree_preserves_scrap_and_is_idempotent(self):
        shared = create_object(Container, key="별도 공용 부품함", location=self.room1)
        api.create_item("generator_repair_part", quantity=3, location_kind="shared_storage", owner_object=shared)
        for amount, location, fixed in ((0, "inventory", False), (1, "personal_storage", False),
                                        (2, "inside", False), (3, "inventory", False), (0, "inventory", True)):
            with self.subTest(amount=amount, location=location, fixed=fixed):
                player = create_object(Explorer, key=f"진행보정{amount}{location}{fixed}", location=self.room1)
                player.push_state = Mock()
                profile = rules.new_profile()
                profile["inventory"]["scrap"] = 20
                profile["quests"]["radio_tower"]["generator_fixed"] = fixed
                player.db.profile = profile
                if amount:
                    if location == "inside":
                        # owner tree 기준이며 child의 직접 owner FK는 없다.
                        parent = api.create_item("outpost_supply_pass", location_kind="inventory", owner_object=player)
                        api.create_item("generator_repair_part", quantity=amount, location_kind="inside", parent_item=parent, socket="payload")
                    else:
                        api.create_item("generator_repair_part", quantity=amount, location_kind=location, owner_object=player)
                with migration_context():
                    convert_source("explorer", player, time())
                    rows = api.items_owned_by(player)
                    self.assertEqual(sum(row.quantity for row in rows if row.definition_id == "generator_repair_part"), 0 if fixed else 3)
                    self.assertEqual(sum(row.quantity for row in rows if row.definition_id == "scrap"), 20)
                    before = (json_state(player), ItemSequence.objects.get(pk=1).last_value)
                    self.assertTrue(convert_source("explorer", player, time())["skipped"])
                    self.assertEqual(before, (json_state(player), ItemSequence.objects.get(pk=1).last_value))
        self.assert_applied()

    def test_fixed_discovery_entitlements_use_whole_owner_scope_and_digest(self):
        self.profile["discoveries"].update(supply_cache=True, jungle_cache=True)
        self.char1.db.profile = self.profile
        tag = api.create_item("expedition_tag", location_kind="personal_storage", owner_object=self.char1)
        identity = (tag.pk, tag.sequence)
        before = (ItemSequence.objects.get(pk=1).last_value, ItemMigrationLedger.objects.count(), json_state(self.char1))
        plan = next(row for row in item_migration.dry_run()["sources"] if row["identity"] == self.char1.pk)
        self.assertEqual(plan["entitlement_grants"], {"generator_repair_part": 3, "mental_stability_module": 1})
        self.assertEqual(before, (ItemSequence.objects.get(pk=1).last_value, ItemMigrationLedger.objects.count(), json_state(self.char1)))
        self.assert_applied()
        tag.refresh_from_db()
        self.assertEqual((tag.pk, tag.sequence), identity)
        for definition in ("expedition_tag", "mental_stability_module"):
            self.assertEqual(api.items_owned_by(self.char1).filter(definition_id=definition).count(), 1)
        self.assertFalse(api.items_owned_by(self.char2).filter(definition_id__in=("expedition_tag", "mental_stability_module")).exists())
        state = (json_state(self.char1), ItemSequence.objects.get(pk=1).last_value)
        self.assertEqual(item_migration.apply()["errors"], [])
        self.assertEqual(state, (json_state(self.char1), ItemSequence.objects.get(pk=1).last_value))
        self.profile["discoveries"]["jungle_cache"] = False
        self.char1.db.profile = self.profile
        self.assertIn("digest", str(item_migration.verify()["errors"]))

    def test_fixed_rewards_missing_and_inventory_existing_are_not_duplicated(self):
        self.profile["discoveries"].update(supply_cache=True, jungle_cache=True)
        self.char1.db.profile = self.profile
        module = api.create_item("mental_stability_module", location_kind="inventory", owner_object=self.char1)
        second = deserialize(self.char2.db.profile)
        second["discoveries"]["supply_cache"] = True
        self.char2.db.profile = second
        existing_tag = api.create_item("expedition_tag", location_kind="inventory", owner_object=self.char2)
        self.assert_applied()
        self.assertEqual(api.items_owned_by(self.char2).get(definition_id="expedition_tag").pk, existing_tag.pk)
        self.assertEqual(api.items_owned_by(self.char1).filter(definition_id="expedition_tag").count(), 1)
        self.assertEqual(api.items_owned_by(self.char1).get(definition_id="mental_stability_module").pk, module.pk)
        record = ItemMigrationLedger.objects.get(source_kind="explorer", source_identity=self.char1.pk)
        api.delete_item(api.items_owned_by(self.char1).get(definition_id="expedition_tag"))
        record.expected_state = json_state(self.char1)
        record.save()
        self.assertIn("entitlement missing", str(item_migration.verify()["errors"]))

    def test_new_entitlement_failure_rolls_back_source_and_sequence_then_retries(self):
        self.profile["discoveries"]["supply_cache"] = True
        self.char1.db.profile = self.profile
        before = (json_state(self.char1), deserialize(self.char1.db.profile), ItemSequence.objects.get(pk=1).last_value)
        original = api.create_item
        def fail(identity, **kwargs):
            if identity == "expedition_tag":
                self.assertEqual(sum(row.quantity for row in api.items_owned_by(self.char1) if row.definition_id == "generator_repair_part"), 3)
                raise RuntimeError("fixed entitlement failure")
            return original(identity, **kwargs)
        with migration_context(), patch.object(api, "create_item", side_effect=fail), self.assertRaises(RuntimeError):
            convert_source("explorer", self.char1, time())
        self.assertEqual(before, (json_state(self.char1), deserialize(self.char1.db.profile), ItemSequence.objects.get(pk=1).last_value))
        self.assertFalse(ItemMigrationLedger.objects.filter(source_identity=self.char1.pk).exists())
        self.assert_applied()

    def test_repair_verify_and_completed_fixed_warning_do_not_delete_items(self):
        self.profile["quests"]["radio_tower"]["generator_fixed"] = True
        self.char1.db.profile = self.profile
        row = api.create_item("generator_repair_part", quantity=1, owner_object=self.char1, location_kind="inventory")
        report = item_migration.dry_run()
        self.assertIn("수리 완료", str(report))
        self.assert_applied()
        self.assertEqual(api.items_owned_by(self.char1).get(pk=row.pk).quantity, 1)
        record = ItemMigrationLedger.objects.get(source_kind="explorer", source_identity=self.char2.pk)
        part = api.items_owned_by(self.char2).get(definition_id="generator_repair_part")
        api.delete_item(part)
        record.expected_state = json_state(self.char2)
        record.save()
        self.assertIn("entitlement missing", str(item_migration.verify()["errors"]))
