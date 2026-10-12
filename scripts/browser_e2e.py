"""실제 Chromium QA: 기존 Harness가 소유한 격리 서버만 준비하고 정리한다."""

import asyncio
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from time import monotonic

from browser_processes import OwnedBrowser
from smoke_harness import ROOT, Harness, fingerprint


def sanitize_artifacts(directory, passwords):
    """Trace/영상/DB는 수집하지 않고 텍스트 증거의 실제 fixture 비밀번호도 제거한다."""
    for path in directory.rglob('*'):
        if path.is_file() and path.suffix in ('.json', '.html', '.txt', '.log', '.md'):
            content = path.read_text(encoding='utf-8', errors='replace')
            for password in passwords:
                content = content.replace(password, '[REDACTED]')
            path.write_text(content, encoding='utf-8')


def stop_browser(process):
    if process is not None:
        process.stop()


async def browser(harness, results):
    await harness.ready()
    credentials = harness.run_dir/'browser-credentials.json'
    if (harness.run_dir.resolve().parent != (ROOT/'work/smoke').resolve()
            or not (harness.run_dir/'.primal-smoke').is_file()):
        raise RuntimeError('브라우저 자격 증명 경로가 소유 격리 디렉터리가 아님')
    process = None
    harness.browser_processes_stopped = False
    original = None
    try:
        with credentials.open('x', encoding='utf-8') as private:
            os.chmod(credentials, 0o600)
            json.dump(harness.credentials, private)
        env = {**harness.env, 'PRIMAL_BROWSER_URL': f"http://127.0.0.1:{harness.ports['http']}/webclient/",
               'PRIMAL_BROWSER_WS': harness.ws_url, 'PRIMAL_BROWSER_RESULTS': str(results),
               'PRIMAL_BROWSER_DB': str(harness.run_dir / 'evennia-smoke.sqlite3'),
               'PRIMAL_BROWSER_PYTHON': sys.executable,
               'PRIMAL_BROWSER_CREDENTIALS': str(credentials),
               'PLAYWRIGHT_NO_COPY_PROMPT': '1'}
        # subprocess 출력도 자유 입력을 포함할 수 있어 업로드 영역에 생성하지 않는다.
        with (harness.run_dir/'browser-private.log').open('w', encoding='utf-8') as log:
            process = OwnedBrowser(['node', str(ROOT/'node_modules/playwright/cli.js'), 'test',
                                        '--config', str(ROOT/'playwright.config.cjs')],
                                   cwd=ROOT, env=env, stdout=log,
                                   control=harness.run_dir/'browser-process-exit.json')
            await asyncio.to_thread(process.wait, 300)
            if process.returncode:
                raise RuntimeError(f'Playwright 종료 코드 {process.returncode}; {results}')
            report = json.loads((results/'results.json').read_text(encoding='utf-8'))
            if report.get('status') != 'passed' or report.get('errors') != 0:
                raise RuntimeError('브라우저 보고서/증거 정리 실패')
    except BaseException as failure:
        original = failure
        raise
    finally:
        failures = []
        try:
            stop_browser(process)
            harness.browser_processes_stopped = process is None or process.stopped is True
        except BaseException as failure:
            failures.append(failure)
        try:
            credentials.unlink(missing_ok=True)
        except BaseException as failure:
            failures.append(failure)
        try:
            # 중단/강제 종료로 reporter가 실행되지 않았어도 자동 오류 context는 보존하지 않는다.
            for context in results.rglob('error-context.md'):
                if not context.resolve().is_relative_to(results.resolve()):
                    raise RuntimeError('오류 context 경로가 소유 결과 디렉터리 밖임')
                context.unlink()
        except BaseException as failure:
            failures.append(failure)
        if failures:
            raise BaseExceptionGroup('브라우저 실행 및 정리 실패', ([original] if original else []) + failures) from original


def public_report(report):
    """독립적인 업로드 경계에서도 자유 문자열과 알 수 없는 필드를 버린다."""
    def number(value):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 1e10 else 0

    def observation(value):
        action = value.get('lastAction')
        return {'player': value.get('player') if value.get('player') in ('A', 'B', 'C') else 'unknown',
                'path': value.get('path') if value.get('path') in ('/webclient/', '/favicon.ico', '/', '/other', '/invalid') else '/other',
                'lastAction': {'kind': 'command', 'category': 'chat' if action.get('category') == 'chat' else 'command',
                               'length': number(action.get('length'))} if isinstance(action, dict) else None,
                'hasState': value.get('hasState') is True, 'contextClosed': value.get('contextClosed') is True, 'revision': number(value.get('revision')),
                'sockets': [{'closed': s.get('closed') is True, 'frames': number(s.get('frames'))} for s in value.get('sockets', [])],
                'ownedSessions': number(value.get('ownedSessions')), 'detached': value.get('detached') is True,
                'errors': ['browser-error' for _ in value.get('errors', [])],
                'warnings': ['favicon-404' for _ in value.get('warnings', [])]}

    tests = []
    for test in report.get('tests', []):
        entry = {'id': test.get('id') if re.fullmatch(r'TEST-[A-Z0-9-]+', str(test.get('id'))) else 'unknown',
                 'status': test.get('status') if test.get('status') in ('passed', 'failed', 'timedOut', 'skipped', 'interrupted') else 'failed',
                 'seconds': number(test.get('seconds')), 'errors': number(test.get('errors')),
                 'observations': [observation(value) for value in test.get('observations', [])],
                 'evidenceCleanupFailed': test.get('evidenceCleanupFailed') is True,
                 'failureStages': [stage for stage in test.get('failureStages', []) if stage in (
                     'context-close-failed', 'websocket-close: timeout', 'puppet-detach: timeout',
                     'puppet-detach: probe-failed', 'puppet-login: timeout', 'puppet-login: probe-failed',
                     'observations: attach-failed', 'test-failure', 'evidence-cleanup-failed')]}
        if re.fullmatch(r'\d+(\.\d+){3}', str(test.get('chromium'))):
            entry['chromium'] = test['chromium']
        tests.append(entry)
    return {'status': report.get('status') if report.get('status') in ('passed', 'failed', 'timedout', 'interrupted') else 'failed',
            'errors': number(report.get('errors')), 'tests': tests}


