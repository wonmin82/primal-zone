from random import Random
from unittest.mock import Mock, patch

from evennia import create_object
from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.parties import invite, respond
from world.bootstrap import build_world
from world.rules import RuleError


class RewardTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        self.players = [self.char1, self.char2] + [
            create_object(Explorer, key=f"기여탐사자{i}") for i in range(3)
        ]
        for player in self.players:
            player.location = self.rooms["grass"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        self.enterContext(patch("typeclasses.enemies.delay"))
        self.enterContext(patch("typeclasses.explorers.delay"))
        self.enemy = room_enemies(self.rooms["grass"])[0]

    def party(self, leader, member):
        result = invite(leader, member)
        respond(member, True)
        return result

    def test_claim_party_equal_rewards_and_outsider_rejected(self):
        self.party(self.char1, self.char2)
        for player in (self.char1, self.char2):
            self.enemy.engage(player, now=100)
        with self.assertRaises(RuleError):
            self.enemy.engage(self.players[2], now=100)
        self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.enemy.db.hp = 1
        self.enemy.receive_attack(self.char2, now=102.5, rng=Random(1))
        for player in (self.char1, self.char2):
            self.assertEqual((player.profile()["xp"], player.profile()["credits"]), (11, 24))
        self.assertEqual(self.players[2].profile()["xp"], 0)

    def test_claim_timeout_and_flee_release(self):
        self.enemy.engage(self.char1, now=100)
        self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.enemy.reconcile(now=117.5)
        self.assertIsNone(self.enemy.db.claim)
        self.assertIsNone(self.char1.profile()["combat_target"])
        self.assertEqual(self.enemy.db.hp, 24)
        self.enemy.engage(self.char2, now=118)
        self.char2.leave_combat()
        self.assertIsNone(self.enemy.db.claim)

    def test_inactive_party_member_has_no_reward(self):
        self.party(self.char1, self.char2)
        self.enemy.engage(self.char1, now=100)
        self.enemy.engage(self.char2, now=100)
        self.enemy.db.hp = 1
        self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual(self.char1.profile()["xp"], 22)
        self.assertEqual(self.char2.profile()["xp"], 0)

    def test_public_two_parties_and_eligible_quest_credit(self):
        first = self.party(self.players[0], self.players[1])
        second = self.party(self.players[2], self.players[3])
        boss = room_enemies(self.rooms["ridge"])[0]
        for player in self.players:
            player.location = self.rooms["ridge"]
            boss.engage(player, now=100)
        boss.db.contribution = {
            self.players[0].id: {"damage": 30, "last_action_at": 105, "group": f"party:{first.id}"},
            self.players[1].id: {"damage": 10, "last_action_at": 105, "group": f"party:{first.id}"},
            self.players[2].id: {
                "damage": 10,
                "last_action_at": 105,
                "group": f"party:{second.id}",
            },
            self.players[3].id: {
                "damage": 10,
                "last_action_at": 105,
                "group": f"party:{second.id}",
            },
            self.players[4].id: {
                "damage": 1000,
                "last_action_at": 80,
                "group": f"player:{self.players[4].id}",
            },
        }
        boss.db.hp = 0
        boss.finish_death(self.char1, now=105, rng=Random(1))
        self.assertEqual([p.profile()["xp"] for p in self.players], [44, 43, 22, 21, 0])
        self.assertEqual(sum(p.profile()["credits"] - 20 for p in self.players), 50)
        self.assertTrue(all(p.profile()["quests"]["radio_tower"]["boss_defeated"] for p in self.players[:4]))
        self.assertFalse(self.players[4].profile()["quests"]["radio_tower"]["boss_defeated"])

    def test_party_departure_removes_combat_and_contribution(self):
        party = self.party(self.char1, self.char2)
        self.enemy.engage(self.char2, now=100)
        self.enemy.receive_attack(self.char2, now=102.5, rng=Random(1))
        party.remove_member(self.char2)
        self.assertIsNone(self.char2.profile()["combat_target"])
        self.assertNotIn(self.char2.id, self.enemy.db.contribution)
