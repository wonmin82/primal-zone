"""Actor 참조의 실물·Scope·번호와 롤백 경계를 실제 격리 DB에서 검증한다."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from evennia import create_object
from typeclasses.actors import Actor
from world.actions.schema import ReferenceKind, TargetReference
from world.actors.schema import ActorDefinition, ActorPresentation, Classification
from world.multiplayer import world_change
from world.selection_numbers.api import descriptor, number_for, records_for, resolve_reference

from tests.base import GameCommandTest


class ActorReferenceTests(GameCommandTest):
    def setUp(self):
        super().setUp()
        definition = ActorDefinition("fixture.actor", "시험개체", Classification.CREATURE,
                                     ActorPresentation("시험 개체다.", "개체가 서 있다."))
        self.enterContext(patch("world.actors.content.ACTORS", {definition.id: definition}))

    def actor(self, spawn):
        return create_object(Actor, key="시험개체", location=self.room1,
                             attributes=[("actor_id", "fixture.actor"), ("spawn_id", spawn)])

    def test_holes_visibility_and_stale_kind_do_not_select_another_actor(self):
        first, second = self.actor("one"), self.actor("two")
        old = descriptor(first).reference
        reference = descriptor(second).reference
        self.assertEqual((old.kind, number_for(old), number_for(reference)), (ReferenceKind.ACTOR, 1, 2))
        first.delete()
        third = self.actor("three")
        self.assertEqual(number_for(descriptor(third).reference), 3)
        second.locks.add("view:false()")
        self.assertEqual(number_for(reference), 2)
        self.assertIsNone(resolve_reference(old))
        for kind in (ReferenceKind.OBJECT, ReferenceKind.ENEMY):
            self.assertIsNone(resolve_reference(TargetReference(kind, reference.identity, reference.scope_id)))
        self.assertEqual(descriptor(second).reference, reference)

    def test_move_and_rollback_preserve_original_identity_and_number(self):
        actor = self.actor("one")
        reference = descriptor(actor).reference
        with self.assertRaises(RuntimeError):
            with world_change():
                actor.location = self.room2
                raise RuntimeError("controlled")
        self.assertEqual(actor.location, self.room1)
        self.assertEqual(descriptor(actor).reference, reference)
        self.assertEqual(number_for(reference), 1)
        actor.location = self.room2
        self.assertIsNone(resolve_reference(reference))
        self.assertEqual(descriptor(actor).reference.identity, reference.identity)
        self.assertEqual(number_for(descriptor(actor).reference), 1)

    def test_definition_identity_cannot_silently_change_number_group(self):
        actor = self.actor("one")
        reference = descriptor(actor).reference
        with self.assertRaises(ValidationError):
            actor.db.actor_id = "fixture.other"
        self.assertEqual(actor.db.actor_id, "fixture.actor")
        with self.assertRaises(ValidationError):
            with world_change():
                actor.attributes.remove("actor_id")
        self.assertEqual(actor.db.actor_id, "fixture.actor")
        self.assertEqual(number_for(reference), 1)
        self.assertEqual([record.reference for record in records_for(self.char1, kinds=(ReferenceKind.ACTOR,))],
                         [reference])
