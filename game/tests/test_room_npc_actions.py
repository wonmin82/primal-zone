"""운영 Manifest의 M01/M02 실제 공개 입력·Gateway·안정 ID 회귀."""

from dataclasses import replace
from unittest.mock import patch

from evennia import search_tag
from world import rules
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.manifest import get_index
from world.actions.presentation import action_controls
from world.actions.resolver import dispatch_text
from world.door_entities.models import Door
from world.item_entities import api
from world.item_entities.models import ItemEntity

from tests.base import WorldCommandTest
from tests.item_entity_fixture import NativeItemTest


class RoomNpcActionsTests(NativeItemTest, WorldCommandTest):
    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["infirmary"]
        self.session.puppet = self.char1
        self.session.logged_in = True
        self.session.protocol_key = "websocket"
        self.char1.sessions.add(self.session)
        self.output = self.enterContext(patch.object(self.char1, "msg"))
        self.index = get_index()

    def raw(self, value):
        self.output.reset_mock()
        self.char1.execute_cmd(value, session=self.session)
        return " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args)

    def test_production_manifest_and_cutover_registration(self):
        from commands.registry import COMMANDS

        self.assertIn("game.room_npc", self.index.packages)
        migrated = {"열어", "닫아", "잠궈", "풀어", "조사", "수리", "소각", "목록", "사", "팔아",
                    "가치", "회복", "휴식", "배워", "배분", "재분배", "교환", "환율"}
        self.assertFalse(migrated.intersection(command.key for command in COMMANDS))
        self.assertTrue(migrated <= {verb.key for verb in self.index.verbs.values()})

    def test_regular_exit_observation_is_not_a_numbered_object_provider(self):
        from world.targets import parse_selector, resolve

        self.char1.location = self.rooms["dock"]
        endpoint = next(obj for obj in self.char1.location.exits if obj.key == "북")
        self.assertEqual(resolve([endpoint], parse_selector("북"), self.char1), [endpoint])
        before = self.char1.location.pk
        output = self.raw("북 봐")
        self.assertTrue(output)
        self.assertNotIn("처리 중 오류", output)
        self.assertEqual(self.char1.location.pk, before)

    def test_paid_medical_real_command_and_stable_web_effect_once(self):
        self.char1.change(lambda p: p.update(hp=1, credits=1000))
        self.assertIn("체력이 20 회복됐다.", self.raw("의무관에게 20 회복"))
        self.assertEqual(self.char1.profile()["hp"], 21)
        self.assertEqual(self.char1.profile()["credits"], 995)
        control = next(c for c in action_controls(self.char1, self.index) if c["action"]["action_id"] == "medical.treat")
        payload = {**control["action"], "request_id": "medical-once"}
        from server.conf.primal_inputfuncs import pz_action

        pz_action(self.session, payload)
        after = self.char1.profile_snapshot()
        pz_action(self.session, payload)
        self.assertEqual(self.char1.profile_snapshot(), after)
        self.assertEqual(after["hp"], 60)

    def test_call_access_precedes_combat_error_for_stale_provider(self):
        from evennia.objects.models import ObjectDB

        self.char1.change(lambda profile: profile.update(hp=1, credits=1000))
        control = next(row for row in action_controls(self.char1, self.index)
                       if row["action"]["action_id"] == "medical.treat")
        invocation = from_web({**control["action"], "request_id": "medical-stale-provider"}, self.index)
        provider_ref = dict(invocation.roles)["provider"][0]
        provider = ObjectDB.objects.get(pk=provider_ref.identity)
        self.char1.change(lambda profile: profile.update(combat_target=provider.pk))
        visible = execute(self.char1, self.session, invocation, self.index)
        self.assertEqual(visible.messages, ("전투 중입니다. 먼저 승리하거나 도망하세요.",))

        balances = self.char1.profile_snapshot()
        provider.locks.add("call:false()")
        denied = execute(self.char1, self.session, invocation, self.index)
        provider.location = self.rooms["dock"]
        absent = execute(self.char1, self.session, invocation, self.index)
        self.assertEqual(denied, absent)
        self.assertEqual(denied.status, ResultStatus.REFUSED)
        self.assertEqual(self.char1.profile_snapshot(), balances)

    def test_shop_purchase_alias_single_service_and_stable_sale(self):
        self.char1.location = self.rooms["supply_shop"]
        self.char1.change(lambda p: p.update(credits=1000))
        invocation = dispatch_text(self.char1, self.index, "game.buy", "붕대", "구입")
        self.assertEqual(invocation.action_id, "shop.buy.bandage")
        before = self.char1.profile()["inventory"].get("bandage", 0)
        self.assertIn("소지품", self.raw("붕대 구입"))
        self.assertEqual(self.char1.profile()["inventory"].get("bandage", 0), before + 1)
        item = api.items_owned_by(self.char1).filter(definition_id="bandage").first()
        self.assertIsNotNone(item)
        self.assertIn("매입했다", self.raw("붕대 팔아"))
        self.assertEqual(self.char1.profile()["inventory"].get("bandage", 0), before)

    def test_shop_and_burn_share_checked_inventory_and_refuse_stale_subjects(self):
        from world.actions.presentation import reference_json
        from world.actions.schema import ReferenceKind
        from world.currency import format_currency
        from world.selection_numbers import api as selections
        from world.shop_service import resale

        self.char1.location = self.char2.location = self.rooms["supply_shop"]
        incinerator = search_tag("incinerator", category="primal_interactable")[0]
        incinerator.location = self.char1.location
        moved = self.create("bandage", quantity=2)
        deleted = self.create("bandage")
        foreign = api.create_item("bandage", location_kind="inventory", owner_object=self.char2)

        def actions(rows, action_id):
            return [row for row in rows if row["action"]["action_id"] == action_id]

        def subjects(rows):
            return [row["action"]["roles"]["subject"][0] for row in rows]

        scope = f"character:{self.char1.pk}"
        with patch.object(selections, "records_for", wraps=selections.records_for) as reads:
            rows = action_controls(self.char1, self.index, observed_at=100)
        self.assertEqual(sum(
            call.kwargs.get("check_visibility") is True
            and call.kwargs.get("kinds") == (ReferenceKind.ITEM,)
            and scope in call.kwargs.get("scope_ids", ())
            for call in reads.call_args_list
        ), 1)
        sale = actions(rows, "shop.sell.supply")
        burn = actions(rows, "incinerator.burn")
        moved_ref = reference_json(selections.descriptor(moved).reference)
        deleted_ref = reference_json(selections.descriptor(deleted).reference)
        for controls in (sale, burn):
            self.assertEqual(subjects(controls), [moved_ref, moved_ref, deleted_ref])
            self.assertEqual([row["action"]["arguments"]["count"] for row in controls], ["1", "모두", "1"])
        self.assertEqual([row["label"] for row in sale], [
            f"붕대 1 · {format_currency(resale(moved))} 팔아",
            f"붕대 1 모두 팔아 · 총 {format_currency(2 * resale(moved))}",
            f"붕대 2 · {format_currency(resale(deleted))} 팔아",
        ])
        value = actions(rows, "shop.value.bandage")
        self.assertEqual(subjects(value), [moved_ref, moved_ref, deleted_ref])
        self.assertEqual([row["action"]["variant"] for row in value], ["normal"] * 3)

        moved = api.move_item_tree(moved, location_kind="inventory", owner_object=self.char2)
        api.delete_item(deleted)
        replacement = self.create("bandage")
        other_rows = action_controls(self.char2, self.index, observed_at=100)
        for identity in ("shop.sell.supply", "incinerator.burn"):
            self.assertEqual(
                {ref["identity"] for ref in subjects(actions(other_rows, identity))},
                {str(foreign.pk), str(moved.pk)},
            )
        current_rows = action_controls(self.char1, self.index, observed_at=100)
        for identity in ("shop.sell.supply", "incinerator.burn"):
            self.assertEqual(subjects(actions(current_rows, identity)),
                             [reference_json(selections.descriptor(replacement).reference)])

        before = self.atomic_state()
        for row, request in ((sale[1], "stale-sale-owner"), (burn[-1], "stale-burn-delete")):
            invocation = from_web({**row["action"], "request_id": request}, self.index)
            self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
            self.assertEqual(self.atomic_state(), before)

    def test_door_actual_endpoint_and_no_omission_or_stale_retarget(self):
        self.char1.location = self.rooms["hq_admin_office"]
        with patch("world.doors.time", return_value=100):
            self.assertIn("잠금", self.raw("관리실 문 풀어"))
            invocation = dispatch_text(self.char1, self.index, "game.open", "관리실 문", "열어")
            alias_invocation = dispatch_text(self.char1, self.index, "game.open", "w 문", "열어")
            self.assertEqual(alias_invocation.roles, invocation.roles)
            self.assertEqual(dict(invocation.roles)["provider"][0].identity,
                             str(Door.objects.get(door_id="hq_admin_door").exit_b_id))
            self.assertIn("열었다", self.raw("관리실 문 열어"))
            self.assertEqual(Door.objects.get(door_id="hq_admin_door").auto_close_at, 160)
            self.raw("관리실 문 열어")
            self.assertEqual(Door.objects.get(door_id="hq_admin_door").auto_close_at, 160)
            before = Door.objects.get(door_id="hq_admin_door").state
            self.raw("닫아")
            self.assertEqual(Door.objects.get(door_id="hq_admin_door").state, before)
            self.char1.location = self.rooms["dock"]
            self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)

    def test_door_controls_share_observation_only_within_one_render(self):
        from world import doors

        self.char1.location = self.rooms["hq_admin_office"]
        with patch.object(doors, "time", return_value=100):
            self.assertIn("잠금", self.raw("관리실 문 풀어"))
            self.assertIn("열었다", self.raw("관리실 문 열어"))
        door = Door.objects.get(door_id="hq_admin_door")
        endpoint = str(door.exit_b_id)

        def labels(rows):
            return [row["label"] for row in rows if any(
                ref["kind"] == "door" and ref["identity"] == endpoint
                for ref in row["action"]["roles"].get("provider", ())
            )]

        with (patch.object(doors, "time", return_value=159),
              patch.object(doors, "current_doors", wraps=doors.current_doors) as candidates,
              patch.object(doors, "actions_for", wraps=doors.actions_for) as operations):
            self.assertEqual(labels(action_controls(self.char1, self.index)), ["닫아"])
            candidates.assert_called_once_with(self.char1, 159)
            self.assertEqual(operations.call_count, 1)
            self.assertEqual(operations.call_args.args[1].exit_pk, door.exit_b_id)
            self.assertEqual(operations.call_args.args[2], 159)

            self.assertEqual(labels(action_controls(self.char1, self.index, 160)), ["열어"])
            self.assertEqual(candidates.call_count, 2)
            self.assertEqual(operations.call_count, 2)
            self.assertEqual(operations.call_args.args[2], 160)
        door.refresh_from_db()
        self.assertEqual((door.state, door.auto_close_at), ("OPEN", 160))

    def test_incineration_confirmation_keeps_original_item(self):
        self.char1.location = self.rooms["salvage_office"]
        item = self.create("outpost_supply_pass")
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "incinerator.burn" and
                       c["action"]["roles"]["subject"][0]["identity"] == str(item.pk))
        invocation = from_web({**control["action"], "request_id": "burn-warning"}, self.index)
        result = execute(self.char1, self.session, invocation, self.index)
        self.assertEqual(result.status, ResultStatus.CONFIRMATION)
        self.assertTrue(ItemEntity.objects.filter(pk=item.pk).exists())
        self.assertIsNotNone(result.confirmation_token)
        confirmed = replace(invocation, variant_id="confirmed", confirmation_token=result.confirmation_token,
                            request_id="burn-confirmed")
        applied = execute(self.char1, self.session, confirmed, self.index)
        self.assertEqual(applied.status, ResultStatus.SUCCESS)
        self.assertFalse(ItemEntity.objects.filter(pk=item.pk).exists())
        self.assertEqual(execute(self.char1, self.session, confirmed, self.index).status, ResultStatus.REFUSED)
        self.assertFalse(ItemEntity.objects.filter(pk=item.pk).exists())

    def test_shop_value_numbered_item_and_fixed_catalog_argument(self):
        self.char1.location = self.rooms["supply_shop"]
        first = self.create("bandage")
        second = self.create("bandage")
        invocation = dispatch_text(self.char1, self.index, "game.value", "붕대 2", "얼마")
        self.assertEqual(dict(invocation.roles)["subject"][0].identity, str(second.pk))
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        self.assertTrue(ItemEntity.objects.filter(pk=first.pk).exists())
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "shop.buy.bandage")
        from world.rules import RuleError

        before = self.char1.profile_snapshot()
        with self.assertRaises(RuleError):
            from_web({**control["action"], "arguments": {"value": "scrap"}, "request_id": "forged-catalog"}, self.index)
        self.assertEqual(self.char1.profile_snapshot(), before)

    def test_original_name_normalization_and_quantity_value_syntax(self):
        self.char1.location = self.rooms["supply_shop"]
        self.char1.change(lambda p: p.update(credits=1000))
        for name in ("BANDAGE", "붕 대"):
            self.assertIn("소지품", self.raw(name + " 사"))
        for query in ("붕대 2개", "붕대 모두", "BANDAGE"):
            invocation = dispatch_text(self.char1, self.index, "game.value", query, "얼마")
            self.assertEqual(invocation.action_id, "shop.value.bandage")
            self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        self.assertIn("매입했다", self.raw("bandage 팔아"))
        self.char1.location = self.rooms["training_room"]
        self.char1.change(lambda p: p.update(xp=rules.xp_threshold(50)))
        self.assertIn("훈련", self.raw("강 타 배워"))
        before = rules.allocated(self.char1.profile(), "strength")
        self.assertIn("힘이 10에서 11로", self.raw("힘 +1 배분"))
        self.assertEqual(rules.allocated(self.char1.profile(), "strength"), before + 1)

    def test_settlement_default_quantity_alias_and_exact_cost(self):
        self.char1.location = self.rooms["salvage_office"]
        self.create("scrap", quantity=10)
        before = self.char1.profile()["credits"]
        self.assertIn("1개를 정산했다", self.raw("회수 부품 exchange"))
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 9)
        self.assertEqual(self.char1.profile()["credits"], before + 10)
        self.assertIn("3개를 정산했다", self.raw("회수부품 3개 교환"))
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 6)
        self.assertEqual(self.char1.profile()["credits"], before + 40)

    def test_settlement_usage_keeps_provider_source_and_normalized_amounts(self):
        from world.actions.presentation import provider_controls
        from world.selection_numbers.api import descriptor

        self.char1.location = self.rooms["salvage_office"]
        officer = next(obj for obj in self.char1.location.contents
                       if getattr(obj, "action_provider_definition", None) == "world.settlementofficer")
        self.create("scrap", quantity=12)
        appearance = officer.return_appearance(self.char1, observed_at=100)
        commands = [command for line in appearance.splitlines() for command in line.split(" · ")
                    if command.endswith((" 환율", " 교환"))]
        self.assertEqual(len(commands), 5)
        rows = [row["action"] for row in provider_controls(self.char1, officer, 100)]
        web = {row["action_id"]: from_web({**row, "request_id": row["action_id"]}, self.index) for row in rows}
        rate = web["settlement.rate"]
        all_exchange = web["settlement.all"]
        amounts = []
        for command in commands:
            args, _, verb = command.rpartition(" ")
            verb_id = "game.rate" if verb == "환율" else "game.exchange"
            text = dispatch_text(self.char1, self.index, verb_id, args, verb)
            self.assertEqual(text.variant_id, "normal")
            self.assertEqual(dict(text.roles)["provider"], (descriptor(officer).reference,))
            if verb == "환율":
                self.assertEqual((text.action_id, dict(text.roles), text.arguments),
                                 (rate.action_id, dict(rate.roles), rate.arguments))
                continue
            self.assertEqual(dict(text.roles), dict(all_exchange.roles))
            arguments = dict(text.arguments)
            self.assertEqual(arguments.pop("snapshot"), "")
            if text.action_id == all_exchange.action_id:
                self.assertEqual(arguments, {})
                self.assertTrue(dict(all_exchange.arguments)["snapshot"])
            else:
                self.assertEqual(text.action_id, "settlement.exchange")
                amounts.append(arguments["value"])
        self.assertCountEqual(amounts, [1, 10, 10])

    def test_two_merchants_require_explicit_provider_and_do_not_fallback(self):
        from world.actors.spawn import create_actor

        self.char1.location = self.rooms["supply_shop"]
        self.char1.change(lambda p: p.update(credits=1000))
        second = create_actor("supply_shopkeeper", self.char1.location, name="두번째 보급관")
        before = self.char1.profile_snapshot()
        self.assertIn("여러 명", self.raw("붕대 사"))
        self.assertEqual(self.char1.profile_snapshot(), before)
        invocation = dispatch_text(self.char1, self.index, "game.buy", "두번째 보급관에게 붕대", "사")
        self.assertEqual(dict(invocation.roles)["provider"][0].identity, str(second.pk))
        second.location = self.rooms["dock"]
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.char1.profile_snapshot(), before)

    def test_stale_settlement_web_does_not_consume_replacement_stack(self):
        self.char1.location = self.rooms["salvage_office"]
        original = self.create("scrap", quantity=3)
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "settlement.all")
        self.assertEqual(control["action"]["roles"]["source"][0]["identity"], str(self.char1.pk))
        self.assertEqual(len(control["action"]["arguments"]["snapshot"]), 64)
        invocation = from_web({**control["action"], "request_id": "old-salvage"}, self.index)
        api.delete_item(original)
        replacement = self.create("scrap", quantity=3)
        before = self.char1.profile_snapshot()
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
        replacement.refresh_from_db()
        self.assertEqual(replacement.quantity, 3)
        self.assertEqual(self.char1.profile_snapshot(), before)

    def test_aggregate_inventory_source_supports_more_than_32_stacks(self):
        self.char1.location = self.rooms["salvage_office"]
        for _ in range(33):
            self.create("scrap")
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "settlement.all")
        invocation = from_web({**control["action"], "request_id": "many-salvage"}, self.index)
        before = self.char1.profile()["credits"]
        result = execute(self.char1, self.session, invocation, self.index)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(self.char1.profile()["inventory"].get("scrap", 0), 0)
        self.assertEqual(self.char1.profile()["credits"], before + 330)

    def test_inventory_source_rejects_other_owner_and_changed_quantity(self):
        self.char1.location = self.rooms["salvage_office"]
        row = self.create("scrap", quantity=5)
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "settlement.all")
        payload = {**control["action"], "request_id": "wrong-source"}
        roles = dict(payload["roles"])
        roles["source"] = [{"kind": "inventory", "identity": str(self.char2.pk),
                            "scope_id": f"inventory:{self.char2.pk}"}]
        before = self.char1.profile_snapshot()
        forged = from_web({**payload, "roles": roles}, self.index)
        self.assertEqual(execute(self.char1, self.session, forged, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.char1.profile_snapshot(), before)
        row.quantity = 4
        row.save(update_fields=["quantity"])
        before = self.char1.profile_snapshot()
        stale = from_web(payload, self.index)
        self.assertEqual(execute(self.char1, self.session, stale, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.char1.profile_snapshot(), before)

    def test_growth_and_settlement_real_services(self):
        self.char1.location = self.rooms["training_room"]
        self.char1.change(lambda p: p.update(xp=1000))
        before = rules.skill_rank(self.char1.profile(), "heavy")
        self.assertIn("훈련", self.raw("강타 배워"))
        self.assertEqual(rules.skill_rank(self.char1.profile(), "heavy"), before + 1)
        self.char1.location = self.rooms["salvage_office"]
        self.create("scrap", quantity=10)
        before = self.char1.profile()["credits"]
        self.assertIn("정산했다", self.raw("회수부품 모두 교환"))
        self.assertEqual(self.char1.profile()["credits"], before + 100)

    def test_world_object_quest_effect_once(self):
        record = search_tag("maintenance_log", category="primal_interactable")[0]
        self.char1.location = record.location
        self.assertIn("복구 절차", self.raw("정비기록 조사"))
        self.assertTrue(self.char1.profile()["quests"]["radio_tower"]["record_read"])
