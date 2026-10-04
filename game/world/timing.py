"""게임 타이머의 production 기본값. 실제 서버 설정만 선택적으로 덮어쓴다."""

PRODUCTION_TIMING = {
    "COMBAT_INTERVAL": 2.5,
    "CORPSE_TTL_SECONDS": 30,
    "RESPAWN_DELAY_SECONDS": 15,
    "LOOT_PROTECTION_SECONDS": 120,
    "CLAIM_TIMEOUT_SECONDS": 15,
    "PARTICIPATION_TIMEOUT_SECONDS": 15,
    "ENEMY_RECOVERY_DELAY_SECONDS": 15,
}


def configured_timings(settings):
    timings = {
        key: getattr(settings, "PRIMAL_" + key, default)
        for key, default in PRODUCTION_TIMING.items()
    }
    timings["ENEMY_RECOVERY_DELAY_SECONDS"] = getattr(
        settings, "PRIMAL_ENEMY_RECOVERY_DELAY_SECONDS",
        getattr(settings, "PRIMAL_ENEMY_RESET_SECONDS", PRODUCTION_TIMING["ENEMY_RECOVERY_DELAY_SECONDS"]),
    )
    return timings
