"""격리 DB에서 웹 지도 입력부터 출력 JSON까지 실제 비용을 측정한다."""

from contextlib import ExitStack
from json import dumps
from os import environ
from pathlib import Path
from statistics import median
from time import perf_counter
from tracemalloc import get_traced_memory, start, stop
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from world import map_commands, map_projection, minimap_presentation
from world.content import ROOMS

from tests.bench_exploration_map import MapBenchmark
from tests.test_minimap import MinimapTests


class WebMapBenchmark(MinimapTests):
    def test_benchmark_map_transport(self):
        self.char1.change(lambda p: p.update(visited=list(ROOMS)))
        self.char1.location = self.rooms["support_5f_c"]
        fixtures = [self.measure("headquarters_5f")]
        for size in (10, 100, 1000):
            rooms, zones, index, sheet = MapBenchmark.fixture(size)
            with ExitStack() as stack:
                for module in (map_commands, map_projection, minimap_presentation):
                    stack.enter_context(patch.object(module, "ROOMS", {**ROOMS, **rooms}))
                stack.enter_context(patch.object(minimap_presentation, "map_context",
                                                return_value=(index, self.char1.zone, set(zones))))
                fixtures.append(self.measure(size, sheet.name, rooms[zones[size // 2]]["name"]))
        output = environ.get("PRIMAL_MINIMAP_BENCH_OUTPUT")
        if output:
            Path(output).write_text(dumps(fixtures), encoding="utf-8")

    def measure(self, name, sheet=None, center=None):
        def request():
            entry = getattr(self.session, "primal_minimap", None)
            next_id = entry.request_id + 1 if entry else 1
            return self.send_map(id=next_id, sheet=sheet, center=center)

        samples = []
        for _ in range(20):
            begin = perf_counter()
            request()
            samples.append((perf_counter() - begin) * 1000)
        with CaptureQueriesContext(connection) as queries:
            request()
        start()
        try:
            payload = request()
            peak = get_traced_memory()[1]
        finally:
            stop()
        self.assertTrue(any(message["kind"] == "map" for message in payload["messages"]))
        frame = ["pz_map", [payload], {}]
        print(dumps({
            "rooms": name, "median_ms": round(median(samples), 3),
            "p95_ms": round(sorted(samples)[18], 3), "sql": len(queries),
            "json_bytes": len(dumps(frame).encode()), "python_peak_bytes": peak,
        }), flush=True)
        return frame
