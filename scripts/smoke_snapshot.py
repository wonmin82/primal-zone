"""격리 서버의 restart 검증용 read-only persistent snapshot. 비밀번호는 조회하지 않는다."""

import json
from contextlib import contextmanager


@contextmanager
def read_snapshot_transaction(connection):
    """격리 snapshot 연결만 DEFERRED로 읽고 종료 시 항상 rollback한다."""
    assert connection.vendor == "sqlite", "snapshot은 격리 SQLite 전용이다"
    assert connection.get_autocommit() and not connection.in_atomic_block, "snapshot transaction 중첩 금지"
    # smoke의 일반 atomic()은 IMMEDIATE이므로 writer 예약 없이 읽기 snapshot을 고정한다.
    with connection.cursor() as cursor:
        cursor.execute("BEGIN DEFERRED")
    try:
        yield
    finally:
        connection.rollback()


def snapshot():
    from django.conf import settings
    from server.conf.smoke_support import require_smoke

    require_smoke(settings)
    import django

    django.setup()
    import evennia

    evennia._init()
    from django.db import connection
    from evennia import search_tag
    from evennia.utils.dbserialize import deserialize
    from typeclasses.enemies import Enemy
    from typeclasses.explorers import Explorer
    from typeclasses.loot import Corpse, DroppedLoot
    from world.bootstrap import stale_definitions
    from world.environment_state import lifecycle_script
    from world.item_entities import api
    from world.loot_entities.models import CurrencyLoot, LootClaim
    from world.loot_service import native_source, source_entries

    def owned_items(owner):
        # archive profile/storage/db.items는 native restart 보존의 증거가 아니다.
        return {str(item.pk): {"definition": item.definition_id, "quantity": item.quantity,
                               "sequence": item.sequence, "location": item.location_kind,
                               "parent": str(item.parent_item_id) if item.parent_item_id else None,
                               "slot": item.slot, "socket": item.socket, "state": item.state}
                for item in api.items_owned_by(owner)}

    def owned_loot(source):
        items = owned_items(source)
        return {
            "corpse": isinstance(source, Corpse), "native": native_source(source),
            "room": source.db_location_id, "entries": source_entries(source),
            "created_at": source.db.created_at if isinstance(source, Corpse) else None,
            "items": items,
            "claims": {str(row.item_entity_id): {
                "id": row.pk, "reserved_party": row.reserved_party_id,
                "reserved_player": row.reserved_player_id, "assigned_player": row.assigned_player_id,
                "protection_until": row.protection_until,
            } for row in LootClaim.objects.filter(item_entity_id__in=items)},
            "currency": {str(row.pk): {
                "quantity": row.quantity, "reserved_party": row.reserved_party_id,
                "reserved_player": row.reserved_player_id, "protection_until": row.protection_until,
                "shares": {str(share.pk): {"player": share.player_id, "remaining": share.remaining_amount}
                           for share in row.shares.all()},
            } for row in CurrencyLoot.objects.filter(owner_object=source)},
        }

    from time import time

    with read_snapshot_transaction(connection):
        observed_at = time()
        script = lifecycle_script()
        result = {
            "observed_at": observed_at,
            "players": {player.key: {"profile": player.profile_snapshot(), "zone": player.zone,
                                      "home": player.home.db.zone_id, "id": player.id,
                                      "active_weapon": player.db.active_weapon_item_id,
                                      "active_light": player.db.active_light_item_id,
                                      "items": owned_items(player)}
                        for player in Explorer.objects.all() if player.key != "admin"},
            "box": owned_items(search_tag("shared_container", category="primal_interactable")[0]),
            "facilities": deserialize(script.db.facilities),
            "clock": deserialize(script.db.environment)["clock"],
            "enemies": {str(enemy.id): {"state": enemy.db.state, "combatants": list(enemy.db.combatants or []),
                                        "claim": deserialize(enemy.db.claim)} for enemy in Enemy.objects.all()},
            "loot": {str(obj.id): owned_loot(obj)
                     for model in (Corpse, DroppedLoot) for obj in model.objects.all()},
            "stale": stale_definitions(),
        }
        result["completed_at"] = time()
        return result


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False))
