"""Korean commands use the same server-side rules as browser buttons."""

from evennia import Command
from evennia.commands.default.general import CmdLook
from evennia.utils.ansi import strip_ansi
from world import rules
from world.content import ENEMIES, EXCHANGE, ITEMS, ROOMS, SHOP, find_id


class GameCommand(Command):
    help_category = "원시구역"

    def func(self):
        try:
            self.run()
        except rules.RuleError as error:
            self.caller.msg(f"|y{error}|n")

    def peaceful(self):
        rules.require_peace(self.caller.profile())

    def at_dock(self):
        self.peaceful()
        if self.caller.zone != "dock":
            raise rules.RuleError("부두에서만 이용할 수 있습니다. '귀환'으로 돌아가세요.")


class Look(CmdLook):
    key = "보기"
    aliases = ["look", "l", "둘러보기"]

    def func(self):
        super().func()
        self.caller.push_state()


class Help(GameCommand):
    key = "도움말"
    aliases = ["안내", "?"]

    def run(self):
        self.caller.msg(
            "|g탐사 안내|n\n"
            "이동: 북/남/동/서 (n/s/e/w) · 보기 · 지도\n"
            "사냥: 공격 대상 · 강타 · 방어 · 회복 · 도주\n"
            "성장: 상태 · 가방 · 장비 · 착용 장비이름\n"
            "보급: 귀환 · 휴식 · 상점 · 구매 물건 · 교환 장비\n"
            "탐험: 임무 · 대화 윤대장 · 조사 대상 · 수리 발전기\n"
            "교류: 말 내용 · 접속자 · 종료\n\n"
            "첫 탐사: 대화 윤대장 → 북 → 공격 어린청소룡 → 가방 → 착용 강철마체테\n"
            "전투 중 강타·방어·회복은 다음 차례에 실행됩니다. 반복 입력해도 공격 속도는 늘지 않습니다.\n"
            "개인 교전은 접속 종료 시 멈추며, 재접속 후 '공격'으로 이어갑니다."
        )


class Status(GameCommand):
    key = "상태"
    aliases = ["stat", "정보"]

    def run(self):
        profile = self.caller.profile()
        values = rules.stats(profile)
        self.caller.msg(
            f"|g{self.caller.key} · Lv.{values['level']}|n\n"
            f"체력 {profile['hp']}/{values['max_hp']} · 공격 {values['attack']} · 방어 {values['defense']}\n"
            f"경험치 {profile['xp']} · 크레딧 {profile['credits']} · 처치 {profile['kills']}\n"
            f"무기 {ITEMS[profile['equipment']['weapon']]['name']} · "
            f"방어구 {ITEMS[profile['equipment']['armor']]['name']}"
        )
        self.caller.push_state()


class Inventory(GameCommand):
    key = "가방"
    aliases = ["i", "인벤토리", "장비"]

    def run(self):
        profile = self.caller.profile()
        lines = ["|g소지품|n"]
        for key, count in profile["inventory"].items():
            item = ITEMS[key]
            equipped = " [착용]" if key in profile["equipment"].values() else ""
            bonus = (
                f" 공격 +{item.get('attack', 0)} / 방어 +{item.get('defense', 0)}"
                if item["slot"] in ("weapon", "armor")
                else ""
            )
            lines.append(f"{item['name']} ×{count}{equipped}{bonus}")
        self.caller.msg("\n".join(lines))


class Equip(GameCommand):
    key = "착용"
    aliases = ["equip"]

    def run(self):
        item = find_id(ITEMS, self.args.strip())
        if not item:
            raise rules.RuleError("사용법: 착용 강철마체테")
        self.caller.change(lambda profile: rules.equip(profile, item))
        self.caller.msg(f"{ITEMS[item]['name']} 착용 완료.")


class Attack(GameCommand):
    key = "공격"
    aliases = ["사냥", "attack"]

    def run(self):
        name = self.args.strip()
        current = self.caller.profile()["encounter"]
        enemy = find_id(ENEMIES, name) if name else current["enemy"] if current else None
        if not enemy:
            raise rules.RuleError("사용법: 공격 어린청소룡 · '보기'로 사냥 대상을 확인하세요.")
        self.caller.start_combat(enemy)


class Heavy(GameCommand):
    key = "강타"
    aliases = ["heavy"]
    action = "heavy"

    def run(self):
        self.caller.change(lambda profile: rules.queue_action(profile, self.action))
        self.caller.msg(f"다음 차례에 {self.key}합니다.")


class Guard(Heavy):
    key = "방어"
    aliases = ["guard"]
    action = "guard"


class Heal(GameCommand):
    key = "회복"
    aliases = ["붕대", "heal"]

    def run(self):
        if self.caller.profile()["encounter"]:
            self.caller.change(lambda profile: rules.queue_action(profile, "heal"))
            self.caller.msg("다음 차례에 붕대를 사용합니다. 이번 기본 공격을 대신합니다.")
        else:
            amount = self.caller.change(rules.heal)
            self.caller.msg(f"체력 {amount} 회복.")


class Flee(GameCommand):
    key = "도주"
    aliases = ["flee"]

    def run(self):
        if not self.caller.profile()["encounter"]:
            raise rules.RuleError("진행 중인 교전이 없습니다.")
        self.caller.stop_combat_timer()
        self.caller.change(lambda profile: profile.update(encounter=None))
        self.caller.msg("교전을 끝냈습니다. 보상은 없으며, 다음 교전은 처음부터 시작합니다.")


