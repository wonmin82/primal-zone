"""격리 DB의 실제 실물·번호·외부 트랜잭션 최종 상태를 검증한다."""

from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from evennia import create_object
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultRoom
from typeclasses.enemies import Enemy
from typeclasses.exits import Exit
from typeclasses.explorers import Explorer
from typeclasses.interactables import ActionObject
from typeclasses.loot import Corpse, DroppedLoot
from world.actions.schema import ReferenceKind
from world.content import ENEMIES
from world.door_entities.models import Door
from world.item_entities.api import create_item, merge_stack, move_item, move_item_tree, split_stack
from world.loot_entities.models import CurrencyLoot
from world.multiplayer import world_change
from world.selection_numbers.api import (
    backfill,
    descriptor,
    label,
    number_for,
    records_for,
    resolve_reference,
    schedule_object,
    verify,
)
from world.selection_numbers.models import NumberScope, SelectionNumber

from tests.base import GameCommandTest, clear_test_caches


class SelectionNumberTests(GameCommandTest):
    def test_historical_schema_context_is_test_only_and_resets_after_failure(self):
        from django.test import override_settings
        from world.selection_numbers.mode import enabled, historical_schema

        self.assertTrue(enabled())
        with override_settings(TEST_ENVIRONMENT=False):
            with self.assertRaises(RuntimeError):
                with historical_schema():
                    self.fail("운영 환경은 진입할 수 없어야 합니다.")
        with self.assertRaises(ValueError):
            with historical_schema():
                self.assertFalse(enabled())
                raise ValueError("controlled")
        self.assertTrue(enabled())

    def test_door_endpoint_replacement_releases_original_without_reusing_hole(self):
        left = create_object(Exit, key="첫 출구", location=self.room1, destination=self.room2)
        right = create_object(Exit, key="반대 출구", location=self.room2, destination=self.room1)
        door = Door.objects.create(door_id="replace_test", name="시험 문", room_a="a", room_b="b",
                                   exit_a=left, exit_b=right, direction_a="첫 출구", direction_b="반대 출구", state="CLOSED")
        old = descriptor(left).reference
        replacement = create_object(Exit, key="새 출구", location=self.room1, destination=self.room2)
        door.exit_a = replacement
        door.save()
        self.assertIsNone(resolve_reference(old))
        self.assertIsNone(number_for(old))
        self.assertEqual(number_for(descriptor(replacement).reference), 2)
        self.assertEqual(verify(), ())

    def test_seed_final_audit_failure_rolls_back_allocations(self):
        from unittest.mock import patch

        obj = self.facility()
        reference = descriptor(obj).reference
        row = SelectionNumber.objects.get(kind=reference.kind, identity=reference.identity)
        SelectionNumber.objects.create(scope=row.scope, kind="object", identity="999999", number=99, name="없는 실물")
        before = list(SelectionNumber.objects.values())
        with patch("world.selection_numbers.maintenance.backup_database") as backup:
            with self.assertRaises(ValidationError):
                backfill(dry_run=False, backup_path="isolated-unit-boundary")
            backup.assert_called_once()
        self.assertEqual(list(SelectionNumber.objects.values()), before)

    def test_group_metadata_removal_is_rejected_and_cached_name_rollback_restored(self):
        first = self.facility("첫 시설", "fixture.first")
        second = self.facility("다른 시설", "fixture.second")
        reference = descriptor(first).reference
        with self.assertRaises(ValidationError):
            with world_change():
                first.attributes.remove("selection_definition_id")
        self.assertEqual(first.db.selection_definition_id, "fixture.first")
        self.assertEqual(number_for(reference), 1)
        with self.assertRaises(ValidationError):
            first.db.selection_definition_id = "fixture.changed"
        self.assertEqual(first.db.selection_definition_id, "fixture.first")
        with self.assertRaises(ValidationError):
            first.key = second.key
        self.assertEqual(first.key, "첫 시설")
        self.assertEqual(ObjectDB.objects.get(pk=first.pk).key, "첫 시설")
        self.assertEqual(verify(), ())

    def facility(self, name="시험 시설", definition="fixture.facility", group=None, room=None):
        attributes = [("selection_definition_id", definition)]
        if group:
            attributes.append(("selection_group_id", group))
        return create_object(ActionObject, key=name, location=room or self.room1, attributes=attributes)

    def test_holes_not_reused_last_removal_resets_and_two_alone_shows_number(self):
        a, b, c = [self.facility() for _ in range(3)]
        self.assertEqual([number_for(descriptor(obj).reference) for obj in (a, b, c)], [1, 2, 3])
        a.delete()
        d = self.facility()
        self.assertEqual(number_for(descriptor(d).reference), 4)
        c.delete()
        d.delete()
        record = descriptor(b)
        from dataclasses import replace

        self.assertEqual(label(replace(record, number=2), 1), "시험 시설 2")
        b.delete()
        fresh = self.facility()
        self.assertEqual(number_for(descriptor(fresh).reference), 1)

    def test_move_releases_old_scope_and_stale_reference(self):
        a, b = self.facility(), self.facility()
        reference = descriptor(a).reference
        a.move_to(self.room2, quiet=True)
        self.assertIsNone(resolve_reference(reference))
        self.assertEqual(number_for(descriptor(a).reference), 1)
        self.assertEqual(number_for(descriptor(b).reference), 2)
        self.assertEqual(number_for(descriptor(self.facility()).reference), 3)

    def test_enemy_state_and_respawn_preserve_same_number(self):
        enemy = create_object(Enemy, key="시험 적", location=self.room1,
                              attributes=[("enemy_id", next(iter(ENEMIES)))])
        before = descriptor(enemy).reference
        number = number_for(before)
        with world_change():
            enemy.db.state = "respawning"
            enemy.db.hp = 0
            schedule_object(enemy.pk)
        self.assertEqual(number_for(before), number)
        with world_change():
            enemy.db.state = "alive"
            schedule_object(enemy.pk)
        self.assertEqual(number_for(before), number)

    def test_same_name_different_group_rejected_creation_is_rolled_back(self):
        a = self.facility()
        before = ObjectDB.objects.count()
        with self.assertRaises(ValidationError):
            self.facility(definition="fixture.other")
        self.assertEqual(ObjectDB.objects.count(), before)
        self.assertEqual(number_for(descriptor(a).reference), 1)
        self.facility(definition="fixture.other", group=descriptor(a).group_id)

    def test_name_changes_do_not_change_group_or_number(self):
        a = self.facility()
        original = descriptor(a)
        a.key = "새 이름"
        a.save()
        self.assertEqual(descriptor(a).group_id, original.group_id)
        self.assertEqual(number_for(descriptor(a).reference), 1)

    def test_outer_failure_restores_numbers_location_and_evennia_cache(self):
        a = self.facility()
        reference = descriptor(a).reference
        scope = NumberScope.objects.get(scope_id=reference.scope_id, group_id=descriptor(a).group_id)
        with self.assertRaises(RuntimeError):
            with world_change():
                a.move_to(self.room2, quiet=True)
                self.facility()
                raise RuntimeError("controlled")
        self.assertEqual(a.location.pk, self.room1.pk)
        self.assertEqual(number_for(reference), 1)
        scope.refresh_from_db()
        self.assertEqual(scope.next_number, 2)

    def test_nested_rollback_restores_pending_finalizer_collection(self):
        with world_change():
            a = self.facility()
            try:
                with world_change():
                    self.facility()
                    raise RuntimeError("controlled")
            except RuntimeError:
                pass
            b = self.facility()
        self.assertEqual([number_for(descriptor(obj).reference) for obj in (a, b)], [1, 2])
        self.assertEqual(verify(), ())

    def test_final_group_not_temporarily_empty_when_last_deleted_and_recreated(self):
        a = self.facility()
        with world_change():
            a.delete()
            b = self.facility()
        self.assertEqual(number_for(descriptor(b).reference), 2)

    def test_pure_observation_and_hidden_object_do_not_renumber(self):
        a, b = self.facility(), self.facility()
        before = list(SelectionNumber.objects.values_list("pk", "number"))
        a.locks.add("view:false()")
        records_for(self.char1, ReferenceKind.OBJECT)
        records_for(self.char1, ReferenceKind.OBJECT)
        self.assertEqual(list(SelectionNumber.objects.values_list("pk", "number")), before)
        self.assertEqual(number_for(descriptor(b).reference), 2)

    def test_backfill_dry_run_is_read_only_and_write_requires_backup(self):
        self.facility()
        before = list(SelectionNumber.objects.values_list("pk", "number"))
        self.assertFalse(backfill()["written"])
        self.assertEqual(list(SelectionNumber.objects.values_list("pk", "number")), before)
        with self.assertRaises(ValidationError):
            backfill(dry_run=False)

    def test_item_partial_split_immediate_merge_preserves_uuid_and_no_wasted_number(self):
        explorer = create_object(Explorer, key="번호 탐사자", location=self.room1)
        a = create_item("bandage", location_kind="inventory", owner_object=explorer, quantity=5)
        original = descriptor(a).reference
        with world_change():
            part = split_stack(a, 2)
            merge_stack(part, a)
        a.refresh_from_db()
        self.assertEqual(a.quantity, 5)
        self.assertEqual(number_for(original), 1)
        fresh = create_item("bandage", location_kind="inventory", owner_object=explorer)
        self.assertEqual(number_for(descriptor(fresh).reference), 2)

    def test_corpse_and_ground_sources_keep_identity(self):
        corpse = create_object(Corpse, key="시험 시체", location=self.room1)
        self.assertEqual(number_for(descriptor(corpse).reference), 1)
        source = create_object(DroppedLoot, key="시험 물건", location=self.room1)
        explorer = create_object(Explorer, key="번호 탐사자", location=self.room1)
        a = create_item("bandage", location_kind="inventory", owner_object=explorer)
        ref = descriptor(a).reference
        self.assertEqual(ref.kind, ReferenceKind.ITEM)
        self.assertNotEqual(descriptor(source).reference.identity, descriptor(corpse).reference.identity)

    def test_inside_parent_scope_survives_parent_move_and_extraction_gets_new_number(self):
        explorer = create_object(Explorer, key="번호 탐사자", location=self.room1)
        other = create_object(Explorer, key="다른 탐사자", location=self.room1)
        parent = create_item("bandage", location_kind="inventory", owner_object=explorer)
        child = create_item("bandage", location_kind="inside", parent_item=parent,
                            socket="supplies", quantity=3)
        before = descriptor(child).reference
        move_item_tree(parent, location_kind="inventory", owner_object=other)
        child.refresh_from_db()
        self.assertEqual(descriptor(child).reference, before)
        self.assertEqual(number_for(before), 1)
        moved = move_item(child, location_kind="inventory", owner_object=other)
        self.assertEqual(number_for(descriptor(moved).reference), 2)
        self.assertIsNone(resolve_reference(before))

    def test_personal_storage_scope_is_separate_from_carried_and_shared_storage(self):
        explorer = create_object(Explorer, key="번호 탐사자", location=self.room1)
        a = create_item("bandage", location_kind="inventory", owner_object=explorer)
        b = create_item("bandage", location_kind="personal_storage", owner_object=explorer)
        self.assertNotEqual(descriptor(a).scope_id, descriptor(b).scope_id)
        self.assertEqual([number_for(descriptor(item).reference) for item in (a, b)], [1, 1])
        self.assertEqual(descriptor(a).scope_id, f"character:{explorer.pk}")

    def test_ground_items_share_room_numbers_but_keep_individual_sources(self):
        sources = [create_object(DroppedLoot, key=f"낙하 물건 {i}", location=self.room1) for i in range(2)]
        items = [create_item("bandage", location_kind="world_loot", owner_object=source) for source in sources]
        self.assertEqual([number_for(descriptor(item).reference) for item in items], [1, 2])
        self.assertEqual(items[0].owner_object_id, sources[0].pk)
        self.assertEqual(items[1].owner_object_id, sources[1].pk)
        sources[0].move_to(self.room2, quiet=True)
        items[0].refresh_from_db()
        self.assertEqual(number_for(descriptor(items[0]).reference), 1)
        self.assertEqual(number_for(descriptor(items[1]).reference), 2)

    def test_currency_permissions_and_partial_quantity_do_not_change_shared_number(self):
        source = create_object(Corpse, key="시험 시체", location=self.room1)
        a = CurrencyLoot.objects.create(owner_object=source, quantity=5)
        b = CurrencyLoot.objects.create(owner_object=source, quantity=8)
        reference = descriptor(b).reference
        a.delete()
        b.quantity = 3
        # 실제 예약 대상 타입 계약은 Explorer이며 관측 권한과 번호 자체는 독립이다.
        b.reserved_player = create_object(Explorer, key="보호 탐사자", location=self.room1)
        b.save()
        self.assertEqual(number_for(reference), 2)
        self.assertEqual(number_for(descriptor(CurrencyLoot.objects.create(owner_object=source, quantity=2)).reference), 3)

    def test_file_backed_sqlite_snapshot_survives_independent_process_restart(self):
        import json
        import sqlite3
        import subprocess
        import sys
        from contextlib import closing
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from django.db import connection

        a, b = self.facility(), self.facility()
        a.delete()
        reference = descriptor(b).reference
        # 격리 in-memory DB를 SQLite serialize로 복사한다. 실제 플레이 파일은 읽지 않는다.
        with TemporaryDirectory(prefix="pz-b1-restart-") as directory:
            target = Path(directory) / "isolated.sqlite3"
            snapshot = sqlite3.connect(":memory:")
            snapshot.deserialize(connection.connection.serialize())
            with closing(sqlite3.connect(target)) as disk:
                snapshot.backup(disk)
            snapshot.close()
            code = (
                "import sqlite3,json,sys; c=sqlite3.connect(sys.argv[1]); "
                "print(json.dumps(c.execute('SELECT number FROM selection_numbers_selectionnumber "
                "WHERE kind=? AND identity=?',sys.argv[2:]).fetchone()))"
            )
            for _ in range(2):
                result = subprocess.run([sys.executable, "-c", code, str(target), reference.kind,
                                         reference.identity], capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(result.stdout), [2])

    def test_room_reference_is_observed_without_number_allocation(self):
        record, = records_for(self.char1, ReferenceKind.ROOM)
        self.assertEqual(record.reference.identity, str(self.char1.location.pk))
        self.assertIsNone(record.number)
        self.assertEqual(resolve_reference(record.reference), self.char1.location)
        self.assertFalse(SelectionNumber.objects.filter(kind="room").exists())

    def test_door_endpoints_use_exit_identity_and_common_room_group(self):
        references = []
        for index in range(2):
            a = create_object(Exit, key=f"시험 방향 {index}", location=self.room1, destination=self.room2)
            b = create_object(Exit, key=f"반대 방향 {index}", location=self.room2, destination=self.room1)
            door = Door.objects.create(door_id=f"fixture_{index}", name=f"시험 문 {index}",
                                       room_a="test_a", room_b="test_b", exit_a=a, exit_b=b,
                                       direction_a=a.key, direction_b=b.key, state="CLOSED")
            references.append(descriptor(a).reference)
            self.assertEqual(references[-1].identity, str(a.pk))
            door.state = "OPEN"
            door.save()
            self.assertEqual(number_for(references[-1]), index + 1)
        self.assertEqual([number_for(ref) for ref in references], [1, 2])

    def test_definition_conversion_requires_existing_explicit_maintenance_mapping(self):
        from copy import deepcopy
        from unittest.mock import patch

        from world.content import ITEMS
        from world.item_runtime import maintenance

        explorer = create_object(Explorer, key="변환 탐사자", location=self.room1)
        old = deepcopy(ITEMS["explorer_machete"])
        old["name"] = "이전 시험 무기"
        with patch.dict(ITEMS, {"machete": old}):
            previous = create_item("machete", location_kind="inventory", owner_object=explorer)
            current = create_item("explorer_machete", location_kind="inventory", owner_object=explorer)
            identity = previous.pk
            previous.definition_id = "explorer_machete"
            with self.assertRaises(ValidationError):
                previous.save()
            token = maintenance.set(True)
            try:
                previous.save()
            finally:
                maintenance.reset(token)
            previous.refresh_from_db()
            self.assertEqual(previous.pk, identity)
            self.assertEqual(number_for(descriptor(current).reference), 1)
            self.assertEqual(number_for(descriptor(previous).reference), 2)
            self.assertEqual(verify(), ())

    def test_group_metadata_change_is_rejected_even_during_scope_move(self):
        a = self.facility()
        before = descriptor(a)
        with self.assertRaises(ValidationError):
            with world_change():
                a.db.selection_group_id = "fixture.changed"
                a.move_to(self.room2, quiet=True)
        self.assertEqual(descriptor(a), before)

    def test_normalized_formal_name_collision_requires_explicit_shared_group(self):
        a = self.facility(name="시험 시설")
        with self.assertRaises(ValidationError):
            self.facility(name="시험시설", definition="fixture.other")
        self.facility(name="시험시설", definition="fixture.other", group=descriptor(a).group_id)

    def test_verify_reports_unseeded_live_member_without_allocating_it(self):
        obj = self.facility()
        ref = descriptor(obj).reference
        SelectionNumber.objects.filter(kind=ref.kind, identity=ref.identity).delete()
        self.assertIn((ref.kind, ref.identity, "missing"), verify())
        self.assertIsNone(number_for(ref))


