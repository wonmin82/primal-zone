"""계단과 공용 승강기가 같은 여섯 중앙 공간을 서로 독립적으로 연결한다."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_object
from typeclasses.explorers import Explorer
from world.content.elevator import ELEVATOR_STOPS
from world.state import multiplayer_state

from tests.base import WorldCommandTest


class StairsTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.push_state = Mock()
        self.char1.location = self.rooms["hq_concourse"]

    def test_adjacent_floor_round_trip_and_web_actions_without_fake_exits(self):
        stops = [s["room"] for s in ELEVATOR_STOPS.values()]
        lift = self.rooms["support_elevator"]
        for command, destinations in (
            ("계단 올라", stops[1:]),
            ("계단 내려", list(reversed(stops[:-1]))),
        ):
            for destination in destinations:
                actions = multiplayer_state(self.char1)["stairs"]
                self.assertIn(command, [a["command"] for a in actions])
                self.char1.execute_cmd(command)
                self.assertEqual(self.char1.zone, destination)
                self.assertIn(destination, self.char1.profile_snapshot()["visited"])
                self.assertEqual(lift.db.current_stop, "1f")
                self.assertNotIn("계단", [obj.key for obj in self.char1.location.exits])

    def test_bounds_unknown_action_and_noncentral_room_leave_state_unchanged(self):
        for zone, commands in (
            ("hq_concourse", ("계단 내려", "계단 5층", "계단")),
            ("support_roof", ("계단 올라",)),
            ("storage_room", ("계단 올라", "계단 내려")),
        ):
            self.char1.location = self.rooms[zone]
            before = deepcopy(self.char1.profile_snapshot())
            for command in commands:
                self.char1.execute_cmd(command)
                self.assertEqual(self.char1.zone, zone)
                self.assertEqual(self.char1.profile_snapshot(), before)

    def test_failed_move_and_combat_do_not_change_room_or_shared_floor(self):
        before = deepcopy(self.char1.profile_snapshot())
        with patch.object(self.char1, "move_to", return_value=False):
            self.char1.execute_cmd("계단 올라")
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.char1.change(lambda p: p.update(combat_target=999))
        self.char1.execute_cmd("계단 올라")
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.assertEqual(self.rooms["support_elevator"].db.current_stop, "1f")

    def test_fifth_floor_selection_preserves_other_passenger_and_current_floor(self):
        self.char2.location = self.char1.location
        self.char1.execute_cmd("승강기")
        self.char2.execute_cmd("승강기")
        self.char1.execute_cmd("5층")
        self.assertEqual(self.char1.zone, "support_5f_c")
        self.assertEqual(self.char2.zone, "support_elevator")
        self.char1.execute_cmd("계단 내려")
        self.assertEqual(self.char1.zone, "support_4f_c")
        self.char2.execute_cmd("내려")
        self.assertEqual(self.char2.zone, "support_5f_c")

    def test_global_help_does_not_register_global_stair_execution(self):
        from commands.elevator import Stairs
        from commands.registry import COMMANDS

        self.assertNotIn(Stairs, COMMANDS)
        for zone in ("hq_concourse", "storage_room"):
            self.char1.location = self.rooms[zone]
            with patch.object(self.char1, "msg") as output:
                self.char1.execute_cmd("계단 도움말")
            text = str(output.call_args_list)
            for token in ("계단", "중앙 공간", "바로 위층", "계단 올라", "계단 내려", "1층", "옥상"):
                self.assertIn(token, text)
            self.assertEqual(self.char1.zone, zone)
        before = deepcopy(self.char1.profile_snapshot())
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd("계단 올라")
        self.assertIn("명령을 확인", str(output.call_args_list))
        self.assertEqual(self.char1.zone, "storage_room")
        self.assertEqual(self.char1.profile_snapshot(), before)


class StairPresenceTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.origin = self.rooms["hq_concourse"]
        self.destination = self.rooms["support_2f_c"]
        self.char1.location = self.char2.location = self.origin
        self.arrival = create_object(Explorer, key="도착방 관찰자", location=self.destination)
        for observer in (self.char2, self.arrival):
            self.enterContext(patch.object(observer.sessions, "count", return_value=1))
            observer.msg = self.enterContext(patch.object(observer, "msg"))
        for player in (self.char1, self.char2, self.arrival):
            player.push_state = Mock()

    def test_successful_stairs_defer_departure_and_arrival_exactly_once(self):
        from world.multiplayer import world_change
        from world.stairs import move

        with world_change():
            move(self.char1, "올라")
            self.assertEqual(self.char1.location, self.destination)
            self.char2.msg.assert_not_called()
            self.arrival.msg.assert_not_called()
        self.char2.msg.assert_called_once()
        self.arrival.msg.assert_called_once()
        self.assertIn("떠났다", self.char2.msg.call_args.args[0])
        self.assertIn("도착했다", self.arrival.msg.call_args.args[0])

    def test_post_move_failure_and_outer_rollback_emit_no_notifications(self):
        from world.multiplayer import world_change
        from world.stairs import move

        before = deepcopy(self.char1.profile_snapshot())
        original = self.char1.at_post_move

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("post move failure")

        with patch.object(self.char1, "at_post_move", side_effect=fail):
            self.char1.execute_cmd("계단 올라")
        self.assertEqual(self.char1.location, self.origin)
        self.assertEqual(self.char1.profile_snapshot(), before)
        with self.assertRaisesRegex(RuntimeError, "outer rollback"), world_change():
            move(self.char1, "올라")
            raise RuntimeError("outer rollback")
        self.assertEqual(self.char1.location, self.origin)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.char2.msg.assert_not_called()
        self.arrival.msg.assert_not_called()

    def test_view_lock_and_poor_visibility_hide_presence(self):
        from dataclasses import replace

        from world.observation import context_for
        from world.stairs import move

        self.char1.locks.add("view:false()")
        move(self.char1, "올라")
        self.char2.msg.assert_not_called()
        self.arrival.msg.assert_not_called()
        self.char1.location = self.origin
        self.char1.locks.add("view:all()")

        def poor(*args, **kwargs):
            context = context_for(*args, **kwargs)
            return replace(context, snapshot=replace(context.snapshot, effective_visibility="poor"))

        with patch("world.observation.context_for", side_effect=poor):
            move(self.char1, "올라")
        self.char2.msg.assert_not_called()
        self.arrival.msg.assert_not_called()

    def test_elevator_preserves_visible_departure_and_arrival(self):
        self.arrival.location = self.rooms["support_elevator"]
        self.char1.execute_cmd("승강기")
        self.char2.msg.assert_called_once()
        self.arrival.msg.assert_called_once()
        self.assertIn("떠났다", self.char2.msg.call_args.args[0])
        self.assertIn("도착했다", self.arrival.msg.call_args.args[0])
