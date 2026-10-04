"""교관에게 위임하는 성장 명령. 포인트 계산은 순수 규칙에서 수행한다."""

from world import rules
from world.content import find_id
from world.progression import ATTRIBUTES, SKILLS
from world.targets import item_selector, names, parse_relation, resolve, room_objects

from commands.base import GameCommand


def training_input(caller, value):
    objects = room_objects(caller)
    if "에게" in value:
        selector, value = parse_relation(value, "에게", [n for obj in objects for n in names(obj)])
        return selector, value
    return None, value


def provider(caller, action, identity, selector=None):
    from typeclasses.interactables import AttributeTrainer, SkillTrainer, TrainingManager

    kind = SkillTrainer if action == "배워" else AttributeTrainer if action == "배분" else TrainingManager
    objects = room_objects(caller)
    if selector:
        return resolve(objects, selector, caller, action, lambda obj: isinstance(obj, kind))[0]
    candidates = [obj for obj in objects if isinstance(obj, kind) and
                  (action == "재분배" or (obj.db.skill_id if action == "배워" else obj.db.attribute_id) == identity)]
    if not candidates:
        label = SKILLS[identity]["name"] if action == "배워" else ATTRIBUTES[identity]["name"] if action == "배분" else "재훈련"
        raise rules.RuleError(f"이곳에는 {label}를 가르치는 교관이 없다.")
    if len(candidates) > 1:
        raise rules.RuleError("어느 교관에게 훈련받을지 명확하지 않다. 대상을 지정해 다시 입력해 주세요.")
    return candidates[0]


class Learn(GameCommand):
    key = "배워"
    input_style = "target"
    category = "성장"
    usage = "강타 배워 · 타격교관에게 강타 배워"
    summary = "담당 교관에게 남은 기술 훈련 1회로 다음 Rank를 배웁니다. 비용은 없습니다."

    def run(self):
        selector, value = training_input(self.caller, self.args)
        skill = item_selector(value, SKILLS, self.key)
        if not skill:
            raise rules.RuleError(self.usage)
        provider(self.caller, "배워", skill, selector).perform_action(self.caller, "배워", skill)


class Allocate(GameCommand):
    key = "배분"
    input_style = "target"
    category = "성장"
    usage = "힘 1 배분 · 민첩 1 배분 · 체질 1 배분 · 지혜 1 배분"
    summary = "주변 훈련관에게 미사용 특성 포인트를 투자합니다."

    def run(self):
        selector, value = training_input(self.caller, self.args)
        parts = value.strip().split()
        try:
            name, amount = (parts[0], int(parts[1])) if len(parts) == 2 else (parts[0], 1)
        except (ValueError, IndexError):
            raise rules.RuleError(self.usage) from None
        attribute = find_id(ATTRIBUTES, name)
        if len(parts) not in (1, 2) or not attribute:
            raise rules.RuleError(self.usage)
        provider(self.caller, "배분", attribute, selector).perform_action(self.caller, "배분", (attribute, amount))


class Retrain(GameCommand):
    key = "재분배"
    aliases = ["재훈련"]
    input_style = "target"
    category = "성장"
    usage = "특성 재분배 · 기술 재분배 · 전체 재훈련"
    summary = "훈련관리관에게 무료로 투자한 특성·기술 훈련을 반환받습니다. 탐사 기록은 유지합니다."

    def run(self):
        selector, value = training_input(self.caller, self.args)
        scope = {"특성": "attributes", "기술": "skills", "전체": "all"}.get(value.strip())
        if not scope:
            raise rules.RuleError(self.usage)
        provider(self.caller, "재분배", scope, selector).perform_action(self.caller, "재분배", scope)
