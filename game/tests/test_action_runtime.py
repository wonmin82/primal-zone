"""명시 콘텐츠 선언에서 실제 Evennia/구조화 입력의 단일 실행 경계를 확인한다."""

from dataclasses import replace
from unittest.mock import patch

from django.test import override_settings
from evennia import create_object
from server.conf.primal_inputfuncs import pz_action
from twisted.internet.defer import Deferred
from typeclasses.loot import Corpse
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.manifest import compiled, get_index
from world.actions.presentation import action_controls, help_entries, reference_json
from world.actions.providers import ActionProviderObject
from world.actions.resolver import dispatch_text, select_role
from world.actions.schema import DefaultTargetPolicy, ReferenceKind, RoleDefinition
from world.actions.scope import CMDSET_KEY, refresh
from world.multiplayer import world_change
from world.rules import RuleError
from world.selection_numbers.api import descriptor, number_for
from world.selection_numbers.models import SelectionNumber

from tests.item_entity_fixture import NativeItemTest


@override_settings(ACTION_CONTENT_PACKAGES=("world.actions.validation_content",))
class ActionRuntimeTests(NativeItemTest):
    def test_item_number_quantity_syntax_and_shortage_never_replace_default(self):
        a, b = self.create("bandage", quantity=2), self.create("bandage", quantity=5)
        self.raw("붕대 2개 검측")
        self.assertEqual((self.events()[-1]["roles"]["subject"], self.events()[-1]["quantity"]), ([str(a.pk)], 2))
        self.raw("붕대 2 3개 검측")
        self.assertEqual((self.events()[-1]["roles"]["subject"], self.events()[-1]["quantity"]), ([str(b.pk)], 3))
        self.raw("붕대 3개 검측")
        self.assertEqual(len(self.events()), 2)

    def test_default_item_legacy_sequence_is_independent_of_new_scope_number(self):
        from world.item_entities.api import create_item, move_item

        older = create_item("bandage", location_kind="inventory", owner_object=self.char2)
        newer = self.create("bandage")
        move_item(older, location_kind="inventory", owner_object=self.char1)
        older.refresh_from_db()
        self.assertEqual(number_for(descriptor(newer).reference), 1)
        self.assertEqual(number_for(descriptor(older).reference), 2)
        self.raw("붕대 검측")
        self.assertEqual(self.events()[0]["roles"]["subject"], [str(older.pk)])
        self.raw("붕대 1 검측")
        self.assertEqual(self.events()[1]["roles"]["subject"], [str(newer.pk)])

    def test_fixed_corpse_shortcut_holes_and_explicit_door_role(self):
        from commands.aliases import SHORTCUTS
        from typeclasses.exits import Exit
        from world.door_entities.models import Door

        a, b, c = self.corpse(), self.corpse(), self.corpse()
        b.delete()
        expanded = SHORTCUTS["시2"]
        self.assertIn("시체 2", expanded)
        source_role = RoleDefinition("source", (ReferenceKind.CORPSE,), DefaultTargetPolicy.FIRST_LEGACY_ORDER)
        with self.assertRaises(RuleError):
            select_role(self.char1, source_role, "시체 2")
        self.assertEqual(select_role(self.char1, source_role, "시체 3"), (descriptor(c).reference,))
        left = create_object(Exit, key="동", location=self.char1.location, destination=self.room2)
        right = create_object(Exit, key="서", location=self.room2, destination=self.char1.location)
        Door.objects.create(door_id="validation_door", name="관리실 문", room_a="test_a", room_b="test_b",
                            exit_a=left, exit_b=right, direction_a="동", direction_b="서", state="CLOSED")
        role = RoleDefinition("subject", (ReferenceKind.DOOR,))
        self.assertEqual(select_role(self.char1, role, "문"), (descriptor(left).reference,))
        with self.assertRaises(RuleError):
            select_role(self.char1, role, "")
        self.assertEqual(select_role(self.char1, role, "문 1"), (descriptor(left).reference,))
        self.assertEqual(number_for(descriptor(a).reference), 1)

    def test_provider_direct_location_collision_rolls_back_live_and_number_state(self):
        from django.core.exceptions import ValidationError
        from world.selection_numbers.api import verify

        first = self.instrument("같은 이름")
        create_object(ActionProviderObject, key="같은 이름", location=self.room2,
                      attributes=[("action_provider_id", "validation.instrument"),
                                  ("selection_group_id", "validation.other_group")])
        reference = descriptor(first).reference
        with self.assertRaises(ValidationError):
            first.location = self.room2
        self.assertEqual(first.location, self.char1.location)
        self.assertEqual(number_for(reference), 1)
        self.assertEqual(verify(), ())

    def test_first_policy_rejects_cross_group_alias_and_duplicate_numeric_actual_names(self):
        a, b = self.instrument("실제 빨강"), self.instrument("실제 파랑")
        a.aliases.add("공용별칭")
        b.aliases.add("공용별칭")
        from dataclasses import replace
        from unittest.mock import patch
        first = descriptor(a)
        second = replace(descriptor(b), group_id="validation.other")
        role = RoleDefinition("subject", (ReferenceKind.OBJECT,), DefaultTargetPolicy.FIRST_LEGACY_ORDER)
        with patch("world.actions.resolver.role_records", return_value=(first, second)):
            with self.assertRaises(RuleError):
                select_role(self.char1, role, "공용별칭")
        numeric = (replace(first, name="상자 1"), replace(second, name="상자 1"))
        with patch("world.actions.resolver.role_records", return_value=numeric):
            with self.assertRaises(RuleError):
                select_role(self.char1, role, "상자 1")

    def test_actual_loot_stable_source_rights_and_two_observers_keep_same_number(self):
        from time import time

        from world import loot_service
        from world.item_entities.api import create_item
        from world.selection_numbers.api import records_for

        source = self.corpse()
        loot_service.populate_source(source, [])
        item = create_item("bandage", location_kind="corpse_loot", owner_object=source)
        claim = loot_service.create_claim(item, reserved_player=self.char2,
                                         assigned_player=self.char2, protection_until=time() + 300)
        ref = descriptor(item).reference
        payload = {"action_id": "validation.loot", "variant": "normal", "request_id": "loot-1",
                   "roles": {"provider": [reference_json(ref)], "subject": [reference_json(ref)]}, "arguments": {}}
        self.assertEqual(execute(self.char1, self.session, from_web(payload, self.index), self.index).status,
                         ResultStatus.REFUSED)
        self.assertEqual(self.events(), [])
        self.char2.location = self.char1.location
        before = number_for(ref)
        self.assertEqual([row.number for row in records_for(self.char1, ReferenceKind.LOOT)],
                         [row.number for row in records_for(self.char2, ReferenceKind.LOOT)])
        claim.protection_until = 0
        claim.save()
        self.raw("붕대 전리검측")
        self.assertEqual(self.events()[0]["roles"]["subject"], [str(item.pk)])
        self.assertEqual(number_for(ref), before)

    def setUp(self):
        super().setUp()
        compiled.cache_clear()
        self.index = get_index()
        self.session.puppet = self.char1
        self.session.logged_in = True
        self.session.protocol_key = "websocket"
        self.char1.sessions.add(self.session)
        self.output = self.enterContext(patch.object(self.char1, "msg"))
        self.prompt = self.enterContext(patch.object(self.char1, "push_prompt", wraps=self.char1.push_prompt))
        self.counters = self.enterContext(patch.object(self.session, "update_session_counters"))
        self.char1.db.action_validation_events = []

    def tearDown(self):
        compiled.cache_clear()
        super().tearDown()

    def instrument(self, name="검증기", room=None, unique=False):
        with world_change():
            obj = create_object(ActionProviderObject, key=name, location=room or self.char1.location,
                                attributes=[("action_provider_id", "validation.instrument"),
                                            ("selection_group_id", "validation.instruments"),
                                            ("selection_unique_names", [name] if unique else [])])
            obj.locks.add("call:true();view:true();delete:true()")
        return obj

    def corpse(self):
        with world_change():
            obj = create_object(Corpse, key="시험 시체", location=self.char1.location,
                                attributes=[("action_provider_id", "validation.corpse")])
            obj.locks.add("call:true();view:true()")
            return obj

    def events(self):
        return list(self.char1.db.action_validation_events or [])

    def raw(self, text):
        self.prompt.reset_mock()
        self.output.reset_mock()
        done = []
        deferred = self.char1.execute_cmd(text, session=self.session)
        self.assertIsInstance(deferred, Deferred)
        deferred.addCallback(lambda result: done.append(True))
        self.assertEqual(done, [True], text)
        self.prompt.assert_called_once()
        frames = [call.args[0] for call in self.output.call_args_list if call.args]
        self.assertEqual(sum(getattr(frame, "kind", None) == "prompt" for frame in frames), 1)
        self.assertEqual(getattr(frames[-1], "kind", None), "prompt")
        return self.events()

    def payload(self, action="validation.quantity", target=None, quantity=2, request_id="test-1"):
        target = target or self.instrument()
        return {"action_id": action, "variant": "normal", "request_id": request_id,
                "roles": {"provider": [reference_json(descriptor(target).reference)]},
                "arguments": {"quantity": quantity} if action == "validation.quantity" else {}}

    def test_one_dynamic_command_shared_providers_multi_service_and_actual_prompt(self):
        a, b = self.instrument(), self.instrument()
        refresh(self.char1)
        cmdset = next(cmdset for cmdset in self.char1.cmdset.cmdset_stack if cmdset.key == CMDSET_KEY)
        self.assertEqual(sum(command.key == "검측" for command in cmdset), 1)
        self.raw("검증기 2 3 검측")
        event, = self.events()
        self.assertEqual(event["roles"]["provider"], [str(b.pk)])
        self.assertEqual(event["quantity"], 3)
        self.raw("검증기 1 계측 확정")
        self.assertEqual([event["service"] for event in self.events()], ["quantity", "object"])
        self.assertEqual(self.events()[-1]["roles"]["provider"], [str(a.pk)])

    def test_independent_provider_omission_requires_unique_and_no_first_wins(self):
        a = self.instrument()
        invocation = dispatch_text(self.char1, self.index, "validation.measure", "", "검측 확정")
        self.assertEqual(dict(invocation.roles)["provider"], (descriptor(a).reference,))
        self.instrument()
        with self.assertRaises(RuleError):
            dispatch_text(self.char1, self.index, "validation.measure", "", "검측 확정")

    def test_item_self_provider_default_does_not_apply_independent_provider_ambiguity(self):
        a, b = self.create("bandage"), self.create("bandage")
        self.raw("붕대 검측")
        self.assertEqual(self.events()[0]["roles"]["subject"], [str(a.pk)])
        self.assertEqual(self.events()[0]["roles"]["provider"], [str(a.pk)])
        self.raw("붕대 2 검측")
        self.assertEqual(self.events()[1]["roles"]["provider"], [str(b.pk)])

    def test_normal_confirmed_variants_and_web_flag_cannot_skip_confirmation(self):
        obj = self.instrument()
        payload = self.payload("validation.object", obj)
        normal = from_web(payload, self.index)
        result = execute(self.char1, self.session, normal, self.index)
        self.assertEqual(result.status, ResultStatus.CONFIRMATION)
        self.assertEqual(self.events(), [])
        confirmed = replace(normal, variant_id="confirmed", request_id="confirm-2")
        self.assertEqual(execute(self.char1, self.session, confirmed, self.index).status, ResultStatus.REFUSED)
        confirmed = replace(confirmed, confirmation_token=result.confirmation_token)
        self.assertEqual(execute(self.char1, self.session, confirmed, self.index).status, ResultStatus.SUCCESS)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(execute(self.char1, self.session, confirmed, self.index).status, ResultStatus.REFUSED)
        with self.assertRaises(RuleError):
            from_web({**payload, "confirmed": True}, self.index)

    def test_structured_web_same_service_duplicate_stale_and_current_permission(self):
        obj = self.instrument()
        payload = self.payload(target=obj)
        pz_action(self.session, payload)
        self.assertEqual(len(self.events()), 1)
        self.prompt.assert_called_once()
        self.counters.assert_called_once()
        self.prompt.reset_mock()
        pz_action(self.session, payload)
        self.assertEqual(len(self.events()), 1)
        self.prompt.assert_not_called()
        payload = {**payload, "request_id": "other"}
        obj.locks.add("call:false()")
        pz_action(self.session, payload)
        self.assertEqual(len(self.events()), 1)
        obj.locks.add("call:true()")
        obj.move_to(self.room2, quiet=True)
        self.instrument()
        pz_action(self.session, {**payload, "request_id": "stale"})
        self.assertEqual(len(self.events()), 1)

    def test_session_account_puppet_and_attachment_ownership_all_required(self):
        payload = self.payload()
        invocation = from_web(payload, self.index)
        self.session.puppet = self.char2
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
        self.session.puppet = self.char1
        with patch.object(self.char1.sessions, "all", return_value=[]):
            self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
        with patch.object(self.session, "account", self.account2):
            self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.events(), [])

    def test_b1_gap_numeric_real_name_and_explicit_all_selection(self):
        a, b, c = [self.instrument() for _ in range(3)]
        a.delete()
        role = RoleDefinition("provider", (ReferenceKind.OBJECT,))
        with self.assertRaises(RuleError):
            select_role(self.char1, role, "검증기 1")
        self.assertEqual(select_role(self.char1, role, "검증기 3"), (descriptor(c).reference,))
        real = self.instrument("검증기 1")
        self.assertEqual(select_role(self.char1, role, "검증기 1"), (descriptor(real).reference,))
        multi = RoleDefinition("subject", (ReferenceKind.OBJECT,),
                               DefaultTargetPolicy.FIRST_LEGACY_ORDER, allow_all=True)
        self.assertEqual(set(select_role(self.char1, multi, "검증기 모두")),
                         {descriptor(b).reference, descriptor(c).reference})
        self.assertEqual(number_for(descriptor(b).reference), 2)

    def test_corpse_self_provider_default_and_multi_source_single_service(self):
        a, b = self.corpse(), self.corpse()
        self.raw("시체에서 채록")
        self.assertEqual(self.events()[0]["roles"]["provider"], [str(a.pk)])
        self.raw("모든 시체에서 채록")
        self.assertEqual(len(self.events()), 2)
        self.assertEqual(self.events()[1]["roles"]["source"], [str(a.pk), str(b.pk)])
        self.assertEqual(self.events()[1]["roles"]["provider"], [str(a.pk), str(b.pk)])

    def test_refusal_exception_and_invalid_argument_rollback_effects(self):
        obj = self.instrument()
        invocation = from_web(self.payload(target=obj), self.index)
        obj.db.validation_refuse = True
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.events(), [])
        obj.db.validation_refuse = False
        obj.db.validation_error = True
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.ERROR)
        self.assertEqual(self.events(), [])
        with self.assertRaises(RuleError):
            from_web(self.payload(target=obj, quantity=True), self.index)

    def test_help_and_controls_are_pure_and_default_settings_do_not_enable_fixture(self):
        self.instrument()
        self.create("bandage")
        before = list(SelectionNumber.objects.values_list("pk", "number"))
        for _ in range(2):
            self.assertTrue(help_entries(self.index))
            self.assertTrue(action_controls(self.char1, self.index))
        self.assertEqual(list(SelectionNumber.objects.values_list("pk", "number")), before)
        self.assertEqual(self.events(), [])
        with override_settings(ACTION_CONTENT_PACKAGES=()):
            self.assertEqual(dict(get_index().actions), {})

    def test_item_merged_stale_uuid_and_foreign_or_inside_provider_are_not_replaced(self):
        from world.item_entities.api import create_item, merge_stack

        a, b = self.create("bandage"), self.create("bandage")
        ref = reference_json(descriptor(a).reference)
        payload = {"action_id": "validation.item", "variant": "normal", "request_id": "stale-item",
                   "roles": {"provider": [ref], "subject": [ref]}, "arguments": {}}
        merge_stack(a, b)
        self.assertEqual(execute(self.char1, self.session, from_web(payload, self.index), self.index).status,
                         ResultStatus.REFUSED)
        foreign = create_item("bandage", location_kind="inventory", owner_object=self.char2)
        inside = create_item("bandage", location_kind="inside", parent_item=b, socket="supply")
        for item in (foreign, inside):
            ref = reference_json(descriptor(item).reference)
            candidate = {**payload, "roles": {"provider": [ref], "subject": [ref]}}
            self.assertEqual(execute(self.char1, self.session, from_web(candidate, self.index), self.index).status,
                             ResultStatus.REFUSED)
        self.assertEqual(self.events(), [])

    def test_explicit_denied_provider_does_not_fallback_and_scope_refreshes_next_command(self):
        a, b = self.instrument(), self.instrument()
        a.locks.add("call:false()")
        self.raw("검증기 1 2 검측")
        self.assertEqual(self.events(), [])
        self.raw("검증기 2 2 검측")
        self.assertEqual(self.events()[0]["roles"]["provider"], [str(b.pk)])
        b.move_to(self.room2, quiet=True)
        self.raw("검증기 2 2 검측")
        self.assertEqual(len(self.events()), 1)

    def test_real_get_input_replaces_dynamic_commands_and_web_then_restores(self):
        from evennia.utils.evmenu import InputCmdSet, get_input

        obj = self.instrument()
        for owner in (self.char1, self.account):
            with self.subTest(owner=owner.__class__.__name__):
                self.char1.db.action_validation_events = []
                received = []

                def callback(caller, prompt, answer):
                    received.append(answer)
                    return answer != "완료"

                refresh(self.char1)
                get_input(owner, "검증 응답을 입력하세요.", callback, session=self.session)
                refresh(self.char1)
                self.assertFalse(any(cmdset.key == CMDSET_KEY for cmdset in self.char1.cmdset.cmdset_stack))
                waiting = next(cmdset for cmdset in owner.cmdset.cmdset_stack if cmdset.key == InputCmdSet.key)
                self.assertEqual(waiting.priority, 1)
                self.assertEqual(waiting.mergetype, "Replace")
                pz_action(self.session, self.payload(target=obj, request_id="waiting"))
                self.assertEqual(self.events(), [])
                self.assertEqual(received, [])
                completed = []
                self.char1.execute_cmd("검증기 2 검측", session=self.session).addCallback(lambda value: completed.append(True))
                self.assertEqual(completed, [True])
                self.assertEqual(received, ["검증기 2 검측"])
                self.assertEqual(self.events(), [])
                self.char1.execute_cmd("완료", session=self.session)
                self.assertIsNone(owner.ndb._getinput)
                self.raw("검증기 2 검측")
                self.assertEqual(len(self.events()), 1)
                get_input(owner, "중단 검증", callback, session=self.session)
                owner.cmdset.remove(InputCmdSet)
                del owner.ndb._getinput
                self.raw("검증기 3 검측")
                self.assertEqual(len(self.events()), 2)

    def test_registration_engine_global_protection_and_actual_exit_priority(self):
        from evennia.objects.objects import DefaultExit
        from world.actions.manifest import protected_names
        from world.actions.registry import RegistryError, compile_manifest
        from world.actions.schema import PackageManifest
        from world.actions.validation_content import PACKAGE

        for key in ("@help", "봐", "북"):
            altered = replace(PACKAGE, verbs=(replace(PACKAGE.verbs[0], key=key), PACKAGE.verbs[1]))
            with self.subTest(key=key), self.assertRaises(RegistryError):
                compile_manifest(PackageManifest((altered,)), protected_names())
        self.instrument()
        create_object(DefaultExit, key="검측", location=self.char1.location, destination=self.room2)
        self.raw("검측")
        self.assertEqual(self.char1.location, self.room2)
        self.assertEqual(self.events(), [])

    def test_current_engine_command_suppresses_dynamic_verb(self):
        from evennia import CmdSet, Command

        self.instrument()
        calls = []
        command = Command(key="검측", locks="cmd:all()")
        command.func = lambda: calls.append(True)
        cmdset = CmdSet(key="ValidationEngine")
        cmdset.add(command)
        self.char1.cmdset.add(cmdset)
        self.raw("검측")
        self.assertEqual(calls, [True])
        self.assertEqual(self.events(), [])

    def test_current_engine_exit_and_variant_collision_revalidate_old_web_payload(self):
        from evennia import CmdSet, Command
        from evennia.objects.objects import DefaultExit

        obj = self.instrument()
        payload = self.payload(target=obj)
        invocation = from_web(payload, self.index)
        for key in ("검측", "검측 확정", "/검측 확정"):
            with self.subTest(engine_key=key):
                cmdset = CmdSet(key="ValidationCollision")
                cmdset.add(Command(key=key))
                self.account.cmdset.add(cmdset)
                refresh(self.char1)
                self.assertFalse(any(row["action"]["action_id"] == "validation.object"
                                     for row in action_controls(self.char1, self.index)))
                self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
                self.assertEqual(self.events(), [])
                self.account.cmdset.remove("ValidationCollision")
        for key in ("검측", "검측 확정"):
            with self.subTest(exit_key=key):
                exit_obj = create_object(DefaultExit, key=key, location=self.char1.location, destination=self.room2)
                refresh(self.char1)
                self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
                self.assertFalse(any(row["action"]["action_id"] == "validation.object"
                                     for row in action_controls(self.char1, self.index)))
                self.assertEqual(self.events(), [])
                exit_obj.delete()
        refresh(self.char1)
        self.assertTrue(any(row["action"]["action_id"] == "validation.object"
                            for row in action_controls(self.char1, self.index)))
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.SUCCESS)
        self.assertEqual(len(self.events()), 1)

    def test_personal_same_name_active_action_then_inactive_shortcut(self):
        obj = self.instrument()
        self.raw("검측 점수 줄임말")
        self.assertEqual(self.char1.profile_snapshot()["command_shortcuts"]["검측"], "점수")
        self.raw("검증기 2 검측")
        self.assertEqual(len(self.events()), 1)
        self.raw("검측")
        self.assertFalse(any(getattr(call.args[0], "kind", None) == "sheet"
                             for call in self.output.call_args_list if call.args))
        obj.move_to(self.room2, quiet=True)
        self.raw("검측")
        self.assertTrue(any(getattr(call.args[0], "kind", None) == "sheet"
                            for call in self.output.call_args_list if call.args))
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.char1.profile_snapshot()["command_shortcuts"]["검측"], "점수")

    def test_dynamic_bundle_single_prompt_and_five_ten_thousand_limits(self):
        self.instrument()
        self.raw("검증기 2 검측, 검증기 3 검측 해")
        self.assertEqual([event["quantity"] for event in self.events()], [2, 3])
        self.char1.db.action_validation_events = []
        self.char1.change(lambda profile: profile.update(command_shortcuts={
            **{f"a{i}": f"a{i + 1}" for i in range(4)}, "a4": "검증기 2 검측"}))
        self.raw("a0")
        self.assertEqual(len(self.events()), 1)
        self.char1.change(lambda profile: profile["command_shortcuts"].update(a4="a5", a5="검증기 2 검측"))
        self.raw("a0")
        self.assertEqual(len(self.events()), 1)
        self.assertIn("5단계", " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args))
        self.char1.db.action_validation_events = []
        self.raw(", ".join(["검증기 2 검측"] * 11) + " 해")
        self.assertEqual(len(self.events()), 10)
        self.assertIn("11번째", " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args))
        self.char1.db.action_validation_events = []
        leaf = "검증기 " + "0" * (1000 - len("검증기 2 검측")) + "2 검측"
        self.assertEqual(len(leaf), 1000)
        self.raw(leaf + ", 검증기 2 검측 해")
        self.assertEqual(len(self.events()), 1)
        self.char1.db.action_validation_events = []
        oversized = "검증기 0" + leaf[len("검증기 "):]
        self.assertEqual(len(oversized), 1001)
        self.raw(oversized + ", 검증기 2 검측 해")
        self.assertEqual(self.events(), [])
        self.assertIn("1,000", " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args))
        self.assertIsNone(self.char1.ndb.shortcut_execution)

    def test_unique_formal_name_one_compatibility_never_applies_to_bandage_holes(self):
        from world.item_entities.api import delete_item

        self.instrument()
        unique = self.instrument("고유 검증기", unique=True)
        role = RoleDefinition("provider", (ReferenceKind.OBJECT,))
        self.assertEqual(number_for(descriptor(unique).reference), 2)
        self.assertEqual(select_role(self.char1, role, "고유 검증기 1"), (descriptor(unique).reference,))
        a, b = self.create("bandage"), self.create("bandage")
        delete_item(a)
        item_role = RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER)
        with self.assertRaises(RuleError):
            select_role(self.char1, item_role, "붕대 1")
        self.assertEqual(select_role(self.char1, item_role, "붕대 2"), (descriptor(b).reference,))
        self.instrument("고유 검증기", unique=False)
        with self.assertRaises(RuleError):
            select_role(self.char1, role, "고유 검증기 1")

    def test_indirect_delayed_handler_registration_and_unfinished_result_rollback(self):
        from twisted.internet.task import Clock
        from world.actions.registry import RegistryError, compile_manifest
        from world.actions.schema import PackageManifest
        from world.actions.validation_content import PACKAGE, record

        clock, calls = Clock(), []

        def delayed_helper(context):
            clock.callLater(0, lambda: calls.append(True))

        def indirectly_delayed(context):
            return delayed_helper(context)

        def alternate(handler):
            return replace(PACKAGE, services=tuple(replace(service, handler=handler)
                           if service.id == "validation.quantity_service" else service for service in PACKAGE.services))

        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((alternate(indirectly_delayed),)))
        self.assertEqual(clock.getDelayedCalls(), [])
        self.assertEqual(calls, [])
        pending = [Deferred()]

        def unfinished(context):
            record(context, "unfinished")
            return pending[0]

        index = compile_manifest(PackageManifest((alternate(unfinished),)))
        invocation = from_web(self.payload(), index)
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)
        self.assertFalse(pending[0].called)
        self.assertEqual(self.events(), [])

    def test_private_help_controls_and_guessing_do_not_disclose_or_create_effects(self):
        from world.actions.registry import compile_manifest
        from world.actions.schema import ActionBinding, PackageManifest, VerbDefinition
        from world.actions.validation_content import PACKAGE

        obj = self.instrument()
        hidden = replace(PACKAGE.actions[1], id="validation.private", verb_id="validation.private_verb",
                         public=False, help="숨은 서비스의 내부 안내")
        package = replace(PACKAGE, verbs=(*PACKAGE.verbs, VerbDefinition(hidden.verb_id, "은밀측정")),
                          actions=(*PACKAGE.actions, hidden), bindings=(*PACKAGE.bindings,
                          ActionBinding("validation.private_binding", "validation.instrument", hidden.id,
                                        "validation.quantity_service")))
        index = compile_manifest(PackageManifest((package,)))
        before = list(SelectionNumber.objects.values())
        for _ in range(2):
            self.assertNotIn("숨은 서비스", str(help_entries(index)))
            self.assertNotIn(hidden.id, str(action_controls(self.char1, index)))
        payload = {**self.payload(target=obj), "action_id": hidden.id}
        with self.assertRaises(RuleError) as failure:
            from_web(payload, index)
        self.assertNotIn("숨은 서비스", str(failure.exception))
        self.assertEqual(SelectionNumber.objects.values().count(), len(before))
        self.assertEqual(list(SelectionNumber.objects.values()), before)
        self.assertEqual(self.events(), [])
