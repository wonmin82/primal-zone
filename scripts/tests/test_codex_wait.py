"""게임 서버나 새 CI Run 없이 감시기의 소유권·결과 계약을 검증한다."""

import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import codex_wait as cli  # noqa: E402
import codex_watch as worker  # noqa: E402
import smoke_harness  # noqa: E402

FAKE_DEV = '''import json, os, pathlib, subprocess, sys, time
root = pathlib.Path.cwd()
action = os.environ.get("WATCH_TEST_ACTION", "success")
print("fixture output", flush=True)
if action == "handshake":
    deadline = time.monotonic() + 3
    while not (root / "work" / "parent-exited").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("fixture parent did not return")
        time.sleep(0.005)
if action in ("sleep", "tree"):
    if action == "tree":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 start_new_session=os.name != "nt")
        (root / "work" / "child.json").write_text(json.dumps({"pid": child.pid}))
    time.sleep(30)
if action == "stale":
    (root / "source.py").write_text("changed = True\\n")
sys.exit(7 if action == "failure" else 0)
'''


def until(condition, timeout=3):
    deadline = time.monotonic() + timeout
    while True:
        value = condition()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise AssertionError("짧은 fixture 완료 제한시간 초과")
        time.sleep(0.005)


class WatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_directory = tempfile.TemporaryDirectory(prefix="primal-watch-template-")
        cls.addClassCleanup(cls.template_directory.cleanup)
        cls.template = Path(cls.template_directory.name).resolve()
        (cls.template / "scripts").mkdir()
        (cls.template / "scripts" / "dev.py").write_text(FAKE_DEV, encoding="utf-8")
        (cls.template / "source.py").write_text("original = True\n")
        (cls.template / ".gitignore").write_text("work/\n")
        # 복사 중 .git/objects/maintenance.lock이 사라지는 background 경합을
        # 테스트 전용 저장소에서만 차단한다. 사용자/프로젝트 설정은 바꾸지 않는다.
        for args in (["init", "-q"], ["config", "--local", "maintenance.auto", "false"],
                     ["config", "--local", "gc.auto", "0"], ["add", "."],
                     ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                                       "commit", "-qm", "fixture"]):
            subprocess.run(["git", "-C", str(cls.template), *args], capture_output=True, check=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="primal-watch-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        shutil.copytree(self.template, self.root, dirs_exist_ok=True)
        (self.root / "work").mkdir()
        self.jobs = []
        self.addCleanup(self.stop_jobs)

    def stop_jobs(self):
        for job_id in self.jobs:
            value = cli.cancel(self.root, job_id)
            if value.get("cancel_requested"):
                until(lambda: cli.status(self.root, job_id)["status"] in worker.TERMINAL)
            process = cli._workers.pop(job_id, None)
            if process is not None:
                process.wait(timeout=3)
            else:
                final = cli.status(self.root, job_id)
                if final.get("worker_pid"):
                    until(lambda: not worker.identity_alive(final["worker_pid"], final.get("worker_identity")))

    def request(self, **options):
        return cli.validate_request(self.root, kind="local", **options)

    def launch(self, action="success", **options):
        with patch.dict(os.environ, WATCH_TEST_ACTION=action):
            result = cli.start(self.request(**options))
        self.jobs.append(result["job_id"])
        return result

    def completed(self, job_id):
        return until(lambda: (value if (value := cli.status(self.root, job_id))["status"] in worker.TERMINAL else None))

    def saved_job(self, request):
        job_id = os.urandom(16).hex()
        directory = worker.job_directory(self.root, job_id)
        directory.mkdir()
        request = {**request, "job_id": job_id, "nonce": os.urandom(16).hex(),
                   "parent_pid": os.getpid(), "parent_identity": worker.process_identity(os.getpid()),
                   "ready_deadline": time.time() + 5}
        worker.atomic_json(directory / "request.json", request)
        worker.atomic_json(directory / "state.json", {"job_id": job_id, "nonce": request["nonce"], "status": "STARTING", "ready": False})
        worker.atomic_json(directory / "notification.json", {"status": "NOT_REQUESTED", "attempted": False})
        return directory, request

    def test_t01_local_success_ready_independent_and_result(self):
        self.assertEqual(worker.git(self.root, "config", "--local", "--get", "maintenance.auto").strip(), b"false")
        self.assertEqual(worker.git(self.root, "config", "--local", "--get", "gc.auto").strip(), b"0")
        with patch.dict(os.environ, WATCH_TEST_ACTION="handshake", PYTHONUTF8="1"):
            parent = subprocess.run([sys.executable, str(ROOT / "scripts" / "codex_wait.py"),
                                     "local", "--parallel", "2", "tests.selected"],
                                    cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=3, check=True)
        result = json.loads(parent.stdout)
        self.jobs.append(result["job_id"])
        self.assertTrue(result["ready"])
        directory = worker.job_directory(self.root, result["job_id"])
        request = worker.read_json(directory / "request.json")
        self.assertIsNone(worker.process_identity(request["parent_pid"]))
        self.assertEqual(cli.status(self.root, result["job_id"])["status"], "RUNNING")
        (self.root / "work" / "parent-exited").touch()
        final = self.completed(result["job_id"])
        self.assertEqual((final["status"], final["exit_code"]), ("PASSED", 0))
        self.assertEqual(final["target"]["python"], sys.executable)
        self.assertEqual(final["target"]["labels"], ["tests.selected"])
        self.assertTrue(final["cleanup_verified"])
        self.assertTrue(all((directory / file).is_file() for file in
                            ("request.json", "state.json", "result.json", "output.log", "notification.json")))
        request = worker.read_json(directory / "request.json")
        self.assertEqual(request["parallel"], 2)
        self.assertEqual(request["labels"], ["tests.selected"])
        self.assertNotEqual(request["job_id"], request["nonce"])
        self.assertIn("fixture output", (directory / "output.log").read_text())
        self.assertEqual(final["notification"]["status"], "NOT_REQUESTED")
        # macOS 커널 호출의 모의 계약 검증이며 실환경 PASS가 아니다.
        directory, request = self.saved_job(self.request())
        anchor = Mock(pid=4321, returncode=0)
        anchor.poll.return_value = None
        with patch("codex_watch.subprocess.Popen", return_value=anchor) as spawn, \
                patch("codex_watch.process_identity", return_value="born"), \
                patch("codex_watch.os.getpgid", return_value=4321, create=True), \
                patch("codex_watch.os.getsid", return_value=4321, create=True):
            group = worker.MacGroup(directory, request, ["fixture"], None, None)
            self.assertTrue(spawn.call_args.kwargs["start_new_session"])
            self.assertTrue(group.owned())
        worker.atomic_json(group.path / "exit.json", {"nonce": group.boundary["nonce"], "exit_code": 0})
        self.assertEqual(group.result(), 0)
        self.assertIsNone(anchor.poll())
        with patch.object(group, "owned", return_value=True), patch("codex_watch.clean_anchored_group", return_value=True), \
                patch("codex_watch.signal.SIGKILL", 9, create=True):
            self.assertTrue(group.cleanup())
        self.assertTrue((group.path / "release").exists())
        if os.name == "posix":
            with self.subTest(platform="POSIX supervisor kernel contract"):
                directory, request = self.saved_job(self.request())
                child_path = directory / "child.json"
                program = ("import subprocess,sys,pathlib,json; "
                           "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
                           f"pathlib.Path({str(child_path)!r}).write_text(json.dumps(p.pid))")
                with (directory / "output.log").open("ab") as output:
                    group = worker.MacGroup(directory, request, [sys.executable, "-c", program], output, output)
                    try:
                        until(lambda: group.result() is not None)
                        self.assertEqual(group.result(), 0)
                        self.assertTrue(group.owned())
                        child_pid = json.loads(child_path.read_text())
                        self.assertTrue(group.cleanup())
                        self.assertIsNone(worker.process_identity(child_pid))
                    finally:
                        if group.process.poll() is None:
                            group.cleanup()

    def test_t02_failure_and_worker_start_error_are_not_success(self):
        launched = self.launch("failure")
        final = self.completed(launched["job_id"])
        self.assertEqual((final["status"], final["exit_code"], final["test_status"]), ("FAILED", 7, "FAILED"))
        request = self.request(command="smoke")
        with patch("codex_wait.subprocess.Popen", side_effect=OSError("fixture startup error")):
            failed = cli.start(request)
        self.assertEqual(failed["status"], "ERROR")
        self.assertEqual(cli.status(self.root, failed["job_id"])["phase"], "worker_start")
        with self.assertRaises(ValueError):
            self.request(labels=["--settings=production"])
        invalid = self.request()
        invalid["command"] = "setup"
        rejected = cli.start(invalid)
        self.jobs.append(rejected["job_id"])
        self.assertEqual(rejected["status"], "ERROR")
        self.assertFalse(rejected["ready"])
        self.assertNotIn("fixture output", (worker.job_directory(self.root, rejected["job_id"]) / "output.log").read_text())
        owned, request = self.saved_job(self.request())
        execution = worker.Execution(owned, request)
        failed_cleanup = Mock()
        failed_cleanup.result.return_value = 0
        failed_cleanup.cleanup.return_value = False
        with patch("codex_watch.MacGroup", return_value=failed_cleanup):
            with self.assertRaisesRegex(RuntimeError, "정리 미확인"):
                execution.run_mac(["fixture"])
        self.assertEqual(execution.last_exit_code, 0)

    def test_t03_ci_result_identity_attempt_pr_and_query_errors(self):
        request = {"run_id": 17, "repo": "fixture/project", "sha": "a" * 40, "attempt": 2, "pr": 3}
        run = {"databaseId": 17, "attempt": 2, "headSha": "a" * 40, "status": "completed", "conclusion": "success"}

        class FakeExecution:
            def __init__(self, values):
                self.request = request
                self.values = iter(values)
                self.calls = []

            def run(self, args, capture=False):
                self.calls.append(args)
                value = next(self.values)
                return value if isinstance(value, tuple) else (0, json.dumps(value).encode(), b"")

        for conclusion, expected in (("success", "PASSED"), ("failure", "FAILED"), ("cancelled", "CANCELLED"), ("timed_out", "TIMED_OUT")):
            with self.subTest(conclusion=conclusion):
                value = {**run, "conclusion": conclusion}
                execution = FakeExecution([value, {"headRefOid": "a" * 40}, value, {"headRefOid": "a" * 40}])
                self.assertEqual(worker.ci_run(execution)["status"], expected)
        for field, changed in (("attempt", 3), ("headSha", "b" * 40)):
            with self.subTest(stale=field):
                self.assertEqual(worker.ci_run(FakeExecution([{**run, field: changed}]))["status"], "STALE")
        execution = FakeExecution([run, {"headRefOid": "a" * 40}, run, {"headRefOid": "b" * 40}])
        self.assertEqual(worker.ci_run(execution)["status"], "STALE")
        execution = FakeExecution([{**run, "status": "in_progress"}, {"headRefOid": "a" * 40},
                                   (0, b"", b""), {**run, "attempt": 3}])
        self.assertEqual(worker.ci_run(execution)["status"], "STALE")
        execution = FakeExecution([{**run, "status": "in_progress", "conclusion": None}, {"headRefOid": "a" * 40},
                                   (1, b"", b""), run, {"headRefOid": "a" * 40}])
        self.assertEqual(worker.ci_run(execution)["status"], "PASSED")
        self.assertEqual(sum("watch" in call for call in execution.calls), 1)
        with self.assertRaisesRegex(RuntimeError, "조회 오류"):
            worker.ci_run(FakeExecution([(1, b"", b"private error")]))
        with self.assertRaisesRegex(RuntimeError, "JSON 오류"):
            worker.ci_run(FakeExecution([(0, b"broken", b"")]))
        with patch("codex_wait.lookup_attempt", return_value=2):
            implicit = cli.validate_request(self.root, kind="ci", repo="fixture/project", run_id=17, sha="a" * 40)
        explicit = cli.validate_request(self.root, kind="ci", repo="fixture/project", run_id=17, sha="a" * 40, attempt=2)
        self.assertEqual(implicit["key"], explicit["key"])
        directory = self.root / "work" / "result-fixture"
        directory.mkdir()
        saved = {**explicit, "job_id": "a" * 32, "nonce": "b" * 32}
        with patch("codex_watch.notify"):
            worker.finish(directory, saved, {"status": "ERROR", "exit_code": None}, time.monotonic())
        self.assertEqual(worker.read_json(directory / "result.json")["target"],
                         {name: saved.get(name) for name in ("repo", "run_id", "attempt", "sha", "pr")})
        owned, saved = self.saved_job(explicit)
        execution = Mock()
        execution.cleanup.return_value = True
        with patch("codex_watch.sys.platform", "darwin"), patch("codex_watch.WindowsJob"), \
                patch("codex_watch.Execution", return_value=execution), \
                patch("codex_watch.ci_run", return_value={"status": "PASSED", "exit_code": 0, "run": run}), \
                patch("codex_watch.notify"):
            worker.run_worker(self.root, saved["job_id"])
        self.assertEqual(worker.read_json(owned / "result.json")["status"], "PASSED")

    def test_t04_timeout_cancel_owned_tree_and_other_process_protection(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (other.terminate(), other.wait(timeout=3)) if other.poll() is None else None)
        # Worker 초기화 자체를 재는 대신 자식 생성 후 트리 정리를 관측한다.
        # Windows에서 0.5초는 실제 fixture 자식 시작 전 만료될 수 있다.
        for timeout, expected in ((2, "TIMED_OUT"), (10, "CANCELLED")):
            with self.subTest(expected=expected):
                child_file = self.root / "work" / "child.json"
                child_file.unlink(missing_ok=True)
                launched = self.launch("tree", timeout=timeout)
                until(child_file.exists)
                child = json.loads(child_file.read_text())["pid"]
                self.assertIsNotNone(worker.process_identity(child))
                if expected == "CANCELLED":
                    self.assertTrue(cli.cancel(self.root, launched["job_id"])["cancel_requested"])
                final = self.completed(launched["job_id"])
                self.assertEqual(final["status"], expected)
                self.assertIsInstance(final["exit_code"], int)
                self.assertTrue(final["cleanup_verified"])
                self.assertIsNone(worker.process_identity(child))
                self.assertIsNone(other.poll())
        anchor, child = 4321, 4322
        with patch("codex_watch.group_processes", side_effect=[[(anchor, 1, anchor, "S"), (child, anchor, anchor, "S")],
                                                              [(anchor, 1, anchor, "S")]]), \
                patch("codex_watch.process_identity", return_value="born"), \
                patch("codex_watch.identity_alive", return_value=True), \
                patch("codex_watch.os.getpgid", return_value=anchor, create=True), \
                patch("codex_watch.os.getsid", return_value=anchor, create=True), \
                patch("codex_watch.os.killpg", create=True) as terminate_group, \
                patch("codex_watch.os.kill") as kill_pid, patch("codex_watch.signal.SIGKILL", 9, create=True):
            self.assertTrue(worker.clean_anchored_group(anchor, lambda: True))
            terminate_group.assert_called_once_with(anchor, worker.signal.SIGTERM)
            kill_pid.assert_called_once_with(child, 9)
        with patch("codex_watch.os.killpg", create=True) as terminate_group:
            self.assertFalse(worker.clean_anchored_group(anchor, lambda: False))
            terminate_group.assert_not_called()
        group = worker.MacGroup.__new__(worker.MacGroup)
        group.process = Mock(pid=anchor)
        group.escaped = False
        with patch.object(group, "owned", return_value=True), \
                patch("codex_watch.group_processes", return_value=[(anchor, 1, anchor, "S"), (child, anchor, 999, "S")]), \
                patch("codex_watch.os.getsid", return_value=999, create=True):
            with self.assertRaisesRegex(RuntimeError, "이탈"):
                group.observe()
            self.assertTrue(group.escaped)
        directory, request = self.saved_job(self.request())
        boundary_path = directory / ("execution-" + "a" * 32) / "boundary.json"
        boundary_path.parent.mkdir()
        value = {"repository": str(self.root), "job_id": request["job_id"], "execution_id": boundary_path.parent.name,
                 "nonce": "b" * 32, "pgid": anchor, "sid": anchor, "anchor_pid": anchor,
                 "anchor_identity": "born", "worker_pid": os.getpid(), "worker_identity": "parent"}
        worker.atomic_json(boundary_path, value)
        environment = {"PRIMAL_CODEX_WATCH_BOUNDARY": str(boundary_path), "PRIMAL_CODEX_WATCH_NONCE": "b" * 32}
        with patch("codex_watch.sys.platform", "darwin"), patch("codex_watch.identity_alive", return_value=True), \
                patch("codex_watch.os.getpgid", return_value=anchor, create=True), \
                patch("codex_watch.os.getsid", return_value=anchor, create=True):
            self.assertEqual(worker.boundary_from_environment(environment), value)
            for marker_nonce, environment_nonce in ((None, None), ("", ""), ("invalid", "invalid"),
                                                     ("b" * 32, None), (None, "b" * 32), ("b" * 32, "c" * 32)):
                with self.subTest(marker_nonce=marker_nonce, environment_nonce=environment_nonce):
                    marker = {key: item for key, item in value.items() if key != "nonce"}
                    env = {key: item for key, item in environment.items() if key != "PRIMAL_CODEX_WATCH_NONCE"}
                    if marker_nonce is not None:
                        marker["nonce"] = marker_nonce
                    if environment_nonce is not None:
                        env["PRIMAL_CODEX_WATCH_NONCE"] = environment_nonce
                    worker.atomic_json(boundary_path, marker)
                    with self.assertRaisesRegex(RuntimeError, "불일치"):
                        worker.boundary_from_environment(env)
            worker.atomic_json(boundary_path, value)
            with patch("codex_watch.os.getsid", return_value=999):
                with self.assertRaisesRegex(RuntimeError, "불일치"):
                    worker.boundary_from_environment(environment)
            with patch("codex_watch.read_json") as read:
                with self.assertRaisesRegex(RuntimeError, "경로 오류"):
                    worker.boundary_from_environment({**environment, "PRIMAL_CODEX_WATCH_BOUNDARY": str(self.root / "secret.json")})
                read.assert_not_called()
        harness = smoke_harness.Harness("quick")
        harness.run_dir = self.root
        (self.root / "game").mkdir(exist_ok=True)
        harness.env = {}
        boundary = {"pgid": anchor, "sid": anchor}
        posix = Mock(wraps=os)
        posix.name = "posix"
        posix.getpgid = Mock(return_value=anchor)
        posix.getsid = Mock(return_value=anchor)
        posix.killpg = Mock()
        processes = [Mock(pid=4322), Mock(pid=4323)]
        for process in processes:
            process.returncode = None
            process.poll.side_effect = lambda item=process: item.returncode
            process.terminate.side_effect = lambda item=process: setattr(item, "returncode", -15)
        with patch("smoke_harness.os", posix), patch("smoke_harness.boundary_from_environment", return_value=boundary), \
                patch("smoke_harness.process_identity", return_value="born"), \
                patch("smoke_harness.identity_alive", return_value=True), \
                patch("smoke_harness.subprocess.Popen", side_effect=processes) as spawn:
            harness.start()
            self.assertTrue(all(not call.kwargs["start_new_session"] for call in spawn.call_args_list))
            harness.stop()
            posix.killpg.assert_not_called()
            for process in processes:
                process.terminate.assert_called_once_with()
        harness.processes.clear()
        harness.handles.clear()
        with patch("smoke_harness.os", posix), patch("smoke_harness.boundary_from_environment", return_value=None), \
                patch("smoke_harness.subprocess.Popen", side_effect=processes) as spawn:
            harness.start()
            self.assertTrue(all(call.kwargs["start_new_session"] for call in spawn.call_args_list))
        for handle in harness.handles:
            handle.close()

    def test_t05_notification_support_failure_once_and_result_first(self):
        directory = self.root / "work"
        request = {"job_id": "a" * 32, "thread": "fixture-thread"}
        result = {"status": "FAILED", "exit_code": 7, "elapsed_seconds": 0.1}
        worker.atomic_json(directory / "result.json", result)
        for supported, code, expected in ((False, 0, "UNSUPPORTED"), (True, 0, "ACCEPTED_UNCONFIRMED"), (True, 1, "FAILED")):
            worker.atomic_json(directory / "notification.json", {"status": "NOT_REQUESTED", "attempted": False})

            def invoke(args, **kwargs):
                self.assertEqual(worker.read_json(directory / "result.json"), result)
                if "--help" in args:
                    return (0 if supported else 2), b"--thread --message", b""
                message = args[args.index("--message") + 1]
                self.assertNotIn("fixture output", message)
                self.assertIn("exit_code=7", message)
                return code, b"", b""

            guard = Mock()
            guard.run.side_effect = invoke
            guard.cleanup.return_value = True
            with patch("codex_watch.sys.platform", "darwin"), patch("codex_watch.shutil.which", return_value="fixture-codex"), patch("codex_watch.Execution", return_value=guard) as factory:
                worker.notify(directory, request, result, execution=Mock(windows_job=None))
                count = guard.run.call_count
                worker.notify(directory, request, result, execution=Mock(windows_job=None))
                self.assertEqual(guard.run.call_count, count)
                self.assertFalse(factory.call_args.kwargs["honour_cancel"])
            notification = worker.read_json(directory / "notification.json")
            self.assertEqual(notification["status"], expected)
            self.assertEqual(notification["session_resumed"], "UNVERIFIED")
            self.assertTrue(notification["cleanup_verified"])
        worker.atomic_json(directory / "notification.json", {"status": "NOT_REQUESTED", "attempted": False})
        guard.run.side_effect = [ (0, b"--thread --message", b""), worker.StopRequested("TIMED_OUT")]
        with patch("codex_watch.shutil.which", return_value="fixture-codex"), patch("codex_watch.Execution", return_value=guard):
            worker.notify(directory, request, result, execution=Mock(windows_job=None))
        self.assertEqual(worker.read_json(directory / "notification.json")["status"], "FAILED")
        self.assertEqual(worker.read_json(directory / "result.json"), result)

    def test_t06_recovery_stale_corruption_duplicates_and_ready_timeout(self):
        stale = self.launch("stale")
        value = self.completed(stale["job_id"])
        self.assertEqual((value["status"], value["test_status"], value["exit_code"]), ("STALE", "PASSED", 0))
        with patch("codex_wait.watch.repository_root", return_value=self.root), patch("builtins.print"):
            self.assertEqual(cli.main(["status", stale["job_id"]]), 1)
        directory = worker.job_directory(self.root, stale["job_id"])
        original_request = worker.read_json(directory / "request.json")
        for missing in ("nonce", "key", "kind", "python", "baseline", "ready_timeout"):
            bad = {name: value for name, value in original_request.items() if name != missing}
            worker.atomic_json(directory / "request.json", bad)
            self.assertEqual(cli.status(self.root, stale["job_id"])["status"], "ERROR", missing)
        worker.atomic_json(directory / "request.json", original_request)
        worker.atomic_json(directory / "result.json", {**value, "status": "PASSED", "exit_code": None})
        self.assertEqual(cli.status(self.root, stale["job_id"])["status"], "ERROR")
        (directory / "result.json").write_text("broken")
        self.assertEqual(cli.status(self.root, stale["job_id"])["status"], "ERROR")
        (directory / "result.json").unlink()
        state = worker.read_json(directory / "state.json")
        worker.atomic_json(directory / "state.json", {**state, "status": "RUNNING", "worker_pid": os.getpid(),
                                                     "worker_identity": "fixture-impossible-start"})
        self.assertEqual(cli.status(self.root, stale["job_id"])["status"], "INTERRUPTED")
        with self.assertRaises(ValueError):
            cli.status(self.root, "../../outside")
        with patch.dict(os.environ, WATCH_TEST_ACTION="sleep"):
            request = self.request(timeout=10)
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                results = list(pool.map(lambda _: cli.start(request), range(2)))
        job_id = results[0]["job_id"]
        self.jobs.append(job_id)
        self.assertEqual(results[1]["job_id"], job_id)
        self.assertEqual(sum(item.get("duplicate", False) for item in results), 1)
        self.assertTrue(all(item["ready"] for item in results))
        cli.cancel(self.root, job_id)
        self.assertEqual(self.completed(job_id)["status"], "CANCELLED")
        request = self.request(command="smoke-full", ready_timeout=0.01)
        missing = Mock(pid=os.getpid())
        missing.poll.return_value = None
        with patch("codex_wait.subprocess.Popen", return_value=missing):
            timeout = cli.start(request)
        cli._workers.pop(timeout["job_id"], None)
        self.assertFalse(timeout["ready"])
        self.assertEqual(timeout["status"], "TIMED_OUT")
        self.assertFalse((worker.job_directory(self.root, timeout["job_id"]) / "result.json").exists())
        self.assertTrue((worker.job_directory(self.root, timeout["job_id"]) / "cancel").exists())
        directory, request = self.saved_job(self.request(ready_timeout=2))
        dead = Mock(returncode=23)
        dead.poll.return_value = 23
        cli._workers[request["job_id"]] = dead
        began = time.monotonic()
        interrupted = cli.await_ready(request, False)
        self.assertEqual(interrupted["status"], "INTERRUPTED")
        self.assertLess(time.monotonic() - began, 1)
        self.assertFalse((directory / "result.json").exists())
        cli._workers.pop(request["job_id"], None)
        real_popen = subprocess.Popen
        def early_exit(args, **kwargs):
            if len(args) > 1 and str(args[1]).endswith("codex_watch.py"):
                args = [sys.executable, "-c", "raise SystemExit(23)"]
            return real_popen(args, **kwargs)
        with patch("codex_wait.subprocess.Popen", side_effect=early_exit):
            interrupted = cli.start(self.request(parallel=3))
        self.jobs.append(interrupted["job_id"])
        self.assertEqual(interrupted["status"], "INTERRUPTED")
        self.assertFalse((worker.job_directory(self.root, interrupted["job_id"]) / "result.json").exists())
        directory, request = self.saved_job(self.request())
        with patch("codex_watch.notify"):
            worker.finish(directory, request, {"status": "FAILED", "exit_code": 7, "cleanup_verified": True}, time.monotonic())
        before_result = (directory / "result.json").read_bytes()
        request["ready_deadline"] = time.time() - 1
        self.assertEqual(cli.await_ready(request, False)["status"], "FAILED")
        self.assertEqual((directory / "result.json").read_bytes(), before_result)
        active = worker.work_root(self.root) / (".active-" + request["key"] + ".json")
        worker.atomic_json(active, {"job_id": request["job_id"]})
        with patch("codex_watch.notify"):
            worker.finish(directory, request, {"status": "ERROR", "exit_code": 0, "cleanup_verified": False}, time.monotonic())
        self.assertEqual(worker.read_json(active)["job_id"], request["job_id"])
        before = worker.snapshot(self.root)
        private_paths = [self.root / name for name in ("secret_settings.py", ".env", "secrets.py", "credentials.py", ".codex/auth.json")]
        for path in private_paths:
            path.parent.mkdir(exist_ok=True)
            path.write_text("private")
        read = Path.read_bytes
        def observe(path):
            self.assertNotIn(path, private_paths)
            return read(path)
        with patch.object(Path, "read_bytes", side_effect=observe, autospec=True):
            self.assertEqual(worker.snapshot(self.root), before)
        if os.name == "nt":
            junction_root, outside = self.root / "junction-root", self.root / "outside"
            junction_root.mkdir()
            outside.mkdir()
            marker = outside / "sentinel"
            marker.write_text("preserved")
            link = junction_root / "work"
            subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
            try:
                with self.assertRaises(ValueError), worker.registry_lock(junction_root):
                    self.fail("junction을 소유 경로로 사용하면 안 됩니다.")
                self.assertEqual(list(outside.iterdir()), [marker])
                self.assertEqual(marker.read_text(), "preserved")
            finally:
                link.rmdir()
        for code in (0, 7):
            owned, request = self.saved_job(self.request())
            execution = Mock(last_exit_code=code)
            execution.run.return_value = (code, b"", b"")
            execution.cleanup.return_value = True
            with patch("codex_watch.WindowsJob"), patch("codex_watch.Execution", return_value=execution), \
                    patch("codex_watch.snapshot", side_effect=[request["baseline"], OSError("fixture fingerprint failure")]):
                worker.run_worker(self.root, request["job_id"])
            final = worker.read_json(owned / "result.json")
            self.assertEqual((final["status"], final["exit_code"], final["test_status"]),
                             ("ERROR", code, "PASSED" if code == 0 else "FAILED"))


if __name__ == "__main__":
    unittest.main()
