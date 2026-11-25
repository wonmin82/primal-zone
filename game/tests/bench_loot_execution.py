"""잠금 후 Loot 검증 계측. scripts/dev.py test tests.bench_loot_execution --parallel 1."""

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from itertools import count
from json import dumps
from statistics import median
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

from django.db import connection
from world import loot_service
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.loot_presentation import source_controls
from world.actions.manifest import get_index
from world.item_entities.models import ItemEntity

from tests.loot_entity_fixture import NativeLootTest

STOP = "회수 변경 직전의 계측 경계"


class LootExecutionBenchmark(NativeLootTest):
    def test_current_entry_read(self):
        items = []
        for size in (1, 10, 100):
            for _ in range(len(items), size):
                items.append(self.loot_item(quantity=2, deadline=10**10))
            expected = loot_service.loot_snapshot(self.source).entries[0]
            self.assertEqual(expected.item_id, items[0].pk)
            reads = 0
            times = []

            def read():
                self.assertEqual(loot_service._current_entry(self.source, expected), expected)

            def capture(execute_sql, sql, params, many, context):
                nonlocal reads
                self.assertTrue(sql.strip().upper().startswith("SELECT"))
                reads += 1
                return execute_sql(sql, params, many, context)

            read()
            for _ in range(5):
                start = perf_counter()
                read()
                times.append((perf_counter() - start) * 1000)
            with connection.execute_wrapper(capture):
                read()
            print("LOOT_CURRENT_BENCH " + dumps({
                "objects": size, "sql": reads, "median_ms": round(median(times), 3),
            }), flush=True)

    def test_locked_validation(self):
        from world.rules import RuleError

        index = get_index()
        self.session.puppet = self.char1
        self.session.logged_in = True
        self.session.protocol_key = "websocket"
        self.char1.sessions.add(self.session)
        identities = count(1)
        self.enterContext(patch.object(ItemEntity._meta.pk, "_get_default",
                                       new=lambda: UUID(int=next(identities))))
        self.enterContext(patch("world.actions.loot_services.time", return_value=100))
        items = []
        for size in (1, 10, 100):
            for _ in range(len(items), size):
                items.append(self.loot_item(quantity=2, deadline=10**10))
            action = source_controls(self.char1, 100)[self.source.pk]["take_action"]
            invocation = from_web({**action, "request_id": "벤치-회수"}, index)
            self.assertEqual([ref.identity for ref in dict(invocation.roles)["subject"]],
                             [str(item.pk) for item in items])
            data = asdict(invocation)
            # The independently randomized signature is excluded from the fixture digest.
            data["arguments"] = {key: value for key, value in data["arguments"] if key != "snapshot"}
            queries = Counter()
            item_reads = Counter()

            def count_sql(execute_sql, sql, params, many, context):
                statement = sql.lstrip().upper()
                queries["sql"] += 1
                if statement.startswith("SELECT") and ItemEntity._meta.db_table.upper() in statement:
                    queries["item_select"] += 1
                    item_reads[(sql, tuple(params or ()))] += 1
                if statement.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
                    queries["writes"] += 1
                return execute_sql(sql, params, many, context)

            before = self.all_state()
            durations = []
            # 기존 실제 잠금과 검증을 모두 통과한 직후, 첫 도메인 변경 전에만 중단한다.
            with patch.object(loot_service, "pickup", side_effect=RuleError(STOP)) as pickup:
                def read():
                    outcome = execute(self.char1, self.session, invocation, index)
                    self.assertEqual((outcome.status, outcome.messages), (ResultStatus.REFUSED, (STOP,)))

                read()
                for _ in range(5):
                    start = perf_counter()
                    read()
                    durations.append((perf_counter() - start) * 1000)
                with connection.execute_wrapper(count_sql):
                    read()
                self.assertEqual(pickup.call_count, 7)
                self.assertEqual(pickup.call_args.args[1].item_id, items[0].pk)
            self.assertEqual(self.all_state(), before)
            print("LOOT_LOCKED_BENCH " + dumps({
                "objects": size, "sql": queries["sql"], "item_select": queries["item_select"],
                "repeated_item_select": sum(n - 1 for n in item_reads.values()), "writes": queries["writes"],
                "median_ms": round(median(durations), 3),
                "payload_sha256": sha256(dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            }, sort_keys=True), flush=True)
