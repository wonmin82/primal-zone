"""신뢰된 콘텐츠의 일반 Python 함수만 지원하는 동기 Handler 등록 계약.

직접 참조·closure·기본 인자·명시 wrapper에서 확인 가능한 예약/비동기를 거절한다.
동적 attribute 조회나 임의 Python 프로그램의 안전성을 증명하는 sandbox는 아니다.
실제 반환값과 변경 rollback은 Gateway에서 별도로 검증한다.
"""

import inspect
from types import AsyncGeneratorType, CodeType, CoroutineType, FunctionType, GeneratorType

from twisted.internet.defer import Deferred


def validate_handler(handler):
    if not isinstance(handler, FunctionType):
        raise ValueError("Handler는 일반 Python 함수로 선언해야 합니다.")
    visited, containers, code_seen = set(), set(), set()
    unsafe = {"Deferred", "callLater", "callWhenRunning", "callFromThread", "deferLater",
              "deferToThread", "ensureDeferred", "create_task", "ensure_future",
              "get_input", "execute_cmd"}

    def code(callback_code):
        if callback_code in code_seen:
            return
        code_seen.add(callback_code)
        if (len(code_seen) > 256 or unsafe.intersection(callback_code.co_names)
                or callback_code.co_flags & (inspect.CO_COROUTINE | inspect.CO_GENERATOR | inspect.CO_ASYNC_GENERATOR)):
            raise ValueError("동기 완료를 보장하지 않는 함수 본문")
        for constant in callback_code.co_consts:
            if isinstance(constant, CodeType):
                code(constant)

    def value(item):
        if isinstance(item, (Deferred, CoroutineType, GeneratorType, AsyncGeneratorType)) or item is Deferred:
            raise ValueError("미완료 실행 객체를 가진 Handler")
        if isinstance(item, FunctionType):
            walk(item)
        elif type(item) in (tuple, list, dict, set, frozenset):
            if id(item) in containers:
                return
            containers.add(id(item))
            if len(containers) > 256 or len(item) > 256:
                raise ValueError("Handler 참조 검증 범위를 초과했습니다.")
            members = (*item.keys(), *item.values()) if type(item) is dict else item
            for member in members:
                value(member)
        elif callable(item) and not isinstance(item, type):
            # bound method, partial, callable instance와 C wrapper를 일반 함수처럼 통과시키지 않는다.
            raise ValueError("검증할 수 없는 보조 Callable 형식입니다.")

    def walk(callback):
        if inspect.iscoroutinefunction(callback) or inspect.isgeneratorfunction(callback) or inspect.isasyncgenfunction(callback):
            raise ValueError("동기 완료를 보장하지 않는 Handler")
        if not isinstance(callback, FunctionType):
            raise ValueError("보조 Handler는 일반 Python 함수여야 합니다.")
        if callback in visited:
            return
        visited.add(callback)
        if len(visited) > 128:
            raise ValueError("동기 완료를 보장하지 않는 보조 함수")
        code(callback.__code__)
        values = inspect.getclosurevars(callback)
        for item in (*values.nonlocals.values(), *values.globals.values(),
                     *(callback.__defaults__ or ()), *(callback.__kwdefaults__ or {}).values()):
            value(item)
        if "__wrapped__" in callback.__dict__:
            wrapped = callback.__dict__["__wrapped__"]
            if not isinstance(wrapped, FunctionType):
                raise ValueError("검증할 수 없는 wrapper 형식입니다.")
            walk(wrapped)

    walk(handler)
