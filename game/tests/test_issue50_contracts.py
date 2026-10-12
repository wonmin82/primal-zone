"""D03/D04: 실제 Registry·Help·CmdSet을 전수 비교하는 통합 계약."""

from copy import deepcopy
from unittest.mock import patch

from commands.aliases import SHORTCUTS
from commands.default_cmdsets import CharacterCmdSet
from commands.help_pages import help_page
from commands.registry import COMMANDS
from evennia.commands.cmdhandler import CMD_NOMATCH
from world import rules
from world import text as ft

from tests.base import WorldCommandTest


class IntegratedContractTests(WorldCommandTest):
    def test_all_registry_aliases_actual_help_dispatch_and_semantics(self):
        titles = ("사용법", "예시", "실행 규칙", "제한", "관련 도움말")
        commands = [c for c in COMMANDS if c.key != CMD_NOMATCH]
        names = [name.casefold() for c in commands for name in (c.key, *c.aliases)]
        self.assertEqual(len(names), len(set(names)), "정식 명령/Alias 충돌")
        cmdset = CharacterCmdSet()
        # 동결은 #46~49 신규/변경 명령의 6절을 요구한다. 무관한 기존 명령의
        # 간결한 Help까지 새 정책으로 바꾸지 않고, 그 Alias/dispatcher는 전수 검사한다.
        required = {"봐", "출구", "점수", "가진거", "정보", "때려", "목록", "사", "팔아",
                    "쏴", "지도", "경험치", "장비", "착용", "벗어", "가져", "가치",
                    "줄임말", "해", "해지", "단축어", "회복", "조사",
                    "말", "대화", "대답", "대화거부", "열어", "닫아", "잠궈", "풀어"}
        required.update(c.key for c in commands if c.key.startswith("일행"))
        self.assertTrue(required <= {c.key for c in commands})
        for cls in commands:
            with self.subTest(command=cls.key):
                self.assertIsInstance(cmdset.get(cls.key), cls)
                page = help_page(cls.key, COMMANDS)
                self.assertIsInstance(page, ft.Text)
                self.assertTrue(getattr(cls, "summary", ""), cls.key)
                if cls.key in required:
                    self.assertEqual([title for title, _ in cls.help_sections], list(titles))
                    self.assertTrue(all(body and all(str(entry).strip() for entry in body)
                                        for _, body in cls.help_sections))
                    self.assertEqual([line for line in str(page).splitlines() if line in titles], list(titles))
                else:
                    self.assertIn("사용법", str(page))
                for name in (cls.key, *cls.aliases):
                    self.assertEqual(help_page(name, COMMANDS), page)
                    for suffix in ("도움", "도움말"):
                        with patch.object(self.char1, "msg") as messages:
                            done = []
                            self.char1.execute_cmd(name + " " + suffix).addCallback(lambda _: done.append(True))
                        self.assertEqual(done, [True])
                        sheets = [call.args[0] for call in messages.call_args_list
                                  if call.args and isinstance(call.args[0], ft.Text) and call.args[0].kind == "sheet"]
                        self.assertIn(page, sheets, (name, suffix))
        for alias in SHORTCUTS:
            self.assertIsNotNone(help_page(alias, COMMANDS), alias)

    def test_medical_level_boundaries_exact_formula_and_failure_invariance(self):
        # 기대값은 production 함수로 계산하지 않고 동결 공식에서 독립적으로 도출한다.
        for level in (1, 99, 100, rules.MAX_LEVEL):
            for missing in (1, 7, 20):
                with self.subTest(level=level, missing=missing):
                    p = rules.new_profile()
                    p.update(xp=rules.xp_threshold(level), credits=100000)
                    maximum = rules.stats(p)["max_hp"]
                    p["hp"] = maximum - missing
                    cost = max(1, (2 * missing + (level if level < 100 else 2 * level) + 9) // 10)
                    self.assertEqual(rules.treatment_quote(p, missing + 100, safe=True), (missing, cost))
                    self.assertEqual(rules.treat(p, missing + 100, safe=True), (missing, cost))
                    self.assertEqual((p["hp"], p["credits"]), (maximum, 100000 - cost))
                    p.update(hp=maximum - missing, credits=cost - 1)
                    before = deepcopy(p)
                    with self.assertRaises(rules.RuleError):
                        rules.treat(p, missing, safe=True)
                    self.assertEqual(p, before)
