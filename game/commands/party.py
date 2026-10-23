"""party 영역의 명시적 게임 명령."""

from world import rules
from world import text as ft
from world.targets import matching, names, ordered, parse_selector, require_single, strict_single

from commands.base import GameCommand


class PartyCommand(GameCommand):
    category = "일행·교류"
    usage = "일행"
    summary = "리더·멤버·초대를 확인합니다."
    key = "일행"

    def run(self):
        from typeclasses.parties import invitation_for, online, party_for, request_for
        from world.multiplayer import object_by_id

        party = party_for(self.caller)
        lines = []
        if party:
            state = party.state()
            leader = object_by_id(state["leader"])
            summary = ft.text(
                "리더 ",
                ft.token("player", leader.key if leader else "없음"),
                " (온라인)" if online(leader) else " (오프라인·일행승계 가능)",
                " · 전리품 ",
                "순번" if state["loot_mode"] == "round_robin" else state["loot_mode"],
            )
            members = []
            for identity in state["members"]:
                member = object_by_id(identity)
                if member:
                    members.append(
                        ft.text(
                            ft.token("player", member.key),
                            "(장)" if identity == state["leader"] else "",
                        )
                    )
            lines.append(ft.text("멤버: ", ft.join(members, " · ")))
            defender = object_by_id(state["tactics"].get("defender_id"))
            lines.append(ft.text("방어 담당: ", ft.token("player", defender.key) if defender else "없음", " · 지정은 전투 밖에서도 유지"))
            lines.append(ft.text("대기 초청 ", str(len(state["invitations"])), " · 가입 요청 ", str(len(state["join_requests"]))))
        else:
            summary = ft.text("소속 일행 없음 · 플레이어이름 ", ft.token("command", "일행초청"))
        invited, invitation = invitation_for(self.caller)
        if invited:
            inviter = object_by_id(invitation["inviter"])
            lines.append(
                ft.text(
                    "초대: ",
                    ft.token("player", inviter.key if inviter else "탐사자"),
                    " → ",
                    ft.token("command", "일행합류"),
                    " / ",
                    ft.token("command", "일행거절"),
                )
            )
        requested, _ = request_for(self.caller)
        if requested:
            lines.append(ft.text("가입 요청: 일행 #", str(requested.pk), " (60초 이내)"))
        self.caller.msg(ft.compact("일행", *lines, summary=summary))


class PartyInvite(GameCommand):
    category = "일행·교류"
    usage = "플레이어 일행초청"
    summary = "최대 4명의 일행에 초대합니다."
    key = "일행초청"
    input_style = "target"

    def run(self):
        from evennia.objects.models import ObjectDB
        from typeclasses.parties import invite

        players = ordered(
            ObjectDB.objects.filter(db_typeclass_path="typeclasses.explorers.Explorer")
        )
        selector = parse_selector(self.args, [n for obj in players for n in names(obj)])
        require_single(selector, self.key)
        target = strict_single(matching(players, selector), selector, self.key)
        invite(self.caller, target)
        self.caller.msg(ft.text(ft.token("player", target.key), "에게 일행 초대를 보냈다."))


class PartyAccept(GameCommand):
    category = "일행·교류"
    usage = "일행합류"
    summary = "유효한 초대를 수락합니다."
    key = "일행합류"
    accept = True

    def run(self):
        from typeclasses.parties import respond

        respond(self.caller, self.accept)


class PartyReject(PartyAccept):
    category = "일행·교류"
    usage = "일행거절 · 민수 일행거절"
    summary = "자기 초청 또는 현재 리더의 지정 가입 요청을 거절합니다."
    key = "일행거절"
    input_style = "target"
    accept = False

    def run(self):
        if self.args.strip():
            required(self.caller).answer_request(self.caller, resolve(self.args), False)
        else:
            super().run()


class PartyLeave(GameCommand):
    category = "일행·교류"
    usage = "일행탈퇴"
    summary = "일행에서 나갑니다."
    key = "일행탈퇴"

    def run(self):
        from typeclasses.parties import party_for

        party = party_for(self.caller)
        if not party:
            raise rules.RuleError("소속 일행이 없습니다.")
        party.remove_member(self.caller)


class PartyKick(GameCommand):
    category = "일행·교류"
    usage = "플레이어 일행제외"
    summary = "리더가 멤버를 제외합니다."
    key = "일행제외"
    input_style = "target"
    transfer = False

    def run(self):
        from typeclasses.parties import party_for
        from world.multiplayer import object_by_id

        party = party_for(self.caller)
        if not party:
            raise rules.RuleError("소속 일행이 없습니다.")
        members = ordered([obj for key in party.state()["members"] if (obj := object_by_id(key))])
        selector = parse_selector(self.args, [n for obj in members for n in names(obj)])
        require_single(selector, self.key)
        target = strict_single(matching(members, selector), selector, self.key)
        if not target:
            raise rules.RuleError("일행 멤버를 지정하세요.")
        if self.transfer:
            party.transfer(self.caller, target)
        else:
            party.remove_member(self.caller, target)


