"""일행의 기존 영속 객체·가입 순서·전리품 상태를 관리한다."""

from copy import deepcopy
from time import time

from evennia import create_object
from evennia.objects.objects import DefaultObject
from evennia.utils.dbserialize import deserialize
from world import text as ft
from world.multiplayer import (
    PARTY_INVITE_TTL_SECONDS,
    PARTY_MAX_SIZE,
    after_change,
    object_by_id,
    world_change,
)
from world.rules import RuleError


def online(character):
    """계정/AFK가 아니라 실제 이 캐릭터를 제어하는 활성 세션을 확인한다."""
    return bool(character and character.pk and any(
        getattr(session, "puppet", None) == character and getattr(session, "logged_in", False)
        for session in character.sessions.all()
    ))


def party_for(character):
    party = object_by_id(character.db.party_id)
    if isinstance(party, Party) and character.id in party.state()["members"]:
        return party
    return None


def in_combat(character):
    """오래된 profile target만으로 교전이라고 판정하지 않는다."""
    from typeclasses.enemies import Enemy

    enemy = object_by_id(character.profile().get("combat_target"))
    return bool(isinstance(enemy, Enemy) and enemy.db.state == "alive"
                and character.id in (enemy.db.combatants or []) and enemy.location == character.location)


def invitation_for(character, now=None):
    now = time() if now is None else now
    for party in Party.objects.all():
        party.reconcile(now)
        invitation = party.state()["invitations"].get(character.id)
        if invitation:
            return party, invitation
    return None, None


def request_for(character, now=None):
    now = time() if now is None else now
    for party in Party.objects.all():
        party.reconcile(now)
        request = party.state()["join_requests"].get(character.id)
        if request:
            return party, request
    return None, None


def clear_pending(character):
    for party in Party.objects.all():
        state = party.state()
        changed = False
        for field in ("invitations", "join_requests"):
            if character.id in state[field]:
                del state[field][character.id]
                changed = True
        if changed:
            party.db.state = state


def announce(party, message):
    if not party.pk:
        return
    for identity in party.state()["members"]:
        member = object_by_id(identity)
        if online(member):
            member.msg(message)
            member.push_state()


def create_party(caller, now=None):
    now = time() if now is None else now
    with world_change():
        if party_for(caller):
            raise RuleError("이미 일행에 속해 있습니다.")
        if in_combat(caller):
            raise RuleError("교전 중에는 일행을 만들 수 없습니다. 먼저 도망하세요.")
        party = create_object(Party, key="탐사 일행")
        state = party.state()
        state.update(leader=caller.id, members=[caller.id], created_at=now)
        party.db.state = state
        caller.db.party_id = party.id
        clear_pending(caller)
        after_change(lambda: caller.msg("1인 일행을 만들었습니다."))
        return party


def invite(caller, target, now=None):
    now = time() if now is None else now
    with world_change():
        if not target or not hasattr(target, "profile") or not online(target):
            raise RuleError("온라인인 탐사자 이름을 입력하세요.")
        if target == caller:
            raise RuleError("자기 자신은 초청할 수 없습니다.")
        party = party_for(caller)
        if party:
            party.require_leader(caller)
        if party_for(target):
            raise RuleError("이미 일행에 속한 탐사자입니다.")
        pending, _ = invitation_for(target, now)
        if pending:
            if pending == party:
                return party
            raise RuleError("이미 다른 일행의 초청을 받고 있습니다.")
        if party and len(party.state()["members"]) >= PARTY_MAX_SIZE:
            raise RuleError("일행 정원이 가득 찼습니다.")
        if not party:
            party = create_party(caller, now)
        state = party.state()
        state["invitations"][target.id] = {"inviter": caller.id, "expires_at": now + PARTY_INVITE_TTL_SECONDS}
        party.db.state = state
        after_change(lambda: target.msg(ft.text(ft.named("player", caller.key, "이/가"),
                     " 일행에 초청했다.\n", ft.token("command", "일행합류"), " / ",
                     ft.token("command", "일행거절"), " (60초 이내)")))
        return party


def join(party, character):
    state = party.state()
    if not party.pk or not state["members"] or not object_by_id(state["leader"]):
        raise RuleError("일행이 더 이상 유효하지 않습니다.")
    if party_for(character) or in_combat(character) or not online(character):
        raise RuleError("온라인·미가입·비교전 상태에서만 합류할 수 있습니다.")
    if len(state["members"]) >= PARTY_MAX_SIZE:
        raise RuleError("일행 정원이 가득 찼습니다.")
    state["members"].append(character.id)
    party.db.state = state
    character.db.party_id = party.id
    clear_pending(character)
    after_change(lambda: announce(party, ft.text(ft.named("player", character.key, "이/가"), " 일행에 합류했다.")))


