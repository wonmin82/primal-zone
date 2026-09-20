"""world_actions 영역의 명시적 게임 명령."""

from world import rules

from commands.base import GameCommand


class Return(GameCommand):
    category = "탐사"
    usage = "귀환"
    summary = "비전투 상태에서 부두로 돌아갑니다."
    key = "귀환"
    aliases = ["home"]

    def run(self):
        from world.bootstrap import get_room

        self.peaceful()
        self.caller.move_to(get_room("dock"), quiet=True)


class Rest(GameCommand):
    category = "보급"
    usage = "휴식"
    summary = "부두 의무실에서 체력을 회복합니다."
    key = "휴식"
    aliases = ["rest"]

    def run(self):
        self.at_dock()
        self.caller.change(lambda profile: profile.update(hp=rules.stats(profile)["max_hp"]))
        self.caller.msg("부두 의무실에서 체력을 모두 회복했습니다.")


def resolve_action(caller, action, name=None):
    from typeclasses.interactables import action_objects

    normalized = "".join(name.split()).casefold() if name else None
    matches = [
        obj
        for obj in action_objects(caller.location)
        if obj.supports_action(action)
        and (
            normalized is None
            or normalized
            in ["".join(value.split()).casefold() for value in (obj.key, *obj.aliases.all())]
        )
    ]
    if len(matches) != 1:
        raise rules.RuleError("이곳에서 행동할 대상을 확인하세요. '보기'로 주변을 살펴보세요.")
    return matches[0]


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
