"""실제 일반 설정에서의 타이머와 fixture DB 접근 차단."""

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from evennia import create_object, create_script, search_tag
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse
from typeclasses.scripts import WorldLifecycle
from world import environment, equipment_service, multiplayer, recovery, rules
from world.bootstrap import build_world
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence
from world.loot_service import populate_source
from world.timing import PRODUCTION_TIMING, configured_timings

from tests.base import clear_test_caches

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


class NativeSmokeSnapshotTests(TransactionTestCase):
    """standalone snapshot과 같이 외부 atomic 없이 실제 DB를 읽는 fixture."""

    def tearDown(self):
        clear_test_caches()
        super().tearDown()

    def test_checkpoint_reads_native_storage_equipment_and_loot_without_archive_fallback(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.enterContext(patch("typeclasses.explorers.delay"))
        self.enterContext(patch("world.lighting_service.time", return_value=100))
        rooms = build_world()
        script = create_script(WorldLifecycle, autostart=False)
        script.db.environment = environment.new_environment(100)
        self.char1 = create_object(Explorer, key="smoke 탐사자", location=rooms["grass"], home=rooms["grass"])
        self.char1.push_state = Mock()
        profile = rules.new_profile()
        profile.update(inventory={}, equipment={"weapon": None, "armor": None},
                       hp=30, mental=20, recovery=recovery.initialize(100))
        self.char1.db.profile = profile
        equipment_service.use_item_entities(self.char1)
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
        self.assertTrue(connection.get_autocommit())
        self.assertFalse(connection.in_atomic_block)
        with patch("server.conf.smoke_support.require_smoke"), patch("django.setup"), patch("evennia._init"):
            saved = snapshot()
        self.assertTrue(connection.get_autocommit())
        self.assertFalse(connection.in_atomic_block)
        self.assertEqual(saved["box"][str(shared.pk)]["quantity"], 2)
        owned = saved["players"][self.char1.key]["items"]
        self.assertEqual(owned[str(personal.pk)]["location"], "personal_storage")
        self.assertEqual(owned[str(equipment.pk)]["location"], "equipment")
        self.assertEqual({(entry["kind"], entry["id"], entry["quantity"])
                          for entry in saved["loot"][str(corpse.pk)]["entries"]},
                         {("item", "bandage", 3), ("currency", "credits", 8)})
        self.assertEqual(before, (list(ItemEntity.objects.order_by("sequence").values()),
                                  ItemSequence.objects.get(pk=1).last_value))


from tests.item_entity_fixture import NativeItemTest  # noqa: E402


class SmokeLootBirthObserverTests(NativeItemTest):
    """실제 격리 test DB의 죽음·생성·ledger rollback 경계를 검증한다."""

    def setUp(self):
        super().setUp()
        from server.conf.smoke_startstop import install_observer
        from typeclasses import loot
        from typeclasses.enemies import Enemy, room_enemies

        self.rooms = build_world()
        from world.item_entities.models import ItemRuntime
        ItemRuntime.objects.update_or_create(pk=1, defaults={"version": 1})
        for char in (self.char1, self.char2):
            char.db.item_runtime_version = 1
            char.location = self.rooms["grass"]
        self.enemy = room_enemies(self.rooms["grass"])[0]
        self.enterContext(patch("typeclasses.enemies.delay"))
        self.enterContext(patch("typeclasses.loot.delay"))
        self.enterContext(patch.object(Enemy, "_finish_death", Enemy._finish_death))
        self.enterContext(patch.object(loot, "build_entries", loot.build_entries))
        with patch("server.conf.smoke_support.require_smoke"), self.settings(PRIMAL_SMOKE_MODE="full"):
            install_observer()

    def death(self):
        from random import Random
        self.enemy.engage(self.char1, now=100)
        self.enemy.db.hp = 1
        self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))

    def test_actual_native_death_observed_once_with_exact_rows(self):
        from evennia.utils.dbserialize import deserialize
        from server.conf.smoke_startstop import owned_loot

        self.death()
        corpse = Corpse.objects.all().get()
        events = deserialize(self.enemy.db.smoke_loot_births)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], {"at": 102.5, "source_id": str(corpse.pk), "source": owned_loot(corpse)})
        self.assertTrue(events[0]["source"]["currency"])
        self.enemy.finish_death(self.char1, now=103)
        self.assertEqual(deserialize(self.enemy.db.smoke_loot_births), events)

    def test_duplicate_creation_inside_death_is_rejected_and_rolled_back(self):
        from world.loot_service import populate_source as actual_populate
        original_count = ItemEntity.objects.count()

        from world.loot_service import create_currency
        for field in ("item", "currency"):
            def duplicated(source, entries):
                actual_populate(source, entries)
                if field == "item":
                    api.create_item("bandage", quantity=1, location_kind="corpse_loot", owner_object=source)
                else:
                    create_currency(source, 1)

            with self.subTest(field=field), patch("world.loot_service.populate_source", side_effect=duplicated):
                with self.assertRaisesRegex(AssertionError, "생성 계약"):
                    self.death()
            self.assertFalse(Corpse.objects.all().exists())
            self.assertEqual(ItemEntity.objects.count(), original_count)
            self.assertFalse(self.enemy.db.smoke_loot_births)
            self.assertEqual(self.enemy.db.state, "alive")

    def test_outer_rollback_removes_assets_and_ledger_together(self):
        from world.multiplayer import world_change
        original_count = ItemEntity.objects.count()
        with self.assertRaisesRegex(RuntimeError, "rollback"), world_change():
            self.death()
            self.assertTrue(self.enemy.db.smoke_loot_births)
            raise RuntimeError("rollback")
        self.assertFalse(Corpse.objects.all().exists())
        self.assertEqual(ItemEntity.objects.count(), original_count)
        self.assertFalse(self.enemy.db.smoke_loot_births)

    def test_observer_refuses_non_smoke_before_installing(self):
        from server.conf.smoke_startstop import install_observer
        with self.assertRaisesRegex(RuntimeError, "marker"):
            install_observer()

    def test_firearm_child_and_zero_share_contract_is_exact(self):
        from copy import deepcopy

        from server.conf.smoke_startstop import assert_generated_tree, entry_contract, owned_loot
        source = create_object(Corpse, key="선언 생성", location=self.rooms["grass"])
        entries = [{"kind": "item", "id": "guard_carbine", "quantity": 1,
                    "acquisition": {"mode": "partial", "magazine_definition": "magazine_556", "rounds": 3}}]
        from world.content import ITEMS
        from world.firearm_service import STANDARD_MAGAZINES
        family = ITEMS["guard_carbine"]["firearm_family"]
        entries[0]["acquisition"]["magazine_definition"] = STANDARD_MAGAZINES[family]
        populate_source(source, entries)
        saved = owned_loot(source)
        assert_generated_tree(entries, saved)
        child = next(identity for identity, row in saved["items"].items() if row["parent"])
        for mutation in ("duplicate", "rounds"):
            changed = deepcopy(saved)
            if mutation == "duplicate":
                changed["items"]["extra-child"] = deepcopy(changed["items"][child])
            else:
                changed["items"][child]["state"]["rounds"] += 1
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                assert_generated_tree(entries, changed)
        currency = {"kind": "currency", "id": "credits", "quantity": 1,
                    "eligible_players": [self.char1.pk, self.char2.pk],
                    "remaining_shares": {self.char1.pk: 1}}
        changed = deepcopy(currency)
        changed["eligible_players"].remove(self.char2.pk)
        self.assertNotEqual(entry_contract([currency]), entry_contract([changed]))
