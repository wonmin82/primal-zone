"""방향 SSOT와 대각선 폐쇄 방향의 순수 계약."""

from unittest import TestCase
from unittest.mock import patch

from world import text as ft
from world.content import OPPOSITES, ROOMS
from world.content.directions import (
    DIRECTION_ALIASES,
    DIRECTION_ORDER,
    DIRECTIONS,
    OPPOSITE_DIRECTIONS,
    ordered_directions,
)
from world.navigation import blocked_exit_message


class DirectionTests(TestCase):
    def test_eight_direction_invariants(self):
        self.assertEqual(DIRECTION_ORDER, ("북", "북동", "동", "남동", "남", "남서", "서", "북서"))
        self.assertEqual(set(DIRECTIONS), set(DIRECTION_ORDER))
        self.assertEqual(set(DIRECTION_ALIASES.values()), {"n", "ne", "e", "se", "s", "sw", "w", "nw"})
        self.assertEqual(tuple(DIRECTION_ALIASES[key] for key in DIRECTION_ORDER),
                         ("n", "ne", "e", "se", "s", "sw", "w", "nw"))
        self.assertEqual(tuple(OPPOSITE_DIRECTIONS[key] for key in DIRECTION_ORDER),
                         ("남", "남서", "서", "북서", "북", "북동", "동", "남동"))
        self.assertEqual(tuple((DIRECTIONS[key]["row"], DIRECTIONS[key]["column"]) for key in DIRECTION_ORDER),
                         ((0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0), (0, 0)))
        self.assertEqual(len(set((d["row"], d["column"]) for d in DIRECTIONS.values())), 8)
        self.assertNotIn((1, 1), {(d["row"], d["column"]) for d in DIRECTIONS.values()})
        self.assertIs(OPPOSITES, DIRECTION_ALIASES)
        for direction in DIRECTION_ORDER:
            opposite = OPPOSITE_DIRECTIONS[direction]
            self.assertIn(opposite, DIRECTIONS)
            self.assertEqual(OPPOSITE_DIRECTIONS[opposite], direction)

    def test_clockwise_order_and_other_exit_fallback(self):
        self.assertEqual(ordered_directions(["계단", "남서", "북동", "북", "문"]), ["북", "북동", "남서", "계단", "문"])

    def test_diagonal_blocked_alias_is_trimmed_without_selector_confusion(self):
        with patch.dict(ROOMS["support_roof"], blocked_exits={"북동": "북동쪽 통로는 현재 폐쇄되어 있다."}):
            for value in ("북동", "ne", " NE "):
                self.assertEqual(blocked_exit_message("support_roof", value), "북동쪽 통로는 현재 폐쇄되어 있다.")
            for value in ("동북", "ne 모두", "북동 2", "북"):
                self.assertIsNone(blocked_exit_message("support_roof", value))

    def test_terminal_display_width_policy(self):
        for value, width in (("북", 2), ("북동", 4), ("｜", 2), ("／", 2), ("＼", 2), ("[현재]", 6)):
            self.assertEqual(ft.display_width(value), width)
        self.assertEqual(str(ft.row("북동", "표시", width=8)), "북동    표시")
