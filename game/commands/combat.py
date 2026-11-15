"""combat 영역의 명시적 게임 명령."""

from commands.base import GameCommand
from commands.help_contracts import command_sections


class Attack(GameCommand):
    help_sections = command_sections('때려')
    category = "전투·회복"
    usage = "대상이름 때려 · 대상 2 때려"
    summary = "공유 적에게 2.5초 간격으로 기본 공격합니다."
    input_style = "target"
    key = "때려"
    aliases = ["쳐", "공격"]

    def func(self):
        from world.actions.global_actions import invoke

        return invoke(self.caller, self.session, "attack", query=self.args)


class Heavy(GameCommand):
    category = "전투·회복"
    usage = "강타"
    summary = "다음 차례에 강타를 예약합니다. 반복 입력으로 빨라지지 않습니다."
    key = "강타"
    aliases = ["heavy"]
    action = "heavy"

    def func(self):
        from world.actions.global_actions import invoke

        return invoke(self.caller, self.session, "queue_attack", skill=self.action)


class Shooting(Heavy):
    help_sections = command_sections('쏴')
    category = "전투·회복"
    usage = "쏴"
    summary = "총기로 다음 자동 공격을 강화합니다."
    key = "쏴"
    aliases = []
    action = "shooting"


class Insight(Heavy):
    key = "간파"
    aliases = ["insight"]
    usage = "간파"
    summary = "공격 한 차례를 포기하고 현재 상대의 빈틈을 분석합니다."
    action = "insight"


class Suppress(Heavy):
    key = "견제"
    aliases = ["suppress"]
    usage = "견제"
    summary = "다음 공격으로 상대의 이후 공격력을 낮춥니다."
    action = "suppress"


class Heal(GameCommand):
    category = "전투·회복"
    usage = "치료 · 철수 치료"
    summary = "정신력으로 자신 또는 같은 방의 일행원을 치료합니다. 전투 중에는 다음 공격을 대신합니다."
    input_style = "target"
    key = "치료"
    aliases = ["힐", "heal"]
    action = "heal"

    def func(self):
        from world.actions.global_actions import invoke

        return invoke(self.caller, self.session, "support", skill=self.action, query=self.args)


class Breathe(Heal):
    key = "호흡"
    aliases = ["breathing"]
    usage = "호흡"
    summary = "정신력을 회복합니다. 전투 중에는 공격 한 차례를 사용합니다."
    action = "breathing"
    input_style = "bare"




class Flee(GameCommand):
    category = "전투·회복"
    usage = "도망"
    summary = "교전에서 이탈합니다."
    key = "도망"
    aliases = ["flee"]

    def func(self):
        from world.actions.global_actions import invoke

        return invoke(self.caller, self.session, "flee")
