"""실제 도움말 dispatcher·semantic 출력과 기존 일반 도움말의 경계를 검증한다."""

from unittest.mock import Mock, patch

from commands.help_pages import help_page, root_page
from commands.registry import COMMANDS
from evennia.utils.ansi import strip_ansi
from typeclasses.explorers import Explorer
from world import text as ft

from tests.base import WorldCommandTest


class ShortcutHelpTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.char1.push_state = Mock()
        self.enterContext(patch("typeclasses.explorers.time",
                                return_value=self.char1.profile_snapshot()["recovery"]["updated_at"]))

    def page(self, name):
        with patch.object(self.char1, "msg") as output:
            completed = []
            self.char1.execute_cmd(name + " 도움말").addCallback(lambda _: completed.append(True))
            self.assertEqual(completed, [True])
        return next(call.args[0] for call in output.call_args_list
                    if call.args and isinstance(call.args[0], ft.Text) and call.args[0].kind == "sheet")

    def test_four_pages_have_same_sections_order_semantics_and_no_double_frame(self):
        titles = ("사용법", "예시", "실행 규칙", "제한", "관련 도움말")
        for name in ("해", "줄임말", "해지", "단축어"):
            with self.subTest(name=name):
                page = self.page(name)
                self.assertTrue(page.startswith(f"[{name}]\n"))
                self.assertEqual(page, help_page(name, COMMANDS))
                lines = page.splitlines()
                self.assertEqual([line for line in lines if line in titles], list(titles))
                self.assertNotIn("\n\n\n", page)
                self.assertNotIn("────", page)
                self.assertEqual(strip_ansi(page.ansi()), page)
                self.assertTrue(all(any(part["role"] == "title" and part["text"] == title
                                        for part in page.segments) for title in titles))
                self.assertIn("줄임말 도움말" if name != "줄임말" else "해 도움말",
                              [part["text"] for part in page.segments if part["role"] == "command"])

    def test_sequence_help_explains_partial_execution_and_progressive_not_arguments(self):
        page = self.page("해")
        for value in ("두 개 이상", "북, 봐 해", "실행 직전", "새 장소", "실패 시", "계속",
                      "중단", "되돌리지", "10개", "1,000자", "2,000자", "추가 응답", "북 봐",
                      "하나", "줄임말 도움말"):
            self.assertIn(value, page)

    def test_personal_help_contains_management_variables_limits_and_priority(self):
        page = self.page("줄임말")
        for value in ("이름 줄임말", "이름 정의 줄임말", "이름 해지", "등록·수정", "모두 삭제 줄임말",
                      "모두 삭제 확인 줄임말", "$1~$9", "$*", "$$", "행동 이름", "잠긴 명령",
                      "엔진", "새로운 묶음", "100개", "1~20자", "원본 정의 최대 2,000자",
                      "호출 인자 최대 2,000자", "10개", "1,000자", "5단계", "60초가 지나기 전에",
                      "구형 비활성", "해지 도움말", "단축어 도움말"):
            self.assertIn(value, page)
        self.assertNotIn("look 도움", page)

    def test_deletion_and_global_help_do_not_confuse_personal_and_system(self):
        page = self.page("해지")
        for value in ("이름 해지", "모두 해지", "전체 삭제가 아니라", "연쇄 변경하지",
                      "별도로 직접 입력", "60초가 지나기 전에"):
            self.assertIn(value, page)
        page = self.page("단축어")
        for value in ("전역 줄임말", "상 → 점수", "장 → 장비", "정확하게 일치", "한 번만",
                      "개인 줄임말보다 우선", "등록·수정·삭제할 수 없습니다"):
            self.assertIn(value, page)

    def test_general_help_keeps_usage_alias_shortcut_and_category_layout(self):
        for name in ("공격", "봐", "상태"):
            page = self.page(name)
            self.assertIn("사용법\n", page)
            self.assertIn("\n실행 규칙\n", page)
        self.assertEqual(self.page("상"), self.page("점수"))
        self.assertEqual(self.page("보"), self.page("봐"))
        self.assertIn("묶음 실행", self.page("입력"))
        self.assertIn("해지", self.page("편의"))
        self.assertIn("해지", root_page())
