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
    from world.selection_numbers.mode import historical_schema
    historical_fixture = historical_schema()
    historical_fixture.__enter__()
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
    historical_fixture.__exit__(None, None, None)
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

RESTART_SEED = r'''
import json
from pathlib import Path
from evennia import create_object
from evennia.objects.models import ObjectDB
from world import rules
door = Door.objects.get(door_id="hq_admin_door")
Door.objects.filter(pk=door.pk).update(state="OPEN", auto_close_at=777)
door.exit_a.swap_typeclass("evennia.objects.objects.DefaultExit", clean_attributes=False, run_start_hooks=None)
player = create_object("typeclasses.explorers.Explorer", key="재시작탐사자", location=door.exit_a.location)
player.db.profile = {**rules.new_profile(), "credits": 456, "visited": ["dock"]}
expected = {"doors": list(Door.objects.order_by("pk").values()),
            "journals": list(DoorInstallation.objects.order_by("pk").values()),
            "endpoints": list(ObjectDB.objects.filter(pk__in=[door.exit_a_id, door.exit_b_id]).order_by("pk")
                              .values_list("pk", "db_location_id", "db_destination_id", "db_typeclass_path")),
            "objects": ObjectDB.objects.count(), "player": player.pk}
Path(os.environ["PZ_DOOR_RESTART_PROOF"]).write_text(json.dumps(expected), encoding="utf-8")
'''

RESTART_CHECK = r'''
import os
import json
import logging
from pathlib import Path
import django
from django.conf import settings
settings.DATABASES["default"]["NAME"] = os.environ["PZ_DOOR_SCHEMA_DB"]
settings.TEST_ENVIRONMENT = True
django.setup()
import evennia
evennia._init()
from evennia.objects.models import ObjectDB
from world import doors
from world.door_entities.models import Door, DoorInstallation
from server.conf.at_server_startstop import at_server_start
from unittest.mock import Mock, patch
expected = json.loads(Path(os.environ["PZ_DOOR_RESTART_PROOF"]).read_text(encoding="utf-8"))
assert list(Door.objects.order_by("pk").values()) == expected["doors"]
assert list(DoorInstallation.objects.order_by("pk").values()) == expected["journals"]
records = []
class Capture(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())
handler = Capture()
doors.logger.addHandler(handler)
with patch("evennia.create_script"), patch("world.doors.time", return_value=100), patch("world.lifecycle.time", return_value=100):
    at_server_start()
doors.logger.removeHandler(handler)
assert any("hq_admin_door" in record and "국소 격리" in record for record in records)
assert list(Door.objects.order_by("pk").values()) == expected["doors"]
assert list(DoorInstallation.objects.order_by("pk").values()) == expected["journals"]
broken = Door.objects.get(door_id="hq_admin_door")
assert [list(row) for row in ObjectDB.objects.filter(pk__in=[broken.exit_a_id, broken.exit_b_id]).order_by("pk")
        .values_list("pk", "db_location_id", "db_destination_id", "db_typeclass_path")] == expected["endpoints"]
assert ObjectDB.objects.count() == expected["objects"]
player = ObjectDB.objects.get(pk=expected["player"])
player.msg = Mock()
player.push_state = Mock()
assert player.profile_snapshot()["credits"] == 456 and player.profile_snapshot()["visited"] == ["dock"]
for endpoint in (broken.exit_a, broken.exit_b):
    assert doors.state_for_exit(endpoint, 100) == doors.UNAVAILABLE
    player.location = endpoint.location
    before = player.profile_snapshot()
    endpoint.at_traverse(player, endpoint.destination)
    assert player.location == endpoint.location and player.profile_snapshot() == before
recovery = Door.objects.get(door_id="recovery_room_door")
player.location = recovery.exit_a.location
doors.operate(player, "문", "닫아", 100)
doors.operate(player, "문", "열어", 110)
with patch("world.doors.time", return_value=120):
    recovery.exit_a.at_traverse(player, recovery.exit_a.destination)
assert player.location == recovery.exit_a.destination
assert Door.objects.get(pk=recovery.pk).auto_close_at == 180
normal = ObjectDB.objects.get(db_tags__db_key="dock:동", db_tags__db_category="primal_zone_exit")
player.location = normal.location
normal.at_traverse(player, normal.destination)
assert player.location == normal.destination
print("Door restart PASS: persistent damage isolated in a new process")
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

    def test_p1_08_damaged_door_survives_new_process_server_start(self):
        with TemporaryDirectory(prefix="pz-door-restart-") as directory:
            environment = {**os.environ, "DJANGO_SETTINGS_MODULE": "server.conf.settings_test", "PYTHONUTF8": "1",
                           "PZ_DOOR_SCHEMA_DB": str(Path(directory) / "isolated.sqlite3"),
                           "PZ_DOOR_SCHEMA_EXISTING": "0", "PZ_DOOR_RESTART_PROOF": str(Path(directory) / "proof.json")}
            for source, success in ((SCHEMA_CHECK + RESTART_SEED, "Door schema PASS"),
                                    (RESTART_CHECK, "Door restart PASS")):
                result = subprocess.run([sys.executable, "-c", source], cwd=Path(__file__).resolve().parents[1],
                                        env=environment, capture_output=True, text=True, encoding="utf-8", timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(success, result.stdout)
