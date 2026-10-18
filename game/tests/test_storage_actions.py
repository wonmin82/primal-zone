"""운영 Storage Action의 UUID·수량·접근·원자성·B-1 회귀."""

from unittest.mock import patch

from evennia import create_object
from typeclasses.interactables import Container, PersonalLocker
from world import rules
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.manifest import compiled, get_index
from world.actions.presentation import action_controls
from world.actions.resolver import dispatch_text, role_records
from world.actions.schema import ReferenceKind, RoleDefinition
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.item_transfer_native import stored_items, transfer_selected
from world.selection_numbers.api import descriptor, label, number_for

from tests.item_entity_fixture import NativeItemTest


class StorageActionsTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.box = create_object(Container, key="공용 보관함", location=self.char1.location)
        self.locker = create_object(PersonalLocker, key="개인 보관함", location=self.char1.location)
        self.session.puppet = self.char1
        self.session.logged_in = True
        self.session.protocol_key = "websocket"
        self.char1.sessions.add(self.session)
        self.output = self.enterContext(patch.object(self.char1, "msg"))
        compiled.cache_clear()
        self.index = get_index()

    def raw(self, text):
        self.output.reset_mock()
        self.char1.execute_cmd(text, session=self.session)
        return " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args)

    def control(self, identity="storage.store", item=None, count="1", provider=None):
        controls = action_controls(self.char1, self.index)
        return next(control for control in controls
                    if control["action"]["action_id"] == identity
                    and control["action"]["arguments"]["count"] == count
                    and (item is None or control["action"]["roles"]["subject"][0]["identity"] == str(item.pk))
                    and (provider is None or control["action"]["roles"]["provider"][0]["identity"] == str(provider.pk)))

    def invoke(self, control, request="storage-test"):
        invocation = from_web({**control["action"], "request_id": request}, self.index)
        return execute(self.char1, self.session, invocation, self.index)

    def test_operating_manifest_and_root_uuid_round_trip(self):
        from commands.registry import COMMANDS

        self.assertIn("game.storage", self.index.packages)
        self.assertFalse({"넣어", "꺼내"}.intersection(command.key for command in COMMANDS))
        row = self.create("bandage")
        from world.state import multiplayer_state

        controls = {entry["name"]: entry["actions"] for entry in multiplayer_state(self.char1)["interactables"]}
        for provider in (self.box, self.locker):
            self.assertTrue(any(control.get("label") == "봐" and control.get("command", "").endswith(" 봐")
                                for control in controls[provider.key]))
        self.assertIn("보관했다", self.raw("개인 보관함에 붕대 넣어"))
        row.refresh_from_db()
        self.assertEqual((row.location_kind, row.owner_object_id), ("personal_storage", self.char1.pk))
        self.assertIn("꺼냈다", self.raw("개인 보관함에서 붕대 꺼내"))
        row.refresh_from_db()
        self.assertEqual((row.location_kind, row.owner_object_id), ("inventory", self.char1.pk))

    def test_number_quantity_and_partial_split_keep_source_number(self):
        first = self.create("bandage", quantity=4)
        second = self.create("bandage", quantity=5)
        number = number_for(descriptor(second).reference)
        invocation = dispatch_text(self.char1, self.index, "game.store", "개인 보관함에 붕대 2 3개", "넣어")
        self.assertEqual(dict(invocation.roles)["subject"], (descriptor(second).reference,))
        self.assertEqual(dict(invocation.arguments)["count"], "3개")
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        second.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual((first.quantity, second.quantity), (4, 2))
        self.assertEqual(number_for(descriptor(second).reference), number)
        self.assertEqual(sum(row.quantity for row in stored_items(self.char1, self.locker)), 3)

    def test_all_text_selects_all_stacks_and_merges_without_extra_execution(self):
        a = self.create("bandage", quantity=2)
        b = self.create("bandage", quantity=3)
        invocation = dispatch_text(self.char1, self.index, "game.store", "개인 보관함에 붕대 모두", "넣어")
        self.assertEqual(set(dict(invocation.roles)["subject"]), {descriptor(a).reference, descriptor(b).reference})
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        rows = stored_items(self.char1, self.locker)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].quantity, 5)
        self.assertEqual(rows[0].pk, a.pk)
        self.assertIn("꺼냈다", self.raw("개인 보관함에서 붕대 모두 꺼내"))
        self.assertEqual(api.items_in_location("inventory", owner_object=self.char1).get().quantity, 5)

    def test_quantity_without_number_and_invalid_quantity_do_not_change_selection(self):
        first = self.create("bandage", quantity=4)
        second = self.create("bandage", quantity=5)
        self.assertIn("보관했다", self.raw("개인 보관함에 붕대 2개 넣어"))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.quantity, second.quantity), (2, 5))
        before = self.atomic_state()
        self.raw("개인 보관함에 붕대 0개 넣어")
        self.assertEqual(self.atomic_state(), before)
        self.raw("개인 보관함에 붕대 100개 넣어")
        self.assertEqual(self.atomic_state(), before)

    def test_web_stable_stack_all_and_request_duplicate_effect_once(self):
        from server.conf.primal_inputfuncs import pz_action

        a = self.create("bandage", quantity=4)
        b = self.create("bandage", quantity=3)
        control = self.control(item=b, count="모두", provider=self.locker)
        self.assertIn(label(descriptor(b)), control["label"])
        self.assertIn("스택 전부", control["label"])
        payload = {**control["action"], "request_id": "storage-once"}
        pz_action(self.session, payload)
        a.refresh_from_db()
        self.assertEqual(a.quantity, 4)
        self.assertEqual(stored_items(self.char1, self.locker)[0].pk, b.pk)
        # 실제 웹 어댑터는 완료한 요청을 재실행하지 않는다.
        before = self.atomic_state()
        pz_action(self.session, payload)
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(stored_items(self.char1, self.locker)[0].quantity, 3)

    def test_remote_storage_and_permissions_rechecked_for_stale_web(self):
        row = self.create("bandage")
        self.assertEqual(transfer_selected(self.char1, self.locker, [row]), ("bandage", 1))
        control = self.control("storage.retrieve", row, provider=self.locker)
        before = self.atomic_state()
        self.locker.locks.add("call:false()")
        self.assertEqual(self.invoke(control).status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        self.locker.locks.add("call:true();view:false()")
        self.assertEqual(self.invoke(control, "storage-view").status, ResultStatus.REFUSED)
        self.locker.locks.add("view:true()")
        self.char1.location = self.room2
        self.assertEqual(self.invoke(control, "storage-remote").status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)

    def test_personal_and_shared_ownership_scopes_are_distinct(self):
        own = self.create("bandage", quantity=2)
        transfer_selected(self.char1, self.locker, [own])
        private = stored_items(self.char1, self.locker)[0]
        public = api.create_item("bandage", location_kind="shared_storage", owner_object=self.box)
        other = api.create_item("bandage", location_kind="personal_storage", owner_object=self.char2)
        self.assertEqual(descriptor(private).scope_id, f"personal_storage:{self.char1.pk}")
        self.assertEqual(descriptor(public).scope_id, f"shared_storage:{self.box.pk}")
        current = {record.reference for record in role_records(self.char1, RoleDefinition("subject", (ReferenceKind.ITEM,)))}
        self.assertNotIn(descriptor(private).reference, current)
        self.assertNotIn(descriptor(other).reference, current)
        self.assertEqual(self.invoke(self.control("storage.retrieve", public, provider=self.box)).status, ResultStatus.SUCCESS)
        # 회수한 스택은 기존 소지 스택에 병합되며 살아남은 UUID를 유지한다.
        own.refresh_from_db()
        self.assertEqual((own.owner_object_id, own.quantity), (self.char1.pk, 2))
        self.assertFalse(ItemEntity.objects.filter(pk=public.pk).exists())
        before = self.atomic_state()
        with self.assertRaises(rules.RuleError):
            transfer_selected(self.char1, self.locker, [other], withdraw=True)
        self.assertEqual(self.atomic_state(), before)

    def test_explicit_missing_number_does_not_fallback_or_move_storage_item(self):
        first = self.create("bandage")
        second = self.create("bandage")
        api.delete_item(first)
        before = self.atomic_state()
        self.char1.push_state.reset_mock()
        self.raw("개인 보관함에 붕대 1 넣어")
        self.assertEqual(self.atomic_state(), before)
        second.refresh_from_db()
        self.assertEqual(second.location_kind, "inventory")
        self.assertEqual(number_for(descriptor(second).reference), 2)

    def test_stale_uuid_rejects_replacement_and_rollback_after_partial_work(self):
        first = self.create("bandage", quantity=2)
        control = self.control(item=first, provider=self.locker)
        api.delete_item(first)
        replacement = self.create("bandage", quantity=2)
        self.assertEqual(self.invoke(control).status, ResultStatus.REFUSED)
        replacement.refresh_from_db()
        self.assertEqual(replacement.quantity, 2)
        second = self.create("bandage", quantity=3)
        before = self.atomic_state()
        self.char1.push_state.reset_mock()
        original = api.move_item_tree
        calls = []

        def fail_second(*args, **kwargs):
            calls.append(args[0].pk)
            if len(calls) == 2:
                raise rules.RuleError("격리 실패 재현")
            return original(*args, **kwargs)

        with patch("world.item_transfer_native.api.move_item_tree", side_effect=fail_second):
            with self.assertRaises(rules.RuleError):
                transfer_selected(self.char1, self.locker, [replacement, second], None)
        self.assertEqual(self.atomic_state(), before)
        self.char1.push_state.assert_not_called()

    def test_parent_tree_uuid_and_inside_numbers_survive_storage_move(self):
        parent = self.create("flashlight")
        child = api.create_item("battery", location_kind="inside", parent_item=parent, socket="power")
        before = descriptor(child).reference
        number = number_for(before)
        transfer_selected(self.char1, self.locker, [parent])
        child.refresh_from_db()
        self.assertEqual(child.parent_item_id, parent.pk)
        self.assertEqual(descriptor(child).reference, before)
        self.assertEqual(number_for(before), number)
        controls = action_controls(self.char1, self.index)
        self.assertFalse(any(c["action"]["roles"]["provider"][0]["identity"] == str(child.pk) for c in controls))
        transfer_selected(self.char1, self.locker, [parent], withdraw=True)
        child.refresh_from_db()
        self.assertEqual(descriptor(child).reference, before)

    def test_shared_transfer_policy_combat_and_equipped_item_reject_without_effect(self):
        key = self.create("hq_admin_key")
        before = self.atomic_state()
        with self.assertRaises(rules.RuleError):
            transfer_selected(self.char1, self.box, [key])
        self.assertEqual(self.atomic_state(), before)
        weapon = self.create("explorer_machete")
        api.move_item_tree(weapon, location_kind="equipment", owner_object=self.char1, slot="hands", operation="equip")
        equipped_before = self.atomic_state()
        with self.assertRaises(rules.RuleError):
            transfer_selected(self.char1, self.locker, [weapon])
        self.assertEqual(self.atomic_state(), equipped_before)
        row = self.create("bandage")
        self.char1.change(lambda p: p.update(combat_target="test"))
        with self.assertRaises(rules.RuleError):
            transfer_selected(self.char1, self.locker, [row])
        row.refresh_from_db()
        self.assertEqual(row.location_kind, "inventory")
