"""character 영역의 명시적 게임 명령."""

from evennia.commands.default.general import CmdLook
from world import presentation as view
from world import rules
from world import text as ft
from world.content import REGIONS, ROOMS

from commands.base import GameCommand


class Look(CmdLook):
    category = "탐사"
    usage = "보기 · 대상 보기"
    summary = "주변과 대상을 살펴봅니다."
    input_style = "target"
    key = "보기"
    aliases = ["look", "l", "둘러보기"]

    def func(self):
        from world.content import ITEMS
        from world.lifecycle import reconcile_room

        name = self.args.strip()
        if name and self.caller.location:
            reconcile_room(self.caller.location)
            normalized = "".join(name.split()).casefold()
            matches = [
                obj
                for obj in self.caller.location.contents
                if normalized
                in ["".join(value.split()).casefold() for value in (obj.key, *obj.aliases.all())]
            ]
            if len(matches) == 1:
                self.caller.msg(self.caller.at_look(matches[0]))
                self.caller.push_state()
                return
            if not matches:
                inventory = self.caller.profile()["inventory"]
                identity = next(
                    (
                        key
                        for key in inventory
                        if inventory[key] > 0
                        and normalized in (key, "".join(ITEMS[key]["name"].split()).casefold())
                    ),
                    None,
                )
                if identity:
                    self.caller.msg(view.item_appearance(identity))
                    self.caller.push_state()
                    return
        super().func()
        self.caller.push_state()


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
