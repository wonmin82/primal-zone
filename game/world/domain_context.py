"""사용자 인증과 좁은 서버 이벤트 권한을 구별하는 실행 문맥."""

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from time import time
from uuid import UUID

from world.rules import RuleError

_SERVER_SEAL = object()


class Origin(StrEnum):
    PLAYER = "player"
    AI = "ai"
    TIMER = "timer"
    LIFECYCLE = "lifecycle"


def identity(entity):
    """표시 이름과 독립적인 실제 영속 객체 식별자."""
    value = getattr(entity, "pk", None)
    if not (type(value) is int and value > 0 or isinstance(value, UUID)):
        raise RuleError("실행 주체 또는 대상의 영속 정체성을 확인할 수 없습니다.")
    return str(value)


@dataclass(frozen=True)
class Principal:
    origin: Origin
    actor_id: str
    domain_scope: str
    operations: frozenset[str]
    operation_id: str
    generation: int | None = None
    target_id: str | None = None
    session: object = field(default=None, repr=False, compare=False)
    _seal: object = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class DomainExecutionContext:
    origin: Origin
    principal: Principal
    actor: object
    target: object | None
    operation_id: str
    domain_scope: str
    clock: object = field(default=time, repr=False, compare=False)
    generation: int | None = None

    @property
    def now(self):
        value = self.clock()
        if type(value) not in (int, float) or not isfinite(value):
            raise RuleError("실행 기준 시각이 유효하지 않습니다.")
        return value


def _context(origin, actor, target, operation_id, domain_scope, operations, clock, generation=None, session=None):
    if (type(operation_id) is not str or not operation_id or len(operation_id) > 180
            or type(domain_scope) is not str or not domain_scope or len(domain_scope) > 180
            or not callable(clock) or generation is not None and (type(generation) is not int or generation < 1)):
        raise RuleError("도메인 실행 식별자·범위·세대를 확인하세요.")
    principal = Principal(origin, identity(actor), domain_scope, frozenset(operations), operation_id, generation,
                          identity(target) if target is not None else None, session, _SERVER_SEAL)
    context = DomainExecutionContext(origin, principal, actor, target, operation_id, domain_scope, clock, generation)
    context.now
    return context


def for_player(caller, session, *, operation_id, domain_scope, target=None, clock=time):
    from world.actions.gateway import require_session

    require_session(caller, session)
    return _context(Origin.PLAYER, caller, target, operation_id, domain_scope, ("player",), clock, session=session)


def combat_timer_context(actor, *, operation_id, domain_scope, generation, target=None, clock=time):
    """신뢰된 서버 Combat Timer 진입점만 호출한다. 웹 입력은 이 문맥을 받지 않는다."""
    return _context(Origin.TIMER, actor, target, operation_id, domain_scope, ("combat.tick",), clock, generation)


def respawn_context(actor, *, operation_id, domain_scope, generation, clock=time):
    return _context(Origin.LIFECYCLE, actor, None, operation_id, domain_scope, ("respawn",), clock, generation)


def recovery_context(actor, *, operation_id, domain_scope, clock=time):
    return _context(Origin.LIFECYCLE, actor, None, operation_id, domain_scope, ("recovery",), clock)


def validate_context(context, operation, *, actor, domain_scope, generation=None, target=None, permission):
    """권한 증거와 현재 도메인 상태를 함께 검증한다. Timer에 전역 권한을 주지 않는다."""
    if not isinstance(context, DomainExecutionContext) or not isinstance(context.principal, Principal):
        raise RuleError("인증된 도메인 실행 문맥이 필요합니다.")
    principal = context.principal
    target_id = identity(target) if target is not None else None
    if (principal._seal is not _SERVER_SEAL or context.origin != principal.origin
            or principal.actor_id != identity(actor) or identity(context.actor) != identity(actor)
            or context.domain_scope != domain_scope or principal.domain_scope != domain_scope
            or context.operation_id != principal.operation_id
            or context.generation != generation or principal.generation != generation
            or principal.target_id != target_id
            or (identity(context.target) if context.target is not None else None) != target_id):
        raise RuleError("도메인 실행의 주체·대상·범위·세대가 바뀌었습니다.")
    from evennia.objects.models import ObjectDB

    target_exists = target is None or target._meta.model._default_manager.filter(pk=target.pk).exists()
    if not ObjectDB.objects.filter(pk=actor.pk).exists() or not target_exists:
        raise RuleError("도메인 실행의 주체 또는 대상이 사라졌습니다.")
    if principal.origin == Origin.PLAYER:
        from world.actions.gateway import require_session

        require_session(actor, principal.session)
    elif operation not in principal.operations:
        raise RuleError("서버 이벤트에 이 도메인 효과의 실행 권한이 없습니다.")
    if not callable(permission) or not permission(context):
        raise RuleError("현재 도메인 상태에서 이 효과를 실행할 수 없습니다.")
    context.now
    return context
