"""배치·렌더러의 방향, 표시 셀, 선언 오류와 교차 경계 회귀."""

from unittest import TestCase

from world.map_layout import LayoutUnrepresentable, MapDeclarationInvalid, layout, render
from world.text import display_width


class MapLayoutTests(TestCase):
    def make_layout(self, names, edges, positions=None, routes=None, anchors=()):
        return layout(names, edges, positions or {}, routes or {}, anchors)

    def test_deterministic_square_cycle_with_another_component(self):
        nodes = ("a", "b", "c", "d", "isolated")
        edges = (
            ("a", "동", "b"), ("b", "서", "a"),
            ("b", "남", "c"), ("c", "북", "b"),
            ("c", "서", "d"), ("d", "동", "c"),
            ("a", "남", "d"), ("d", "북", "a"),
        )
        result = self.make_layout(nodes, edges, anchors=("a",))
        reversed_input = self.make_layout(reversed(nodes), reversed(edges), anchors=("a",))
        self.assertEqual(result, reversed_input)
        self.assertEqual(len(result.rooms), 5)
        self.assertEqual(len(result.paths), 4)
        self.assertEqual([str(row) for row in render(result, current="a").lines], [
            "@─o     o", "│ │", "o─o",
        ])

    def test_eight_direction_hub(self):
        nodes = ("a", "n", "ne", "e", "se", "s", "sw", "w", "nw")
        edges = tuple(
            ("a", name, target)
            for name, target in zip(("북", "북동", "동", "남동", "남", "남서", "서", "북서"), nodes[1:])
        )
        result = self.make_layout(nodes, edges, anchors=("a",))
        unicode_map = render(result, current="a")
        ascii_map = render(result, current="a", ascii_only=True)
        self.assertEqual(list(map(str, unicode_map.lines)), [
            "o o o", " ╲│╱", "o─@─o", " ╱│╲", "o o o",
        ])
        self.assertEqual(list(map(str, ascii_map.lines)), [
            "o o o", " \\|/", "o-@-o", " /|\\", "o o o",
        ])
        for row in (*unicode_map.lines, *ascii_map.lines):
            self.assertLessEqual(display_width(row), 60)

    def test_relative_hint_and_route_share_one_bidirectional_path(self):
        result = self.make_layout(
            ("a", "b"), (("a", "동", "b"), ("b", "서", "a")),
            {"b": ("a", (3, 1))},
            {("a", "동"): ((2, 0), (2, 1))},
        )
        self.assertEqual(len(result.paths), 1)
        self.assertEqual(result.paths[0].points, ((0, 0), (2, 0), (2, 1), (3, 1)))
        self.assertEqual(list(map(str, render(result, current="a").lines)), [
            "@───·", "    │", "    ·─o",
        ])

    def test_route_can_supply_endpoint_distance_without_a_position_hint(self):
        result = self.make_layout(
            ("a", "b"), (("a", "동", "b"),),
            routes={("a", "동"): ((2, 0), (2, 1))},
            anchors=("b",),
        )
        self.assertEqual(result.rooms["b"], (3, 1))
        self.assertEqual(result.paths[0].points[1:3], ((2, 0), (2, 1)))

    def test_spacing_matches_existing_neighbors_when_a_hint_expands_a_cycle(self):
        result = self.make_layout(
            ("a", "b", "c", "z"),
            (("a", "동", "z"), ("a", "남", "b"), ("b", "동", "c"), ("z", "남", "c")),
            positions={"z": ("a", (2, 0))}, anchors=("a",),
        )
        self.assertEqual(result.rooms, {"a": (0, 0), "z": (2, 0), "b": (0, 1), "c": (2, 1)})
        self.assertEqual(list(map(str, render(result, current="a").lines)), [
            "@───o", "│   │", "o───o",
        ])

    def test_place_all_fixed_anchor_neighbors_before_following_one_branch(self):
        result = self.make_layout(
            ("a", "b", "c", "d", "z"),
            (("a", "서", "b"), ("b", "남", "c"), ("c", "동", "d"),
             ("a", "남동", "z"), ("z", "남", "d")),
            positions={"z": ("a", (3, 3))}, anchors=("a",),
        )
        self.assertEqual(
            result.rooms, {"a": (1, 0), "z": (4, 3), "b": (0, 0), "d": (4, 4), "c": (0, 4)}
        )

    def test_invalid_hints_and_unsupported_topology_are_distinct(self):
        edges = (("a", "동", "b"), ("b", "서", "a"))
        for positions, routes in (
            ({"b": ("a", (0, 0))}, {}),
            ({"b": ("a", (2, 0)), "a": ("b", (-2, 0))}, {}),
            ({"b": ("a", (2, 1))}, {}),
            ({}, {("a", "동"): ((1, 1),)}),
            ({}, {("a", "동"): ((2, 0), (1, 0))}),
            ({}, {("a", "동"): ((2, 0), (2, 1), (1, 1))}),
            ({}, {("a", "동"): ((2, 0), (2, 1)), ("b", "서"): ((-1, 0),)}),
        ):
            with self.subTest(positions=positions, routes=routes):
                with self.assertRaises(MapDeclarationInvalid):
                    self.make_layout(("a", "b"), edges, positions, routes)

        with self.assertRaises(LayoutUnrepresentable):
            self.make_layout(("a", "b", "c"), (
                ("a", "동", "b"), ("b", "동", "c"), ("c", "동", "a"),
            ))

    def test_crossing_diagonals_are_rejected_even_between_logical_cells(self):
        nodes = ("a", "b", "c", "d")
        edges = (("a", "남동", "c"), ("b", "남서", "d"), ("a", "동", "b"))
        with self.assertRaises(LayoutUnrepresentable):
            self.make_layout(nodes, edges)

    def test_route_hint_cannot_pass_through_another_room(self):
        # 중간 Room을 자동 선택한 배치만 실패하면 선언을 무효로 판정하지 않는다.
        with self.assertRaises(LayoutUnrepresentable):
            self.make_layout(
                ("a", "b", "c", "n"),
                (("a", "동", "b"), ("a", "북", "n"), ("n", "남동", "c")),
                routes={("a", "동"): ((2, 0),)}, anchors=("a",),
            )
        with self.assertRaises(MapDeclarationInvalid):
            self.make_layout(
                ("a", "b", "c", "n"),
                (("a", "동", "b"), ("a", "북", "n"), ("n", "남동", "c")),
                positions={"n": ("a", (0, -1)), "c": ("n", (1, 1))},
                routes={("a", "동"): ((2, 0),)}, anchors=("a",),
            )

    def test_valid_hint_shifting_the_whole_crossing_leaves_it_unrepresentable(self):
        with self.assertRaises(LayoutUnrepresentable):
            self.make_layout(
                ("anchor", "a", "b", "c", "d"),
                (("anchor", "남", "a"), ("a", "남동", "c"),
                 ("b", "남서", "d"), ("a", "동", "b")),
                positions={"a": ("anchor", (0, 3))}, anchors=("anchor",),
            )

    def test_known_room_and_boundary_symbols_never_overwrite_an_unrelated_line(self):
        result = self.make_layout(("a", "b", "c"), (
            ("a", "동", "b"), ("b", "남", "c"),
        ))
        blocked = render(result, (("a", "동", "×"), ("b", "동", "+"), ("c", "동", "?")),
                         current="a")
        self.assertEqual(list(map(str, blocked.lines)), ["@×o+", "  │", "  o?"])
        ambiguous = render(result, (("a", "동", "?"),), current="a")
        self.assertEqual(ambiguous.omitted, (("a", "동", "?"),))
        self.assertEqual(str(ambiguous.lines[0]), "@─o")

    def test_large_maps_and_long_hints_render_a_bounded_viewport(self):
        for size in (10, 100, 1000):
            for direction in ("동", "남"):
                nodes = tuple(f"room-{index:04d}" for index in range(size))
                edges = tuple((a, direction, b) for a, b in zip(nodes, nodes[1:]))
                result = self.make_layout(nodes, edges)
                for ascii_only, marker in ((True, "..."), (False, "…")):
                    view = render(result, current=nodes[size // 2], ascii_only=ascii_only)
                    body = "\n".join(view.lines)
                    self.assertEqual(body.count("@"), 1)
                    self.assertLessEqual(len(view.lines), 24)
                    self.assertTrue(all(display_width(row) <= 60 for row in view.lines))
                    self.assertEqual(view.partial, size > 10)
                    self.assertEqual(marker in body, size > 10)
                    self.assertFalse(view.omitted)

        sparse = self.make_layout(
            ("a", "b"), (("a", "동", "b"),), {"b": ("a", (10**12, 0))}
        )
        view = render(sparse, current="a")
        self.assertTrue(view.partial)
        self.assertEqual(len(view.lines), 1)
        self.assertTrue(view.lines[0].endswith("…"))
