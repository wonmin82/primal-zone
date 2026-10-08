"""실제 계단/승강기 출구 구조의 순수 무결성 검사."""
from unittest import TestCase
from unittest.mock import patch

from world.content import REGIONS, ROOMS
from world.content.headquarters import ELEVATOR_ROOM, HQ_LANDINGS
from world.content.headquarters import ROOMS as HQ_ROOMS
from world.content.integrity import elevator_errors, errors
from world.test_headquarters import content_targets


class ElevatorRulesTests(TestCase):
    def test_real_room_links_safety_and_native_graph(self):
        self.assertEqual(len(HQ_ROOMS), 52)
        self.assertEqual(errors(content_targets()), [])
        for index, (label, landing, stairs) in enumerate(HQ_LANDINGS):
            self.assertEqual(ROOMS[landing]["exits"]["계단"], stairs)
            self.assertEqual(ROOMS[landing]["exits"]["승강기"], ELEVATOR_ROOM)
            self.assertEqual(ROOMS[ELEVATOR_ROOM]["exits"][label], landing)
            expected = {"나가기": landing}
            if index:
                expected["아래"] = HQ_LANDINGS[index - 1][2]
            if index + 1 < 6:
                expected["위"] = HQ_LANDINGS[index + 1][2]
            self.assertEqual(ROOMS[stairs]["exits"], expected)
            self.assertIn(stairs, REGIONS["headquarters"]["rooms"])
            self.assertEqual((ROOMS[stairs]["safe"], ROOMS[stairs]["enemies"]), (True, []))
            self.assertNotIn("recovery", ROOMS[stairs])
        visited, pending = set(), ["staging_room"]
        while pending:
            zone = pending.pop()
            if zone in visited:
                continue
            visited.add(zone)
            pending.extend(ROOMS[zone]["exits"].values())
        self.assertEqual(visited, set(ROOMS))

    def test_invalid_stairs_and_elevator_links_are_detected(self):
        for zone, exits in (("hq_stairs_1f", {"아래": "hq_stairs_roof"}),
                            ("hq_stairs_roof", {"위": "hq_stairs_1f"}),
                            (ELEVATOR_ROOM, {"위": "support_roof"}),
                            ("hq_concourse", {"승강기": "dock"})):
            with self.subTest(zone=zone), patch.dict(ROOMS[zone]["exits"], exits):
                self.assertTrue(errors(content_targets()))
        with patch.dict(ROOMS["hq_stairs_1f"], recovery={"hp_per_minute": 1}):
            self.assertTrue(elevator_errors())
        with patch.dict(ROOMS[ELEVATOR_ROOM], exits={"1층": "dock"}):
            self.assertTrue(elevator_errors())
        with patch.dict(REGIONS["headquarters"], rooms=()):
            self.assertTrue(elevator_errors())
