"""파티 구성과 초대의 단일 영속 상태. 멤버 목록 순서가 가입 순서다."""

from time import time

from evennia import create_object
from evennia.objects.objects import DefaultObject
from evennia.utils.dbserialize import deserialize
from world.multiplayer import (
    PARTY_INVITE_TTL_SECONDS,
    PARTY_MAX_SIZE,
    object_by_id,
    world_change,
)
from world.rules import RuleError


def party_for(character):
    party = object_by_id(character.db.party_id)
    if party and party.is_typeclass(Party, exact=True) and character.id in party.state()["members"]:
        return party
    return None


def invitation_for(character, now=None):
    now = time() if now is None else now
    for party in Party.objects.all():
        party.reconcile(now)
        invitation = party.state()["invitations"].get(character.id)
        if invitation:
            return party, invitation
    return None, None


def invite(caller, target, now=None):
    now = time() if now is None else now
    with world_change():
        if not target or not hasattr(target, "profile"):
            raise RuleError("존재하는 탐사자 이름을 입력하세요.")
        if target == caller:
            raise RuleError("자기 자신은 초대할 수 없습니다.")
        party = party_for(caller)
        if party:
            party.require_leader(caller)
        if party_for(target):
            raise RuleError("이미 파티에 속한 탐사자입니다.")
        pending, _ = invitation_for(target, now)
        if pending:
            if pending == party:
                return party
            raise RuleError("이미 다른 파티의 초대를 받고 있습니다.")
        if party and len(party.state()["members"]) >= PARTY_MAX_SIZE:
            raise RuleError("파티 정원이 가득 찼습니다.")
        if not party:
            party = create_object(Party, key="탐사 파티")
            state = party.state()
            state.update(leader=caller.id, members=[caller.id], created_at=now)
            party.db.state = state
            caller.db.party_id = party.id
        state = party.state()
        state["invitations"][target.id] = {
            "inviter": caller.id,
            "expires_at": now + PARTY_INVITE_TTL_SECONDS,
        }
        party.db.state = state
        target.msg(f"{caller.key}의 파티 초대: 파티수락 / 파티거절 (60초 이내)")
        return party


def respond(character, accept, now=None):
    with world_change():
        party, _ = invitation_for(character, now)
        if not party:
            raise RuleError("유효한 파티 초대가 없습니다.")
        state = party.state()
        if accept:
            if party_for(character):
                raise RuleError("이미 파티에 속해 있습니다.")
            if not state["members"] or not object_by_id(state["leader"]):
                raise RuleError("초대한 파티가 더 이상 유효하지 않습니다.")
            if len(state["members"]) >= PARTY_MAX_SIZE:
                raise RuleError("파티 정원이 가득 찼습니다.")
            state["members"].append(character.id)
            character.db.party_id = party.id
        del state["invitations"][character.id]
        party.db.state = state
        return party


class Party(DefaultObject):
    def at_object_creation(self):
        self.locks.add("get:false();puppet:false();delete:false()")
        self.db.state = {
            "leader": None,
            "members": [],
            "invitations": {},
            "loot_mode": "round_robin",
            "round_robin_cursor": 0,
            "created_at": time(),
        }

    def state(self):
        return deserialize(self.db.state)

    def reconcile(self, now=None):
        now = time() if now is None else now
        with world_change():
            state = self.state()
            invitations = {
                key: value
                for key, value in state["invitations"].items()
                if value["expires_at"] > now
            }
            if invitations != state["invitations"]:
                state["invitations"] = invitations
                self.db.state = state

    def require_leader(self, caller):
        if self.state()["leader"] != caller.id:
            raise RuleError("파티장만 실행할 수 있습니다.")

    def transfer(self, caller, target):
        with world_change():
            self.require_leader(caller)
            state = self.state()
            if not target or target.id not in state["members"]:
                raise RuleError("파티 멤버를 지정하세요.")
            state["leader"] = target.id
            self.db.state = state

    def remove_member(self, caller, target=None):
        with world_change():
            if target is not None:
                self.require_leader(caller)
                if target == caller:
                    raise RuleError("자신은 파티탈퇴로 나가세요.")
            else:
                target = caller
            state = self.state()
            if target.id not in state["members"]:
                raise RuleError("파티 멤버가 아닙니다.")
            state["members"].remove(target.id)
            target.db.party_id = None
            if not state["members"]:
                self.delete()
                return
            if state["leader"] == target.id:
                state["leader"] = state["members"][0]
            self.db.state = state
