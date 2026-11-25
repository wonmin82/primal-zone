"""Selection v1.5의 격리 DB 실측. scripts/dev.py test tests.bench_selection_phase2 --parallel 1."""

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from itertools import count as integers
from json import dumps
from statistics import median
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

from django.db import connection
from django.test.utils import CaptureQueriesContext
from evennia import create_object
from evennia.objects.models import ObjectDB
from typeclasses.exits import Exit
from typeclasses.interactables import PersonalLocker
from typeclasses.loot import Corpse, DroppedLoot
from typeclasses.zone_rooms import ZoneRoom
from world import loot_service
from world.actions.global_actions import select_look_reference
from world.actions.loot_presentation import source_controls
from world.actions.manifest import get_index
from world.actions.presentation import action_controls
from world.actions.resolver import dispatch_text
from world.actions.schema import ReferenceKind
from world.actors.spawn import create_actor
from world.content import ENEMIES
from world.door_entities.models import Door, DoorInstallation
from world.equipment_service import entity_snapshot, equip_item, resolve_item
from world.item_entities.api import create_item
from world.item_entities.models import ItemEntity
from world.selection_display import room_snapshot
from world.selection_numbers.api import descriptor, number_for
from world.selection_numbers.models import SelectionNumber
from world.state import multiplayer_state
from world.targets import exact_selector, parse_exact_selector

from tests.item_entity_fixture import NativeItemTest

COUNTS = (1, 10, 100)
SAMPLES = 5
NOW = 100


