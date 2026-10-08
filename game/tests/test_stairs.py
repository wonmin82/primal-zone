"""계단과 공용 승강기가 같은 여섯 중앙 공간을 서로 독립적으로 연결한다."""

from copy import deepcopy
from unittest.mock import Mock, patch

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
