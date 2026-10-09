"""선택된 경로만 처리하는 캐릭터별 순차 실행기. 계획·컨텍스트는 영속 저장하지 않는다."""

from collections import deque
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from inspect import iscoroutinefunction, isgeneratorfunction, unwrap
from threading import RLock
from types import CoroutineType, GeneratorType

from evennia import Command
from twisted.internet.defer import Deferred, inlineCallbacks
from world import rules
from world import text as ft

from commands.shortcuts import (
    MAX_COMMANDS,
    MAX_DEPTH,
    MAX_EXPANDED_CHARACTERS,
    BoundSegment,
    parse_definition,
    require_shortcut_store,
    shortcut_name,
    stored_key,
)

_START_LOCK = RLock()
_DISPATCH_ORIGIN = ContextVar("shortcut_dispatch_origin", default=None)


@dataclass(frozen=True)
class QueueItem:
    command: str | BoundSegment
    shortcut_path: tuple[str, ...] = ()
    global_expanded: bool = False


@dataclass(frozen=True)
class Invocation:
    # 사용자 문자열/kwargs 플래그가 아닌 실행기 객체의 소유권으로 간접 입력을 증명한다.
    execution: object = None

    @property
    def direct(self):
        return self.execution is None

    def allows_prompt(self):
        return self.direct or (not self.execution.cancelled and self.execution.owns_session())


def dispatch_origin():
    return _DISPATCH_ORIGIN.get() or Invocation()


class ShortcutError(Command):
    key = "__shortcut_error"
    read_only = True

    def __init__(self, message):
        super().__init__()
        self.error_message = message

    def func(self):
        self.caller.msg(ft.text(ft.token("error", self.error_message), kind="error"))


def stop_execution(caller, session=None):
    execution = caller.ndb.shortcut_execution
    if isinstance(execution, Execution) and (session is None or session is execution.session):
        execution.stop()


def require_completed_command(command, caller, session, *, multimatch=False):
    """6.1은 func의 Deferred를 await하지 않는다. pre/post Deferred만 완료 계약이 있다."""
    from evennia.commands.default.help import CmdHelp

    if getattr(command, "shortcut_completion_guaranteed", True) is False:
        raise rules.RuleError("추가 입력·완료를 보장하지 않는 명령은 묶음·줄임말 밖에서 실행하세요.")
    if multimatch:
        from evennia.commands.default import syscommands
        from evennia.utils import utils

        # 기본 핸들러는 후보를 보여주기만 한다. 후보 존재 자체로 Sequence를 실행하지 않는다.
        # 임의 선택/추가 입력 핸들러는 새 Command의 최종 선택을 보장할 수 없으므로 실행 전 거절한다.
        function = unwrap(command.func)
        if (getattr(function, "__func__", function) is not syscommands.SystemMultimatch.func
                or syscommands.at_search_result is not utils.at_search_result):
            raise rules.RuleError("추가 선택·완료를 보장하지 않는 다중 명령 처리는 직접 실행하세요.")
    if isinstance(command, CmdHelp) and type(command).help_more:
        options = caller.account.db._saved_webclient_options if caller.account else None
        popup = (session and session.protocol_key in ("webclient/websocket", "webclient/ajax")
                 and isinstance(options, dict) and options.get("helppopup"))
        if not popup:
            raise rules.RuleError("페이지 입력을 받을 수 있는 엔진 도움말은 직접 실행하세요.")
    function = unwrap(command.func)
    code = getattr(function, "__code__", None)
    unsafe_names = {"get_input", "ask_yes_no", "evmore", "EvMore", "EvEditor", "EvMenu",
                    "deferLater", "callLater", "ensureDeferred", "puppet_object", "execute_cmd", "cmdhandler",
                    "batch_cmd_exec", "batch_code_exec"}
    if (isgeneratorfunction(function) or iscoroutinefunction(function)
            or (code and unsafe_names.intersection(code.co_names))):
        raise rules.RuleError("추가 입력·완료를 보장하지 않는 명령은 묶음·줄임말 밖에서 실행하세요.")
    # 직접 Deferred를 반환하는 사용자 정의 동기 함수도 실행 전에 감지한다.
    # pre/post hook은 이 검사에 포함하지 않으며 엔진이 실제 완료를 기다린다.
    if code:
        from inspect import getclosurevars

        closure = getclosurevars(function)
        if "Deferred" in code.co_names or any(
                isinstance(value, (Deferred, GeneratorType, CoroutineType))
                or isgeneratorfunction(value) or iscoroutinefunction(value)
                for value in (*closure.nonlocals.values(), *closure.globals.values())):
            raise rules.RuleError("func의 비동기 완료를 보장하지 않는 명령은 직접 실행하세요.")
    from commands.prompt import PromptLifecycle

    for name in ("at_pre_cmd", "parse", "at_post_cmd"):
        hook = command.original_hook(name) if isinstance(command, PromptLifecycle) else getattr(command, name)
        if isgeneratorfunction(hook) or iscoroutinefunction(hook):
            raise rules.RuleError("완료를 보장하지 않는 generator/coroutine hook은 직접 실행하세요.")


