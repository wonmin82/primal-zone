"""구매 목록과 매입 category. 가격은 아이템 정의가 소유한다."""

SHOP_CATALOGS = {
    "supply": {"purchase_catalog": ("flashlight", "battery", "bandage", "field_ration", "water"),
               "accepts": ("tool", "consumable")},
    "weapon": {"purchase_catalog": ("blade", "spear", "carbine"),
               "accepts": ("weapon", "magazine", "ammo")},
    "armor": {"purchase_catalog": ("leather_suit", "armor"), "accepts": ("armor", "equipment")},
    "outpost_weapon": {"purchase_catalog": ("jungle_blade", "heavy_carbine"),
                       "accepts": ("weapon", "magazine", "ammo")},
    "outpost_equipment": {"purchase_catalog": ("tactical_vest", "heavy_suit"),
                          "accepts": ("armor", "equipment")},
}


def accepts(shop_id, definition):
    return definition.get("item_type") in SHOP_CATALOGS.get(shop_id, {}).get("accepts", ())
