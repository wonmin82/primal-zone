"""character 영역의 명시적 게임 명령."""

from time import time

from evennia.commands.default.general import CmdLook
from world import presentation as view
from world import rules
from world import text as ft
from world.content import REGIONS, ROOMS

from commands.base import GameCommand


class Look(CmdLook):
    category = "탐사"
    usage = "보기 · 대상 보기 · 대상 봐 · 대상 2 보기 · 대상 모두 보기 · 시체 모두 보기 · 북 보기 · 북 봐"
    summary = "주변과 대상을 살펴봅니다. 방향을 보면 이동 없이 인접 장소의 존재만 관찰합니다."
    input_style = "target"
    key = "보기"
    aliases = ["look", "l", "둘러보기", "봐"]

    def func(self):
        from typeclasses.exits import Exit
        from typeclasses.loot import Corpse
        from world.content import ITEMS
        from world.lifecycle import reconcile_room
        from world.target_presentation import corpse_overview
        from world.targets import Mode, item_selector, names, parse_selector, resolve, room_objects

        name = self.args.strip()
        observed_at = time()
        if name and self.caller.location:
            # 실제 Exit도 같은 selector로 선택한다. 관찰만 할 때는 로컬 갱신/at_desc도 실행하지 않는다.
            objects = room_objects(self.caller)
            from world.targets import matching

            try:
                selector = parse_selector(name, [n for obj in objects for n in names(obj)])
            except rules.RuleError:
                selector = None  # 가방의 실제 이름도 포함하는 기존 보기 경로에서 검증한다.
            candidates = matching(objects, selector) if selector else []
            if candidates and all(isinstance(obj, Exit) for obj in candidates):
                try:
                    selected = resolve(objects, selector, self.caller)
                    self.caller.msg(
                        ft.join(
                            [obj.return_appearance(self.caller, observed_at=observed_at) for obj in selected],
                            "\n\n",
                        )
                    )
                except rules.RuleError as error:
                    self.caller.msg(ft.token("error", str(error)))
                return
            reconcile_room(self.caller.location, observed_at)
            objects = room_objects(self.caller)
            inventory = {
                key: ITEMS[key]
                for key, count in self.caller.profile_snapshot()["inventory"].items()
                if count > 0
            }
            try:
                selector = parse_selector(
                    name,
                    [n for obj in objects for n in names(obj)]
                    + [n for key, data in inventory.items() for n in (key, data["name"])],
                )
                if matching(objects, selector):
                    selected = resolve(objects, selector, self.caller)
                    if selector.mode == Mode.ALL and all(
                        isinstance(obj, Corpse) for obj in selected
                    ):
                        output = corpse_overview(
                            selected,
                            self.caller,
                            observed_at,
                            pool=[obj for obj in objects if isinstance(obj, Corpse)],
                        )
                    else:
                        output = ft.join(
                            [self.caller.at_look(obj, observed_at=observed_at) for obj in selected],
                            "\n\n",
                        )
                    self.caller.msg(output)
                else:
                    identity = item_selector(name, inventory, "보기")
                    self.caller.msg(view.item_appearance(identity))
            except rules.RuleError as error:
                self.caller.msg(ft.token("error", str(error)))
                self.caller.push_state(observed_at=observed_at)
                return
            self.caller.push_state(observed_at=observed_at)
            return
        if self.caller.location:
            self.caller.msg(self.caller.at_look(self.caller.location, observed_at=observed_at))
        else:
            super().func()
        self.caller.push_state(observed_at=observed_at)


class Weather(GameCommand):
    category = "탐사"
    usage = "날씨 · 환경"
    summary = "현재 장소의 게임 시각·날씨·달·밝기와 계산된 시야 상태를 확인합니다."
    key = "날씨"
    aliases = ["환경"]

    def func(self):
        from world.environment import display
        from world.environment_state import snapshot_for

        observed_at = time()
        environment = snapshot_for(self.caller.location, observed_at)
        if environment is None:
            self.caller.msg("이곳의 환경은 아직 확인할 수 없다.")
            return
        values = display(environment)
        weather_label = ("바깥 날씨: " if environment.exposure == "indoor" else "") + values["weather"]["name"]
        lines = [
            f"{environment.game_day}일 {values['time']} · {values['period']['name']}",
            f"{weather_label} · {values['light']['name']} · 시야 {values['visibility']['name']}",
        ]
        if environment.period == "night":
            lines.append(values["moon"]["name"])
        self.caller.msg(ft.compact(ft.token("title", "환경"), *lines))
        self.caller.push_state(observed_at=observed_at)


