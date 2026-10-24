"""게임 상태 쓰기 없이 격리 제어의 소유권·정리·매트릭스 경계를 검사한다."""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from integration_e2e import SCENARIOS, restore_restart, wait_browser  # noqa: E402
from integration_probe import snapshot  # noqa: E402
from issue50_contracts import records  # noqa: E402
from release_guard import validate  # noqa: E402


class IntegrationContractManifestTests(unittest.TestCase):
    def test_timing_projection_reads_real_sqlite_without_mutation_or_django(self):
        import base64
        import hashlib
        import pickle
        import sqlite3
        from contextlib import closing
        from uuid import UUID
        parent = ROOT / 'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            run = Path(directory)
            (run / '.primal-smoke').touch()
            db = run / 'evennia-smoke.sqlite3'
            with closing(sqlite3.connect(db)) as connection, connection:
                connection.executescript('''
                    CREATE TABLE objects_objectdb(id, db_key, db_typeclass_path, db_location_id, db_sessid);
                    CREATE TABLE typeclasses_attribute(id, db_key, db_category, db_value);
                    CREATE TABLE objects_objectdb_db_attributes(objectdb_id, attribute_id);
                    CREATE TABLE door_entities_door(door_id, aliases, lockable, state, auto_close_at);
                    CREATE TABLE item_entities_itementity(id, parent_item_id, state, sequence);
                    CREATE TABLE loot_entities_lootclaim(id, item_entity_id);
                    INSERT INTO objects_objectdb VALUES (1,'fixture','typeclasses.explorers.Explorer',10,'7,8');
                    INSERT INTO objects_objectdb VALUES (2,'party','typeclasses.parties.Party',NULL,NULL);
                    INSERT INTO door_entities_door VALUES ('door','["alias"]',0,'OPEN',60);
                ''')
                party = {'leader': 1, 'leader_offline_since': None, 'members': [1], 'tactics': {'defender_id': 1}}
                for number, owner, key, value in ((1, 10, 'zone_id', 'outside'), (2, 2, 'state', party)):
                    encoded = base64.b64encode(pickle.dumps(value)).decode()
                    connection.execute('INSERT INTO typeclasses_attribute VALUES (?,?,NULL,?)', (number, key, encoded))
                    connection.execute('INSERT INTO objects_objectdb_db_attributes VALUES (?,?)', (owner, number))
                identity = UUID('12345678-1234-5678-1234-567812345678')
                connection.execute('INSERT INTO item_entities_itementity VALUES (?,NULL,?,1)', (identity.hex, '{"charge":2}'))
                connection.execute('INSERT INTO loot_entities_lootclaim VALUES (1,?)', (identity.hex,))
            before = (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
            with patch.dict(os.environ, PRIMAL_SMOKE_RUN_DIR=str(run), PRIMAL_BROWSER_DB=str(db)):
                observed = snapshot(timing=True)
            self.assertEqual(observed['players'], {'fixture': {'zone': 'outside'}})
            self.assertEqual(observed['sessions'], {'fixture': ['7', '8']})
            self.assertEqual(observed['parties'], {'2': party})
            self.assertEqual(observed['doors'], [{'door_id': 'door', 'aliases': ['alias'], 'lockable': False, 'state': 'OPEN', 'auto_close_at': 60}])
            self.assertEqual(observed['items'][0]['id'], str(identity))
            self.assertEqual(observed['items'][0]['state'], {'charge': 2})
            self.assertEqual(observed['claims'][0]['item_entity_id'], str(identity))
            self.assertEqual(before, (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns))
            # 압축되지 않은 내장 Attribute만 읽는다. 객체/global 복원 및 중복은 실패한다.
            with closing(sqlite3.connect(db)) as connection, connection:
                encoded = base64.b64encode(pickle.dumps(complex(1, 2))).decode()
                connection.execute('UPDATE typeclasses_attribute SET db_value=? WHERE id=2', (encoded,))
            with patch.dict(os.environ, PRIMAL_SMOKE_RUN_DIR=str(run), PRIMAL_BROWSER_DB=str(db)):
                with self.assertRaisesRegex(ValueError, '내장 데이터'):
                    snapshot(timing=True)
            with closing(sqlite3.connect(db)) as connection, connection:
                connection.execute('INSERT INTO objects_objectdb_db_attributes VALUES (10,1)')
            with patch.dict(os.environ, PRIMAL_SMOKE_RUN_DIR=str(run), PRIMAL_BROWSER_DB=str(db)):
                with self.assertRaisesRegex(ValueError, '소실 또는 중복'):
                    snapshot(timing=True)

    def test_release_profile_connects_two_wall_clock_observers_not_normal_pr(self):
        package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
        self.assertEqual(package['scripts']['test:browser:timing'], 'uv run python scripts/integration_e2e.py --profile timing')
        self.assertEqual(SCENARIOS[-2:], ('TIMING-DOOR', 'TIMING-PARTY'))
        workflow = (ROOT / '.github/workflows/release-validation.yml').read_text(encoding='utf-8')
        self.assertIn('run: npm run test:browser:timing', workflow)
        pr = (ROOT / '.github/workflows/tests.yml').read_text(encoding='utf-8')
        self.assertNotIn('test:browser:timing', pr)
        spec = (ROOT / 'scripts/browser/integration.spec.cjs').read_text(encoding='utf-8')
        for scenario in ('DOOR', 'PARTY'):
            section = spec.split("test('TEST-TIMING-" + scenario, 1)[1].split("test('")[0]
            self.assertIn('monitorBeforeDeadline', section)
            self.assertIn('timingSnapshot()', section)
            self.assertIn('finalSeen: true', section)
        self.assertIn("control('party-before')", spec)
        self.assertIn("control('party-at')", spec)

    def test_restart_checkpoint_utf8_child_output_is_not_windows_locale(self):
        from smoke_harness import Harness
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'game').mkdir()
            (root / 'scripts/smoke_snapshot.py').write_text(
                "import json; print(json.dumps({'unicode': '\\u2500'}, ensure_ascii=False))", encoding='utf-8')
            harness = Harness('full')
            harness.run_dir = root
            harness.env = {**os.environ, 'PYTHONUTF8': '1'}
            with patch('smoke_harness.ROOT', root):
                self.assertEqual(harness.checkpoint(), {'unicode': '\u2500'})

    def test_integrated_snapshot_rejects_foreign_database_before_django_load(self):
        parent = ROOT/'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            run = Path(directory)
            (run/'.primal-smoke').touch()
            with patch.dict(os.environ, PRIMAL_SMOKE_RUN_DIR=str(run),
                            PRIMAL_BROWSER_DB=str(ROOT/'game/server/evennia.db3')):
                for timing in (False, True):
                    with self.subTest(timing=timing), self.assertRaisesRegex(RuntimeError, '불일치'):
                        snapshot(timing=timing)

    def test_release_rejects_pr_unmatched_sha_or_implicit_branch(self):
        head = 'a'*40
        environment = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/main',
                       'GITHUB_SHA': head, 'PRIMAL_RELEASE_SHA': head}
        self.assertEqual(validate(environment, head), head)
        for key, value in [('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_REF', 'refs/heads/codex/test'),
                           ('GITHUB_SHA', 'b'*40), ('PRIMAL_RELEASE_SHA', 'main')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                validate({**environment, key: value}, head)

    def test_every_frozen_function_id_has_a_real_assertion_path(self):
        rows = records()
        self.assertEqual(len(rows), 74)
        expected = {f'T50-{group}-{number:02}' for group, count in
                    {'CMD': 6, 'ALIAS': 7, 'GAME': 9, 'NPC': 8, 'MSG': 6, 'PARTY': 12,
                     'DOOR': 10, 'HELP': 7, 'DATA': 9}.items() for number in range(1, count+1)}
        self.assertEqual({r['id'] for r in rows}, expected)
        self.assertTrue(all(r['execution'] == 'NOT RUN' for r in rows))
        self.assertEqual(SCENARIOS[:14], tuple(f'E2E-{n:02}' for n in range(1, 15)))


class IntegrationControlTests(unittest.IsolatedAsyncioTestCase):
    def owned_restore_fixture(self, run):
        import sqlite3
        from contextlib import closing

        (run/'.primal-smoke').touch()
        database = run/'evennia-smoke.sqlite3'
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute('CREATE TABLE retained (identity TEXT, number INTEGER, quantity INTEGER)')
            connection.execute("INSERT INTO retained VALUES ('same-uuid',3,7)")
        return SimpleNamespace(run_dir=run, env={'PRIMAL_SMOKE_RUN_DIR': str(run),
                               'DJANGO_SETTINGS_MODULE': 'server.conf.settings_smoke'},
                               processes=[], handles=[], graceful_stop=Mock(), start=Mock(), ready=AsyncMock())

    async def test_backup_restores_owned_sqlite_and_retains_stopped_original(self):
        import sqlite3
        from contextlib import closing

        parent = ROOT/'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            run = Path(directory).resolve()
            harness = self.owned_restore_fixture(run)
            result = await restore_restart(harness)
            harness.graceful_stop.assert_called_once()
            harness.start.assert_called_once()
            harness.ready.assert_awaited_once()
            self.assertEqual(result['restore_integrity'], 'ok')
            self.assertTrue((run/'persistence-stopped.sqlite3').is_file())
            self.assertTrue((run/'persistence-backup.sqlite3').is_file())
            with closing(sqlite3.connect(run/'evennia-smoke.sqlite3')) as connection:
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone(), ('ok',))
                self.assertEqual(connection.execute('SELECT * FROM retained').fetchall(), [('same-uuid', 3, 7)])
            self.assertFalse(harness.restarting)

    async def test_restore_rejects_foreign_run_missing_marker_and_symlink_before_read(self):
        parent = ROOT/'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            run = Path(directory).resolve()
            harness = self.owned_restore_fixture(run)
            for condition in ('marker', 'symlink', 'foreign', 'environment'):
                with self.subTest(condition=condition):
                    marker = run/'.primal-smoke'
                    if condition == 'marker':
                        marker.unlink()
                    harness.env['PRIMAL_SMOKE_RUN_DIR'] = 'foreign' if condition == 'environment' else str(run)
                    harness.run_dir = run.parent if condition == 'foreign' else run
                    with patch('integration_e2e.sqlite3.connect') as connect, patch.object(Path, 'is_symlink', return_value=condition == 'symlink'):
                        with self.assertRaisesRegex(RuntimeError, '불일치'):
                            await restore_restart(harness)
                        connect.assert_not_called()
                    if condition == 'marker':
                        marker.touch()
                    harness.graceful_stop.assert_not_called()

    async def test_live_process_after_stop_blocks_restore_and_start(self):
        parent = ROOT/'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            run = Path(directory).resolve()
            harness = self.owned_restore_fixture(run)
            harness.processes = [('server', SimpleNamespace(poll=lambda: None))]
            with self.assertRaisesRegex(RuntimeError, '정상 종료'):
                await restore_restart(harness)
            harness.start.assert_not_called()
            self.assertFalse((run/'persistence-restored.sqlite3').exists())
            self.assertFalse((run/'persistence-stopped.sqlite3').exists())
            self.assertFalse(harness.restarting)

    async def test_dangling_artifact_symlinks_are_rejected_before_database_read(self):
        parent = ROOT/'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            run = Path(directory).resolve()
            harness = self.owned_restore_fixture(run)
            for name in ('persistence-backup.sqlite3', 'persistence-restored.sqlite3', 'persistence-stopped.sqlite3'):
                with self.subTest(name=name):
                    with patch.object(Path, 'is_symlink', autospec=True, side_effect=lambda path: path.name == name), patch('integration_e2e.sqlite3.connect') as connect:
                        with self.assertRaisesRegex(RuntimeError, '덮어쓸'):
                            await restore_restart(harness)
                        connect.assert_not_called()
                        harness.graceful_stop.assert_not_called()

    async def test_unknown_control_cannot_mutate_or_skip_owned_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = SimpleNamespace(wait=lambda _: __import__('time').sleep(0.1), stop=lambda: stopped.append(True))
            stopped = []
            harness = SimpleNamespace(run_dir=root, env={'PRIMAL_INTEGRATION_SCENARIO': 'E2E-12'}, restart=AsyncMock())
            async def submit():
                while not (root/'integration-control').exists():
                    await asyncio.sleep(0)
                (root/'integration-control/request.json').write_text('{"operation":"set-profile"}')
            task = asyncio.create_task(submit())
            with self.assertRaisesRegex(RuntimeError, '허용되지'):
                await wait_browser(process, harness)
            await task
            harness.restart.assert_not_awaited()
            self.assertEqual(stopped, [True])

    async def test_restart_only_owned_harness_and_response_after_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = SimpleNamespace(wait=lambda _: __import__('time').sleep(0.15), stop=lambda: None)
            harness = SimpleNamespace(run_dir=root, env={'PRIMAL_INTEGRATION_SCENARIO': 'E2E-12'}, restart=AsyncMock())
            async def submit():
                while not (root/'integration-control').exists():
                    await asyncio.sleep(0)
                request = root/'integration-control/request.json'
                request.write_text('{"operation":"restart"}')
            task = asyncio.create_task(submit())
            await wait_browser(process, harness)
            await task
            harness.restart.assert_awaited_once()
            self.assertEqual(json.loads((root/'integration-control/response.json').read_text()), {'ready': True})

    async def test_restart_error_still_stops_browser_and_retains_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stopped = []
            process = SimpleNamespace(wait=lambda _: __import__('time').sleep(0.1), stop=lambda: stopped.append(True))
            harness = SimpleNamespace(run_dir=root, env={'PRIMAL_INTEGRATION_SCENARIO': 'E2E-12'},
                                      restart=AsyncMock(side_effect=RuntimeError('owned restart failure')))
            async def submit():
                while not (root/'integration-control').exists():
                    await asyncio.sleep(0)
                (root/'integration-control/request.json').write_text('{"operation":"restart"}')
            task = asyncio.create_task(submit())
            with self.assertRaisesRegex(RuntimeError, 'owned restart failure'):
                await wait_browser(process, harness)
            await task
            self.assertEqual(stopped, [True])
            self.assertFalse((root/'integration-control/response.json').exists())
