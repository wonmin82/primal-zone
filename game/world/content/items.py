"""아이템과 보급 가격. Stable ID는 저장 데이터와 연결된다."""

from world.content.final_items import FINAL_ITEMS

ITEMS = {
    "flashlight": {
        "value": 35,
        "name": "탐사용손전등", "aliases": ["손전등"], "slot": "tool",
        "description": "교체형 전원을 넣어 켜는 탐사용 광원이다. 현재 장소와 인접한 곳을 비춘다.",
        "light_source": {"strength": 2, "range": 1, "power_type": "flashlight_battery", "max_power_seconds": 1800},
    },
    "battery": {
        "value": 8,
        "name": "건전지", "slot": "consumable",
        "description": "탐사용 광원에 넣는 전원이다. 실제 사용 시간 약 30분을 제공한다.",
        "power_source": {"type": "flashlight_battery", "capacity_seconds": 1800},
    },
    "fang": {"name": "우두머리송곳니", "slot": "trophy", "attack": 0, "defense": 0},
    "bandage": {"value": 10, "name": "붕대", "slot": "consumable", "heal": 20},
    "field_ration": {"value": 5, "name": "야전식량", "slot": "consumable", "heal": 12, "consume_action": "먹어", "description": "탐사 중 간단히 먹을 수 있는 보존식이다. 비전투 중 먹으면 체력을 회복한다."},
    "water": {"value": 3, "name": "정제수", "slot": "consumable", "heal": 6, "consume_action": "마셔", "description": "안전하게 정제한 식수다. 비전투 중 마시면 체력을 조금 회복한다."},
    "scrap": {"name": "회수부품", "slot": "material"},
    "generator_repair_part": {
        "name": "정비용 회수부품", "aliases": ["정비부품", "발전기부품"], "slot": "material",
        "item_type": "quest_resource", "stackable": True, "max_stack": 3,
        "unique_per_owner": False, "transferable": False,
        "description": "수송차 보급상자에 보관된 발전기 수리 전용 부품이다.",
        "operation_policy": {operation: operation == "submit" for operation in (
            "drop", "give", "store", "sell", "burn", "consume", "equip", "unequip", "loot", "load", "unload", "submit")},
    },
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

# Phase 3의 탄창·탄약 구조에 Phase 6 최종 가격과 획득 경로를 연결한다.
for identity, name, alias, family, ammo_type, capacity in (
    ("mag_9_small", "9mm 소형탄창", "권총소형", "pistol_9mm", "9mm", 8),
    ("mag_9_standard", "9mm 표준탄창", "권총표준", "pistol_9mm", "9mm", 12),
    ("mag_9_extended", "9mm 확장탄창", "권총확장", "pistol_9mm", "9mm", 18),
    ("mag_556_short", "5.56mm 단축탄창", "카빈단축", "carbine_556", "556mm", 15),
    ("mag_556_standard", "5.56mm 표준탄창", "카빈표준", "carbine_556", "556mm", 20),
    ("mag_556_extended", "5.56mm 확장탄창", "카빈확장", "carbine_556", "556mm", 30),
    ("mag_762_standard", "7.62mm 표준탄창", "중량표준", "rifle_762", "762mm", 8),
    ("mag_762_extended", "7.62mm 확장탄창", "중량확장", "rifle_762", "762mm", 12),
):
    ITEMS[identity] = {"name": name, "aliases": [alias], "slot": "magazine", "stackable": False,
                       "magazine": {"family": family, "ammo_type": ammo_type, "capacity": capacity}}
for identity, name, alias, ammo_type in (
    ("ammo_9", "9mm 권총탄", "권총탄", "9mm"),
    ("ammo_556", "5.56mm 카빈탄", "카빈탄", "556mm"),
    ("ammo_762", "7.62mm 소총탄", "중량탄", "762mm"),
):
    ITEMS[identity] = {"name": name, "aliases": [alias], "slot": "ammo", "ammo_type": ammo_type}

# 출입증은 기존 profile 저장과 무관한 고유 Entity다.
for identity, name, quest in (
    ("outpost_supply_pass", "전초 보급구역 출입증", "radio_tower"),
    ("special_supply_pass", "특수 보급구역 출입증", "deep_jungle"),
):
    ITEMS[identity] = {"name": name, "slot": "credential", "item_type": "credential",
                       "stackable": False, "max_stack": 1, "unique_per_owner": True,
                       "transferable": False, "credential_properties": {"quest": quest},
                       "operation_policy": {operation: operation == "burn" for operation in (
                           "drop", "give", "store", "sell", "consume", "equip", "unequip",
                           "loot", "burn", "load", "unload", "submit")}}

# 최종 장비는 별도 stable ID를 사용한다. 이전 ID 해석은 migration mapping에만 있다.

ITEMS.update(FINAL_ITEMS)
for identity, price in {
    "mag_9_small": 16, "mag_9_standard": 24, "mag_9_extended": 40,
    "mag_556_short": 30, "mag_556_standard": 45, "mag_556_extended": 65,
    "mag_762_standard": 50, "mag_762_extended": 70,
}.items():
    ITEMS[identity].update(value=price, resale_unit_value=price // 2)
for identity, purchase, resale, quantity in (("ammo_9", 2, 1, 12), ("ammo_556", 2, 1, 20), ("ammo_762", 4, 2, 8)):
    ITEMS[identity].update(value=purchase, purchase_unit_value=purchase, resale_unit_value=resale, purchase_quantity=quantity)

# 일반 물품은 이동 가능하고 임무 핵심 물품은 정의에서 명시적으로 차단한다.
for definition in ITEMS.values():
    definition.setdefault("transferable", True)
    # 공통 정의 기본값. 저장 구조의 변환은 명시적인 maintenance tooling이 담당한다.
    definition.setdefault("item_type", definition["slot"])
    definition.setdefault("stackable", definition["slot"] not in ("weapon", "armor", "tool"))
    definition.setdefault("max_stack", None)
    definition.setdefault("unique_per_owner", False)
    definition.setdefault("operation_policy", {
        **{operation: definition["transferable"] for operation in ("drop", "give", "store", "sell")},
        "consume": bool(definition.get("heal") or definition.get("power_source")),
        "submit": definition is ITEMS["jungle_cell"],
        "equip": definition["slot"] in ("weapon", "armor"),
        "unequip": definition["slot"] in ("weapon", "armor"),
        "loot": definition["transferable"],
        "burn": definition["transferable"],
        "load": bool(definition.get("magazine") or definition.get("ammo_type")),
        "unload": bool(definition.get("magazine") or definition.get("ammo_type")),
    })

# 행동 선택은 아이템 이름이 아니라 slot만 사용한다.
EQUIPMENT_ACTIONS = {"weapon": "무장", "armor": "착용"}
UNEQUIP_ACTIONS = {"weapon": "해제", "armor": "벗어"}


def find_id(catalog, name):
    """stable ID·표시명·alias에 공통 대상 정규화를 적용한다."""
    from world.targets import normalized as normalize

    normalized = normalize(name)
    return next(
        (
            key
            for key, value in catalog.items()
            if normalized in [normalize(name)
                              for name in (key, value["name"], *value.get("aliases", []))]
        ),
        None,
    )
