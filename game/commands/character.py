"""character 영역의 명시적 게임 명령."""

from time import time

from evennia.commands.default.general import CmdLook
from world import presentation as view
from world import rules
from world import text as ft
from world.content import REGIONS, ROOMS

from commands.base import GameCommand
from commands.help_contracts import command_sections


class Look(CmdLook):
    help_sections = command_sections('봐')
    category = "이동·탐사"
    usage = "봐 · 대상 봐 · 대상 2 봐 · 대상 모두 봐 · 시체 모두 봐 · 북 봐 · 북동 봐"
    summary = "주변과 대상을 살펴봅니다. 방향을 보면 이동 없이 인접 장소의 존재만 관찰합니다."
    input_style = "target"
    key = "봐"
    aliases = ["본", "보", "`"]

    def func(self):
        from world.actions.global_actions import invoke

        return invoke(self.caller, self.session, "look", query=self.args)


class Exits(GameCommand):
    help_sections = command_sections('출구')
    category = "이동·탐사"
    usage = "출구"
    summary = "실제 출구와 목적지의 공개 가능한 이름, 현재 이동 제한을 조회합니다. 전투 중에도 사용할 수 있습니다."
    key = "출구"
    aliases = ["exits"]
    read_only = True

    def func(self):
        from world.exit_presentation import exits_sheet

        self.caller.msg(exits_sheet(self.caller, time()))


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
    help_sections = command_sections('도움')
    category = "편의"
    usage = "도움 · 명령이름 도움"
    summary = "분류별 명령과 개별 명령의 사용법·별칭을 확인합니다."
    input_style = "target"
    key = "도움"
    aliases = ["도움말"]

    def func(self):
        from world.actions.global_actions import invoke

        return invoke(self.caller, self.session, "help", query=getattr(self, "args", "") or "")


class Status(GameCommand):
    help_sections = command_sections('점수')
    category = "성장"
    usage = "점수"
    summary = "레벨·체력·전투 수치·특성을 확인합니다."
    key = "점수"
    aliases = ["상태", "상", "점"]

    def func(self):
        from world.actions.global_actions import invoke

        return invoke(self.caller, self.session, "status")


class Quest(GameCommand):
    category = "이동·탐사"
    usage = "임무"
    summary = "개인 임무 진행을 확인합니다."
    key = "임무"
    aliases = ["quest", "퀘스트"]

    def run(self):
        self.caller.msg(view.quest(self.caller.profile()))


class Map(GameCommand):
    help_sections = command_sections('지도')
    category = "이동·탐사"
    usage = "지도 · 지도 근처 · 지도 전체 · 지도 목록 · 지도 <지도명> · 지도 중심 <방문 장소> · 지도 ascii · 지도 도움말"
    summary = "공개 가능한 방문 장소의 연결을 문자 지도로 확인합니다."
    input_style = "prefix"
    key = "지도"
    aliases = ["지"]

    def func(self):
        # 명령 출력과 자연회복은 기존 dispatcher가 처리한다. 조회는 전역 갱신을 예약하지 않는다.
        query = self.args.strip()
        if query == "목록":
            try:
                self.show_list()
            except rules.RuleError as error:
                self.caller.msg(ft.text(ft.token("error", str(error)), kind="error"))
            return
        from world.map_commands import map_text

        result = map_text(self.caller, query)
        for message in result if isinstance(result, list) else (result,):
            self.caller.msg(message)

    def show_list(self):
        visited = set(self.caller.profile_snapshot()["visited"])
        lines = ["방문한 장소만 표시됩니다.", ""]
        for region in REGIONS.values():
            region_rooms = [key for key in region["rooms"] if key in visited]
            if not region_rooms:
                continue
            lines.append(f"[{region['name']}]")
            for key in region_rooms:
                room = ROOMS[key]
                mark = " ← 현재" if self.caller.zone == key else ""
                from world.bootstrap import get_room
                from world.exit_presentation import exit_entries

                actual_room = get_room(key)
                entries = exit_entries(self.caller, actual_room, reveal_observed=False) if actual_room else []
                exits = ft.join(
                    [ft.text(ft.token("direction", entry["name"]), ": ",
                             entry["destination_name"] if entry["exists"] else "폐쇄")
                     for entry in entries], ", ")
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
    help_sections = command_sections('경험치')
    aliases = ["경"]
    key = "경험치"
    category = "성장"
    summary = "현재 레벨의 경험치 진행과 다음 레벨의 훈련·특성 획득량을 확인합니다."

    def run(self):
        self.caller.msg(view.experience(self.caller.profile()))


class GlobalShortcuts(GameCommand):
    key = "단축어"
    category = "편의"
    usage = "단축어"
    summary = "게임에서 기본 제공하는 고정 단축어를 확인합니다."
    help_sections = (
        ("사용법", ("단축어", "전역 줄임말")),
        ("예시", ("상 → 점수", "장 → 장비", "ㅇ → 위", "아 → 아래", "시 → 시체에서 모두 가져", "시2 → 시체 2에서 모두 가져")),
        ("실행 규칙", (
            "고정 단축어는 정확하게 일치하는 입력에 적용하며 한 번만 변환합니다.",
            "고정 단축어는 개인 줄임말보다 우선합니다.",
            "단축어와 전역 줄임말은 같은 기본 단축어 목록을 보여줍니다.",
        )),
        ("제한", (
            "사용자가 고정 단축어를 등록·수정·삭제할 수 없습니다.",
            "고정 단축어와 충돌하는 이름으로 개인 줄임말을 등록할 수 없습니다.",
        )),
        ("관련 도움말", ("줄임말 도움", "해 도움")),
    )

    def run(self):
        from commands.help_pages import shortcut_page

        self.caller.msg(shortcut_page())
