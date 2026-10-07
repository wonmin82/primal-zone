"""실제 일반 설정에서의 타이머와 fixture DB 접근 차단."""

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from django.conf import settings
from evennia import create_object, create_script, search_tag
from typeclasses.loot import Corpse
from typeclasses.scripts import WorldLifecycle
from world import environment, multiplayer
from world.bootstrap import build_world
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence
from world.loot_service import populate_source
from world.timing import PRODUCTION_TIMING, configured_timings

from tests.item_entity_fixture import NativeItemTest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.smoke_setup import setup  # noqa: E402
from scripts.smoke_snapshot import snapshot  # noqa: E402


class SmokeInfrastructureTests(TestCase):
    def test_normal_test_settings_keep_production_gameplay_timers(self):
        self.assertEqual(configured_timings(settings), PRODUCTION_TIMING)
        self.assertEqual({key: getattr(multiplayer, key) for key in PRODUCTION_TIMING}, PRODUCTION_TIMING)
        self.assertFalse(getattr(settings, "PRIMAL_SMOKE", False))

    def test_fixture_refuses_normal_settings_before_django_setup_or_migrate(self):
        with patch("django.setup") as initialize, patch("django.core.management.call_command") as command:
            with self.assertRaisesRegex(RuntimeError, "marker"):
                setup([])
            initialize.assert_not_called()
            command.assert_not_called()


class NativeSmokeSnapshotTests(NativeItemTest):
    def test_checkpoint_reads_native_storage_equipment_and_loot_without_archive_fallback(self):
        rooms = build_world()
        script = create_script(WorldLifecycle, autostart=False)
        script.db.environment = environment.new_environment(100)
        self.char1.location = rooms["grass"]
        box = search_tag("shared_container", category="primal_interactable")[0]
        shared = api.create_item("bandage", quantity=2, location_kind="shared_storage", owner_object=box)
        personal = api.create_item("water", quantity=1, location_kind="personal_storage", owner_object=self.char1)
        equipment = api.create_item("explorer_machete", location_kind="equipment",
                                    owner_object=self.char1, slot="hands")
        corpse = create_object(Corpse, key="smoke 시체", location=rooms["grass"])
        populate_source(corpse, [{"kind": "item", "id": "bandage", "quantity": 3},
                                 {"kind": "currency", "id": "credits", "quantity": 8}])
        self.assertFalse(box.db.items)
        self.assertFalse(corpse.db.entries)
        before = (list(ItemEntity.objects.order_by("sequence").values()),
                  ItemSequence.objects.get(pk=1).last_value)
        with patch("server.conf.smoke_support.require_smoke"), patch("django.setup"), patch("evennia._init"):
            saved = snapshot()
        self.assertEqual(saved["box"][str(shared.pk)]["quantity"], 2)
        owned = saved["players"][self.char1.key]["items"]
        self.assertEqual(owned[str(personal.pk)]["location"], "personal_storage")
        self.assertEqual(owned[str(equipment.pk)]["location"], "equipment")
        self.assertEqual({(entry["kind"], entry["id"], entry["quantity"])
                          for entry in saved["loot"][str(corpse.pk)]["entries"]},
                         {("item", "bandage", 3), ("currency", "credits", 8)})
        self.assertEqual(before, (list(ItemEntity.objects.order_by("sequence").values()),
                                  ItemSequence.objects.get(pk=1).last_value))
