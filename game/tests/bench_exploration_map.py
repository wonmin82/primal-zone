"""격리 SQLite에서 지도 조회 비용을 재현한다.

저장소 루트에서 python scripts/dev.py test tests.bench_exploration_map --parallel 1
"""

import cProfile
import os
import platform
import sqlite3
import sys
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from json import dumps
from linecache import getline
from math import ceil
from pathlib import Path
from pstats import Stats
from re import sub
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from django.db import connection, connections
from django.test import TransactionTestCase
from evennia import __version__ as evennia_version
from evennia.objects.models import ObjectDB
from evennia.typeclasses.attributes import Attribute
from evennia.typeclasses.tags import Tag
from typeclasses.explorers import Explorer
from world import map_projection
from world.bootstrap import CATEGORY, EXIT_CATEGORY
from world.content import OPPOSITE_DIRECTIONS, ROOMS
from world.map_layout import layout, render
from world.map_metadata import build_catalog
from world.text import display_width

from tests.base import WorldCommandTest

REPEATS = 20


def print_record(**record):
    print(dumps(record, ensure_ascii=False), flush=True)


def stats(samples):
    columns = list(zip(*samples, strict=True))
    return {
        "median_ms": [round(median(values), 3) for values in columns],
        "p95_ms": [round(sorted(values)[ceil(0.95 * len(values)) - 1], 3) for values in columns],
    }


def timed_map(viewer, catalog, sheet, *, current, visited, center=None, near=False):
    start = perf_counter()
    graph = map_projection.project(
        viewer, catalog, sheet, current=current, visited=visited, now=0, center=center, near=near,
    )
    projected = perf_counter()
    placed = layout(graph.names, graph.edges, graph.positions, graph.routes, graph.anchors)
    laid_out = perf_counter()
    output = render(placed, graph.boundaries, current=graph.current, center=graph.center)
    done = perf_counter()
    return graph, output, [1000 * duration for duration in
                           (projected - start, laid_out - projected, done - laid_out)]


def measure_queries(request, *, explain=False):
    statements = []

    def recorder(execute, sql, params, many, context):
        start = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            statements.append((sql, params or (), 1000 * (perf_counter() - start)))

    with connection.execute_wrapper(recorder):
        result = request()
    sql_ms = sum(elapsed for _, _, elapsed in statements)
    record = {"queries": len(statements), "sql_execute_ms": round(sql_ms, 3),
              "projection_minus_sql_execute_ms": round(result[2][0] - sql_ms, 3)}
    if explain:
        with connection.cursor() as cursor:
            plans = []
            for sql, params, elapsed in statements:
                cursor.execute("EXPLAIN QUERY PLAN " + sql, params)
                plans.append({"sql": sub(r"(?:%s, ){8,}%s", "%s, …", sql),
                              "parameters": len(params), "execute_ms": round(elapsed, 3),
                              "plan": [row[-1] for row in cursor.fetchall()]})
        record["query_plans"] = plans
    return record


def profile_request(request):
    # cProfile과 줄별 구간 계측은 처리 시간 표와 별도 실행한다.
    profiler = cProfile.Profile()
    profiler.runcall(request)
    entries = []
    for (path, _, name), (_, calls, own, cumulative, _) in Stats(profiler).stats.items():
        if path.endswith(("/map_projection.py", "/map_layout.py", "/observation.py", "/doors.py")) or name in (
            "from_db", "__call__", "access", "_fetch_all", "check", "value", "dbunserialize",
        ):
            entries.append((path.rsplit("/", 1)[-1], name, calls, round(1000 * own, 3),
                            round(1000 * cumulative, 3)))

    current = {}
    rows = {}
    target = map_projection.__file__

    def trace(frame, event, arg):
        if frame.f_code.co_filename != target:
            return None
        if event in ("line", "return"):
            now = perf_counter()
            if frame in current:
                previous, started = current.pop(frame)
                row = rows.setdefault((frame.f_code.co_name, previous), [0, 0.0])
                row[0] += 1
                row[1] += 1000 * (now - started)
            if event == "line":
                current[frame] = (frame.f_lineno, now)
        return trace

    previous_trace = sys.gettrace()
    sys.settrace(trace)
    try:
        request()
    finally:
        sys.settrace(previous_trace)
    lines = [(name, lineno, getline(target, lineno).strip(), count, round(elapsed, 3))
             for (name, lineno), (count, elapsed) in rows.items()]
    return {"call_columns": ["module", "function", "calls", "self_ms", "inclusive_ms"],
            "calls": sorted(entries, key=lambda entry: entry[-1], reverse=True)[:50],
            "line_columns": ["function", "line", "source", "visits", "inclusive_ms"],
            "lines": sorted(lines, key=lambda entry: entry[-1], reverse=True)[:50]}


def output_record(graph, output):
    plain = "\n".join(output.lines).encode()
    value = repr((graph, tuple((line.kind, line.segments) for line in output.lines))).encode()
    return {"plain_utf8_bytes": len(plain), "public_output_sha256": sha256(value).hexdigest()}


