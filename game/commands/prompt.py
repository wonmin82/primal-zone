"""dispatcher의 실제 완료 hook을 사용한다. func/progressive 처리는 변경하지 않는다."""

from copy import copy
from functools import lru_cache

from twisted.internet.defer import maybeDeferred


class PromptLifecycle:
    def at_pre_cmd(self):
        begin = getattr(self.caller, "begin_command_output", None)
        if not begin:
            return super().at_pre_cmd()
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

        return maybeDeferred(super().at_pre_cmd).addCallback(aborted)

    def finish_prompt(self):
        if getattr(self, "primal_prompt_context", False):
            self.primal_prompt_context = False
            self.primal_prompt_caller.end_command_output()

    def at_post_cmd(self):
        def completed(result):
            self.finish_prompt()
            return result

        return maybeDeferred(super().at_post_cmd).addBoth(completed)


@lru_cache(maxsize=128)
def prompt_class(original):
    return type("Prompt" + original.__name__, (PromptLifecycle, original), {})


def with_prompt(command):
    # cmdhandler가 다시 copy해도 hook은 그 실행 인스턴스를 사용해야 한다.
    command = copy(command)
    if not isinstance(command, PromptLifecycle):
        command.__class__ = prompt_class(type(command))
    return command
