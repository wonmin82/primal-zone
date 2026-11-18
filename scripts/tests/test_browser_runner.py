"""실행기 격리/비밀 제거의 중요 실패 경계. 실제 서버/브라우저는 E2E가 검증한다."""

import asyncio
import ctypes
import errno
import json
import os
import signal
import sqlite3
import subprocess
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
import browser_macos  # noqa: E402
import browser_probe  # noqa: E402
import browser_processes  # noqa: E402


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

    async def test_owner_start_failures_remove_credentials_and_preserve_start_error(self):
        for error in (FileNotFoundError('missing node'), OSError('popen failure')):
            with self.subTest(error=type(error).__name__), patch.object(browser_e2e, 'OwnedBrowser', side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    await browser_e2e.browser(self.harness, self.results)
                self.assertIs(caught.exception, error)
                self.assertFalse(self.credentials.exists())

    async def test_abnormal_exit_stops_owned_process_and_removes_credentials(self):
        process = Mock(returncode=2)
        context = self.results/'error-context.md'
        context.write_text('private-diagnostic-sentinel', encoding='utf-8')
        with patch.object(browser_e2e, 'OwnedBrowser', return_value=process), patch.object(browser_e2e, 'stop_browser') as stop:
            with self.assertRaisesRegex(RuntimeError, '종료 코드 2'):
                await browser_e2e.browser(self.harness, self.results)
            stop.assert_called_once_with(process)
            self.assertFalse(self.credentials.exists())
            self.assertFalse(context.exists())

    async def test_success_cleans_credentials_after_real_creation(self):
        process = Mock(returncode=0, stopped=True)
        def create(*args, **kwargs):
            self.assertTrue(self.credentials.is_file())
            self.assertEqual(json.loads(self.credentials.read_text(encoding='utf-8'))[0][1], 'private-password')
            self.assertEqual(kwargs['env']['PLAYWRIGHT_NO_COPY_PROMPT'], '1')
            (self.results/'results.json').write_text(json.dumps({'status': 'passed', 'errors': 0}), encoding='utf-8')
            return process
        with patch.object(browser_e2e, 'OwnedBrowser', side_effect=create), patch.object(browser_e2e, 'stop_browser') as stop:
            await browser_e2e.browser(self.harness, self.results)
            stop.assert_called_once_with(process)
            self.assertTrue(self.harness.browser_processes_stopped)
            self.assertFalse(self.credentials.exists())

    async def test_reporter_cleanup_failure_is_not_a_successful_browser_run(self):
        process = Mock(returncode=0, stopped=True)
        (self.results/'results.json').write_text(json.dumps({'status': 'failed', 'errors': 1}), encoding='utf-8')
        with patch.object(browser_e2e, 'OwnedBrowser', return_value=process), patch.object(browser_e2e, 'stop_browser'):
            with self.assertRaisesRegex(RuntimeError, '증거 정리 실패'):
                await browser_e2e.browser(self.harness, self.results)
            self.assertFalse(self.credentials.exists())

    async def test_stop_failure_does_not_skip_credential_deletion_or_hide_original(self):
        process = Mock(returncode=2)
        with patch.object(browser_e2e, 'OwnedBrowser', return_value=process), patch.object(browser_e2e, 'stop_browser', side_effect=OSError('stop failed')):
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
        with patch.object(browser_e2e, 'OwnedBrowser', side_effect=FileNotFoundError('missing node')), patch.object(Path, 'unlink', unlink):
            with self.assertRaises(ExceptionGroup) as caught:
                await browser_e2e.browser(self.harness, self.results)
            self.assertIsInstance(caught.exception.exceptions[0], FileNotFoundError)
            self.assertIsInstance(caught.exception.exceptions[1], PermissionError)
        self.credentials.unlink()

    async def test_wait_timeout_and_cancellation_clean_owned_resources(self):
        for error in (browser_e2e.subprocess.TimeoutExpired('node', 300), asyncio.CancelledError(), KeyboardInterrupt()):
            process = Mock(returncode=None)
            # 취소/인터럽트는 worker thread에서 발생시키지 않고 await 경계에 주입한다.
            with self.subTest(error=type(error).__name__), patch.object(browser_e2e, 'OwnedBrowser', return_value=process), patch.object(browser_e2e.asyncio, 'to_thread', new=AsyncMock(side_effect=error)), patch.object(browser_e2e, 'stop_browser') as stop:
                with self.assertRaises(type(error)):
                    await browser_e2e.browser(self.harness, self.results)
                stop.assert_called_once_with(process)
                self.assertFalse(self.credentials.exists())


class DarwinAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.coalition = browser_macos.Coalition.__new__(browser_macos.Coalition)
        self.coalition.api = Mock()

    def test_signal_uses_return_value_even_if_errno_disagrees(self):
        for result, stale_errno, outcome in (
            (0, errno.EPERM, True), (errno.ESRCH, errno.EACCES, False),
            (errno.EPERM, errno.ESRCH, PermissionError), (errno.EINVAL, errno.ESRCH, OSError),
            (-1, errno.ESRCH, RuntimeError),
        ):
            def signal_call(_token, _signum):
                ctypes.set_errno(stale_errno)
                return result

            with self.subTest(result=result):
                self.coalition.api.proc_signal_with_audittoken.side_effect = signal_call
                if isinstance(outcome, bool):
                    self.assertIs(self.coalition.send((12, 34), signal.SIGTERM), outcome)
                else:
                    with self.assertRaises(outcome) as caught:
                        self.coalition.send((12, 34), signal.SIGTERM)
                    if isinstance(caught.exception, OSError):
                        self.assertEqual(caught.exception.errno, result)

    def test_pidinfo_distinguishes_denied_and_gone(self):
        for code in (errno.ESRCH, errno.EPERM, errno.EACCES):
            def pidinfo_call(*_):
                ctypes.set_errno(code)
                return 0

            with self.subTest(code=code):
                self.coalition.api.proc_pidinfo.side_effect = pidinfo_call
                if code == errno.ESRCH:
                    self.assertIsNone(self.coalition.identity(123))
                else:
                    with self.assertRaises(PermissionError) as caught:
                        self.coalition.identity(123)
                    self.assertEqual(caught.exception.errno, code)

    def test_denied_unproven_pids_do_not_block_other_members_or_receive_signals(self):
        owner = self.coalition
        with (patch.object(owner, 'count', side_effect=[1, 0]),
              patch.object(owner, 'pids', return_value=[10, 11, 12, 13]),
              patch.object(owner, 'member', side_effect=[
                  PermissionError(errno.EPERM, ''), PermissionError(errno.EACCES, ''), None, (13, 2)]),
              patch.object(owner, 'send', return_value=True) as send):
            self.assertEqual(owner.drain(55, 5), 0)
        send.assert_called_once_with((13, 2), signal.SIGTERM)

    def test_denied_previously_owned_pid_with_residue_is_not_success(self):
        owner = self.coalition
        with (patch.object(owner, 'count', return_value=1),
              patch.object(owner, 'pids', return_value=[13]),
              patch.object(owner, 'member', side_effect=[(13, 2), PermissionError(errno.EPERM, '')]),
              patch.object(owner, 'send', return_value=True) as send,
              patch.object(browser_macos, 'monotonic', side_effect=[0, 0, 0, 1, 1, 3])):
            with self.assertRaisesRegex(TimeoutError, '활성 1.*이전 소유 PID 1'):
                owner.drain(55, 0.5)
        send.assert_called_once_with((13, 2), signal.SIGTERM)

    def test_pid_reuse_between_reads_does_not_prove_membership(self):
        with (patch.object(self.coalition, 'identity', side_effect=[(13, 1), (13, 2)]),
              patch.object(self.coalition, 'group', return_value=55)):
            self.assertIsNone(self.coalition.member(13, 55))


class BrowserProcessTreeTests(unittest.TestCase):
    """TEST-P2-04-A~F: Windows Job, Linux 입양, macOS coalition의 실제 OS 프로세스."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.owners = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for owner in self.owners:
            owner.stop(timeout=2)

    def start(self, *, child=False, early=True, stubborn=False, grandchild=False):
        index = len(self.owners)
        record = self.root/f'ids-{index}.json'
        script = self.root/f'parent-{index}.py'
        handler = 'signal.signal(signal.SIGBREAK if os.name == "nt" else signal.SIGTERM, signal.SIG_IGN);' if stubborn else ''
        ready = self.root/f'ready-{index}'
        child_code = ('import time,signal,os;' + handler
                      + f'open({str(ready)!r},"w").write(str(os.getpid()));time.sleep(120)')
        if grandchild:
            child_code = ('import subprocess,sys;'
                          + f'subprocess.Popen([sys._base_executable,"-c",{child_code!r}],start_new_session=True)')
        script.write_text('import subprocess,sys,time,json,os,signal\n' + handler + '\n'
                          + (f'child=subprocess.Popen([sys._base_executable,"-c",{child_code!r}],start_new_session=os.name!="nt")\n' if child else '')
                          + f'open({str(record)+".tmp"!r},"w").write(json.dumps({{"parent":os.getpid(),"child":child.pid if {child!r} else None}}))\n'
                          + f'os.replace({str(record)+".tmp"!r},{str(record)!r})\n'
                          + (f'while not os.path.exists({str(ready)!r}): time.sleep(0.01)\n' if child else '')
                          + ('sys.exit(2 if '+str(child)+' else 0)\n' if early else 'time.sleep(120)\n'), encoding='utf-8')
        log = (self.root/f'log-{index}').open('w')
        self.addCleanup(log.close)
        owner = browser_processes.OwnedBrowser([sys._base_executable, str(script)], cwd=ROOT,
                                              env=os.environ.copy(), stdout=log,
                                              control=self.root/f'exit-{index}.json')
        self.owners.append(owner)
        browser_processes.until(record.exists, 10)
        ids = json.loads(record.read_text())
        if grandchild:
            browser_processes.until(lambda: ready.exists() and ready.stat().st_size > 0, 10)
            ids['child'] = int(ready.read_text())
        # 정체성을 보유한 Windows process HANDLE. 종료 확인에 PID 재사용을 의존하지 않는다.
        if os.name == 'nt':
            import ctypes
            api = ctypes.WinDLL('kernel32', use_last_error=True)
            api.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
            api.OpenProcess.restype = ctypes.c_void_p
            api.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            api.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = api.OpenProcess(0x1000, False, ids['child']) if child else None
            if handle:
                self.addCleanup(lambda: api.CloseHandle(handle))
            def alive():
                if not handle:
                    return False
                code = ctypes.c_ulong()
                self.assertTrue(api.GetExitCodeProcess(handle, ctypes.byref(code)))
                return code.value == 259
        elif sys.platform == 'darwin':
            api = owner.mac.api
            identity = api.member(ids['child'], owner.mac.coalition) if child else None
            if child:
                self.assertIsNotNone(identity)

            def alive():
                return identity is not None and api.member(ids['child'], owner.mac.coalition) == identity
        else:
            import select
            fd = os.pidfd_open(ids['child']) if child else None
            if fd is not None:
                self.addCleanup(lambda: os.close(fd))
            def alive():
                return fd is not None and not select.select([fd], [], [], 0)[0]
        return owner, alive

    def test_p204_a_normal_parent_no_child_needs_no_forced_termination(self):
        owner, _ = self.start()
        self.assertEqual(owner.wait(10), 0)
        target = owner.job if os.name == 'nt' else browser_processes.os
        method = 'terminate' if os.name == 'nt' else 'killpg'
        with patch.object(target, method, wraps=getattr(target, method)) as terminate:
            if os.name == 'nt':
                owner.process.wait(10)
            owner.stop()
            terminate.assert_not_called()
        self.assertTrue(owner.stopped)
        if os.name != 'nt':
            self.assertEqual(owner.forced_count, 0)

    def test_p204_b_abnormal_parent_leaves_real_child_then_cleanup_removes_it(self):
        owner, alive = self.start(child=True)
        self.assertEqual(owner.wait(10), 2)
        if os.name == 'nt':
            owner.process.wait(10)
        self.assertTrue(alive(), '부모 종료 후 실제 자식 잔류 재현')
        owner.stop(timeout=1)
        self.assertFalse(alive())
        self.assertTrue(owner.stopped)

    def test_p204_c_live_parent_and_child_timeout_cleanup(self):
        owner, alive = self.start(child=True, early=False)
        with self.assertRaises(subprocess.TimeoutExpired):
            owner.wait(0)
        self.assertTrue(alive())
        owner.stop(timeout=1)
        self.assertFalse(alive())
        if sys.platform != 'darwin':
            self.assertIsNotNone(owner.process.poll())

    def test_p204_c_stubborn_child_requires_owned_forced_termination(self):
        owner, alive = self.start(child=True, stubborn=True)
        self.assertEqual(owner.wait(10), 2)
        # 부모의 종료 기록은 자식의 handler 설치/ready 이후에 작성된다.
        browser_processes.until(lambda: alive(), 10)
        if os.name == 'nt':
            with patch.object(owner.job, 'terminate', wraps=owner.job.terminate) as terminate:
                owner.stop(timeout=0.3)
                terminate.assert_called_once()
        else:
            owner.stop(timeout=0.3)
            self.assertGreater(owner.forced_count, 0)
        self.assertFalse(alive())
        self.assertTrue(owner.stopped)

    def test_p204_d_repeated_cleanup_is_safe(self):
        owner, alive = self.start(child=True)
        owner.wait(10)
        owner.stop(timeout=1)
        owner.stop(timeout=0)
        self.assertFalse(alive())

    def test_p204_e_termination_error_is_reported_and_not_marked_stopped(self):
        owner, _ = self.start(child=True, early=False)
        if os.name == 'nt':
            with patch.object(owner.job, 'active', return_value=2), patch.object(owner.job, 'terminate', side_effect=OSError('controlled termination failure')):
                with self.assertRaises(OSError):
                    owner.stop(timeout=0)
        elif sys.platform == 'darwin':
            with patch.object(owner.mac.api, 'count', side_effect=OSError('controlled cleanup proof failure')):
                with self.assertRaises(OSError):
                    owner.stop(timeout=0)
        else:
            with patch.object(owner.process, 'wait', side_effect=OSError('controlled cleanup wait failure')):
                with self.assertRaises(OSError):
                    owner.stop(timeout=0)
        self.assertFalse(owner.stopped)
        owner.stop(timeout=1)

    def test_p204_f_non_owned_process_remains_alive(self):
        outsider = subprocess.Popen([sys._base_executable, '-c', 'import time;time.sleep(120)'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            owner, alive = self.start(child=True)
            owner.wait(10)
            owner.stop(timeout=1)
            self.assertFalse(alive())
            self.assertIsNone(outsider.poll())
        finally:
            outsider.terminate()
            outsider.wait(10)

    def test_p204_launch_failure_still_cleans_ownership_container(self):
        log = (self.root/'failed.log').open('w')
        self.addCleanup(log.close)
        owner = browser_processes.OwnedBrowser(['missing-primal-browser-executable'], cwd=ROOT,
                                              env=os.environ.copy(), stdout=log, control=self.root/'failed.json')
        self.owners.append(owner)
        with self.assertRaisesRegex(RuntimeError, '시작/소유권'):
            owner.wait(10)
        owner.stop(timeout=1)
        self.assertTrue(owner.stopped)

    def test_p204_job_assignment_failure_never_creates_child(self):
        control = self.root/'registration.json'
        job = Mock()
        job.assign_current.side_effect = OSError('controlled Job assignment failure')
        with patch.object(browser_processes.os, 'name', 'nt'), patch.object(browser_processes, 'WindowsJob', return_value=job), patch.object(browser_processes.subprocess, 'Popen') as child:
            browser_processes.guardian(control, 'owned-fixture', ['unused'])
        child.assert_not_called()
        job.close.assert_called_once()
        self.assertEqual(json.loads(control.read_text()), {'error': 'launch-failed'})

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS launchd coalition')
    def test_macos_reaps_detached_grandchild_after_both_parents_exit(self):
        owner, alive = self.start(child=True, grandchild=True)
        self.assertEqual(owner.wait(10), 2)
        self.assertTrue(alive())
        owner.stop(1)
        self.assertFalse(alive())
        self.assertEqual(owner.forced_count, 0)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS launchd coalition')
    def test_macos_lost_guardian_recovers_residue_but_does_not_certify_run(self):
        owner, alive = self.start(child=True, early=False)
        self.owners.remove(owner)  # 이 실행은 stop에서 실패가 유지되어야 한다.
        try:
            self.assertTrue(owner.mac.api.send(owner.mac.guardian, browser_processes.signal.SIGKILL))
            with self.assertRaisesRegex(RuntimeError, '조기 종료'):
                owner.wait(5)
            self.assertTrue(alive())
        finally:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, '정리 증거 없음'):
                    owner.stop(1)
        self.assertFalse(owner.stopped)
        self.assertFalse(alive())
        self.assert_macos_recovery(owner, guardian_forced=False)

    def assert_macos_recovery(self, owner, *, guardian_forced):
        recovery = json.loads(owner.control.with_suffix('.recovery.json').read_text())
        self.assertFalse(recovery['stopped'])
        self.assertEqual(recovery['active'], 0)
        if guardian_forced is not None:
            self.assertIs(recovery['guardian_forced'], guardian_forced)
        self.assertTrue(recovery['job_removed'])
        self.assertEqual(browser_macos.launchctl('print', owner.mac.target), browser_macos.BOOTSTRAP_UNKNOWN_SERVICE)
        self.assertFalse(owner.stopped)
        return recovery

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS Guardian 실제 정지 경계')
    def test_macos_stopped_guardian_times_out_then_removes_detached_residue_and_job(self):
        owner, alive = self.start(child=True, early=False, stubborn=True)
        browser_processes.until((self.root/'ready-0').exists, 10)
        self.owners.remove(owner)
        try:
            self.assertTrue(owner.mac.api.send(owner.mac.guardian, signal.SIGSTOP))
            self.assertGreaterEqual(owner.mac.api.count(owner.mac.coalition), 3)
            self.assertTrue(alive())
        finally:
            with self.assertRaisesRegex(TimeoutError, '정리 제어 Timeout'):
                owner.stop(0.25)
        recovery = self.assert_macos_recovery(owner, guardian_forced=True)
        self.assertGreaterEqual(recovery['forced'], 1)
        self.assertFalse(alive())
        self.assertFalse(owner.mac.proof.exists())
        with patch.object(owner.mac.api, 'send') as send, self.assertRaises(TimeoutError):
            owner.stop(0)
        send.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS 제어 응답 오류')
    def test_macos_invalid_response_still_removes_owned_processes(self):
        owner, alive = self.start(child=True, early=False)
        self.owners.remove(owner)
        owner.mac.connection = Mock(wraps=owner.mac.connection)
        owner.mac.connection.recv.return_value = b'?'
        with self.assertRaisesRegex(RuntimeError, '제어 응답 불일치'):
            owner.stop(0.25)
        self.assertFalse(alive())
        self.assert_macos_recovery(owner, guardian_forced=None)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS 정리 실패와 재시도')
    def test_macos_preserves_timeout_with_drain_and_release_failures_then_retries(self):
        owner, alive = self.start(child=True, early=False, stubborn=True)
        self.owners.remove(owner)
        self.assertTrue(owner.mac.api.send(owner.mac.guardian, signal.SIGSTOP))
        owner.mac.connection = Mock(wraps=owner.mac.connection)
        owner.mac.connection.recv.side_effect = TimeoutError('주입된 소켓 Timeout')
        original = browser_macos.launchctl
        try:
            with (patch.object(owner.mac.api, 'drain', side_effect=OSError('coalition 조회 실패')),
                  patch.object(browser_macos, 'launchctl', wraps=original) as ctl,
                  self.assertRaises(ExceptionGroup) as first):
                owner.stop(0)
            ctl.assert_not_called()
            self.assertTrue(alive())
            self.assertEqual([type(error) for error in first.exception.exceptions], [TimeoutError, OSError])
            self.assertFalse(owner.control.with_suffix('.recovery.json').exists())
            with (patch.object(browser_macos, 'launchctl', side_effect=lambda *args: 0 if args[0] == 'bootout' else original(*args)),
                  self.assertRaises(ExceptionGroup) as second):
                owner.stop(0.25)
            self.assertIs(second.exception.exceptions[0], first.exception.exceptions[0])
            self.assertIn('작업 해제 실패', str(second.exception.exceptions[1]))
            self.assertFalse(alive())
            self.assertFalse(json.loads(owner.control.with_suffix('.recovery.json').read_text())['job_removed'])
        finally:
            with self.assertRaises(TimeoutError):
                owner.stop(0.25)
        self.assert_macos_recovery(owner, guardian_forced=True)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS audit token')
    def test_macos_rejects_stale_generation_for_live_owned_pid(self):
        from browser_macos import Coalition

        owner, alive = self.start(child=True)
        pid = json.loads((self.root/'ids-0.json').read_text())['child']
        api = Coalition()
        self.assertIsNone(api.member(pid, api.group(os.getpid())))
        _, version = api.member(pid, owner.mac.coalition)
        self.assertFalse(api.send((pid, version ^ 1), browser_processes.signal.SIGKILL))
        self.assertTrue(alive())

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS launchd 준비 경계')
    def test_macos_unverified_coalition_never_receives_node_command(self):
        from browser_macos import Coalition

        control = self.root/'exit.json'
        unexpected = self.root/'unexpected'
        command = [sys.executable, '-c', f'open({str(unexpected)!r},"x").close()']
        with (self.root/'log').open('w') as log, patch.object(Coalition, 'count', return_value=2):
            with self.assertRaisesRegex(RuntimeError, '전용 coalition 소유권 확인 실패'):
                browser_processes.OwnedBrowser(command, cwd=ROOT, env=dict(os.environ), stdout=log, control=control)
        self.assertFalse(unexpected.exists())
        self.assertFalse(control.with_suffix('.ready').exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS 제어 소켓 취소 경계')
    def test_macos_sigterm_to_controller_cleans_detached_child(self):
        from browser_macos import Coalition

        control = self.root/'exit.json'
        record = self.root/'child'
        child = f'import os,time;open({str(record)!r},"w").write(str(os.getpid()));time.sleep(120)'
        command = ('import subprocess,sys,time;'
                   f'subprocess.Popen([sys.executable,"-c",{child!r}],start_new_session=True);time.sleep(120)')
        script = f"""
import os, signal, sys
from pathlib import Path
from browser_processes import OwnedBrowser
def cancel(*_):
    raise SystemExit(42)
signal.signal(signal.SIGTERM, cancel)
owner = OwnedBrowser([sys.executable, '-c', {command!r}], cwd=Path.cwd(), env=dict(os.environ),
                     stdout=sys.stdout, control=Path({str(control)!r}))
try:
    owner.wait(120)
finally:
    owner.stop(1)
"""
        controller = subprocess.Popen([sys.executable, '-c', script], cwd=ROOT/'scripts', stdout=subprocess.DEVNULL)
        try:
            browser_processes.until(lambda: record.exists() and record.stat().st_size > 0, 10)
            pid = int(record.read_text())
            coalition = json.loads(control.with_suffix('.ready').read_text())['coalition']
            api = Coalition()
            self.assertIsNotNone(api.member(pid, coalition))
            controller.send_signal(signal.SIGTERM)
            self.assertEqual(controller.wait(10), 42)
            self.assertIsNone(api.member(pid, coalition))
            self.assertTrue(json.loads(control.with_suffix('.clean').read_text())['stopped'])
        finally:
            if controller.poll() is None:
                controller.terminate()
                controller.wait(10)

    @unittest.skipUnless(os.name == 'nt', 'Windows Job 마지막 핸들 종료 경계')
    def test_p204_windows_last_job_handle_close_kills_owned_child(self):
        owner, alive = self.start(child=True)
        owner.wait(10)
        owner.process.wait(10)
        self.assertTrue(alive())
        owner.job.close()
        browser_processes.until(lambda: not alive(), 5)
        owner.process.stdin.close()
        owner.stopped = True  # 위 실제 HANDLE 종료 관측이 확인된 뒤에만 test fixture 정리 완료.

    @unittest.skipIf(os.name == 'nt', 'POSIX 그룹 정체성 실패 경계')
    def test_p204_lost_posix_guardian_does_not_signal_unproven_group(self):
        owner = SimpleNamespace(stopped=False, job=None, process=Mock(), control=self.root/'missing-proof.json')
        owner.process.poll.return_value = 1
        with patch.object(browser_processes.os, 'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError, '보호 실패'):
                browser_processes.OwnedBrowser.stop(owner)
            kill.assert_not_called()

    def test_p204_closed_control_pipe_requires_verified_cleanup_proof(self):
        for verified in (True, False):
            with self.subTest(verified=verified):
                control = self.root/f'pipe-{verified}.json'
                if verified:
                    control.with_suffix('.clean').write_text(json.dumps({'stopped': True, 'forced': 0}))
                process = Mock(pid=999, returncode=1)
                process.poll.return_value = 1 if verified else None
                process.stdin.closed = False
                process.stdin.flush.side_effect = BrokenPipeError('controlled dead pipe')
                process.stdin.close.side_effect = BrokenPipeError('controlled dead pipe')
                owner = SimpleNamespace(stopped=False, job=None, process=process, control=control)
                with patch.object(browser_processes.os, 'getpgid', return_value=999, create=True):
                    if verified:
                        browser_processes.OwnedBrowser.stop(owner)
                        self.assertTrue(owner.stopped)
                        process.stdin.write.assert_not_called()
                    else:
                        with self.assertRaises(BrokenPipeError):
                            browser_processes.OwnedBrowser.stop(owner)
                        self.assertFalse(owner.stopped)


if __name__ == '__main__':
    unittest.main()
