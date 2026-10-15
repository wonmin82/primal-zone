"""이전 스키마 테스트 Fixture 생성만 명시적으로 분리한다. 운영 fallback이 아니다."""

from contextlib import contextmanager
from contextvars import ContextVar

_historical = ContextVar("b1_historical_schema_fixture", default=False)


def enabled():
    return not _historical.get()


@contextmanager
def historical_schema():
    from django.conf import settings

    if not getattr(settings, "TEST_ENVIRONMENT", False):
        raise RuntimeError("이전 스키마 Fixture는 격리 테스트에서만 허용됩니다.")
    token = _historical.set(True)
    try:
        yield
    finally:
        _historical.reset(token)
