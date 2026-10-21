"""생존 격리 서버의 DB를 query_only로 읽는다. 출력은 실행 중 Assertion 전용이다."""

import json


def _timing_snapshot():
    """초기화 비용 없이 현재 격리 SQLite만 읽는 시간 관측 전용 projection."""
    import base64
    import io
    import os
    import pickle
    import sqlite3
    from contextlib import closing
    from pathlib import Path
    from uuid import UUID

    class PlainUnpickler(pickle.Unpickler):
        def find_class(self, module, name):
            raise ValueError('시간 관측 Attribute는 내장 데이터만 허용')

    def attribute(connection, identity, key):
        rows = connection.execute(
            'SELECT a.db_value FROM typeclasses_attribute a '
            'JOIN objects_objectdb_db_attributes j ON j.attribute_id=a.id '
            'WHERE j.objectdb_id=? AND a.db_key=? AND a.db_category IS NULL', (identity, key)).fetchall()
        if len(rows) != 1:
            raise ValueError('시간 관측 Attribute 소실 또는 중복')
        return PlainUnpickler(io.BytesIO(base64.b64decode(rows[0][0], validate=True))).load()

    # snapshot()의 sessions()가 소유 경로/marker/DB를 먼저 검증한다. fallback 없음.
    database = Path(os.environ['PRIMAL_BROWSER_DB']).resolve()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only = ON')
        connection.execute('BEGIN')
        players, connected = {}, {}
        for row in connection.execute('SELECT id, db_key, db_location_id, db_sessid FROM objects_objectdb '
                                      'WHERE db_typeclass_path=?', ('typeclasses.explorers.Explorer',)):
            connected[row['db_key']] = [value for value in (row['db_sessid'] or '').split(',') if value]
            if row['db_key'] != 'admin':
                players[row['db_key']] = {'zone': attribute(connection, row['db_location_id'], 'zone_id')
                                          if row['db_location_id'] else None}
        parties = {str(row['id']): attribute(connection, row['id'], 'state') for row in connection.execute(
            'SELECT id FROM objects_objectdb WHERE db_typeclass_path=?', ('typeclasses.parties.Party',))}
        doors = [dict(row) for row in connection.execute('SELECT * FROM door_entities_door ORDER BY door_id')]
        for door in doors:
            door['aliases'] = json.loads(door['aliases'])
            door['lockable'] = bool(door['lockable'])
        items = [dict(row) for row in connection.execute('SELECT * FROM item_entities_itementity ORDER BY sequence')]
        for item in items:
            item['state'] = json.loads(item['state'])
            for field in ('id', 'parent_item_id'):
                if item[field] is not None:
                    item[field] = str(UUID(item[field]))
        claims = [dict(row) for row in connection.execute('SELECT * FROM loot_entities_lootclaim ORDER BY id')]
        for claim in claims:
            claim['item_entity_id'] = str(UUID(claim['item_entity_id']))
        return {'players': players, 'parties': parties, 'doors': doors, 'items': items,
                'claims': claims, 'sessions': connected}


def snapshot(*, timing=False):
    from browser_probe import sessions
    sessions()  # ROOT/work/smoke 소유 경로·marker·명시 DB 일치를 초기화 전에 확인한다.
    if timing:
        return _timing_snapshot()
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
    from django.db.models import Q
    from evennia.objects.models import ObjectDB
    from evennia.utils.dbserialize import deserialize
    from typeclasses.explorers import Explorer
    from typeclasses.loot import Corpse
    from typeclasses.parties import Party
    from world.content import ROOMS
    from world.door_entities.models import Door, DoorInstallation
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot, CurrencyLootShare, LootClaim
    from world.selection_numbers.models import NumberScope, SelectionNumber
    players = {}
    for player in Explorer.objects.all():
        if player.key == "admin":
            continue
        profile = player.profile_snapshot()
        players[player.key] = {"id": player.pk, "zone": player.zone, "profile": profile,
                               "prelogout_zone": getattr(player.db.prelogout_location, 'db', None).zone_id if player.db.prelogout_location else None,
                               "party_id": player.db.party_id, "session_ids": list(player.db.session_ids or [])}
    journals = list(DoorInstallation.objects.order_by("door_id").values())
    # 정적 routes는 이동 계획 전용이다. 영속 비교는 실제 ObjectDB/Tag/Attribute다.
    exits = []
    for obj in ObjectDB.objects.filter(Q(db_destination__isnull=False) | Q(db_tags__db_category="primal_zone_exit")).distinct().order_by("pk"):
        exits.append({"pk": obj.pk, "key": obj.db_key, "location_pk": obj.db_location_id,
                      "destination_pk": obj.db_destination_id, "typeclass": obj.db_typeclass_path,
                      "managed_ids": sorted(obj.tags.get(category="primal_zone_exit", return_list=True)),
                      "door_id": obj.db.door_id,
                      "installation_ids": sorted(j["door_id"] for j in journals if any(e["exit_pk"] == obj.pk for e in j["endpoints"]))})
    rooms = {tag: obj.pk for obj in ObjectDB.objects.filter(db_tags__db_category="primal_zone_room").distinct()
             for tag in obj.tags.get(category="primal_zone_room", return_list=True)}
    race_room = ObjectDB.objects.filter(db_key="Phase3 경합 방").first()
    return {"players": players, "parties": {str(p.pk): p.state() for p in Party.objects.all()},
            "phase3_race": deserialize(race_room.db.phase3_race) if race_room else None,
            "exits": exits, "rooms": rooms,
            "doors": list(Door.objects.order_by("door_id").values()),
            "installations": journals,
            "items": list(ItemEntity.objects.order_by("sequence").values()),
            "claims": list(LootClaim.objects.order_by("pk").values()),
            "currency": list(CurrencyLoot.objects.order_by("pk").values()),
            "shares": list(CurrencyLootShare.objects.order_by("pk").values()),
            "number_scopes": list(NumberScope.objects.order_by("pk").values()),
            "selection_numbers": list(SelectionNumber.objects.order_by("pk").values()),
            "legacy_loot": {str(c.pk): list(c.db.entries or []) for c in Corpse.objects.all()},
            "routes": {key: data["exits"] for key, data in ROOMS.items()}}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--timing', action='store_true')
    print(json.dumps(snapshot(timing=parser.parse_args().timing), ensure_ascii=False, default=str))
