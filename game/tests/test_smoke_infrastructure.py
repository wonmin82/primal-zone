"""실제 일반 설정에서의 타이머와 fixture DB 접근 차단."""

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from django.conf import settings
from world import multiplayer
from world.timing import PRODUCTION_TIMING, configured_timings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.smoke_setup import setup  # noqa: E402


class SmokeInfrastructureTests(TestCase):
    def test_normal_test_settings_keep_production_gameplay_timers(self):
        self.assertEqual(configured_timings(settings), PRODUCTION_TIMING)
        self.assertEqual({key: getattr(multiplayer, key) for key in PRODUCTION_TIMING}, PRODUCTION_TIMING)
        self.assertFalse(getattr(settings, "PRIMAL_SMOKE", False))

    def test_fixture_refuses_normal_settings_before_django_setup_or_migrate(self):
        with patch("django.setup") as initialize, patch("django.core.management.call_command") as command:
            with self.assertRaisesRegex(RuntimeError, "marker"):
                setup([])
            initialize.assert_not_called()
            command.assert_not_called()
