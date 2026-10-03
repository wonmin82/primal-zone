"""world_actions 영역의 명시적 게임 명령."""

from world import rules
from world.targets import TargetSelector, names, normalized, parse_selector, resolve, room_objects

from commands.base import GameCommand


class Return(GameCommand):
    category = "이동·탐사"
    usage = "귀환"
    summary = "비전투 상태에서 지원동 옥상으로 돌아갑니다."
    key = "귀환"
    aliases = ["home"]

    def run(self):
        from world.bootstrap import get_room

        self.peaceful()
        self.caller.move_to(get_room("support_roof"), quiet=True)


class Rest(GameCommand):
    category = "전투·회복"
    input_style = "target"
    usage = "휴식 · 침대 휴식 · 침대에서 휴식"
    summary = "주변 침대에서 무료로 체력과 정신력을 모두 회복합니다."
    key = "휴식"
    aliases = ["rest"]

    def run(self):
        resolve_medical(self.caller, self.key, self.args).perform_action(self.caller, self.key)


class Treat(GameCommand):
    category = "전투·회복"
    input_style = "target"
    usage = "진료 · 의무관 진료 · 의무관에게 진료"
    summary = "주변 의무관에게 무료로 체력을 모두 회복합니다."
    key = "진료"
    aliases = ["treat"]

    def run(self):
        resolve_medical(self.caller, self.key, self.args).perform_action(self.caller, self.key)


def resolve_medical(caller, action, name=""):
    """의료 bare 입력은 보이는 서비스가 정확히 하나일 때만 선택한다."""
    from typeclasses.interactables import Bed, Doctor

    kind = Doctor if action == "진료" else Bed
    objects = [obj for obj in room_objects(caller) if isinstance(obj, kind)]
    name = name.strip()
    known = [n for obj in objects for n in names(obj)]
    if not name:
        if not objects:
            raise rules.RuleError("이곳에서 이용할 대상을 찾지 못했습니다. '보기'로 주변을 살펴보세요.")
        if len(objects) > 1:
            raise rules.RuleError(f"이용할 대상이 여러 개입니다. 대상 이름과 번호를 지정해 {action}하세요.")
        return objects[0]
    particle = "에게" if action == "진료" else "에서"
    if normalized(name) not in {normalized(n) for n in known} and name.endswith(particle):
        name = name[:-len(particle)].strip()
    return resolve(objects, parse_selector(name, known), caller, action)[0]


def resolve_action(caller, action, name=None):
    objects = room_objects(caller)

    def supports(obj):
        return hasattr(obj, "supports_action") and obj.supports_action(action)

    if name:
        selector = parse_selector(name, [n for obj in objects for n in names(obj)])
        return resolve(objects, selector, caller, action, supports)[0]
    objects = [obj for obj in objects if supports(obj)]
    if not objects:
        raise rules.RuleError("이곳에서 행동할 대상을 확인하세요. '보기'로 주변을 살펴보세요.")
    return resolve(objects, TargetSelector(objects[0].key), caller, action)[0]


class TargetAction(GameCommand):
    input_style = "target"

    def run(self):
        if not self.args.strip():
            raise rules.RuleError(f"대상 이름 뒤에 {self.key}를 입력하세요.")
        resolve_action(self.caller, self.key, self.args).perform_action(self.caller, self.key)


class Talk(TargetAction):
    key = "대화"
    usage = "윤대장 대화 · 탐사대 훈련관 대화"
    summary = "주변 인물과 대화합니다."


class Investigate(TargetAction):
    key = "조사"
    usage = "정비기록 조사 · 보급상자 조사"
    summary = "주변 단서와 보급품을 조사합니다."


class Repair(TargetAction):
    key = "수리"
    usage = "발전기 수리"
    summary = "대상 시설을 복구합니다."
