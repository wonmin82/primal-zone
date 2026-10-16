"""명시적인 소지품 Source의 안정 UUID 집합 버전. 번호나 표시명으로 다시 선택하지 않는다."""

import json
from hashlib import sha256


def inventory_version(caller, definition_ids):
    from world.item_entities.models import ItemEntity

    rows = ItemEntity.objects.filter(owner_object=caller, location_kind="inventory", parent_item=None,
                                    definition_id__in=definition_ids).order_by("pk")
    members = tuple([(str(item.pk), item.quantity) for item in rows])
    value = json.dumps((str(caller.pk), tuple(definition_ids), members), separators=(",", ":"))
    return sha256(value.encode()).hexdigest(), members
