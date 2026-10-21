"""시나리오마다 기존 Harness를 재사용하는 Chromium 통합/RELEASE 진입점."""

import argparse
import asyncio
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from time import monotonic

E2E = tuple(f"E2E-{number:02}" for number in range(1, 15))
SCENARIOS = (*E2E, "TIMING-DOOR", "TIMING-PARTY")


async def restore_restart(harness):
    """소유 SQLite만 backup API로 보관하고, 정상 정지 후 새 파일로 복원한다."""
    run = harness.run_dir.resolve()
    database = run/'evennia-smoke.sqlite3'
    from smoke_harness import ROOT, fingerprint
    if (run.parent != (ROOT/'work/smoke').resolve() or not (run/'.primal-smoke').is_file()
            or database.is_symlink() or database.resolve().parent != run
            or harness.env.get('PRIMAL_SMOKE_RUN_DIR') != str(run)
            or harness.env.get('DJANGO_SETTINGS_MODULE') != 'server.conf.settings_smoke'
            or any(key.startswith('PRIMAL_DB_') for key in harness.env)):
        raise RuntimeError('백업/복원 소유 경로 또는 격리 설정 불일치')
    backup, restored = run/'persistence-backup.sqlite3', run/'persistence-restored.sqlite3'
    stopped = run/'persistence-stopped.sqlite3'
    if any(path.exists() or path.is_symlink() or path.resolve().parent != run
           for path in (backup, restored, stopped)):
        raise RuntimeError('기존 백업/복원 파일을 덮어쓸 수 없습니다.')
    # SQLite connect가 기존 파일을 열지 않도록 경로를 먼저 배타 생성한다.
    with backup.open('xb'):
        pass
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise RuntimeError('격리 백업 무결성 실패')
    harness.restarting = True
    try:
        await asyncio.to_thread(harness.graceful_stop)
        if any(process.poll() is None for _, process in harness.processes):
            raise RuntimeError('소유 프로세스 정상 종료 확인 전 복원 금지')
        harness.processes.clear()
        harness.handles.clear()
        if any(Path(str(database)+suffix).exists() for suffix in ('-wal', '-journal')):
            raise RuntimeError('정상 정지 후 활성 SQLite journal이 남았습니다.')
        with backup.open('rb') as source, restored.open('xb') as target:
            shutil.copyfileobj(source, target)
        if fingerprint(backup)['sha256'] != fingerprint(restored)['sha256']:
            raise RuntimeError('격리 복원 파일 fingerprint 불일치')
        with closing(sqlite3.connect(restored.as_uri()+'?mode=ro', uri=True)) as target:
            if target.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise RuntimeError('격리 복원 무결성 실패')
        # 삭제 대신 원본 정지 DB를 같은 소유 Run에 보존한다.
        with database.open('rb') as source, stopped.open('xb') as target:
            shutil.copyfileobj(source, target)
        restored.replace(database)
        harness.start()
        await harness.ready()
        return {'ready': True, 'boundary': 'restore-restart', 'backup_integrity': 'ok',
                'restore_integrity': 'ok', 'restored_sha256': fingerprint(backup)['sha256']}
    finally:
        harness.restarting = False


async def wait_browser(process, harness):
    """허용된 정상 restart만 실행한다. 게임 상태 변경 RPC는 제공하지 않는다."""
    control = harness.run_dir/'integration-control'
    control.mkdir()
    waiter = asyncio.create_task(asyncio.to_thread(process.wait, 800))
    try:
        while not waiter.done():
            request = control/'request.json'
            if request.exists():
                payload = json.loads(request.read_text(encoding='utf-8'))
                if payload in ({'operation': 'party-before'}, {'operation': 'party-at'}) and harness.env['PRIMAL_INTEGRATION_SCENARIO'] == 'E2E-11':
                    # 실제 서버 Lifecycle이 시각 인자를 가진 같은 서비스를 실행한다.
                    # 이 부모/Probe는 DB 또는 세션을 변경하지 않는다.
                    await asyncio.sleep(0.05)
                    continue
                if payload not in ({'operation': 'restart'}, {'operation': 'restore-restart'}) or harness.env['PRIMAL_INTEGRATION_SCENARIO'] != 'E2E-12':
                    raise RuntimeError('허용되지 않은 격리 제어')
                request.unlink()
                if payload['operation'] == 'restore-restart':
                    response = await restore_restart(harness)
                else:
                    await harness.restart()
                    response = {'ready': True}
                (control/'response.json').write_text(json.dumps(response), encoding='utf-8')
            await asyncio.wait({waiter}, timeout=0.05)
        await waiter
    finally:
        if not waiter.done():
            await asyncio.to_thread(process.stop)
        await asyncio.gather(waiter, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description='Issue #50 실제 격리 Chromium')
    parser.add_argument('--scenario', choices=SCENARIOS, action='append')
    parser.add_argument('--profile', choices=('pr', 'timing', 'persistence'), default='pr')
    args = parser.parse_args()
    selected = args.scenario or {'pr': E2E, 'timing': SCENARIOS[-2:], 'persistence': ('E2E-12', 'E2E-13')}[args.profile]
    from browser_e2e import main as run
    started = monotonic()
    for scenario in selected:
        run(scenario)
    print(json.dumps({'profile': args.profile, 'tests': len(selected), 'seconds': round(monotonic()-started, 3)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
