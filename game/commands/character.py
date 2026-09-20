"""character 영역의 명시적 게임 명령."""

from evennia.commands.default.general import CmdLook
from world import rules
from world.content import ITEMS, ROOMS

from commands.base import GameCommand


class Look(CmdLook):
    category = "탐사"
    usage = "보기 · 대상 보기"
    summary = "주변과 대상을 살펴봅니다."
    input_style = "target"
    key = "보기"
    aliases = ["look", "l", "둘러보기"]

    def func(self):
        super().func()
        self.caller.push_state()


class Help(GameCommand):
    category = "탐사"
    usage = "도움말"
    summary = "등록된 명령과 단축어를 확인합니다."
    key = "도움말"
    aliases = ["안내", "?"]

    def run(self):
        from commands.aliases import SHORTCUTS
        from commands.registry import COMMANDS

        lines = ["|g탐사 안내|n", "대상 + 행동 · 이동: 북/남/동/서 · 채팅: 내용 말 또는 '내용"]
        for command in COMMANDS:
            if not getattr(command, "input_style", None):
                continue
            aliases = " / ".join(command.aliases) if command.aliases else ""
            usage = getattr(command, "usage", "") or command.key
            lines.append(
                f"[{getattr(command, 'category', '탐사')}] {usage}: {command.summary}"
                + (f" (별칭: {aliases})" if aliases else "")
            )
        lines.append(
            "단축어: " + " · ".join(f"{key} → {value}" for key, value in SHORTCUTS.items())
        )
        lines.append(
            "일반 적은 그룹 점유, 우두머리는 공동 참여. 경험치·크레딧은 참여자에게, 아이템은 시체에 배정됩니다."
        )
        lines.append(
            "시체 30초 · 전리품 보호 120초 · 적 재생성 45초. 접속 종료 시 교전에서 이탈합니다."
        )
        self.caller.msg("\n".join(lines))


class Status(GameCommand):
    category = "성장"
    usage = "상태"
    summary = "레벨·체력·전투 수치·특성을 확인합니다."
    key = "상태"
    aliases = ["stat", "정보"]

    def run(self):
        profile = self.caller.profile()
        values = rules.stats(profile)
        self.caller.msg(
            f"|g{self.caller.key} · Lv.{values['level']}|n\n"
            f"체력 {profile['hp']}/{values['max_hp']} · 공격 {values['attack']} · 방어 {values['defense']}\n"
            f"특성 {attribute_summary(profile)}\n"
            f"경험치 {profile['xp']} · 크레딧 {profile['credits']} · 처치 {profile['kills']}\n"
            f"무기 {ITEMS[profile['equipment']['weapon']]['name']} · "
            f"방어구 {ITEMS[profile['equipment']['armor']]['name']}"
        )
        self.caller.push_state()


class Quest(GameCommand):
    category = "탐사"
    usage = "임무"
    summary = "개인 임무 진행을 확인합니다."
    key = "임무"
    aliases = ["quest", "퀘스트"]

    def run(self):
        self.caller.msg("|g통신탑 복구|n\n" + self.caller.quest_text(self.caller.profile()))


class Map(GameCommand):
    category = "탐사"
    usage = "지도"
    summary = "방문한 지역과 출구를 확인합니다."
    key = "지도"
    aliases = ["map"]

    def run(self):
        visited = set(self.caller.profile()["visited"])
        lines = ["|g탐사 지도 · 방문한 장소만 표시됩니다.|n"]
        for key, room in ROOMS.items():
            if key in visited:
                mark = " ← 현재" if self.caller.zone == key else ""
                exits = ", ".join(
                    f"{direction}: {ROOMS[target]['name'] if target in visited else '미탐사'}"
                    for direction, target in room["exits"].items()
                )
                lines.append(f"{room['name']}{mark} / {exits}")
        self.caller.msg("\n".join(lines))


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
        from world.progression import ATTRIBUTES, PROFICIENCIES

        profile = self.caller.profile()
        lines = ["[특성]"]
        for key, data in ATTRIBUTES.items():
            entry = profile["attributes"][key]
            lines.append(
                f"{data['name']}: 기본 {entry['base']} + 투자 {entry['allocated']} · {data['description']}"
            )
        lines.append(f"미사용 특성 포인트: {rules.point_pools(profile)['attribute_points']}")
        lines.append("[숙련]")
        lines.extend(
            f"{name}: Rank {rules.proficiency_rank(profile, key)}"
            for key, name in PROFICIENCIES.items()
        )
        self.caller.msg("\n".join(lines))


class Skills(GameCommand):
    key = "기술"
    category = "성장"
    summary = "기술 Rank와 다음 학습 조건·비용을 확인합니다."

    def run(self):
        from world.progression import SKILLS

        profile = self.caller.profile()
        lines = ["[기술]"]
        for key, data in SKILLS.items():
            rank = rules.skill_rank(profile, key)
            next_rank = rank + 1
            cost = (
                f"다음: Lv.{data['requirements'][next_rank]} · 기술점수 {data['point_cost'][next_rank]} · {data['credit_cost'][next_rank]} 크레딧"
                if next_rank <= data["max_rank"]
                else "최고 Rank"
            )
            lines.append(f"{data['name']} Rank {rank} · {data['description']} · {cost}")
        lines.append(f"미사용 기술점수: {rules.point_pools(profile)['skill_points']}")
        lines.append("부두 훈련관: 기술이름 배워 · 기술 재분배 (무료, 기본 Rank 1 유지)")
        self.caller.msg("\n".join(lines))


class Experience(GameCommand):
    key = "경험치"
    category = "성장"
    summary = "캐릭터와 숙련 경험치를 확인합니다."

    def run(self):
        from world.progression import PROFICIENCIES

        profile = self.caller.profile()
        level = rules.level_of(profile)
        remaining = rules.xp_threshold(level + 1) - profile["xp"] if level < rules.MAX_LEVEL else 0
        lines = [f"캐릭터 XP {profile['xp']} · 다음 레벨까지 {remaining}"]
        lines.extend(
            f"{name} 숙련 XP {profile['proficiencies'][key]['xp']} / 200 · Rank {rules.proficiency_rank(profile, key)}"
            for key, name in PROFICIENCIES.items()
        )
        self.caller.msg("\n".join(lines))
