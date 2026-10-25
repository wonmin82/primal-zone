"""전투 참가자와 회차의 최소 계약. 계산·보상 정책은 도메인 Service가 소유한다."""

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from uuid import uuid4

from world.domain_context import identity, validate_context
from world.multiplayer import after_change, world_change
from world.rules import RuleError


@dataclass(frozen=True)
class Combatant:
    entity: object

    @property
    def identity(self):
        return identity(self.entity)

    def snapshot(self):
        if callable(getattr(self.entity, "profile_snapshot", None)):
            return deepcopy(self.entity.profile_snapshot())
        if not callable(getattr(self.entity, "capability_active", None)) or not self.entity.capability_active("combat"):
            raise RuleError("전투 Capability가 활성화된 참가자가 아닙니다.")
        return deepcopy(dict(self.entity.db.combat_state or {}))

    def validate_participation(self, other, permission):
        identity(self.entity)
        identity(other.entity)
        if self.entity.location != other.entity.location or not permission(self, other):
            raise RuleError("현재 전투에 참가할 수 없습니다.")

    def apply(self, effect):
        """Service의 상태 변경 경계에서만 호출한다. 별도 Commit이나 계산식을 갖지 않는다."""
        from world.multiplayer import _context

        if not getattr(_context, "depth", 0):
            raise RuntimeError("전투 효과는 world_change 안에서 적용해야 합니다.")
        state = self.snapshot()
        effect(state)
        if callable(getattr(self.entity, "save_profile", None)):
            self.entity.save_profile(state)
        else:
            self.entity.db.combat_state = state
        return deepcopy(state)


class EncounterPolicy(StrEnum):
    SHARED = "shared"
    EXCLUSIVE_DUEL = "exclusive_duel"
    SIMULATION = "simulation"
    WORLD_EVENT = "world_event"


class PendingState(StrEnum):
    PENDING = "pending"
    DUE = "due"
    COMPLETED = "completed"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True)
class Encounter:
    owner: object
    generation: int

    @property
    def state(self):
        return deepcopy(dict(self.owner.db.encounter_state or {}))

    @property
    def identity(self):
        return f"{identity(self.owner)}:{self.owner.db.combat_identity}:{self.generation}"

    def current(self):
        state = self.state
        if not state or state.get("generation") != self.generation:
            raise RuleError("오래된 전투 회차입니다.")
        return state


def begin_encounter(owner, participants, *, policy=EncounterPolicy.SHARED):
    """Shared의 최소 영속 근거. Duel/미지원 정책 실행은 후속 구현 전 거절한다."""
    if policy != EncounterPolicy.SHARED:
        raise RuleError("아직 실행을 지원하지 않는 Encounter 정책입니다.")
    participant_ids = tuple(identity(entity) for entity in participants)
    if not participant_ids or len(participant_ids) != len(set(participant_ids)):
        raise RuleError("전투 참가자가 비었거나 중복되었습니다.")
    with world_change():
        previous = dict(owner.db.encounter_state or {})
        if previous.get("state") == "active":
            raise RuleError("이미 진행 중인 전투가 있습니다.")
        previous_generation = owner.db.combat_generation
        if previous_generation is not None and (type(previous_generation) is not int or previous_generation < 0):
            raise RuleError("손상된 전투 세대입니다.")
        generation = (previous_generation or 0) + 1
        owner.db.combat_generation = generation
        if not owner.db.combat_identity:
            owner.db.combat_identity = uuid4().hex
        owner.db.encounter_state = {
            "identity": f"{identity(owner)}:{owner.db.combat_identity}:{generation}", "generation": generation,
            "participants": participant_ids, "policy": str(policy), "state": "active",
            "final_result": None, "settled": False, "pending": None, "completed_operations": (),
        }
    return Encounter(owner, generation)


def settle_encounter(encounter, result, settle):
    """종료·정산·완료 근거를 함께 확정한다. 실패는 DB와 Evennia Cache를 함께 복구한다."""
    if type(result) is not dict or not result or not callable(settle):
        raise RuleError("종료 결과와 정산 함수가 필요합니다.")
    with world_change():
        state = encounter.current()
        if state["state"] == "finished" and state["settled"]:
            return False
        if state["state"] != "active" or state["settled"]:
            raise RuleError("종료할 수 없는 전투 상태입니다.")
        settle(state)
        state.update(state="finished", final_result=deepcopy(result), settled=True, pending=None)
        encounter.owner.db.encounter_state = state
    return True


def plan_tick(encounter, *, operation_id, due_at, trigger):
    """호출 누락 시 재구성할 근거를 먼저 저장하고 Commit 뒤 메모리 예약을 촉발한다."""
    if (type(operation_id) is not str or not operation_id or type(due_at) not in (int, float)
            or not isfinite(due_at) or not callable(trigger)):
        raise RuleError("작업 ID와 실행 예정 시각이 필요합니다.")
    with world_change():
        state = encounter.current()
        if state["state"] != "active":
            raise RuleError("종료된 전투에는 공격을 예약할 수 없습니다.")
        if operation_id in state.get("completed_operations", ()):
            return False
        if state.get("pending") and state["pending"]["operation_id"] == operation_id:
            return False
        state["pending"] = {"operation_id": operation_id, "due_at": due_at, "completed": False}
        encounter.owner.db.encounter_state = state
        after_change(lambda: trigger(encounter, operation_id, due_at))
    return True


def pending_state(encounter, context):
    state = encounter.state
    if state.get("generation") != encounter.generation or context.generation != encounter.generation:
        return PendingState.STALE
    if state.get("state") == "finished" and state.get("settled"):
        return PendingState.COMPLETED
    pending = state.get("pending")
    if state.get("state") != "active" or not pending or pending["operation_id"] != context.operation_id:
        return PendingState.INVALID
    if pending["completed"]:
        return PendingState.COMPLETED
    return PendingState.DUE if context.now >= pending["due_at"] else PendingState.PENDING


def apply_tick(encounter, context, apply):
    """중복·오래된 Timer가 게임 효과를 다시 확정하지 않도록 도메인 상태로 판정한다."""
    with world_change():
        validate_context(context, "combat.tick", actor=encounter.owner, domain_scope=encounter.identity,
                         generation=encounter.generation, target=context.target,
                         permission=lambda current: pending_state(encounter, current) == PendingState.DUE)
        state = encounter.current()
        apply(state)
        state["pending"]["completed"] = True
        state["completed_operations"] = (*state.get("completed_operations", ()), context.operation_id)
        encounter.owner.db.encounter_state = state
    return True
