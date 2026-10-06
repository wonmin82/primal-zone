"""확정 V1 드롭: 자원과 special은 독립이며 각 roll에서 최대 하나다."""

LOOT = {
    "scavenger": {"resource": (.30, (("water", .50), ("field_ration", .35), ("bandage", .15))), "special": (("security_goggles", .04), ("non_slip_boots", .04))},
    "hunter": {"resource": (.30, (("bandage", .50), ("field_ration", .30), ("water", .20))), "special": (("shock_absorbing_gloves", .06), ("protection_ring", .04))},
    "sentinel": {"resource": (.25, (("battery", .40), ("ammo_556", .60))), "quantities": {"ammo_556": (2, 5)}, "special": (("portable_analyzer", .08), ("guard_carbine", .07)), "firearms": {"guard_carbine": ("mag_556_short", 2, 6)}},
    "alpha": {"trophy": "fang"},
    "dartclaw": {"resource": (.30, (("bandage", .45), ("field_ration", .35), ("water", .20))), "special": (("jungle_longblade", .03), ("strike_assist_gloves", .035), ("stabilizing_boots", .035))},
    "shellback": {"resource": (.35, (("scrap", 1.0),)), "quantities": {"scrap": (1, 2)}, "special": (("composite_shield", .045), ("marsh_protective_pants", .045), ("regeneration_module", .03))},
    "stalker": {"resource": (.30, (("bandage", .50), ("field_ration", .30), ("water", .20))), "special": (("tactical_pistol", .05), ("tactical_analyzer", .03), ("shooting_stability_gloves", .02), ("suppression_tactical_belt", .02), ("tactical_computing_module", .03)), "firearms": {"tactical_pistol": ("mag_9_standard", 2, 5)}},
    "jungle_apex": {"trophy": "apex_scale"},
}
