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
        for args in (["init", "-q"], ["add", "."], ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
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

    def test_t04_timeout_cancel_owned_tree_and_other_process_protection(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (other.terminate(), other.wait(timeout=3)) if other.poll() is None else None)
        for timeout, expected in ((0.5, "TIMED_OUT"), (10, "CANCELLED")):
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
            with patch("codex_watch.shutil.which", return_value="fixture-codex"), patch("codex_watch.Execution", return_value=guard) as factory:
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
        missing = Mock()
        missing.poll.return_value = None
        with patch("codex_wait.subprocess.Popen", return_value=missing):
            timeout = cli.start(request)
        cli._workers.pop(timeout["job_id"], None)
        self.assertFalse(timeout["ready"])
        self.assertEqual(timeout["status"], "TIMED_OUT")
        self.assertEqual(cli.status(self.root, timeout["job_id"])["phase"], "READY")
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
        owned, request = self.saved_job(self.request(thread="fixture-thread"))
        with patch("codex_watch.sys.platform", "darwin"), patch("codex_watch.Execution") as launch, \
                patch("codex_watch.subprocess.run") as external:
            worker.run_worker(self.root, request["job_id"])
        launch.assert_not_called()
        external.assert_not_called()
        final = worker.read_json(owned / "result.json")
        self.assertEqual((final["status"], final["test_status"], final["phase"]),
                         ("ERROR", "NOT_STARTED", "platform_initialization"))
        self.assertFalse(final["cleanup_verified"])
        self.assertEqual(worker.read_json(owned / "notification.json")["status"], "UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
