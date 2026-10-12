"""지정된 현행 표/예시만 검사한다. 역사적 서술 전체를 자동 PASS 처리하지 않는다."""

import ast
import re

PATHS = ('docs/commands.md', 'docs/gameplay.md', 'docs/command-shortcuts.md',
         'docs/npc-dialogue.md', 'docs/party-and-tactics.md', 'docs/doors-and-keys.md',
         'docs/item-entities.md', 'docs/equipment.md', 'docs/lighting-firearms.md')


def tables(document):
    header = None
    for line in document.splitlines():
        if not line.startswith('|'):
            header = None
            continue
        row = [cell.strip() for cell in line.strip('|').split('|')]
        if header is None:
            header = row
        elif not all(re.fullmatch(r'[-: ]+', cell) for cell in row):
            yield header, row


def number(text):
    values = re.findall(r'\d[\d,]*', text)
    if not values:
        raise ValueError('문서 수치 누락')
    return int(values[-1].replace(',', ''))


def verify(documents, metadata, limits, door_seconds, profile_version, npc_roles, example, medical):
    checked, examples = set(), []
    for header, row in tables(documents['docs/commands.md']):
        if not header or header[0] != '정식 명령':
            continue
        key, text = row[:2]
        key, text = key.strip('`'), text.strip('`')
        if key not in metadata:
            raise ValueError('현행 문서의 제거/미등록 명령')
        aliases = set() if text == '없음' else {s.strip().strip('`') for s in text.replace('ASCII 0x60 백틱', 'BACKTICK').split(',')}
        aliases = {'`' if v == 'BACKTICK' else v for v in aliases}
        if key == '말':
            aliases = {'say'} if text == "say`, 앞의 작은따옴표 `'" else aliases
        if aliases != set(metadata[key]):
            raise ValueError('문서 Alias 불일치')
        checked.add(key)
    if len({key for key in checked if key.startswith('일행')}) != 16:
        raise ValueError('문서 일행 16명령 불일치')
    shortcut = documents['docs/command-shortcuts.md']
    found = {row[0]: number(row[1]) for header, row in tables(shortcut) if header == ['한도', '값']}
    if found != limits:
        raise ValueError('문서 개인 줄임말 한도 불일치')
    door = documents['docs/doors-and-keys.md']
    seconds = re.findall(r'열기 성공 시각부터 (\d+)초 뒤', door)
    if seconds != [str(door_seconds)]:
        raise ValueError('문서 Door 만료 불일치')
    permission_rows = [row for header, row in tables(door) if header == ['조작', '관리실 외부', '관리실 내부', '회복실 양쪽']]
    if permission_rows != [
        ['닫힌 문 열기 / 열린 문 닫기', '열쇠 불필요', '열쇠 불필요', '열쇠 불필요'],
        ['닫힌 문 잠그기', '열쇠 필요', '열쇠 필요', '잠금 불가'],
        ['잠긴 문 풀기', '열쇠 필요', '열쇠 없이 래치 허용', '잠금 불가']]:
        raise ValueError('문서 Door 잠금/래치 정책 불일치')
    for name in ('docs/item-entities.md', 'docs/equipment.md'):
        if re.findall(r'현재 profile version은 (\d+)', documents[name]) != [str(profile_version)]:
            raise ValueError('문서 현행 Profile 버전 불일치')
    npc = documents['docs/npc-dialogue.md']
    roles = {row[0]: number(row[1]) for header, row in tables(npc) if header[:2] == ['역할', '수']}
    if roles != npc_roles:
        raise ValueError('문서 NPC 역할/개수 불일치')
    medical_rows = [row for header, row in tables(documents['docs/gameplay.md']) if header == ['레벨', '실제 회복 HP', '비용']]
    for pattern, expected in [(r'`P = ([^`]+)`', '2*H + (L if L < 100 else 2*L)'),
                              (r'비용은 `([^`]+)`칩', 'max(1, ceil(P/10))')]:
        expressions = re.findall(pattern, documents['docs/gameplay.md'])
        if len(expressions) != 1 or ast.dump(ast.parse(expressions[0], mode='eval')) != ast.dump(ast.parse(expected, mode='eval')):
            raise ValueError('문서 의료 공식 불일치')
    if not medical_rows:
        raise ValueError('문서 의료 경계 표 누락')
    for row in medical_rows:
        level, hp, cost = map(number, row)
        if medical(level, hp) != cost:
            raise ValueError('문서 의료 가격 불일치')
    # 표의 입력 열과 지정된 현행 코드 블록. 마이그레이션/오류/과거 사례 제외.
    for name in ('docs/gameplay.md', 'docs/command-shortcuts.md'):
        for header, row in tables(documents[name]):
            if len(header) > 1 and header[0] in ('기능', '원하는 행동', '목적', '조작') and header[1] in ('입력', '입력 예시'):
                examples.extend(re.findall(r'`([^`]+)`', row[1]))
            if name == 'docs/gameplay.md' and header[0] in ('회복 수단', '기술·행동'):
                examples.extend(re.findall(r'`([^`]+)`', row[0]))
    for name in ('docs/command-shortcuts.md', 'docs/doors-and-keys.md', 'docs/lighting-firearms.md'):
        section = documents[name].split('## 명령과 재장전', 1)[1] if name == 'docs/lighting-firearms.md' else documents[name]
        block = re.search(r'```text\n(.*?)\n```', section, flags=re.S)
        if not block:
            raise ValueError('문서 현행 예시 블록 누락')
        examples.extend(block[1].splitlines())
    # 정의를 먼저 제공해 문서의 개인 호출도 실제 select_command 경로로 판정한다.
    definitions = {}
    for text in examples:
        parts = text.split(None, 1)
        if len(parts) == 2 and parts[1].endswith(' 줄임말') and parts[1].removesuffix(' 줄임말'):
            definitions[parts[0]] = parts[1].removesuffix(' 줄임말')
    for text in examples:
        example(text, definitions)
    return {'documents': list(PATHS), 'command_tables': len(checked), 'examples': len(examples),
            'shortcut_limits': len(found), 'npc_roles': len(roles), 'medical_rows': len(medical_rows)}
