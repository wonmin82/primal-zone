"""#112 실측: scripts/dev.py test tests.bench_firearm_presentation --parallel 1."""

from collections import Counter
from hashlib import sha256
from itertools import count
from json import dumps
from statistics import median
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

from django.db import connection
from django.test import override_settings
from world import firearm_service
from world.actions import collections, resolver
from world.actions.manifest import get_index
from world.actions.presentation import action_controls
from world.content import ITEMS
from world.item_entities.models import ItemEntity
from world.selection_numbers import api as selection
from world.selection_numbers.models import SelectionNumber

from tests.item_entity_fixture import NativeItemTest

NOW = 100
COUNTS = (1, 10, 100)
SAMPLES = 5


@override_settings(ACTION_CONTENT_PACKAGES=("world.actions.item_shared_content", "world.actions.firearm_lighting_content"))
class FirearmPresentationBenchmark(NativeItemTest):
    def setUp(self):
        super().setUp()
        identities = count(1)
        self.enterContext(patch.object(ItemEntity._meta.pk, "_get_default",
                                       new=lambda: UUID(int=next(identities))))
        self.index = get_index()

    def measure(self, name, size, provider=None):
        def read():
            return action_controls(self.char1, self.index, NOW, provider_reference=provider)

        expected = read()
        durations = []
        for _ in range(SAMPLES):
            start = perf_counter()
            rows = read()
            durations.append((perf_counter() - start) * 1000)
            self.assertEqual(rows, expected)

        sql_counts = Counter()
        scope_reads = Counter()

        def count_sql(execute, sql, params, many, context):
            statement = sql.lstrip().upper()
            sql_counts["all"] += 1
            if statement.startswith("SELECT"):
                if SelectionNumber._meta.db_table.upper() in statement:
                    sql_counts["b1"] += 1
                    scope_reads[(sql, tuple(params or ()))] += 1
                if ItemEntity._meta.db_table.upper() in statement:
                    sql_counts["item"] += 1
            elif statement.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
                sql_counts["writes"] += 1
            return execute(sql, params, many, context)

        with (connection.execute_wrapper(count_sql),
              patch.object(resolver, "role_records", wraps=resolver.role_records) as roles,
              patch.object(firearm_service, "firearm_snapshot", wraps=firearm_service.firearm_snapshot) as firearms,
              patch.object(firearm_service, "magazine_snapshot", wraps=firearm_service.magazine_snapshot) as mags,
              patch.object(firearm_service, "compatible_magazines", wraps=firearm_service.compatible_magazines) as compatible,
              patch.object(collections, "inventory_version", wraps=collections.inventory_version) as versions):
            counted = read()

        self.assertEqual(counted, expected)
        self.assertEqual(sql_counts["writes"], 0)
        digest = sha256(dumps(expected, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        print("FIREARM_BENCH " + dumps({
            "scenario": name, "count": size, "controls": len(expected), "payload_sha256": digest,
            "median_ms": round(median(durations), 3), "sql": sql_counts["all"],
            "b1_select": sql_counts["b1"], "item_select": sql_counts["item"],
            "repeated_b1_select": sum(repetitions - 1 for repetitions in scope_reads.values()),
            "role_records": roles.call_count, "firearm_snapshot": firearms.call_count,
            "magazine_snapshot": mags.call_count, "compatible_magazines": compatible.call_count,
            "inventory_version": versions.call_count,
        }, sort_keys=True), flush=True)
        return expected

    def assert_sources(self, rows, action_id, provider, sources):
        actual = [row["action"]["roles"]["source"][0] for row in rows
                  if row["action"]["action_id"] == action_id
                  and row["action"]["roles"]["provider"][0]["identity"] == str(provider.pk)]
        ref_objects = {selection.descriptor(source).reference for source in sources}
        self.assertEqual({(ref["kind"], ref["identity"], ref["scope_id"]) for ref in actual},
                         {(ref.kind, ref.identity, ref.scope_id) for ref in ref_objects})

    def test_one_firearm_with_candidate_growth(self):
        gun = firearm_service.create_firearm("guard_carbine", owner_object=self.char1, mode="empty")
        inserted = firearm_service.loaded_magazine_item(gun)
        capacity = ITEMS["mag_556_standard"]["magazine"]["capacity"]
        magazines = []
        ammo = []
        for size in COUNTS:
            for n in range(len(magazines), size):
                magazines.append(self.create("mag_556_standard", state={"rounds": n % capacity + 1}))
                ammo.append(self.create("ammo_556", quantity=n % 20 + 1))
            rows = self.measure("one_firearm", size, selection.descriptor(gun).reference)
            self.assert_sources(rows, "item_ops.load", gun, [inserted, *magazines])
            self.assert_sources(rows, "item_ops.inside_ammo_insert", gun, ammo)
            recommended = [row["action"]["roles"]["source"][0]["identity"] for row in rows
                           if row["label"].endswith(" · 재장전")]
            best = max(magazines, key=lambda row: (row.state["rounds"], -row.sequence))
            self.assertEqual(recommended, [str(best.pk)])
            fill = [row["action"] for row in rows if row["action"]["action_id"] == "item_ops.inside_fill"]
            self.assertEqual(len(fill), 1)
            self.assertEqual(fill[0]["roles"]["subject"][0]["identity"], str(inserted.pk))
            self.assertEqual(fill[0]["roles"]["source"][0], {
                "kind": "inventory", "identity": str(self.char1.pk), "scope_id": f"inventory:{self.char1.pk}",
            })
            definitions = tuple(identity for identity, data in ITEMS.items() if data.get("ammo_type") == "556mm")
            self.assertEqual(fill[0]["arguments"]["snapshot"], collections.inventory_version(self.char1, definitions)[0])

    def test_full_screen_with_candidate_growth(self):
        gun = firearm_service.create_firearm("guard_carbine", owner_object=self.char1, mode="partial", rounds=5)
        other_gun = firearm_service.create_firearm("guard_carbine", owner_object=self.char1)
        light = self.create("flashlight")
        second_light = self.create("flashlight")
        # 탄창도 Provider가 되므로 탄약과 탄창의 교차 곱을 억제하여 후보 비용을 따로 관찰한다.
        magazine = self.create("mag_556_standard", state={"rounds": 12})
        self.create("mag_9_standard", state={"rounds": 3})
        ammo, batteries = [], []
        for size in COUNTS:
            for n in range(len(ammo), size):
                ammo.append(self.create("ammo_556", quantity=n % 20 + 1))
                batteries.append(self.create("battery", quantity=n % 5 + 1))
            rows = self.measure("full_screen", size)
            self.assert_sources(rows, "item_ops.inside_ammo_insert", gun, ammo)
            self.assert_sources(rows, "item_ops.load", other_gun, [magazine])
            for provider in (light, second_light):
                self.assert_sources(rows, "item_ops.power_insert", provider, batteries)