class PartyTransfer(PartyKick):
    category = "일행·교류"
    usage = "플레이어 일행리더"
    summary = "리더가 권한을 위임합니다."
    key = "일행리더"
    transfer = True


class PartyLootMode(GameCommand):
    category = "일행·교류"
    usage = "순번 일행분배"
    summary = "참여자 순번 분배를 설정합니다."
    key = "일행분배"
    input_style = "target"

    def run(self):
        from typeclasses.parties import party_for
        from world.multiplayer import world_change

        with world_change():
            party = party_for(self.caller)
            if not party:
                raise rules.RuleError("소속 일행이 없습니다.")
            party.require_leader(self.caller)
            if self.args.strip() not in ("순번", "round_robin"):
                raise rules.RuleError("현재 지원하는 전리품 방식: 순번 일행분배")
            state = party.state()
            state["loot_mode"] = "round_robin"
            party.db.state = state
        self.caller.msg("전리품을 참여자 순번으로 배분합니다.")


def required(caller):
    from typeclasses.parties import party_for

    party = party_for(caller)
    if not party:
        raise rules.RuleError("소속 일행이 없습니다.")
    return party


def resolve(value, pool=None):
    from world.private_messaging import players

    pool = ordered(players() if pool is None else pool)
    selector = parse_selector(value, [n for obj in pool for n in names(obj)])
    return strict_single(matching(pool, selector), selector, "일행")


def member(caller, value):
    from world.multiplayer import object_by_id

    return resolve(value, [obj for identity in required(caller).state()["members"]
                           if (obj := object_by_id(identity))])


class PartyCreate(GameCommand):
    category = "일행·교류"
    key = "일행모으기"
    aliases = ["그룹만들기", "그룹모으기"]
    usage = "일행모으기"
    summary = "비교전·미가입 상태에서 1인 일행을 만듭니다."

    def run(self):
        from typeclasses.parties import create_party
        create_party(self.caller)


class PartyRequest(PartyInvite):
    key = "일행요청"
    aliases = ["그룹요청"]
    usage = "철수 일행요청"
    summary = "온라인인 기존 일행 리더에게 60초 가입 요청을 보냅니다."

    def run(self):
        from typeclasses.parties import request_join
        request_join(self.caller, resolve(self.args))


class PartyApprove(PartyInvite):
    key = "일행허락"
    aliases = ["그룹허락"]
    usage = "민수 일행허락"
    summary = "현재 리더가 유효한 가입 요청을 승인합니다."

    def run(self):
        required(self.caller).answer_request(self.caller, resolve(self.args), True)


class PartySuccession(PartyCreate):
    key = "일행승계"
    aliases = ["그룹승계"]
    usage = "일행승계"
    summary = "현재 온라인 일반 멤버가 실제 오프라인 리더를 즉시 승계합니다."

    def run(self):
        required(self.caller).succeed(self.caller)


class PartyDissolve(PartyCreate):
    key = "일행해체"
    aliases = ["그룹해체"]
    input_style = "target"
    usage = "일행해체 · 확인 일행해체"
    summary = "리더가 60초 2단계 확인으로 비교전 일행을 해체합니다."

    def run(self):
        if self.args.strip() not in ("", "확인"):
            raise rules.RuleError("일행해체 후 60초 내 확인 일행해체를 입력하세요.")
        required(self.caller).dissolve(self.caller, confirm=self.args.strip() == "확인")


class PartyChat(PartyCreate):
    key = "일행대화"
    aliases = ["무리말", "그룹대화", "무"]
    input_style = "chat"
    usage = "모여 주세요 일행대화 · 모여 주세요 무"
    summary = "발신자를 포함한 현재 온라인 구성원에게만 비공개 발화합니다."

    def run(self):
        required(self.caller).chat(self.caller, self.args)


class PartyAttack(PartyCreate):
    key = "일행공격"
    aliases = ["일공"]
    input_style = "target"
    usage = "어린청소룡 일공 · 일행공격"
    summary = "리더가 참가 가능한 구성원의 기존 자동 전투를 시작합니다."

    def run(self):
        from typeclasses.enemies import Enemy
        from world.targets import Mode, normalized, room_objects
        from world.targets import resolve as resolve_target

        party = required(self.caller)
        party.require_leader(self.caller)
        target = self.caller.combat_target()
        if self.args.strip():
            pool = [obj for obj in room_objects(self.caller) if isinstance(obj, Enemy)]
            selector = parse_selector(self.args, [name for obj in pool for name in names(obj)])
            # 일행공격의 무번호 복수 후보 거절은 일반 공격의 기본 첫 대상과 다르다.
            if selector.mode == Mode.DEFAULT:
                matches = matching(pool, selector)
                exact = [obj for obj in matches if normalized(obj.key) == normalized(selector.name)]
                strict_single(exact or matches, selector, self.key)
            target = resolve_target(pool, selector, self.caller, self.key)[0]
        party.attack(self.caller, target)


