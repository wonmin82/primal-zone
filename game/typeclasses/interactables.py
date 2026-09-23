"""공통 행동을 받는 영속 콘텐츠 객체. 진행 상태는 개인 규칙으로 변경한다."""

from evennia.objects.objects import DefaultObject
from world import rules
from world import text as ft
from world.content import ENEMIES, ROOMS
from world.progression import ATTRIBUTES, SKILLS


class ActionObject(DefaultObject):
    actions = ()
    semantic_role = "object"
    presence = "가까이에서 살펴볼 수 있다."
    description = "탐사 중에 발견한 물건이다."

    def return_appearance(self, looker, **kwargs):
        return ft.sheet(
            ft.token(self.semantic_role, self.key), self.description, "", ft.actions(self.actions)
        )

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
    semantic_role = "npc"
    presence = "낡은 지도를 펼쳐 놓고 탐사대를 기다리고 있다."
    description = "탐사대를 지휘하는 책임자다. 낡은 지도와 무전기를 늘 곁에 두고 있다."
    actions = ("대화",)

    def act(self, caller, action, args):
        from world import presentation as view

        before = caller.profile()
        result = caller.change(rules.commander_talk)
        after = caller.profile()
        if result == "start":
            body = ft.text(
                "  장비를 마련하고 관리동의 ",
                content_name("maintenance_log"),
                "을 찾아보게. ",
                content_name("generator"),
                "를 복구하고 ",
                ft.token("hostile", ENEMIES["alpha"]["name"]),
                "를 처치하면 통신탑을 되찾을 수 있네.",
            )
        elif result == "complete":
            body = ft.text(
                ft.token("success", "첫 탐사를 완수했다."),
                "\n통신탑에서 구조 신호가 퍼져 나간다.\n보고를 마치고 ",
                ft.token("reward", f"경험치 {after['xp'] - before['xp']}"),
                ", ",
                ft.token("reward", f"{after['credits'] - before['credits']}크레딧"),
                ", ",
                ft.item("bandage"),
                f" {after['inventory'].get('bandage', 0) - before['inventory'].get('bandage', 0)}개를 받았다.",
            )
        else:
            body = view.quest(after)
        caller.msg(ft.text(ft.token("npc", self.key), "\n\n", body))


class MaintenanceLog(ActionObject):
    presence = "젖은 책상 위에 펼쳐져 있다."
    description = "발전기 복구 절차와 현장 전투 기록이 남아 있는 문서다."
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.read_record)
        caller.msg(
            ft.text(
                content_name("maintenance_log"),
                "을 펼쳐 복구 절차를 읽었다.\n  ",
                ft.item("scrap"),
                " 3개로 ",
                content_name("generator"),
                "를 수리하면 능선의 문을 열 수 있다.\n  ",
                ft.named("hostile", ENEMIES["alpha"]["name"], "이/가"),
                " 몸을 낮추면 다음 차례에는 ",
                ft.token("command", "방어"),
                "할 것.",
            )
        )


class SupplyCache(ActionObject):
    presence = "뒤집힌 수송차 틈에 걸려 있다."
    description = "누군가 남긴 보급품이 들어 있는 튼튼한 상자다."
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.claim_cache)
        caller.msg(
            ft.text(
                ft.token("object", self.key), "에서 ", ft.item("bandage"), " 2개를 찾아 챙겼다."
            )
        )


class Generator(ActionObject):
    presence = "낡은 외벽 너머로 희미한 경고등을 깜빡이고 있다."
    description = "능선 진입문에 전력을 공급하는 설비다. 정비기록과 부품이 필요하다."
    actions = ("수리",)

    def act(self, caller, action, args):
        before = caller.profile()["xp"]
        caller.change(rules.fix_generator)
        caller.msg(
            ft.text(
                ft.named("object", self.key, "이/가"),
                " 다시 돌아가기 시작했다. 능선 진입문이 열렸다.\n복구 작업으로 ",
                ft.token("reward", f"경험치 {caller.profile()['xp'] - before}"),
                "를 얻었다.",
            )
        )


class Instructor(ActionObject):
    semantic_role = "npc"
    presence = "탐사자의 전투 기록을 살피며 훈련 계획을 세우고 있다."
    description = "전투 기록을 분석하고 신체 훈련과 전술을 다시 설계하는 교관이다."
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
                ft.text(
                    ft.token("npc", self.key),
                    "\n\n  전투 기록을 분석하고 훈련 계획을 다시 짜 드리지요.\n  재훈련은 무료입니다. 기본 Rank 1은 유지하며 학습 크레딧은 반환하지 않습니다.\n\n",
                    ft.actions(self.actions),
                )
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


