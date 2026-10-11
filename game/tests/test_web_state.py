import json
from unittest.mock import Mock, patch

from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse
from typeclasses.parties import invite, respond
from world.state import multiplayer_state

from tests.base import WorldCommandTest


class WebStateTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["grass"]
            player.push_state = Mock()
            self.connect_character(player)
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

    def test_rt45_tactics_succession_requests_and_confirm_snapshot(self):
        from evennia import create_object
        from typeclasses.parties import request_join
        party = invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=101)
        third = create_object(Explorer, key="요청탐사자", location=self.char1.location)
        self.connect_character(third)
        third.push_state = Mock()
        request_join(third, self.char1, now=102)
        party.set_defender(self.char1, self.char2)
        party.dissolve(self.char1, now=102)
        before = multiplayer_state(self.char1, now=103)["party"]
        self.assertTrue(before["confirm_dissolve"])
        self.assertEqual(before["max_size"], 4)
        self.assertEqual(before["join_requests"][0]["id"], third.pk)
        self.assertEqual(before["defender"], {"id": self.char2.pk, "name": self.char2.key, "online": True, "active": False})
        self.assertTrue(multiplayer_state(third, now=103)["join_request"])
        with patch.object(self.char1.sessions, "all", return_value=[]), patch.object(self.char1.sessions, "count", return_value=0):
            state = multiplayer_state(self.char2, now=103)["party"]
            self.assertTrue(state["can_succeed"])
            self.assertFalse(state["leader_online"])
            party.succeed(self.char2, now=104)
        after = multiplayer_state(self.char2, now=104)["party"]
        self.assertTrue(after["is_leader"])
        self.assertEqual(after["defender"]["id"], self.char2.pk)
        self.assertFalse(after["confirm_dissolve"])
        self.assertEqual(after["join_requests"], before["join_requests"])

    def test_rt45_member_buttons_use_member_selector_order_not_global_duplicate_order(self):
        from evennia import create_object
        third = create_object(Explorer, key='동명', location=self.char1.location)
        self.connect_character(third)
        third.push_state = Mock()
        self.char1.key = self.char2.key = '동명'
        party = invite(self.char2, third, now=100)
        respond(third, True, now=101)
        state = multiplayer_state(self.char2, now=102)['party']
        self.assertEqual([row['label'] for row in state['members']], ['동명 1', '동명 2'])
        self.char2.execute_cmd(state['members'][1]['label'] + ' 일행방어')
        self.assertEqual(party.state()['tactics']['defender_id'], third.pk)
        self.char2.execute_cmd(state['members'][1]['label'] + ' 일행리더')
        self.assertEqual(party.state()['leader'], third.pk)
        self.assertIsNone(self.char1.db.party_id)

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
        self.assertEqual(len(snapshot["ground_loot"]), 3)
        currency = next(entry for loot in snapshot["ground_loot"]
                        for entry in loot["loot"] if entry["kind"] == "currency")
        self.assertEqual((currency["id"], currency["quantity"]), ("credits", 8))
        self.assertTrue(currency["can_take"])
        self.assertFalse(currency["protected"])
        self.assertTrue(snapshot["ground_loot"][0]["loot"][0]["can_take"])
        self.assertFalse(snapshot["ground_loot"][0]["loot"][0]["protected"])
        json.dumps(snapshot)

    def test_growth_web_state_matches_rules_and_training_location(self):
        from world import rules

        self.char1.location = self.rooms["training_room"]
        self.char1.change(
            lambda profile: rules.allocate_attribute(profile, "constitution", 2, safe=True)
        )
        with patch.object(self.char1, "msg") as message:
            Explorer.push_state(self.char1)
        state = message.call_args.kwargs["pz_state"][0][0]
        self.assertTrue(state["training_available"])
        self.assertEqual(state["growth"]["attribute_points"], 2)
        self.assertEqual((state["hp"], state["max_hp"]), (60, 68))
        self.assertFalse(state["growth"]["skills"][0]["can_learn"])
        self.assertNotIn("proficiencies", state["growth"])
        self.assertIn("strength", state["training_controls"])
        json.dumps(state)
        self.char1.location = self.rooms["grass"]
        with patch.object(self.char1, "msg") as message:
            Explorer.push_state(self.char1)
        self.assertFalse(message.call_args.kwargs["pz_state"][0][0]["training_available"])
