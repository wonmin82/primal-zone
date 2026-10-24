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
    from time import time

    from django.db import connection
    from evennia import search_tag
    from evennia.utils.dbserialize import deserialize
    from server.conf.smoke_startstop import owned_items, owned_loot
    from typeclasses.enemies import Enemy
    from typeclasses.explorers import Explorer
    from typeclasses.loot import Corpse, DroppedLoot
    from world.bootstrap import stale_definitions
    from world.environment_state import lifecycle_script

    with read_snapshot_transaction(connection):
        observed_at = time()
        script = lifecycle_script()
        result = {
            "observed_at": observed_at,
            "loot_births": {str(enemy.pk): deserialize(enemy.db.smoke_loot_births) or []
                            for enemy in Enemy.objects.all()},
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
                                        "claim": deserialize(enemy.db.claim), "room": enemy.db_location_id} for enemy in Enemy.objects.all()},
            "loot": {str(obj.id): owned_loot(obj)
                     for model in (Corpse, DroppedLoot) for obj in model.objects.all()},
            "stale": stale_definitions(),
        }
        result["completed_at"] = time()
        return result


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False))
