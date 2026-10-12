"""D03/D04: 실제 Registry·Help·CmdSet을 전수 비교하는 통합 계약."""

import json
import re
import sys
from collections import Counter
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
    def _audit_feature_documents(self, documents):
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / 'scripts'))
        from commands import shortcuts as s
        from issue50_document_contracts import number, tables, verify
        from server.conf.cmdparser import select_command
        from typeclasses import interactables
        from typeclasses.interactables import INTERACTABLES
        from world.content import DIRECTION_ALIASES, DIRECTION_SHORTCUTS, ROOMS
        from world.content.doors import AUTO_CLOSE_SECONDS, DOORS
        from world.dialogue_intents import intents_for
        from world.equipment import SLOT_CAPACITY
        from world.multiplayer import PARTY_INVITE_TTL_SECONDS, PARTY_MAX_SIZE
        from world.npc_dialogue import validate_message
        cmdset = CharacterCmdSet()
        cmdset.add(Who())
        cmdset.add(Quit())
        commands = [*COMMANDS, Who, Quit]
        directions = set(DIRECTION_ALIASES) | set(DIRECTION_ALIASES.values()) | set(DIRECTION_SHORTCUTS)
        directions.update(direction for room in ROOMS.values() for direction in room['exits'])
        def example(text, definitions):
            if text in directions:
                return  # 경로/권한은 실제 Exit 및 브라우저 회귀가 별도로 검증한다.
            selected = select_command(text, cmdset, self.char1, shortcuts=definitions)
            if not selected.matches:
                raise ValueError('문서 예시의 미등록/제거된 행동: ' + text)
            if text.endswith((' 도움', ' 도움말')):
                query = text.rsplit(None, 1)[0]
                if help_page(query, commands) is None:
                    raise ValueError('문서 예시의 없는 Help')
        def medical(level, hp):
            p = rules.new_profile()
            p.update(xp=rules.xp_threshold(level), credits=100000)
            p['hp'] = rules.stats(p)['max_hp'] - hp
            return rules.treatment_quote(p, hp, safe=True)[1]
        counts = Counter(data['typeclass'] for data in INTERACTABLES.values())
        roles = {'윤대장·선발대 길잡이': counts['Commander'] + counts['Pathfinder'], '기술 교관': counts['SkillTrainer'],
                 '특성 교관': counts['AttributeTrainer'], '훈련관리관': counts['TrainingManager'], '상인': counts['Shopkeeper'],
                 '의무관': counts['Doctor'], '정산관': counts['SettlementOfficer']}
        self.assertEqual(sum(roles.values()), 22)
        role_types = {'윤대장·선발대 길잡이': 'Commander', '기술 교관': 'SkillTrainer', '특성 교관': 'AttributeTrainer',
                      '훈련관리관': 'TrainingManager', '상인': 'Shopkeeper', '의무관': 'Doctor', '정산관': 'SettlementOfficer'}
        for header, row in tables(documents['docs/npc-dialogue.md']):
            if header[:2] != ['역할', '수']:
                continue
            kind = role_types[row[0]]
            intents = intents_for(kind)
            tokens = set(re.findall(r'[가-힣]+', row[2]))
            allowed = {word for i in intents if not i.mutates_state for word in (i.keyword, *i.aliases)}
            self.assertTrue(tokens <= allowed, row[0])
            self.assertTrue({i.keyword for i in intents if not i.mutates_state} <= tokens, row[0])
            actions = {s.strip() for s in row[3].removesuffix(' Intent').split('·')}
            expected_actions = {i.keyword for i in intents if i.mutates_state} if kind == 'Commander' else set(getattr(interactables, kind).actions)
            self.assertEqual(actions, expected_actions, row[0])
        capacities = {}
        for header, row in tables(documents['docs/equipment.md']):
            if header == ['slot', '표시', 'capacity']:
                for slot in row[0].split(' / '):
                    capacities[slot] = number(row[2])
        self.assertEqual(capacities, SLOT_CAPACITY)
        party_document = documents['docs/party-and-tactics.md']
        self.assertEqual(re.findall(r'정원 (\d+)명', party_document), [str(PARTY_MAX_SIZE)])
        self.assertEqual(re.findall(r'TTL은 (\d+)초', party_document), [str(PARTY_INVITE_TTL_SECONDS)])
        self.assertEqual(re.findall(r'연속 (\d+)초가 경과', party_document), ['600'])
        self.assertEqual(re.findall(r'발화 1~(\d+)자', documents['docs/npc-dialogue.md']), ['300'])
        self.assertEqual((DOORS['hq_admin_door']['initial_state'], DOORS['recovery_room_door']['initial_state'],
                          DOORS['recovery_room_door']['lockable']), ('LOCKED', 'OPEN', False))
        self.assertEqual(len(validate_message('가' * 300)), 300)
        with self.assertRaises(rules.RuleError):
            validate_message('가' * 301)
        result = verify(documents, {c.key: list(c.aliases) for c in commands},
                        {'이름': s.MAX_NAME_CHARACTERS, '저장 개수': s.MAX_SHORTCUTS, '원본 정의': s.MAX_DEFINITION_CHARACTERS,
                         '호출 인자': s.MAX_ARGUMENT_CHARACTERS, '직접 즉석 묶음 입력': s.MAX_DEFINITION_CHARACTERS,
                         '실제 하위 실행 시도': s.MAX_COMMANDS, '개인 정의 깊이': s.MAX_DEPTH, '최종 하위 문자열 합계': s.MAX_EXPANDED_CHARACTERS},
                        AUTO_CLOSE_SECONDS, rules.PROFILE_VERSION, roles, example, medical)
        # 실제 템플릿 Action은 동일 parser/Help 계약을 통과해야 한다.
        html = (root / 'game/web/templates/webclient/webclient.html').read_text(encoding='utf-8')
        actions = re.findall(r'data-command="([^"]+)"', html)
        for action in actions:
            example(action, {})
        self.assertGreater(len(actions), 20)
        self.assertIn('웹 조작은 기존 SURROUNDINGS/이동 버튼과 같은 텍스트 명령', documents['docs/doors-and-keys.md'])
        return result

    def _feature_documents(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        from issue50_document_contracts import PATHS
        root = Path(__file__).resolve().parents[2]
        return {name: (root / name).read_text(encoding='utf-8') for name in PATHS}

    def test_feature_document_tables_examples_policy_and_web_actions(self):
        result = self._audit_feature_documents(self._feature_documents())
        self.assertEqual(len(result['documents']), 9)
        self.assertGreater(result['examples'], 40)
        self.assertEqual(result['npc_roles'], 7)
        self.assertEqual(result['shortcut_limits'], 8)
        self.assertEqual(result['medical_rows'], 5)

    def test_feature_document_corruption_is_rejected(self):
        documents = self._feature_documents()
        cases = [
            ('docs/commands.md', '| 점수 | 상태, 상, 점 |', '| 점수 | 틀린별칭 |', 'Alias'),
            ('docs/gameplay.md', '`20 회복`', '`20 진료`', '미등록/제거'),
            ('docs/command-shortcuts.md', '| 실제 하위 실행 시도 | 10개 |', '| 실제 하위 실행 시도 | 11개 |', '한도'),
            ('docs/doors-and-keys.md', '| 열쇠 필요 | 열쇠 필요 | 잠금 불가 |', '| 열쇠 필요 | 열쇠 필요 | 열쇠 필요 |', '잠금/래치'),
            ('docs/item-entities.md', '현재 profile version은 14', '현재 profile version은 13', '버전'),
            ('docs/gameplay.md', '| 100 | 20 | 24칩 |', '| 100 | 20 | 14칩 |', '가격'),
            ('docs/gameplay.md', 'P = 2*H + (L if L < 100 else 2*L)', 'P = H + L', '공식'),
        ]
        for name, old, new, error in cases:
            with self.subTest(document=name, error=error):
                self.assertIn(old, documents[name])
                corrupted = {**documents, name: documents[name].replace(old, new)}
                with self.assertRaisesRegex(ValueError, error):
                    self._audit_feature_documents(corrupted)

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
