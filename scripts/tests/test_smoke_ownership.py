"""운영 DB를 열지 않는 격리 DB 관측 경계의 회귀."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import action_e2e  # noqa: E402
from smoke_harness import Harness, smoke_environment  # noqa: E402


class OwnedDatabaseTests(unittest.TestCase):
    def test_only_marked_owned_database_is_hashed(self):
        parent = ROOT / "work" / "smoke"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            harness = Harness("quick")
            harness.run_dir = Path(directory).resolve()
            harness.env = smoke_environment(harness.run_dir, "quick", {})
            database = harness.run_dir / "evennia-smoke.sqlite3"
            database.write_bytes(b"owned fixture")
            with patch("smoke_harness.fingerprint", return_value={"size": 13}) as observe:
                with self.assertRaises(RuntimeError):
                    harness.owned_database_fingerprint()
                observe.assert_not_called()
                (harness.run_dir / ".primal-smoke").touch()
                self.assertEqual(harness.owned_database_fingerprint(), {"size": 13})
                observe.assert_called_once_with(database)
                harness.env["PRIMAL_DB_NAME"] = "forbidden"
                observe.reset_mock()
                with self.assertRaises(RuntimeError):
                    harness.owned_database_fingerprint()
                observe.assert_not_called()

    def test_database_environment_does_not_leak_to_owned_run(self):
        with patch.dict(os.environ, PRIMAL_DB_NAME="forbidden", PRIMAL_SMOKE_RUN_DIR="other"):
            env = smoke_environment(Path("owned"), "full", {})
        self.assertNotIn("PRIMAL_DB_NAME", env)
        self.assertEqual(env["PRIMAL_SMOKE_RUN_DIR"], "owned")
        self.assertEqual(env["DJANGO_SETTINGS_MODULE"], "server.conf.settings_smoke")


class ActionCleanupTests(unittest.TestCase):
    def run_main(self, harness, *, scenario_error=None):
        harness.owned_database_fingerprint.return_value = {"size": 1}
        with (patch.object(action_e2e, "Harness", return_value=harness),
              patch.object(action_e2e, "scenario", new=Mock(return_value="scenario")),
              patch.object(action_e2e.asyncio, "run", side_effect=scenario_error),
              patch("builtins.print")):
            action_e2e.main()

    def test_success_requires_normal_shutdown_before_discard(self):
        harness = Mock()
        harness.owned_database_fingerprint.return_value = {"size": 1}
        self.run_main(harness)
        calls = [call[0] for call in harness.mock_calls]
        self.assertLess(calls.index("graceful_stop"), calls.index("stop"))
        self.assertLess(calls.index("stop"), calls.index("discard"))
        harness.graceful_stop.assert_called_once_with()
        harness.stop.assert_called_once_with()
        harness.discard.assert_called_once_with()

    def test_failed_normal_shutdown_still_stops_and_preserves_fixture(self):
        harness = Mock()
        original = RuntimeError("normal shutdown failed")
        harness.graceful_stop.side_effect = original
        with self.assertRaises(RuntimeError) as raised:
            self.run_main(harness)
        self.assertIs(raised.exception, original)
        harness.stop.assert_called_once_with()
        harness.discard.assert_not_called()

    def test_failed_scenario_uses_existing_cleanup_and_preserves_original_failure(self):
        harness = Mock()
        original = RuntimeError("scenario failed")
        with self.assertRaises(RuntimeError) as raised:
            self.run_main(harness, scenario_error=original)
        self.assertIs(raised.exception, original)
        harness.graceful_stop.assert_not_called()
        harness.stop.assert_called_once_with()
        harness.discard.assert_not_called()
