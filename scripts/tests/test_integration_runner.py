"""게임 상태 쓰기 없이 격리 제어의 소유권·정리·매트릭스 경계를 검사한다."""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from integration_e2e import SCENARIOS, wait_browser  # noqa: E402
from integration_probe import snapshot  # noqa: E402
from issue50_contracts import records  # noqa: E402
from release_guard import validate  # noqa: E402


class IntegrationContractManifestTests(unittest.TestCase):
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
                with self.assertRaisesRegex(RuntimeError, '불일치'):
                    snapshot()

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