def respond(character, accept, now=None):
    with world_change():
        party, _ = invitation_for(character, now)
        if not party:
            raise RuleError("유효한 일행 초청이 없습니다.")
        if accept:
            join(party, character)
        else:
            state = party.state()
            del state["invitations"][character.id]
            party.db.state = state
            after_change(lambda: character.msg("일행 초청을 거절했습니다."))
        return party


def request_join(caller, leader, now=None):
    now = time() if now is None else now
    with world_change():
        party = party_for(leader) if leader else None
        if not party or party.state()["leader"] != leader.id or not online(leader):
            raise RuleError("온라인인 기존 일행 리더에게 요청하세요.")
        if party_for(caller) or in_combat(caller) or not online(caller):
            raise RuleError("온라인·미가입·비교전 상태에서만 요청할 수 있습니다.")
        pending, _ = request_for(caller, now)
        if pending:
            if pending == party:
                return party
            raise RuleError("이미 다른 일행에 가입 요청을 보냈습니다.")
        state = party.state()
        if len(state["members"]) >= PARTY_MAX_SIZE:
            raise RuleError("일행 정원이 가득 찼습니다.")
        state["join_requests"][caller.id] = {"expires_at": now + PARTY_INVITE_TTL_SECONDS}
        party.db.state = state
        after_change(lambda: leader.msg(ft.text(ft.token("player", caller.key), "의 가입 요청: ",
                     ft.token("command", caller.key + " 일행허락"), " / ",
                     ft.token("command", caller.key + " 일행거절"), " (60초 이내)")))
        after_change(lambda: caller.msg("일행 가입 요청을 보냈습니다."))
        return party


def preserve_loot(party, now):
    """삭제 전 권리 검증. native FK SET_NULL과 legacy 개인 배정을 보존한다."""
    from world.loot_assets import normalize_entry
    from world.loot_entities.models import CurrencyLoot, LootClaim

    from typeclasses.explorers import Explorer
    from typeclasses.loot import Corpse, DroppedLoot

    def personal(identity):
        return isinstance(object_by_id(identity), Explorer)

    for claim in LootClaim.objects.filter(reserved_party_id=party.id):
        if (claim.assigned_player_id and not personal(claim.assigned_player_id)
                or claim.reserved_player_id and not personal(claim.reserved_player_id)
                or now < claim.protection_until and not (claim.assigned_player_id or claim.reserved_player_id)):
            raise RuleError("확정 개인 전리품 권리를 보존할 수 없어 일행 삭제를 중단합니다.")
    for row in CurrencyLoot.objects.filter(reserved_party_id=party.id):
        shares = list(row.shares.all())
        if (row.reserved_player_id and not personal(row.reserved_player_id)
                or any(not personal(share.player_id) for share in shares)
                or now < row.protection_until and not (shares or row.reserved_player_id)):
            raise RuleError("확정 개인 화폐 지분을 보존할 수 없어 일행 삭제를 중단합니다.")
    for source in [*Corpse.objects.all(), *DroppedLoot.objects.all()]:
        entries = deserialize(source.db.entries)
        if not entries:
            continue
        changed = False
        for raw in entries:
            if raw.get("reserved_party") != party.id:
                continue
            entry = normalize_entry(raw)
            identities = ([entry.get("assigned_player"), entry.get("reserved_player")]
                          if entry["kind"] == "item" else [*entry["eligible_players"], entry.get("reserved_player")])
            identities = [identity for identity in identities if identity is not None]
            if any(not personal(identity) for identity in identities) or now < entry["protection_until"] and not identities:
                raise RuleError("구형 전리품 개인 권리를 보존할 수 없어 일행 삭제를 중단합니다.")
            raw["reserved_party"] = None
            changed = True
        if changed:
            source.db.entries = entries


