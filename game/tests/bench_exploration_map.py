"""격리 SQLite에서 지도 조회 비용을 재현한다.

저장소 루트에서 python scripts/dev.py test tests.bench_exploration_map --parallel 1
"""

import platform
import sqlite3
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from json import dumps
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection, connections
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from evennia.objects.models import ObjectDB
from evennia.typeclasses.attributes import Attribute
from evennia.typeclasses.tags import Tag
from world.bootstrap import CATEGORY, EXIT_CATEGORY
from world.map_layout import layout, render
from world.map_metadata import build_catalog
from world.map_projection import project


class MapBenchmark(TransactionTestCase):
    def test_map_query_cost(self):
        print(dumps({"platform": platform.platform(), "python": platform.python_version(),
                     "sqlite": sqlite3.sqlite_version}))
        for size in (10, 100, 1000):
            self.measure(size)

    def measure(self, size):
        region = f"bench_{size}"
        zones = [f"{region}_{i:04d}" for i in range(size)]
        rooms = {}
        for i, zone in enumerate(zones):
            exits = {}
            if i:
                exits["서"] = zones[i - 1]
            if i + 1 < size:
                exits["동"] = zones[i + 1]
            rooms[zone] = {"name": f"장소 {i}", "exits": exits}
        regions = {region: {"name": "실험 지역", "entry": zones[0], "rooms": zones}}
        catalog = build_catalog(rooms, regions, dict.fromkeys(zones, region))
        sheet = catalog.sheets[region]
        room_models = ObjectDB.objects.bulk_create([
            ObjectDB(db_key=zone, db_typeclass_path="typeclasses.zone_rooms.ZoneRoom",
                     db_lock_storage="view:all()") for zone in zones
        ])
        ids = {room.db_key: room.pk for room in room_models}
        tags = Tag.objects.bulk_create([Tag(db_key=zone, db_category=CATEGORY, db_model="objectdb")
                                        for zone in zones])
        attrs = Attribute.objects.bulk_create([Attribute(db_key="zone_id", db_value=zone, db_model="objectdb")
                                               for zone in zones])
        membership = ObjectDB.db_tags.through
        membership.objects.bulk_create([membership(objectdb_id=ids[t.db_key], tag_id=t.pk) for t in tags])
        membership = ObjectDB.db_attributes.through
        membership.objects.bulk_create([membership(objectdb_id=ids[z], attribute_id=a.pk)
                                       for z, a in zip(zones, attrs, strict=True)])
        exit_models = ObjectDB.objects.bulk_create([
            ObjectDB(db_key=direction, db_location_id=ids[zone], db_destination_id=ids[target],
                     db_typeclass_path="typeclasses.exits.Exit", db_lock_storage="view:all()")
            for zone, data in rooms.items() for direction, target in data["exits"].items()
        ])
        exit_tags = Tag.objects.bulk_create([
            Tag(db_key=f"{zone}:{direction}", db_category=EXIT_CATEGORY, db_model="objectdb")
            for zone, data in rooms.items() for direction in data["exits"]
        ])
        membership = ObjectDB.db_tags.through
        membership.objects.bulk_create([membership(objectdb_id=obj.pk, tag_id=tag.pk)
                                       for obj, tag in zip(exit_models, exit_tags, strict=True)])
        viewer = SimpleNamespace(location=SimpleNamespace(pk=-1), is_superuser=False)
        visited = set(zones)

        def request():
            start = perf_counter()
            graph = project(viewer, catalog, sheet, current="", visited=visited, now=0, center=zones[size // 2])
            projected = perf_counter()
            placed = layout(graph.names, graph.edges, graph.positions, graph.routes, graph.anchors)
            laid_out = perf_counter()
            output = render(placed, graph.boundaries, center=graph.center)
            done = perf_counter()
            return (graph, output, [round(1000 * duration, 3) for duration in
                                    (projected - start, laid_out - projected, done - laid_out)])

        def parallel_request(_):
            worker = connections["default"]
            worker.settings_dict = {**worker.settings_dict, "NAME": str(snapshot)}
            try:
                return request()[2]
            finally:
                worker.close()

        with patch("world.map_projection.ROOMS", rooms):
            tracemalloc.start()
            with CaptureQueriesContext(connection) as queries:
                graph, output, traced_ms = request()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            _, _, ms = request()
            with TemporaryDirectory(prefix="primal-map-bench-") as folder:
                snapshot = Path(folder) / "benchmark.sqlite3"
                copy = sqlite3.connect(snapshot)
                try:
                    connection.connection.backup(copy)
                finally:
                    copy.close()
                start = perf_counter()
                with ThreadPoolExecutor(max_workers=4) as pool:
                    concurrent = list(pool.map(parallel_request, range(4)))
                parallel_ms = (perf_counter() - start) * 1000
        self.assertEqual(len(graph.names), size)
        self.assertLessEqual(len(queries), 10)
        self.assertEqual(len(graph.edges), 2 * (size - 1))
        print(dumps({
            "rooms": size, "queries": len(queries), "peak_bytes": peak,
            "projection_layout_render_ms": ms, "traced_ms": traced_ms,
            "plain_utf8_bytes": len("\n".join(output.lines).encode()),
            "four_concurrent_wall_ms": round(parallel_ms, 3), "four_concurrent_ms": concurrent,
        }))
