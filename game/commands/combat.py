"""combat 영역의 명시적 게임 명령."""

from world import rules
from world.content import ENEMIES, find_id

from commands.base import GameCommand


class Attack(GameCommand):
    category = "전투"
    usage = "어린청소룡 공격"
    summary = "공유 적에게 2.5초 간격으로 기본 공격합니다."
    input_style = "target"
    key = "공격"
    aliases = ["사냥", "attack"]

    def run(self):
        name = self.args.strip()
        current = self.caller.combat_target()
        enemy = find_id(ENEMIES, name) if name else current.db.enemy_id if current else None
        if not enemy:
            raise rules.RuleError("사용법: 어린청소룡 공격 · '보기'로 사냥 대상을 확인하세요.")
        self.caller.start_combat(enemy)


class Heavy(GameCommand):
    category = "전투"
    usage = "강타"
    summary = "다음 차례에 강타를 예약합니다. 반복 입력으로 빨라지지 않습니다."
    key = "강타"
    aliases = ["heavy"]
    action = "heavy"

    def run(self):
        self.caller.change(lambda profile: rules.queue_action(profile, self.action))
        self.caller.msg(f"다음 차례에 {self.key}합니다.")


class Guard(Heavy):
    category = "전투"
    usage = "방어"
    summary = "다음 차례에 방어를 예약합니다."
    key = "방어"
    aliases = ["guard"]
    action = "guard"


class Heal(GameCommand):
    category = "전투"
    usage = "회복"
    summary = "붕대로 회복합니다. 전투 중에는 다음 기본 공격을 대신합니다."
    key = "회복"
    aliases = ["붕대", "heal", "응급치료"]

    def run(self):
        if self.caller.profile().get("combat_target"):
            self.caller.change(lambda profile: rules.queue_action(profile, "heal"))
            self.caller.msg("다음 차례에 붕대를 사용합니다. 이번 기본 공격을 대신합니다.")
        else:
            amount = self.caller.change(rules.heal)
            self.caller.msg(f"체력 {amount} 회복.")


class Flee(GameCommand):
    category = "전투"
    usage = "도주"
    summary = "교전에서 이탈합니다."
    key = "도주"
    aliases = ["flee"]

    def run(self):
        if not self.caller.profile().get("combat_target"):
            raise rules.RuleError("진행 중인 교전이 없습니다.")
        self.caller.leave_combat()
        self.caller.msg("교전을 끝냈습니다. 적은 일정 시간 아무도 싸우지 않으면 회복합니다.")
