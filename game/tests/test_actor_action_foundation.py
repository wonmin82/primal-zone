"""Global과 복합 효과를 실제 Registry·Resolver·Gateway로 실행한다."""

from dataclasses import replace
from unittest.mock import patch

from evennia import create_object
from typeclasses.actors import Actor
from world.actions.effects import run_effect
from world.actions.gateway import ActionResult, ResultStatus, execute, from_web
from world.actions.registry import RegistryError, compile_manifest
from world.actions.resolver import ActionInvocation, dispatch_text, provided
from world.actions.schema import (
    ActionBinding,
    ActionDefinition,
    Completion,
    ContentPackage,
    EffectDefinition,
    EntitySource,
    ExecutionPolicy,
    GlobalSource,
    PackageManifest,
    ReferenceKind,
    RoleDefinition,
    ScopeRoot,
    ServiceDefinition,
    SyntaxVariant,
    VerbDefinition,
)
from world.actors.schema import ActorDefinition, ActorPresentation, Classification
from world.item_entities import api as item_api
from world.selection_numbers.api import descriptor

from tests.base import GameCommandTest
from tests.item_entity_fixture import NativeItemTest


def read(context):
    return ActionResult(messages=("조회",))


def read_target(context):
    return ActionResult(messages=tuple([str(target.pk) for target in context.roles["target"]]))


def forbidden_write(context):
    context.caller.db.foundation_value = 100
    return ActionResult(changed=True)


def failing_write(context):
    context.caller.db.foundation_value = 100
    return ActionResult(ResultStatus.REFUSED, ("거절",))


def grant_once(context):
    if context.caller.db.foundation_done:
        return ActionResult(duplicate=True)
    context.caller.db.foundation_value = (context.caller.db.foundation_value or 0) + 1
    context.caller.db.foundation_done = True
    return ActionResult(changed=True, completion=Completion.ACCEPTED)


def refused_dialogue(context):
    speech = run_effect(context, "speech", read)
    quest = run_effect(context, "quest", failing_write)
    return ActionResult(messages=speech.messages + quest.messages)


def rewarded_dialogue(context):
    run_effect(context, "speech", read)
    run_effect(context, "quest", grant_once)
    return ActionResult()


def package(handler=read, *, policy=ExecutionPolicy.READ_ONLY, effects=()):
    return ContentPackage("foundation.global", verbs=(VerbDefinition("foundation.inspect_verb", "검조회"),),
        actions=(ActionDefinition("foundation.inspect", "foundation.inspect_verb", (), (SyntaxVariant("normal", ""),)),),
        services=(ServiceDefinition("foundation.service", handler, policy=policy, effects=effects),),
        bindings=(ActionBinding("foundation.binding", "", "foundation.inspect", "foundation.service",
                                source=GlobalSource(ScopeRoot.CURRENT_ROOM)),))


