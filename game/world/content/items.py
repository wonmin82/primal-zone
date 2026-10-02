"""아이템과 보급 가격. Stable ID는 저장 데이터와 연결된다."""

ITEMS = {
    "flashlight": {
        "value": 30,
        "name": "탐사용손전등", "aliases": ["손전등"], "slot": "tool",
        "description": "교체형 전원을 넣어 켜는 탐사용 광원이다. 현재 장소와 인접한 곳을 비춘다.",
        "light_source": {"strength": 2, "range": 1, "power_type": "flashlight_battery"},
    },
    "battery": {
        "value": 6,
        "name": "건전지", "slot": "consumable",
        "description": "탐사용 광원에 넣는 전원이다. 실제 사용 시간 약 30분을 제공한다.",
        "power_source": {"type": "flashlight_battery", "capacity_seconds": 1800},
    },
    "machete": {"name": "낡은마체테", "slot": "weapon", "attack": 2, "defense": 0},
    "vest": {"name": "탐사조끼", "slot": "armor", "attack": 0, "defense": 1},
    "blade": {"value": 60, "name": "강철마체테", "slot": "weapon", "attack": 6, "defense": 0},
    "armor": {"value": 65, "name": "강화조끼", "slot": "armor", "attack": 0, "defense": 4},
    "carbine": {"value": 130, "name": "탐사카빈", "slot": "weapon", "attack": 10, "defense": 0},
    "spear": {"value": 35, "name": "사냥창", "slot": "weapon", "attack": 4, "defense": 1},
    "jungle_blade": {"value": 95, "name": "정글도", "slot": "weapon", "attack": 8, "defense": 0},
    "heavy_carbine": {"value": 240, "name": "중량카빈", "slot": "weapon", "attack": 12, "defense": 0},
    "leather_suit": {"value": 35, "name": "가죽보호복", "slot": "armor", "attack": 0, "defense": 2},
    "tactical_vest": {"value": 85, "name": "경량전술조끼", "slot": "armor", "attack": 1, "defense": 3},
    "heavy_suit": {"value": 190, "name": "중장방호복", "slot": "armor", "attack": 0, "defense": 6},
    "fang": {"name": "우두머리송곳니", "slot": "trophy", "attack": 0, "defense": 0},
    "bandage": {"value": 8, "name": "붕대", "slot": "consumable", "heal": 35},
    "field_ration": {"value": 4, "name": "야전식량", "slot": "consumable", "heal": 12, "consume_action": "먹어", "description": "탐사 중 간단히 먹을 수 있는 보존식이다. 비전투 중 먹으면 체력을 회복한다."},
    "water": {"value": 3, "name": "정제수", "slot": "consumable", "heal": 6, "consume_action": "마셔", "description": "안전하게 정제한 식수다. 비전투 중 마시면 체력을 조금 회복한다."},
    "scrap": {"name": "회수부품", "slot": "material"},
    "jungle_cell": {
        "name": "밀림 신호전지",
        "transferable": False,
        "slot": "material",
        "description": "선발대가 수몰 도로에 남긴 전지다. 거목 군락의 신호 장치를 가동한다.",
    },
    "apex_scale": {
        "name": "포식자 비늘",
        "slot": "trophy",
        "description": "밀림의 우두머리에게서 얻은 단단한 비늘이다. 탐사 완료를 증명한다.",
    },
}

# 일반 물품은 이동 가능하고 임무 핵심 물품은 정의에서 명시적으로 차단한다.
for definition in ITEMS.values():
    definition.setdefault("transferable", True)

# 행동 선택은 아이템 이름이 아니라 slot만 사용한다.
EQUIPMENT_ACTIONS = {"weapon": "무장", "armor": "착용"}
UNEQUIP_ACTIONS = {"weapon": "해제", "armor": "벗어"}


def find_id(catalog, name):
    """Accept a stable ID or an exact Korean display name, ignoring spaces."""
    normalized = name.replace(" ", "").lower()
    return next(
        (
            key
            for key, value in catalog.items()
            if normalized in [str(name).replace(" ", "").lower()
                              for name in (key, value["name"], *value.get("aliases", []))]
        ),
        None,
    )
