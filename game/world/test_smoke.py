"""Smoke 타이밍·DB guard·CLI·실패 정리 계약. 실제 게임 시간 검증은 live 실행이 맡는다."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from server.conf.smoke_support import QUICK_TIMING, require_smoke, smoke_timings

from world.timing import PRODUCTION_TIMING, configured_timings

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from scripts import dev, smoke_harness  # noqa: E402


class SmokeContractsTests(TestCase):
    def test_production_defaults_and_full_timing_are_unchanged(self):
        expected = {
            "COMBAT_INTERVAL": 2.5, "CORPSE_TTL_SECONDS": 30, "RESPAWN_DELAY_SECONDS": 15,
            "LOOT_PROTECTION_SECONDS": 120, "CLAIM_TIMEOUT_SECONDS": 15,
            "PARTICIPATION_TIMEOUT_SECONDS": 15, "ENEMY_RESET_SECONDS": 15,
        }
        self.assertEqual(PRODUCTION_TIMING, expected)
        self.assertEqual(configured_timings(SimpleNamespace()), expected)
        self.assertEqual(smoke_timings("full"), expected)
        self.assertEqual(set(QUICK_TIMING), set(expected))
        self.assertTrue(all(0 < value < expected[key] for key, value in QUICK_TIMING.items()))
        config = SimpleNamespace(**{"PRIMAL_" + key: value for key, value in QUICK_TIMING.items()})
        self.assertEqual(configured_timings(config), smoke_timings("quick"))
        with self.assertRaises(ValueError):
            smoke_timings("invalid")

    def test_guard_rejects_normal_settings_before_fixture_database_access(self):
        with self.assertRaisesRegex(RuntimeError, "marker"):
            require_smoke(SimpleNamespace(PRIMAL_SMOKE=False))

    def test_marker_alone_cannot_authorize_other_database_or_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder).resolve()
            (run / ".primal-smoke").touch()
            config = SimpleNamespace(PRIMAL_SMOKE=True, PRIMAL_SMOKE_RUN_DIR=folder,
                                     GAME_DIR=str(run / "game"), DATABASES={"default": {
                                         "ENGINE": "django.db.backends.sqlite3",
                                         "NAME": str(run / "evennia-smoke.sqlite3")}})
            require_smoke(config)
            for engine, database, game in (
                ("django.db.backends.postgresql", "play", str(run / "game")),
                ("django.db.backends.sqlite3", str(run / "evennia.db3"), str(run / "game")),
                ("django.db.backends.sqlite3", str(run / "evennia-smoke.sqlite3"), str(PROJECT / "game")),
            ):
                with self.subTest(engine=engine, database=database, game=game):
                    bad = SimpleNamespace(**vars(config))
                    bad.DATABASES = {"default": {"ENGINE": engine, "NAME": database}}
                    bad.GAME_DIR = game
                    with self.assertRaises(RuntimeError):
                        require_smoke(bad)
            (run / ".primal-smoke").unlink()
            with self.assertRaises(RuntimeError):
                require_smoke(config)

    def test_smoke_environment_ignores_user_postgres_and_python_settings(self):
        with patch.dict(os.environ, {"PRIMAL_DB_NAME": "do-not-connect", "PRIMAL_DB_PASSWORD": "private",
                                    "DJANGO_SETTINGS_MODULE": "server.conf.settings",
                                    "PYTHONPATH": "unrelated"}):
            env = smoke_harness.smoke_environment(Path("isolated"), "full", {"ws": 12345})
        self.assertFalse(any(key.startswith("PRIMAL_DB_") for key in env))
        self.assertEqual(env["DJANGO_SETTINGS_MODULE"], "server.conf.settings_smoke")
        self.assertEqual(env["PRIMAL_SMOKE_MODE"], "full")
        self.assertEqual(env["PRIMAL_SMOKE_WS"], "12345")

    def test_loaded_smoke_settings_use_marker_sqlite_and_correct_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder).resolve()
            (run / ".primal-smoke").touch()
            game = run / "game"
            shutil.copytree(PROJECT / "game" / "server" / "conf", game / "server" / "conf",
                            ignore=shutil.ignore_patterns("secret_settings.py", "__pycache__"))
            (game / "server" / "conf" / "secret_settings.py").write_text("SECRET_KEY = 'temporary'\n")
            code = ("from django.conf import settings; from world.timing import configured_timings; "
                    "import json; print(json.dumps([settings.PRIMAL_SMOKE, settings.DATABASES, "
                    "configured_timings(settings), settings.NEW_ACCOUNT_REGISTRATION_ENABLED]))")
            for mode in ("quick", "full"):
                env = smoke_harness.smoke_environment(run, mode,
                                                     {"ws": 4102, "http": 4101, "internal": 4105, "amp": 4106})
                env["PYTHONPATH"] += os.pathsep + str(PROJECT / "game")
                output = subprocess.check_output([sys.executable, "-c", code], cwd=game, env=env, text=True)
                marker, databases, timing, registration = json.loads(output.splitlines()[-1])
                self.assertIs(marker, True)
                self.assertEqual(databases["default"]["NAME"], str(run / "evennia-smoke.sqlite3"))
                self.assertEqual(databases["default"]["ENGINE"], "django.db.backends.sqlite3")
                self.assertEqual(timing, smoke_timings(mode))
                self.assertIs(registration, False)

    def test_dev_cli_dispatches_quick_full_and_rejects_test_options(self):
        for command, mode in (("smoke", "quick"), ("smoke-full", "full")):
            with patch.object(sys, "argv", ["dev.py", command]), patch.object(dev, "run") as run:
                dev.main()
                run.assert_called_once_with(str(PROJECT / "scripts" / "smoke.py"), "--mode", mode,
                                            cwd=PROJECT)
            with patch.object(sys, "argv", ["dev.py", command, "--parallel", "2"]):
                with self.assertRaises(SystemExit) as error:
                    dev.main()
                self.assertEqual(error.exception.code, 2)
        with patch.object(sys, "argv", ["dev.py", "smoke-unknown"]):
            with self.assertRaises(SystemExit) as error:
                dev.main()
            self.assertEqual(error.exception.code, 2)

    def test_failure_stops_owned_process_and_next_run_has_clean_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(smoke_harness, "ROOT", Path(folder)):
            parent = Path(folder) / "work" / "smoke"
            parent.mkdir(parents=True)
            previous = None
            for failing in (True, False):
                harness = smoke_harness.Harness("quick")
                harness.run_dir = Path(tempfile.mkdtemp(dir=parent)).resolve()
                (harness.run_dir / ".primal-smoke").touch()
                self.assertNotEqual(harness.run_dir, previous)
                flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {
                    "start_new_session": True}
                process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **flags)
                harness.processes.append(("owned", process))

                async def scenario():
                    if failing:
                        raise AssertionError("harness failure injection")

                try:
                    if failing:
                        with self.assertRaisesRegex(AssertionError, "failure injection"):
                            asyncio.run(harness.supervise(scenario()))
                    else:
                        asyncio.run(harness.supervise(scenario()))
                finally:
                    harness.stop()
                self.assertIsNotNone(process.poll())
                previous = harness.run_dir
                harness.discard()
                self.assertFalse(previous.exists())

    def test_premature_exit_and_unsafe_cleanup_fail_explicitly(self):
        harness = smoke_harness.Harness("quick")
        harness.run_dir = PROJECT
        process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
        process.wait()
        harness.processes.append(("server", process))
        with self.assertRaisesRegex(RuntimeError, "조기 종료"):
            harness.check_alive()
        with self.assertRaisesRegex(RuntimeError, "소유권"):
            harness.discard()
