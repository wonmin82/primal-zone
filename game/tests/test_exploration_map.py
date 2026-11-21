"""실제 월드와 명령 실행의 지도 공개 경계를 검증한다."""

from time import time
from unittest.mock import Mock, patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from evennia import create_object
from evennia.utils.ansi import parse_ansi
from typeclasses.explorers import Explorer
from world.content import REGIONS, ROOM_REGION, ROOMS
from world.exit_presentation import exit_entries
from world.map_commands import map_text
from world.map_metadata import catalog
from world.map_projection import RuntimeGraphMismatch, project
from world.text import display_width

from tests.base import WorldCommandTest


class ExplorationMapTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["support_roof"]
        self.index = catalog()

    def graph(self, visited, *, near=False):
        current = self.char1.zone
        sheet_id = self.index.room_sheet[current]
        return project(self.char1, self.index, self.index.sheets.get(sheet_id),
                       current=current, visited=set(visited), now=time(), near=near)

    def test_maps_for_all_actual_rooms(self):
        self.assertEqual(len(self.rooms), 67)
        self.assertEqual(sum(sheet is None for sheet in self.index.room_sheet.values()), 7)
        self.assertEqual({region: len(data["rooms"]) for region, data in REGIONS.items()},
                         {"headquarters": 52, "outpost": 8, "deep_jungle": 7})
        self.char1.change(lambda profile: profile.update(visited=list(ROOMS)))
        for zone, instance in self.rooms.items():
            self.char1.location = instance
            with self.subTest(zone=zone, region=ROOM_REGION[zone]):
                result = map_text(self.char1, "")
                if self.index.room_sheet[zone] is None:
                    for entry in exit_entries(self.char1):
                        if entry["exists"]:
                            self.assertIn(entry["name"], result)
                else:
                    self.assertIsInstance(result, list, result)
                    body = result[1]
                    self.assertEqual(body.count("@"), 1)
                    self.assertLessEqual(len(body.splitlines()), 24)
                    self.assertTrue(all(display_width(line) <= 60 for line in body.splitlines()))
                    self.assertEqual(parse_ansi(body.ansi(), strip_ansi=True), body)

    def test_unvisited_observable_and_hidden_visited_destinations(self):
        key = "support_roof_ne"
        observed = next(entry for entry in exit_entries(self.char1) if entry["name"] == "북동")
        self.assertEqual(observed["destination_name"], ROOMS[key]["name"])
        self.assertIn(("0", "북동", "?"), self.graph([]).boundaries)
        self.assertIn(ROOMS[key]["name"], self.graph([key]).names.values())
        self.rooms[key].locks.add("view:false()")
        self.assertEqual(self.graph([]), self.graph([key]))
        move = next(obj for obj in self.char1.location.exits if obj.key == "북동")
        move.locks.add("view:false()")
        before = self.graph([key])
        self.assertFalse(any(direction == "북동" for _, direction, _ in before.boundaries))
        with patch.dict(ROOMS[key], name="비공개 장소 수정", exits={}):
            self.assertEqual(before, self.graph([key]))
        move.locks.add("view:all()")
        before = self.graph([key])
        from dataclasses import replace

        alternate = replace(self.index, room_sheet={**self.index.room_sheet, key: None})
        self.char1.change(lambda p: p.update(visited=[key]))
        def wire(index):
            with patch("world.map_commands.catalog", return_value=index):
                return [(text.kind, text.segments) for text in map_text(self.char1, "")]
        with patch.object(self, "index", alternate):
            self.assertEqual(before, self.graph([key]))
        altered = replace(alternate, positions={key: ("support_roof", (99, 99))},
                          routes={("support_roof", "북동"): ((40, -40),)})
        self.assertEqual(wire(self.index), wire(altered))

    def test_remote_static_live_door_and_dynamic_policies(self):
        self.char1.location = self.rooms["staging_room"]
        visited = {"staging_room", "hq_concourse", "hq_admin_office"}
        with patch("world.doors.state_for_exit", return_value=None) as door:
            before = self.graph(visited)
            door.assert_not_called()
        with patch("world.doors.state_for_exit", return_value="LOCKED") as door:
            self.assertEqual(before, self.graph(visited))
            door.assert_not_called()
        create_object("typeclasses.exits.Exit", key="임시 문", location=self.rooms["hq_concourse"],
                      destination=self.rooms["hq_admin_office"])
        self.assertEqual(before, self.graph(visited))
        names = {entry["name"] for entry in exit_entries(self.char1, self.rooms["hq_concourse"])}
        self.assertIn("임시 문", names)
        self.char1.location = self.rooms["hq_concourse"]
        self.assertIn(("임시 문", "지도에 배치되지 않은 출구"), self.graph(visited).notices)
        self.assertTrue(any(direction == "동" and symbol == "×" for _, direction, symbol in self.graph(visited).boundaries))

    def test_remote_new_static_link_requires_real_managed_exit(self):
        from world.bootstrap import EXIT_CATEGORY

        north, northeast = "support_roof_n", "support_roof_ne"
        visited = {north, northeast}
        before = self.graph(visited)
        east = create_object("typeclasses.exits.Exit", key="동", location=self.rooms[north],
                             destination=self.rooms[northeast])
        west = create_object("typeclasses.exits.Exit", key="서", location=self.rooms[northeast],
                             destination=self.rooms[north])
        declared_east = ROOMS[north]["exits"] | {"동": northeast}
        declared_west = ROOMS[northeast]["exits"] | {"서": north}
        with patch.dict(ROOMS[north], exits=declared_east), patch.dict(ROOMS[northeast], exits=declared_west):
            self.assertEqual(before, self.graph(visited))
            east.tags.add(f"{north}:동", category=EXIT_CATEGORY)
            west.tags.add(f"{northeast}:서", category=EXIT_CATEGORY)
            after = self.graph(visited)
            self.assertNotEqual(before, after)
            self.assertEqual(len(after.edges), len(before.edges) + 2)
            create_object("typeclasses.exits.Exit", key="동", location=self.rooms[north],
                          destination=self.rooms[northeast])
            self.assertEqual(after, self.graph(visited))

    def test_cross_sheet_and_remote_current_marker(self):
        self.char1.location = self.rooms["hq_concourse"]
        graph = self.graph({"dock", "hq_concourse"})
        self.assertTrue(any(direction == "서" and symbol == "+" for _, direction, symbol in graph.boundaries))
        self.char1.change(lambda p: p.update(visited=["dock", "hq_concourse"]))
        result = map_text(self.char1, "탐사대 전초구역")
        self.assertIsInstance(result, list, result)
        self.assertNotIn("@", result[1])
        self.assertIn("인자", map_text(self.char1, "근처 추가"))
        self.assertIn("인자", map_text(self.char1, "중심"))
        self.assertIn("조회할 수", map_text(self.char1, "없는 지도"))

    def test_ambiguous_center_and_hidden_candidate(self):
        southeast = "support_roof_se"
        northeast = "support_roof_ne"
        self.char1.change(lambda p: p.update(visited=[southeast, northeast]))
        with patch.dict(ROOMS[southeast], name=ROOMS[northeast]["name"]):
            query = f"중심 {ROOMS[northeast]['name']}"
            self.assertIn("여러 곳", map_text(self.char1, query))
            self.rooms[southeast].locks.add("view:false()")
            result = map_text(self.char1, query)
            self.assertIsInstance(result, list, result)
            self.assertIn(ROOMS[northeast]["name"], result[0])

    def test_current_dynamic_hub_is_bounded_and_never_uses_layout(self):
        for index in range(16):
            create_object("typeclasses.exits.Exit", key=f"임시 출구 {index:02d}",
                          location=self.char1.location, destination=self.rooms["dock"])
        graph = self.graph([], near=True)
        self.assertEqual(len(graph.notices), 12)
        self.assertTrue(graph.partial)
        self.assertEqual(graph.edges, ())
        self.assertNotIn(ROOMS["dock"]["name"], str(graph))

    def test_mismatched_public_exit_fails_for_visited_and_unvisited(self):
        target = "support_roof_ne"
        exit_obj = next(obj for obj in self.char1.location.exits if obj.key == "북동")
        for destination in (self.rooms["dock"], None):
            exit_obj.destination = destination
            for visited in ([], [target]):
                with self.subTest(destination=destination, visited=visited):
                    with self.assertRaises(RuntimeGraphMismatch):
                        self.graph(visited)
                    self.char1.change(lambda profile: profile.update(visited=visited))
                    with self.assertLogs("world.map_projection", level="WARNING") as log:
                        result = map_text(self.char1, "")
                    self.assertIn("RuntimeGraphMismatch", str(log.output))
                    self.assertIn("정확하게 표시할 수 없습니다", result)
                    self.assertNotIn("support_roof", result)
                    self.assertNotIn("방문한 장소만 표시됩니다", result)

    def test_hidden_exit_damage_and_absence_preserve_public_output(self):
        exit_obj = next(obj for obj in self.char1.location.exits if obj.key == "북동")
        exit_obj.locks.add("view:false()")
        visited = ["support_roof_ne"]
        before = self.graph(visited)
        for destination in (self.rooms["dock"], None):
            exit_obj.destination = destination
            with self.assertLogs("world.map_projection", level="WARNING") as log:
                self.assertEqual(before, self.graph(visited))
            self.assertIn("RuntimeGraphMismatch", str(log.output))
        exit_obj.delete()
        with self.assertLogs("world.map_projection", level="WARNING") as log:
            self.assertEqual(before, self.graph(visited))
        self.assertIn("누락", str(log.output))

    def test_management_tag_and_public_duplicate_integrity(self):
        from world.bootstrap import EXIT_CATEGORY

        source, target = self.char1.zone, "support_roof_ne"
        direction = "북동"
        identity = f"{source}:{direction}"
        original = next(obj for obj in self.char1.location.exits if obj.key == direction)
        before = self.graph([target])
        duplicate = create_object("typeclasses.exits.Exit", key=direction,
                                  location=self.char1.location, destination=self.rooms[target])
        duplicate.tags.add(identity, category=EXIT_CATEGORY)
        with self.assertRaisesRegex(RuntimeGraphMismatch, "중복"):
            self.graph([target])
        duplicate.locks.add("view:false()")
        with self.assertLogs("world.map_projection", level="WARNING"):
            self.assertEqual(before, self.graph([target]))
        duplicate.delete()
        original.tags.add("damaged", category=EXIT_CATEGORY)
        with self.assertRaisesRegex(RuntimeGraphMismatch, "정체성"):
            self.graph([target])
        self.assertTrue(any(entry["name"] == direction and entry["exists"]
                            for entry in exit_entries(self.char1)))

    def test_unobservable_non_exit_with_management_tag_is_diagnostic_only(self):
        from dataclasses import replace

        from world.bootstrap import EXIT_CATEGORY
        from world.observation import context_for

        context = context_for(self.char1)
        context = replace(context, snapshot=replace(context.snapshot, effective_visibility="poor"))
        before = self.graph([])
        prop = create_object("typeclasses.objects.Object", key="숨은 물체", location=self.char1.location)
        prop.locks.add("view:all()")
        prop.tags.add(f"{self.char1.zone}:북동", category=EXIT_CATEGORY)
        with patch("world.observation.context_for", return_value=context):
            with self.assertLogs("world.map_projection", level="WARNING"):
                self.assertEqual(before, self.graph([]))

    def test_room_lookup_rejects_extra_tags_and_zone_attribute_damage(self):
        from world.bootstrap import CATEGORY
        from world.map_projection import load_rooms

        zone = "support_roof_ne"
        room = self.rooms[zone]
        self.assertEqual(load_rooms({zone}), {zone: room})
        room.tags.add("extra_zone_identity", category=CATEGORY)
        with self.assertLogs("world.map_projection", level="WARNING"):
            self.assertEqual(load_rooms({zone}), {})
        room.tags.remove("extra_zone_identity", category=CATEGORY)
        room.db.zone_id = ("not", "a", "zone")
        with self.assertLogs("world.map_projection", level="WARNING"):
            self.assertEqual(load_rooms({zone}), {})

    def test_wrong_origin_does_not_expose_the_missing_direction(self):
        source = self.char1.zone
        exit_obj = next(obj for obj in self.char1.location.exits if obj.key == "북동")
        exit_obj.location = self.rooms["support_roof_ne"]
        with self.assertLogs("world.map_projection", level="WARNING") as log:
            graph = self.graph([])
        self.assertIn(f"{source}/북동", str(log.output))
        self.assertFalse(any(direction == "북동" for _, direction, _ in graph.boundaries))
        with self.assertRaisesRegex(RuntimeGraphMismatch, "정체성"):
            self.graph(["support_roof_ne"])

    def test_query_writes_no_state_and_dispatch_preserves_recovery_and_prompt(self):
        self.char1.change(lambda p: p.update(visited=[self.char1.zone]))
        self.char1.push_state = Mock()
        self.char2.push_state = Mock()
        session = self.connect_character(self.char1)
        self.enterContext(patch.object(session, "protocol_key", "websocket"))
        self.connect_character(self.char2)
        with CaptureQueriesContext(connection) as queries:
            self.assertIsInstance(map_text(self.char1, ""), list)
        self.assertFalse([entry for entry in queries if not entry["sql"].lstrip().startswith("SELECT")])
        before = self.char1.profile_snapshot()
        with patch("typeclasses.explorers.time", return_value=before["recovery"]["boundary"] + 120):
            with patch.object(self.char1, "msg") as output:
                with patch.object(self.char1, "reconcile_recovery", wraps=self.char1.reconcile_recovery) as recovery:
                    done = []
                    self.char1.execute_cmd("지도").addCallback(lambda result: done.append(True))
                    self.assertEqual(done, [True])
                    recovery.assert_called_once()
        self.assertEqual(output.call_args_list[-1].args[0].kind, "prompt")
        self.char1.push_state.assert_not_called()
        self.char2.push_state.assert_not_called()
