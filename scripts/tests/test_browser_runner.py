"""실행기 격리/비밀 제거의 중요 실패 경계. 실제 서버/브라우저는 E2E가 검증한다."""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import browser_e2e  # noqa: E402
import browser_probe  # noqa: E402


class BrowserIsolationTests(unittest.TestCase):
    def test_export_keeps_only_masked_viewport_with_playwright_attachment_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root/'results'
            screenshots = results/'screenshots'
            screenshots.mkdir(parents=True)
            image = screenshots/('safe-viewport-390-'+'a'*40+'.png')
            image.write_bytes(b'\x89PNG\r\n\x1a\nfixture-image')
            (results/'results.json').write_text(json.dumps({'status': 'passed', 'tests': [], 'screenshots': [
                {'source': image.name, 'name': 'safe-viewport-390.png'}]}), encoding='utf-8')
            evidence = root/'evidence'
            browser_e2e.publish_evidence(results, evidence, {'success': True}, None)
            self.assertEqual((evidence/'safe-viewport-390.png').read_bytes(), image.read_bytes())

    def test_export_allowlist_excludes_private_messages_tokens_logs_and_unknown_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root/'results'
            results.mkdir()
            secret = 'PRIVATE-PASSWORD-TOKEN-SENTINEL'
            (results/'results.json').write_text(json.dumps({'status': 'failed', 'error': secret, 'tests': [
                {'id': 'TEST-P2-02-D', 'status': 'failed', 'message': secret,
                 'observations': [{'player': 'A', 'lastCommand': secret, 'errors': [secret], 'path': '?token='+secret}]}],
                'screenshots': [{'source': '../private.png', 'name': 'unsafe.png'},
                                {'source': '../server.log', 'name': 'safe-viewport-1366.png'}]}), encoding='utf-8')
            (results/'credentials.json').write_text(secret, encoding='utf-8')
            (root/'server.log').write_text(secret, encoding='utf-8')
            evidence = root/'evidence'
            browser_e2e.publish_evidence(results, evidence, {'success': False}, root)
            self.assertEqual({p.name for p in evidence.iterdir()}, {'run.json', 'results.json', 'report.html', 'browser.log', 'setup.log', 'server.log', 'portal.log'})
            for path in evidence.iterdir():
                self.assertNotIn(secret, path.read_text(encoding='utf-8'))
            self.assertEqual(json.loads((evidence/'results.json').read_text())['tests'][0]['status'], 'failed')

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


class BrowserCredentialTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        parent = ROOT/'work/smoke'
        parent.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.directory.cleanup)
        self.run = Path(self.directory.name)
        (self.run/'.primal-smoke').touch()
        self.harness = SimpleNamespace(ready=AsyncMock(), run_dir=self.run, credentials=[('fixture', 'private-password')],
                                       env={}, ports={'http': 1}, ws_url='ws://127.0.0.1:2')
        self.results = self.run/'results'
        self.results.mkdir()
        self.credentials = self.run/'browser-credentials.json'

    async def test_popen_failures_remove_credentials_and_preserve_start_error(self):
        for error in (FileNotFoundError('missing node'), OSError('popen failure')):
            with self.subTest(error=type(error).__name__), patch.object(browser_e2e.subprocess, 'Popen', side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    await browser_e2e.browser(self.harness, self.results)
                self.assertIs(caught.exception, error)
                self.assertFalse(self.credentials.exists())

    async def test_abnormal_exit_stops_owned_process_and_removes_credentials(self):
        process = Mock(returncode=2)
        context = self.results/'error-context.md'
        context.write_text('private-diagnostic-sentinel', encoding='utf-8')
        with patch.object(browser_e2e.subprocess, 'Popen', return_value=process), patch.object(browser_e2e, 'stop_browser') as stop:
            with self.assertRaisesRegex(RuntimeError, '종료 코드 2'):
                await browser_e2e.browser(self.harness, self.results)
            stop.assert_called_once_with(process)
            self.assertFalse(self.credentials.exists())
            self.assertFalse(context.exists())

    async def test_success_cleans_credentials_after_real_creation(self):
        process = Mock(returncode=0)
        def create(*args, **kwargs):
            self.assertTrue(self.credentials.is_file())
            self.assertEqual(json.loads(self.credentials.read_text(encoding='utf-8'))[0][1], 'private-password')
            self.assertEqual(kwargs['env']['PLAYWRIGHT_NO_COPY_PROMPT'], '1')
            (self.results/'results.json').write_text(json.dumps({'status': 'passed', 'errors': 0}), encoding='utf-8')
            return process
        with patch.object(browser_e2e.subprocess, 'Popen', side_effect=create), patch.object(browser_e2e, 'stop_browser') as stop:
            await browser_e2e.browser(self.harness, self.results)
            stop.assert_called_once_with(process)
            self.assertFalse(self.credentials.exists())

    async def test_reporter_cleanup_failure_is_not_a_successful_browser_run(self):
        process = Mock(returncode=0)
        (self.results/'results.json').write_text(json.dumps({'status': 'failed', 'errors': 1}), encoding='utf-8')
        with patch.object(browser_e2e.subprocess, 'Popen', return_value=process), patch.object(browser_e2e, 'stop_browser'):
            with self.assertRaisesRegex(RuntimeError, '증거 정리 실패'):
                await browser_e2e.browser(self.harness, self.results)
            self.assertFalse(self.credentials.exists())

    async def test_stop_failure_does_not_skip_credential_deletion_or_hide_original(self):
        process = Mock(returncode=2)
        with patch.object(browser_e2e.subprocess, 'Popen', return_value=process), patch.object(browser_e2e, 'stop_browser', side_effect=OSError('stop failed')):
            with self.assertRaises(ExceptionGroup) as caught:
                await browser_e2e.browser(self.harness, self.results)
            self.assertIsInstance(caught.exception.exceptions[0], RuntimeError)
            self.assertIsInstance(caught.exception.exceptions[1], OSError)
            self.assertFalse(self.credentials.exists())

    async def test_unlink_failure_keeps_both_start_and_cleanup_errors(self):
        original_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path == self.credentials:
                raise PermissionError('controlled unlink failure')
            return original_unlink(path, *args, **kwargs)
        with patch.object(browser_e2e.subprocess, 'Popen', side_effect=FileNotFoundError('missing node')), patch.object(Path, 'unlink', unlink):
            with self.assertRaises(ExceptionGroup) as caught:
                await browser_e2e.browser(self.harness, self.results)
            self.assertIsInstance(caught.exception.exceptions[0], FileNotFoundError)
            self.assertIsInstance(caught.exception.exceptions[1], PermissionError)
        self.credentials.unlink()

    async def test_wait_timeout_and_cancellation_clean_owned_resources(self):
        for error in (browser_e2e.subprocess.TimeoutExpired('node', 300), asyncio.CancelledError(), KeyboardInterrupt()):
            process = Mock(returncode=None)
            # 취소/인터럽트는 worker thread에서 발생시키지 않고 await 경계에 주입한다.
            with self.subTest(error=type(error).__name__), patch.object(browser_e2e.subprocess, 'Popen', return_value=process), patch.object(browser_e2e.asyncio, 'to_thread', new=AsyncMock(side_effect=error)), patch.object(browser_e2e, 'stop_browser') as stop:
                with self.assertRaises(type(error)):
                    await browser_e2e.browser(self.harness, self.results)
                stop.assert_called_once_with(process)
                self.assertFalse(self.credentials.exists())


if __name__ == '__main__':
    unittest.main()
