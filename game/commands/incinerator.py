"""소각은 서버의 단일 폐기 서비스로 처리한다."""

from commands.base import GameCommand


class Burn(GameCommand):
    key = "소각"
    aliases = ["소각 확정"]
    input_style = "target"
    category = "아이템·보급"
    usage = "붕대 소각 · 붕대 3개 소각 · 붕대 모두 소각 · 전초 보급구역 출입증 소각 확정"
    summary = "주변 소각기에서 물품을 폐기합니다. 출입증은 소각 확정이 필요합니다."

    def run(self):
        from world.incinerator_service import incinerate

        self.caller.msg(incinerate(self.caller, self.args, confirmed=self.cmdstring == "소각 확정"))
