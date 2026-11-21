"""탐사 지도 정적 분류와 선언의 검증."""

from collections import Counter
from unittest import TestCase

from world.content import REGIONS, ROOM_REGION, ROOMS
from world.content.headquarters import ELEVATOR_ROOM, HQ_LANDINGS
from world.map_layout import MapDeclarationInvalid, layout
from world.map_metadata import build_catalog, validate_geometry


def sample():
    rooms = {
        "a": {"name": "복도", "exits": {"동": "b", "남": "c"}},
        "b": {"name": "창고", "exits": {"서": "a"}},
        "c": {"name": "보관실", "exits": {"북": "a"}},
    }
    regions = {"sample": {"name": "폐허", "entry": "a", "rooms": tuple(rooms)}}
    return rooms, regions, dict.fromkeys(rooms, "sample")


class MapMetadataTests(TestCase):
    def test_all_production_rooms_and_sheet_topologies(self):
        metadata = build_catalog(ROOMS, REGIONS, ROOM_REGION)
        self.assertEqual(
            Counter(ROOM_REGION.values()), {"headquarters": 52, "outpost": 8, "deep_jungle": 7}
        )
        self.assertEqual(set(metadata.room_sheet), set(ROOMS))
        connectors = {room for room, sheet in metadata.room_sheet.items() if sheet is None}
        self.assertEqual(connectors, {ELEVATOR_ROOM, *(stairs for _, _, stairs in HQ_LANDINGS)})
        self.assertEqual(
            {sheet.id: len(sheet.rooms) for sheet in metadata.sheets.values()},
            {
                "deep_jungle": 7, "headquarters_1f": 4, "headquarters_2f": 6,
                "headquarters_3f": 6, "headquarters_4f": 9, "headquarters_5f": 11,
                "headquarters_roof": 9, "outpost": 8,
            },
        )
        self.assertEqual((metadata.positions, metadata.routes), ({}, {}))
        for sheet in metadata.sheets.values():
            with self.subTest(sheet=sheet.id):
                edges = [
                    (room, direction, target) for room in sheet.rooms
                    for direction, target in ROOMS[room]["exits"].items()
                    if metadata.room_sheet[target] == sheet.id
                ]
                self.assertIsNotNone(layout(sheet.rooms, edges, {}, {}, sheet.anchors))
        for region in ("outpost", "deep_jungle"):
            self.assertNotIn("map", REGIONS[region])
            self.assertTrue(all("map" not in ROOMS[room] for room in REGIONS[region]["rooms"]))

    def test_new_planar_regions_require_no_map_declaration(self):
        for size in (10, 100, 1000):
            with self.subTest(size=size):
                rooms = {f"room{i}": {"name": f"장소 {i}", "exits": {}} for i in range(size)}
                regions = {"synthetic": {"name": "합성 구역", "entry": "room0", "rooms": tuple(rooms)}}
                association = dict.fromkeys(rooms, "synthetic")
                metadata = build_catalog(rooms, regions, association)
                sheet = metadata.sheets["synthetic"]
                self.assertEqual((sheet.name, sheet.anchors), ("합성 구역", ("room0",)))
                self.assertEqual(set(sheet.rooms), set(rooms))
                self.assertEqual(metadata.room_sheet, association)

    def test_multiple_sheets_and_connector(self):
        rooms, regions, association = sample()
        regions["sample"]["map"] = {"sheets": {
            "west": {"name": "서쪽 관", "anchor": "a"}, "east": {"name": "동쪽 관"},
        }}
        rooms["a"]["map"] = {"sheet": "west"}
        rooms["b"]["map"] = {"sheet": "east"}
        rooms["c"]["map"] = {"presentation": "connector"}
        metadata = build_catalog(rooms, regions, association)
        self.assertEqual(metadata.room_sheet, {"a": "west", "b": "east", "c": None})
        self.assertEqual(metadata.sheets["west"].anchors, ("a",))
        self.assertEqual(metadata.sheets["east"].anchors, ())
        rooms["b"]["map"] = {}
        with self.assertRaises(MapDeclarationInvalid):
            build_catalog(rooms, regions, association)

    def test_invalid_declarations_and_reserved_or_duplicate_names(self):
        for metadata in (
            (), {"unknown": True}, {"sheets": {}}, {"sheets": {"": {}}},
            {"sheets": {"same": {"name": "목록"}}},
            {"sheets": {"same": {"name": "중심 방"}}},
            {"sheets": {"same": {"name": "아스키", "aliases": ["ASCII"]}}},
            {"sheets": {"same": {"name": "동쪽", "anchor": "missing"}}},
            {"sheets": {"one": {"name": "동쪽"}, "two": {"name": "동 쪽"}}},
        ):
            with self.subTest(metadata=metadata):
                rooms, regions, association = sample()
                regions["sample"]["map"] = metadata
                with self.assertRaises(MapDeclarationInvalid):
                    build_catalog(rooms, regions, association)
        for metadata in (
            None, {"unknown": "a"}, {"sheet": "not_a_sheet"}, {"presentation": []},
            {"presentation": "connector", "sheet": "sample"}, {"aliases": [0]},
        ):
            with self.subTest(metadata=metadata):
                rooms, regions, association = sample()
                rooms["a"]["map"] = metadata
                with self.assertRaises(MapDeclarationInvalid):
                    build_catalog(rooms, regions, association)

    def test_same_sheet_duplicate_room_names_require_distinct_aliases(self):
        rooms, regions, association = sample()
        rooms["c"]["name"] = rooms["b"]["name"]
        rooms["b"]["map"] = {"aliases": ("동쪽 창고",)}
        with self.assertRaises(MapDeclarationInvalid):
            build_catalog(rooms, regions, association)
        rooms["c"]["map"] = {"aliases": ("동쪽창고",)}
        with self.assertRaises(MapDeclarationInvalid):
            build_catalog(rooms, regions, association)
        rooms["c"]["map"] = {"aliases": ("남쪽 창고",)}
        metadata = build_catalog(rooms, regions, association)
        self.assertEqual(metadata.room_aliases, {"b": ("동쪽 창고",), "c": ("남쪽 창고",)})

    def test_sheet_ids_reject_empty_whitespace_control_and_normalized_collisions(self):
        for sheet_id in ("", " ", "west wing", "west\t", "west\x00", "_"):
            with self.subTest(sheet_id=sheet_id), self.assertRaises(MapDeclarationInvalid):
                rooms, regions, association = sample()
                regions["sample"]["map"] = {"sheets": {sheet_id: {"name": "폐허 지도"}}}
                build_catalog(rooms, regions, association)

        for duplicate in ("west_wing", "West-Wing"):
            with self.subTest(duplicate=duplicate), self.assertRaises(MapDeclarationInvalid):
                rooms, regions, association = sample()
                regions["sample"]["map"] = {"sheets": {"west_wing": {"name": "폐허 지도"}}}
                regions["other"] = {"name": "다른 구역", "entry": "d", "rooms": ("d",),
                                    "map": {"sheets": {duplicate: {"name": "다른 지도"}}}}
                rooms["d"] = {"name": "다른 장소", "exits": {}}
                association["d"] = "other"
                build_catalog(rooms, regions, association)

        rooms, regions, association = sample()
        self.assertEqual(build_catalog(rooms, regions, association).sheets["sample"].id, "sample")
        regions["sample"]["map"] = {"sheets": {"west_wing": {"name": "폐허 지도"}}}
        self.assertEqual(build_catalog(rooms, regions, association).room_sheet,
                         dict.fromkeys(rooms, "west_wing"))

    def test_position_and_route_hint_types_references_ownership_and_cycles(self):
        rooms, regions, association = sample()
        rooms["b"]["map"] = {"layout": {"position": {"relative_to": "a", "offset": [6, 2]}}}
        rooms["a"]["map"] = {"layout": {"routes": {"동": {"via": [[2, 0], [2, 2], [4, 2]]}}}}
        metadata = build_catalog(rooms, regions, association)
        self.assertEqual(metadata.positions, {"b": ("a", (6, 2))})
        self.assertEqual(metadata.routes, {("a", "동"): ((2, 0), (2, 2), (4, 2))})
        validate_geometry(rooms, metadata)

        for relative_to, offset in (("c", [6, 2]), ("a", [0, 0]), ("a", [False, 2])):
            with self.subTest(reference=relative_to, offset=offset):
                rooms["b"]["map"]["layout"]["position"] = {"relative_to": relative_to, "offset": offset}
                with self.assertRaises(MapDeclarationInvalid):
                    build_catalog(rooms, regions, association)

        rooms["b"]["map"]["layout"]["position"] = {"relative_to": "a", "offset": [6, 2]}
        rooms["a"]["map"]["layout"]["position"] = {"relative_to": "b", "offset": [-6, -2]}
        with self.assertRaises(MapDeclarationInvalid):
            build_catalog(rooms, regions, association)
        del rooms["a"]["map"]["layout"]["position"]

        rooms["b"]["map"]["layout"]["routes"] = {"서": {"via": [[-1, 0]]}}
        with self.assertRaises(MapDeclarationInvalid):
            build_catalog(rooms, regions, association)
        del rooms["b"]["map"]["layout"]["routes"]
        for via in ([], [[0, 0]], [[1, 0], [1, 0]], [[0, 1]]):
            rooms["a"]["map"]["layout"]["routes"]["동"]["via"] = via
            with self.subTest(via=via), self.assertRaises(MapDeclarationInvalid):
                build_catalog(rooms, regions, association)

    def test_hint_coordinate_collision_is_a_declaration_error(self):
        rooms, regions, association = sample()
        for room in ("b", "c"):
            rooms[room]["map"] = {"layout": {"position": {"relative_to": "a", "offset": [2, 2]}}}
        with self.assertRaises(MapDeclarationInvalid):
            validate_geometry(rooms, build_catalog(rooms, regions, association))
