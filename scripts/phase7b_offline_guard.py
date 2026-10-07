"""실제 owned Portal/Server와 별도 migration CLI의 offline guard 회귀."""

import json
import subprocess
import sys
from time import monotonic

from phase7b import command, fixture
from smoke_closeout import stop_for_restart


def status(harness):
    result = subprocess.run([sys.executable, "-m", "world.item_migration.runtime_status"],
                            cwd=harness.run_dir / "game", env=harness.env, capture_output=True,
                            text=True, encoding="utf-8", timeout=30, check=True)
    return json.loads(result.stdout)


async def run(harness):
    secret = harness.run_dir / "game/server/conf/secret_settings.py"
    with secret.open("a", encoding="utf-8") as output:
        output.write("ITEM_MAINTENANCE = True\n")
    started = monotonic()
    harness.start()
    await harness.ready()
    harness.check_alive()
    before = fixture(harness, "inspect")
    evidence = {"label": "TEST / RUNNING SERVER OFFLINE GUARD", "running": {}, "rejections": {}}
    # Windows launcher와 같은 no-pid 상태에서도 실제 두 프로세스가 살아 있다.
    evidence["running"] = {name: process.poll() is None for name, process in harness.processes}
    evidence["pid_files"] = [str(path.name) for path in (harness.run_dir / "game/server").glob("*.pid")]
    assert evidence["running"] == {"portal": True, "server": True}
    evidence["running_status"] = status(harness)
    assert evidence["running_status"] == {"portal": True, "server": True, "proof": "amp"}
    for mode in ("apply", "cutover"):
        result = command(harness, mode, success=False)
        assert "Evennia offline 확인 실패" in result.stderr and "실행 중" in result.stderr, result.stderr
        assert fixture(harness, "inspect") == before, "running 거절이 item/ledger/sequence/runtime/legacy source를 변경"
        evidence["rejections"][mode] = {"exit": result.returncode, "running_guard": True, "state_unchanged": True}
    stop_for_restart(harness)
    evidence["stopped"] = {name: process.poll() is not None for name, process in harness.processes}
    assert evidence["stopped"] == {"portal": True, "server": True}
    evidence["stopped_status"] = status(harness)
    assert evidence["stopped_status"] == {"portal": False, "server": False, "proof": "connection-refused"}, evidence["stopped_status"]
    stopped = fixture(harness, "inspect")
    assert fixture(harness, "offline-check") == {"offline": True}, "정상 정지 후 guard 거절"
    assert fixture(harness, "inspect") == stopped, "offline guard가 DB를 변경"
    evidence.update(offline_pass=True, seconds=round(monotonic() - started, 3))
    (harness.run_dir / "offline-guard-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False), flush=True)