class Execution:
    ACTIVE, STOPPING, FINISHED = "ACTIVE", "STOPPING", "FINISHED"

    def __init__(self, caller, session, items):
        self.caller, self.session = caller, session
        self.account = caller.account
        self.queue = deque(items)
        self.shortcuts = deepcopy(caller.profile_snapshot().get("command_shortcuts", {}))
        self.state = self.ACTIVE
        self.cancelled = False
        self.attempts = self.characters = 0
        self.outputs = []

    @classmethod
    def start(cls, caller, session, items):
        # 검사와 활성화 사이에는 Deferred/yield가 없다. 같은 캐릭터의 다른 세션도 공유한다.
        with _START_LOCK:
            active = caller.ndb.shortcut_execution
            if isinstance(active, cls) and active.state != cls.FINISHED:
                raise rules.RuleError("이미 이 캐릭터에서 묶음·줄임말을 실행 중입니다.")
            execution = cls(caller, session, items)
            if not execution.owns_session():
                raise rules.RuleError("실행 세션의 캐릭터 제어권을 확인할 수 없습니다.")
            caller.ndb.shortcut_execution = execution
            return execution

    def owns_session(self):
        if self.caller.account is not self.account:
            return False
        if self.session is None:
            return True  # 세션 없는 서버 내부 호출도 캐릭터/컨텍스트 소유권을 유지한다.
        from evennia import SESSION_HANDLER

        return (SESSION_HANDLER.get(self.session.sessid) is self.session
                and self.session.puppet is self.caller
                and self.session.account is self.account)

    def valid(self):
        return (self.state == self.ACTIVE and self.caller.ndb.shortcut_execution is self
                and self.owns_session())

    def stop(self):
        if self.state == self.FINISHED:
            return
        self.state = self.STOPPING
        self.cancelled = True
        self.queue.clear()
        # 비동기 callback 전에도 출력 깊이/다른 세션의 정상 입력을 해제한다.
        for command in tuple(self.outputs):
            command.finish_prompt()
        self.finish()

    def finish(self):
        self.state = self.FINISHED
        self.queue.clear()
        with _START_LOCK:
            if self.caller.ndb.shortcut_execution is self:
                self.caller.ndb.shortcut_execution = None

    def expand_personal(self, name, arguments, item):
        require_shortcut_store(self.shortcuts)
        shortcut_name(name)
        key = stored_key(self.shortcuts, name)
        definition = self.shortcuts[key]
        if not isinstance(definition, str):
            raise rules.RuleError("비활성 구형 줄임말입니다. 유효한 정의로 재등록하세요.")
        if name in item.shortcut_path:
            raise rules.RuleError("줄임말의 순환 참조입니다. 남은 실행을 중단합니다.")
        if len(item.shortcut_path) >= MAX_DEPTH:
            raise rules.RuleError("줄임말 중첩은 5단계까지 가능합니다.")
        commands = parse_definition(definition).bind_segments(arguments)
        path = (*item.shortcut_path, name)
        self.queue.extendleft(reversed(tuple(QueueItem(text, path) for text in commands)))

    @inlineCallbacks
    def run(self):
        from evennia.commands.cmdhandler import (
            CMD_MULTIMATCH,
            CMD_NOMATCH,
            cmdhandler,
            generate_cmdset_providers,
            get_and_merge_cmdsets,
        )
        from server.conf.cmdparser import select_command

        from commands.command_shortcuts import GlobalShortcut, PersonalShortcut, Sequence
        from commands.prompt import with_prompt

        try:
            while self.queue and self.valid():
                item = self.queue.popleft()
                text = item.command.render() if isinstance(item.command, BoundSegment) else item.command
                _, providers, _, caller, _ = generate_cmdset_providers(self.caller, session=self.session)
                cmdset = yield get_and_merge_cmdsets(caller, providers, "object", text)
                if not self.valid():
                    break
                if not cmdset:
                    raise rules.RuleError("현재 명령 집합을 확인할 수 없어 남은 실행을 중단합니다.")
                selection = select_command(text, cmdset, caller, session=self.session,
                                           shortcuts=self.shortcuts, personal=not item.global_expanded,
                                           global_aliases=not item.global_expanded)
                matches = selection.matches
                if item.global_expanded and not matches:
                    from commands.aliases import ARGUMENT_SHORTCUTS, SHORTCUTS
                    from commands.shortcuts import normalized_keys

                    action = selection.text.rsplit(None, 1)[-1].casefold()
                    if (selection.text in SHORTCUTS or action in ARGUMENT_SHORTCUTS
                            or isinstance(self.shortcuts, dict) and normalized_keys(self.shortcuts, action)):
                        raise rules.RuleError("인자형 전역 정의는 다른 단축어·개인 줄임말로 재확장하지 않습니다.")
                if len(matches) == 1:
                    name, args, command, _, _, _ = matches[0]
                    if isinstance(command, GlobalShortcut):
                        self.queue.appendleft(QueueItem(command.global_command, item.shortcut_path, True))
                        continue
                    if isinstance(command, PersonalShortcut):
                        self.expand_personal(command.shortcut_name, args, item)
                        continue
                    if isinstance(command, Sequence):
                        raise rules.RuleError("단일 세그먼트에서 새 묶음을 생성할 수 없습니다.")
                else:
                    command = cmdset.get(CMD_MULTIMATCH if matches else CMD_NOMATCH)
                    if command is None:
                        raise rules.RuleError("명령 오류 처리기를 확인할 수 없습니다.")
                    name, args = command.key, selection.text
                    if matches:
                        from copy import copy

                        command = copy(command)
                        command.matches = matches
                require_completed_command(command, caller, self.session, multimatch=len(matches) > 1)
                if self.attempts >= MAX_COMMANDS:
                    raise rules.RuleError("명령 실행은 10개까지 가능합니다. 11번째부터 중단합니다.")
                if self.characters + len(selection.text) > MAX_EXPANDED_CHARACTERS:
                    raise rules.RuleError("최종 명령 문자열 합계는 1,000자까지 가능합니다.")
                self.attempts += 1
                self.characters += len(selection.text)
                command = with_prompt(command)
                command.retain_instance = True  # 매번 새 copy. cmdobj로 이 선택 인스턴스만 실행한다.
                command.shortcut_invocation = Invocation(self)
                command.shortcut_dispatch = (cmdset, selection.text)
                self.outputs.append(command)
                original_func = command.func

                def guarded_func(original_func=original_func, command=command):
                    if not self.valid():
                        return None
                    try:
                        result = original_func()
                        if isinstance(result, (Deferred, GeneratorType, CoroutineType)):
                            if isinstance(result, (GeneratorType, CoroutineType)):
                                result.close()
                            self.stop()
                            raise rules.RuleError("명령의 완료를 확인할 수 없습니다.")
                        return result
                    except Exception:
                        self.stop()
                        raise

                command.func = guarded_func
                # 문자열/nick/parser를 다시 거치지 않는다. engine pre/parse/func/post는 유지한다.
                token = _DISPATCH_ORIGIN.set(command.shortcut_invocation)
                try:
                    yield cmdhandler(self.caller, args, callertype="object", session=self.session,
                                     cmdobj=command, cmdobj_key=name)
                finally:
                    _DISPATCH_ORIGIN.reset(token)
                if not self.valid():
                    break
        except rules.RuleError as error:
            if self.owns_session():
                self.caller.msg(ft.text(ft.token("error", str(error)), kind="error"))
        except Exception:
            if self.owns_session():
                self.caller.msg(ft.text(ft.token("error", "실행기 오류로 남은 명령을 중단했습니다."), kind="error"))
            self.stop()
            raise
        finally:
            if not self.owns_session():
                self.stop()
            self.finish()