class Return(GameCommand):
    key = "귀환"
    aliases = ["home"]

    def run(self):
        from world.bootstrap import get_room

        self.peaceful()
        self.caller.move_to(get_room("dock"), quiet=True)


class Rest(GameCommand):
    key = "휴식"
    aliases = ["rest"]

    def run(self):
        self.at_dock()
        self.caller.change(lambda profile: profile.update(hp=rules.stats(profile)["max_hp"]))
        self.caller.msg("부두 의무실에서 체력을 모두 회복했습니다.")


class Shop(GameCommand):
    key = "상점"
    aliases = ["shop"]

    def run(self):
        self.at_dock()
        lines = ["|g부두 보급소|n"]
        for key, price in SHOP.items():
            exchange = f" / 회수부품 {EXCHANGE[key]}개" if key in EXCHANGE else ""
            lines.append(f"{ITEMS[key]['name']}: {price} 크레딧{exchange}")
        lines.append("구매 붕대 · 구매 강철마체테 · 교환 강화조끼 (한 번에 1개)")
        self.caller.msg("\n".join(lines))


class Buy(GameCommand):
    key = "구매"
    aliases = ["buy"]
    exchange = False

    def run(self):
        self.at_dock()
        item = find_id(ITEMS, self.args.strip())
        if not item:
            raise rules.RuleError("물건 이름을 확인하세요. 예: 구매 붕대")
        self.caller.change(lambda profile: rules.buy(profile, item, exchange=self.exchange))
        self.caller.msg(f"{ITEMS[item]['name']} 1개를 받았습니다.")


class Exchange(Buy):
    key = "교환"
    aliases = ["exchange"]
    exchange = True


class Quest(GameCommand):
    key = "임무"
    aliases = ["quest", "퀘스트"]

    def run(self):
        self.caller.msg("|g통신탑 복구|n\n" + self.caller.quest_text(self.caller.profile()))


class Talk(GameCommand):
    key = "대화"

    def run(self):
        self.at_dock()
        if self.args.strip().replace(" ", "") not in ("윤대장", "대장"):
            raise rules.RuleError("대화 윤대장")
        profile = self.caller.profile()
        if not profile["quest_started"]:
            self.caller.change(lambda data: data.update(quest_started=True))
            self.caller.msg(
                "윤대장: 장비를 마련하고 관리동의 정비기록을 찾아보게. "
                "발전기를 복구하고 능선의 우두머리를 처치하면 통신탑을 되찾을 수 있네."
            )
        elif profile["boss_defeated"] and not profile["quest_claimed"]:
            self.caller.change(rules.claim_quest)
            self.caller.msg(
                "|g첫 탐사 완료!|n 경험치 +100 · 크레딧 +100 · 붕대 +3\n"
                "통신탑에서 구조 신호가 퍼져 나간다. 자유롭게 사냥과 장비 수집을 계속할 수 있습니다."
            )
        else:
            self.caller.msg(self.caller.quest_text(profile))


class Investigate(GameCommand):
    key = "조사"

    def run(self):
        self.peaceful()
        target = self.args.strip().replace(" ", "")
        profile = self.caller.profile()
        if self.caller.zone == "office" and target in ("정비기록", "기록"):
            self.caller.change(lambda data: data.update(record_read=True))
            self.caller.msg(
                "정비기록: 회수부품 3개로 발전기를 수리하면 능선의 문을 열 수 있다.\n"
                "현장 메모: 우두머리가 몸을 낮추면 다음 차례에는 방어할 것."
            )
        elif self.caller.zone == "wreck" and target in ("보급상자", "상자"):
            if profile["cache_claimed"]:
                raise rules.RuleError("이미 보급품을 챙겼습니다.")
            rules.add_item(profile, "bandage", 2)
            profile["cache_claimed"] = True
            self.caller.save_profile(profile)
            self.caller.msg("보급상자에서 붕대 2개를 찾았습니다.")
        else:
            raise rules.RuleError("특별한 단서를 찾지 못했습니다. 방 설명과 안내를 확인하세요.")


class Repair(GameCommand):
    key = "수리"

    def run(self):
        if self.caller.zone != "generator" or self.args.strip() != "발전기":
            raise rules.RuleError("발전실에서 '수리 발전기'를 입력하세요.")
        self.caller.change(rules.fix_generator)
        self.caller.msg("발전기가 돌아갑니다! 경험치 +50. 능선 진입문이 열렸습니다.")


class Map(GameCommand):
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


class Say(GameCommand):
    key = "말"
    aliases = ["say"]

    def run(self):
        text = strip_ansi(self.args.strip()).replace("|", "||")
        if not text:
            raise rules.RuleError("말 내용")
        if len(text) > 300:
            raise rules.RuleError("대화는 300자 이하로 입력하세요.")
        self.caller.location.msg_contents(f"{self.caller.key}: {text}")


COMMANDS = [
    Look,
    Help,
    Status,
    Inventory,
    Equip,
    Attack,
    Heavy,
    Guard,
    Heal,
    Flee,
    Return,
    Rest,
    Shop,
    Buy,
    Exchange,
    Quest,
    Talk,
    Investigate,
    Repair,
    Map,
    Say,
]
