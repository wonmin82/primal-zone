"""교관에게 위임하는 성장 명령. 포인트 계산은 순수 규칙에서 수행한다."""

from world import rules
from world.content import find_id
from world.progression import ATTRIBUTES, SKILLS

from commands.base import GameCommand
from commands.world_actions import resolve_action


class Learn(GameCommand):
    key = "배워"
    input_style = "target"
    category = "성장"
    usage = "강타 배워 · 방어 배워 · 응급치료 배워"
    summary = "부두 교관에게 기술점수와 크레딧으로 다음 Rank를 배웁니다."

    def run(self):
        skill = find_id(SKILLS, self.args.strip())
        if not skill:
            raise rules.RuleError(self.usage)
        resolve_action(self.caller, "배워").perform_action(self.caller, "배워", skill)


class Allocate(GameCommand):
    key = "배분"
    input_style = "target"
    category = "성장"
    usage = "힘 1 배분 · 민첩 1 배분 · 체질 1 배분 · 지혜 1 배분"
    summary = "부두 교관에게 미사용 특성 포인트를 투자합니다."

    def run(self):
        parts = self.args.strip().split()
        try:
            name, amount = (parts[0], int(parts[1])) if len(parts) == 2 else (parts[0], 1)
        except (ValueError, IndexError):
            raise rules.RuleError(self.usage) from None
        attribute = find_id(ATTRIBUTES, name)
        if len(parts) not in (1, 2) or not attribute:
            raise rules.RuleError(self.usage)
        resolve_action(self.caller, "배분").perform_action(self.caller, "배분", (attribute, amount))


class Retrain(GameCommand):
    key = "재분배"
    aliases = ["재훈련"]
    input_style = "target"
    category = "성장"
    usage = "특성 재분배 · 기술 재분배 · 전체 재훈련"
    summary = "부두 교관에게 무료로 투자 포인트를 반환받습니다. 숙련과 탐사 기록은 유지합니다."

    def run(self):
        scope = {"특성": "attributes", "기술": "skills", "전체": "all"}.get(self.args.strip())
        if not scope:
            raise rules.RuleError(self.usage)
        resolve_action(self.caller, "재분배").perform_action(self.caller, "재분배", scope)
