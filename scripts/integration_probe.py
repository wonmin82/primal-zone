"""생존 격리 서버의 DB를 query_only로 읽는다. 출력은 실행 중 Assertion 전용이다."""

import json


def snapshot():
    from browser_probe import sessions
    sessions()  # ROOT/work/smoke 소유 경로·marker·명시 DB 일치를 초기화 전에 확인한다.
    from django.conf import settings
    from server.conf.smoke_support import require_smoke
    require_smoke(settings)
    import django
    django.setup()
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA query_only = ON")
    import evennia
    evennia._init()
    from typeclasses.explorers import Explorer
    from typeclasses.loot import Corpse
    from typeclasses.parties import Party
    from world.content import ROOMS
    from world.door_entities.models import Door, DoorInstallation
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot, CurrencyLootShare, LootClaim
    players = {}
    for player in Explorer.objects.all():
        if player.key == "admin":
            continue
        profile = player.profile_snapshot()
        players[player.key] = {"id": player.pk, "zone": player.zone, "profile": profile,
                               "prelogout_zone": getattr(player.db.prelogout_location, 'db', None).zone_id if player.db.prelogout_location else None,
                               "party_id": player.db.party_id, "session_ids": list(player.db.session_ids or [])}
    return {"players": players, "parties": {str(p.pk): p.state() for p in Party.objects.all()},
            "doors": list(Door.objects.order_by("door_id").values()),
            "installations": list(DoorInstallation.objects.order_by("door_id").values()),
            "items": list(ItemEntity.objects.order_by("sequence").values()),
            "claims": list(LootClaim.objects.order_by("pk").values()),
            "currency": list(CurrencyLoot.objects.order_by("pk").values()),
            "shares": list(CurrencyLootShare.objects.order_by("pk").values()),
            "legacy_loot": {str(c.pk): list(c.db.entries or []) for c in Corpse.objects.all()},
            "routes": {key: data["exits"] for key, data in ROOMS.items()}}


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False, default=str))
