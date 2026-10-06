"""Phase 6 변환의 유일한 legacy → 최종 stable ID 매핑."""

LEGACY_ITEM_MAPPING = {
    "machete": "explorer_machete", "vest": "expedition_workwear",
    "blade": "cutting_machete", "spear": "pioneer_spear",
    "jungle_blade": "jungle_longblade", "carbine": "guard_carbine",
    "heavy_carbine": "heavy_rifle", "leather_suit": "light_protective_suit",
    "armor": "reinforced_vest", "tactical_vest": "tactical_protective_suit",
    "heavy_suit": "heavy_protective_suit",
}

STARTER_EQUIPMENT = ("explorer_machete", "expedition_workwear")
BOSS_REWARDS = {"radio_tower": "ridge_predator_mark", "deep_jungle": "predator_scale_charm"}
FIXED_DISCOVERY_REWARDS = {"supply_cache": "expedition_tag", "jungle_cache": "mental_stability_module"}
