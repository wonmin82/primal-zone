"""격리형 smoke의 설정 계약과 fixture 실행 전 안전 검사."""

from pathlib import Path

from world.timing import PRODUCTION_TIMING

QUICK_TIMING = {
    # 실제 join/state 왕복보다 빠른 공격으로 두 번째 참가자의 첫 피해가
    # 처치 뒤로 밀리지 않도록 공동 전투는 production 공격 기회를 사용한다.
    "COMBAT_INTERVAL": PRODUCTION_TIMING["COMBAT_INTERVAL"],
    # Quick도 실제 SQLite/WebSocket 왕복을 거친다. 첫 state 전송 전에
    # 시체가 사라지지 않도록 명령 관찰 timeout(10초)만큼 창을 확보한다.
    "CORPSE_TTL_SECONDS": 10,
    "RESPAWN_DELAY_SECONDS": 2,
    "LOOT_PROTECTION_SECONDS": 20,
    # 점유/보상 자격 만료는 Quick의 관찰 대상이 아니다. DB·state 전송이
    # 단축 전투 간격보다 오래 걸려도 유효 참가자를 지우지 않도록 production을 쓴다.
    "CLAIM_TIMEOUT_SECONDS": PRODUCTION_TIMING["CLAIM_TIMEOUT_SECONDS"],
    "PARTICIPATION_TIMEOUT_SECONDS": PRODUCTION_TIMING["PARTICIPATION_TIMEOUT_SECONDS"],
    "ENEMY_RECOVERY_DELAY_SECONDS": 2,
}


def smoke_timings(mode):
    if mode not in ("quick", "full"):
        raise ValueError("smoke mode는 quick 또는 full이어야 합니다.")
    return dict(QUICK_TIMING if mode == "quick" else PRODUCTION_TIMING)


def require_smoke(settings):
    """DB에 접근하기 전에 marker, 실제 작업 경로와 SQLite DB를 함께 확인한다."""
    if getattr(settings, "PRIMAL_SMOKE", False) is not True:
        raise RuntimeError("PRIMAL_SMOKE marker 없이 smoke fixture를 실행할 수 없습니다.")
    run = Path(settings.PRIMAL_SMOKE_RUN_DIR).resolve()
    database = settings.DATABASES["default"]
    if (
        not (run / ".primal-smoke").is_file()
        or Path(settings.GAME_DIR).resolve() != run / "game"
        or database["ENGINE"] != "django.db.backends.sqlite3"
        or Path(database["NAME"]).resolve() != run / "evennia-smoke.sqlite3"
    ):
        raise RuntimeError("smoke 전용 작업 경로와 SQLite DB가 일치하지 않습니다.")
