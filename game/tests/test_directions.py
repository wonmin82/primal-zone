"""실제 Exit/dispatcher/보기/웹 상태와 고정 텍스트 방향도 회귀."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import search_tag
from evennia.objects.models import ObjectDB
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES, action_objects
from typeclasses.zone_rooms import exit_diagram
from world import text as ft
from world.bootstrap import EXIT_CATEGORY, build_world, stale_definitions
from world.content import REGIONS, ROOMS
from world.content.directions import DIRECTION_ALIASES, DIRECTION_ORDER, OPPOSITE_DIRECTIONS
from world.content.headquarters import ROOF_ROOMS, ROOF_SIDES
from world.content.integrity import errors

from tests.base import WorldCommandTest


class DirectionIntegrationTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["support_roof"]
        self.char1.home = self.rooms["dock"]
        self.char1.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def raw(self, command):
        with patch.object(self.char1, "msg") as output:
            completed = []
            self.char1.execute_cmd(command).addCallback(lambda result: completed.append(True))
            self.assertEqual(completed, [True])
        return [call.args[0] for call in output.call_args_list if call.args]

    def test_actual_eight_directions_and_english_alias_round_trips(self):
        for direction in DIRECTION_ORDER:
            reverse = OPPOSITE_DIRECTIONS[direction]
            for outward, inward in ((direction, reverse), (DIRECTION_ALIASES[direction], DIRECTION_ALIASES[reverse])):
                self.raw(outward)
                self.assertEqual(self.char1.zone, ROOF_SIDES[direction])
                self.raw(inward)
                self.assertEqual(self.char1.zone, "support_roof")
        self.assertEqual(self.char1.home, self.rooms["dock"])

    def test_diagonal_look_is_distant_read_only_and_accepts_aliases(self):
        before = self.char1.profile_snapshot()
        for command, destination in (("북동 보기", "support_roof_ne"), ("ne 보기", "support_roof_ne"),
                                     ("남서 봐", "support_roof_sw"), ("sw 봐", "support_roof_sw")):
            self.assertIn(ROOMS[destination]["name"], "\n".join(map(str, self.raw(command))))
            self.assertEqual(self.char1.zone, "support_roof")
            self.assertEqual(self.char1.profile_snapshot(), before)

    def test_sequence_dispatches_diagonal_round_trip(self):
        self.raw("북동, 남서 해")
        self.assertEqual(self.char1.zone, "support_roof")
        self.assertIn("support_roof_ne", self.char1.profile_snapshot()["visited"])

    def test_web_exits_follow_clockwise_hub_and_single_reverse(self):
        for zone, expected in (("support_roof", list(DIRECTION_ORDER)), ("support_roof_ne", ["남서"])):
            self.char1.location = self.rooms[zone]
            with patch.object(self.char1, "msg") as output:
                Explorer.push_state(self.char1)
            state = output.call_args.kwargs["pz_state"][0][0]
            self.assertEqual(state["exits"], expected)
            self.assertEqual(state["interactables"], [])
            self.assertEqual(action_objects(self.char1.location), [])

    def test_map_orders_directions_preserving_unvisited_and_current(self):
        self.char1.change(lambda p: p.update(visited=["support_roof", "support_roof_ne"]))
        with patch.dict(ROOMS["support_roof"], exits=dict(reversed(list(ROOMS["support_roof"]["exits"].items())))):
            output = "\n".join(map(str, self.raw("지도")))
        hub = next(line for line in output.splitlines() if "본부 옥상 ← 현재" in line)
        positions = [hub.index(direction + ":") for direction in DIRECTION_ORDER]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("북동: 북동쪽 설비 구역", hub)
        self.assertIn("남서: 미탐사", hub)

    def test_roof_bootstrap_reuses_all_exits_and_preserves_profile(self):
        self.char1.change(lambda p: p.update(credits=123, storage={"scrap": 2}))
        before = deepcopy(self.char1.profile_snapshot())
        identities = {f"{zone}:{direction}": search_tag(f"{zone}:{direction}", category=EXIT_CATEGORY)[0].id
                      for zone in ("support_roof", *ROOF_SIDES.values()) for direction in ROOMS[zone]["exits"]}
        count = ObjectDB.objects.count()
        for _ in range(2):
            build_world()
            self.assertEqual(ObjectDB.objects.count(), count)
            self.assertEqual(self.char1.profile_snapshot(), before)
            self.assertEqual(self.char1.zone, "support_roof")
            self.assertEqual(stale_definitions(), [])
            for identity, db_id in identities.items():
                objects = search_tag(identity, category=EXIT_CATEGORY)
                self.assertEqual([obj.id for obj in objects], [db_id])
                self.assertEqual(objects[0].aliases.all(), [DIRECTION_ALIASES[objects[0].key]])

    def test_map_merges_actual_and_blocked_directions_in_one_order(self):
        self.char1.location = self.rooms["support_5f_c"]
        self.char1.change(lambda p: p.update(visited=["support_5f_c", "support_5f_w1", "support_2f_w1"]))
        output = self.raw("지도")[-1]
        lines = output.splitlines()
        east = next(line for line in lines if "본부 5층 중앙 복도 ← 현재" in line)
        west = next(line for line in lines if "본부 2층 서쪽 복도 /" in line)
        for line, expected in ((east, ["북", "동", "남", "서"]), (west, ["북", "동", "남"])):
            positions = [line.index(direction + ":") for direction in expected]
            self.assertEqual(positions, sorted(positions))
        self.assertIn("서: 본부 5층 서쪽 복도", east)
        self.assertIn("북: 폐쇄, 동: 미탐사, 남: 폐쇄", east)
        self.assertIn("북: 미탐사", west)
        self.assertIn("남: 폐쇄", west)
        self.assertIn("[" + REGIONS["headquarters"]["name"] + "]", output)
        self.assertEqual([part["text"] for part in output.segments if part["role"] == "direction"],
                         ["북", "동", "남", "북", "동", "남", "서", "북", "동", "남", "서"])

    def test_map_preserves_special_exit_fallback_order_after_merged_directions(self):
        self.char1.change(lambda p: p.update(visited=["support_roof"]))
        with patch.dict(ROOMS["support_roof"], exits={"계단": "dock", "서": "dock", "문": "dock"},
                        blocked_exits={"남": "폐쇄", "북": "폐쇄"}):
            output = self.raw("지도")[-1]
        self.assertEqual([part["text"] for part in output.segments if part["role"] == "direction"],
                         ["북", "남", "서", "계단", "문"])

    def test_static_integrity_rejects_any_roof_interactable_definition(self):
        self.assertEqual(errors(INTERACTABLES), [])
        for zone in ROOF_ROOMS:
            with self.subTest(zone=zone), patch.dict(INTERACTABLES, roof_fixture={"room": zone, "actions": ["대화"]}):
                issues = errors(INTERACTABLES)
                self.assertTrue(any("roof_fixture" in issue and zone in issue and "interactable/NPC" in issue
                                    for issue in issues))
        self.assertEqual(errors(INTERACTABLES), [])

    def test_text_canvas_and_axis_remain_fixed_for_exit_combinations(self):
        for directions in ([], ["북"], ["남"], ["동", "서"], ["북동"], ["남서"],
                           ["북", "남", "동", "서"], list(DIRECTION_ORDER)):
            with self.subTest(directions=directions):
                output = exit_diagram(directions)
                lines = output.split("\n")
                self.assertEqual(len(lines), 5)
                self.assertEqual([ft.display_width(line) for line in lines], [30] * 5)
                self.assertEqual(ft.display_width(lines[2].split("[현재]")[0]), 12)
                self.assertEqual({part["text"] for part in output.segments if part["role"] == "direction"}, set(directions))
                for direction, row in (("북", 1), ("남", 3)):
                    if direction in directions:
                        self.assertEqual(ft.display_width(lines[row].split("｜")[0]), 14)

    def test_text_special_exit_remains_in_fallback(self):
        output = exit_diagram(["북동", "계단"])
        self.assertEqual([part["text"] for part in output.segments if part["role"] == "direction"], ["북동", "계단"])
        self.assertIn("기타 출구: 계단", output)