class PartyDefense(PartyCreate):
    key = "일행방어"
    aliases = ["그룹방어"]
    input_style = "target"
    usage = "철수 일행방어 · 일행방어 · 해제 일행방어"
    summary = "영속 방어 담당을 조회하거나 리더가 지정·해제합니다."

    def run(self):
        from world.multiplayer import object_by_id
        party = required(self.caller)
        if not self.args.strip():
            defender = object_by_id(party.state()["tactics"].get("defender_id"))
            self.caller.msg(ft.text("방어 담당: ", ft.token("player", defender.key) if defender else "없음"))
        else:
            party.set_defender(self.caller, None if self.args.strip() == "해제" else member(self.caller, self.args))


PartyCommand.aliases = ["무리", "그룹"]
PartyInvite.aliases = ["그룹초청"]
PartyAccept.aliases = ["그룹가입"]
PartyReject.aliases = []
PartyLeave.aliases = ["그룹탈퇴"]
PartyKick.aliases = []
PartyTransfer.aliases = ["그룹리더"]
PartyLootMode.aliases = []
PARTY_COMMANDS = (PartyCommand, PartyCreate, PartyInvite, PartyAccept, PartyReject,
                  PartyRequest, PartyApprove, PartyKick, PartyLeave, PartyTransfer,
                  PartySuccession, PartyDissolve, PartyChat, PartyAttack, PartyDefense, PartyLootMode)
_RULES = {
    "일행초청": "현재 리더만 온라인 미가입 타인을 초청합니다. 60초 만료이며 반복 입력은 연장하지 않습니다. 미소속이면 비교전일 때 자동 생성합니다.",
    "일행합류": "비교전 상태에서 유효한 초청을 수락합니다. 리더가 오프라인이어도 유효 일행에 합류합니다.",
    "일행거절": "무인자는 자기 초청, 대상 지정은 리더의 가입 요청 거절만 처리합니다.",
    "일행허락": "요청자가 오프라인이면 거절하되 TTL까지 요청을 유지합니다. 가입 성공 시 다른 초청과 요청을 정리합니다.",
    "일행리더": "현재 리더가 대상 구성원에게 명시적으로 위임합니다. 무인자 승계는 허용하지 않습니다.",
    "일행승계": "실제 리더 캐릭터 세션이 없으면 즉시 승계합니다. 명령 없이 연속 600초 뒤 첫 5초 월드 tick에서도 가장 먼저 가입한 온라인 구성원이 자동 승계합니다. AFK는 오프라인이 아닙니다.",
    "일행해체": "일행해체 후 60초 내 확인 일행해체를 입력합니다. 일행·리더·멤버/가입 순서가 바뀌면 무효입니다. 실제 교전 중에는 거절하고 개인별 확정 전리품 권리를 보존합니다.",
    "일행대화": "다른 방에서도 온라인 멤버만 수신합니다. 개인 차단·최근 상대와 무관하며 본문을 명령이나 NPC 화제로 실행하지 않습니다. 최대 300자입니다.",
    "일행공격": "리더 지시로 가능한 구성원만 참가합니다. 무인자는 리더의 현재 적을 사용합니다. 기존 동일 적 전투는 재시작하지 않고 즉시 타격·타이머 초기화 없이 부분 결과를 표시합니다.",
    "일행방어": "리더는 오프라인 멤버도 영속 지정합니다. 전투 종료·도망·패배·이동·접속 종료·재시작·승계 후에도 지정은 유지합니다. 같은 일행 기본 피해자의 같은 적 유효 참가 담당자에게만 대상이 바뀝니다. 해제는 제어어 우선이며 해제 1 일행방어로 동명 멤버를 지정합니다.",
}
for _cls in PARTY_COMMANDS:
    _cls.help_sections = (
        ("사용법", (_cls.usage,)), ("예시", tuple(_cls.usage.split(" · "))),
        ("실행 규칙", (_RULES.get(_cls.key, _cls.summary), "실행 시 구성원·리더·권한을 다시 확인하며 기존 XP·전리품·전투 수치를 유지합니다.")),
        ("제한", ("정원 4명입니다. 이름·번호를 사용하며 모호한 대상을 임의 선택하지 않습니다.",)),
        ("관련 도움말", ("일행 도움", "일행승계 도움", "일행방어 도움")),
    )
