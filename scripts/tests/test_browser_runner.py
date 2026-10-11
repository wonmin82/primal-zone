"""실행기 격리/비밀 제거의 중요 실패 경계. 실제 서버/브라우저는 E2E가 검증한다."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import browser_e2e  # noqa: E402
import browser_probe  # noqa: E402


class BrowserIsolationTests(unittest.TestCase):
    def test_report_sanitization_removes_actual_password_without_losing_public_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'results.json'
            path.write_text(json.dumps({'error': 'fill private-token', 'public': '검증가: 안녕'}), encoding='utf-8')
            browser_e2e.sanitize_artifacts(Path(directory), ['private-token'])
            result = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(result['error'], 'fill [REDACTED]')
            self.assertEqual(result['public'], '검증가: 안녕')

    def test_read_only_probe_rejects_database_outside_owned_directory(self):
        parent = ROOT/'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            run = Path(directory)
            (run/'.primal-smoke').touch()
            with patch.dict(os.environ, PRIMAL_SMOKE_RUN_DIR=str(run), PRIMAL_BROWSER_DB=str(ROOT/'game/server/evennia.db3')):
                with self.assertRaisesRegex(RuntimeError, '불일치'):
                    browser_probe.sessions()

    def test_probe_reads_actual_puppet_ids_and_preserves_database(self):
        parent = ROOT/'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            run = Path(directory)
            (run/'.primal-smoke').touch()
            database = run/'evennia-smoke.sqlite3'
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute('CREATE TABLE objects_objectdb (db_key TEXT, db_sessid TEXT, db_typeclass_path TEXT)')
                connection.executemany('INSERT INTO objects_objectdb VALUES (?, ?, ?)', [
                    ('검증가', '1,2', 'typeclasses.explorers.Explorer'),
                    ('검증나', None, 'typeclasses.explorers.Explorer')])
            before = browser_e2e.fingerprint(database)
            with patch.dict(os.environ, PRIMAL_SMOKE_RUN_DIR=str(run), PRIMAL_BROWSER_DB=str(database)):
                self.assertEqual(browser_probe.sessions(), {'검증가': ['1', '2'], '검증나': []})
            self.assertEqual(browser_e2e.fingerprint(database), before)


if __name__ == '__main__':
    unittest.main()
