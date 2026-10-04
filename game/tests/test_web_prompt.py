"""Node 표준 모듈로 실제 Web client의 DOM/WS 입출력 경계를 검증한다."""

import shutil
import subprocess
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase


@skipUnless(shutil.which("node"), "Web client 회귀 실행에는 Node.js가 필요합니다.")
class WebPromptInputTests(SimpleTestCase):
    def test_actual_client_prompt_input_paths(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [shutil.which("node"), "--test", "scripts/tests/test_web_prompt.cjs"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
