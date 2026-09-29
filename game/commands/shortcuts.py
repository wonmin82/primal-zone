"""개인 줄임말과 묶음의 순수 문법·확장·전체 삭제 확인 계약."""

import hashlib
import json
import re

from world.rules import RuleError

MAX_COMMANDS = 10
MAX_DEPTH = 5
MAX_EXPANDED_CHARACTERS = 1000
MAX_NAME_CHARACTERS = 20
DELETE_ALL_CONFIRM_TTL_SECONDS = 60


def shortcut_name(value):
    if not re.fullmatch(r"[가-힣ㄱ-ㅎㅏ-ㅣ\u1100-\u11ffA-Za-z0-9_]" + rf"{{1,{MAX_NAME_CHARACTERS}}}", value):
        raise RuleError(f"줄임말 이름은 한글·자모·영문·숫자·밑줄 1~{MAX_NAME_CHARACTERS}자로 입력하세요.")
    return value.casefold()


def parse_sequence(arguments):
    commands = [part.strip() for part in arguments.split(",")]
    if len(commands) < 2 or any(not command for command in commands):
        raise RuleError("묶음은 빈 항목 없이 두 명령 이상 입력하세요: 상태, 장비 해")
    return commands


def parse_shortcut_definition(definition):
    text = definition.strip()
    if not text:
        raise RuleError("줄임말에 저장할 명령을 입력하세요.")
    parts = text.rsplit(None, 1)
    if not text.startswith("'") and parts[-1] == "해":
        return parse_sequence(parts[0] if len(parts) == 2 else "")
    return [text]


def expand_shortcuts(commands, shortcuts, reserved=()):
    """전체 요청을 먼저 flatten한다. 실제 명령의 이름은 개인 정의로 치환하지 않는다."""
    flat = []
    size = 0
    reserved = {name.casefold() for name in reserved}

    def visit(command, path):
        nonlocal size
        if not isinstance(command, str) or not command.strip():
            raise RuleError("줄임말 정의에 빈 명령이나 잘못된 값이 있습니다.")
        command = command.strip()
        name = command.casefold()
        if name in shortcuts and name not in reserved:
            if name in path:
                raise RuleError("줄임말의 순환 참조는 사용할 수 없습니다.")
            if len(path) >= MAX_DEPTH:
                raise RuleError(f"줄임말 중첩은 {MAX_DEPTH}단계까지 가능합니다.")
            definition = shortcuts[name]
            if not isinstance(definition, list) or not definition:
                raise RuleError("줄임말 정의는 비어 있지 않은 명령 목록이어야 합니다.")
            for child in definition:
                visit(child, (*path, name))
            return
        nested = parse_shortcut_definition(command)
        if nested != [command]:
            for child in nested:
                visit(child, path)
            return
        flat.append(command)
        size += len(command)
        if len(flat) > MAX_COMMANDS:
            raise RuleError(f"한 번에 실행할 명령은 {MAX_COMMANDS}개까지 가능합니다.")
        if size > MAX_EXPANDED_CHARACTERS:
            raise RuleError(f"확장된 명령은 합계 {MAX_EXPANDED_CHARACTERS}자까지 가능합니다.")

    if not isinstance(commands, list) or not commands:
        raise RuleError("실행할 명령 목록이 비어 있습니다.")
    for command in commands:
        visit(command, ())
    return flat


def validate_shortcut_graph(shortcuts, reserved=()):
    for name in shortcuts:
        shortcut_name(name)
        expand_shortcuts([name], shortcuts, reserved)


def shortcut_fingerprint(shortcuts):
    data = json.dumps(shortcuts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def delete_all_request(shortcuts, now):
    return {"requested_at": now, "fingerprint": shortcut_fingerprint(shortcuts)} if shortcuts else None


def validate_delete_all(request, shortcuts, now):
    if not request:
        raise RuleError("먼저 '줄임말 모두 삭제'를 입력해 삭제를 요청하세요.")
    if not 0 <= now - request["requested_at"] < DELETE_ALL_CONFIRM_TTL_SECONDS:
        raise RuleError("전체 삭제 요청이 만료되었습니다. 다시 '줄임말 모두 삭제'를 입력하세요.")
    if request["fingerprint"] != shortcut_fingerprint(shortcuts):
        raise RuleError("삭제 요청 후 줄임말 목록이 변경되었습니다. 다시 '줄임말 모두 삭제'를 입력하세요.")
