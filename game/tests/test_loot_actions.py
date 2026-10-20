"""운영 가져/집 Cutover와 Source/Entry의 실제 고정 번호 회귀."""

from unittest.mock import patch

from evennia import create_object
from typeclasses.loot import Corpse, DroppedLoot
from world import loot_service
from world.actions.gateway import ResultStatus, execute
from world.actions.manifest import compiled, get_index
from world.actions.resolver import dispatch_text
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.rules import RuleError
from world.selection_numbers.api import descriptor, number_for

from tests.loot_entity_fixture import NativeLootTest


class LootActionTests(NativeLootTest):
    def setUp(self):
        super().setUp()
        compiled.cache_clear()
        self.index = get_index()
        self.enterContext(patch("world.actions.loot_resolution.time", return_value=100))
        self.enterContext(patch("world.actions.loot_services.time", return_value=100))
        self.session.puppet = self.char1
        self.session.logged_in = True
        self.session.protocol_key = "websocket"
        self.char1.sessions.add(self.session)
        self.output = self.enterContext(patch.object(self.char1, "msg"))

    def invocation(self, text, command="가져"):
        return dispatch_text(self.char1, self.index, "game.take", text, command)

    def run_take(self, text):
        return execute(self.char1, self.session, self.invocation(text), self.index)

    def corpse(self):
        source = create_object(Corpse, key="시험 시체", location=self.char1.location)
        source.db.decay_at = 200
        loot_service.populate_source(source, [])
        return source

    def test_operating_manifest_and_legacy_command_removed(self):
        from commands.registry import COMMANDS
        self.assertIn("game.loot", self.index.packages)
        self.assertFalse(any(command.key == "가져" for command in COMMANDS))
        self.assertEqual(self.index.verbs_by_public_keys["집"], "game.take")

    def test_public_evennia_command_and_alias_change_real_inventory(self):
        item = self.loot_item(quantity=3)
        for command in ("시체에서 9mm 권총탄 가져", "시체에서 9mm 권총탄 집"):
            completed = []
            self.char1.execute_cmd(command, session=self.session).addCallback(lambda _: completed.append(True))
            self.assertEqual(completed, [True])
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)
        self.assertEqual(ItemEntity.objects.get(owner_object=self.char1, definition_id="ammo_9").quantity, 2)

    def test_default_source_before_provider_binding(self):
        item = self.loot_item(quantity=3)
        other = self.corpse()
        api.create_item("ammo_9", quantity=5, location_kind="corpse_loot", owner_object=other)
        invocation = self.invocation("시체에서 모두")
        self.assertEqual(dict(invocation.roles)["source"], (descriptor(self.source).reference,))
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        item.refresh_from_db()
        self.assertEqual(item.owner_object_id, self.char1.pk)
        self.assertEqual(ItemEntity.objects.get(owner_object=other).quantity, 5)

    def test_corpse_numbers_holes_new_four_and_reset(self):
        second, third = self.corpse(), self.corpse()
        self.assertEqual([number_for(descriptor(source).reference) for source in (self.source, second, third)], [1, 2, 3])
        second.delete()
        fourth = self.corpse()
        self.assertEqual(number_for(descriptor(third).reference), 3)
        self.assertEqual(number_for(descriptor(fourth).reference), 4)
        with self.assertRaises(RuleError):
            self.invocation("시체 2에서 모두")
        self.source.delete()
        third.delete()
        fourth.delete()
        fresh = self.corpse()
        self.assertEqual(number_for(descriptor(fresh).reference), 1)

    def test_global_shortcut_missing_number_never_replaces_source(self):
        from commands.aliases import SHORTCUTS
        self.assertEqual(SHORTCUTS["시2"], "시체 2에서 모두 가져")
        second, third = self.corpse(), self.corpse()
        second.delete()
        item = api.create_item("ammo_9", quantity=3, location_kind="corpse_loot", owner_object=third)
        self.char1.execute_cmd("시2", session=self.session)
        item.refresh_from_db()
        self.assertEqual(item.owner_object_id, third.pk)

    def test_internal_entry_numbers_independent_from_source_number(self):
        second = self.corpse()
        item = api.create_item("ammo_9", quantity=3, location_kind="corpse_loot", owner_object=second)
        self.assertEqual(number_for(descriptor(second).reference), 2)
        self.assertEqual(number_for(descriptor(item).reference), 1)
        invocation = self.invocation("시체 2에서 9mm 권총탄 1")
        self.assertEqual(dict(invocation.roles)["subject"], (descriptor(item).reference,))

    def test_multiple_sources_all_and_currency_amount(self):
        self.loot_item(quantity=2)
        second = self.corpse()
        api.create_item("ammo_9", quantity=3, location_kind="corpse_loot", owner_object=second)
        self.assertEqual(self.run_take("모든 시체에서 9mm 권총탄 모두").status, ResultStatus.SUCCESS)
        self.assertEqual(ItemEntity.objects.get(owner_object=self.char1, definition_id="ammo_9").quantity, 5)
        row = loot_service.create_currency(self.source, 30)
        self.assertEqual(self.run_take("시체에서 20칩").status, ResultStatus.SUCCESS)
        row.refresh_from_db()
        self.assertEqual(row.quantity, 10)

    def test_ground_without_source_and_entry_number(self):
        ground = create_object(DroppedLoot, key="탄약", location=self.char1.location)
        loot_service.populate_source(ground, [{"kind": "item", "id": "ammo_9", "quantity": 3}])
        item = ItemEntity.objects.get(owner_object=ground)
        invocation = self.invocation("9mm 권총탄 1")
        self.assertEqual(dict(invocation.roles)["source"], (descriptor(ground).reference,))
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_expired_source_reference_refused_after_lifecycle(self):
        self.loot_item(quantity=3)
        invocation = self.invocation("시체에서 모두")
        self.source.db.decay_at = 99
        result = execute(self.char1, self.session, invocation, self.index)
        self.assertEqual(result.status, ResultStatus.REFUSED)
        self.assertFalse(Corpse.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(ItemEntity.objects.filter(owner_object=self.char1).exists())
        self.assertTrue(DroppedLoot.objects.exists())


    def test_public_look_uses_actual_typed_corpse_and_keeps_npc_and_room(self):
        from typeclasses.interactables import Doctor

        self.loot_item(quantity=2)
        doctor = create_object(Doctor, key="시험 의무관", location=self.char1.location)
        with patch("commands.character.time", return_value=100), patch.object(
                self.char1, "at_look", wraps=self.char1.at_look) as at_look:
            for command, expected in (("시체 1 봐", self.source), ("시험 의무관 1 봐", doctor),
                                      ("봐", self.char1.location)):
                at_look.reset_mock()
                completed = []
                self.char1.execute_cmd(command, session=self.session).addCallback(lambda _: completed.append(True))
                self.assertEqual(completed, [True], command)
                self.assertEqual(at_look.call_count, 1, command)
                self.assertEqual(at_look.call_args.args[0], expected, command)
        self.assertEqual(ItemEntity.objects.get(owner_object=self.source).quantity, 2)


    def test_isolated_integration_hook_compiles_new_service_and_rolls_back(self):
        import importlib.util
        from pathlib import Path

        from django.conf import settings
        from world.actions import loot_content

        path = Path(__file__).resolve().parents[2] / "scripts" / "integration_hooks.py"
        spec = importlib.util.spec_from_file_location("primal_test_integration_hooks", path)
        hooks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hooks)
        self.loot_item(quantity=2)
        invocation = self.invocation("시체에서 모두")
        before = self.all_state()
        package = loot_content.PACKAGE
        try:
            with patch("server.conf.smoke_support.require_smoke") as require_smoke:
                hooks.install_loot_rollback(settings)
                require_smoke.assert_called_once_with(settings)
            index = get_index()
            self.assertNotEqual(index.services["loot.pickup"].handler,
                                self.index.services["loot.pickup"].handler)
            result = execute(self.char1, self.session, invocation, index)
            self.assertEqual(result.status, ResultStatus.REFUSED)
            self.assertIn("상위 변경 롤백", str(result.messages))
            self.assertEqual(self.all_state(), before)
            self.output.assert_not_called()
        finally:
            loot_content.PACKAGE = package
            compiled.cache_clear()


    def scoped_items(self, first, second):
        from copy import deepcopy

        from world.content import ITEMS

        definitions = {}
        for identity, values in (("scope_loot_a", first), ("scope_loot_b", second)):
            definitions[identity] = {**deepcopy(ITEMS["ammo_9"]), **values}
        self.enterContext(patch.dict(ITEMS, definitions))
        return [api.create_item(identity, quantity=3, location_kind="corpse_loot", owner_object=self.source)
                for identity in definitions]

    def test_scope_alias_shared_by_different_groups_is_ambiguous(self):
        self.scoped_items({"name": "첫째물품", "aliases": ["겹친별칭"]},
                          {"name": "둘째물품", "aliases": ["겹친별칭"]})
        with self.assertRaisesMessage(RuleError, "선택 그룹"):
            self.invocation("시체에서 겹친별칭")
        self.assertFalse(ItemEntity.objects.filter(owner_object=self.char1).exists())

    def test_actual_numeric_name_precedes_another_definition_alias(self):
        first, named = self.scoped_items({"name": "먼저물품", "aliases": ["물품 2"]},
                                         {"name": "물품 2", "aliases": []})
        invocation = self.invocation("시체에서 물품 2")
        self.assertEqual(dict(invocation.roles)["subject"], (descriptor(named).reference,))
        self.assertNotEqual(descriptor(first).reference, descriptor(named).reference)
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        self.assertEqual(ItemEntity.objects.get(owner_object=self.char1).definition_id, named.definition_id)

    def test_same_name_shared_selection_group_selects_actual_number(self):
        first, second = self.scoped_items({"name": "공유물품", "aliases": [], "selection_group_id": "test:loot_shared"},
                                          {"name": "공유물품", "aliases": [], "selection_group_id": "test:loot_shared"})
        self.assertEqual([number_for(descriptor(item).reference) for item in (first, second)], [1, 2])
        invocation = self.invocation("시체에서 공유물품 2")
        self.assertEqual(dict(invocation.roles)["subject"], (descriptor(second).reference,))
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        self.assertEqual(ItemEntity.objects.get(owner_object=self.char1).definition_id, second.definition_id)

    def test_protected_ground_hides_content_in_full_state_room_and_detail(self):
        import json
        from copy import deepcopy

        from typeclasses.zone_rooms import ZoneRoom
        from world.content import ITEMS
        from world.selection_numbers.api import records_for
        from world.state import multiplayer_state

        secret = "비공개시험전리품"
        self.enterContext(patch.dict(ITEMS, {"secret_loot": {**deepcopy(ITEMS["ammo_9"]), "name": secret}}))
        room = create_object(ZoneRoom, key="보호정보 시험장", attributes=[("zone_id", "hq_lounge")])
        for obj in (self.char1, self.char2, self.source):
            obj.location = room
        item = self.loot_item("secret_loot", quantity=739)
        identity = item.pk
        self.source.reconcile(now=201)
        item.refresh_from_db()
        ground = item.owner_object
        reference = descriptor(item).reference
        number = number_for(reference)
        source_reference = descriptor(ground).reference
        source_number = number_for(source_reference)
        with patch("world.observation.time", return_value=201):
            own = multiplayer_state(self.char1, now=201)
            other = multiplayer_state(self.char2, now=201)
            self.assertEqual(own["ground_loot"][0]["id"], other["ground_loot"][0]["id"])
            self.assertIn(secret, json.dumps(own, ensure_ascii=False))
            hidden = json.dumps(other, ensure_ascii=False)
            self.assertNotIn(secret, hidden)
            self.assertNotIn('"quantity": 739', hidden)
            self.assertEqual(other["ground_loot"][0]["loot"], [])
            for output in (room.return_appearance(self.char2, observed_at=201),
                           ground.return_appearance(self.char2, observed_at=201), ground.get_display_name(self.char2)):
                self.assertNotIn(secret, str(output))
                self.assertNotIn("739", str(output))
            self.assertIn(secret, str(room.return_appearance(self.char1, observed_at=201)))
            for player in (self.char1, self.char2):
                record = next(record for record in records_for(player) if record.reference == reference)
                self.assertEqual(record.number, number)
        item.refresh_from_db()
        self.assertEqual(item.pk, identity)
        self.assertEqual(descriptor(ground).reference, source_reference)
        self.assertEqual(number_for(source_reference), source_number)


    def test_name_in_inventory_does_not_shadow_all_sources_loot_syntax(self):
        from copy import deepcopy

        from world.content import ITEMS

        first, second = self.scoped_items({"name": "공유물품", "aliases": [], "selection_group_id": "test:loot_shared"},
                                          {"name": "공유물품", "aliases": [], "selection_group_id": "test:loot_shared"})
        self.enterContext(patch.dict(ITEMS, {"unrelated_loot": {**deepcopy(ITEMS["ammo_9"]), "name": "공유물품 모두"}}))
        self.create("unrelated_loot")
        invocation = self.invocation("모든 시체에서 공유물품 모두")
        self.assertEqual(set(dict(invocation.roles)["subject"]),
                         {descriptor(first).reference, descriptor(second).reference})
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)


    def test_protected_currency_quantity_cannot_be_probed_by_text(self):
        from time import time

        row = loot_service.create_currency(self.source, 17, shares={self.char1: 17},
                                            reserved_player=self.char1, protection_until=time() + 300)
        session = self.connect_character(self.char2)
        before = [player.profile()["credits"] for player in (self.char1, self.char2)]
        results = [execute(self.char2, session,
                           dispatch_text(self.char2, self.index, "game.take", f"시체에서 {amount}칩", "가져"),
                           self.index) for amount in (1, 999)]
        self.assertEqual([result.status for result in results], [ResultStatus.REFUSED] * 2)
        self.assertEqual(results[0].messages, results[1].messages)
        self.assertEqual(results[0].messages, ("지금 선택할 수 없는 전리품입니다.",))
        own = self.run_take("시체에서 999칩")
        self.assertEqual(own.status, ResultStatus.REFUSED)
        self.assertIn("수량이 부족", str(own.messages))
        row.refresh_from_db()
        self.assertEqual(row.quantity, 17)
        self.assertEqual(row.shares.get(player=self.char1).remaining_amount, 17)
        self.assertEqual([player.profile()["credits"] for player in (self.char1, self.char2)], before)

    def test_protected_item_quantity_cannot_be_probed_by_forged_web(self):
        from time import time

        from world.actions.gateway import from_web
        from world.actions.loot_presentation import payload

        item = self.loot_item(quantity=17, deadline=time() + 300)
        session = self.connect_character(self.char2)
        base = payload(self.char1, [(self.source, self.entry(item))], quantity=1, now=100)
        results = []
        for amount in (1, 999):
            forged = {**base, "request_id": f"forged-quantity-{amount}",
                      "arguments": {**base["arguments"], "quantity": amount}}
            results.append(execute(self.char2, session, from_web(forged, self.index), self.index))
        self.assertEqual([result.status for result in results], [ResultStatus.REFUSED] * 2)
        self.assertEqual(results[0].messages, results[1].messages)
        self.assertEqual(results[0].messages, ("지금 선택할 수 없는 전리품입니다.",))
        item.refresh_from_db()
        self.assertEqual((item.owner_object_id, item.quantity), (self.source.pk, 17))


    def test_default_public_look_keeps_first_corpse_with_multiple_sources(self):
        self.loot_item(quantity=2)
        second = self.corpse()
        api.create_item("bandage", quantity=4, location_kind="corpse_loot", owner_object=second)
        with patch("commands.character.time", return_value=100), patch.object(
                self.char1, "at_look", wraps=self.char1.at_look) as at_look:
            for command, expected in (("시체 봐", self.source), ("시체 2 봐", second)):
                at_look.reset_mock()
                completed = []
                self.char1.execute_cmd(command, session=self.session).addCallback(lambda _: completed.append(True))
                self.assertEqual(completed, [True])
                self.assertEqual(at_look.call_count, 1)
                self.assertEqual(at_look.call_args.args[0], expected)

    def test_legacy_blob_readonly_state_and_detail_have_no_fake_action(self):
        from copy import deepcopy

        from evennia.utils.dbserialize import deserialize
        from world.actions.loot_presentation import all_controls, source_controls
        from world.state import multiplayer_state

        legacy = create_object(Corpse, key="과거 저장 시체", location=self.char1.location)
        legacy.db.decay_at = 200
        legacy.db.entries = [{"item": "bandage", "quantity": 2},
                             {"kind": "currency", "id": "credits", "quantity": 21,
                              "shares": {self.char1.pk: 11, self.char2.pk: 10}, "protection_until": 220}]
        before = deepcopy(deserialize(legacy.db.entries))
        counts = ItemEntity.objects.count()
        control = source_controls(self.char1, 100)[legacy.pk]
        self.assertEqual([entry["id"] for entry in control["loot"]], ["bandage", "credits"])
        self.assertEqual([entry["quantity"] for entry in control["loot"]], [2, 21])
        self.assertTrue(all(entry["action"] is None for entry in control["loot"]))
        self.assertTrue(all(entry["take_command"] == "" for entry in control["loot"]))
        self.assertIsNone(control["take_action"])
        self.assertEqual(control["take_command"], "")
        self.assertEqual(all_controls(self.char1, 100), {"corpses": None, "ground": None})
        state = multiplayer_state(self.char1, 100)
        self.assertTrue(any(source["id"] == legacy.pk for source in state["corpses"]))
        appearance = legacy.return_appearance(self.char1, observed_at=100)
        self.assertIn("붕대 ×2", str(appearance))
        self.assertIn("21칩", str(appearance))
        self.assertNotIn("회수:", str(appearance))
        self.assertEqual(deserialize(legacy.db.entries), before)
        self.assertEqual(ItemEntity.objects.count(), counts)
