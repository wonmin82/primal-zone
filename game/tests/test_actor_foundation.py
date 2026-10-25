"""운영 콘텐츠를 전환하지 않는 Actor 구성·실물 정체성 수직 Fixture."""

from dataclasses import replace
from types import MappingProxyType
from unittest import TestCase
from unittest.mock import patch

from evennia import create_object
from typeclasses.actors import Actor
from typeclasses.world_objects import WorldObject
from world.actions.gateway import ActionResult
from world.actions.registry import compile_manifest
from world.actions.schema import (
    ActionBinding,
    ActionDefinition,
    ArgumentDefinition,
    ContentPackage,
    PackageManifest,
    ProviderDefinition,
    ReferenceKind,
    RoleDefinition,
    ServiceDefinition,
    SyntaxVariant,
    VerbDefinition,
)
from world.actors import content
from world.actors.schema import (
    ActorDefinition,
    ActorPresentation,
    ActorSpawn,
    CapabilityDescriptor,
    Classification,
    WorldObjectDefinition,
)
from world.actors.spawn import ensure_spawn
from world.actors.validation import ActorDefinitionError, validate_definitions
from world.multiplayer import world_change

from tests.base import GameCommandTest


def noop(context):
    return ActionResult()


def fixture():
    presentation = ActorPresentation("대화와 전투를 함께 제공하는 검증 개체다.", "시험을 기다린다.")
    descriptors = {
        "dialogue": CapabilityDescriptor("dialogue", ("dialogue",),
                                         (("dialogue", (ArgumentDefinition("topic"),)),),
                                         ("fixture.dialogue_binding",)),
        "combat": CapabilityDescriptor("combat", ("combat",),
                                       (("combat", (ArgumentDefinition("max_hp", int, minimum=1),)),),
                                       ("fixture.combat_binding",), active_states=("alive",)),
    }
    definition = ActorDefinition("composite", "복합 검증자", Classification.HUMAN, presentation,
                                 capabilities=("dialogue", "combat"),
                                 profiles={"dialogue": {"topic": "검증"}, "combat": {"max_hp": 40}},
                                 defaults={"state": "alive", "hp": 40},
                                 action_provider_id="fixture.actor")
    return definition, descriptors


def action_index():
    kind = getattr(ReferenceKind, "ACTOR", ReferenceKind.OBJECT)
    role = RoleDefinition("provider", (kind,))
    actions = tuple(ActionDefinition(f"fixture.{identity}", f"fixture.{identity}_verb", (role,),
                                    (SyntaxVariant("normal", r"(?P<provider>.+)"),))
                    for identity in ("dialogue", "combat"))
    return compile_manifest(PackageManifest((ContentPackage(
        "fixture.actors", verbs=(VerbDefinition("fixture.dialogue_verb", "검담"),
                                  VerbDefinition("fixture.combat_verb", "검전")),
        actions=actions, services=(ServiceDefinition("fixture.noop", noop, (role,)),),
        bindings=tuple(ActionBinding(f"fixture.{identity}_binding", "fixture.actor",
                                     f"fixture.{identity}", "fixture.noop")
                       for identity in ("dialogue", "combat")),
        providers=(ProviderDefinition("fixture.actor", "복합 검증자", "actor:composite", "fixture:room"),),
    ),)))


class ActorCompositionTests(TestCase):
    def test_sparse_profiles_and_nested_settings_are_immutable(self):
        definition, capabilities = fixture()
        validate_definitions({definition.id: definition}, capabilities, index=action_index())
        with self.assertRaises(TypeError):
            definition.profiles["combat"]["max_hp"] = 1
        dialogue_only = replace(definition, capabilities=("dialogue",),
                                profiles={"dialogue": {"topic": "검증"}}, defaults={})
        validate_definitions((dialogue_only,), capabilities)
        self.assertNotIn("combat", dialogue_only.profiles)

    def test_missing_unknown_or_wrong_profile_is_rejected(self):
        definition, capabilities = fixture()
        invalid = (
            replace(definition, profiles={"dialogue": {"topic": "검증"}}),
            replace(definition, profiles={**definition.profiles, "combat": {"max_hp": True}}),
            replace(definition, profiles={**definition.profiles, "combat": {"max_hp": 0}}),
            replace(definition, profiles={**definition.profiles, "extra": {}}),
        )
        for actor in invalid:
            with self.subTest(actor=actor), self.assertRaises(ActorDefinitionError):
                validate_definitions((actor,), capabilities)

    def test_identity_classification_level_and_ambiguous_names_are_rejected(self):
        definition, capabilities = fixture()
        for actor in (replace(definition, level=True), replace(definition, level=0),
                      replace(definition, classification="human"),
                      replace(definition, defaults={"spawn_id": "override"})):
            with self.subTest(actor=actor), self.assertRaises(ActorDefinitionError):
                validate_definitions((actor,), capabilities)
        other = replace(definition, id="other")
        with self.assertRaises(ActorDefinitionError):
            validate_definitions((definition, other), capabilities,
                                 (ActorSpawn("first", definition.id, "room"),
                                  ActorSpawn("second", other.id, "room")))

    def test_conflicting_capabilities_and_duplicate_binding_ownership_are_rejected(self):
        definition, capabilities = fixture()
        conflict = {**capabilities, "dialogue": replace(capabilities["dialogue"], conflicts=("combat",))}
        with self.assertRaises(ActorDefinitionError):
            validate_definitions((definition,), conflict)
        duplicate = {**capabilities, "combat": replace(capabilities["combat"],
                                                       binding_ids=("fixture.dialogue_binding",))}
        with self.assertRaises(ActorDefinitionError):
            validate_definitions((definition,), duplicate, index=action_index())

    def test_binding_reference_and_provider_are_checked_without_duplicating_services(self):
        definition, capabilities = fixture()
        index = action_index()
        missing = {**capabilities, "combat": replace(capabilities["combat"], binding_ids=("missing.binding",))}
        with self.assertRaises(ActorDefinitionError):
            validate_definitions((definition,), missing, index=index)
        with self.assertRaises(ActorDefinitionError):
            validate_definitions((replace(definition, action_provider_id="different.provider"),),
                                 capabilities, index=index)
        self.assertFalse(hasattr(capabilities["combat"], "handler"))
        self.assertFalse(hasattr(capabilities["combat"], "service_id"))


