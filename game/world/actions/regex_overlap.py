"""등록용 정규식의 제한된 언어 교집합 검사. 일반 regex 실행 엔진은 아니다.

Python 3.13의 정규식 AST에서 literal/class/category·반복·연결·대안·group만 읽는다.
assertion/backreference/조건식/지원하지 않는 flags 및 크기 제한은 UNKNOWN이다.
fullmatch 언어를 Thompson NFA로 바꾸고 유한 product graph만 탐색한다.
"""

from collections import deque
from enum import StrEnum
from functools import lru_cache
from re import UNICODE, _parser
from re import _constants as C
from re import error as PatternError


class Relation(StrEnum):
    OVERLAP = "OVERLAP"
    DISJOINT = "DISJOINT"
    UNKNOWN = "UNKNOWN"


class Unsupported(ValueError):
    pass


MAX_CHAR = 0x10FFFF
MAX_STATES = 256
MAX_PRODUCT = 8192
MAX_REPEAT = 16


def _merge(ranges):
    result = []
    for low, high in sorted(ranges):
        if result and low <= result[-1][1] + 1:
            result[-1] = (result[-1][0], max(high, result[-1][1]))
        else:
            result.append((low, high))
    return tuple(result)


def _complement(ranges):
    result, next_char = [], 0
    for low, high in ranges:
        if next_char < low:
            result.append((next_char, low - 1))
        next_char = high + 1
    if next_char <= MAX_CHAR:
        result.append((next_char, MAX_CHAR))
    return tuple(result)


@lru_cache(maxsize=24)
def _category(category, ascii_only):
    predicates = {
        C.CATEGORY_DIGIT: str.isdecimal, C.CATEGORY_SPACE: str.isspace,
        C.CATEGORY_WORD: lambda char: char.isalnum() or char == "_",
    }
    negatives = {C.CATEGORY_NOT_DIGIT: C.CATEGORY_DIGIT,
                 C.CATEGORY_NOT_SPACE: C.CATEGORY_SPACE, C.CATEGORY_NOT_WORD: C.CATEGORY_WORD}
    if category in negatives:
        return _complement(_category(negatives[category], ascii_only))
    if category not in predicates:
        raise Unsupported("지원하지 않는 문자 category")
    result, start = [], None
    for number in range(128 if ascii_only else MAX_CHAR + 1):
        matches = predicates[category](chr(number))
        if matches and start is None:
            start = number
        elif not matches and start is not None:
            result.append((start, number - 1))
            start = None
    if start is not None:
        result.append((start, 127 if ascii_only else MAX_CHAR))
    return tuple(result)


def _intersects(a, b):
    i = j = 0
    while i < len(a) and j < len(b):
        if max(a[i][0], b[j][0]) <= min(a[i][1], b[j][1]):
            return True
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return False


def _flags(flags):
    if flags & ~int(UNICODE):
        raise Unsupported("지원하지 않는 정규식 flag")


def _characters(op, value, flags):
    if op == C.LITERAL:
        return ((value, value),)
    if op == C.NOT_LITERAL:
        return _complement(((value, value),))
    if op == C.ANY:
        return ((0, 9), (11, MAX_CHAR))
    if op == C.CATEGORY:
        return _category(value, False)
    if op != C.IN:
        raise Unsupported("지원하지 않는 문자 집합")
    negate, ranges = False, []
    for item, data in value:
        if item == C.NEGATE:
            negate = True
        elif item == C.RANGE:
            ranges.append(data)
        elif item in (C.LITERAL, C.CATEGORY):
            ranges.extend(_characters(item, data, flags))
        else:
            raise Unsupported("지원하지 않는 문자 class")
    merged = _merge(ranges)
    return _complement(merged) if negate else merged


