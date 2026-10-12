"""workflow_dispatch의 최종 main SHA만 RELEASE 근거로 허용한다."""

import os
import re
import subprocess


def validate(environment, head):
    expected = environment.get('PRIMAL_RELEASE_SHA', '')
    if (environment.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or environment.get('GITHUB_REF') != 'refs/heads/main'
            or not re.fullmatch('[0-9a-f]{40}', expected)
            or expected != environment.get('GITHUB_SHA') or expected != head):
        raise RuntimeError('RELEASE는 명시한 실제 main HEAD의 workflow_dispatch에서만 허용합니다.')
    return expected


if __name__ == '__main__':
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    print('RELEASE SHA:', validate(os.environ, head))
