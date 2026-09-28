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
