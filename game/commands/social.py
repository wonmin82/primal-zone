"""social 영역의 명시적 게임 명령."""

from evennia.utils.ansi import strip_ansi
from world import rules
from world import text as ft

from commands.base import GameCommand


class Say(GameCommand):
    category = "교류"
    usage = "내용 말 · '내용"
    summary = "같은 방의 탐사자에게 말합니다."
    input_style = "chat"
    key = "말"
    aliases = ["say"]

    def run(self):
        text = strip_ansi(self.args.strip())
        if not text:
            raise rules.RuleError("내용 말 또는 '내용")
        if len(text) > 300:
            raise rules.RuleError("대화는 300자 이하로 입력하세요.")
        # msg_contents의 템플릿 해석 없이 중괄호와 $You()도 입력 그대로 전달한다.
        message = ft.text(ft.token("player", self.caller.key), ": ", text, kind="chat")
        for recipient in self.caller.location.contents:
            recipient.msg(message)
