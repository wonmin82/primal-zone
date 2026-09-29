"""지역별 콘텐츠를 합쳐 기존 world.content import surface를 유지한다."""

from .deep_jungle import ENEMIES as JUNGLE_ENEMIES
from .deep_jungle import ROOMS as JUNGLE_ROOMS
from .directions import (
    DIRECTION_ALIASES,
    DIRECTION_ORDER,
    DIRECTIONS,
    OPPOSITE_DIRECTIONS,
    ordered_directions,
)
from .economy import SALVAGE_CREDIT_RATE
from .headquarters import ROOMS as HEADQUARTERS_ROOMS
from .items import EQUIPMENT_ACTIONS, ITEMS, UNEQUIP_ACTIONS, find_id
from .shops import SHOP_CATALOGS
from .starter import ENEMIES as STARTER_ENEMIES
from .starter import ROOMS as STARTER_ROOMS

# 기존 import surface만 유지한다. OPPOSITES의 의미는 방향 alias다.
OPPOSITES = DIRECTION_ALIASES

REGION_ENEMIES = {"outpost": STARTER_ENEMIES, "deep_jungle": JUNGLE_ENEMIES}
ENEMIES = {
    identity: data for enemies in REGION_ENEMIES.values() for identity, data in enemies.items()
}
ROOMS = {**HEADQUARTERS_ROOMS, **STARTER_ROOMS, **JUNGLE_ROOMS}
REGIONS = {
    "headquarters": {
        "name": "탐사대 본부",
        "weather_zone": "island",
        "recommended_level": (1, 1),
        "entry": "staging_room",
        "rooms": tuple(HEADQUARTERS_ROOMS),
    },
    "outpost": {
        "name": "탐사대 전초구역",
        "weather_zone": "island",
        "recommended_level": (1, 4),
        "entry": "dock",
        "rooms": tuple(STARTER_ROOMS),
    },
    "deep_jungle": {
        "name": "깊은 밀림",
        "weather_zone": "island",
        "recommended_level": (4, 10),
        "entry": "jungle_edge",
        "rooms": tuple(JUNGLE_ROOMS),
    },
}
ROOM_REGION = {zone: region for region, data in REGIONS.items() for zone in data["rooms"]}


def spawn_id_for(zone, enemy_id):
    """기존 zone:enemy 태그를 기본값으로 유지하며 이동할 spawn만 ID를 고정한다."""
    return ROOMS[zone].get("spawn_ids", {}).get(enemy_id, f"{zone}:{enemy_id}")


__all__ = [
    "ITEMS",
    "SHOP_CATALOGS",
    "SALVAGE_CREDIT_RATE",
    "OPPOSITES",
    "DIRECTIONS",
    "DIRECTION_ORDER",
    "DIRECTION_ALIASES",
    "OPPOSITE_DIRECTIONS",
    "ordered_directions",
    "EQUIPMENT_ACTIONS",
    "UNEQUIP_ACTIONS",
    "find_id",
    "ENEMIES",
    "ROOMS",
    "REGIONS",
    "REGION_ENEMIES",
    "ROOM_REGION",
    "spawn_id_for",
]
