"""CLI와 공유하는 canonical corpus의 의미·원자성·guard 회귀."""

import sys
from pathlib import Path

from django.test import override_settings
from evennia import create_object
from typeclasses.explorers import Explorer
from world import item_migration
from world.bootstrap import build_world
from world.content.item_mapping import LEGACY_ITEM_MAPPING
from world.item_entities import api
from world.item_entities.models import ItemMigrationLedger, ItemRuntime, ItemSequence
from world.item_migration.scan import raw_source

from tests.item_entity_fixture import NativeItemTest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.phase7b_fixture import alter_corpus, build_corpus, inspect  # noqa: E402


@override_settings(ITEM_MIGRATION_AUDIT=True, ITEM_MIGRATION_TEST_OVERRIDE=True)
class CanonicalLegacyCorpusTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        rooms = build_world()
        self.char1.key, self.char2.key = "검증가", "검증나"
        for name in ("검증다", "검증라"):
            create_object(Explorer, key=name, location=rooms["staging_room"])

    def test_valid_corpus_all_mappings_entitlements_and_preservation(self):
        before = build_corpus("valid")
        self.assertEqual(item_migration.dry_run()["errors"], [])
        self.assertEqual(inspect(), before)
        self.assertEqual(item_migration.apply()["errors"], [])
        applied = inspect()
        self.assertEqual(item_migration.verify()["errors"], [])
        self.assertEqual(item_migration.apply()["errors"], [])
        self.assertEqual(inspect(), applied)
        items = [row for source in applied["sources"].values() for row in source["native"]["items"]]
        self.assertTrue(set(LEGACY_ITEM_MAPPING.values()) <= {row["definition"] for row in items})
        first = applied["players"]["검증가"]["native"]["items"]
        blades = [row for row in first if row["definition"] == "cutting_machete"]
        self.assertEqual(len(blades), 2)
        self.assertEqual([row["location"] for row in blades], ["equipment", "inventory"])
        self.assertEqual(sum(row["quantity"] for row in first if row["definition"] == "generator_repair_part"), 3)
        for name in ("검증나", "검증다", "보존검증"):
            existing = {row["id"]: row for row in before["players"][name]["native"]["items"]}
            restored = {row["id"]: row for row in applied["players"][name]["native"]["items"]}
            self.assertEqual(existing, {identity: restored[identity] for identity in existing})
        old = Explorer.objects.get(db_key="구형탐사")
        self.assertEqual(raw_source("explorer", old)["discoveries"], {"supply_cache": True, "jungle_cache": True})
        self.assertEqual(set(api.items_owned_by(old).values_list("definition_id", flat=True)),
                         {"expedition_tag", "mental_stability_module"})
        self.assertEqual(old.db.profile["version"], 3)
        item_migration.cutover()
        self.assertEqual(ItemRuntime.objects.get(pk=1).version, 1)

    def test_warning_corpus_requires_explicit_acceptance(self):
        build_corpus("warning")
        report = item_migration.dry_run()
        self.assertIn("장착 수량 누락", str(report))
        self.assertEqual(item_migration.apply()["errors"], [])
        self.assertEqual(item_migration.verify()["errors"], [])
        before = inspect()
        with self.assertRaisesRegex(ValueError, "warning"):
            item_migration.cutover()
        self.assertEqual(inspect(), before)
        item_migration.cutover(accept_warnings=True)
        self.assertEqual(ItemRuntime.objects.get(pk=1).version, 1)

    def test_invalid_source_is_atomic_other_sources_skip_and_retry(self):
        before = build_corpus("invalid")
        self.assertIn("unknown", str(item_migration.dry_run()["errors"]))
        self.assertEqual(inspect(), before)
        result = item_migration.apply()
        self.assertIn("unknown", str(result["errors"]))
        failed = Explorer.objects.get(db_key="검증라")
        self.assertFalse(api.items_owned_by(failed).exists())
        self.assertFalse(ItemMigrationLedger.objects.filter(source_identity=failed.pk).exists())
        applied = inspect()
        item_migration.apply()
        self.assertEqual(inspect(), applied)
        with self.assertRaises(ValueError):
            item_migration.cutover()
        self.assertEqual(ItemRuntime.objects.get(pk=1).version, 0)
        alter_corpus("repair-invalid")
        self.assertEqual(item_migration.apply()["errors"], [])
        self.assertEqual(item_migration.verify()["errors"], [])
        retried = inspect()
        for key, source in applied["sources"].items():
            if source["key"] != "검증라":
                self.assertEqual(retried["sources"][key]["native"], source["native"])

    def test_corruption_is_read_only_detected_and_blocks_cutover(self):
        build_corpus("valid")
        self.assertEqual(item_migration.apply()["errors"], [])
        alter_corpus("corrupt")
        before = inspect()
        self.assertTrue(item_migration.verify()["errors"])
        self.assertEqual(inspect(), before)
        with self.assertRaises(ValueError):
            item_migration.cutover()
        self.assertEqual(inspect(), before)
        alter_corpus("restore")
        self.assertEqual(item_migration.verify()["errors"], [])
        self.assertEqual(ItemSequence.objects.get(pk=1).last_value, before["sequence"])
