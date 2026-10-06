"""구매 목록과 매입 category. 가격은 아이템 정의가 소유한다."""

SHOP_CATALOGS = {
    "supply": {"purchase_catalog": ("flashlight", "battery", "bandage", "field_ration", "water"), "accepts": ("tool", "consumable")},
    "weapon": {"purchase_catalog": ("cutting_machete", "pioneer_spear", "scout_pistol", "guard_carbine", "folding_shield", "portable_analyzer", "mag_9_small", "mag_9_standard", "mag_556_short", "mag_556_standard", "ammo_9", "ammo_556"), "accepts": ("weapon", "hand_equipment", "magazine", "ammo")},
    "armor": {"purchase_catalog": ("security_goggles", "light_protective_suit", "reinforced_vest", "shock_absorbing_gloves", "emergency_belt", "reinforced_explorer_pants", "non_slip_boots", "focus_ring", "protection_ring", "survival_module"), "accepts": ("armor", "equipment")},
    "outpost_weapon": {"purchase_catalog": ("jungle_longblade", "shattering_spear", "tactical_pistol", "exploration_carbine", "heavy_rifle", "composite_shield", "tactical_analyzer", "emergency_injector", "mag_9_small", "mag_9_standard", "mag_9_extended", "mag_556_short", "mag_556_standard", "mag_556_extended", "mag_762_standard", "mag_762_extended", "ammo_9", "ammo_556", "ammo_762"), "accepts": ("weapon", "hand_equipment", "magazine", "ammo")},
    "outpost_equipment": {"purchase_catalog": ("tracking_goggles", "breathing_mask", "biomonitor", "neural_stabilizing_collar", "tactical_protective_suit", "heavy_protective_suit", "strike_assist_gloves", "shooting_stability_gloves", "medical_tactical_belt", "suppression_tactical_belt", "marsh_protective_pants", "stabilizing_boots", "bio_stability_ring", "mental_focus_ring", "suppression_ring", "medical_ring"), "accepts": ("armor", "equipment")},
}


def accepts(shop_id, definition):
    return definition.get("item_type") in SHOP_CATALOGS.get(shop_id, {}).get("accepts", ())
