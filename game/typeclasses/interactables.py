"""공통 행동을 받는 영속 콘텐츠 객체. 진행 상태는 개인 규칙으로 변경한다."""

from evennia.objects.objects import DefaultObject
from world import rules
from world.content import ROOMS
from world.progression import ATTRIBUTES, SKILLS


class ActionObject(DefaultObject):
    actions = ()

    def at_object_creation(self):
        self.locks.add("get:false();puppet:false()")

    def supports_action(self, action):
        return action in self.actions

    def perform_action(self, caller, action, args=None):
        if self.location != caller.location or not self.supports_action(action):
            raise rules.RuleError("이곳에서 그 대상에게 할 수 없는 행동입니다.")
        rules.require_peace(caller.profile())
        return self.act(caller, action, args)


class Commander(ActionObject):
    actions = ("대화",)

    def act(self, caller, action, args):
        result = caller.change(rules.commander_talk)
        messages = {
            "start": "윤대장: 장비를 마련하고 관리동의 정비기록을 찾아보게. 발전기를 복구하고 능선의 우두머리를 처치하면 통신탑을 되찾을 수 있네.",
            "complete": "|g첫 탐사 완료!|n 경험치 +100 · 크레딧 +100 · 붕대 +3\n통신탑에서 구조 신호가 퍼져 나간다. 자유롭게 사냥과 장비 수집을 계속할 수 있습니다.",
        }
        caller.msg(messages.get(result, caller.quest_text(caller.profile())))


class MaintenanceLog(ActionObject):
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.read_record)
        caller.msg(
            "정비기록: 회수부품 3개로 발전기를 수리하면 능선의 문을 열 수 있다.\n현장 메모: 우두머리가 몸을 낮추면 다음 차례에는 방어할 것."
        )


class SupplyCache(ActionObject):
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.claim_cache)
        caller.msg("보급상자에서 붕대 2개를 찾았습니다.")


class Generator(ActionObject):
    actions = ("수리",)

    def act(self, caller, action, args):
        caller.change(rules.fix_generator)
        caller.msg("발전기가 돌아갑니다! 경험치 +50. 능선 진입문이 열렸습니다.")


class Instructor(ActionObject):
    actions = ("대화", "배워", "배분", "재분배")

    def available(self, caller):
        return (
            self.location == caller.location
            and caller.zone == "dock"
            and ROOMS["dock"]["safe"]
            and not caller.profile().get("combat_target")
        )

    def act(self, caller, action, args):
        safe = self.available(caller)
        if action == "대화":
            caller.msg(
                "탐사대 훈련관: 전투 기록을 분석하고 훈련 계획을 다시 짜 드리지요.\n힘 1 배분 · 강타 배워 · 특성 재분배 · 기술 재분배 · 전체 재훈련\n재훈련은 무료입니다. 기본 Rank 1은 유지하며 학습 크레딧은 반환하지 않습니다."
            )
        elif action == "배워":
            caller.change(lambda profile: rules.learn_skill(profile, args, safe=safe))
            caller.msg(f"{SKILLS[args]['name']} Rank {caller.profile()['skills'][args]} 학습 완료.")
        elif action == "배분":
            attribute, amount = args
            caller.change(
                lambda profile: rules.allocate_attribute(profile, attribute, amount, safe=safe)
            )
            caller.msg(f"{ATTRIBUTES[attribute]['name']}에 {amount} 포인트를 배분했습니다.")
        elif action == "재분배":
            caller.change(lambda profile: rules.retrain(profile, args, safe=safe))
            caller.msg("재훈련 완료. 투자 포인트를 반환했습니다. 숙련과 탐사 기록은 유지됩니다.")


def action_objects(room):
    return [obj for obj in room.contents if isinstance(obj, ActionObject)] if room else []


def instructor_for(caller):
    return next(
        (obj for obj in action_objects(caller.location) if isinstance(obj, Instructor)), None
    )


DEFINITIONS = (
    ("commander", "dock", "Commander", "윤대장", ["대장"]),
    ("instructor", "dock", "Instructor", "탐사대 훈련관", ["훈련관", "교관"]),
    ("maintenance_log", "office", "MaintenanceLog", "정비기록", ["기록"]),
    ("supply_cache", "wreck", "SupplyCache", "보급상자", ["상자"]),
    ("generator", "generator", "Generator", "발전기", []),
)