def publish_evidence(results, evidence, metadata, run_dir):
    """텍스트 원문·DB·추가 이미지 대신 안전 스키마와 승인된 마스킹 이미지만 내보낸다."""
    report_path = results/'results.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    content = json.dumps(public_report(report), ensure_ascii=False, indent=2)
    evidence.mkdir(parents=True, exist_ok=False)
    (evidence/'results.json').write_text(content, encoding='utf-8')
    (evidence/'run.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    (evidence/'report.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>Phase 50-A 검증</title><h1>Phase 50-A 실제 브라우저 검증</h1><pre>'+html.escape(content)+'</pre></html>', encoding='utf-8')
    # 원본 서버 로그는 실패 시 로컬 격리 디렉터리에만 남긴다. 줄 수만 Artifact로 보낸다.
    for name in ('setup', 'server', 'portal', 'browser-private'):
        source = run_dir/(name+'.log') if run_dir else None
        lines = len(source.read_text(encoding='utf-8', errors='replace').splitlines()) if source and source.exists() else 0
        (evidence/('browser.log' if name == 'browser-private' else name+'.log')).write_text(json.dumps({'present': bool(source and source.exists()), 'lines': lines, 'raw_content_collected': False}), encoding='utf-8')
    screenshots = (results/'screenshots').resolve()
    for image in report.get('screenshots', []):
        name = image.get('name')
        if name not in ('safe-viewport-1366.png', 'safe-viewport-390.png'):
            continue
        candidate = screenshots/image['source']
        source = candidate.resolve()
        # Playwright.attach()가 마스킹 파일을 복사하며 40자리 digest를 덧붙인다.
        allowed_name = re.fullmatch(re.escape(Path(name).stem)+r'(-[a-f0-9]{40})?\.png', source.name)
        if (source.is_relative_to(screenshots) and not candidate.is_symlink()
                and source.is_file() and allowed_name
                and source.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')):
            shutil.copyfile(source, evidence/name)


def main():
    harness = Harness('full')  # 브라우저 QA는 production 타이머를 유지한다.
    parent = ROOT/'work/browser-e2e'
    parent.mkdir(parents=True, exist_ok=True)
    results = Path(tempfile.mkdtemp(prefix='run-', dir=parent)).resolve()
    started = monotonic()
    before = fingerprint(ROOT/'game/server/evennia.db3')
    success = False
    error = None
    previous = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        harness.prepare()
        harness.start()
        asyncio.run(harness.supervise(browser(harness, results)))
        success = True
    except BaseException as failure:
        error = failure
    finally:
        try:
            harness.stop()
        except BaseException as failure:
            error = BaseExceptionGroup('실행 및 서버 정리 실패', [error, failure]) if error else failure
            success = False
        finally:
            signal.signal(signal.SIGTERM, previous)
            sanitize_artifacts(results, [password for _, password in harness.credentials])
        after = fingerprint(ROOT/'game/server/evennia.db3')
        if before != after:
            raise RuntimeError('플레이 DB hash/mtime/size 변경: 격리 실패')
        metadata = {'success': success, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    'seconds': round(monotonic()-started, 3), 'play_db_unchanged': True,
                    'processes_stopped': all(p.poll() is not None for _, p in harness.processes),
                    'browser_processes_stopped': getattr(harness, 'browser_processes_stopped', False),
                    'credentials_removed': not (harness.run_dir/'browser-credentials.json').exists() if harness.run_dir else True,
                    'mode': 'full', 'python': sys.version.split()[0], 'platform': sys.platform}
        if not all(metadata[key] for key in ('credentials_removed', 'processes_stopped', 'browser_processes_stopped')):
            success = metadata['success'] = False
            failure = RuntimeError('자격 증명 또는 소유 프로세스 정리 미완료')
            error = BaseExceptionGroup('실행 및 정리 실패', [error, failure]) if error else failure
        (results/'run.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        evidence = ROOT/'work/browser-evidence'/results.name
        publish_evidence(results, evidence, metadata, harness.run_dir)
        if success:
            harness.discard()
        print(json.dumps({'results': str(results), **metadata}, ensure_ascii=False), flush=True)
        if error:
            raise error


if __name__ == '__main__':
    main()
