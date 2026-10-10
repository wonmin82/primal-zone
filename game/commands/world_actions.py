"""world_actions 영역의 명시적 게임 명령."""

from world import rules
from world.targets import TargetSelector, names, normalized, parse_selector, resolve, room_objects

from commands.base import GameCommand


class Return(GameCommand):
    category = "이동·탐사"
    usage = "귀환"
    summary = "비전투 상태에서 본부 옥상으로 돌아갑니다."
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
    read_only = True  # 검증 실패는 자연회복도 저장하지 않는다. 성공 시 의료 transaction이 저장한다.
    usage = "회복 · 20 회복 · 의무관 회복 · 의무관에게 20 회복"
    summary = "의무관에게 보급칩을 지불해 자신의 부족한 HP만 회복합니다."
    key = "회복"
    aliases = []
    help_sections = (
        ("사용법", (usage,)),
        ("예시", ("회복", "20 회복", "의무관 회복", "의무관에게 20 회복")),
        ("실행 규칙", ("생략하면 부족 HP 전량, 수량을 지정하면 부족 HP 범위에서 요청량까지 회복합니다.",
                      "H=실제 회복 HP, L=현재 레벨, P=2*H+(L if L<100 else 2*L), 비용=max(1, ceil(P/10))칩입니다.",
                      "레벨 10의 HP 5는 2칩, HP 20은 5칩입니다. 레벨 50/99/100의 HP 20은 9/14/24칩입니다.",
                      "실행 당시 상태로 비용을 다시 계산하며 HP 증가와 비용 차감을 함께 저장합니다.")),
        ("제한", ("같은 방의 보이는 의무관 · 안전 지역 · 비전투 상태에서 자신만 이용합니다. 정신력은 회복하지 않습니다.",
                "회복할 HP 없음·잔액 부족·0/음수/비정수/1,000,000 초과 수량은 거절하고 과금하지 않습니다.",
                "회복실 침대의 무료 HP·정신력 전체 휴식은 별도 서비스입니다.")),
        ("관련 도움말", ("휴식 도움", "치료 도움", "점수 도움")),
    )

    def run(self):
        from typeclasses.interactables import Doctor
        from world.multiplayer import world_change
        from world.targets import parse_relation

        value = self.args.strip()
        requested = None
        with world_change():
            if value.endswith("에게"):
                doctor = resolve_medical(self.caller, self.key, value)
            elif any(word.endswith("에게") for word in value.split()):
                doctors = [obj for obj in room_objects(self.caller) if isinstance(obj, Doctor)]
                selector, quantity = parse_relation(value, "에게", [n for obj in doctors for n in names(obj)])
                doctor = resolve(doctors, selector, self.caller, self.key)[0]
                requested = parse_recovery_quantity(quantity) if quantity else None
            elif value and (value[0].isdigit() or value[0] in "+-."):
                requested = parse_recovery_quantity(value)
                doctor = resolve_medical(self.caller, self.key)
            else:
                doctor = resolve_medical(self.caller, self.key, value)
            doctor.perform_action(self.caller, self.key, requested)


def parse_recovery_quantity(value):
    if not value.isascii() or not value.isdecimal() or len(value) > 7:
        raise rules.RuleError("회복량은 1~1,000,000 사이의 정수로 입력하세요.")
    quantity = int(value)
    if not 1 <= quantity <= rules.MAX_TREAT_HP:
        raise rules.RuleError("회복량은 1~1,000,000 사이의 정수로 입력하세요.")
    return quantity


def resolve_medical(caller, action, name=""):
    """의료 bare 입력은 보이는 서비스가 정확히 하나일 때만 선택한다."""
    from typeclasses.interactables import Bed, Doctor

    kind = Doctor if action == "회복" else Bed
    objects = [obj for obj in room_objects(caller) if isinstance(obj, kind)]
    name = name.strip()
    known = [n for obj in objects for n in names(obj)]
    if not name:
        if not objects:
            raise rules.RuleError("이곳에서 이용할 대상을 찾지 못했습니다. '봐'로 주변을 살펴보세요.")
        if len(objects) > 1:
            raise rules.RuleError(f"이용할 대상이 여러 개입니다. 대상 이름과 번호를 지정해 {action}하세요.")
        return objects[0]
    particle = "에게" if action == "회복" else "에서"
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
        raise rules.RuleError("이곳에서 행동할 대상을 확인하세요. '봐'로 주변을 살펴보세요.")
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
