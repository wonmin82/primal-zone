"""신뢰된 콘텐츠 Service의 직접·보조 함수에서 미완료 실행을 거절한다."""

import inspect
from types import CoroutineType, FunctionType, GeneratorType

from twisted.internet.defer import Deferred


def validate_handler(handler):
    visited = set()
    unsafe = {"Deferred", "callLater", "deferLater", "ensureDeferred", "get_input", "execute_cmd"}

    def walk(callback):
        if inspect.iscoroutinefunction(callback) or inspect.isgeneratorfunction(callback) or inspect.isasyncgenfunction(callback):
            raise ValueError("동기 완료를 보장하지 않는 Handler")
        if not isinstance(callback, FunctionType) or callback in visited:
            return
        visited.add(callback)
        if len(visited) > 128 or unsafe.intersection(callback.__code__.co_names):
            raise ValueError("동기 완료를 보장하지 않는 보조 함수")
        values = inspect.getclosurevars(callback)
        for value in (*values.nonlocals.values(), *values.globals.values()):
            if isinstance(value, (Deferred, CoroutineType, GeneratorType)) or value is Deferred:
                raise ValueError("미완료 실행 객체를 가진 Handler")
            if isinstance(value, FunctionType):
                walk(value)

    walk(handler)
