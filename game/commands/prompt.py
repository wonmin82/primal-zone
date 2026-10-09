"""dispatcher의 실제 완료 hook을 사용한다. func/progressive 처리는 변경하지 않는다."""

from copy import copy
from functools import lru_cache
from types import MethodType

from twisted.internet.defer import maybeDeferred


class PromptLifecycle:
    def original_hook(self, name):
        hook = getattr(self, "primal_original_" + name, None)
        if name in getattr(self, "primal_bound_hooks", ()):
            return MethodType(hook, self)
        return hook or getattr(super(), name)

    def at_pre_cmd(self):
        origin = getattr(self, "shortcut_invocation", None)
        if origin and not origin.direct and not origin.execution.valid():
            return True
        prepared = getattr(self, "shortcut_dispatch", None)
        if prepared:
            self.cmdset, self.raw_string = prepared
        begin = getattr(self.caller, "begin_command_output", None)
        if not begin:
            return self.original_hook("at_pre_cmd")()
        if (getattr(self, "equipment_change", False) or getattr(self, "read_only", False)
                or getattr(self, "is_exit", False)):
            begin(reconcile=False)
        else:
            begin()
        self.primal_prompt_context = True
        # MuxAccountCommand.parse가 caller를 Account로 바꿔도 시작 캐릭터를 종료한다.
        self.primal_prompt_caller = self.caller

        def aborted(result):
            if result:
                self.finish_prompt()
            return result

        return maybeDeferred(self.original_hook("at_pre_cmd")).addCallback(aborted).addErrback(self.failed_hook)

    def failed_hook(self, failure):
        origin = getattr(self, "shortcut_invocation", None)
        if origin and not origin.direct:
            origin.execution.stop()
        self.finish_prompt()
        return failure

    def parse(self):
        return maybeDeferred(self.original_hook("parse")).addErrback(self.failed_hook)

    def finish_prompt(self):
        if getattr(self, "primal_prompt_context", False):
            self.primal_prompt_context = False
            origin = getattr(self, "shortcut_invocation", None)
            self.primal_prompt_caller.end_command_output(
                emit_prompt=not origin or origin.allows_prompt())

    def at_post_cmd(self):
        def completed(result):
            self.finish_prompt()
            return result

        return maybeDeferred(self.original_hook("at_post_cmd")).addErrback(self.failed_hook).addBoth(completed)


@lru_cache(maxsize=128)
def prompt_class(original):
    return type("Prompt" + original.__name__, (PromptLifecycle, original), {})


def with_prompt(command):
    # cmdhandler가 다시 copy해도 hook은 그 실행 인스턴스를 사용해야 한다.
    source, command = command, copy(command)
    bound = set(getattr(command, "primal_bound_hooks", ()))
    for name in ("at_pre_cmd", "parse", "at_post_cmd"):
        if name in command.__dict__:
            hook = command.__dict__.pop(name)
            if isinstance(hook, MethodType) and hook.__self__ is source:
                hook = hook.__func__
                bound.add(name)
            else:
                bound.discard(name)
            command.__dict__["primal_original_" + name] = hook
    command.primal_bound_hooks = frozenset(bound)
    if not isinstance(command, PromptLifecycle):
        command.__class__ = prompt_class(type(command))
    return command
