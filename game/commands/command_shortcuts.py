"""개인 설정과 서버 dispatcher를 연결한다. gameplay 규칙을 직접 실행하지 않는다."""

from inspect import iscoroutinefunction, isgeneratorfunction
from time import monotonic

from evennia import Command
from twisted.internet.defer import inlineCallbacks
from world import rules
from world import text as ft

from commands.base import GameCommand
from commands.shortcuts import (
    delete_all_request,
    expand_shortcuts,
    parse_sequence,
    parse_shortcut_definition,
    shortcut_name,
    validate_delete_all,
    validate_shortcut_graph,
)


def reserved_names(cmdset):
    """잠긴 실제 명령도 예약한다. 다른 층/장소의 정적 이동 명령도 등록을 막는다."""
    from django.conf import settings
    from world.content import DIRECTION_ALIASES, ROOMS

    from commands.aliases import SHORTCUTS
    from commands.default_cmdsets import UnloggedinCmdSet
    from commands.elevator import ElevatorInsideCmdSet, ElevatorLandingCmdSet
    from commands.registry import COMMANDS

    names = set(SHORTCUTS)
    for commands in (cmdset, UnloggedinCmdSet(), ElevatorInsideCmdSet(), ElevatorLandingCmdSet()):
        names.update(commands.get_all_cmd_keys_and_aliases())
    for cls in COMMANDS:
        names.update((cls.key, *cls.aliases))
    names.update(DIRECTION_ALIASES)
    names.update(DIRECTION_ALIASES.values())
    for room in ROOMS.values():
        names.update(room["exits"])
        names.update(room.get("blocked_exits", {}))
    return {normalized for name in names
            for normalized in (name.casefold(), name.casefold().lstrip(settings.CMD_IGNORE_PREFIXES))}


class Sequence(Command):
    key = "해"
    input_style = "target"
    help_category = "원시구역"
    category = "조작"
    usage = "상태, 장비, 가방 해"
    summary = "두 명령 이상을 순서대로 실행합니다. 개별 명령 실패 뒤에도 계속하며 묶음은 transaction이 아닙니다."

    def commands_to_expand(self):
        return parse_sequence(self.args)

    def func(self):
        self.flat_commands = []
        try:
            if getattr(self, "primal_sequence_leaf", False):
                raise rules.RuleError("묶음 실행 중 새로 생긴 줄임말·묶음은 다시 확장하지 않습니다.")
            commands = expand_shortcuts(
                self.commands_to_expand(),
                self.caller.profile_snapshot().get("command_shortcuts", {}),
                reserved_names(self.cmdset),
            )
            from server.conf.cmdparser import cmdparser

            for command in commands:
                for match in cmdparser(command, self.cmdset, self.caller, session=self.session):
                    # 6.1의 progressive func는 dispatcher Deferred보다 늦게 끝난다.
                    if isgeneratorfunction(match[2].func) or iscoroutinefunction(match[2].func):
                        raise rules.RuleError("추가 입력·대기를 사용하는 엔진 명령은 묶음 밖에서 실행하세요.")
            self.flat_commands = commands
        except rules.RuleError as error:
            self.caller.msg(ft.text(ft.token("error", str(error)), kind="error"))

    @inlineCallbacks
    def at_post_cmd(self):
        # Evennia 6.1은 일반 func의 Deferred 반환은 기다리지 않지만 이 hook은 yield한다.
        for command in self.flat_commands:
            yield self.caller.execute_cmd(command, session=self.session, primal_sequence_leaf=True)


class PersonalShortcut(Sequence):
    """정상 match가 없는 exact input에만 parser가 제공하는 내부 명령."""

    key = "__personal_shortcut"

    def commands_to_expand(self):
        return [self.args]


class Shortcuts(GameCommand):
    key = "줄임말"
    input_style = "prefix"
    category = "조작"
    usage = (
        "줄임말 · 줄임말 추가 이름 정의 · 줄임말 삭제 이름 · "
        "줄임말 모두 삭제 · 줄임말 모두 삭제 확인"
    )
    summary = "캐릭터 개인 줄임말을 관리합니다. 전체 삭제 요청과 확인은 각각 직접 입력하며, 60초 안에 확인해야 합니다. 목록 변경 시 요청이 취소됩니다."

    def run(self):
        args = self.args.strip()
        # 금지된 간접 실행은 요청 생성·기존 요청 소비 전에 거절한다.
        if args in ("모두 삭제", "모두 삭제 확인") and getattr(self, "primal_sequence_leaf", False):
            raise rules.RuleError("전체 삭제 요청과 확인은 각각 직접 입력하세요. 묶음·줄임말로 실행할 수 없습니다.")
        shortcuts = self.caller.profile_snapshot().get("command_shortcuts", {})
        if not args:
            entries = [f"{name} = {', '.join(commands) + ' 해' if len(commands) > 1 else commands[0]}"
                       for name, commands in sorted(shortcuts.items())]
            self.caller.msg(ft.sheet("개인 줄임말", *(entries or ["등록된 개인 줄임말이 없습니다."])))
            return
        if args == "모두 삭제":
            self.caller.ndb.shortcut_delete_all_request = delete_all_request(shortcuts, monotonic())
            if not shortcuts:
                self.caller.msg("삭제할 개인 줄임말이 없습니다.")
                return
            self.caller.msg(f"개인 줄임말 {len(shortcuts)}개를 모두 삭제합니다. "
                            "계속하려면 '줄임말 모두 삭제 확인'을 입력하세요.")
            return
        if args == "모두 삭제 확인":
            request = self.caller.ndb.shortcut_delete_all_request
            self.caller.ndb.shortcut_delete_all_request = None  # 성공/실패 모두 one-shot

            def clear(profile):
                current = profile["command_shortcuts"]
                validate_delete_all(request, current, monotonic())
                count = len(current)
                profile["command_shortcuts"] = {}
                return count

            count = self.caller.change(clear)
            self.caller.msg(f"개인 줄임말 {count}개를 모두 삭제했습니다.")
            return
        parts = args.split(None, 1)
        operation, rest = parts[0], parts[1] if len(parts) > 1 else ""
        if operation == "추가":
            parts = rest.split(None, 1)
            if len(parts) != 2:
                raise rules.RuleError("줄임말 추가 이름 정의")
            name = shortcut_name(parts[0])
            reserved = reserved_names(self.cmdset)
            if name in reserved:
                raise rules.RuleError("기존 명령·별칭·시스템 단축어는 줄임말 이름으로 사용할 수 없습니다.")
            definition = parse_shortcut_definition(parts[1])

            def register(profile):
                current = profile["command_shortcuts"]
                replacement = name in current
                prospective = {**current, name: definition}
                validate_shortcut_graph(prospective, reserved)
                profile["command_shortcuts"] = prospective
                return replacement

            replaced = self.caller.change(register)
            self.caller.ndb.shortcut_delete_all_request = None
            self.caller.msg("줄임말을 변경했습니다." if replaced else "줄임말을 추가했습니다.")
            return
        if operation == "삭제":
            name = shortcut_name(rest.strip())

            def remove(profile):
                if name not in profile["command_shortcuts"]:
                    raise rules.RuleError("등록된 개인 줄임말을 찾을 수 없습니다.")
                del profile["command_shortcuts"][name]

            self.caller.change(remove)
            self.caller.ndb.shortcut_delete_all_request = None
            self.caller.msg("줄임말을 삭제했습니다.")
            return
        raise rules.RuleError(self.usage)
