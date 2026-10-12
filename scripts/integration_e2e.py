"""시나리오마다 기존 Harness를 재사용하는 Chromium 통합/RELEASE 진입점."""

import argparse
import asyncio
import json
from time import monotonic

E2E = tuple(f"E2E-{number:02}" for number in range(1, 15))
SCENARIOS = (*E2E, "TIMING-DOOR", "TIMING-PARTY")


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
                if payload != {'operation': 'restart'} or harness.env['PRIMAL_INTEGRATION_SCENARIO'] != 'E2E-12':
                    raise RuntimeError('허용되지 않은 격리 제어')
                request.unlink()
                await harness.restart()
                (control/'response.json').write_text('{"ready":true}', encoding='utf-8')
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
