"""상인이 취급하는 품목만 정의한다. 가격은 ITEMS의 value에서 읽는다."""

SHOP_CATALOGS = {
    "supply": ("flashlight", "battery", "bandage", "field_ration", "water"),
    "weapon": ("spear", "blade", "jungle_blade", "carbine", "heavy_carbine"),
    "armor": ("leather_suit", "tactical_vest", "armor", "heavy_suit"),
}
