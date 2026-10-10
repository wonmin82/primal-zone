"""DB·CmdSet과 독립적인 정의 문법, 한 번의 치환, 저장 영역과 삭제 확인 계약."""

import hashlib
import json
import math
import re
from dataclasses import dataclass

from world.rules import RuleError

MAX_COMMANDS = 10
MAX_DEPTH = 5
MAX_EXPANDED_CHARACTERS = 1000
MAX_NAME_CHARACTERS = 20
MAX_SHORTCUTS = 100
MAX_DEFINITION_CHARACTERS = 2000
MAX_ARGUMENT_CHARACTERS = 2000
# 중간 개인 호출은 2,000자 인자 + 20자 이름 + 구분 공백까지 허용한다.
# 최종 명령 누적 1,000자 한도와 별개이며 파서에도 이보다 큰 치환값을 전달하지 않는다.
MAX_INTERMEDIATE_CHARACTERS = MAX_ARGUMENT_CHARACTERS + MAX_NAME_CHARACTERS + 1
DELETE_ALL_CONFIRM_TTL_SECONDS = 60
_NAME = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ\u1100-\u11ff\ua960-\ua97f\ud7b0-\ud7ffA-Za-z0-9_]{1,20}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def shortcut_name(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise RuleError("줄임말 이름은 한글·자모·영문·숫자·밑줄 1~20자로 입력하세요.")
    return value.casefold()


def _input(value, maximum):
    if not isinstance(value, str) or _CONTROL.search(value):
        raise RuleError("줄임말 입력에 개행·제어문자를 사용할 수 없습니다.")
    if len(value) > maximum:
        raise RuleError(f"줄임말 입력은 {maximum:,}자까지 가능합니다.")
    return value.strip()


def parse_sequence(arguments):
    arguments = _input(arguments, MAX_DEFINITION_CHARACTERS)
    commands = [part.strip() for part in arguments.split(",")]
    if len(commands) < 2 or any(not part for part in commands):
        raise RuleError("두 명령 이상을 콤마로 구분하세요: 상태, 장비 해")
    return commands


def parse_shortcut_definition(definition):
    text = _input(definition, MAX_DEFINITION_CHARACTERS)
    if not text:
        raise RuleError("줄임말에 저장할 명령을 입력하세요.")
    parts = text.rsplit(None, 1)
    if not text.startswith("'") and parts[-1] == "해":
        return parse_sequence(parts[0] if len(parts) == 2 else "")
    return [text]


@dataclass(frozen=True)
class Variable:
    key: str


@dataclass(frozen=True)
class BoundSegment:
    tokens: tuple[str | Variable, ...]
    values: tuple[str, ...]

    def pieces(self):
        for token in self.tokens:
            yield self.values[0 if token.key == "*" else int(token.key)] if isinstance(token, Variable) else token

    def render(self, maximum=MAX_INTERMEDIATE_CHARACTERS):
        # 반복 문자열을 만들지 않고 길이만 합산한다. join 이전·축적 중 모두 검사한다.
        expected = sum(len(piece) for piece in self.pieces())
        if expected > maximum:
            raise RuleError("줄임말 치환 문자열이 허용 크기를 초과했습니다. 남은 실행을 중단합니다.")
        parts, size = [], 0
        for piece in self.pieces():
            size += len(piece)
            if size > maximum:
                raise RuleError("줄임말 치환 문자열이 허용 크기를 초과했습니다.")
            parts.append(piece)
        return "".join(parts).strip()


@dataclass(frozen=True)
class Definition:
    segments: tuple[tuple[str | Variable, ...], ...]
    positions: frozenset[int]
    all_arguments: bool

    def bind_segments(self, arguments):
        text = _input(arguments, MAX_ARGUMENT_CHARACTERS)
        args = text.split()
        required = max(self.positions, default=0)
        if len(args) < required or (self.all_arguments and not args):
            raise RuleError("줄임말 호출 인자가 부족합니다.")
        if not self.all_arguments and len(args) > required:
            raise RuleError("줄임말에서 사용하지 않는 추가 인자가 있습니다.")
        values = (" ".join(args), *args[:9])
        # 사용자 인자는 토큰으로 다시 분석하지 않는다. 경계도 다시 분할하지 않는다.
        return tuple(BoundSegment(segment, values) for segment in self.segments)

    def bind(self, arguments):
        return tuple(segment.render() for segment in self.bind_segments(arguments))


def parse_definition(definition):
    if isinstance(definition, dict) and "원본" in definition and "문제" in definition:
        raise RuleError("비활성 개인 줄임말입니다: " + str(definition["문제"]) + " 원본을 확인한 뒤 현재 명령으로 재등록하세요.")
    segments, positions, all_arguments = [], set(), False
    for command in parse_shortcut_definition(definition):
        tokens, literal, index = [], [], 0
        while index < len(command):
            char = command[index]
            if char != "$":
                literal.append(char)
                index += 1
                continue
            if index + 1 < len(command) and command[index + 1] == "$":
                literal.append("$")
                index += 2
                continue
            token = re.match(r"\$(\*|[0-9]+|[A-Za-z_]+)?", command[index:])[0]
            key = token[1:]
            if key not in ("*", *map(str, range(1, 10))):
                raise RuleError("변수는 $1~$9, $*, $$만 사용할 수 있습니다.")
            if literal:
                tokens.append("".join(literal))
                literal = []
            tokens.append(Variable(key))
            all_arguments |= key == "*"
            if key != "*":
                positions.add(int(key))
            index += len(token)
        if literal:
            tokens.append("".join(literal))
        segments.append(tuple(tokens))
    if positions and not all_arguments and positions != set(range(1, max(positions) + 1)):
        raise RuleError("위치 변수는 $1부터 순서대로 빠짐없이 사용하세요.")
    return Definition(tuple(segments), frozenset(positions), all_arguments)


def safe_legacy_definition(values):
    """원래 경계·순서가 순수 파서로 그대로 재현되는 리스트만 문자열로 옮긴다."""
    if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
        return None
    candidate = values[0] if len(values) == 1 else ", ".join(values) + " 해"
    try:
        if parse_shortcut_definition(candidate) != values:
            return None
        parse_definition(candidate)
    except RuleError:
        return None
    return candidate


def normalized_keys(shortcuts, name):
    return tuple(key for key in shortcuts if isinstance(key, str) and key.casefold() == name)


def stored_key(shortcuts, name):
    keys = normalized_keys(shortcuts, name)
    if len(keys) > 1:
        raise RuleError("정규화 이름 충돌입니다. 전체 삭제 또는 관리자 복구가 필요합니다.")
    return keys[0] if keys else None


def require_shortcut_store(shortcuts):
    def compatible(value):
        if isinstance(value, float):
            return math.isfinite(value)
        if value is None or isinstance(value, (str, bool, int)):
            return True
        if isinstance(value, list):
            return all(compatible(item) for item in value)
        if isinstance(value, dict):
            return all(isinstance(key, str) and compatible(item) for key, item in value.items())
        return False

    try:
        if not isinstance(shortcuts, dict) or not compatible(shortcuts):
            raise ValueError("unsupported shortcut store")
    except (ValueError, TypeError, RecursionError) as error:
        raise RuleError("개인 줄임말 저장 영역 오류입니다. 관리자 확인이 필요합니다.") from error
    return shortcuts


def shortcut_fingerprint(shortcuts):
    require_shortcut_store(shortcuts)
    data = json.dumps(shortcuts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def delete_all_request(shortcuts, now):
    fingerprint = shortcut_fingerprint(shortcuts)
    return {"requested_at": now, "fingerprint": fingerprint} if shortcuts else None


def validate_delete_all(request, shortcuts, now):
    if not request:
        raise RuleError("먼저 '모두 삭제 줄임말'을 입력해 삭제를 요청하세요.")
    if not 0 <= now - request["requested_at"] < DELETE_ALL_CONFIRM_TTL_SECONDS:
        raise RuleError("전체 삭제 요청이 만료되었습니다. 다시 '모두 삭제 줄임말'을 입력하세요.")
    if request["fingerprint"] != shortcut_fingerprint(shortcuts):
        raise RuleError("삭제 요청 후 줄임말 목록이 변경되었습니다. 다시 '모두 삭제 줄임말'을 입력하세요.")
