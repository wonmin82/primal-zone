"""Phase 7B: 소유한 격리 SQLite corpus/브라우저 서버만 실행한다."""

import argparse
import asyncio
import json
import secrets
import shutil
import subprocess
import sys
from time import monotonic

from smoke_harness import ROOT, Harness, fingerprint


def fixture(harness, action):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "phase7b_fixture.py"), action],
                            cwd=harness.run_dir / "game", env=harness.env, text=True,
                            encoding="utf-8", capture_output=True, timeout=120)
    (harness.run_dir / f"fixture-{action}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout.splitlines()[-1])


def command(harness, mode, success=True, accept=False):
    args = [sys.executable, "-m", "evennia", "migrate_items", "--settings", "settings_smoke", "--" + mode]
    if accept:
        args.append("--accept-warnings")
    start = monotonic()
    result = subprocess.run(args, cwd=harness.run_dir / "game", env=harness.env,
                            capture_output=True, text=True, encoding="utf-8", timeout=120)
    suffix = "-accepted" if accept else ""
    ordinal = len(list(harness.run_dir.glob("migration-*.log"))) + 1
    log = harness.run_dir / f"migration-{ordinal:02d}-{mode}{suffix}.log"
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    assert (result.returncode == 0) == success, (mode, result.returncode, str(log))
    print(json.dumps({"mode": mode, "accepted": accept, "exit": result.returncode,
                      "seconds": round(monotonic() - start, 3), "log": str(log)}, ensure_ascii=False), flush=True)
    return result


def new_harness():
    harness = Harness("full")
    harness.credentials = [(name, secrets.token_urlsafe(24)) for name in ("검증가", "검증나", "검증다", "검증라")]
    harness.prepare()
    return harness


def archive_evidence(harness):
    """재생성 가능한 성공 DB 대신 비밀이 없는 관찰 결과만 보존한다."""
    destination = ROOT / "work" / "phase7b" / "evidence" / harness.run_dir.name
    destination.mkdir(parents=True, exist_ok=True)
    for pattern in ("*-evidence.json", "corpus-*.json", "migration-*.log", "browser-*.txt", "browser-*.png"):
        for path in harness.run_dir.glob(pattern):
            shutil.copy2(path, destination / path.name)
    return destination


async def serve(harness, reports=False):
    fixture(harness, "live")
    if reports:
        fixture(harness, "reports")
    harness.start()
    await harness.ready()
    private = harness.run_dir / "fixture-login.json"
    private.write_text(json.dumps(harness.credentials, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ready": True, "run": str(harness.run_dir), "http": harness.ports["http"],
                      "ws": harness.ports["ws"], "credentials_file": str(private)}, ensure_ascii=False), flush=True)
    # stdin 종료나 interrupt도 finally에서 owned process만 종료한다.
    await asyncio.to_thread(sys.stdin.readline)


def corpus(harness, kind):
    before = fixture(harness, kind)
    (harness.run_dir / "corpus-before.json").write_text(json.dumps(before, ensure_ascii=False, default=str), encoding="utf-8")
    secret = harness.run_dir / "game/server/conf/secret_settings.py"
    with secret.open("a", encoding="utf-8") as output:
        output.write("ITEM_MAINTENANCE = True\nITEM_MIGRATION_AUDIT = True\n")
    db = harness.run_dir / "evennia-smoke.sqlite3"
    immutable = fingerprint(db)
    command(harness, "dry-run", kind != "invalid")
    assert fingerprint(db) == immutable, "dry-run DB 변경"
    command(harness, "cutover", False)
    assert fixture(harness, "inspect") == before, "apply 전 cutover 실패가 상태를 변경"
    command(harness, "apply", kind != "invalid")
    applied = fixture(harness, "inspect")
    assert applied["runtime"][0]["version"] == 0, "apply가 cutover를 수행"
    read_only = fingerprint(db)
    command(harness, "verify", kind != "invalid")
    assert fingerprint(db) == read_only, "verify DB 변경"
    assert fixture(harness, "inspect") == applied, "verify 변경"
    command(harness, "apply", kind != "invalid")
    assert fixture(harness, "inspect") == applied, "apply 재실행 중복/sequence 변경"
    if kind != "invalid":
        fixture(harness, "corrupt")
        corrupted = fingerprint(db)
        command(harness, "verify", False)
        assert fingerprint(db) == corrupted, "실패 verify DB 변경"
        command(harness, "cutover", False)
        fixture(harness, "restore")
        command(harness, "verify")
    command(harness, "cutover", kind == "valid")
    if kind == "warning":
        assert fixture(harness, "inspect") == applied, "미승인 warning cutover 변경"
        command(harness, "cutover", accept=True)
    final = fixture(harness, "inspect")
    (harness.run_dir / "corpus-after.json").write_text(json.dumps(final, ensure_ascii=False, default=str), encoding="utf-8")
    preserved = before["players"]["보존검증"]["native"]["items"]
    preserved_ids = {row["id"] for row in preserved}
    assert [row for row in final["players"]["보존검증"]["native"]["items"]
            if row["id"] in preserved_ids] == preserved, "기존 native Entity 변경"
    assert final["runtime"][0]["version"] == (0 if kind == "invalid" else 1)
    if kind == "invalid":
        assert applied["ledger"] and len(applied["ledger"]) == len(applied["sources"]) - 1
        failed = applied["players"]["검증라"]
        assert failed["native"]["items"] == []
        assert failed["profile"] == before["players"]["검증라"]["profile"]
        fixture(harness, "repair-invalid")
        command(harness, "apply")
        retried = fixture(harness, "inspect")
        for key, row in applied["sources"].items():
            if row["key"] != "검증라":
                assert retried["sources"][key]["native"] == row["native"], "성공 source 재생성"
        command(harness, "verify")
        command(harness, "cutover")
        final = fixture(harness, "inspect")
    print(json.dumps({"corpus": kind, "PASS": True, "sources": len(final["sources"]),
                      "ledger": len(final["ledger"]), "sequence": final["sequence"],
                      "runtime": final["runtime"], "run": str(harness.run_dir)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("serve", "serve-reports", "multiplayer", "loot", "items", "valid", "warning", "invalid"))
    parser.add_argument("--keep-fixture", action="store_true", help="수동 조사 중 성공 fixture를 유지한다.")
    args = parser.parse_args()
    original = fingerprint(ROOT / "game/server/evennia.db3")
    harness = new_harness()
    completed = False
    try:
        if args.mode in ("serve", "serve-reports"):
            asyncio.run(serve(harness, args.mode == "serve-reports"))
        elif args.mode == "multiplayer":
            from phase7b_multiplayer import run

            asyncio.run(run(harness))
        elif args.mode == "loot":
            from phase7b_loot import run

            asyncio.run(run(harness))
        elif args.mode == "items":
            from phase7b_items import run

            asyncio.run(run(harness))
        else:
            corpus(harness, args.mode)
            if args.mode == "valid":
                from phase7b_postcutover import run

                asyncio.run(run(harness))
        completed = True
    finally:
        harness.stop()
        assert original == fingerprint(ROOT / "game/server/evennia.db3"), "개발 DB 변경"
        print("owned process 종료 / 개발 DB 불변", flush=True)
        if completed and not args.keep_fixture:
            evidence = archive_evidence(harness)
            harness.discard()
            print("성공 fixture cleanup / 증거: " + str(evidence), flush=True)
