"""실제 Chromium QA: 기존 Harness가 소유한 격리 서버만 준비하고 정리한다."""

import asyncio
import html
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from time import monotonic

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
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        # 종료 대상은 이 실행기에서 생성한 Node와 그 자식뿐이다.
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=True,
                           stdout=subprocess.DEVNULL)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=15)


async def browser(harness, results):
    await harness.ready()
    credentials = harness.run_dir/'browser-credentials.json'
    with credentials.open('w', encoding='utf-8') as private:
        os.chmod(credentials, 0o600)
        json.dump(harness.credentials, private)
    env = {**harness.env, 'PRIMAL_BROWSER_URL': f"http://127.0.0.1:{harness.ports['http']}/webclient/",
           'PRIMAL_BROWSER_WS': harness.ws_url, 'PRIMAL_BROWSER_RESULTS': str(results),
           'PRIMAL_BROWSER_DB': str(harness.run_dir / 'evennia-smoke.sqlite3'),
           'PRIMAL_BROWSER_PYTHON': sys.executable,
           'PRIMAL_BROWSER_CREDENTIALS': str(credentials)}
    flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {
        'start_new_session': True}
    with (results/'browser.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(['node', str(ROOT/'node_modules/playwright/cli.js'), 'test',
                                    '--config', str(ROOT/'playwright.config.cjs')],
                                   cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, text=True, **flags)
        try:
            await asyncio.to_thread(process.wait, 300)
            if process.returncode:
                raise RuntimeError(f'Playwright 종료 코드 {process.returncode}; {results}')
        finally:
            stop_browser(process)
            credentials.unlink(missing_ok=True)


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
        finally:
            signal.signal(signal.SIGTERM, previous)
            if harness.run_dir:
                for name in ('setup', 'server', 'portal'):
                    source = harness.run_dir / (name+'.log')
                    if source.exists():
                        (results/(name+'.log')).write_text(source.read_text(encoding='utf-8', errors='replace'), encoding='utf-8')
            sanitize_artifacts(results, [password for _, password in harness.credentials])
        after = fingerprint(ROOT/'game/server/evennia.db3')
        if before != after:
            raise RuntimeError('플레이 DB hash/mtime/size 변경: 격리 실패')
        metadata = {'success': success, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    'seconds': round(monotonic()-started, 3), 'play_db_unchanged': True,
                    'processes_stopped': all(p.poll() is not None for _, p in harness.processes),
                    'mode': 'full', 'python': sys.version.split()[0], 'platform': sys.platform}
        (results/'run.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        report = (results/'results.json').read_text(encoding='utf-8') if (results/'results.json').exists() else '{}'
        (results/'report.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>Phase 50-A 검증</title><h1>Phase 50-A 실제 브라우저 검증</h1><pre>'+html.escape(report)+'</pre></html>', encoding='utf-8')
        # 업로드 대상은 cleanup과 sanitization을 모두 마친 복사본뿐이다.
        evidence = ROOT/'work/browser-evidence'/results.name
        shutil.copytree(results, evidence)
        if success:
            harness.discard()
        print(json.dumps({'results': str(results), **metadata}, ensure_ascii=False), flush=True)
        if error:
            raise error


if __name__ == '__main__':
    main()
