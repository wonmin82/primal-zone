"""소형 나침반은 저장 상태 없이 실제 출구 정보와 semantic role로 계산한다."""

from unittest import TestCase

from world import text as ft
from world.content.directions import PLANAR_DIRECTIONS
from world.exit_presentation import exit_diagram


class ExitDiagramTests(TestCase):
    def test_planar_combinations_keep_three_ascii_columns(self):
        glyphs = {"북": (0, 1, "|"), "북동": (0, 2, "/"), "동": (1, 2, "-"),
                  "남동": (2, 2, "\\"), "남": (2, 1, "|"), "남서": (2, 0, "/"),
                  "서": (1, 0, "-"), "북서": (0, 0, "\\")}
        for names in ([], ["북"], ["북동"], ["동", "서"], ["북", "동", "남", "서"], PLANAR_DIRECTIONS):
            output = exit_diagram(names)
            canvas = [line[:3] for line in output.splitlines()[:3]]
            self.assertEqual(len(canvas), 3)
            self.assertEqual(canvas[1][1], "o")
            for name, (row, column, glyph) in glyphs.items():
                self.assertEqual(canvas[row][column], glyph if name in names else ".")
            self.assertTrue(all(ft.display_width(line) == 3 and line.isascii() for line in canvas))

    def test_vertical_shape_and_whole_symbol_restriction_role(self):
        for names, symbol in (([], "o"), (["위"], "^"), (["아래"], "v"), (["위", "아래"], "X")):
            for restricted in (False, True):
                entries = [dict(name=name, exists=True, can_move=not (restricted and index == 0))
                           for index, name in enumerate(names)]
                output = exit_diagram(entries)
                self.assertEqual(output.splitlines()[1][1], symbol)
                token = next(part for part in output.segments if part["text"] == symbol)
                self.assertEqual(token["role"], "object" if not names else "warning" if restricted else "direction")
                self.assertNotIn("^이다", output)

    def test_special_names_are_integrated_once_and_wrapped_at_names(self):
        names = ["1층", "2층", "3층", "4층", "5층", "옥상"]
        output = exit_diagram(names)
        self.assertNotIn("기타 출구", output)
        self.assertEqual([line[:3] for line in output.splitlines()[:3]], ["...", ".o.", "..."])
        for name in names:
            self.assertEqual(output.count(name), 1)
        self.assertTrue(all(ft.display_width(line) <= 41 for line in output.splitlines()))
        output = exit_diagram([dict(name="위", exists=True, can_move=False),
                               dict(name="북", exists=False, can_move=False),
                               dict(name="나가기", exists=True, can_move=True)])
        self.assertEqual(output.splitlines()[0], "...")
        self.assertIn("출입 제한: 위", output)
        self.assertIn("폐쇄: 북", output)
        self.assertIn("갈 수 있는 곳은 나가기이다.", output)