class SelectionNumberConcurrencyTests(TransactionTestCase):
    def tearDown(self):
        clear_test_caches()
        super().tearDown()

    def test_last_removal_and_two_creations_are_serialized_without_duplicate_or_reset(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from django.db import connections

        room = create_object(DefaultRoom, key="경합 방")

        def create():
            return create_object(ActionObject, key="경합 시설", location=room,
                                 attributes=[("selection_definition_id", "fixture.concurrent")])

        original = create()
        shared_connection = connections["default"]
        shared_connection.inc_thread_sharing()
        barrier = Barrier(2)

        def change(remove):
            # Evennia test runner는 private :memory: SQLite를 사용한다. 단일 서버의
            # 같은 연결을 RLock으로 직렬화하는 계약을 시험하며 별도 빈 DB를 만들지 않는다.
            connections["default"] = shared_connection
            barrier.wait(timeout=10)
            with world_change():
                if remove:
                    original.delete()
                current = create()
            return descriptor(current).reference

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(change, True)
                second = pool.submit(change, False)
                refs = (first.result(timeout=20), second.result(timeout=20))
        finally:
            shared_connection.dec_thread_sharing()
        self.assertEqual(sorted(number_for(ref) for ref in refs), [2, 3])
        self.assertEqual(verify(), ())
