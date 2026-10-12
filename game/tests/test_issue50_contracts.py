"""D03/D04: 실제 Registry·Help·CmdSet을 전수 비교하는 통합 계약."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from commands.account_commands import Quit, Who
from commands.aliases import SHORTCUTS
from commands.default_cmdsets import AccountCmdSet, CharacterCmdSet
from commands.help_pages import help_page
from commands.registry import COMMANDS
from evennia.commands.cmdhandler import CMD_NOMATCH
from world import rules
from world import text as ft

from tests.base import WorldCommandTest


class IntegratedContractTests(WorldCommandTest):
    def test_frozen_all_keys_aliases_and_input_styles(self):
        expected = json.loads((Path(__file__).resolve().parents[2]/'scripts/issue50-command-contract.json').read_text(encoding='utf-8'))
        # Evennia 6.1은 Alias를 set에서 정규화한다. Alias 순서는 계약이 아니지만
        # key/전체 Alias 집합/Registry 순서/입력 방식은 정확히 보존한다.
        self.assertEqual([{'key': c.key, 'aliases': sorted(c.aliases), 'input_style': getattr(c, 'input_style', 'standalone')}
                          for c in [*COMMANDS, Who, Quit]], expected)

    def test_all_registry_aliases_actual_help_dispatch_and_semantics(self):
        titles = ("사용법", "예시", "실행 규칙", "제한", "관련 도움말")
        commands = [c for c in [*COMMANDS, Who] if c.key != CMD_NOMATCH]
        names = [name.casefold() for c in commands for name in (c.key, *c.aliases)]
        self.assertEqual(len(names), len(set(names)), "정식 명령/Alias 충돌")
        cmdset, account_cmdset = CharacterCmdSet(), AccountCmdSet()
        # 동결은 #46~49 신규/변경 명령의 6절을 요구한다. 무관한 기존 명령의
        # 간결한 Help까지 새 정책으로 바꾸지 않고, 그 Alias/dispatcher는 전수 검사한다.
        required = {"봐", "출구", "도움", "누구", "점수", "가진거", "정보", "때려", "목록", "사", "팔아",
                    "쏴", "지도", "경험치", "장비", "착용", "벗어", "가져", "가치",
                    "줄임말", "해", "해지", "단축어", "회복", "조사",
                    "말", "대화", "대답", "대화거부", "열어", "닫아", "잠궈", "풀어"}
        required.update(c.key for c in commands if c.key.startswith("일행"))
        self.assertTrue(required <= {c.key for c in commands})
        for cls in commands:
            with self.subTest(command=cls.key):
                self.assertIsInstance((account_cmdset if cls is Who else cmdset).get(cls.key), cls)
                page = help_page(cls.key, commands)
                self.assertIsInstance(page, ft.Text)
                self.assertTrue(getattr(cls, "summary", ""), cls.key)
                if cls.key in required:
                    self.assertEqual([title for title, _ in cls.help_sections], list(titles))
                    self.assertTrue(all(body and all(str(entry).strip() for entry in body)
                                        for _, body in cls.help_sections))
                    self.assertEqual([line for line in str(page).splitlines() if line in titles], list(titles))
                    for target in dict(cls.help_sections)['관련 도움말']:
                        query = target.removesuffix(' 도움말').removesuffix(' 도움')
                        self.assertIsNotNone(help_page(query, commands), target)
                else:
                    self.assertIn("사용법", str(page))
                for name in (cls.key, *cls.aliases):
                    self.assertEqual(help_page(name, commands), page)
                    for suffix in ("도움", "도움말"):
                        with patch.object(self.char1, "msg") as messages:
                            done = []
                            self.char1.execute_cmd(name + " " + suffix).addCallback(lambda _: done.append(True))
                        self.assertEqual(done, [True])
                        sheets = [call.args[0] for call in messages.call_args_list
                                  if call.args and isinstance(call.args[0], ft.Text) and call.args[0].kind == "sheet"]
                        self.assertIn(page, sheets, (name, suffix))
        for alias in SHORTCUTS:
            self.assertIsNotNone(help_page(alias, commands), alias)
        # 문서의 명시된 명령/Alias 표는 실제 metadata와 일치해야 한다.
        document = (Path(__file__).resolve().parents[2]/'docs/commands.md').read_text(encoding='utf-8')
        by_key = {c.key: c for c in commands}
        checked = set()
        for line in document.splitlines():
            cells = [part.strip().strip('`') for part in line.strip('|').split('|')]
            if len(cells) < 2 or cells[0] not in by_key:
                continue
            key, value = cells[:2]
            if key == '말':
                value = 'say'  # 작은따옴표는 Alias가 아니라 기존 입력 문법이다.
            value = value.replace('ASCII 0x60 백틱', '`')
            aliases = set() if value == '없음' else {part.strip().strip('`') if part.strip() != '`' else '`' for part in value.split(',')}
            self.assertEqual(aliases, set(by_key[key].aliases), key)
            checked.add(key)
        self.assertTrue({'누구', '정보', '쏴', '회복', '말', '일행승계', '잠궈'} <= checked)

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
