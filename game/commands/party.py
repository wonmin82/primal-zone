"""party 영역의 명시적 게임 명령."""

from world import rules
from world import text as ft

from commands.base import GameCommand


class PartyCommand(GameCommand):
    category = "파티"
    usage = "파티"
    summary = "파티장·멤버·초대를 확인합니다."
    key = "파티"

    def run(self):
        from typeclasses.parties import invitation_for, party_for
        from world.multiplayer import object_by_id

        party = party_for(self.caller)
        lines = []
        if party:
            state = party.state()
            leader = object_by_id(state["leader"])
            lines.extend(
                [
                    ft.row("파티장", ft.token("player", leader.key)),
                    "전리품 : 참여자 순번 분배",
                    "",
                    "[ 멤버 ]",
                ]
            )
            for identity in state["members"]:
                member = object_by_id(identity)
                if member:
                    lines.append(
                        ft.text(
                            ft.token("player", member.key),
                            " [파티장]" if identity == state["leader"] else "",
                        )
                    )
        else:
            lines.append(
                ft.text(
                    "소속 파티가 없습니다. 플레이어이름 ",
                    ft.token("command", "파티초대"),
                    "로 시작하세요.",
                )
            )
        invited, _ = invitation_for(self.caller)
        if invited:
            lines.append(
                ft.text(
                    "대기 중인 초대 : ",
                    ft.token("command", "파티수락"),
                    " / ",
                    ft.token("command", "파티거절"),
                )
            )
        self.caller.msg(ft.sheet("탐사 파티", *lines))


class PartyInvite(GameCommand):
    category = "파티"
    usage = "플레이어 파티초대"
    summary = "최대 4명의 파티에 초대합니다."
    key = "파티초대"
    input_style = "target"

    def run(self):
        from evennia.objects.models import ObjectDB
        from typeclasses.parties import invite

        target = ObjectDB.objects.filter(
            db_key__iexact=self.args.strip(), db_typeclass_path="typeclasses.explorers.Explorer"
        ).first()
        invite(self.caller, target)
        self.caller.msg(ft.text(ft.token("player", target.key), "에게 파티 초대를 보냈다."))


class PartyAccept(GameCommand):
    category = "파티"
    usage = "파티수락"
    summary = "유효한 초대를 수락합니다."
    key = "파티수락"
    accept = True

    def run(self):
        from typeclasses.parties import respond

        party = respond(self.caller, self.accept)
        if self.accept:
            announce(
                party, ft.text(ft.named("player", self.caller.key, "이/가"), " 파티에 합류했다.")
            )
        else:
            self.caller.msg(ft.text("파티 초대를 거절했다."))


class PartyReject(PartyAccept):
    category = "파티"
    usage = "파티거절"
    summary = "초대를 거절합니다."
    key = "파티거절"
    accept = False


class PartyLeave(GameCommand):
    category = "파티"
    usage = "파티탈퇴"
    summary = "파티에서 나갑니다."
    key = "파티탈퇴"

    def run(self):
        from typeclasses.parties import party_for

        party = party_for(self.caller)
        if not party:
            raise rules.RuleError("소속 파티가 없습니다.")
        party.remove_member(self.caller)
        message = ft.text(ft.named("player", self.caller.key, "이/가"), " 파티를 떠났다.")
        self.caller.msg(message)
        if party.pk:
            announce(party, message)


class PartyKick(GameCommand):
    category = "파티"
    usage = "플레이어 파티제외"
    summary = "파티장이 멤버를 제외합니다."
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
        message = ft.text(
            ft.named("player", target.key, "이/가"),
            " 파티장을 맡았다." if self.transfer else " 파티에서 제외되었다.",
        )
        announce(party, message)
        if not self.transfer:
            target.msg(message)


class PartyTransfer(PartyKick):
    category = "파티"
    usage = "플레이어 파티장위임"
    summary = "파티장이 권한을 위임합니다."
    key = "파티장위임"
    transfer = True


class PartyLootMode(GameCommand):
    category = "파티"
    usage = "순번 파티분배"
    summary = "참여자 순번 분배를 설정합니다."
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


def announce(party, message):
    from world.multiplayer import object_by_id

    for identity in party.state()["members"]:
        member = object_by_id(identity)
        if member:
            member.msg(message)
