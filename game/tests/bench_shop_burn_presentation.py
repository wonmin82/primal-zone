"""#113 계측: scripts/dev.py test tests.bench_shop_burn_presentation --parallel 1."""

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
from evennia import create_object
from evennia.objects.models import ObjectDB
from typeclasses.interactables import Incinerator
from world import firearm_service, shop_service
from world.actions import resolver
from world.actions.manifest import get_index
from world.actions.presentation import action_controls, reference_json
from world.actions.room_npc_presentation import sort_controls
from world.actors.spawn import create_actor
from world.content import ITEMS
from world.item_entities import api
from world.item_entities import policy as item_policy
from world.item_entities.models import ItemEntity
from world.selection_numbers import api as selection
from world.selection_numbers.models import SelectionNumber

from tests.item_entity_fixture import NativeItemTest

NOW = 100
COUNTS = (1, 10, 100)
SAMPLES = 5


@override_settings(ACTION_CONTENT_PACKAGES=("world.actions.room_npc_content",))
class ShopBurnPresentationBenchmark(NativeItemTest):
    def setUp(self):
        super().setUp()
        identities = count(1)
        self.enterContext(patch.object(ItemEntity._meta.pk, "_get_default",
                                       new=lambda: UUID(int=next(identities))))
        room = self.char1.location
        room.db.zone_id = "supply_shop"
        self.shop = create_actor("supply_shopkeeper", room)
        self.burner = create_object(Incinerator, key="실측 소각로", location=room)
        self.index = get_index()

    def screen(self, scenario):
        if scenario.startswith("firearm_") or "_firearm_" in scenario:
            if scenario.endswith("_full_screen"):
                return action_controls(self.char1, self.index, NOW)
            if scenario.endswith("_sell"):
                provider = selection.descriptor(self.firearm_shop).reference
                verb = "팔아"
            else:
                provider = selection.descriptor(self.burner).reference
                verb = "소각"
            return action_controls(self.char1, self.index, NOW, provider_reference=provider, verb_key=verb)
        if scenario == "sell":
            return action_controls(self.char1, self.index, NOW,
                                   provider_reference=selection.descriptor(self.shop).reference, verb_key="팔아")
        if scenario == "burn":
            return action_controls(self.char1, self.index, NOW,
                                   provider_reference=selection.descriptor(self.burner).reference, verb_key="소각")
        rows = action_controls(self.char1, self.index, NOW)
        provider = [reference_json(selection.descriptor(self.shop).reference)]
        shop_rows = [row for row in rows if row["action"]["roles"].get("provider") == provider]
        other_rows = [row for row in rows if row["action"]["roles"].get("provider") != provider]
        return sort_controls(self.shop, shop_rows) + other_rows

    def measure(self, scenario, size):
        baseline = self.screen(scenario)
        durations = []
        for _ in range(SAMPLES):
            start = perf_counter()
            current = self.screen(scenario)
            durations.append((perf_counter() - start) * 1000)
            self.assertEqual(current, baseline)

        queries = Counter()
        b1_queries = Counter()
        object_queries = Counter()
        pricing_depth = 0
        firearm_policy_depth = 0

        def count_sql(execute, sql, params, many, context):
            statement = sql.lstrip().upper()
            queries["sql"] += 1
            if pricing_depth:
                queries["pricing_sql"] += 1
            if statement.startswith("SELECT"):
                if firearm_policy_depth and ItemEntity._meta.db_table.upper() in statement:
                    queries["firearm_policy_sql"] += 1
                if SelectionNumber._meta.db_table.upper() in statement:
                    queries["b1_select"] += 1
                    b1_queries[(sql, tuple(params or ()))] += 1
                if ItemEntity._meta.db_table.upper() in statement:
                    queries["item_select"] += 1
                    where = statement.partition(" WHERE ")[2]
                    if "PARENT_ITEM_ID" in where and "SOCKET" in where and "magazine" in (params or ()):
                        queries["magazine_relation_select"] += 1
                if ObjectDB._meta.db_table.upper() in statement:
                    queries["object_select"] += 1
                    object_queries[(sql, tuple(params or ()))] += 1
            elif statement.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
                queries["writes"] += 1
            return execute(sql, params, many, context)

        resale = shop_service.resale
        can_item_operation = item_policy.can_item_operation

        def price(item):
            nonlocal pricing_depth
            pricing_depth += 1
            try:
                return resale(item)
            finally:
                pricing_depth -= 1

        def check_item_operation(item, operation, *args, **kwargs):
            nonlocal firearm_policy_depth
            is_firearm_disposal = (
                operation in ("sell", "burn")
                and ITEMS.get(getattr(item, "definition_id", None), {}).get("firearm_family")
            )
            if is_firearm_disposal:
                firearm_policy_depth += 1
            try:
                return can_item_operation(item, operation, *args, **kwargs)
            finally:
                if is_firearm_disposal:
                    firearm_policy_depth -= 1

        with (connection.execute_wrapper(count_sql),
              patch.object(resolver, "role_records", wraps=resolver.role_records) as roles,
              patch.object(selection, "resolve_reference", wraps=selection.resolve_reference) as resolves,
              patch.object(shop_service, "resale", side_effect=price) as prices,
              patch.object(item_policy, "can_item_operation", side_effect=check_item_operation) as policies):
            actual = self.screen(scenario)

        self.assertEqual(actual, baseline)
        self.assertEqual(queries["writes"], 0)
        print("SHOP_BURN_BENCH " + dumps({
            "scenario": scenario, "count": size, "controls": len(actual),
            "payload_sha256": sha256(dumps(actual, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "median_ms": round(median(durations), 3),
            **{name: queries[name] for name in (
                "sql", "item_select", "b1_select", "magazine_relation_select", "object_select",
                "firearm_policy_sql", "pricing_sql", "writes",
            )},
            "repeated_object_select": sum(repeats - 1 for repeats in object_queries.values()),
            "repeated_b1_select": sum(repeats - 1 for repeats in b1_queries.values()),
            "role_records": roles.call_count, "item_resolves": sum(
                call.args[0].kind == "item" for call in resolves.call_args_list if call.args and call.args[0] is not None
            ),
            "resale_calls": prices.call_count,
            "firearm_policy_calls": policies.call_count,
        }, sort_keys=True), flush=True)
        return actual

    def test_shop_burn_controls_with_candidate_growth(self):
        entities = []
        for size in COUNTS:
            for n in range(len(entities), size):
                entities.append(self.create("bandage", quantity=n % 2 + 1))
            expected = [reference_json(selection.descriptor(item).reference)
                        for item in entities for _ in range(2 if item.quantity > 1 else 1)]
            for scenario, actions in (
                ("sell", ("shop.sell.supply",)),
                ("burn", ("incinerator.burn",)),
                ("full_screen", ("shop.sell.supply", "incinerator.burn", "shop.value.bandage")),
            ):
                rows = self.measure(scenario, size)
                for action in actions:
                    subjects = [row["action"]["roles"]["subject"][0] for row in rows
                                if row["action"]["action_id"] == action]
                    self.assertEqual(subjects, expected)
                if scenario == "full_screen":
                    self.assertTrue(any(row["action"]["action_id"] == "shop.buy.bandage" for row in rows))

    def test_firearm_sell_burn_mounting_candidates(self):
        room = self.char1.location
        room.db.zone_id = "weapon_shop"
        self.firearm_shop = create_actor("weapon_shopkeeper", room)

        for scenario in ("unmounted", "mounted", "mixed"):
            rows = []
            mounted = []
            for size in COUNTS:
                while len(rows) < size:
                    index = len(rows)
                    is_mounted = scenario == "mounted" or (scenario == "mixed" and index % 2 == 1)
                    identity = "guard_carbine" if index % 2 else "scout_pistol"
                    gun = firearm_service.create_firearm(
                        identity,
                        owner_object=self.char1,
                        mode="full_standard" if is_mounted else "no_mag",
                    )
                    rows.append(gun)
                    mounted.append(is_mounted)

                expected = {str(gun.pk) for gun, has_magazine in zip(rows, mounted) if not has_magazine}
                for action_scenario, action_id in (
                    ("firearm_sell", "shop.sell.weapon"),
                    ("firearm_burn", "incinerator.burn"),
                    ("firearm_full_screen", None),
                ):
                    controls = self.measure(f"{scenario}_{action_scenario}", size)
                    relevant = [row["action"] for row in controls
                                if row["action"]["action_id"] in ("shop.sell.weapon", "incinerator.burn")]
                    if action_id is not None:
                        selected = {action["roles"]["subject"][0]["identity"] for action in relevant
                                    if action["action_id"] == action_id}
                        self.assertEqual(selected, expected)
                    else:
                        for selected_action_id in ("shop.sell.weapon", "incinerator.burn"):
                            selected = {action["roles"]["subject"][0]["identity"] for action in relevant
                                        if action["action_id"] == selected_action_id}
                            self.assertEqual(selected, expected)

            for gun in rows:
                magazine = firearm_service.loaded_magazine_item(gun)
                if magazine is not None:
                    api.delete_item(magazine)
                api.delete_item(gun)
