"""Korean commands use the same server-side rules as browser buttons."""

from evennia import Command
from evennia.commands.default.general import CmdLook
from evennia.utils.ansi import strip_ansi
from world import rules
from world.content import ENEMIES, EXCHANGE, ITEMS, ROOMS, SHOP, find_id


class GameCommand(Command):
    help_category = "원시구역"
    input_style = "standalone"

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
    input_style = "target"
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
            "사냥: 대상 공격 · 강타 · 방어 · 회복 · 도주\n"
            "성장: 상태 · 가방 · 장비 · 장비이름 착용\n"
            "보급: 귀환 · 휴식 · 상점 · 물건 구매 · 장비 교환\n"
            "탐험: 임무 · 윤대장 대화 · 대상 조사 · 발전기 수리\n"
            "교류: 내용 말 또는 '내용 · 접속자 · 종료\n\n"
            "첫 탐사: 윤대장 대화 → 북 → 어린청소룡 공격 → 가방 → 강철마체테 착용\n"
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
    input_style = "target"
    key = "착용"
    aliases = ["equip"]

    def run(self):
        item = find_id(ITEMS, self.args.strip())
        if not item:
            raise rules.RuleError("사용법: 강철마체테 착용")
        self.caller.change(lambda profile: rules.equip(profile, item))
        self.caller.msg(f"{ITEMS[item]['name']} 착용 완료.")


class Attack(GameCommand):
    input_style = "target"
    key = "공격"
    aliases = ["사냥", "attack"]

    def run(self):
        name = self.args.strip()
        current = self.caller.combat_target()
        enemy = find_id(ENEMIES, name) if name else current.db.enemy_id if current else None
        if not enemy:
            raise rules.RuleError("사용법: 어린청소룡 공격 · '보기'로 사냥 대상을 확인하세요.")
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
        if self.caller.profile().get("combat_target"):
            self.caller.change(lambda profile: rules.queue_action(profile, "heal"))
            self.caller.msg("다음 차례에 붕대를 사용합니다. 이번 기본 공격을 대신합니다.")
        else:
            amount = self.caller.change(rules.heal)
            self.caller.msg(f"체력 {amount} 회복.")


class Flee(GameCommand):
    key = "도주"
    aliases = ["flee"]

    def run(self):
        if not self.caller.profile().get("combat_target"):
            raise rules.RuleError("진행 중인 교전이 없습니다.")
        self.caller.leave_combat()
        self.caller.msg("교전을 끝냈습니다. 적은 일정 시간 아무도 싸우지 않으면 회복합니다.")


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
        lines.append("붕대 구매 · 강철마체테 구매 · 강화조끼 교환 (한 번에 1개)")
        self.caller.msg("\n".join(lines))


class Buy(GameCommand):
    input_style = "target"
    key = "구매"
    aliases = ["buy"]
    exchange = False

    def run(self):
        self.at_dock()
        item = find_id(ITEMS, self.args.strip())
        if not item:
            raise rules.RuleError("물건 이름을 확인하세요. 예: 붕대 구매")
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
    input_style = "target"
    key = "대화"

    def run(self):
        self.at_dock()
        if self.args.strip().replace(" ", "") not in ("윤대장", "대장"):
            raise rules.RuleError("윤대장 대화")
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
    input_style = "target"
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
    input_style = "target"
    key = "수리"

    def run(self):
        if self.caller.zone != "generator" or self.args.strip().replace(" ", "") != "발전기":
            raise rules.RuleError("발전실에서 '발전기 수리'를 입력하세요.")
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
    input_style = "chat"
    key = "말"
    aliases = ["say"]

    def run(self):
        text = strip_ansi(self.args.strip())
        if not text:
            raise rules.RuleError("내용 말 또는 '내용")
        if len(text) > 300:
            raise rules.RuleError("대화는 300자 이하로 입력하세요.")
        # msg_contents의 템플릿 해석 없이 중괄호와 $You()도 입력 그대로 전달한다.
        message = f"{self.caller.key}: {text.replace('|', '||')}"
        for recipient in self.caller.location.contents:
            recipient.msg(message)


class UnknownCommand(Command):
    key = "__nomatch_command"

    def func(self):
        self.caller.msg(
            "명령을 확인하세요. 대상 뒤에 행동을 입력합니다: 어린청소룡 공격 · 윤대장 대화\n"
            "채팅: 안녕하세요 말 또는 '안녕하세요 · 전체 안내: 도움말"
        )