class Party(DefaultObject):
    def at_object_creation(self):
        self.locks.add("get:false();puppet:false();delete:false()")
        self.db.state = {"leader": None, "members": [], "invitations": {},
                         "loot_mode": "round_robin", "round_robin_cursor": 0, "created_at": time(),
                         "join_requests": {}, "tactics": {"defender_id": None}, "leader_offline_since": None}

    def state(self):
        raw = deserialize(self.db.state) or {}
        if not isinstance(raw, dict):
            raise RuleError("일행 저장 상태를 확인할 수 없습니다.")
        state = deepcopy(raw)
        for key, default in {"leader": None, "members": [], "invitations": {}, "loot_mode": "round_robin",
                             "round_robin_cursor": 0, "created_at": None, "join_requests": {},
                             "tactics": {"defender_id": None}, "leader_offline_since": None}.items():
            state.setdefault(key, default)
        return state

    def reconcile(self, now=None):
        now = time() if now is None else now
        with world_change():
            state = self.state()
            for field in ("invitations", "join_requests"):
                state[field] = {key: value for key, value in state[field].items() if value["expires_at"] > now}
            defender = state["tactics"].get("defender_id")
            if defender and (defender not in state["members"] or not object_by_id(defender)):
                state["tactics"]["defender_id"] = None
            if state != deserialize(self.db.state):
                self.db.state = state

    def require_leader(self, caller):
        if not self.pk or party_for(caller) != self or self.state()["leader"] != caller.id:
            raise RuleError("현재 일행 리더만 실행할 수 있습니다.")

    def transfer(self, caller, target):
        with world_change():
            self.require_leader(caller)
            state = self.state()
            if not target or target.id not in state["members"] or party_for(target) != self:
                raise RuleError("현재 일행 구성원을 지정하세요.")
            if state["leader"] == target.id:
                return
            state.update(leader=target.id, leader_offline_since=None)
            self.db.state = state
            after_change(lambda: announce(self, ft.text(ft.named("player", target.key, "이/가"), " 일행 리더를 맡았다.")))

    def answer_request(self, caller, target, accept, now=None):
        now = time() if now is None else now
        with world_change():
            self.require_leader(caller)
            self.reconcile(now)
            state = self.state()
            if not target or target.id not in state["join_requests"]:
                raise RuleError("유효한 가입 요청이 없습니다.")
            if accept:
                join(self, target)
            else:
                del state["join_requests"][target.id]
                self.db.state = state
                after_change(lambda: caller.msg("가입 요청을 거절했습니다."))
                after_change(lambda: target.msg("일행 가입 요청이 거절되었습니다."))

    def remove_member(self, caller, target=None, now=None):
        now = time() if now is None else now
        with world_change():
            if target is not None:
                self.require_leader(caller)
                if target == caller:
                    raise RuleError("자신은 일행탈퇴로 나가세요.")
            else:
                target = caller
            state = self.state()
            if not target or target.id not in state["members"] or party_for(target) != self:
                raise RuleError("현재 일행 구성원이 아닙니다.")
            if len(state["members"]) == 1:
                preserve_loot(self, now)
            target.leave_combat(now=now)
            state["members"].remove(target.id)
            target.db.party_id = None
            if state["tactics"].get("defender_id") == target.id:
                state["tactics"]["defender_id"] = None
            if not state["members"]:
                self.delete()
            else:
                if state["leader"] == target.id:
                    state.update(leader=state["members"][0], leader_offline_since=None)
                self.db.state = state
                after_change(lambda: announce(self, ft.text(ft.named("player", target.key, "이/가"), " 일행에서 나갔다.")))
            after_change(lambda: target.msg("일행에서 나왔습니다."))

    def dissolve(self, caller, confirm=False, now=None):
        now = time() if now is None else now
        with world_change():
            self.require_leader(caller)
            state = self.state()
            members = [object_by_id(identity) for identity in state["members"]]
            if any(obj and in_combat(obj) for obj in members):
                raise RuleError("실제로 교전 중인 구성원이 있어 일행을 해체할 수 없습니다.")
            snapshot = (self.id, state["leader"], tuple(state["members"]))
            if not confirm:
                after_change(lambda: setattr(caller.ndb, "party_dissolve_request", {"snapshot": snapshot, "expires_at": now + 60}))
                after_change(lambda: caller.msg(ft.text("60초 내 ", ft.token("command", "확인 일행해체"), "로 해체를 확인하세요.")))
                return
            request = caller.ndb.party_dissolve_request
            if not request or now >= request["expires_at"] or request["snapshot"] != snapshot:
                raise RuleError("해체 확인이 없거나 만료·구성 변경으로 무효입니다. 일행해체부터 다시 요청하세요.")
            preserve_loot(self, now)
            for obj in members:
                if obj:
                    obj.db.party_id = None
            self.delete()
            after_change(lambda: setattr(caller.ndb, "party_dissolve_request", None))
            for obj in members:
                if obj:
                    after_change(lambda obj=obj: obj.msg("일행을 해체했습니다. 확정 개인 전리품 권리는 유지됩니다."))
