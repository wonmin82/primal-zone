"""승강기 콘텐츠와 방향 출구에 독립적인 이동 가능성을 순수 검사한다."""

from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from world.content import REGIONS, ROOMS
from world.content.elevator import ELEVATOR_DEFAULT_STOP, ELEVATOR_ROOM, ELEVATOR_STOPS
from world.content.integrity import elevator_errors, errors
from world.elevator import controls, normalized_stop, stop_for_room
from world.test_headquarters import content_targets


class ElevatorRulesTests(TestCase):
    def test_stop_contract_room_and_content_integrity(self):
        self.assertEqual(ELEVATOR_DEFAULT_STOP, "1f")
        self.assertEqual(set(ELEVATOR_STOPS), {"1f", "2f", "3f", "4f", "5f", "roof"})
        self.assertEqual({stop["room"] for stop in ELEVATOR_STOPS.values()}, {
            "hq_concourse", "support_2f_c", "support_3f_c", "support_4f_c", "support_5f_c", "support_roof",
        })
        self.assertIn(ELEVATOR_ROOM, REGIONS["headquarters"]["rooms"])
        room = ROOMS[ELEVATOR_ROOM]
        self.assertEqual((room["safe"], room["enemies"], room["exits"]), (True, [], {}))
        self.assertEqual((room["exposure"], room["light_profile"]), ("indoor", "artificial"))
        self.assertEqual(errors(content_targets()), [])

    def test_invalid_state_normalization_and_read_only_controls(self):
        before = deepcopy(ELEVATOR_STOPS)
        for stop, data in ELEVATOR_STOPS.items():
            self.assertEqual(normalized_stop(stop), stop)
            self.assertEqual(stop_for_room(data["room"]), stop)
            self.assertEqual(controls(data["room"])["actions"], [{"label": "승강기", "command": "승강기"}])
            inside = controls(ELEVATOR_ROOM, stop)
            self.assertEqual(inside["current_floor"], data["label"])
            self.assertEqual([a["command"] for a in inside["actions"]], [s["label"] for s in before.values()] + ["내려"])
        for invalid in (None, "", "2층", "missing", 1, [], {}):
            self.assertEqual(normalized_stop(invalid), ELEVATOR_DEFAULT_STOP)
        self.assertIsNone(controls("support_2f_w1"))
        self.assertEqual(ELEVATOR_STOPS, before)

    def test_transport_reaches_all_rooms_without_fake_cardinal_edges(self):
        stop_rooms = {stop["room"] for stop in ELEVATOR_STOPS.values()}
        visited, pending = set(), ["staging_room"]
        while pending:
            zone = pending.pop()
            if zone in visited:
                continue
            visited.add(zone)
            pending.extend(ROOMS[zone]["exits"].values())
            if zone in stop_rooms:
                pending.append(ELEVATOR_ROOM)
            if zone == ELEVATOR_ROOM:
                pending.extend(stop_rooms)
        self.assertEqual(visited, set(ROOMS))
        self.assertFalse(any(ELEVATOR_ROOM in room["exits"].values() for room in ROOMS.values()))
        self.assertEqual(ROOMS[ELEVATOR_ROOM]["exits"], {})

    def test_integrity_detects_missing_rooms_region_and_fake_exits(self):
        content = {zone: room for zone, room in ROOMS.items() if zone != ELEVATOR_ROOM}
        with patch("world.content.integrity.ROOMS", content):
            self.assertIn("승강기 Room이 없습니다.", elevator_errors())
        with patch.dict(REGIONS["headquarters"], rooms=()):
            self.assertTrue(any("Region" in issue for issue in elevator_errors()))
        with patch.dict(ROOMS[ELEVATOR_ROOM]["exits"], 북="support_2f_c"):
            self.assertTrue(any("방향 출구" in issue for issue in elevator_errors()))
        with patch.dict(ROOMS["support_5f_c"]["exits"], 남=ELEVATOR_ROOM):
            issues = errors(content_targets())
            self.assertTrue(any("가짜 방향" in issue for issue in issues))
            self.assertTrue(any("폐쇄 출입구가 겹칩니다" in issue for issue in issues))

    def test_integrity_detects_invalid_stop_targets_labels_and_default(self):
        for field, value, expected in (
            ("room", "missing", "대상 Room"),
            ("room", "support_2f_c", "정류 층은"),
            ("label", "", "표시명이 유효"),
            ("label", "   ", "표시명이 유효"),
            ("label", "2층", "표시명이 중복"),
        ):
            with self.subTest(field=field, value=value), patch.dict(ELEVATOR_STOPS["1f"], {field: value}):
                self.assertTrue(any(expected in issue for issue in elevator_errors()))
        with patch("world.content.integrity.ELEVATOR_DEFAULT_STOP", "unknown"):
            self.assertTrue(any("기본 정류 층" in issue for issue in elevator_errors()))
        with patch.dict(ELEVATOR_STOPS, {"": {"room": "support_roof", "label": "추가"}}):
            self.assertTrue(any("ID/정의" in issue for issue in elevator_errors()))
