"""base 영역의 명시적 게임 명령."""

from evennia import Command
from world import rules


class GameCommand(Command):
    help_category = "원시구역"
    input_style = "standalone"

    def func(self):
        try:
            self.run()
            from typeclasses.explorers import Explorer

            for player in Explorer.objects.all():
                if player.sessions.count():
                    player.push_state()
        except rules.RuleError as error:
            self.caller.msg(f"|y{error}|n")

    def peaceful(self):
        rules.require_peace(self.caller.profile())

    def at_dock(self):
        self.peaceful()
        if self.caller.zone != "dock":
            raise rules.RuleError("부두에서만 이용할 수 있습니다. '귀환'으로 돌아가세요.")


class UnknownCommand(Command):
    key = "__nomatch_command"

    def func(self):
        self.caller.msg(
            "명령을 확인하세요. 대상 뒤에 행동을 입력합니다: 어린청소룡 공격 · 윤대장 대화\n"
            "채팅: 안녕하세요 말 또는 '안녕하세요 · 전체 안내: 도움말"
        )
