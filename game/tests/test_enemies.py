from time import time

from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import Enemy, room_enemies
from typeclasses.explorers import Explorer
from world.bootstrap import build_world
from world.content import ROOMS


class EnemySpawnTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def test_idempotent_bootstrap_preserves_hp_and_state(self):
        rooms = build_world()
        enemy = room_enemies(rooms["grass"])[0]
        enemy.db.hp = 7
        enemy.db.state = "respawning"
        identity = enemy.id
        build_world()
        self.assertEqual(Enemy.objects.count(), sum(len(room["enemies"]) for room in ROOMS.values()))
        again = room_enemies(rooms["grass"], alive_only=False)[0]
        self.assertEqual((again.id, again.db.hp, again.db.state), (identity, 7, "respawning"))

    def test_same_species_independent_and_appearance_alive_only(self):
        rooms = build_world()
        first, second = (room_enemies(rooms[key])[0] for key in ("grass", "wreck"))
        self.assertNotEqual(first.id, second.id)
        first.db.hp = 2
        self.assertEqual(second.db.hp, 24)
        self.assertIn(first, rooms["grass"].contents)
        self.assertIn(first.key, rooms["grass"].return_appearance(self.char1))
        first.db.state = "respawning"
        first.db.respawn_at = time() + 100
        # 살아 있는 적의 의미 조각이 사라지는지 확인한다.
        output = rooms["grass"].return_appearance(self.char1)
        self.assertNotIn("hostile", [part["role"] for part in output.segments])
