"""빈 DB와 Door 이전 스키마를 별도 프로세스/임시 SQLite에서 업그레이드한다."""

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

SCHEMA_CHECK = r'''
import os
import django
import sqlite3
from django.conf import settings
settings.DATABASES["default"]["NAME"] = os.environ["PZ_DOOR_SCHEMA_DB"]
settings.TEST_ENVIRONMENT = True
django.setup()
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

existing = os.environ["PZ_DOOR_SCHEMA_EXISTING"] == "1"
if existing:
    executor = MigrationExecutor(connection)
    executor.migrate([node for node in executor.loader.graph.leaf_nodes() if node[0] != "door_entities"])
    call_command("migrate", "door_entities", "zero", verbosity=0, interactive=False)
    import evennia
    evennia._init()
    from evennia.objects.models import ObjectDB
    from world.item_entities import api
    from world.item_runtime import maintenance
    from world import rules
    token = maintenance.set(True)
    from evennia import create_object
    from world.content import ROOMS
    from world.content.doors import DOORS
    rooms, original_exits = {}, []
    for data in DOORS.values():
        for origin, direction, target in data["endpoints"]:
            for zone in (origin, target):
                if zone not in rooms:
                    rooms[zone] = create_object("typeclasses.zone_rooms.ZoneRoom", key=ROOMS[zone]["name"])
                    rooms[zone].db.zone_id = zone
                    rooms[zone].tags.add(zone, category="primal_zone_room")
            obj = create_object("typeclasses.exits.Exit", key=direction, location=rooms[origin], destination=rooms[target])
            obj.tags.add(origin + ":" + direction, category="primal_zone_exit")
            original_exits.append((obj.pk, obj.db_location_id, obj.db_destination_id))
    player = create_object("typeclasses.explorers.Explorer", key="보존탐사자")
    player.db.profile = {**rules.new_profile(), "credits": 123, "visited": ["dock"]}
    api.create_item("bandage", quantity=7, location_kind="inventory", owner_object=player)
    maintenance.reset(token)
    def rows():
        with connection.cursor() as cursor:
            return {table: tuple(cursor.execute('SELECT * FROM "' + table + '" ORDER BY 1').fetchall())
                    for table in connection.introspection.table_names() if table != "django_migrations"}
    before = rows()
    # 이미 저장된 fixture DB의 격리 복제본만 업그레이드한다.
    clone_name = settings.DATABASES["default"]["NAME"] + ".clone"
    with sqlite3.connect(clone_name) as clone:
        connection.connection.backup(clone)
    connection.close()
    connection.settings_dict["NAME"] = clone_name
call_command("migrate", verbosity=0, interactive=False)
if existing:
    after = rows()
    assert all(all(row in after[table] for row in records) for table, records in before.items()), "기존 행 변경/소실"
    assert player.profile_snapshot()["credits"] == 123
    assert api.ItemEntity.objects.get(definition_id="bandage").quantity == 7
else:
    import evennia
    evennia._init()
from world.bootstrap import build_world
from world.door_entities.models import Door, DoorInstallation
from unittest.mock import patch
with patch("world.doors.time", return_value=100):
    build_world()
assert Door.objects.count() == DoorInstallation.objects.count() == 2
if existing:
    assert [(obj.pk, obj.db_location_id, obj.db_destination_id)
            for pk, _, _ in original_exits for obj in [ObjectDB.objects.get(pk=pk)]] == original_exits
assert Door.objects.get(door_id="recovery_room_door").auto_close_at == 160
before_doors = list(Door.objects.values())
with patch("world.doors.time", return_value=200):
    build_world()
assert list(Door.objects.values()) == before_doors
call_command("makemigrations", "door_entities", check=True, dry_run=True, verbosity=0)
print("Door schema PASS: " + ("existing rows preserved" if existing else "empty database"))
'''


class DoorSchemaTests(SimpleTestCase):
    def verify_schema(self, existing):
        with TemporaryDirectory(prefix="pz-door-schema-") as directory:
            result = subprocess.run([sys.executable, "-c", SCHEMA_CHECK],
                                    cwd=Path(__file__).resolve().parents[1],
                                    env={**os.environ, "DJANGO_SETTINGS_MODULE": "server.conf.settings_test",
                                         "PYTHONUTF8": "1", "PZ_DOOR_SCHEMA_DB": str(Path(directory) / "isolated.sqlite3"),
                                         "PZ_DOOR_SCHEMA_EXISTING": str(int(existing))},
                                    capture_output=True, text=True, encoding="utf-8", timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Door schema PASS", result.stdout)

    def test_empty_database_migrate_first_install_and_rebootstrap(self):
        self.verify_schema(False)

    def test_existing_schema_preserves_profile_native_items_and_all_old_rows(self):
        self.verify_schema(True)
