"""실제 Actor에 귀속되는 독점 대련의 시간·접속·정산 정책."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from time import time
from uuid import uuid4

from evennia.objects.models import ObjectDB
from evennia.utils import delay
from evennia.utils.dbserialize import deserialize

from world import rules
from world.combat_contracts import (
    Combatant,
    Encounter,
    EncounterPolicy,
    apply_tick,
    encounter_state,
    plan_tick,
    settle_encounter,
    validate_final_result,
)
from world.domain_context import combat_timer_context
from world.multiplayer import COMBAT_INTERVAL, after_change, object_by_id, world_change

MAX_DURATION = 600
IDLE_LIMIT = 60
RECONNECT_GRACE = 30
COOLDOWN = 30
SKILLS = ("attack", "heavy", "shooting", "insight", "suppress", "heal", "breathing")


def _state(actor):
    stored = actor.db.duel_state
    if stored is None:
        return {}
    if not isinstance(stored, Mapping):
        return {"state": "active"}
    return deepcopy(deserialize(stored))


@dataclass(frozen=True)
class DuelEncounter(Encounter):
    duel_id: str

    @property
    def state(self):
        return _state(self.owner)

    @property
    def identity(self):
        return self.duel_id

    def save(self, state):
        self.owner.db.duel_state = state


def _encounter(actor, state):
    return DuelEncounter(actor, state["generation"], state["identity"])


def active_on(actor):
    stored = actor.db.duel_state
    return stored is not None and (not isinstance(stored, Mapping) or stored.get("state") == "active")


def generation_on(actor):
    return _state(actor).get("generation", 0)


def _active_actor(player):
    actor = object_by_id(player.db.active_duel_actor)
    if actor is not None:
        state = _state(actor)
        if state.get("state") == "active" and state.get("participant_id") == player.pk:
            return actor
    return None


def active_for(player):
    return bool(player.db.active_duel_actor and _active_actor(player) is not None)


def _eligible(actor, player, now):
    from typeclasses.actors import Actor
    from typeclasses.explorers import Explorer

    from world.observation import can_perceive, context_for

    return (
        isinstance(actor, Actor) and isinstance(player, Explorer) and actor.pk and player.pk
        and actor.capability_active("duel") and actor.capability_active("combat")
        and actor.location is not None and player.location == actor.location
        and can_perceive(actor, context_for(player, observed_at=now))
    )


def _lock_actor(actor):
    if not ObjectDB.objects.select_for_update().filter(pk=actor.pk).exists():
        raise rules.RuleError("대련 상대가 더는 존재하지 않습니다.")


def _publish(actor):
    from world.shared_combat import broadcast_state

    after_change(lambda: broadcast_state(actor))


def start(actor, player, *, expected_generation=None, now=None):
    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        _lock_actor(actor)
        state = _state(actor)
        generation = state.get("generation", 0)
        if expected_generation is not None and expected_generation != generation:
            raise rules.RuleError("오래된 대련 신청입니다. 대상을 다시 확인하세요.")
        if (state.get("state") == "active" or active_for(player) or actor.db.combatants or actor.db.claim
                or (actor.db.encounter_state or {}).get("state") == "active"):
            raise rules.RuleError("이미 교전 또는 대련이 진행 중입니다.")
        cooldowns = {key: end for key, end in state.get("cooldowns", {}).items() if end > now}
        if str(player.pk) in cooldowns:
            raise rules.RuleError("대련 재신청은 종료 30초 뒤에 가능합니다.")
        actor_combatant = Combatant(actor)
        player_combatant = Combatant(player)
        actor_combatant.validate_participation(
            player_combatant, lambda *_: bool(player.sessions.count()) and _eligible(actor, player, now),
        )
        profile = player_combatant.snapshot()
        actor_hp = actor_combatant.snapshot()["hp"]
        if profile.get("combat_target") or profile["hp"] <= 0 or actor_hp <= 0:
            raise rules.RuleError("현재 상태로 대련할 수 없습니다.")
        encounter = DuelEncounter(actor, generation + 1, uuid4().hex)
        state = encounter_state(encounter, (actor_combatant.identity, player_combatant.identity),
                                EncounterPolicy.EXCLUSIVE_DUEL)
        state.update(participant_id=player.pk, room_id=actor.location.pk, started_at=now, ends_at=now + MAX_DURATION,
                     last_action_at=now, reconnect_until=None, cooldowns=cooldowns,
                     actor_hp=actor_hp, player_hp=profile["hp"], enemy_round=0,
                     queued_skill="attack", insight=None, suppressions={})
        encounter.save(state)
        player.db.active_duel_actor = actor.pk
        _plan_round(encounter, now + COMBAT_INTERVAL)
        from world.shared_combat import deliver_combat_message

        deliver_combat_message(player, "대련을 시작합니다. 최대 10분이며, 자동 공격과 별도로 60초마다 전투 행동을 입력해야 합니다.")
        _publish(actor)
        return encounter.identity


def _require_participant(actor, player, encounter_id, now):
    state = _state(actor)
    if (state.get("state") != "active" or state.get("identity") != encounter_id
            or not _valid_state(state) or state.get("participant_id") != player.pk
            or state["room_id"] != actor.db_location_id
            or player.db.active_duel_actor != actor.pk or not player.sessions.count()
            or not _eligible(actor, player, now) or _expired(state, now)
            or state.get("reconnect_until") is not None):
        raise rules.RuleError("현재 대련에 이 행동을 사용할 수 없습니다.")
    return state


def act(actor, player, encounter_id, *, skill="attack", now=None):
    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        _lock_actor(actor)
        state = _require_participant(actor, player, encounter_id, now)
        if skill not in SKILLS:
            raise rules.RuleError("지원하지 않는 대련 행동입니다.")
        profile = player.profile_snapshot()
        if skill != "attack":
            profile["hp"] = state["player_hp"]
            rules.validate_skill_action(profile, skill, now)
        from world.equipment_service import active_weapon_item, entity_runtime
        from world.firearm_service import loaded_magazine
        from world.firearms import needs_shot

        equipped = rules.equipment.context(profile).active
        if entity_runtime(player) and equipped and needs_shot(skill, equipped.weapon_type):
            firearm = active_weapon_item(player)
            magazine = loaded_magazine(firearm) if firearm else None
            if not magazine or magazine.rounds <= 0:
                raise rules.RuleError("총기에 발사할 탄약이 없다. 재장전하세요.")
        state.update(last_action_at=now, queued_skill=skill)
        actor.db.duel_state = state
        _publish(actor)
    return True


def surrender(actor, player, encounter_id, *, now=None):
    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        _lock_actor(actor)
        state = _require_participant(actor, player, encounter_id, now)
        return _finish(actor, state, "surrender", now)


def _expired(state, now):
    deadlines = [(state["ends_at"], "maximum"), (state["last_action_at"] + IDLE_LIMIT, "idle")]
    if state["reconnect_until"] is not None:
        deadlines.append((state["reconnect_until"], "disconnect"))
    deadline, reason = min(deadlines)
    return reason if now >= deadline else None


def _finish(actor, state, kind, now, reason=None):
    encounter = _encounter(actor, state)
    result = {"kind": kind, "reason": reason, "finished_at": now}

    def settle(saved):
        player = object_by_id(saved.get("participant_id"))
        if player is not None and player.db.active_duel_actor == actor.pk:
            player.attributes.remove("active_duel_actor")
            from world.shared_combat import deliver_combat_message

            label = {"victory": "승리", "defeat": "패배", "surrender": "기권", "timeout": "시간 초과",
                     "disconnect": "연결 유예 만료", "abort": "진행 불가"}[kind]
            deliver_combat_message(player, f"대련이 끝났습니다. {label}.")
        cooldowns = {key: end for key, end in saved.get("cooldowns", {}).items() if end > now}
        if kind in ("surrender", "timeout"):
            cooldowns[str(saved["participant_id"])] = now + COOLDOWN
        for key in ("queued_skill", "insight", "suppressions", "completed_operations"):
            saved.pop(key, None)
        saved.update(cooldowns=cooldowns, reconnect_until=None)
        after_change(lambda: _unschedule(actor, encounter.identity))
        _publish(actor)

    return settle_encounter(encounter, result, settle)


def _unschedule(actor, identity):
    task = actor.ndb.duel_task
    if task and task[0] == identity:
        actor.ndb.duel_task = None
        task[2].remove()


def _schedule(actor, state, now):
    identity = state["identity"]
    due_at = state["pending"]["due_at"]
    deadline = min(state["ends_at"], state["last_action_at"] + IDLE_LIMIT)
    offline = state["reconnect_until"]
    wake_at = min(deadline, due_at if offline is None else offline)
    task = actor.ndb.duel_task
    if task and task[:2] == (identity, wake_at):
        return
    if task:
        _unschedule(actor, task[0])
    actor.ndb.duel_task = (identity, wake_at, delay(max(0, wake_at - now), _wake, actor, identity, wake_at))


def _wake(actor, identity, scheduled_at):
    task = actor.ndb.duel_task
    if not task or task[:2] != (identity, scheduled_at):
        return
    actor.ndb.duel_task = None
    reconcile(actor)


def _plan_round(encounter, due_at):
    # 마감 기한과 다음 회차 시각은 재시작 뒤 현재 상태에서 재예약할 수 있다.
    plan_tick(encounter, operation_id=f"duel:{due_at}", due_at=due_at,
              trigger=lambda current, *_: _schedule_current(current.owner, current.identity))


def _schedule_current(actor, identity):
    state = _state(actor)
    if state.get("state") == "active" and state.get("identity") == identity:
        _schedule(actor, state, time())


def _valid_state(state):
    enemy_round = state.get("enemy_round")
    return (
        state.get("policy") == EncounterPolicy.EXCLUSIVE_DUEL
        and type(state.get("generation")) is int and state["generation"] > 0
        and type(state.get("identity")) is str and bool(state["identity"])
        and type(state.get("participant_id")) is int
        and type(state.get("room_id")) is int
        and type(state.get("settled")) is bool and not state["settled"]
        and state.get("queued_skill") in SKILLS and "insight" in state
        and isinstance(state.get("suppressions"), dict) and isinstance(state.get("cooldowns"), dict)
        and all(type(value) in (int, float) and isfinite(value) for value in state["cooldowns"].values())
        and isinstance(state.get("pending"), dict)
        and type(state["pending"].get("operation_id")) is str
        and state["pending"].get("completed") is False
        and all(type(value) in (int, float) and isfinite(value)
                for value in (state.get("ends_at"), state.get("last_action_at"),
                              state["pending"].get("due_at"), state.get("actor_hp"),
                              state.get("player_hp")))
        and (type(enemy_round) is int or type(enemy_round) is float and enemy_round.is_integer())
        and enemy_round >= 0
        and "reconnect_until" in state
        and (state["reconnect_until"] is None
             or type(state["reconnect_until"]) in (int, float) and isfinite(state["reconnect_until"]))
    )


def _abort_invalid(actor, state, now):
    final_result = {"kind": "abort", "reason": "invalid", "finished_at": now}
    validate_final_result(final_result)
    invalid_identity = state.get("identity")
    participant_id = state.get("participant_id")
    player = object_by_id(participant_id) if type(participant_id) is int and participant_id > 0 else None
    if player and player.db.active_duel_actor == actor.pk:
        player.attributes.remove("active_duel_actor")
    generation = state.get("generation")
    actor.db.duel_state = {
        "identity": invalid_identity if isinstance(invalid_identity, str) else uuid4().hex,
        "generation": generation if type(generation) is int and generation > 0 else 1,
        "participant_id": participant_id if player else None, "policy": str(EncounterPolicy.EXCLUSIVE_DUEL),
        "state": "finished", "settled": True, "final_result": final_result,
    }
    after_change(lambda: _unschedule(actor, invalid_identity))
    _publish(actor)


def _refresh(actor, state, now, online=None, *, restart=False):
    if not _valid_state(state):
        _abort_invalid(actor, state, now)
        return None
    player = object_by_id(state["participant_id"])
    reason = _expired(state, now)
    if reason:
        _finish(actor, state, "disconnect" if reason == "disconnect" else "timeout", now, reason)
        return None
    if player is None or player.db.active_duel_actor != actor.pk:
        _finish(actor, state, "abort", now, "invalid")
        return None
    online = bool(player.sessions.count()) if online is None else online
    eligible = (_eligible(actor, player, now) if online or player.location is not None
                else _offline_scope(actor, player, state))
    if state["room_id"] != actor.db_location_id or not eligible:
        _finish(actor, state, "abort", now, "invalid")
        return None
    if not online and state["reconnect_until"] is None:
        if restart:
            # 비정상 종료 시 마지막 연결 종료 시각을 복구할 수 없다.
            _finish(actor, state, "abort", now, "unknown_disconnect")
            return None
        state["reconnect_until"] = now + RECONNECT_GRACE
        actor.db.duel_state = state
        _publish(actor)
    elif online and state["reconnect_until"] is not None:
        state["reconnect_until"] = None
        actor.db.duel_state = state
        _publish(actor)
    return player


def reconcile(actor, now=None, *, restart=False):
    now = time() if now is None else now
    if not active_on(actor):
        return
    with world_change(isolate_callbacks=True):
        _lock_actor(actor)
        state = _state(actor)
        if state.get("state") != "active":
            return
        player = _refresh(actor, state, now, restart=restart)
        if player and state["reconnect_until"] is None and now >= state["pending"]["due_at"]:
            _run_tick(actor, state, player, now)
        elif player:
            after_change(lambda: _schedule_current(actor, state["identity"]))


def _run_tick(actor, state, player, now, rng=None):
    encounter = _encounter(actor, state)
    pending = state["pending"]
    context = combat_timer_context(actor, target=player, operation_id=pending["operation_id"],
                                   domain_scope=encounter.identity, generation=encounter.generation, clock=lambda: now)
    from world.shared_combat import duel_round

    def apply(saved):
        kind = duel_round(actor, player, saved, now, rng)
        if kind:
            encounter.save(saved)
            _finish(actor, saved, kind, now)

    apply_tick(encounter, context, apply)
    updated = encounter.current()
    if updated["state"] == "active":
        # 지난 회차는 현재 Pending ID와도 일치할 수 없다.
        updated["completed_operations"] = ()
        encounter.save(updated)
        _plan_round(encounter, now + COMBAT_INTERVAL)
        _publish(actor)


def tick(actor, encounter_id, due_at, *, now=None, rng=None):
    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        _lock_actor(actor)
        state = _state(actor)
        if (state.get("state") != "active" or state.get("identity") != encounter_id
                or (state.get("pending") or {}).get("due_at") != due_at or now < due_at):
            return False
        player = _refresh(actor, state, now)
        if player is None or state["reconnect_until"] is not None:
            return False
        _run_tick(actor, state, player, now, rng)
        return True


def connection_changed(player, *, now=None, online=None):
    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        actor = _active_actor(player)
        if actor is not None:
            _lock_actor(actor)
            state = _state(actor)
            if _refresh(actor, state, now, online):
                after_change(lambda: _schedule_current(actor, state["identity"]))


def _offline_scope(actor, player, state):
    return (actor.capability_active("duel") and actor.capability_active("combat")
            and actor.db_location_id == state["room_id"]
            and getattr(player.db.prelogout_location, "pk", None) == state["room_id"])


def reconnect_room(player, now=None):
    now = time() if now is None else now
    actor = _active_actor(player)
    if actor is not None:
        state = _state(actor)
        if (_valid_state(state) and state["room_id"] == actor.db_location_id and not _expired(state, now)
                and (_offline_scope(actor, player, state) if player.location is None
                     else _eligible(actor, player, now))):
            return actor.location
    return None


def projection(actor, viewer, *, now=None):
    from world.observation import can_perceive, context_for

    state = _state(actor)
    if not state or actor.location is None or not can_perceive(actor, context_for(viewer, observed_at=now)):
        return None
    if state.get("state") == "active" and not _valid_state(state):
        return None
    cooldowns = state.get("cooldowns")
    participant = state.get("participant_id") == viewer.pk
    return {"identity": state.get("identity"), "generation": state.get("generation"),
            "state": state.get("state"), "participant": participant,
            "participant_id": state.get("participant_id") if participant else None,
            "actor_hp": state.get("actor_hp"), "player_hp": state.get("player_hp") if participant else None,
            "ends_at": state.get("ends_at"),
            "idle_at": state["last_action_at"] + IDLE_LIMIT if "last_action_at" in state else None,
            "reconnect_until": state.get("reconnect_until") if participant else None,
            "cooldown_until": cooldowns.get(str(viewer.pk)) if isinstance(cooldowns, dict) else None,
            "final_result": state.get("final_result") if participant else None}