class Pathfinder(ActionObject):
    semantic_role = "npc"
    presence = "젖은 지도 위에 선발대의 이동 경로를 표시하고 있다."
    description = "밀림에서 돌아온 선발대 길잡이다. 두 갈래 탐사로의 표식을 찾고 있다."
    actions = ("대화",)

    def act(self, caller, action, args):
        before = caller.profile()
        result = caller.change(rules.jungle_talk)
        after = caller.profile()
        if result == "start":
            body = "관측소와 수몰 도로의 표식을 확인해 주세요. 두 기록을 맞추면 거목의 신호 장치가 연구구역 길을 열 겁니다."
        elif result == "complete":
            body = ft.text(
                ft.token("success", "밀림의 탐사를 마쳤다."), " 보고를 마치고 ",
                ft.token("reward", f"경험치 {after['xp'] - before['xp']}"), ", ",
                ft.token("reward", f"{after['credits'] - before['credits']}크레딧"),
                ", ", ft.item("bandage"), " 3개를 받았다.",
            )
        else:
            from world import presentation as view
            body = view.quest(after)
        caller.msg(ft.text(ft.token("npc", self.key), "\n\n", body))


class JungleMarker(ActionObject):
    presence = "나무와 돌에 선발대의 흔적이 남아 있다."
    description = "선발대가 길을 잃지 않도록 남긴 현장 표식이다."
    actions = ("조사",)
    quest_flag = None

    def act(self, caller, action, args):
        newly_marked = caller.change(lambda profile: rules.jungle_mark(profile, self.quest_flag))
        caller.msg(ft.text(ft.token("object", self.key), "을 살펴 선발대의 경로를 확인했다."))
        return newly_marked


class WatchMarker(JungleMarker):
    quest_flag = "watch_marked"


class WaterMarker(JungleMarker):
    quest_flag = "road_marked"

    def act(self, caller, action, args):
        if super().act(caller, action, args):
            caller.msg(ft.text("표식 아래에서 ", ft.item("jungle_cell"), "를 확보했다."))


class SignalDevice(ActionObject):
    presence = "닫힌 출입문 옆에서 신호등을 깜빡이고 있다."
    description = "두 탐사 표식의 좌표를 맞추면 연구구역의 문을 열 수 있다."
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.open_jungle_gate)
        caller.msg(ft.text(ft.item("jungle_cell"), "로 ", ft.token("object", self.key), "의 좌표를 맞추자 연구구역의 문이 열렸다."))


class JungleCache(ActionObject):
    presence = "검은 물가에 반쯤 잠겨 있다."
    description = "선발대가 늪을 지날 때 남긴 작은 보급 주머니다."
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.claim_jungle_cache)
        caller.msg(ft.text(ft.token("object", self.key), "에서 ", ft.item("bandage"), " 2개를 찾아 챙겼다."))


def action_objects(room):
    return [obj for obj in room.contents if isinstance(obj, ActionObject)] if room else []


def instructor_for(caller):
    return next(
        (obj for obj in action_objects(caller.location) if isinstance(obj, Instructor)), None
    )


INTERACTABLES = {
    "commander": {"room": "dock", "typeclass": "Commander", "name": "윤대장", "aliases": ["대장"]},
    "instructor": {"room": "dock", "typeclass": "Instructor", "name": "탐사대 훈련관", "aliases": ["훈련관", "교관"]},
    "maintenance_log": {"room": "office", "typeclass": "MaintenanceLog", "name": "정비기록", "aliases": ["기록"]},
    "supply_cache": {"room": "wreck", "typeclass": "SupplyCache", "name": "보급상자", "aliases": ["상자"]},
    "generator": {"room": "generator", "typeclass": "Generator", "name": "발전기", "aliases": []},
    "pathfinder": {"room": "jungle_edge", "typeclass": "Pathfinder", "name": "선발대 길잡이", "aliases": ["길잡이"]},
    "watch_marker": {"room": "jungle_watch", "typeclass": "WatchMarker", "name": "관측 표식", "aliases": ["표식"]},
    "water_marker": {"room": "jungle_road", "typeclass": "WaterMarker", "name": "수위 표식", "aliases": ["표식"]},
    "signal_device": {"room": "jungle_grove", "typeclass": "SignalDevice", "name": "신호 장치", "aliases": ["장치"]},
    "jungle_cache": {"room": "jungle_fen", "typeclass": "JungleCache", "name": "늪지 보급품", "aliases": ["보급품"]},
}


def content_name(identity):
    """콘텐츠 정의의 실제 이름과 타입으로 대화/임무에서 대상을 표현한다."""
    definition = INTERACTABLES[identity]
    cls = globals()[definition["typeclass"]]
    return ft.token(cls.semantic_role, definition["name"])
