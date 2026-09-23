"""아이템과 보급 가격. Stable ID는 저장 데이터와 연결된다."""

ITEMS = {
    "machete": {"name": "낡은마체테", "slot": "weapon", "attack": 2, "defense": 0},
    "vest": {"name": "탐사조끼", "slot": "armor", "attack": 0, "defense": 1},
    "blade": {"name": "강철마체테", "slot": "weapon", "attack": 6, "defense": 0},
    "armor": {"name": "강화조끼", "slot": "armor", "attack": 0, "defense": 4},
    "carbine": {"name": "탐사카빈", "slot": "weapon", "attack": 10, "defense": 0},
    "spear": {"name": "사냥창", "slot": "weapon", "attack": 4, "defense": 1},
    "jungle_blade": {"name": "정글도", "slot": "weapon", "attack": 8, "defense": 0},
    "heavy_carbine": {"name": "중량카빈", "slot": "weapon", "attack": 12, "defense": 0},
    "leather_suit": {"name": "가죽보호복", "slot": "armor", "attack": 0, "defense": 2},
    "tactical_vest": {"name": "경량전술조끼", "slot": "armor", "attack": 1, "defense": 3},
    "heavy_suit": {"name": "중장방호복", "slot": "armor", "attack": 0, "defense": 6},
    "fang": {"name": "우두머리송곳니", "slot": "trophy", "attack": 0, "defense": 0},
    "bandage": {"name": "붕대", "slot": "consumable", "heal": 35},
    "scrap": {"name": "회수부품", "slot": "material"},
    "jungle_cell": {
        "name": "밀림 신호전지",
        "slot": "material",
        "description": "선발대가 수몰 도로에 남긴 전지다. 거목 군락의 신호 장치를 가동한다.",
    },
    "apex_scale": {
        "name": "포식자 비늘",
        "slot": "trophy",
        "description": "밀림의 우두머리에게서 얻은 단단한 비늘이다. 탐사 완료를 증명한다.",
    },
}

OPPOSITES = {"북": "n", "남": "s", "동": "e", "서": "w"}
# 행동 선택은 아이템 이름이 아니라 slot만 사용한다.
EQUIPMENT_ACTIONS = {"weapon": "무장", "armor": "착용"}
SHOP = {
    "bandage": 8,
    "spear": 35,
    "blade": 60,
    "jungle_blade": 95,
    "carbine": 130,
    "heavy_carbine": 240,
    "leather_suit": 35,
    "tactical_vest": 85,
    "armor": 65,
    "heavy_suit": 190,
}
EXCHANGE = {
    "spear": 3,
    "blade": 6,
    "jungle_blade": 9,
    "carbine": 12,
    "heavy_carbine": 24,
    "leather_suit": 3,
    "tactical_vest": 8,
    "armor": 6,
    "heavy_suit": 18,
}


def find_id(catalog, name):
    """Accept a stable ID or an exact Korean display name, ignoring spaces."""
    normalized = name.replace(" ", "").lower()
    return next(
        (
            key
            for key, value in catalog.items()
            if normalized in (key, value["name"].replace(" ", "").lower())
        ),
        None,
    )