class Help(GameCommand):
    category = "탐사"
    usage = "도움말 · 명령이름 도움말"
    summary = "분류별 명령과 개별 명령의 사용법·별칭을 확인합니다."
    input_style = "target"
    key = "도움말"
    aliases = ["안내", "?"]

    def run(self):
        from world.progression import ATTRIBUTES

        from commands.aliases import SHORTCUTS
        from commands.registry import COMMANDS

        commands = [cls for cls in COMMANDS if getattr(cls, "input_style", None)]
        query = (getattr(self, "args", "") or "").strip().casefold()
        if query:
            query = SHORTCUTS.get(query, query)
            selected = next(
                (
                    cls
                    for cls in commands
                    if query in {str(name).casefold() for name in (cls.key, *cls.aliases)}
                ),
                None,
            )
            if not selected:
                raise rules.RuleError("등록된 명령을 찾을 수 없습니다. '도움말'에서 확인하세요.")
            lines = [selected.summary]
            lines.append(
                ft.text(
                    "사용법: ",
                    ft.usage(
                        getattr(selected, "usage", "") or selected.key,
                        {selected.key, *selected.aliases},
                    ),
                )
            )
            aliases = [*selected.aliases, *[k for k, v in SHORTCUTS.items() if v == selected.key]]
            if aliases:
                lines.append(
                    ft.text("별칭: ", ft.join([ft.token("command", a) for a in aliases], " / "))
                )
            if selected is Abilities:
                lines.extend(
                    f"{data['name']} | {data['description']}" for data in ATTRIBUTES.values()
                )
            self.caller.msg(ft.compact(ft.token("command", selected.key), *lines))
            return
        groups = {}
        for cls in commands:
            groups.setdefault(getattr(cls, "category", "탐사"), []).append(
                ft.token("command", cls.key)
            )
        lines = [
            ft.text(category, " | ", ft.join(entries, " · "))
            for category, entries in groups.items()
        ]
        lines.extend(
            [
                ft.text("상세: 명령이름 ", ft.token("command", "도움말")),
                ft.text("대상: 대상이름 ", ft.token("command", "보기")),
                "대상 + 행동 · 채팅: 내용 말 또는 '내용",
                "번호 없이 기본 하나, 대상 2로 두 번째, 대상 모두로 같은 종류 전부를 지정한다.",
                "보기·가져는 모두 선택 가능. 공격·대화·조사·수리·무장·착용은 하나만 지정한다.",
                ft.usage(
                    "갈퀴사냥룡 2 공격 · 갈퀴사냥룡 모두 보기 · 시체 모두 보기 · 시체에서 회수부품 모두 가져 · 시체 2에서 모두 가져 · 모든 시체에서 회수부품 모두 가져",
                    {"공격", "보기", "가져"},
                ),
                "모두 가져는 전리품 모두 가져의 축약이다. 여러 출처는 '모든 시체에서'로 지정한다.",
                "가방·보관 아이템은 스택이다. 버려·줘·넣어·꺼내는 하나 또는 모두를 옮기며 장착분과 임무 핵심 물건은 남긴다.",
                "에게(플레이어) · 에(보관함) · 에서(보관함)로 출처/목적지를 지정한다. 사용법은 개별 명령 도움말에서 확인한다.",
                ft.text(
                    "단축어: ",
                    ft.join(
                        [
                            ft.text(ft.token("command", k), "→", ft.token("command", v))
                            for k, v in SHORTCUTS.items()
                        ],
                        " · ",
                    ),
                ),
            ]
        )
        self.caller.msg(ft.compact("도움말", *lines))


class Status(GameCommand):
    category = "성장"
    usage = "상태"
    summary = "레벨·체력·전투 수치·특성을 확인합니다."
    key = "상태"
    aliases = ["stat", "정보"]

    def run(self):
        self.caller.msg(view.status(self.caller.key, self.caller.profile()))
        self.caller.push_state()


class Quest(GameCommand):
    category = "탐사"
    usage = "임무"
    summary = "개인 임무 진행을 확인합니다."
    key = "임무"
    aliases = ["quest", "퀘스트"]

    def run(self):
        self.caller.msg(view.quest(self.caller.profile()))


class Map(GameCommand):
    category = "탐사"
    usage = "지도"
    summary = "방문한 지역과 출구를 확인합니다."
    key = "지도"
    aliases = ["map"]

    def run(self):
        visited = set(self.caller.profile()["visited"])
        lines = ["방문한 장소만 표시됩니다.", ""]
        for region in REGIONS.values():
            region_rooms = [key for key in region["rooms"] if key in visited]
            if not region_rooms:
                continue
            lines.append(f"[{region['name']}]")
            for key in region_rooms:
                room = ROOMS[key]
                mark = " ← 현재" if self.caller.zone == key else ""
                exits = ft.join(
                    [
                        ft.text(
                            ft.token("direction", direction),
                            ": ",
                            ROOMS[target]["name"] if target in visited else "미탐사",
                        )
                        for direction, target in room["exits"].items()
                    ],
                    ", ",
                )
                lines.append(ft.text(room["name"], mark, " / ", exits))
        self.caller.msg(ft.sheet("탐사 지도", *lines))


def attribute_summary(profile):
    from world.progression import ATTRIBUTES

    return " · ".join(
        f"{data['name']} {profile['attributes'][key]['base'] + rules.allocated(profile, key)}"
        for key, data in ATTRIBUTES.items()
    )


class Abilities(GameCommand):
    key = "능력"
    category = "성장"
    summary = "기본 특성과 투자 포인트, 실제 행동으로 쌓은 숙련을 확인합니다."

    def run(self):
        self.caller.msg(view.abilities(self.caller.profile()))


class Skills(GameCommand):
    key = "기술"
    category = "성장"
    summary = "기술 Rank와 다음 학습 조건·비용을 확인합니다."

    def run(self):
        self.caller.msg(view.skills(self.caller.profile()))


class Experience(GameCommand):
    key = "경험치"
    category = "성장"
    summary = "캐릭터와 숙련 경험치를 확인합니다."

    def run(self):
        self.caller.msg(view.experience(self.caller.profile()))