class ActorRuntimeTests(GameCommandTest):
    def setUp(self):
        super().setUp()
        self.definition, self.capabilities = fixture()
        self.enterContext(patch.object(content, "ACTORS", MappingProxyType({self.definition.id: self.definition})))
        self.enterContext(patch.object(content, "CAPABILITIES", MappingProxyType(self.capabilities)))
        self.spawn = ActorSpawn("fixture_spawn", self.definition.id, "fixture_room")

    def test_composite_actor_runs_each_binding_through_actual_gateway(self):
        from world.actions.gateway import ResultStatus, execute
        from world.actions.resolver import dispatch_text, provided

        self.connect_character(self.char1)
        index = action_index()
        actor = ensure_spawn(self.spawn, self.room1, index=index)
        offered = {binding.id for _, binding in provided(self.char1, index)}
        self.assertEqual(offered, {"fixture.dialogue_binding", "fixture.combat_binding"})
        for name, verb in (("dialogue", "검담"), ("combat", "검전")):
            invocation = dispatch_text(self.char1, index, f"fixture.{name}_verb", actor.key, verb)
            result = execute(self.char1, self.session, invocation, index)
            self.assertEqual(result.status, ResultStatus.SUCCESS)
        old = dispatch_text(self.char1, index, "fixture.combat_verb", actor.key, "검전")
        actor.set_capability_active("combat", False)
        self.assertEqual(execute(self.char1, self.session, old, index).status, ResultStatus.REFUSED)
        dialogue = dispatch_text(self.char1, index, "fixture.dialogue_verb", actor.key, "검담")
        self.assertEqual(execute(self.char1, self.session, dialogue, index).status, ResultStatus.SUCCESS)

    def test_repeat_spawn_preserves_real_identity_current_state_and_location(self):
        actor = ensure_spawn(self.spawn, self.room1, index=action_index())
        actor.db.hp = 7
        actor.db.encounter_generation = 4
        actor.location = self.room2
        same = ensure_spawn(self.spawn, self.room1, index=action_index())
        self.assertIsInstance(same, Actor)
        self.assertEqual((same.pk, same.actor_id, same.spawn_id),
                         (actor.pk, "composite", "fixture_spawn"))
        self.assertEqual((same.db.hp, same.db.encounter_generation, same.location),
                         (7, 4, self.room2))
        self.assertEqual(same.level, 1)
        self.assertEqual(same.classification, Classification.HUMAN)

    def test_capabilities_have_independent_current_activation(self):
        actor = ensure_spawn(self.spawn, self.room1)
        self.assertTrue(actor.capability_active("dialogue"))
        self.assertTrue(actor.capability_active("combat"))
        actor.set_capability_active("combat", False)
        self.assertEqual(actor.capability_binding_ids(), ("fixture.dialogue_binding",))
        self.assertTrue(actor.capability_active("dialogue"))
        actor.set_capability_active("combat", True)
        actor.db.state = "respawning"
        self.assertFalse(actor.capability_active("combat"))
        self.assertTrue(actor.capability_active("dialogue"))
        with self.assertRaises(ActorDefinitionError):
            actor.set_capability_active("absent", True)

    def test_noncombat_actor_has_no_forced_combat_state_or_timer(self):
        definition = replace(self.definition, capabilities=("dialogue",),
                             profiles={"dialogue": {"topic": "검증"}}, defaults={})
        with patch.object(content, "ACTORS", {definition.id: definition}):
            actor = ensure_spawn(self.spawn, self.room1)
            self.assertFalse(actor.attributes.has("hp"))
            self.assertFalse(actor.attributes.has("next_attack_at"))
            self.assertFalse(actor.attributes.has("combatants"))

    def test_spawn_identity_collision_is_not_silently_converted(self):
        create_object(WorldObject, key="잘못된 실물", location=self.room1,
                      tags=((self.spawn.id, "primal_actor_spawn"),))
        with self.assertRaises(ActorDefinitionError):
            ensure_spawn(self.spawn, self.room1)

    def test_failed_spawn_creation_rolls_back_object_and_defaults(self):
        from evennia.objects.models import ObjectDB

        count = ObjectDB.objects.count()
        with self.assertRaises(RuntimeError):
            with world_change():
                ensure_spawn(self.spawn, self.room1)
                raise RuntimeError("controlled")
        self.assertEqual(ObjectDB.objects.count(), count)

    def test_world_object_is_a_boundary_for_facility_presentation_only(self):
        definition = WorldObjectDefinition("fixture_facility", "검증 시설",
                                           ActorPresentation("시설 설명", "벽에 붙어 있다."),
                                           "fixture.facility")
        with patch.object(content, "WORLD_OBJECTS", {definition.id: definition}):
            facility = create_object(WorldObject, key=definition.name, location=self.room1,
                                     attributes=(("world_object_id", definition.id),))
            self.assertEqual(facility.action_provider_definition, "fixture.facility")
            self.assertFalse(facility.attributes.has("hp"))
            self.assertFalse(facility.attributes.has("door_state"))
