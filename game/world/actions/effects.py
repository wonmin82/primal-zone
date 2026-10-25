"""Service가 명시 호출하는 효과 경계. 순서·의존성과 도메인 멱등성은 Service가 소유한다."""

from contextvars import ContextVar
from dataclasses import dataclass, replace
from types import CoroutineType, MappingProxyType

from django.db import connections
from world.actions.schema import Completion, ExecutionPolicy
from world.multiplayer import after_change, world_change
from world.rules import RuleError

_state_change = ContextVar("action_effect_state_change", default=False)
_effect = ContextVar("action_effect_name", default=None)


@dataclass(frozen=True)
class EffectResult:
    name: str
    status: object
    completion: Completion
    messages: tuple = ()
    changed: bool = False
    duplicate: bool = False


class ReadOnlyViolation(RuleError):
    """조회 효과가 영속 쓰기를 시도했다. 정상 효과로 조용히 승격하지 않는다."""


def _read_query(sql):
    # 알 수 없는 SQL은 허용하지 않는다. WITH/PRAGMA도 쓰기를 포함할 수 있다.
    keyword = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
    return keyword in {"SELECT", "EXPLAIN", "SAVEPOINT", "RELEASE", "ROLLBACK", "BEGIN", "COMMIT"}


class _WriteGuard:
    def __init__(self, *, composite=False):
        self.composite = composite
        self.violated = False

    def __call__(self, execute, sql, params, many, context):
        if not _read_query(sql) and not (self.composite and _state_change.get()):
            self.violated = True
            raise ReadOnlyViolation("READ_ONLY 효과에서는 영속 게임 상태를 변경할 수 없습니다.")
        return execute(sql, params, many, context)


def _call(handler, context):
    from world.actions.gateway import ActionResult, synchronous

    synchronous(handler)
    result = handler(context)
    if isinstance(result, CoroutineType):
        result.close()
    if not isinstance(result, ActionResult):
        raise RuleError("행동의 동기 완료 결과를 확인할 수 없습니다.")
    return result


def _guarded_call(handler, context, *, composite=False):
    from contextlib import ExitStack

    guard = _WriteGuard(composite=composite)
    with ExitStack() as stack:
        for connection in connections.all():
            stack.enter_context(connection.execute_wrapper(guard))
        result = _call(handler, context)
        # Handler가 DB 오류를 잡고 성공을 반환해도 금지된 쓰기를 성공으로 보고하지 않는다.
        if guard.violated or not composite and result.changed:
            raise ReadOnlyViolation("READ_ONLY 효과에서 상태 변경을 시도했습니다.")
        return result


def invoke_service(service, context):
    """기존 단일 Service도 동일 정책 경계를 사용한다. Gateway가 원자적 변경을 소유한다."""
    if service.policy == ExecutionPolicy.READ_ONLY:
        return _guarded_call(service.handler, context)
    return _call(service.handler, context)


def invoke_hook(handler, *args, readonly=False):
    """준비/잠금 Hook도 읽기 전용 또는 복합 효과의 쓰기 경계를 우회하지 않는다."""
    from contextlib import ExitStack

    from world.actions.gateway import synchronous

    synchronous(handler)
    if not readonly:
        return handler(*args)
    guard = _WriteGuard()
    with ExitStack() as stack:
        for connection in connections.all():
            stack.enter_context(connection.execute_wrapper(guard))
        result = handler(*args)
        if guard.violated:
            raise ReadOnlyViolation("READ_ONLY Hook에서 상태 변경을 시도했습니다.")
        return result


def invoke_composite(service, context):
    """효과 순서를 실행하는 엔진이 아니라 도메인 Service의 명시 호출을 검증한다."""
    try:
        result = _guarded_call(service.handler, context, composite=True)
    except Exception:
        # 효과 밖 금지된 쓰기가 Evennia 메모리 값을 먼저 바꿨을 수 있다.
        # 이미 확정한 독립 효과를 되돌리지 않고 현재 DB 기준 캐시 복구 계약을 사용한다.
        try:
            with world_change():
                raise ReadOnlyViolation("복합 Service의 선언된 효과 경계를 확인하세요.")
        except ReadOnlyViolation:
            pass
        raise
    actual = tuple(context.effect_results)
    if result.effects and result.effects != actual:
        raise RuleError("실행한 효과와 복합 결과가 일치하지 않습니다.")
    return replace(result, effects=actual, changed=any(effect.changed for effect in actual))


def run_effect(context, name, handler):
    """사전 선언한 한 효과를 재검증하고 확정한다. 의존성·분기는 호출 도메인의 코드다."""
    from world.actions.gateway import (
        ActionResult,
        ResultAbort,
        ResultStatus,
        _lock_roles,
        revalidate_context,
    )
    from world.multiplayer import world_change

    if _effect.get() is not None:
        raise RuleError("효과 내부에서 다른 효과 경계로 승격할 수 없습니다.")
    service = context.index.services[context.binding.service_id]
    declaration = next(iter([effect for effect in service.effects if effect.name == name]), None)
    if declaration is None:
        raise RuleError("선언하지 않은 도메인 효과입니다.")
    previous = next(iter([effect for effect in context.effect_results if effect.name == name]), None)
    if previous is not None:
        return replace(previous, duplicate=True)
    active = _effect.set(name)
    state = _state_change.set(declaration.policy == ExecutionPolicy.STATE_CHANGE)
    try:
        try:
            with world_change():
                if declaration.policy == ExecutionPolicy.STATE_CHANGE:
                    if service.locker is None:
                        _lock_roles(context.caller, context.invocation)
                    else:
                        service.locker(context.caller, context.invocation)
                current = revalidate_context(context)
                current_context = replace(context, roles=MappingProxyType(current))
                result = (_guarded_call(handler, current_context)
                          if declaration.policy == ExecutionPolicy.READ_ONLY else _call(handler, current_context))
                if result.effects:
                    raise RuleError("단일 효과는 복합 결과를 반환할 수 없습니다.")
                if result.status != ResultStatus.SUCCESS:
                    raise ResultAbort(result)
                if result.changed:
                    from typeclasses.explorers import Explorer

                    after_change(lambda: [player.push_state() for player in Explorer.objects.all()
                                          if player.sessions.count()])
        except ResultAbort as abort:
            result = abort.result
        except RuleError as error:
            result = ActionResult(ResultStatus.REFUSED, (str(error),))
        except Exception:
            result = ActionResult(ResultStatus.ERROR, ("효과 처리 중 오류가 발생했습니다.",))
    finally:
        _state_change.reset(state)
        _effect.reset(active)
    output = EffectResult(name, result.status, result.completion, result.messages,
                          result.changed if result.status == ResultStatus.SUCCESS else False, result.duplicate)
    context.effect_results.append(output)
    return output
