"""base 영역의 명시적 게임 명령."""

from evennia import Command
from evennia.commands.cmdhandler import CMD_NOINPUT, CMD_NOMATCH
from evennia.commands.default.help import CmdHelp
from world import rules
from world import text as ft


class EngineHelp(CmdHelp):
    """엔진 페이지 입력 계약용 별도 이름. 사용자 도움/영문 help와 분리한다."""

    key = "@help"
    aliases = []


class GameCommand(Command):
    help_category = "원시구역"
    input_style = "standalone"
    category = "이동·탐사"

    def func(self):
        try:
            self.run()
            from typeclasses.explorers import Explorer
            from world.multiplayer import after_change

            for player in Explorer.objects.all():
                if player.sessions.count():
                    after_change(player.push_state)
        except rules.RuleError as error:
            self.caller.msg(ft.text(ft.token("error", str(error)), kind="error"))

    def peaceful(self):
        rules.require_peace(self.caller.profile())


class UnknownCommand(Command):
    key = CMD_NOMATCH
    read_only = True

    def at_pre_cmd(self):
        if not getattr(self, "primal_prompt_context", False) and hasattr(self.caller, "begin_command_output"):
            self.caller.begin_command_output(reconcile=not self.read_only)

    def at_post_cmd(self):
        if not getattr(self, "primal_prompt_context", False) and hasattr(self.caller, "end_command_output"):
            self.caller.end_command_output()

    def func(self):
        from world.navigation import blocked_exit_message

        from commands.aliases import SHORTCUTS

        raw = self.raw_string.strip()
        message = blocked_exit_message(getattr(self.caller, "zone", None), SHORTCUTS.get(raw, raw))
        if message:
            self.caller.msg(ft.text(ft.token("warning", message)))
            return
        from world.actions.manifest import get_index
        from world.actions.presentation import help_entries

        entries = help_entries(get_index())
        if any(raw == entry["verb"] or raw.endswith(" " + entry["verb"]) or
               any(raw == alias or raw.endswith(" " + alias) for alias in entry["aliases"])
               for entry in entries):
            self.caller.msg("현재 이곳에서 사용할 수 없는 행동입니다. 대상과 도움말을 확인하세요.")
            return
        self.caller.msg(
            "명령을 확인하세요. 대상 뒤에 행동을 입력합니다: 어린청소룡 때려 · 윤대장에게 임무 말\n"
            "채팅: 안녕하세요 말 또는 '안녕하세요 · 전체 안내: 도움"
        )


class NoInput(UnknownCommand):
    key = CMD_NOINPUT
    read_only = False

    def at_pre_cmd(self):
        self.waiting_depth = getattr(self.caller.ndb, "command_output_depth", 0) or 0
        super().at_pre_cmd()
        if self.waiting_depth:
            self.caller.reconcile_recovery(emit_prompt=False)

    def at_post_cmd(self):
        super().at_post_cmd()
        if self.waiting_depth:
            self.caller.push_prompt()

    def func(self):
        pass
