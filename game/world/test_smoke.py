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
sys.path.insert(0, str(PROJECT / "scripts"))
from scripts import dev, smoke_harness  # noqa: E402
from scripts.smoke_closeout import (  # noqa: E402
    assert_shutdown_items,
    assert_startup_items,
    stop_for_restart,
)


class SmokeContractsTests(TestCase):
    def test_shutdown_preserves_rows_and_only_settles_enabled_light_power(self):
        from copy import deepcopy

        saved = {"light": {"definition": "flashlight", "quantity": 1, "sequence": 8,
                           "location": "inventory", "parent": None, "slot": None, "socket": None,
                           "state": {"power_type": "battery", "remaining_power": 100,
                                     "enabled": True, "started_at": 10}},
                 "stack": {"definition": "bandage", "quantity": 3, "state": {}}}
        restored = deepcopy(saved)
        restored["light"]["state"].update(enabled=False, started_at=None, remaining_power=85)
        saved["off"] = deepcopy(saved["light"])
        saved["off"]["state"].update(enabled=False, started_at=None)
        restored["off"] = deepcopy(saved["off"])
        assert_shutdown_items(saved, restored, 20, 30)
        for field, value in (("quantity", 2), ("sequence", 9), ("location", "personal_storage"),
                             ("definition", "bandage"), ("parent", "other"),
                             ("slot", "hands"), ("socket", "magazine")):
            broken = deepcopy(restored)
            broken["light"][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                assert_shutdown_items(saved, broken, 20, 30)
        for field, value in (("remaining_power", 95), ("remaining_power", 75),
                             ("enabled", True), ("started_at", 20), ("power_type", "unknown")):
            broken = deepcopy(restored)
            broken["light"]["state"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(AssertionError):
                assert_shutdown_items(saved, broken, 20, 30)
        for identity, field, value in (("stack", "quantity", 2), ("stack", "state", {"changed": True}),
                                       ("stack", "parent", "other"), ("off", "state", {})):
            broken = deepcopy(restored)
            broken[identity][field] = value
            with self.subTest(identity=identity, field=field), self.assertRaises(AssertionError):
                assert_shutdown_items(saved, broken, 20, 30)
        for identity in ("stack", "added"):
            broken = deepcopy(restored)
            if identity == "stack":
                del broken[identity]
            else:
                broken[identity] = deepcopy(restored["stack"])
            with self.subTest(identity=identity), self.assertRaises(AssertionError):
                assert_shutdown_items(saved, broken, 20, 30)

    def test_startup_preserves_items_strictly_without_light_settlement_exception(self):
        from copy import deepcopy

        stopped = {"item": {"definition": "flashlight", "quantity": 1, "sequence": 8,
                             "location": "inventory", "parent": None, "slot": None, "socket": None,
                             "state": {"enabled": False, "started_at": None, "remaining_power": 85}}}
        assert_startup_items(stopped, deepcopy(stopped))
        for field, value in (("quantity", 2), ("sequence", 9), ("location", "personal_storage"),
                             ("parent", "other"), ("state", {"enabled": False, "remaining_power": 80})):
            restored = deepcopy(stopped)
            restored["item"][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                assert_startup_items(stopped, restored)
        with self.assertRaises(AssertionError):
            assert_startup_items(stopped, {})
        # startup은 ON → OFF 정산을 두 번째로 허용하지 않는다.
        live = deepcopy(stopped)
        live["item"]["state"].update(enabled=True, started_at=10)
        with self.assertRaises(AssertionError):
            assert_startup_items(live, stopped)

    def test_full_restart_requests_isolated_shutdown_and_checks_owned_process_exit(self):
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as folder:
            process = Mock()
            process.wait.return_value = 0
            harness = SimpleNamespace(mode="full", run_dir=Path(folder), env={"isolated": "yes"},
                                      processes=[("server", process)], check_alive=Mock())
            with patch("scripts.smoke_closeout.subprocess.run") as command:
                stop_for_restart(harness)
                arguments = command.call_args.args[0]
                self.assertEqual(arguments, [sys.executable, "-m", "evennia", "stop",
                                             "--settings", "settings_smoke"])
                self.assertEqual(command.call_args.kwargs["cwd"], Path(folder) / "game")
                self.assertEqual(command.call_args.kwargs["env"], harness.env)
                self.assertTrue(command.call_args.kwargs["check"])
                process.wait.return_value = 1
                with self.assertRaises(AssertionError):
                    stop_for_restart(harness)
            harness.mode = "quick"
            with patch("scripts.smoke_closeout.subprocess.run") as command, self.assertRaises(AssertionError):
                stop_for_restart(harness)
            command.assert_not_called()

    def test_enemy_delay_canonical_setting_precedes_legacy_fallback(self):
        key = "ENEMY_RECOVERY_DELAY_SECONDS"
        self.assertEqual(configured_timings(SimpleNamespace(PRIMAL_ENEMY_RESET_SECONDS=3))[key], 3)
        self.assertEqual(configured_timings(SimpleNamespace(
            PRIMAL_ENEMY_RESET_SECONDS=3, PRIMAL_ENEMY_RECOVERY_DELAY_SECONDS=7))[key], 7)
        self.assertEqual(PRODUCTION_TIMING[key], 15)
        self.assertEqual(QUICK_TIMING[key], 2)

    def test_production_defaults_and_full_timing_are_unchanged(self):
        expected = {
            "COMBAT_INTERVAL": 2.5, "CORPSE_TTL_SECONDS": 30, "RESPAWN_DELAY_SECONDS": 15,
            "LOOT_PROTECTION_SECONDS": 120, "CLAIM_TIMEOUT_SECONDS": 15,
            "PARTICIPATION_TIMEOUT_SECONDS": 15, "ENEMY_RECOVERY_DELAY_SECONDS": 15,
        }
        self.assertEqual(PRODUCTION_TIMING, expected)
        self.assertEqual(configured_timings(SimpleNamespace()), expected)
        self.assertEqual(smoke_timings("full"), expected)
        self.assertEqual(set(QUICK_TIMING), set(expected))
        idle_deadlines = {"COMBAT_INTERVAL", "CLAIM_TIMEOUT_SECONDS", "PARTICIPATION_TIMEOUT_SECONDS"}
        self.assertTrue(all(0 < value < expected[key] for key, value in QUICK_TIMING.items()
                            if key not in idle_deadlines))
        # 처리/화면 전송 지연이 공격 기회보다 길어도 Quick 참가 자격이 사라지지 않는다.
        self.assertEqual({key: QUICK_TIMING[key] for key in idle_deadlines},
                         {key: expected[key] for key in idle_deadlines})
        self.assertGreaterEqual(QUICK_TIMING['CORPSE_TTL_SECONDS'], 10)
        self.assertGreater(QUICK_TIMING['LOOT_PROTECTION_SECONDS'],
                           QUICK_TIMING['CORPSE_TTL_SECONDS'] + QUICK_TIMING['RESPAWN_DELAY_SECONDS'])
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
                self.assertEqual(databases["default"]["OPTIONS"]["timeout"], 30)
                self.assertEqual(databases["default"]["OPTIONS"]["transaction_mode"], "IMMEDIATE")
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


class SmokeRestartTests(TestCase):
    def test_restart_reuses_directory_database_and_ports_without_fixture_reset(self):
        harness = smoke_harness.Harness("full")
        harness.run_dir = Path("same-isolated-db")
        harness.env = {"PRIMAL_SMOKE_MODE": "full"}
        harness.ports = {"ws": 12345}
        events = []
        stopped = {"players": {"fixture": {"profile": {"xp": 12}}}}

        def checkpoint():
            events.append("checkpoint")
            return stopped

        async def ready():
            self.assertTrue(harness.restarting)
            events.append("ready")

        with patch.object(harness, "stop", side_effect=lambda: events.append("stop")), patch.object(
            harness, "start", side_effect=lambda: events.append("start")
        ), patch.object(harness, "ready", side_effect=ready), patch.object(
            harness, "checkpoint", side_effect=checkpoint
        ), patch.object(harness, "prepare") as prepare:
            self.assertEqual(asyncio.run(harness.restart()), stopped)
        self.assertEqual(events, ["stop", "checkpoint", "start", "ready"])
        self.assertEqual(harness.run_dir, Path("same-isolated-db"))
        self.assertEqual(harness.ports, {"ws": 12345})
        self.assertEqual(harness.env, {"PRIMAL_SMOKE_MODE": "full"})
        self.assertFalse(harness.restarting)
        prepare.assert_not_called()

    def test_restart_failure_restores_premature_exit_monitoring(self):
        harness = smoke_harness.Harness("full")
        with patch.object(harness, "stop"), patch.object(harness, "checkpoint", return_value={}), patch.object(
            harness, "start", side_effect=RuntimeError("start failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                asyncio.run(harness.restart())
        self.assertFalse(harness.restarting)
