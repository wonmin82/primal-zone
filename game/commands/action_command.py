"""선언된 정규 동사당 하나의 Evennia Command. Hook/Prompt는 기존 어댑터를 재사용한다."""

from world.actions.gateway import emit, execute
from world.actions.manifest import get_index
from world.actions.resolver import dispatch_text

from commands.base import GameCommand


class DynamicActionCommand(GameCommand):
    input_style = "target"
    dynamic_action = True
    read_only = True

    def func(self):
        from world import rules
        from world import text as ft

        index = get_index()
        try:
            invocation = dispatch_text(self.caller, index, self.verb_id, self.args.strip(), self.cmdstring)
            result = execute(self.caller, self.session, invocation, index)
            emit(self.caller, self.session, invocation, result)
        except rules.RuleError as error:
            self.caller.msg(ft.text(ft.token("error", str(error))), session=self.session, kind="error")
