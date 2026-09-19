from random import Random
from unittest.mock import Mock, patch

from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse, DroppedLoot, room_loot, take_loot
from typeclasses.parties import invitation_for, invite
from world.bootstrap import build_world
from world.lifecycle import reconcile_world
from world.multiplayer import object_by_id


class LifecycleTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        for player in (self.char1, self.char2):
            player.location = self.rooms["grass"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def test_restart_expired_corpse_respawn_invite_and_protection(self):
        invite(self.char1, self.char2, now=100)
        enemy = room_enemies(self.rooms["grass"])[0]
        enemy.engage(self.char1, now=100)
        enemy.db.hp = 1
        enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        corpse = room_loot(self.rooms["grass"])[0]
        original = [dict(entry) for entry in corpse.db.entries]
        # runtime task가 사라진 상황을 흉내 내고 DB의 객체를 다시 조회한다.
        enemy.ndb.lifecycle_task = None
        corpse.ndb.lifecycle_task = None
        enemy = object_by_id(enemy.id)
        reconcile_world(now=170, restart=True)
        reconcile_world(now=170, restart=True)
        self.assertEqual(Corpse.objects.count(), 0)
        self.assertEqual(DroppedLoot.objects.count(), len(original))
        self.assertEqual(enemy.db.state, "alive")
        self.assertEqual(enemy.db.hp, enemy.db.max_hp)
        self.assertEqual(invitation_for(self.char2, now=170), (None, None))
        self.assertIsNone(self.char1.profile()["combat_target"])
        ground = room_loot(self.rooms["grass"], False)
        self.assertEqual([dict(obj.db.entries[0]) for obj in ground], original)
        reconcile_world(now=223, restart=True)
        take_loot(self.char2, corpse=False, now=223)
        self.assertEqual(self.char2.profile()["inventory"]["scrap"], 1)

    def test_restart_clears_live_and_dangling_combat_without_party_change(self):
        party = invite(self.char1, self.char2, now=100)
        enemy = room_enemies(self.rooms["grass"])[0]
        enemy.engage(self.char1, now=100)
        self.char2.change(lambda profile: profile.update(combat_target=999999))
        enemy.db.combatants = [self.char1.id, self.char2.id, 999999]
        reconcile_world(now=120, restart=True)
        self.assertEqual(list(enemy.db.combatants), [])
        self.assertEqual(dict(enemy.db.threat), {})
        self.assertIsNone(enemy.db.claim)
        self.assertIsNone(self.char2.profile()["combat_target"])
        self.assertEqual(party.state()["leader"], self.char1.id)