class ActorActionFoundationTests(GameCommandTest):
    def setUp(self):
        super().setUp()
        self.connect_character(self.char1)

    def invoke(self, declaration):
        index = compile_manifest(PackageManifest((declaration,)))
        invocation = dispatch_text(self.char1, index, "foundation.inspect_verb", "", "검조회")
        return execute(self.char1, self.session, invocation, index)

    def test_providerless_global_text_and_web_share_authenticated_gateway(self):
        index = compile_manifest(PackageManifest((package(),)))
        invocation = dispatch_text(self.char1, index, "foundation.inspect_verb", "", "검조회")
        self.assertEqual(invocation.roles, ())
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.SUCCESS)
        web = from_web({"action_id": invocation.action_id, "variant": "normal", "roles": {},
                        "request_id": "web:1"}, index)
        self.assertEqual(execute(self.char1, self.session, web, index).messages, ("조회",))
        self.session.puppet = self.char2
        self.assertEqual(execute(self.char1, self.session, web, index).status, ResultStatus.REFUSED)

    def test_global_current_room_is_not_provided_without_room(self):
        index = compile_manifest(PackageManifest((package(),)))
        self.char1.location = None
        self.assertEqual(provided(self.char1, index), ())
        invocation = ActionInvocation("foundation.inspect", "normal", ())
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)

    def test_read_only_blocks_real_persistent_write_and_restores_cache(self):
        self.char1.db.foundation_value = 5
        result = self.invoke(package(forbidden_write))
        self.assertNotEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(self.char1.db.foundation_value, 5)

    def test_state_change_refusal_rolls_back_persistent_and_cached_value(self):
        self.char1.db.foundation_value = 5
        result = self.invoke(package(failing_write, policy=ExecutionPolicy.STATE_CHANGE))
        self.assertEqual(result.status, ResultStatus.REFUSED)
        self.assertEqual(self.char1.db.foundation_value, 5)

    def test_speech_success_survives_quest_refusal(self):
        self.char1.db.foundation_value = 5
        result = self.invoke(package(refused_dialogue, effects=(EffectDefinition("speech", ExecutionPolicy.READ_ONLY),
                                                               EffectDefinition("quest", ExecutionPolicy.STATE_CHANGE))))
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual([effect.status for effect in result.effects], [ResultStatus.SUCCESS, ResultStatus.REFUSED])
        self.assertEqual(self.char1.db.foundation_value, 5)

    def test_completed_reward_survives_request_memory_loss_without_double_grant(self):
        declaration = package(rewarded_dialogue, effects=(EffectDefinition("speech", ExecutionPolicy.READ_ONLY),
                                                         EffectDefinition("quest", ExecutionPolicy.STATE_CHANGE)))
        first, second = self.invoke(declaration), self.invoke(declaration)
        self.assertEqual((first.status, second.status), (ResultStatus.SUCCESS, ResultStatus.SUCCESS))
        self.assertEqual(self.char1.db.foundation_value, 1)
        self.assertEqual(first.effects[1].completion, Completion.ACCEPTED)
        self.assertTrue(second.effects[1].duplicate)

    def test_invalid_source_roots_provider_and_duplicate_definitions_fail_registration(self):
        original = package()
        invalid = (
            replace(original, bindings=(replace(original.bindings[0], source=GlobalSource(ScopeRoot.PROVIDER)),)),
            replace(original, bindings=(replace(original.bindings[0], provider_definition="missing.provider", source=None),)),
            replace(original, actions=original.actions * 2),
            replace(original, actions=(replace(original.actions[0], roles=(
                RoleDefinition("target", (ReferenceKind.ROOM,), scope_root=ScopeRoot.ROLE, root_role="target"),)),)),
        )
        for declaration in invalid:
            with self.subTest(declaration=declaration), self.assertRaises(RegistryError):
                compile_manifest(PackageManifest((declaration,)))

    def test_explicit_entity_source_requires_registered_provider_even_with_empty_table(self):
        original = package()
        action = replace(original.actions[0], roles=(RoleDefinition("provider", (ReferenceKind.OBJECT,)),))
        explicit = ActionBinding("foundation.binding", "missing.provider", action.id, original.services[0].id,
                                 source=EntitySource("missing.provider"))
        declaration = replace(original, actions=(action,), bindings=(explicit,))
        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((declaration,)))
        # 기존 positional 선언의 Provider 테이블 생략 호환은 Global과 구별해 보존한다.
        positional = ActionBinding("foundation.binding", "missing.provider", action.id, original.services[0].id)
        compile_manifest(PackageManifest((replace(declaration, bindings=(positional,)),)))

    def test_completion_is_independent_from_status_and_rejects_unknown_values(self):
        self.assertEqual(ActionResult(ResultStatus.REFUSED, completion=Completion.COMPLETED).completion,
                         Completion.COMPLETED)
        for invalid in ("accepted", "later", None):
            with self.subTest(completion=invalid), self.assertRaises(ValueError):
                ActionResult(completion=invalid)

    def actor_target(self):
        definition = ActorDefinition("foundation.target", "검증대상", Classification.HUMAN,
                                     ActorPresentation("행동 대상이다.", "서 있다."))
        self.enterContext(patch("world.actors.content.ACTORS", {definition.id: definition}))
        return create_object(Actor, key=definition.name, location=self.char1.location,
                             attributes=[("actor_id", definition.id), ("spawn_id", "foundation.target_spawn")])

    def targeted_global(self, *, nested=False):
        original = package(read_target)
        target = RoleDefinition("target", (ReferenceKind.ACTOR,), scope_root=ScopeRoot.CURRENT_ROOM)
        root = GlobalSource(ScopeRoot.CURRENT_ROOM)
        roles = (target,)
        if nested:
            anchor = RoleDefinition("anchor", (ReferenceKind.ROOM,), required=False,
                                    scope_root=ScopeRoot.CURRENT_ROOM)
            target = replace(target, scope_root=ScopeRoot.ROLE, root_role="anchor")
            # 선언 순서는 의존 순서와 달라도 Resolver가 올바르게 확정한다.
            roles = (target, anchor)
            root = GlobalSource(ScopeRoot.ROLE, "target")
        return replace(original,
                       actions=(replace(original.actions[0], roles=roles,
                                        variants=(SyntaxVariant("normal", r"(?P<target>.+)"),)),),
                       bindings=(replace(original.bindings[0], source=root),))

    def test_global_actor_target_root_resolves_and_revalidates_visibility_and_movement(self):
        actor = self.actor_target()
        index = compile_manifest(PackageManifest((self.targeted_global(),)))
        invocation = dispatch_text(self.char1, index, "foundation.inspect_verb", actor.key, "검조회")
        reference = descriptor(actor).reference
        self.assertEqual(dict(invocation.roles)["target"], (reference,))
        self.assertEqual(execute(self.char1, self.session, invocation, index).messages, (str(actor.pk),))
        actor.locks.add("view:false()")
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)
        actor.locks.add("view:true()")
        actor.location = self.room2
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)

    def test_nested_global_role_root_is_provided_and_text_web_resolve_same_actor(self):
        actor = self.actor_target()
        index = compile_manifest(PackageManifest((self.targeted_global(nested=True),)))
        self.assertEqual(len(provided(self.char1, index)), 1)
        invocation = dispatch_text(self.char1, index, "foundation.inspect_verb", actor.key, "검조회")
        payload = {"action_id": invocation.action_id, "variant": invocation.variant_id,
                   "request_id": "nested-root", "roles": {
                       name: [{"kind": str(ref.kind), "identity": ref.identity, "scope_id": ref.scope_id}
                              for ref in refs] for name, refs in invocation.roles}}
        web = from_web(payload, index)
        self.assertEqual(dict(web.roles), dict(invocation.roles))
        self.assertEqual(execute(self.char1, self.session, web, index).messages, (str(actor.pk),))
        actor.location = self.room2
        self.assertEqual(provided(self.char1, index), ())
        self.assertEqual(execute(self.char1, self.session, web, index).status, ResultStatus.REFUSED)


class GlobalItemRootTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.connect_character(self.char1)

    def test_caller_item_root_rejects_stale_ownership_without_substitution(self):
        item = self.create("bandage", quantity=2)
        original = package(read_target)
        role = RoleDefinition("target", (ReferenceKind.ITEM,), scope_root=ScopeRoot.CALLER)
        declaration = replace(original, actions=(replace(original.actions[0], roles=(role,),
                               variants=(SyntaxVariant("normal", r"(?P<target>.+)"),)),),
                               bindings=(replace(original.bindings[0], source=GlobalSource(ScopeRoot.CALLER)),))
        index = compile_manifest(PackageManifest((declaration,)))
        invocation = dispatch_text(self.char1, index, "foundation.inspect_verb", "붕대", "검조회")
        self.assertEqual(execute(self.char1, self.session, invocation, index).messages, (str(item.pk),))
        item_api.move_item(item, location_kind="inventory", owner_object=self.char2)
        replacement = self.create("bandage", quantity=2)
        self.assertNotEqual(item.pk, replacement.pk)
        self.assertEqual(execute(self.char1, self.session, invocation, index).status, ResultStatus.REFUSED)
