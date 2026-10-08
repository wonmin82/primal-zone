"""character 영역의 명시적 게임 명령."""

from time import time

from evennia.commands.default.general import CmdLook
from world import presentation as view
from world import rules
from world import text as ft
from world.content import REGIONS, ROOMS, ordered_directions

from commands.base import GameCommand


class Look(CmdLook):
    category = "이동·탐사"
    usage = "보기 · 대상 보기 · 대상 봐 · 대상 2 보기 · 대상 모두 보기 · 시체 모두 보기 · 북 보기 · 북동 보기 · 북 봐"
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
        from world.content.economy import CURRENCY
        from world.currency import is_currency

        if is_currency(name):
            self.caller.msg(ft.compact(CURRENCY["name"], CURRENCY["description"]))
            return
        if name and self.caller.location:
            from world.navigation import blocked_exit_message

            message = blocked_exit_message(self.caller.zone, name)
            if message:
                self.caller.msg(ft.text(message))
                return
            # 실제 Exit도 같은 selector로 선택한다. 관찰만 할 때는 로컬 갱신/at_desc도 실행하지 않는다.
            from world.targets import matching, ordered, visible

            objects = ordered(obj for obj in self.caller.location.exits if visible(obj, self.caller))

            try:
                selector = parse_selector(name, [n for obj in objects for n in names(obj)])
            except rules.RuleError:
                selector = None  # 소지품의 실제 이름도 포함하는 기존 보기 경로에서 검증한다.
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
            objects = room_objects(self.caller, observed_at=observed_at)
            profile = self.caller.profile_snapshot()
            inventory = {
                key: ITEMS[key]
                for key, count in profile["inventory"].items()
                if count > 0
            }
            try:
                selector = parse_selector(
                    name,
                    [n for obj in objects for n in names(obj)]
                    + [n for key, data in inventory.items() for n in (key, data["name"])],
                )
                if matching(objects, selector):
                    selected = resolve(objects, selector, self.caller, observed_at=observed_at)
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
                    from world.equipment_service import (
                        entity_runtime,
                        resolve_item,
                        selector_label,
                        state_summary,
                    )

                    if entity_runtime(self.caller):
                        from world.lighting_service import status as light_status

                        item = resolve_item(self.caller, name, "보기")
                        identity = item.definition_id
                        detail = light_status(self.caller, item, observed_at) if ITEMS[identity].get("light_source") else state_summary(item)
                        self.caller.msg(ft.compact(ft.token("item", selector_label(self.caller, item)),
                                                   ITEMS[identity].get("description", "탐사 중 사용하는 물품이다."),
                                                   detail, ITEMS[identity].get("firearm_family", "")))
                        self.caller.push_state(observed_at=observed_at)
                        return
                    identity = item_selector(name, inventory, "보기")
                    from world import lighting

                    status = lighting.status(profile, identity, observed_at) if ITEMS[identity].get("light_source") else None
                    self.caller.msg(view.item_appearance(identity, light_status=status))
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
    category = "이동·탐사"
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
            f"{weather_label} · {values['light']['name']} · 환경 시야 {values['visibility']['name']}",
        ]
        if environment.period == "night":
            lines.append(values["moon"]["name"])
        from world import lighting
        from world.content.environment import VISIBILITIES
        from world.observation import context_for

        context = context_for(self.caller, observed_at=observed_at, environment=environment)
        sight = context.snapshot
        for light in context.lights.items:
            lines.extend(["", ft.token("item", light.label), lighting.snapshot_status(light)])
        lines.append(f"현재 시야 {VISIBILITIES[sight.effective_visibility]}")
        self.caller.msg(ft.compact(ft.token("title", "환경"), *lines))
        self.caller.push_state(observed_at=observed_at)


class Help(GameCommand):
    category = "편의"
    usage = "도움말 · 명령이름 도움말"
    summary = "분류별 명령과 개별 명령의 사용법·별칭을 확인합니다."
    input_style = "target"
    key = "도움말"
    aliases = ["안내", "?"]

    def run(self):
        from commands.help_pages import help_page, root_page
        from commands.registry import COMMANDS, HELP_ONLY_COMMANDS

        commands = [cls for cls in (*COMMANDS, *HELP_ONLY_COMMANDS) if getattr(cls, "input_style", None)]
        query = (getattr(self, "args", "") or "").strip()
        page = help_page(query, commands) if query else root_page()
        if page is None:
            raise rules.RuleError("등록된 명령을 찾을 수 없습니다. '도움말'에서 확인하세요.")
        self.caller.msg(page)


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
    category = "이동·탐사"
    usage = "임무"
    summary = "개인 임무 진행을 확인합니다."
    key = "임무"
    aliases = ["quest", "퀘스트"]

    def run(self):
        self.caller.msg(view.quest(self.caller.profile()))


class Map(GameCommand):
    category = "이동·탐사"
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
                directions = ordered_directions([*room["exits"], *room.get("blocked_exits", {})])
                exits = ft.join(
                    [
                        ft.text(
                            ft.token("direction", direction),
                            ": ",
                            "폐쇄" if direction not in room["exits"] else (
                                ROOMS[room["exits"][direction]]["name"]
                                if room["exits"][direction] in visited else "미탐사"
                            ),
                        )
                        for direction in directions
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
    summary = "네 특성의 현재 값과 남은 투자 포인트를 확인합니다."

    def run(self):
        self.caller.msg(view.abilities(self.caller.profile()))


class Skills(GameCommand):
    key = "기술"
    category = "성장"
    summary = "8개 기술의 Rank와 남은 기술 훈련을 확인합니다."

    def run(self):
        self.caller.msg(view.skills(self.caller.profile()))


class Experience(GameCommand):
    key = "경험치"
    category = "성장"
    summary = "현재 레벨의 경험치 진행과 다음 레벨의 훈련·특성 획득량을 확인합니다."

    def run(self):
        self.caller.msg(view.experience(self.caller.profile()))


class GlobalShortcuts(GameCommand):
    key = "단축어"
    category = "편의"
    usage = "단축어"
    summary = "게임의 고정 글로벌 단축어를 확인합니다. 개인 설정은 줄임말로 관리합니다."

    def run(self):
        from commands.help_pages import shortcut_page

        self.caller.msg(shortcut_page())
