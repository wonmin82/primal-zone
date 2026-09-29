"""상점 NPC가 참조하는 고정 Credit catalog. 재고 상태는 저장하지 않는다."""

SHOP_CATALOGS = {
    "supply": {
        "flashlight": 30, "battery": 6, "bandage": 8, "field_ration": 4, "water": 3,
    },
    "weapon": {
        "spear": 35, "blade": 60, "jungle_blade": 95, "carbine": 130, "heavy_carbine": 240,
    },
    "armor": {
        "leather_suit": 35, "tactical_vest": 85, "armor": 65, "heavy_suit": 190,
    },
}
