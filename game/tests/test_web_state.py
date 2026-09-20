import json
from unittest.mock import Mock, patch

from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse
from typeclasses.parties import invite, respond
from world.bootstrap import build_world
from world.state import multiplayer_state


class WebStateTests(EvenniaCommandTest):
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

    def test_actual_hp_claim_and_party_invitation(self):
        party = invite(self.char1, self.char2, now=100)
        enemy = room_enemies(self.rooms["grass"])[0]
        enemy.engage(self.char1, now=100)
        enemy.db.hp = 17
        outside = multiplayer_state(self.char2, now=101)
        self.assertFalse(outside["enemies"][0]["can_attack"])
        self.assertEqual(outside["invitation"]["party_id"], party.id)
        respond(self.char2, True, now=101)
        inside = multiplayer_state(self.char2, now=101)
        self.assertTrue(inside["enemies"][0]["can_attack"])
        self.assertEqual(inside["enemies"][0]["hp"], 17)
        self.assertFalse(inside["party"]["is_leader"])
        self.assertIsNone(inside["invitation"])
        json.dumps(inside)

    def test_corpse_ground_and_expired_reservation_snapshot(self):
        enemy = room_enemies(self.rooms["grass"])[0]
        rng = Mock()
        rng.random.return_value = 0
        corpse = Corpse.from_enemy(
            enemy, {f"player:{self.char1.id}": {self.char1.id: 10}}, 100, rng
        )
        self.assertFalse(
            multiplayer_state(self.char2, now=101)["corpses"][0]["loot"][0]["can_take"]
        )
        corpse.reconcile(now=130)
        snapshot = multiplayer_state(self.char2, now=221)
        self.assertEqual(snapshot["corpses"], [])
        self.assertEqual(len(snapshot["ground_loot"]), 2)
        self.assertTrue(snapshot["ground_loot"][0]["loot"][0]["can_take"])
        self.assertFalse(snapshot["ground_loot"][0]["loot"][0]["protected"])
        json.dumps(snapshot)

    def test_growth_web_state_matches_rules_and_training_location(self):
        from world import rules

        self.char1.location = self.rooms["dock"]
        self.char1.change(
            lambda profile: rules.allocate_attribute(profile, "constitution", 2, safe=True)
        )
        with patch.object(self.char1, "msg") as message:
            Explorer.push_state(self.char1)
        state = message.call_args.kwargs["pz_state"][0][0]
        self.assertTrue(state["training_available"])
        self.assertEqual(state["growth"]["attribute_points"], 2)
        self.assertEqual((state["hp"], state["max_hp"]), (60, 68))
        self.assertTrue(state["growth"]["skills"][0]["can_learn"])
        json.dumps(state)
        self.char1.location = self.rooms["grass"]
        with patch.object(self.char1, "msg") as message:
            Explorer.push_state(self.char1)
        self.assertFalse(message.call_args.kwargs["pz_state"][0][0]["training_available"])
