"""플레이 DB·운영 해시와 분리된 자동 테스트 전용 설정."""

from server.conf.settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    },
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
TEST_RUNNER = "server.conf.test_runner.PrimalTestRunner"
# 이전 단계 fixture는 명시적 historical audit다. cutover 회귀는 이 설정을 끄고 검증한다.
ITEM_MIGRATION_AUDIT = True
ITEM_MIGRATION_TEST_OVERRIDE = True