class MapBenchmark(TransactionTestCase):
    def test_map_query_cost(self):
        print_record(platform=platform.platform(), python=platform.python_version(),
                     sqlite=sqlite3.sqlite_version, evennia=evennia_version,
                     revision=os.environ.get("PRIMAL_MAP_BENCH_SHA", "UNRECORDED"),
                     repeats=REPEATS, warm_cold_definition=(
                         "콜드는 Evennia 객체 캐시 초기화, 웜은 동일 DB와 프로세스에서 반복"
                     ))
        for size in (10, 100, 1000):
            self.measure(size)

    @staticmethod
    def fixture(size):
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
        return rooms, zones, catalog, sheet

    def measure(self, size):
        rooms, zones, catalog, sheet = self.fixture(size)
        viewer = SimpleNamespace(location=SimpleNamespace(pk=-1), is_superuser=False)
        with patch.object(map_projection, "ROOMS", rooms):
            for ratio in (10, 50, 100):
                count = size * ratio // 100
                start = size // 2 - count // 2
                visited = set(zones[start:start + count])

                def request():
                    return timed_map(viewer, catalog, sheet, current="", visited=visited, center=zones[size // 2])

                # Django/Evennia 클래스 import 준비는 캐시를 비우기 전에 끝낸다.
                ObjectDB.flush_instance_cache(force=True)
                Attribute.flush_instance_cache(force=True)
                _, _, cold = request()
                samples = [request()[2] for _ in range(REPEATS)]
                query_result = measure_queries(request, explain=size == 1000 and ratio == 100)
                tracemalloc.start()
                try:
                    graph, output, _ = request()
                    _, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                self.assertEqual(len(graph.names), count)
                self.assertLessEqual(query_result["queries"], 10)
                self.assertEqual(len(graph.edges), 2 * (count - 1))
                self.assertLessEqual(len(output.lines), 24)
                self.assertTrue(all(display_width(line) <= 60 for line in output.lines))

                record = dict(scenario="원격 직선", rooms=size, exits=2 * (size - 1), visited_pct=ratio,
                              public_nodes=len(graph.names), cold_ms=[round(value, 3) for value in cold],
                              peak_bytes=peak, **output_record(graph, output))
                if ratio == 100:
                    record["four_concurrent"] = self.concurrent(request)
                if size == 1000 and ratio == 100:
                    record["profile"] = profile_request(request)
                print_record(**record, **stats(samples), **query_result)

    def concurrent(self, request):
        def parallel_request(_):
            worker = connections["default"]
            worker.settings_dict = {**worker.settings_dict, "NAME": str(snapshot)}
            try:
                return request()[2]
            finally:
                worker.close()

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
            return {"wall_ms": round(1000 * (perf_counter() - start), 3), **stats(concurrent)}


class CurrentMapBenchmark(WorldCommandTest):
    character_typeclass = Explorer

    def test_current_world_map(self):
        from world.map_metadata import catalog

        rooms = self.world_rooms()
        self.char1.location = rooms["support_5f_c"]
        current = self.char1.location.db.zone_id
        index = catalog()
        sheet = index.sheets[index.room_sheet[current]]
        for near in (False, True):
            def request():
                return timed_map(self.char1, index, sheet, current=current, visited=set(rooms), near=near)

            graph, output, first = request()
            print_record(scenario="본부 5층 근처" if near else "본부 5층 전체",
                         rooms=len(sheet.rooms), exits=sum(len(ROOMS[zone]["exits"]) for zone in sheet.rooms),
                         public_nodes=len(graph.names), first_ms=[round(value, 3) for value in first],
                         **output_record(graph, output), **stats([request()[2] for _ in range(REPEATS)]),
                         **measure_queries(request), profile=profile_request(request))
            self.assertIn("@", "".join(output.lines))

        for zone in ("support_elevator", "support_3f_c", "dock"):
            self.char1.location = rooms[zone]
            sheet = index.sheets.get(index.room_sheet[zone])
            graph = map_projection.project(self.char1, index, sheet, current=zone, visited=set(rooms), now=0)
            self.assertTrue(graph.notices or graph.boundaries or graph.edges)
            print_record(scenario="현재 Connector 및 Sheet 경계", target=zone,
                         public_nodes=len(graph.names), boundaries=len(graph.boundaries), notices=len(graph.notices))


class LayoutBenchmark(TestCase):
    def test_conflict_and_viewport_cost(self):
        for scenario, width, height in (
            ("분기", 250, 4), ("순환·복수 경로 격자", 25, 40), ("위치·경로 Hint", 500, 2),
        ):
            nodes = [f"{i:04d}" for i in range(width * height)]
            edges = []
            positions, routes = {}, {}
            for row in range(height):
                for col in range(width):
                    idx = row * width + col
                    if col + 1 < width and (scenario != "분기" or row == 0):
                        edges.append((nodes[idx], "동", nodes[idx + 1]))
                        if scenario == "위치·경로 Hint":
                            positions[nodes[idx + 1]] = (nodes[idx], (3, 0))
                            routes[nodes[idx], "동"] = ((1, 0),)
                    if row + 1 < height and (scenario != "위치·경로 Hint" or col == 0):
                        edges.append((nodes[idx], "남", nodes[idx + width]))
            edges += [(target, OPPOSITE_DIRECTIONS[direction], source) for source, direction, target in edges]
            anchor = nodes[0]

            def request():
                start = perf_counter()
                placed = layout(nodes, edges, positions, routes, (anchor,))
                laid_out = perf_counter()
                output = render(placed, current=nodes[len(nodes) // 2])
                return placed, output, [1000 * (laid_out - start), 1000 * (perf_counter() - laid_out)]

            placed, output, _ = request()
            self.assertEqual(len(placed.rooms), len(nodes))
            self.assertLessEqual(len(output.lines), 24)
            self.assertTrue(all(display_width(line) <= 60 for line in output.lines))
            print_record(scenario=scenario, rooms=len(nodes), exits=len(edges), hints=len(positions) + len(routes),
                         layout_render=stats([request()[2] for _ in range(REPEATS)]),
                         plain_utf8_bytes=len("\n".join(output.lines).encode()),
                         profile=profile_request(request)["calls"])
