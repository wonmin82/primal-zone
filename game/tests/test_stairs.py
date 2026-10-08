"""실제 계단 Exit와 transaction observer 회귀."""
from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_object
from typeclasses.explorers import Explorer
from world.content.headquarters import HQ_LANDINGS

from tests.base import WorldCommandTest


class StairsTests(WorldCommandTest):
    character_typeclass = Explorer
    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["hq_concourse"]
        self.char1.push_state = Mock()

    def test_actual_up_down_exit_chain_and_landings(self):
        self.char1.execute_cmd("계단")
        self.assertEqual(self.char1.zone, HQ_LANDINGS[0][2])
        for _, landing, stairs in HQ_LANDINGS[1:]:
            self.char1.execute_cmd("u")
            self.assertEqual(self.char1.zone, stairs)
            self.char1.execute_cmd("나가기")
            self.assertEqual(self.char1.zone, landing)
            self.char1.execute_cmd("계단")
            self.assertEqual(self.char1.zone, stairs)
        for _, _, stairs in reversed(HQ_LANDINGS[:-1]):
            self.char1.execute_cmd("d")
            self.assertEqual(self.char1.zone, stairs)
        visited = self.char1.profile_snapshot()["visited"]
        self.assertTrue(all(stairs in visited for _, _, stairs in HQ_LANDINGS))

    def test_boundaries_and_all_exit_arguments_are_rejected(self):
        from world.content import ROOMS
        for zone, definition in ROOMS.items():
            self.char1.location = self.rooms[zone]
            for command in definition["exits"]:
                before = deepcopy(self.char1.profile_snapshot())
                self.char1.execute_cmd(command + " 잘못된인자")
                self.assertEqual(self.char1.zone, zone)
                self.assertEqual(self.char1.profile_snapshot(), before)
        for zone, command in (("hq_stairs_1f", "아래"), ("hq_stairs_roof", "위"),
                              ("dock", "계단")):
            self.char1.location = self.rooms[zone]
            self.char1.execute_cmd(command)
            self.assertEqual(self.char1.zone, zone)

    def test_invalid_exit_and_failed_move_do_not_settle_recovery_boundary(self):
        self.char1.change(lambda p: p.update(hp=1, command_shortcuts={"잘못": ["계단 올라"]}))
        before = deepcopy(self.char1.profile_snapshot())
        with patch("typeclasses.explorers.time", return_value=160):
            for command in ("계단 올라", "잘못", "계단 올라, 계단 내려 해"):
                self.char1.execute_cmd(command)
                self.assertEqual(self.char1.profile_snapshot(), before)
            self.assertEqual(self.char1.profile_snapshot(), before)
            with patch.object(self.char1, "at_pre_move", return_value=False):
                self.char1.execute_cmd("계단")
            self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.char1.zone, "hq_concourse")

    def test_postfix_look_shortcuts_and_sequence_keep_common_exit_policy(self):
        self.char1.location = self.rooms["dock"]
        before = deepcopy(self.char1.profile_snapshot())
        for command in ("북 보기", "북 봐", "n 보기", "n 잘못된인자"):
            self.char1.execute_cmd(command)
            self.assertEqual(self.char1.zone, "dock")
            self.assertEqual(self.char1.profile_snapshot(), before)
        self.char1.change(lambda p: p.update(command_shortcuts={"잘못": ["북 잘못된인자"]}))
        self.char1.execute_cmd("잘못")
        self.assertEqual(self.char1.zone, "dock")
        self.char1.execute_cmd("북 잘못된인자, 북 해")
        self.assertEqual(self.char1.zone, "grass")

class StairPresenceTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.origin = self.rooms["hq_concourse"]
        self.destination = self.rooms["hq_stairs_1f"]
        self.exit = next(obj for obj in self.origin.exits if obj.key == "계단")
        self.char1.location = self.char2.location = self.origin
        self.arrival = create_object(Explorer, key="도착방 관찰자", location=self.destination)
        for observer in (self.char2, self.arrival):
            self.enterContext(patch.object(observer.sessions, "count", return_value=1))
            observer.msg = self.enterContext(patch.object(observer, "msg"))
        for player in (self.char1, self.char2, self.arrival):
            player.push_state = Mock()

    def test_successful_stairs_defer_departure_and_arrival_exactly_once(self):
        from world.multiplayer import world_change

        with world_change():
            self.exit.at_traverse(self.char1, self.destination)
            self.assertEqual(self.char1.location, self.destination)
            self.char2.msg.assert_not_called()
            self.arrival.msg.assert_not_called()
        self.char2.msg.assert_called_once()
        self.arrival.msg.assert_called_once()
        self.assertIn("떠났다", self.char2.msg.call_args.args[0])
        self.assertIn("도착했다", self.arrival.msg.call_args.args[0])

    def test_post_move_failure_and_outer_rollback_emit_no_notifications(self):
        from world.multiplayer import world_change

        before = deepcopy(self.char1.profile_snapshot())
        original = self.char1.at_post_move

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("post move failure")

        with patch.object(self.char1, "at_post_move", side_effect=fail):
            self.char1.execute_cmd("계단")
        self.assertEqual(self.char1.location, self.origin)
        self.assertEqual(self.char1.profile_snapshot(), before)
        with self.assertRaisesRegex(RuntimeError, "outer rollback"), world_change():
            self.exit.at_traverse(self.char1, self.destination)
            raise RuntimeError("outer rollback")
        self.assertEqual(self.char1.location, self.origin)
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.char2.msg.assert_not_called()
        self.arrival.msg.assert_not_called()

    def test_view_lock_and_poor_visibility_hide_presence(self):
        from dataclasses import replace

        from world.observation import context_for

        self.char1.locks.add("view:false()")
        self.exit.at_traverse(self.char1, self.destination)
        self.char2.msg.assert_not_called()
        self.arrival.msg.assert_not_called()
        self.char1.location = self.origin
        self.char1.locks.add("view:all()")

        def poor(*args, **kwargs):
            context = context_for(*args, **kwargs)
            return replace(context, snapshot=replace(context.snapshot, effective_visibility="poor"))

        with patch("world.observation.context_for", side_effect=poor):
            self.exit.at_traverse(self.char1, self.destination)
        self.char2.msg.assert_not_called()
        self.arrival.msg.assert_not_called()

    def test_elevator_preserves_visible_departure_and_arrival(self):
        self.arrival.location = self.rooms["support_elevator"]
        self.char1.execute_cmd("승강기")
        self.char2.msg.assert_called_once()
        self.arrival.msg.assert_called_once()
        self.assertIn("떠났다", self.char2.msg.call_args.args[0])
        self.assertIn("도착했다", self.arrival.msg.call_args.args[0])
