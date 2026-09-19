from random import Random
from unittest.mock import Mock, patch

from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse, DroppedLoot, room_loot, take_loot
from typeclasses.parties import invite, respond
from world.bootstrap import build_world
from world.multiplayer import object_by_id
from world.rules import RuleError


class LootTests(EvenniaCommandTest):
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
        self.enemy = room_enemies(self.rooms["grass"])[0]

    def kill(self, party=False):
        if party:
            group = invite(self.char1, self.char2)
            respond(self.char2, True)
            self.enemy.engage(self.char2, now=100)
            self.enemy.receive_attack(self.char2, now=102.5, rng=Random(1))
        else:
            group = None
        self.enemy.engage(self.char1, now=100)
        self.enemy.db.hp = 1
        rng = Mock()
        rng.randint.return_value = 1
        rng.random.return_value = 0
        self.enemy.receive_attack(self.char1, now=102.5, rng=rng)
        return room_loot(self.rooms["grass"])[0], group, rng

    def test_once_only_death_rng_rewards_and_corpse_visibility(self):
        corpse, _, rng = self.kill()
        self.enemy.receive_attack(self.char1, now=102.5, rng=rng)
        self.enemy.finish_death(self.char1, now=102.5, rng=rng)
        self.assertEqual(Corpse.objects.count(), 1)
        rng.random.assert_called_once()
        self.assertEqual(self.char1.profile()["xp"], 22)
        self.assertNotIn("scrap", self.char1.profile()["inventory"])
        with patch("world.lifecycle.time", return_value=103):
            self.assertIn(corpse.key, self.rooms["grass"].return_appearance(self.char1))
        self.assertEqual(room_enemies(self.rooms["grass"]), [])
        with self.assertRaises(RuleError):
            self.enemy.engage(self.char2, now=103)

    def test_specific_then_all_and_outsider_blocked(self):
        corpse, _, _ = self.kill()
        with self.assertRaises(RuleError):
            take_loot(self.char2, corpse=True, now=103)
        take_loot(self.char1, "scrap", corpse=True, now=103)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 1)
        self.assertEqual(len(corpse.db.entries), 1)
        take_loot(self.char1, corpse=True, now=104)
        self.assertEqual(self.char1.profile()["inventory"]["blade"], 1)
        with self.assertRaises(RuleError):
            take_loot(self.char1, corpse=True, now=104)

    def test_party_round_robin_delivers_to_assignees(self):
        corpse, party, _ = self.kill(party=True)
        self.assertEqual(
            [entry["assigned_player"] for entry in corpse.db.entries],
            [self.char1.id, self.char2.id],
        )
        take_loot(self.char2, corpse=True, now=103)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 1)
        self.assertEqual(self.char2.profile()["inventory"]["blade"], 1)
        self.assertNotIn("scrap", self.char2.profile()["inventory"])
        self.assertEqual(party.state()["round_robin_cursor"], 2)

    def test_decay_preserves_reservation_respawn_preserves_ground_and_ffa(self):
        corpse, _, _ = self.kill()
        entries = list(corpse.db.entries)
        corpse.reconcile(now=132.5)
        corpse.reconcile(now=133)
        self.assertEqual(Corpse.objects.count(), 0)
        self.assertEqual(DroppedLoot.objects.count(), 2)
        self.assertEqual(
            [dict(obj.db.entries[0]) for obj in room_loot(self.rooms["grass"], False)], entries
        )
        with self.assertRaises(RuleError):
            take_loot(self.char2, corpse=False, now=133)
        self.enemy.reconcile(now=147.5)
        self.enemy.reconcile(now=148)
        self.assertEqual(self.enemy.db.state, "alive")
        self.assertEqual(DroppedLoot.objects.count(), 2)
        take_loot(self.char2, "scrap", corpse=False, now=222.5)
        self.assertEqual(self.char2.profile()["inventory"]["scrap"], 1)
        take_loot(self.char2, corpse=False, now=223)
        self.assertEqual(self.char2.profile()["inventory"]["blade"], 1)
        self.assertEqual(DroppedLoot.objects.count(), 0)

    def test_ground_owner_can_collect_before_expiry(self):
        corpse, _, _ = self.kill()
        corpse.reconcile(now=133)
        take_loot(self.char1, "scrap", corpse=False, now=134)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 1)

    def test_raw_item_names_ignore_spaces(self):
        self.kill()
        with (
            patch("typeclasses.loot.time", return_value=103),
            patch("world.lifecycle.time", return_value=103),
        ):
            self.char1.execute_cmd("시체에서 회수 부품 가져")
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 1)

    def test_death_failure_rolls_back_hp_rewards_and_corpse(self):
        self.enemy.engage(self.char1, now=100)
        self.enemy.db.hp = 1
        with patch("typeclasses.loot.build_entries", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual(object_by_id(self.enemy.id).db.state, "alive")
        self.assertEqual(self.enemy.db.hp, 1)
        self.assertEqual(self.char1.profile()["xp"], 0)
        self.assertEqual(Corpse.objects.count(), 0)
        self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual(Corpse.objects.count(), 1)
        self.assertEqual(self.char1.profile()["xp"], 22)

    def test_public_groups_receive_separate_item_rights(self):
        boss = room_enemies(self.rooms["ridge"])[0]
        for player in (self.char1, self.char2):
            player.location = self.rooms["ridge"]
            boss.engage(player, now=100)
        boss.db.contribution = {
            player.id: {"damage": 10, "last_action_at": 102, "group": f"player:{player.id}"}
            for player in (self.char1, self.char2)
        }
        boss.db.hp = 0
        boss.finish_death(self.char1, now=102, rng=Random(1))
        corpse = room_loot(self.rooms["ridge"])[0]
        self.assertEqual(
            {entry["assigned_player"] for entry in corpse.db.entries},
            {self.char1.id, self.char2.id},
        )
        take_loot(self.char1, corpse=True, now=103)
        self.assertEqual(len(corpse.db.entries), 1)
        take_loot(self.char2, corpse=True, now=103)
        self.assertEqual(len(corpse.db.entries), 0)
