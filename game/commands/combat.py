"""combat 영역의 명시적 게임 명령."""

from world import rules
from world import text as ft
from world.targets import names, parse_selector, resolve, room_objects

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

    def run(self):
        from typeclasses.enemies import Enemy
        from world.lifecycle import reconcile_room

        name = self.args.strip()
        current = self.caller.combat_target()
        reconcile_room(self.caller.location)
        objects = room_objects(self.caller)
        enemy = (
            resolve(
                objects,
                parse_selector(name, [n for obj in objects for n in names(obj)]),
                self.caller,
                self.key,
                lambda obj: isinstance(obj, Enemy) and obj.db.state == "alive",
            )[0]
            if name
            else current
        )
        if not enemy:
            raise rules.RuleError("사용법: 어린청소룡 때려 · '봐'로 사냥 대상을 확인하세요.")
        self.caller.start_combat(enemy)


class Heavy(GameCommand):
    category = "전투·회복"
    usage = "강타"
    summary = "다음 차례에 강타를 예약합니다. 반복 입력으로 빨라지지 않습니다."
    key = "강타"
    aliases = ["heavy"]
    action = "heavy"

    def run(self):
        self.caller.change(lambda profile: rules.queue_action(profile, self.action))
        self.caller.msg(ft.text("다음 차례에 ", ft.token("command", self.key), " 행동을 준비한다."))


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
    summary = "정신력으로 자신 또는 같은 방의 파티원을 치료합니다. 전투 중에는 다음 공격을 대신합니다."
    input_style = "target"
    key = "치료"
    aliases = ["힐", "heal"]
    action = "heal"

    def run(self):
        from world.skill_services import use_support

        use_support(self.caller, self.action, self.args)


class Breathe(Heal):
    key = "호흡"
    aliases = ["breathing"]
    usage = "호흡"
    summary = "정신력을 회복합니다. 전투 중에는 공격 한 차례를 사용합니다."
    action = "breathing"
    input_style = "bare"


class Use(Heal):
    key = "사용"
    aliases = []
    usage = "붕대 사용"
    summary = "붕대 하나로 HP를 회복합니다. 전투 중에는 다음 공격을 대신하며 정신력은 소비하지 않습니다."
    action = "bandage"

    def run(self):
        if self.args.strip() not in ("붕대", "bandage"):
            raise rules.RuleError(self.usage)
        from world.skill_services import use_support

        use_support(self.caller, self.action)


class Flee(GameCommand):
    category = "전투·회복"
    usage = "도망"
    summary = "교전에서 이탈합니다."
    key = "도망"
    aliases = ["flee"]

    def run(self):
        if not self.caller.profile().get("combat_target"):
            raise rules.RuleError("진행 중인 교전이 없습니다.")
        self.caller.leave_combat()
        self.caller.msg("교전을 끝냈습니다. 적은 일정 시간 아무도 싸우지 않으면 회복합니다.")
