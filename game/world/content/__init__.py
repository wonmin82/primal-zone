"""지역별 콘텐츠를 합쳐 기존 world.content import surface를 유지한다."""

from .deep_jungle import ENEMIES as JUNGLE_ENEMIES
from .deep_jungle import ROOMS as JUNGLE_ROOMS
from .items import EQUIPMENT_ACTIONS, EXCHANGE, ITEMS, OPPOSITES, SHOP, find_id
from .starter import ENEMIES as STARTER_ENEMIES
from .starter import ROOMS as STARTER_ROOMS

REGION_ENEMIES = {"outpost": STARTER_ENEMIES, "deep_jungle": JUNGLE_ENEMIES}
ENEMIES = {
    identity: data for enemies in REGION_ENEMIES.values() for identity, data in enemies.items()
}
ROOMS = {**STARTER_ROOMS, **JUNGLE_ROOMS}
REGIONS = {
    "outpost": {
        "name": "탐사대 전초구역",
        "recommended_level": (1, 4),
        "entry": "dock",
        "rooms": tuple(STARTER_ROOMS),
    },
    "deep_jungle": {
        "name": "깊은 밀림",
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
    "SHOP",
    "EXCHANGE",
    "OPPOSITES",
    "EQUIPMENT_ACTIONS",
    "find_id",
    "ENEMIES",
    "ROOMS",
    "REGIONS",
    "REGION_ENEMIES",
    "ROOM_REGION",
    "spawn_id_for",
]
