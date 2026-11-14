from time import time

from evennia import create_object
from typeclasses.actors import Actor
from typeclasses.explorers import Explorer
from world.actors.spawn import audit_registered_spawns
from world.actors.validation import ActorDefinitionError
from world.bootstrap import build_world
from world.content import ROOMS
from world.shared_combat import room_enemies

from tests.base import GameCommandTest


class EnemySpawnTests(GameCommandTest):
    character_typeclass = Explorer

    def test_legacy_spawn_blocks_bootstrap_before_creating_actors(self):
        legacy = create_object("typeclasses.enemies.Enemy", key="기존 적", location=self.room1,
                               tags=(("grass:scavenger", "primal_spawn"),))
        legacy.db.hp = 7
        before = set(Actor.objects.values_list("pk", flat=True))
        with self.assertRaises(ActorDefinitionError):
            build_world()
        self.assertEqual(set(Actor.objects.values_list("pk", flat=True)), before)
        self.assertEqual(legacy.db.hp, 7)
        self.assertEqual(legacy.location, self.room1)

    def test_legacy_npc_blocks_bootstrap_without_creating_replacement(self):
        legacy = create_object("typeclasses.interactables.Commander", key="기존 대장", location=self.room1,
                               tags=(("commander", "primal_interactable"),))
        before = set(Actor.objects.values_list("pk", flat=True))
        with self.assertRaisesRegex(ActorDefinitionError, "이전 NPC"):
            build_world()
        self.assertEqual(set(Actor.objects.values_list("pk", flat=True)), before)
        self.assertEqual(legacy.location, self.room1)
        self.assertTrue(legacy.tags.has("commander", category="primal_interactable"))

    def test_untagged_legacy_actor_is_detected_without_mutation(self):
        legacy = create_object("typeclasses.enemies.Enemy", key="이전 적", location=self.room1)
        legacy.db.hp = 7
        self.assertNotIn(legacy, room_enemies(self.room1, alive_only=False))
        with self.assertRaisesRegex(ActorDefinitionError, "이전 적"):
            build_world()
        self.assertEqual(legacy.db.hp, 7)
        self.assertEqual(legacy.location, self.room1)

    def test_idempotent_bootstrap_preserves_hp_and_state(self):
        rooms = build_world()
        enemy = room_enemies(rooms["grass"])[0]
        self.assertFalse(enemy.access(self.char1, "delete"))
        enemy.hp = 7
        enemy.db.state = "respawning"
        identity = enemy.id
        build_world()
        self.assertEqual(sum(actor.supports_shared_combat for actor in Actor.objects.all()), sum(len(room["enemies"]) for room in ROOMS.values()))
        again = room_enemies(rooms["grass"], alive_only=False)[0]
        self.assertEqual((again.id, again.hp, again.db.state), (identity, 7, "respawning"))

    def test_spawn_audit_detects_mismatched_identity(self):
        rooms = build_world()
        self.assertEqual(audit_registered_spawns(), [])
        actor = room_enemies(rooms["grass"])[0]
        actor.db.spawn_id = "wrong"
        self.assertIn(f"Actor Spawn 정체성 불일치: #{actor.pk}", audit_registered_spawns())

    def test_bootstrap_rejects_unregistered_spawn_without_changing_rooms(self):
        rooms = build_world()
        room = rooms["grass"]
        actor = room_enemies(room)[0]
        actor.tags.add("unknown", category="primal_actor_spawn")
        room.key = "복구 전 이름"

        with self.assertRaises(ActorDefinitionError):
            build_world()
        self.assertEqual(room.key, "복구 전 이름")

    def test_same_species_independent_and_appearance_alive_only(self):
        rooms = build_world()
        first, second = (room_enemies(rooms[key])[0] for key in ("grass", "wreck"))
        self.assertNotEqual(first.id, second.id)
        first.hp = 2
        self.assertEqual(second.hp, 24)
        self.assertIn(first, rooms["grass"].contents)
        self.assertIn(first.key, rooms["grass"].return_appearance(self.char1))
        first.db.state = "respawning"
        first.db.respawn_at = time() + 100
        # 살아 있는 적의 의미 조각이 사라지는지 확인한다.
        output = rooms["grass"].return_appearance(self.char1)
        self.assertNotIn("hostile", [part["role"] for part in output.segments])
