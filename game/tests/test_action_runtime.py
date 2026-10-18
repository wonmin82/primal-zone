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
    def test_intra_action_overlap_is_rejected_before_service_or_db_changes(self):
        from world.actions.registry import RegistryError, compile_manifest
        from world.actions.schema import PackageManifest, SyntaxVariant
        from world.actions.validation_content import PACKAGE

        self.instrument()
        invalid = replace(PACKAGE.actions[1], variants=(SyntaxVariant("general", r"(?P<provider>.+)"),
                                                       SyntaxVariant("korean", r"(?P<provider>[가-힣]+)")))
        package = replace(PACKAGE, actions=tuple(invalid if a.id == invalid.id else a for a in PACKAGE.actions))
        before = list(SelectionNumber.objects.values()), self.events()
        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((package,)))
        self.assertEqual((list(SelectionNumber.objects.values()), self.events()), before)

    def test_source_normal_all_variants_execute_once_with_stable_roles(self):
        from world.actions.gateway import ExecutionContext

        station = self.instrument()
        for count in (1, 3):
            corpses = [self.corpse() for _ in range(count)]
            for external in (True, False):
                for all_sources in (False, True):
                    command = ("모든 " if all_sources else "") + "시체에서" + (" 검증기" if external else "") + " 채록"
                    invocation = dispatch_text(self.char1, self.index, "validation.sources", command.rsplit(" ", 1)[0], "채록")
                    self.assertEqual(invocation.action_id, "validation.external_sources" if external else "validation.self_sources")
                    self.assertEqual(invocation.variant_id, "all" if all_sources else "normal")
                    before = len(self.events())
                    # 실제 Context 생성/Service는 그대로 실행하고 Binding 식별자만 관측한다.
                    with patch("world.actions.gateway.ExecutionContext", wraps=ExecutionContext) as contexts:
                        self.raw(command)
                    contexts.assert_called_once()
                    service_id = "validation.external_source_service" if external else "validation.self_source_service"
                    self.assertEqual(contexts.call_args.args[3].service_id, service_id)
                    self.assertEqual(len(self.events()), before + 1, command)
                    event = self.events()[-1]
                    sources = corpses if all_sources else corpses[:1]
                    ids = [str(obj.pk) for obj in sources]
                    self.assertEqual(event["variant"], "all" if all_sources else "normal")
                    self.assertEqual(event["service"], "sources")
                    self.assertEqual(event["roles"]["source"], ids)
                    self.assertEqual(event["roles"]["provider"], [str(station.pk)] if external else ids)
                    self.assertEqual(dict(invocation.roles)["source"], tuple(descriptor(source).reference for source in sources))
                    self.assertEqual(event["quantity"], len(ids))
            for corpse in corpses:
                corpse.delete()

    def test_source_variants_reject_missing_or_denied_without_effects(self):
        station = self.instrument()
        for command in ("시체에서 검증기 채록", "모든 시체에서 검증기 채록", "시체에서 채록", "모든 시체에서 채록"):
            self.raw(command)
            self.assertEqual(self.events(), [])
        corpse = self.corpse()
        station.locks.add("call:false()")
        corpse.locks.add("call:false()")
        for command in ("시체에서 검증기 채록", "모든 시체에서 검증기 채록", "시체에서 채록", "모든 시체에서 채록"):
            self.raw(command)
            self.assertEqual(self.events(), [])

    def test_all_prefix_alias_cannot_create_a_second_normal_invocation(self):
        self.instrument()
        corpse = self.corpse()
        corpse.aliases.add("모든 시체")
        for command in ("모든 시체에서 검증기 채록", "모든 시체에서 채록"):
            before = len(self.events())
            self.raw(command)
            self.assertEqual(len(self.events()), before + 1)
            self.assertEqual(self.events()[-1]["variant"], "all")
            self.assertEqual(self.events()[-1]["roles"]["source"], [str(corpse.pk)])

    def test_runtime_rejects_ambiguous_variants_even_if_index_is_corrupted(self):
        from types import MappingProxyType

        from world.actions.schema import SyntaxVariant

        self.instrument()
        # 등록을 우회하는 운영 API가 아니라 손상된 Index에 대한 방어를 시험한다.
        action = replace(self.index.actions["validation.object"], variants=(
            SyntaxVariant("general", r"(?P<provider>.+)"), SyntaxVariant("korean", r"(?P<provider>[가-힣]+)")))
        index = replace(self.index, actions=MappingProxyType({**self.index.actions, action.id: action}))
        with patch("commands.action_command.get_index", return_value=index):
            self.raw("검증기 검측")
        self.assertEqual(self.events(), [])
        self.assertIn("명확하게", " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args))

    def test_normal_confirmed_text_variants_preserve_confirmation_and_single_effect(self):
        obj = self.instrument()
        self.raw("검증기 검측")
        self.assertEqual(self.events(), [])
        self.raw("검증기 검측 확정")
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.events()[0]["variant"], "confirmed")
        self.assertEqual(self.events()[0]["service"], "object")
        self.assertEqual(self.events()[0]["roles"]["provider"], [str(obj.pk)])

    def test_regex_distinct_literals_execute_the_declared_service(self):
        from world.actions.registry import compile_manifest
        from world.actions.schema import (
            ActionBinding,
            ContentPackage,
            PackageManifest,
            ServiceDefinition,
            SyntaxVariant,
        )
        from world.actions.validation_content import PACKAGE, record

        def first_service(context):
            return record(context, "regex.first")

        def second_service(context):
            return record(context, "regex.second")

        obj = self.instrument("첫 검증기")
        obj.aliases.add("둘 검증기")
        actions = tuple(replace(PACKAGE.actions[1], id=f"regex.action_{index}",
                                variants=(SyntaxVariant("normal", f"(?P<provider>{name})"),))
                        for index, name in enumerate(("첫 검증기", "둘 검증기")))
        services = tuple(ServiceDefinition(f"regex.service_{index}", callback, actions[index].roles)
                         for index, callback in enumerate((first_service, second_service)))
        package = ContentPackage("regex.fixture", verbs=(PACKAGE.verbs[0],), actions=actions, services=services,
                                 bindings=tuple(ActionBinding(f"regex.binding_{index}", "validation.instrument", action.id,
                                                              services[index].id) for index, action in enumerate(actions)))
        index = compile_manifest(PackageManifest((package,)))
        for name, expected in (("첫 검증기", "regex.first"), ("둘 검증기", "regex.second")):
            invocation = dispatch_text(self.char1, index, "validation.measure", name, "검측")
            self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.SUCCESS)
            self.assertEqual(self.events()[-1]["service"], expected)
            self.assertEqual(self.events()[-1]["roles"]["provider"], [str(obj.pk)])
        self.assertEqual(len(self.events()), 2)

    def test_regex_collision_registration_has_no_db_or_service_effect(self):
        from world.actions.registry import RegistryError, compile_manifest
        from world.actions.schema import (
            ActionBinding,
            ContentPackage,
            PackageManifest,
            SyntaxVariant,
        )
        from world.actions.validation_content import PACKAGE

        self.instrument()
        actions = tuple(replace(PACKAGE.actions[1], id=f"regex.action_{index}",
                                variants=(SyntaxVariant("normal", f"(?P<provider>{pattern})"),))
                        for index, pattern in enumerate((".+", "[가-힣]+")))
        package = ContentPackage("regex.fixture", verbs=(PACKAGE.verbs[0],), actions=actions,
                                 services=(PACKAGE.services[1],),
                                 bindings=tuple(ActionBinding(f"regex.binding_{index}", "validation.instrument", action.id,
                                                              PACKAGE.services[1].id) for index, action in enumerate(actions)))
        before = list(SelectionNumber.objects.values()), self.char1.profile_snapshot(), self.events()
        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((package,)))
        self.assertEqual((list(SelectionNumber.objects.values()), self.char1.profile_snapshot(), self.events()), before)

    def test_regex_typed_argument_ambiguity_never_executes_first_service(self):
        self.instrument()
        self.raw("검증기 1 검측")
        self.assertEqual(self.events(), [])
        self.assertIn("명확하게", " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args))

    def test_review_storage_is_not_a_generic_item_target(self):
        from world.item_entities.api import create_item
        stored = create_item("bandage", location_kind="personal_storage", owner_object=self.char1)
        role = RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER)
        with self.assertRaises(RuleError):
            select_role(self.char1, role, "붕대")
        owned = self.create("bandage")
        self.assertEqual(select_role(self.char1, role, "붕대"), (descriptor(owned).reference,))
        self.assertNotEqual(descriptor(stored).scope_id, descriptor(owned).scope_id)
        stale = from_web({"action_id": "validation.item", "variant": "normal", "request_id": "remote-storage",
                          "roles": {name: [reference_json(descriptor(stored).reference)]
                                    for name in ("provider", "subject")}}, self.index)
        self.assertEqual(execute(self.char1, self.session, stale, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.events(), [])

    def test_review_storage_context_and_stale_web_access(self):
        from typeclasses.interactables import Container, PersonalLocker
        from world.actions.registry import compile_manifest
        from world.actions.resolver import role_records
        from world.actions.schema import (
            ActionBinding,
            PackageManifest,
            SyntaxVariant,
            TargetScope,
            VerbDefinition,
        )
        from world.actions.validation_content import PACKAGE
        from world.item_entities.api import create_item

        personal = create_object(PersonalLocker, key="개인 검증함", location=self.char1.location,
                                 attributes=[("action_provider_id", "validation.instrument")])
        shared = create_object(Container, key="공용 검증함", location=self.char1.location,
                               attributes=[("action_provider_id", "validation.instrument")])
        # 운영 Container는 클래스 선언을 사용한다. 이 격리 콘텐츠는 명시적으로 별도 Provider다.
        personal.action_provider_definition = shared.action_provider_definition = "validation.instrument"
        stored = create_item("bandage", location_kind="personal_storage", owner_object=self.char1)
        public = create_item("bandage", location_kind="shared_storage", owner_object=shared)
        other = create_item("bandage", location_kind="personal_storage", owner_object=self.char2)
        equipped = create_item("test_pistol", location_kind="equipment", owner_object=self.char1, slot="hands")
        role = RoleDefinition("subject", (ReferenceKind.ITEM,), scope=TargetScope.STORAGE)
        action = replace(PACKAGE.actions[3], id="validation.storage", verb_id="validation.storage_verb", provider_from=None,
                         roles=(PACKAGE.actions[1].roles[0], role),
                         variants=(SyntaxVariant("normal", r"(?P<subject>.+)에서 (?P<provider>.+)"),))
        package = replace(PACKAGE, verbs=(*PACKAGE.verbs, VerbDefinition("validation.storage_verb", "보관검측")),
                          actions=(*PACKAGE.actions, action), bindings=(*PACKAGE.bindings,
                          ActionBinding("validation.storage.binding", "validation.instrument", action.id, "validation.item_service")),
                          services=tuple(replace(s, role_kinds=()) if s.id == "validation.item_service" else s for s in PACKAGE.services))
        index = compile_manifest(PackageManifest((package,)))
        refs = {"provider": (descriptor(personal).reference,)}
        self.assertEqual([r.reference for r in role_records(self.char1, role, refs)], [descriptor(stored).reference])
        self.assertNotIn(descriptor(other).reference, [r.reference for r in role_records(self.char1, role, refs)])
        generic = RoleDefinition("subject", (ReferenceKind.ITEM,))
        self.assertIn(descriptor(equipped).reference, [r.reference for r in role_records(self.char1, generic)])
        text = dispatch_text(self.char1, index, action.verb_id, "붕대에서 개인 검증함", "보관검측")
        invocation = from_web({"action_id": action.id, "variant": "normal", "request_id": "storage-review",
                               "roles": {"provider": [reference_json(refs["provider"][0])],
                                         "subject": [reference_json(descriptor(stored).reference)]}}, index)
        self.assertEqual(dict(text.roles), dict(invocation.roles))
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.SUCCESS)
        self.assertEqual(self.events()[-1]["roles"]["subject"], [str(stored.pk)])
        for denied in ("call:false()", "view:false()"):
            personal.locks.add(denied)
            before = len(self.events())
            self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)
            self.assertEqual(len(self.events()), before)
            personal.locks.add("call:true();view:true()")
        personal.location = self.room2
        with self.assertRaises(RuleError):
            select_role(self.char1, role, "붕대", bindings=refs)
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)
        refs = {"provider": (descriptor(shared).reference,)}
        self.assertEqual(select_role(self.char1, role, "붕대", bindings=refs), (descriptor(public).reference,))
        shared.locks.add("call:false()")
        with self.assertRaises(RuleError):
            select_role(self.char1, role, "붕대", bindings=refs)

    def test_review_number_labels_do_not_depend_on_action_availability(self):
        first, second = self.instrument(), self.instrument()
        second.db.action_available = False
        rows = [row for row in action_controls(self.char1, self.index)
                if row["action"]["action_id"] == "validation.object"]
        self.assertEqual(rows[0]["label"], "검증기 1 검측")
        self.assertEqual(rows[0]["action"]["roles"]["provider"][0]["identity"], str(first.pk))

    def test_review_inside_context_rejects_siblings_and_stale_parent(self):
        from world.actions.registry import compile_manifest
        from world.actions.resolver import provided
        from world.actions.schema import ActionBinding, PackageManifest, TargetScope, VerbDefinition
        from world.actions.validation_content import PACKAGE
        from world.item_entities.api import create_item, move_item

        first, second = self.create("bandage"), self.create("bandage")
        child = create_item("bandage", location_kind="inside", parent_item=first, socket="supplies")
        sibling = create_item("bandage", location_kind="inside", parent_item=second, socket="supplies")
        role = RoleDefinition("subject", (ReferenceKind.ITEM,), scope=TargetScope.INSIDE)
        action = replace(PACKAGE.actions[3], id="validation.inside", verb_id="validation.inside_verb", provider_from=None,
                         roles=(PACKAGE.actions[3].roles[0], role))
        package = replace(PACKAGE, verbs=(*PACKAGE.verbs, VerbDefinition("validation.inside_verb", "내부검측")),
                          actions=(*PACKAGE.actions, action), bindings=(*PACKAGE.bindings,
                          ActionBinding("validation.inside.binding", "item.bandage", action.id, "validation.item_service")))
        index = compile_manifest(PackageManifest((package,)))
        refs = {"provider": (descriptor(first).reference,)}
        self.assertEqual(select_role(self.char1, role, "붕대", bindings=refs), (descriptor(child).reference,))
        self.assertNotIn(descriptor(child).reference, {ref for ref, _ in provided(self.char1, index)})
        payload = {"action_id": action.id, "variant": "normal", "request_id": "inside-review",
                   "roles": {"provider": [reference_json(refs["provider"][0])],
                             "subject": [reference_json(descriptor(child).reference)]}}
        invocation = from_web(payload, index)
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.SUCCESS)
        self.assertEqual(self.events()[-1]["roles"]["subject"], [str(child.pk)])
        payload["roles"]["subject"] = [reference_json(descriptor(sibling).reference)]
        self.assertEqual(execute(self.char1, self.session, from_web(payload, index), index).status, ResultStatus.REFUSED)
        move_item(child, location_kind="inside", parent_item=second, socket="other")
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)
        self.assertEqual(len(self.events()), 1)

    def test_role_candidate_cache_is_local_and_reuses_scopes_across_definitions(self):
        from world.item_entities.api import move_item_tree
        from world.selection_numbers import api

        bandage, food = self.create("bandage"), self.create("field_ration")
        cache = {}
        roles = [RoleDefinition("subject", (ReferenceKind.ITEM,), definition_ids=(identity,))
                 for identity in ("bandage", "field_ration")]
        with patch.object(api, "records_for", wraps=api.records_for) as records:
            for role, item in zip(roles, (bandage, food), strict=True):
                self.assertEqual(select_role(self.char1, role, item.definition_id, cache=cache),
                                 (descriptor(item).reference,))
            self.assertEqual(records.call_count, 1)
        move_item_tree(bandage, location_kind="inventory", owner_object=self.char2, operation="give")
        with self.assertRaises(RuleError):
            select_role(self.char1, roles[0], "bandage", cache={})

    def test_review_queries_ignore_unrelated_world_growth(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from world.actions.resolver import provided
        from world.item_entities.api import create_item
        from world.selection_numbers import api

        for _ in range(8):
            self.instrument()
        self.create("bandage")

        def observe():
            with patch.object(api, "_entity", wraps=api._entity) as entities:
                with CaptureQueriesContext(connection) as queries:
                    provided(self.char1, self.index)
                    refresh(self.char1)
                    action_controls(self.char1, self.index)
                return len(queries), {str(call.args[1]) for call in entities.call_args_list}, [q["sql"] for q in queries]

        observe()  # 실제 Evennia Attribute/CmdSet의 초기 읽기만 준비한다.
        before, _, _ = observe()
        unrelated = set()
        from evennia.objects.objects import DefaultRoom
        rooms = [create_object(DefaultRoom, key=f"격리 성능 방 {i}") for i in range(4)]
        for i in range(40):
            unrelated.add(str(self.instrument(room=rooms[i % len(rooms)]).pk))
            unrelated.add(str(create_item("bandage", location_kind="inventory", owner_object=self.char2).pk))
        after, touched, sql = observe()
        self.assertFalse(unrelated.intersection(touched))
        self.assertLessEqual(after, before + 2)
        numbered = [q for q in sql if "selection_numbers_selectionnumber" in q and q.lstrip().startswith("SELECT")]
        self.assertTrue(numbered)
        self.assertTrue(all("scope_id" in q and " WHERE " in q for q in numbered))
        print(f"Scope query growth: unrelated=80, before={before}, after={after}, unrelated_resolved=0")

    def test_review_fixed_labels_hidden_members_holes_and_reset(self):
        from dataclasses import replace

        from world.selection_numbers.api import label, records_for
        first, second = self.instrument(), self.instrument()

        def check(expected):
            rows = [r for r in action_controls(self.char1, self.index) if r["action"]["action_id"] == "validation.object"]
            self.assertEqual([r["label"] for r in rows], expected)
            visible = {r.reference: label(r) for r in records_for(self.char1, ReferenceKind.OBJECT)}
            for row in rows:
                payload = row["action"]["roles"]["provider"][0]
                ref = next(r for r in visible if r.identity == payload["identity"])
                self.assertEqual(row["label"], visible[ref] + " 검측")

        check(["검증기 1 검측", "검증기 2 검측"])
        first.db.action_available = False
        check(["검증기 2 검측"])
        first.db.action_available = True
        second.locks.add("view:false()")
        check(["검증기 1 검측"])
        self.assertNotIn(str(second.pk), str([r["action"]["roles"] for r in action_controls(self.char1, self.index)]))
        second.locks.add("view:true()")
        first.delete()
        check(["검증기 2 검측"])
        second.delete()
        fresh = self.instrument()
        check(["검증기 1 검측"])
        self.assertEqual(label(replace(descriptor(fresh), number=1)), "검증기 1")

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
        from types import SimpleNamespace
        pending = SimpleNamespace(result=Deferred())

        def unfinished(context):
            record(context, "unfinished")
            return pending.result

        index = compile_manifest(PackageManifest((alternate(unfinished),)))
        invocation = from_web(self.payload(), index)
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)
        self.assertFalse(pending.result.called)
        self.assertEqual(self.events(), [])
        self.output.assert_not_called()
        self.prompt.assert_not_called()
        self.char1.push_state.reset_mock()
        payload = self.payload(request_id="unfinished-result")
        with patch("world.actions.manifest.get_index", return_value=index):
            pz_action(self.session, payload)
        self.assertEqual(self.events(), [])
        self.char1.push_state.assert_not_called()
        self.prompt.assert_called_once()
        self.assertEqual(sum(getattr(call.args[0], "kind", None) == "prompt"
                             for call in self.output.call_args_list if call.args), 1)

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
