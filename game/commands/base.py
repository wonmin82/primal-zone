"""base 영역의 명시적 게임 명령."""

from evennia import Command
from world import rules
from world import text as ft


class GameCommand(Command):
    help_category = "원시구역"
    input_style = "standalone"
    category = "이동·탐사"

    def func(self):
        try:
            self.run()
            from typeclasses.explorers import Explorer

            for player in Explorer.objects.all():
                if player.sessions.count():
                    player.push_state()
        except rules.RuleError as error:
            self.caller.msg(ft.text(ft.token("error", str(error)), kind="error"))

    def peaceful(self):
        rules.require_peace(self.caller.profile())


class UnknownCommand(Command):
    key = "__nomatch_command"

    def func(self):
        from world.navigation import blocked_exit_message

        from commands.aliases import SHORTCUTS

        raw = self.raw_string.strip()
        message = blocked_exit_message(getattr(self.caller, "zone", None), SHORTCUTS.get(raw, raw))
        if message:
            self.caller.msg(ft.text(ft.token("warning", message)))
            return
        self.caller.msg(
            "명령을 확인하세요. 대상 뒤에 행동을 입력합니다: 어린청소룡 공격 · 윤대장 대화\n"
            "채팅: 안녕하세요 말 또는 '안녕하세요 · 전체 안내: 도움말"
        )
