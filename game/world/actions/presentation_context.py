"""한 번의 Action 표현 안에서만 관찰용 조회를 재사용한다."""

import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

_MISSING = object()


@dataclass
class _PresentationContext:
    caller: object
    profile: object = _MISSING
    availability: dict = field(default_factory=dict)


_current = ContextVar("action_presentation_context", default=None)


@contextmanager
def presentation_scope(caller):
    """중첩 호출도 독립 범위를 만들고 예외 시 이전 범위를 복원한다."""
    token = _current.set(_PresentationContext(caller))
    try:
        yield
    finally:
        _current.reset(token)


def profile_snapshot(caller):
    context = _current.get()
    if context is None or context.caller is not caller:
        return caller.profile_snapshot()
    if context.profile is _MISSING:
        context.profile = caller.profile_snapshot()
    # EquipmentProfile의 부가 context도 보존하며 소비자 간 mutable 공유를 막는다.
    return copy.deepcopy(context.profile)


def available(provider, caller, observed_at):
    if not hasattr(provider, "available"):
        return True
    context = _current.get()
    if context is None or context.caller is not caller or observed_at is None:
        return provider.available(caller, observed_at)
    key = (id(provider), observed_at)
    if key not in context.availability:
        # 객체 참조도 보존하여 범위 안에서 id 재사용을 방지한다.
        context.availability[key] = (provider, provider.available(caller, observed_at))
    return context.availability[key][1]