class PartyCommand(GameCommand):
    key = "파티"

    def run(self):
        from typeclasses.parties import invitation_for, party_for
        from world.multiplayer import object_by_id

        party = party_for(self.caller)
        if party:
            state = party.state()
            names = [object_by_id(key).key for key in state["members"] if object_by_id(key)]
            leader = object_by_id(state["leader"])
            self.caller.msg(
                f"파티장: {leader.key} · 멤버: {', '.join(names)} · 전리품: {state['loot_mode']}"
            )
        else:
            self.caller.msg("소속 파티가 없습니다. 플레이어이름 파티초대로 시작하세요.")
        invited, _ = invitation_for(self.caller)
        if invited:
            self.caller.msg("대기 중인 초대가 있습니다: 파티수락 / 파티거절")


class PartyInvite(GameCommand):
    key = "파티초대"
    input_style = "target"

    def run(self):
        from evennia.objects.models import ObjectDB
        from typeclasses.parties import invite

        target = ObjectDB.objects.filter(
            db_key__iexact=self.args.strip(), db_typeclass_path="typeclasses.explorers.Explorer"
        ).first()
        invite(self.caller, target)
        self.caller.msg("파티 초대를 보냈습니다.")


class PartyAccept(GameCommand):
    key = "파티수락"
    accept = True

    def run(self):
        from typeclasses.parties import respond

        respond(self.caller, self.accept)
        self.caller.msg("파티에 가입했습니다." if self.accept else "파티 초대를 거절했습니다.")


class PartyReject(PartyAccept):
    key = "파티거절"
    accept = False


class PartyLeave(GameCommand):
    key = "파티탈퇴"

    def run(self):
        from typeclasses.parties import party_for

        party = party_for(self.caller)
        if not party:
            raise rules.RuleError("소속 파티가 없습니다.")
        party.remove_member(self.caller)
        self.caller.msg("파티를 탈퇴했습니다.")


class PartyKick(GameCommand):
    key = "파티제외"
    input_style = "target"
    transfer = False

    def run(self):
        from typeclasses.parties import party_for
        from world.multiplayer import object_by_id

        party = party_for(self.caller)
        if not party:
            raise rules.RuleError("소속 파티가 없습니다.")
        target = next(
            (
                object_by_id(key)
                for key in party.state()["members"]
                if object_by_id(key)
                and object_by_id(key).key.casefold() == self.args.strip().casefold()
            ),
            None,
        )
        if not target:
            raise rules.RuleError("파티 멤버를 지정하세요.")
        if self.transfer:
            party.transfer(self.caller, target)
        else:
            party.remove_member(self.caller, target)
        self.caller.msg("파티 구성을 변경했습니다.")


class PartyTransfer(PartyKick):
    key = "파티장위임"
    transfer = True


class Take(GameCommand):
    key = "가져"
    input_style = "target"

    def run(self):
        from typeclasses.loot import take_loot
        from world.lifecycle import reconcile_room

        reconcile_room(self.caller.location)

        text = self.args.strip()
        corpse = text.startswith("시체에서 ")
        if corpse:
            text = text[len("시체에서 ") :].strip()
        item = None if text == "모두" else find_id(ITEMS, text)
        if text != "모두" and not item:
            raise rules.RuleError(
                "시체에서 모두 가져 · 시체에서 강화 조끼 가져 · 모두 가져 · 회수 부품 가져"
            )
        take_loot(self.caller, item, corpse=corpse)


class PartyLootMode(GameCommand):
    key = "파티분배"
    input_style = "target"

    def run(self):
        from typeclasses.parties import party_for
        from world.multiplayer import world_change

        with world_change():
            party = party_for(self.caller)
            if not party:
                raise rules.RuleError("소속 파티가 없습니다.")
            party.require_leader(self.caller)
            if self.args.strip() not in ("순번", "round_robin"):
                raise rules.RuleError("현재 지원하는 전리품 방식: 순번 파티분배")
            state = party.state()
            state["loot_mode"] = "round_robin"
            party.db.state = state
        self.caller.msg("전리품을 참여자 순번으로 배분합니다.")


COMMANDS = [
    Take,
    PartyLootMode,
    PartyCommand,
    PartyInvite,
    PartyAccept,
    PartyReject,
    PartyLeave,
    PartyKick,
    PartyTransfer,
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
    UnknownCommand,
]
