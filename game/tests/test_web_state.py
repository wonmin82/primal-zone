import json
from unittest.mock import Mock, patch

from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse
from typeclasses.parties import invite, respond
from world.state import multiplayer_state

from tests.base import WorldCommandTest
from tests.loot_entity_fixture import NativeLootTest


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
        rng.randint.side_effect = lambda low, high: low
        corpse = Corpse.from_enemy(
            enemy, {f"player:{self.char1.id}": {self.char1.id: 10}}, 100, rng, backend="item_entities"
        )
        protected = multiplayer_state(self.char2, now=101)
        self.assertEqual(protected["corpses"][0]["loot"], [])
        self.assertIsNone(protected["corpses"][0]["take_action"])
        self.assertIsNone(protected["loot_actions"]["corpses"])
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

    def test_rt23_rt45_succession_snapshot_rebinding_sessions_and_read_only(self):
        from copy import deepcopy

        from evennia.server.models import ServerConfig
        from typeclasses.parties import party_for
        from world.rules import RuleError

        party = invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=101)
        before = deepcopy(party.state())
        leader_sessions = list(self.char1.sessions.all()) * 2
        with patch.object(self.char1.sessions, "all", side_effect=lambda: leader_sessions), \
                patch.object(self.char1.sessions, "count", side_effect=lambda: len(leader_sessions)):
            self.assertFalse(multiplayer_state(self.char2, now=102)["party"]["can_succeed"])
            leader_sessions.pop()
            self.assertFalse(multiplayer_state(self.char2, now=102)["party"]["can_succeed"])
            leader_sessions.clear()
            self.assertTrue(multiplayer_state(self.char2, now=102)["party"]["can_succeed"])
            self.assertFalse(multiplayer_state(self.char1, now=102)["party"]["can_succeed"])
            ServerConfig.objects.conf("server_restart_mode", "reload")
            self.assertFalse(multiplayer_state(self.char2, now=102)["party"]["can_succeed"])
            with self.assertRaises(RuleError):
                party.succeed(self.char2, now=102)
            ServerConfig.objects.conf("server_restart_mode", delete=True)
            self.assertTrue(multiplayer_state(self.char2, now=102)["party"]["can_succeed"])
            leader_sessions.append(self.char2.sessions.all()[0])
            # 다른 캐릭터를 제어하는 세션은 리더의 실제 puppet 세션이 아니다.
            self.assertTrue(multiplayer_state(self.char2, now=102)["party"]["can_succeed"])
            leader_sessions[:] = [self.connect_character(self.char1)]
            self.assertFalse(multiplayer_state(self.char2, now=102)["party"]["can_succeed"])
        self.assertEqual(party.state(), before)
        self.assertIsNone(party.state()["leader_offline_since"])
        self.char2.db.party_id = None
        self.assertIsNone(party_for(self.char2))
        self.assertIsNone(multiplayer_state(self.char2, now=102)["party"])

    def test_rt45_pending_server_time_boundaries_cleanup_and_stale_ttl(self):
        from copy import deepcopy

        from evennia import create_object
        from typeclasses.parties import request_join
        from world.rules import RuleError

        third = create_object(Explorer, key="가입요청자", location=self.char1.location)
        self.connect_character(third)
        third.push_state = Mock()
        party = invite(self.char1, self.char2, now=100)
        request_join(third, self.char1, now=100)
        invite(self.char1, self.char2, now=120)
        request_join(third, self.char1, now=120)
        before = deepcopy(party.state())
        for now in (100, 118, 159.999):
            incoming = multiplayer_state(self.char2, now=now)
            outgoing = multiplayer_state(third, now=now)
            leader = multiplayer_state(self.char1, now=now)
            self.assertEqual(incoming["server_now"], now)
            self.assertEqual(incoming["invitation"]["expires_at"], 160)
            self.assertEqual(outgoing["join_request"]["expires_at"], 160)
            self.assertEqual(leader["party"]["invitations"][0]["expires_at"], 160)
            self.assertEqual(leader["party"]["join_requests"][0]["expires_at"], 160)
        for now in (160, 161):
            self.assertIsNone(multiplayer_state(self.char2, now=now)["invitation"])
            self.assertIsNone(multiplayer_state(third, now=now)["join_request"])
            leader = multiplayer_state(self.char1, now=now)["party"]
            self.assertEqual(leader["invitations"], [])
            self.assertEqual(leader["join_requests"], [])
        self.assertEqual(party.state(), before)  # 조회는 TTL 정리조차 저장하지 않는다.
        with self.assertRaises(RuleError):
            respond(self.char2, True, now=160)
        with self.assertRaises(RuleError):
            party.answer_request(self.char1, third, True, now=160)
        invite(self.char1, self.char2, now=170)
        respond(self.char2, False, now=171)
        self.assertIsNone(multiplayer_state(self.char2, now=171)["invitation"])
        request_join(third, self.char1, now=170)
        party.answer_request(self.char1, third, False, now=171)
        self.assertIsNone(multiplayer_state(third, now=171)["join_request"])
        invite(self.char1, self.char2, now=172)
        request_join(self.char2, self.char1, now=172)
        respond(self.char2, True, now=173)
        snapshot = multiplayer_state(self.char2, now=173)
        self.assertIsNone(snapshot["invitation"])
        self.assertIsNone(snapshot["join_request"])
        request_join(third, self.char1, now=174)
        party.answer_request(self.char1, third, True, now=175)
        self.assertIsNone(multiplayer_state(third, now=175)["join_request"])

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


