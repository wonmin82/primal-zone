"""Quick/Full 실제 서버 전용 설정. dev.py가 만든 격리 환경에서만 로드한다."""

import os
from pathlib import Path

from server.conf.smoke_support import require_smoke, smoke_timings

# 기본 설정을 읽기 전에도 잘못된 실행을 차단한다. PG 환경 변수는 허용하지 않는다.
_run = Path(os.environ["PRIMAL_SMOKE_RUN_DIR"]).resolve()
if (
    Path.cwd().resolve() != _run / "game"
    or not (_run / ".primal-smoke").is_file()
    or any(key.startswith("PRIMAL_DB_") for key in os.environ)
):
    raise RuntimeError("격리된 smoke 실행 환경이 아닙니다.")

from server.conf.settings import *  # noqa: E402,F403

PRIMAL_SMOKE = True
PRIMAL_SMOKE_RUN_DIR = str(_run)
PRIMAL_SMOKE_MODE = os.environ["PRIMAL_SMOKE_MODE"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(_run / "evennia-smoke.sqlite3"),
        # 재시작 시 Portal과 Server의 SQLite read→write 승격 경합을 직렬화한다.
        "OPTIONS": {"timeout": 30, "transaction_mode": "IMMEDIATE"},
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
NEW_ACCOUNT_REGISTRATION_ENABLED = False
WEBSERVER_INTERFACES = ["127.0.0.1"]
WEBSOCKET_CLIENT_INTERFACE = "127.0.0.1"
WEBSERVER_PORTS = [(int(os.environ["PRIMAL_SMOKE_HTTP"]), int(os.environ["PRIMAL_SMOKE_INTERNAL"]))]
WEBSOCKET_CLIENT_PORT = int(os.environ["PRIMAL_SMOKE_WS"])
WEBSOCKET_CLIENT_URL = f"ws://127.0.0.1:{WEBSOCKET_CLIENT_PORT}"
AMP_PORT = int(os.environ["PRIMAL_SMOKE_AMP"])
AMP_HOST = AMP_INTERFACE = "127.0.0.1"
SSH_ENABLED = SSL_ENABLED = TELNET_ENABLED = False

for _key, _value in smoke_timings(PRIMAL_SMOKE_MODE).items():
    globals()["PRIMAL_" + _key] = _value

# 초기화/fixture와 동일한 DB guard를 설정 로드 시에도 적용한다.
import sys  # noqa: E402

require_smoke(sys.modules[__name__])
