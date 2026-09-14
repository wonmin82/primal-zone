"""Small, authored starter zone. Stable IDs are also used in saved player data."""

ITEMS = {
    "machete": {"name": "낡은마체테", "slot": "weapon", "attack": 2, "defense": 0},
    "vest": {"name": "탐사조끼", "slot": "armor", "attack": 0, "defense": 1},
    "blade": {"name": "강철마체테", "slot": "weapon", "attack": 6, "defense": 0},
    "armor": {"name": "강화조끼", "slot": "armor", "attack": 0, "defense": 4},
    "carbine": {"name": "탐사카빈", "slot": "weapon", "attack": 10, "defense": 0},
    "fang": {"name": "우두머리송곳니", "slot": "trophy", "attack": 0, "defense": 0},
    "bandage": {"name": "붕대", "slot": "consumable", "heal": 35},
    "scrap": {"name": "회수부품", "slot": "material"},
}

ENEMIES = {
    "scavenger": {
        "name": "어린청소룡",
        "hp": 24,
        "attack": 5,
        "defense": 0,
        "xp": 22,
        "credits": 8,
        "drop": "blade",
        "chance": 0.25,
    },
    "hunter": {
        "name": "갈퀴사냥룡",
        "hp": 42,
        "attack": 9,
        "defense": 1,
        "xp": 38,
        "credits": 14,
        "drop": "armor",
        "chance": 0.25,
    },
    "sentinel": {
        "name": "고장난경비기",
        "hp": 60,
        "attack": 11,
        "defense": 3,
        "xp": 55,
        "credits": 20,
        "drop": "carbine",
        "chance": 0.15,
    },
    "alpha": {
        "name": "능선의우두머리",
        "hp": 130,
        "attack": 17,
        "defense": 3,
        "xp": 130,
        "credits": 50,
        "drop": "fang",
        "chance": 1.0,
        "boss": True,
    },
}

ROOMS = {
    "dock": {
        "name": "탐사대 부두",
        "safe": True,
        "enemies": [],
        "desc": "안개 너머로 버려진 섬이 드러난다. 윤대장이 낡은 지도를 펼쳐 보인다.\n"
        "북쪽 초지에서 장비를 마련하고 통신탑을 복구하자. 여기서는 휴식과 보급이 가능하다.",
        "hint": "윤대장 대화 · 상점 · 휴식",
        "exits": {"북": "grass"},
    },
    "grass": {
        "name": "바람 부는 초지",
        "enemies": ["scavenger"],
        "desc": "무릎 높이의 풀 사이로 작은 발자국이 이어진다. 첫 사냥에 적당한 곳이다.",
        "hint": "어린청소룡 공격 · 강타 · 상태",
        "exits": {"남": "dock", "동": "wreck", "북": "trail"},
    },
    "wreck": {
        "name": "부서진 수송차",
        "enemies": ["scavenger"],
        "desc": "뒤집힌 수송차에 낡은 보급상자가 걸려 있다. 누군가 남긴 물자를 찾을 수 있을 것 같다.",
        "hint": "보급상자 조사",
        "exits": {"서": "grass"},
    },
    "trail": {
        "name": "발톱 자국 오솔길",
        "enemies": ["hunter"],
        "desc": "나무마다 깊은 발톱 자국이 남아 있다. 초지보다 강한 사냥룡이 이곳을 배회한다.",
        "hint": "장비를 바꾸고 체력을 확인하자.",
        "exits": {"남": "grass", "동": "office", "북": "marsh"},
    },
    "office": {
        "name": "폐쇄된 관리동",
        "enemies": [],
        "desc": "책상 위에 젖은 정비기록이 펼쳐져 있다. 발전기 복구에 필요한 절차가 적혀 있다.",
        "hint": "정비기록 조사",
        "exits": {"서": "trail", "동": "generator"},
    },
    "generator": {
        "name": "멈춰 선 발전실",
        "enemies": ["sentinel"],
        "desc": "경고등만 켜진 발전기 곁을 경비기가 맴돈다. 기록을 읽고 회수부품 3개를 모으면 수리할 수 있다.",
        "hint": "발전기 수리",
        "exits": {"서": "office"},
    },
    "marsh": {
        "name": "물안개 습지",
        "enemies": ["hunter", "sentinel"],
        "desc": "진흙 위로 생물의 흔적과 기계의 궤적이 교차한다. 북쪽 능선에서 낮은 울음소리가 들린다.",
        "hint": "능선 진입 전 강화조끼와 붕대를 준비하자.",
        "exits": {"남": "trail", "북": "ridge"},
    },
    "ridge": {
        "name": "통신탑 능선",
        "enemies": ["alpha"],
        "desc": "통신탑을 둘러싼 덩굴 사이로 거대한 그림자가 움직인다. 전력이 복구되어야 접근할 수 있다.",
        "hint": "우두머리가 몸을 낮추면 다음 공격을 방어하자.",
        "exits": {"남": "marsh"},
    },
}

OPPOSITES = {"북": "n", "남": "s", "동": "e", "서": "w"}
SHOP = {"bandage": 8, "blade": 60, "armor": 65, "carbine": 130}
EXCHANGE = {"blade": 6, "armor": 6, "carbine": 12}


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
