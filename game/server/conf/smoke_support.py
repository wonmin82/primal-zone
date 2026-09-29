"""격리형 smoke의 설정 계약과 fixture 실행 전 안전 검사."""

from pathlib import Path

from world.timing import PRODUCTION_TIMING

QUICK_TIMING = {
    "COMBAT_INTERVAL": 0.25,
    "CORPSE_TTL_SECONDS": 1,
    "RESPAWN_DELAY_SECONDS": 1,
    "LOOT_PROTECTION_SECONDS": 2,
    "CLAIM_TIMEOUT_SECONDS": 2,
    "PARTICIPATION_TIMEOUT_SECONDS": 2,
    "ENEMY_RESET_SECONDS": 2,
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