class SelectionPhase2Benchmark(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.room = self.char1.location
        self.index = get_index()
        self.b1_counts = {}
        self.enterContext(patch("typeclasses.loot.delay"))
        self.enterContext(patch("world.actions.loot_resolution.time", return_value=NOW))

    def measure(self, name, count, read, *, reconciles=False):
        read()
        durations = []
        for _ in range(SAMPLES):
            begin = perf_counter()
            read()
            durations.append((perf_counter() - begin) * 1000)
        statements = []

        def count_sql(execute, sql, params, many, context):
            statements.append(sql.strip().upper())
            return execute(sql, params, many, context)

        with connection.execute_wrapper(count_sql):
            value = read()
        b1_queries = sum(sql.startswith("SELECT") and SelectionNumber._meta.db_table.upper() in sql
                         for sql in statements)
        writes = sum(sql.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")) for sql in statements)
        self.assertEqual(b1_queries, self.b1_counts.setdefault(name, b1_queries), name)
        if not reconciles:
            self.assertEqual(writes, 0, name)
        print(dumps({
            "path": name, "objects": count, "samples": SAMPLES,
            "median_ms": round(median(durations), 3), "sql": len(statements),
            "b1_select": b1_queries, "writes": writes,
        }), flush=True)
        return value

    def test_assigned_loot_display(self):
        identities = integers(1)
        self.enterContext(patch.object(ItemEntity._meta.pk, "_get_default",
                                       new=lambda: UUID(int=next(identities))))
        self.enterContext(patch("django.core.signing.TimestampSigner.timestamp", return_value="1xViBB"))
        self.enterContext(patch("world.actions.loot_resolution.token_hex", return_value="a" * 32))
        source = create_object(Corpse, key="배정 전리품 계측", location=self.room)
        source.db.decay_at = NOW + 100
        loot_service.populate_source(source, [])
        items = []
        for size in COUNTS:
            for _ in range(len(items), size):
                item = create_item("ammo_9", quantity=2, location_kind="corpse_loot", owner_object=source)
                loot_service.create_claim(item, reserved_player=self.char1, assigned_player=self.char1,
                                          protection_until=NOW + 1)
                items.append(item)
            for observed_at in (NOW, NOW + 1):
                self.measure_assigned_loot(source, items, observed_at)
            self.measure_assigned_loot(source, items, NOW, text=True)

    def measure_assigned_loot(self, source, items, observed_at, *, text=False):
        def read():
            if text:
                return asdict(dispatch_text(self.char1, self.index, "game.take", "모든 시체에서 모두", "가져"))
            return source_controls(self.char1, observed_at)

        expected = read()
        durations = []
        for _ in range(SAMPLES):
            begin = perf_counter()
            actual = read()
            durations.append((perf_counter() - begin) * 1000)
            self.assertEqual(actual, expected)

        queries = Counter()
        object_lookups = Counter()

        def count_sql(execute, sql, params, many, context):
            statement = sql.lstrip().upper()
            queries["sql"] += 1
            if statement.startswith("SELECT"):
                if ObjectDB._meta.db_table.upper() in statement:
                    queries["object_select"] += 1
                    if tuple(params or ()) == (self.char1.pk,):
                        object_lookups[sql] += 1
                if SelectionNumber._meta.db_table.upper() in statement:
                    queries["b1_select"] += 1
                if ItemEntity._meta.db_table.upper() in statement:
                    queries["item_select"] += 1
            elif statement.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
                queries["writes"] += 1
            return execute(sql, params, many, context)

        with connection.execute_wrapper(count_sql):
            actual = read()
        self.assertEqual(actual, expected)
        self.assertEqual(queries["writes"], 0)
        if text:
            roles = dict(actual["roles"])
            self.assertEqual(tuple(ref["identity"] for ref in roles["source"]), (str(source.pk),))
            self.assertEqual([ref["identity"] for ref in roles["subject"]], [str(item.pk) for item in items])
        else:
            rows = actual[source.pk]["loot"]
            self.assertEqual(len(rows), len(items))
            for row, item in zip(rows, items, strict=True):
                self.assertEqual(row["assigned_name"], self.char1.key)
                self.assertEqual(row["protected"], observed_at == NOW)
                self.assertEqual(row["action"]["roles"]["subject"][0]["identity"], str(item.pk))
        print("ASSIGNED_LOOT_BENCH " + dumps({
            "scope": "protected" if observed_at == NOW else "expired",
            "surface": "text" if text else "display",
            "objects": len(items), "samples": SAMPLES, "selected": len(items),
            "median_ms": round(median(durations), 3),
            "payload_sha256": sha256(dumps(actual, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "sql": queries["sql"], "object_select": queries["object_select"],
            "b1_select": queries["b1_select"], "item_select": queries["item_select"],
            "writes": queries["writes"],
            "single_recipient_select": sum(object_lookups.values()),
            "repeated_recipient_select": sum(n - 1 for n in object_lookups.values()),
        }, sort_keys=True), flush=True)

    def test_room_snapshot_and_actor_door_display(self):
        # 정적 정의만 fixture로 교체하고 실제 Door·설치 이력·출구를 조회한다.
        definitions = {}
        self.enterContext(patch("world.doors.DOORS", definitions))
        first = create_object(ZoneRoom, key="측정 A", attributes=[("zone_id", "bench_a")],
                              tags=[("bench_a", "primal_zone_room")])
        second = create_object(ZoneRoom, key="측정 B", attributes=[("zone_id", "bench_b")],
                               tags=[("bench_b", "primal_zone_room")])
        self.char1.location = first
        enemy_id = next(iter(ENEMIES))
        enemies, npcs, doors = [], [], []
        for count in COUNTS:
            for n in range(len(doors), count):
                enemy = create_actor(enemy_id, first)
                npc = create_actor("commander", first)
                left = self.create_door(n, definitions, first, second)
                enemies.append(enemy.pk)
                npcs.append(npc.pk)
                doors.append(left.pk)
            snapshot = self.measure("room_snapshot", count, lambda: room_snapshot(self.char1, NOW))
            self.assertTrue(all(snapshot.references[pk].kind == ReferenceKind.ACTOR for pk in (*enemies, *npcs)))
            self.assertTrue(all(snapshot.references[pk].kind == ReferenceKind.DOOR for pk in doors))
            state = self.measure("enemy_npc_door_web_display", count, lambda: multiplayer_state(self.char1, NOW),
                                 reconciles=True)
            self.assertEqual(len(state["enemies"]), count)
            self.assertEqual({row["id"]: row["label"] for row in state["enemies"]},
                             {pk: snapshot.labels[pk] for pk in enemies})
            references = {row["look_action"]["roles"]["subject"][0]["identity"]: row["label"]
                          for row in state["interactables"]}
            for pk in (*npcs, *doors):
                self.assertEqual(references[str(pk)], snapshot.labels[pk])

    def create_door(self, ordinal, definitions, first, second):
        identity = f"bench_{ordinal}"
        starts = ((first, f"정문 {ordinal}", second), (second, f"후문 {ordinal}", first))
        endpoints = tuple((origin.db.zone_id, direction, target.db.zone_id) for origin, direction, target in starts)
        definitions[identity] = {"name": "실측 문", "aliases": [], "endpoints": endpoints,
                                 "lockable": False, "key_id": "", "inside_room_id": ""}
        exits = [
            create_object(Exit, key=direction, location=origin, destination=target,
                          attributes=[("door_id", identity)],
                          tags=[(f"{origin.db.zone_id}:{direction}", "primal_zone_exit")])
            for origin, direction, target in starts
        ]
        door = Door.objects.create(door_id=identity, name="실측 문", room_a="bench_a", room_b="bench_b",
                                   exit_a=exits[0], exit_b=exits[1], direction_a=exits[0].key,
                                   direction_b=exits[1].key, state="CLOSED")
        DoorInstallation.objects.create(
            door_id=identity, door_pk=door.pk, installed_at=NOW,
            endpoints=[{"exit_pk": obj.pk, "room_pk": obj.db_location_id, "target_pk": obj.db_destination_id}
                       for obj in exits],
        )
        return exits[0]

    def test_exact_door_look(self):
        definitions = {}
        self.enterContext(patch("world.doors.DOORS", definitions))
        first = create_object(ZoneRoom, key="인용 계측 A", attributes=[("zone_id", "bench_a")],
                              tags=[("bench_a", "primal_zone_room")])
        second = create_object(ZoneRoom, key="인용 계측 B", attributes=[("zone_id", "bench_b")],
                               tags=[("bench_b", "primal_zone_room")])
        self.char1.location = first
        endpoints = []
        for size in COUNTS:
            endpoints.extend(self.create_door(n, definitions, first, second)
                             for n in range(len(endpoints), size))
            target = endpoints[-1]
            expected = descriptor(target).reference
            selector = parse_exact_selector(exact_selector("문", number_for(expected)))

            def read():
                return select_look_reference(self.char1, selector, NOW)

            self.assertEqual(self.measure("exact_door_look", size, read), (expected, target))
            with CaptureQueriesContext(connection) as queries:
                reference, selected = read()
            door_reads = sum(query["sql"].lstrip().upper().startswith("SELECT")
                             and f'"{Door._meta.db_table}"' in query["sql"] for query in queries)
            self.assertEqual(door_reads, 1)
            identity = dumps((asdict(reference), selected.pk), sort_keys=True)
            print(dumps({"path": "exact_door_look_relation", "objects": size, "door_select": door_reads,
                         "reference": asdict(reference), "payload_sha256": sha256(identity.encode()).hexdigest()}),
                  flush=True)

    def test_inventory_equipment_and_explicit_number(self):
        equipped = equip_item(self.char1, self.create("guard_carbine"))
        rows = []
        for count in COUNTS:
            rows.extend(self.create("bandage", quantity=2) for _ in range(len(rows), count))
            snapshot = self.measure("inventory_equipment", count, lambda: entity_snapshot(self.char1))
            self.assertEqual(len(snapshot.carried), count + 1)
            self.assertEqual([item.identity for item in snapshot.items], [str(equipped.pk)])
            selected = self.measure(
                "explicit_number", count, lambda: resolve_item(self.char1, exact_selector("붕대", count), "봐"),
            )
            self.assertEqual(selected.pk, rows[-1].pk)

    def test_storage_inside_and_action_controls(self):
        locker = create_object(PersonalLocker, key="개인 보관함", location=self.room)
        provider = descriptor(locker).reference
        root = self.create("bandage")
        children = []
        for count in COUNTS:
            for _ in range(len(children), count):
                create_item("bandage", location_kind="personal_storage", owner_object=self.char1)
                children.append(create_item("battery", location_kind="inside", parent_item=root, socket="power"))
            inside = self.measure("inside_item_display", count, lambda: entity_snapshot(self.char1))
            self.assertEqual(sum(item.location == "inside" for item in inside.carried), count)
            controls = self.measure(
                "storage_controls", count,
                lambda: action_controls(self.char1, self.index, NOW, provider_reference=provider, verb_key="꺼내"),
            )
            self.assertEqual(len(controls), count)
            all_controls = self.measure("action_controls", count, lambda: action_controls(self.char1, self.index, NOW))
            inside_ids = {
                ref["identity"]
                for control in all_controls
                if control["action"]["action_id"] == "global.look_target"
                for ref in control["action"]["roles"]["subject"]
                if ref["scope_id"] == f"inside:{root.pk}"
            }
            self.assertEqual(inside_ids, {str(child.pk) for child in children})

    def test_corpse_ground_and_composite_selection(self):
        corpses = []
        corpse_items = []
        expected_sources = set()
        for count in COUNTS:
            for n in range(len(corpses), count):
                corpse = create_object(Corpse, key=f"시험 시체 {n}", location=self.room)
                corpse.db.decay_at = NOW + 100
                ground = create_object(DroppedLoot, key=f"시험 전리품 {n}", location=self.room)
                for source, kind in ((corpse, "corpse_loot"), (ground, "world_loot")):
                    loot_service.populate_source(source, [])
                    item = create_item("ammo_9", quantity=2, location_kind=kind, owner_object=source)
                    if source is corpse:
                        corpse_items.append(item)
                    expected_sources.add(source.pk)
                corpses.append(corpse)
            controls = self.measure("corpse_ground_loot", count, lambda: source_controls(self.char1, NOW))
            self.assertEqual(set(controls), expected_sources)
            self.assertTrue(all(control["take_action"] for control in controls.values()))
            source = descriptor(corpses[-1])
            args = f'{exact_selector(source.name, count)}에서 "9mm 권총탄" 1'
            invocation = self.measure(
                "source_entry_selection", count,
                lambda: dispatch_text(self.char1, self.index, "game.take", args, "가져"), reconciles=True,
            )
            self.assertEqual(dict(invocation.roles)["source"], (source.reference,))
            self.assertEqual(dict(invocation.roles)["subject"], (descriptor(corpse_items[-1]).reference,))
            all_matches = self.measure(
                "multi_source_entry_selection", count,
                lambda: dispatch_text(self.char1, self.index, "game.take", "모든 시체에서 모두", "가져"),
                reconciles=True,
            )
            self.assertEqual(dict(all_matches.roles)["source"],
                             tuple(descriptor(corpse).reference for corpse in corpses))
            self.assertEqual(dict(all_matches.roles)["subject"],
                             tuple(descriptor(item).reference for item in corpse_items))
