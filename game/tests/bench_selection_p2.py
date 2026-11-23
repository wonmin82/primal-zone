"""잔여 P2 격리 실측. scripts/dev.py test tests.bench_selection_p2 --parallel 1."""

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from itertools import count
from json import dumps
from re import compile as compile_regex
from statistics import median
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

from django.db import connection
from evennia import create_object
from typeclasses.interactables import Container, PersonalLocker
from world import firearm_service, item_transfer_native
from world.actions.manifest import get_index
from world.actions.presentation import action_controls, reference_json
from world.actions.resolver import dispatch_text
from world.equipment_service import equip_item
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.selection_numbers.api import descriptor, number_for
from world.selection_numbers.models import SelectionNumber

from tests.item_entity_fixture import NativeItemTest

NOW = 100
COUNTS = (1, 10, 100)
SAMPLES = 5
ITEM_TABLE = ItemEntity._meta.db_table.upper()
B1_TABLE = SelectionNumber._meta.db_table.upper()
ITEM_ID_LOOKUP = compile_regex(rf'"{ITEM_TABLE}"\."ID"\s*=\s*%S')


class SelectionP2Benchmark(NativeItemTest):
    def setUp(self):
        super().setUp()
        identities = count(1)
        self.enterContext(patch.object(ItemEntity._meta.pk, "_get_default",
                                       new=lambda: UUID(int=next(identities))))
        self.index = get_index()

    def measure(self, scenario, size, read):
        expected = read()
        durations = []
        for _ in range(SAMPLES):
            start = perf_counter()
            value = read()
            durations.append((perf_counter() - start) * 1000)
            self.assertEqual(value, expected)

        queries = Counter()
        by_pk = Counter()
        policy_depth = 0

        def count_sql(execute, sql, params, many, context):
            statement = sql.strip().upper()
            queries["sql"] += 1
            if policy_depth:
                queries["policy_sql"] += 1
            if statement.startswith("SELECT"):
                if B1_TABLE in statement:
                    queries["b1_select"] += 1
                if ITEM_TABLE in statement:
                    queries["item_select"] += 1
                    if ITEM_ID_LOOKUP.search(statement.partition(" WHERE ")[2]):
                        by_pk[tuple(params or ())] += 1
            elif statement.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
                queries["writes"] += 1
            return execute(sql, params, many, context)

        transfer_policy = item_transfer_native.require_ownership_transfer

        def check_transfer(item, destination):
            nonlocal policy_depth
            policy_depth += 1
            try:
                return transfer_policy(item, destination)
            finally:
                policy_depth -= 1

        with (connection.execute_wrapper(count_sql),
              patch.object(item_transfer_native, "require_ownership_transfer", side_effect=check_transfer)):
            actual = read()
        self.assertEqual(actual, expected)
        self.assertEqual(queries["writes"], 0)
        payload = actual if isinstance(actual, list) else asdict(actual)
        print("SELECTION_P2_BENCH " + dumps({
            "scenario": scenario, "count": size, "median_ms": round(median(durations), 3),
            "controls": len(actual) if isinstance(actual, list) else None,
            "selected_uuid": None if isinstance(actual, list) else dict(actual.roles)["subject"][0].identity,
            "payload_sha256": sha256(dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            **{name: queries[name] for name in ("sql", "item_select", "b1_select", "policy_sql", "writes")},
            "item_pk_select": sum(by_pk.values()),
            "repeated_item_pk_select": sum(calls - 1 for calls in by_pk.values()),
        }, sort_keys=True), flush=True)
        return actual

    def test_equipment_and_text_default(self):
        gun = equip_item(self.char1, firearm_service.create_firearm(
            "guard_carbine", owner_object=self.char1, mode="partial", rounds=5,
        ))
        inserted = firearm_service.loaded_magazine_item(gun)
        rows = []
        for size in COUNTS:
            rows.extend(self.create("bandage", quantity=2) for _ in range(size - len(rows)))
            original = rows[0]
            if size == 10:
                # 실물 순서상 첫 후보를 방출했다가 다시 소지하여 영속 번호 순서와 어긋나게 한다.
                api.move_item_tree(original, location_kind="inventory", owner_object=self.char2)
                original = api.move_item_tree(original, location_kind="inventory", owner_object=self.char1)
                rows[0] = original
                self.assertGreater(number_for(descriptor(original).reference),
                                   number_for(descriptor(rows[1]).reference))
            controls = self.measure("equipment", size, lambda: action_controls(self.char1, self.index, NOW))
            information = [row["action"] for row in controls
                           if row["action"]["action_id"] == "item.bandage.information"]
            self.assertEqual({action["roles"]["subject"][0]["identity"] for action in information},
                             {str(item.pk) for item in rows})
            self.assertTrue(any(row["action"]["action_id"].startswith("item.inside_information.")
                                and row["action"]["roles"]["subject"] == [reference_json(descriptor(inserted).reference)]
                                for row in controls))
            result = self.measure(
                "text_default", size, lambda: dispatch_text(self.char1, self.index, "game.information", "붕대", "정보"),
            )
            self.assertEqual(dict(result.roles)["subject"], (descriptor(original).reference,))

    def test_storage_paths(self):
        room = self.char1.location
        locker = create_object(PersonalLocker, key="개인 보관함", location=room)
        box = create_object(Container, key="공용 보관함", location=room)
        inventory, personal, shared = [], [], []
        for size in COUNTS:
            for _ in range(size - len(inventory)):
                inventory.append(self.create("bandage", quantity=2))
                personal.append(api.create_item("bandage", quantity=2, location_kind="personal_storage",
                                                owner_object=self.char1))
                shared.append(api.create_item("bandage", quantity=2, location_kind="shared_storage", owner_object=box))
            for scenario, provider, verb, candidates in (
                ("personal_store", locker, "넣어", inventory),
                ("shared_store", box, "넣어", inventory),
                ("personal_retrieve", locker, "꺼내", personal),
                ("shared_retrieve", box, "꺼내", shared),
            ):
                self.measure_storage(scenario, size, provider, verb, candidates)

            restricted = self.create("generator_repair_part")
            self.measure_storage("mixed_policy_store", size, box, "넣어", inventory)
            api.delete_item(restricted)

    def measure_storage(self, scenario, size, provider, verb, candidates):
        reference = descriptor(provider).reference
        controls = self.measure(scenario, size, lambda: action_controls(
            self.char1, self.index, NOW, provider_reference=reference, verb_key=verb,
        ))
        expected = Counter((str(item.pk), quantity) for item in candidates for quantity in ("1", "모두"))
        actual = Counter((row["action"]["roles"]["subject"][0]["identity"],
                          row["action"]["arguments"]["count"]) for row in controls)
        self.assertEqual(actual, expected)
        self.assertTrue(all(row["action"]["roles"]["provider"] == [reference_json(reference)] for row in controls))