class NativeLootWebTests(NativeLootTest):
    def test_player_rights_filter_keeps_shared_canonical_numbers_and_typed_entries(self):
        from world import loot_service
        from world.item_entities import api
        from world.selection_numbers.api import descriptor, number_for
        from world.state import loot_controls

        first = self.loot_item("scrap", quantity=3, deadline=110)
        second = api.create_item("scrap", quantity=4, location_kind="corpse_loot", owner_object=self.source)
        loot_service.create_claim(second, reserved_player=self.char2, assigned_player=self.char2,
                                  protection_until=110)
        numbers = [number_for(descriptor(row).reference) for row in (first, second)]
        self.assertEqual(numbers, [1, 2])
        a = loot_controls(self.char1, 109)[self.source.pk]
        b = loot_controls(self.char2, 109)[self.source.pk]
        self.assertEqual(a["label"], b["label"])
        self.assertEqual([row["label"] for row in a["loot"]], ["회수부품 1"])
        self.assertEqual([row["label"] for row in b["loot"]], ["회수부품 2"])
        for state, identity in ((a, first.pk), (b, second.pk)):
            self.assertEqual(state["loot"][0]["action"]["roles"]["subject"][0]["identity"], str(identity))
            self.assertEqual(state["loot"][0]["action"]["roles"]["source"][0]["identity"], str(self.source.pk))
        # 권한이 풀려도 번호를 발급하거나 앞당기지 않는다.
        for player in (self.char1, self.char2):
            public = loot_controls(player, 110)[self.source.pk]
            self.assertEqual([row["label"] for row in public["loot"]], ["회수부품 1", "회수부품 2"])
            self.assertEqual([row["action"]["roles"]["subject"][0]["identity"] for row in public["loot"]],
                             [str(first.pk), str(second.pk)])
        self.assertEqual([number_for(descriptor(row).reference) for row in (first, second)], numbers)
        json.dumps(public)

    def test_corpse_hole_and_all_controls_preserve_original_source_refs(self):
        from evennia import create_object
        from world import loot_service
        from world.actions.loot_presentation import all_controls
        from world.state import loot_controls

        second = create_object(Corpse, key="둘째 시체", location=self.char1.location)
        third = create_object(Corpse, key="셋째 시체", location=self.char1.location)
        second.db.decay_at = third.db.decay_at = 200
        loot_service.populate_source(second, [])
        loot_service.populate_source(third, [])
        self.loot_item("scrap", quantity=2, deadline=110)
        original = self.source
        self.source = third
        self.loot_item("scrap", quantity=2, deadline=110)
        self.source = original
        second.delete()
        controls = loot_controls(self.char1, 109)
        self.assertEqual([controls[source.pk]["label"] for source in (original, third)], ["시체 1", "시체 3"])
        payload = all_controls(self.char1, 109)["corpses"]
        self.assertEqual([reference["identity"] for reference in payload["roles"]["source"]],
                         [str(original.pk), str(third.pk)])
        self.assertEqual(payload["arguments"]["quantity"], 0)
        self.assertTrue(payload["arguments"]["snapshot"])