class _NFA:
    def __init__(self):
        self.edges = []

    def state(self):
        if len(self.edges) >= MAX_STATES:
            raise Unsupported("NFA 상태 제한")
        self.edges.append([])
        return len(self.edges) - 1

    def edge(self, start, end, chars=None):
        self.edges[start].append((chars, end))

    def sequence(self, tokens, flags):
        _flags(flags)
        start = current = self.state()
        for op, value in tokens:
            end = self.state()
            if op in (C.LITERAL, C.NOT_LITERAL, C.ANY, C.CATEGORY, C.IN):
                self.edge(current, end, _characters(op, value, flags))
            elif op == C.SUBPATTERN:
                _, add, remove, children = value
                child_start, child_end = self.sequence(children, (flags | add) & ~remove)
                self.edge(current, child_start)
                self.edge(child_end, end)
            elif op == C.BRANCH:
                for children in value[1]:
                    child_start, child_end = self.sequence(children, flags)
                    self.edge(current, child_start)
                    self.edge(child_end, end)
            elif op in (C.MAX_REPEAT, C.MIN_REPEAT):
                minimum, maximum, children = value
                if minimum > MAX_REPEAT or maximum != C.MAXREPEAT and maximum > MAX_REPEAT:
                    raise Unsupported("반복 전개 제한")
                repeat = current
                for _ in range(minimum):
                    child_start, child_end = self.sequence(children, flags)
                    self.edge(repeat, child_start)
                    repeat = child_end
                self.edge(repeat, end)
                if maximum == C.MAXREPEAT:
                    child_start, child_end = self.sequence(children, flags)
                    self.edge(repeat, child_start)
                    self.edge(child_end, repeat)
                else:
                    for _ in range(maximum - minimum):
                        child_start, child_end = self.sequence(children, flags)
                        self.edge(repeat, child_start)
                        repeat = child_end
                        self.edge(repeat, end)
            else:
                raise Unsupported("지원 subset 밖 정규식 연산")
            current = end
        return start, current


def _tree(pattern):
    tree = _parser.parse(pattern, 0)
    _flags(tree.state.flags)
    return tree, list(tree)


@lru_cache(maxsize=256)
def compare_patterns(left, right):
    """지원 subset의 정확한 교집합. 알 수 없는 문법을 비중첩으로 취급하지 않는다."""
    try:
        if type(left) is not str or type(right) is not str:
            return Relation.UNKNOWN
        a_tree, a_tokens = _tree(left)
        b_tree, b_tokens = _tree(right)
        a, b = _NFA(), _NFA()
        a_start, a_end = a.sequence(a_tokens, a_tree.state.flags)
        b_start, b_end = b.sequence(b_tokens, b_tree.state.flags)
        pending, visited = deque(((a_start, b_start),)), set()
        while pending:
            x, y = pending.popleft()
            if (x, y) in visited:
                continue
            visited.add((x, y))
            if len(visited) > MAX_PRODUCT:
                return Relation.UNKNOWN
            if x == a_end and y == b_end:
                return Relation.OVERLAP
            for chars, target in a.edges[x]:
                if chars is None:
                    pending.append((target, y))
            for chars, target in b.edges[y]:
                if chars is None:
                    pending.append((x, target))
            for ca, ta in a.edges[x]:
                if ca is not None:
                    for cb, tb in b.edges[y]:
                        if cb is not None and _intersects(ca, cb):
                            pending.append((ta, tb))
        return Relation.DISJOINT
    except (Unsupported, PatternError, ValueError, OverflowError, RecursionError):
        return Relation.UNKNOWN


def _whole_provider(tokens, group):
    if len(tokens) != 1 or tokens[0][0] != C.SUBPATTERN:
        return False
    identity, add, remove, body = tokens[0][1]
    if identity != group or add or remove or len(body) != 1:
        return False
    op, repeat = body[0]
    return (op in (C.MAX_REPEAT, C.MIN_REPEAT) and repeat[0] in (0, 1)
            and repeat[1] == C.MAXREPEAT and list(repeat[2]) == [(C.ANY, None)])


def explicit_argument_extension(base, extended, argument_name):
    """전체 Provider 입력과 필수 Argument 확장이라는 좁은 구조만 증명한다.

언어 비중첩 증명이 아니다. 두 의미 해석이 모두 유효하면 Dispatcher가 거절해야 한다.
"""
    try:
        a, a_tokens = _tree(base)
        b, b_tokens = _tree(extended)
        if a.state.flags != b.state.flags or set(a.state.groupdict) != {"provider"} or set(b.state.groupdict) != {"provider", argument_name}:
            return False
        if not _whole_provider(a_tokens, a.state.groupdict["provider"]) or len(b_tokens) < 3:
            return False
        if not _whole_provider(b_tokens[:1], b.state.groupdict["provider"]):
            return False
        if not all(op == C.LITERAL and chr(value).isspace() for op, value in b_tokens[1:-1]):
            return False
        op, data = b_tokens[-1]
        if op != C.SUBPATTERN or data[0] != b.state.groupdict[argument_name] or data[1] or data[2]:
            return False
        machine = _NFA()
        start, end = machine.sequence(data[3], b.state.flags)
        # 명시 인자는 반드시 소비되어야 한다. optional/빈 capture는 계약 구분이 아니다.
        pending, visited = [start], set()
        while pending:
            state = pending.pop()
            if state in visited:
                continue
            visited.add(state)
            if state == end:
                return False
            pending.extend(target for chars, target in machine.edges[state] if chars is None)
        return True
    except (Unsupported, PatternError, ValueError, OverflowError, RecursionError):
        return False
