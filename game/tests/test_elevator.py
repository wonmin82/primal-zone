"""실제 Room 이동, 공용 층, bootstrap·재접속·웹 상태와 실패 원자성."""

import json
from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_object
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultCharacter
from typeclasses.explorers import Explorer
from world import elevator
from world.bootstrap import build_world, stale_definitions
from world.content import ROOMS
from world.content.elevator import ELEVATOR_DEFAULT_STOP, ELEVATOR_ROOM, ELEVATOR_STOPS
from world.multiplayer import world_change
from world.state import multiplayer_state

from tests.base import WorldCommandTest


class ElevatorTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.lift = self.rooms[ELEVATOR_ROOM]
        self.assertEqual(self.lift.db.current_stop, ELEVATOR_DEFAULT_STOP)
        for player in (self.char1, self.char2):
            player.location = self.rooms["hq_concourse"]
            player.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def test_each_landing_boards_selects_and_disembarks_with_real_hooks(self):
        for stop, data in ELEVATOR_STOPS.items():
            with self.subTest(stop=stop):
                self.char1.location = self.rooms[data["room"]]
                self.lift.db.current_stop = "roof" if stop != "roof" else "1f"
                self.char1.execute_cmd("승강기")
                self.assertEqual(self.char1.location, self.lift)
                self.assertEqual(self.lift.db.current_stop, stop)
                self.assertIn(ELEVATOR_ROOM, self.char1.profile()["visited"])
                self.char1.execute_cmd(data["label"])
                self.assertEqual(self.char1.location, self.rooms[data["room"]])
                self.assertIn(data["room"], self.char1.profile()["visited"])
        self.char1.execute_cmd("승강기")
        for stop, data in ELEVATOR_STOPS.items():
            self.char1.execute_cmd(data["label"])
            self.assertEqual(self.char1.location, self.rooms[data["room"]])
            self.assertEqual(self.lift.db.current_stop, stop)
            self.assertEqual(self.char1.zone, data["room"])
            self.char1.execute_cmd(" 승강기 ")

    def test_unknown_scope_and_closed_directions_preserve_location_and_state(self):
        self.char1.location = self.rooms["support_2f_w1"]
        before = deepcopy(self.char1.profile())
        for command in ["승강기", *[stop["label"] for stop in ELEVATOR_STOPS.values()]]:
            with patch.object(self.char1, "msg") as output:
                self.char1.execute_cmd(command)
            self.assertIn("명령을 확인하세요.", str(output.call_args_list))
            self.assertEqual(self.char1.zone, "support_2f_w1")
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(self.lift.db.current_stop, "1f")
        for data in ELEVATOR_STOPS.values():
            self.char1.location = self.rooms[data["room"]]
            for direction, message in ROOMS[data["room"]].get("blocked_exits", {}).items():
                with patch.object(self.char1, "msg") as output:
                    self.char1.execute_cmd(direction)
                self.assertIn(message, str(output.call_args_list))
                self.assertEqual(self.char1.zone, data["room"])
            # 호출 명령이 있는 Room에도 내부 층 명령은 없다.
            with patch.object(self.char1, "msg") as output:
                self.char1.execute_cmd("3층")
            self.assertIn("명령을 확인하세요.", str(output.call_args_list))
        self.char1.execute_cmd("도움말")

    def test_same_stop_selection_and_same_landing_board_do_not_save_floor(self):
        self.char1.execute_cmd("승강기")
        self.char1.execute_cmd("2층")
        self.char1.execute_cmd("승강기")
        with patch.object(self.lift.attributes, "add", wraps=self.lift.attributes.add) as save, patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd("2층")
            save.assert_not_called()
            self.assertIn("이미 2층", str(output.call_args_list))
        self.char2.location = self.rooms["support_2f_c"]
        with patch.object(self.lift.attributes, "add", wraps=self.lift.attributes.add) as save:
            self.char2.execute_cmd("승강기")
            save.assert_not_called()
        self.assertEqual(self.char2.location, self.lift)

    def test_shared_selection_external_call_and_independent_disembark(self):
        self.char1.execute_cmd("승강기")
        self.char2.execute_cmd("승강기")
        with patch.object(self.char2, "msg") as output:
            self.char1.execute_cmd("3층")
            self.assertIn("3층에 멈추고", str(output.call_args_list))
        self.assertEqual(self.char1.zone, "support_3f_c")
        self.assertEqual(self.char2.location, self.lift)
        with patch.object(self.char2, "msg") as output:
            self.char2.execute_cmd("내리기")
            self.assertIn("명령을 확인하세요.", str(output.call_args_list))
        self.assertEqual(self.char2.location, self.lift)
        self.char1.execute_cmd("승강기")
        third = create_object(Explorer, key="승강기세번째탐사자", location=self.rooms["support_roof"])
        with patch.object(self.char1, "msg") as first, patch.object(self.char2, "msg") as second:
            third.execute_cmd("승강기")
            self.assertIn("옥상", str(first.call_args_list))
            self.assertIn("옥상", str(second.call_args_list))
        self.assertEqual(self.lift.db.current_stop, "roof")
        self.assertEqual([p.location for p in (self.char1, self.char2, third)], [self.lift] * 3)
        self.char1.execute_cmd("내려")
        self.assertEqual(self.char1.zone, "support_roof")
        self.assertEqual(self.char2.location, self.lift)
        self.assertEqual(third.location, self.lift)
        self.char2.execute_cmd("1층")
        third.execute_cmd("내려")
        self.assertEqual(third.zone, "hq_concourse")
        self.assertEqual(self.char2.zone, "hq_concourse")

    def test_bootstrap_and_reload_preserve_shared_floor_room_ids_and_occupants(self):
        self.char1.execute_cmd("승강기")
        self.char1.execute_cmd("3층")
        self.char1.execute_cmd("승강기")
        count = ObjectDB.objects.count()
        ids = {zone: room.id for zone, room in self.rooms.items()}
        exits = {(zone, obj.key): obj.id for zone, room in self.rooms.items() for obj in room.exits}
        for _ in range(2):
            rebuilt = build_world()
            self.assertEqual({zone: room.id for zone, room in rebuilt.items()}, ids)
            self.assertEqual({(zone, obj.key): obj.id for zone, room in rebuilt.items() for obj in room.exits}, exits)
            self.assertEqual(ObjectDB.objects.count(), count)
            self.assertEqual(self.lift.db.current_stop, "3f")
            self.assertEqual(self.char1.location, self.lift)
        self.lift.attributes.reset_cache()
        self.lift.refresh_from_db()
        self.lift.at_init()
        self.assertEqual(self.lift.db.current_stop, "3f")
        self.assertEqual(stale_definitions(), [])
        self.assertEqual(self.lift.exits, [])
        for invalid in (None, "missing", "2층", [], {}):
            self.lift.db.current_stop = invalid
            build_world()
            self.assertEqual(self.lift.db.current_stop, ELEVATOR_DEFAULT_STOP)

    def test_reconnect_inside_stages_without_changing_shared_floor(self):
        self.char1.execute_cmd("승강기")
        before = deepcopy(self.char1.profile())
        with patch.object(self.char1.sessions, "count", return_value=0):
            self.char1.at_post_unpuppet(account=self.account, session=self.session)
        self.assertIsNone(self.char1.location)
        self.lift.db.current_stop = "roof"
        self.char1.at_pre_puppet(self.account, session=self.session)
        with patch.object(DefaultCharacter, "at_post_puppet"):
            self.char1.at_post_puppet()
        self.assertEqual(self.char1.zone, "staging_room")
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(self.lift.db.current_stop, "roof")

    def test_failed_board_and_shared_transaction_roll_back_without_passenger_notice(self):
        self.char2.location = self.lift
        self.lift.db.current_stop = "3f"
        before = deepcopy(self.char1.profile())
        with patch.object(self.char1, "move_to", return_value=False), patch.object(self.char2, "msg") as output:
            self.char1.execute_cmd("승강기")
            output.assert_not_called()
        self.assertEqual(self.lift.db.current_stop, "3f")
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.assertEqual(self.char1.profile(), before)
        with patch.object(self.char2, "msg") as output:
            with self.assertRaises(RuntimeError), world_change():
                elevator.select_stop(self.char2, "roof")
                raise RuntimeError("공용 변경 실패")
            output.assert_not_called()
        self.assertEqual(self.lift.db.current_stop, "3f")
        self.char1.change(lambda profile: profile.update(combat_target=999))
        self.char1.execute_cmd("승강기")
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.assertEqual(self.lift.db.current_stop, "3f")

    def test_text_web_state_map_and_all_passenger_pushes_share_controls(self):
        self.char1.location = self.rooms["dock"]
        self.assertIsNone(multiplayer_state(self.char1)["elevator"])
        for stop, data in ELEVATOR_STOPS.items():
            self.char1.location = self.rooms[data["room"]]
            state = multiplayer_state(self.char1)
            self.assertEqual(state["elevator"]["actions"], [{"label": "승강기", "command": "승강기"}])
            self.assertIn("승강기로 호출", str(self.char1.location.return_appearance(self.char1)))
            json.dumps(state)
        self.char1.location = self.rooms["support_2f_w1"]
        self.assertIsNone(multiplayer_state(self.char1)["elevator"])
        self.char1.location = self.rooms["hq_concourse"]
        self.char1.execute_cmd("승강기")
        self.char2.execute_cmd("승강기")
        self.char1.execute_cmd("2층")
        self.assertEqual(self.char1.zone, "support_2f_c")
        state = multiplayer_state(self.char2)
        self.assertEqual(state["elevator"]["current_floor"], "2층")
        self.assertEqual(state["elevator"]["current_stop"], "2f")
        self.assertEqual([a["command"] for a in state["elevator"]["actions"]], [s["label"] for s in ELEVATOR_STOPS.values()] + ["내려"])
        self.assertIn("현재 위치: 2층", self.lift.return_appearance(self.char1))
        self.char1.execute_cmd("승강기")
        with patch.object(self.char2.sessions, "count", return_value=1):
            self.char2.push_state.reset_mock()
            self.char1.execute_cmd("3층")
            self.char2.push_state.assert_called()
        self.char1.execute_cmd("승강기")
        with patch.object(self.char1.sessions, "count", return_value=1), patch.object(self.char1, "msg") as output:
            Explorer.push_state(self.char1)
            payload = output.call_args.kwargs["pz_state"][0][0]
            self.assertEqual(payload["exits"], [])
            self.assertEqual(payload["elevator"]["current_floor"], "3층")
            json.dumps(payload)
        self.char1.execute_cmd("내려")
        self.char1.execute_cmd("승강기")
        self.char1.execute_cmd("옥상")
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd("지도")
            text = str(output.call_args_list)
            self.assertIn("본부 승강기", text)
            self.assertIn("본부 3층 중앙 복도", text)
            self.assertIn("본부 옥상", text)
