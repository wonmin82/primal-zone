"""줄임말 v1.14의 격리 서버/WebSocket 입력·재시작 회귀. 플레이 DB는 사용하지 않는다."""

import asyncio
import json
from time import monotonic

from smoke import Client, travel_to
from smoke_harness import ROOT, Harness, fingerprint


async def scenario(harness, report):
    players = [Client(name, password, harness.ws_url) for name, password in harness.credentials[:2]]
    first, second = players

    async def command(player, raw, expected):
        while not player.messages.empty():
            player.messages.get_nowait()
        await player.expect_prompt(raw)
        messages = []
        while not player.messages.empty():
            messages.append(str(player.messages.get_nowait()))
        output = "\n".join(messages)
        if expected not in output:
            raise AssertionError((raw, expected, output))
        report.append({"player": player.name, "command": raw, "expected": expected, "result": "PASS"})
        if raw.endswith(" 도움말"):
            report[-1]["output"] = output

    try:
        await asyncio.gather(*(player.open() for player in players))
        for name in ("해", "줄임말", "해지", "단축어"):
            await command(first, name + " 도움말", f"[{name}]")
            output = report[-1]["output"]
            titles = ("사용법", "예시", "실행 규칙", "제한", "관련 도움말")
            assert [line for line in output.splitlines() if line in titles] == list(titles)
            assert "\n\n\n" not in output
        for name in ("공격", "보기", "상태"):
            await command(first, name + " 도움말", "사용법:")
        await command(first, "증폭 " + "$*" * 1000 + " 줄임말", "추가했습니다")
        before = first.state["zone"]
        await command(first, "x" * 2000 + " 증폭", "허용 크기")
        assert first.state["zone"] == before
        await command(first, "장확 장비 줄임말", "추가했습니다")
        await command(first, "장확 줄임말", "장확 = 장비")
        await command(second, "장확 줄임말", "찾을 수 없습니다")
        await command(first, "동작 남 $1 줄임말", "추가했습니다")
        before = first.state["zone"]
        await command(first, "보기 동작", "중앙 로비")
        assert first.state["zone"] == before
        await command(first, "실행 $* 줄임말", "추가했습니다")
        await command(first, "상태 실행", "상태")
        await command(first, "상태, 장비 해 실행", "새 묶음")
        await command(first, "인사 안녕, 반가워 말 줄임말", "추가했습니다")
        await command(first, "인사, 상태 해", "안녕, 반가워")
        await command(first, "장확 해지, 장확 해", "장비")  # 삭제 이후에도 최초 스냅샷 사용
        await command(first, "장확 줄임말", "찾을 수 없습니다")
        await command(first, "순환 귀환, 순환 해 줄임말", "추가했습니다")
        await command(first, "순환", "순환 참조")
        assert first.state["zone"] == "support_roof"  # 이미 실행된 귀환은 유지
        await travel_to(first, "hq_concourse")
        await command(first, "계단, 위, 나가기, 상태 해", "상태")
        assert first.state["zone"] == "support_2f_c"
        before = first.state["zone"]
        await command(first, "계단 올라, 상태 해", "대상 뒤에 행동")
        assert first.state["zone"] == before
        await command(first, "모두 삭제 줄임말", "계속하려면")
        await command(first, "모두 삭제 확인 줄임말 실행", "각각 직접 입력")
        await command(first, "모두 삭제 확인 줄임말", "모두 삭제했습니다")
        await command(first, "줄임말", "전체 등록: 0개")
        await command(first, "보존 장비 줄임말", "추가했습니다")
        await command(first, "모두 삭제 줄임말", "계속하려면")
        await asyncio.gather(*(player.close() for player in players))
        await harness.restart()
        await first.open()
        await command(first, "모두 삭제 확인 줄임말", "먼저")  # 재시작은 pending을 보존하지 않음
        await command(first, "보존 줄임말", "보존 = 장비")
        await command(first, "보존", "장비")
        await first.close()
        await first.open()
        await command(first, "보존 줄임말", "보존 = 장비")
    finally:
        await asyncio.gather(*(player.close() for player in players))


async def live(harness, report):
    await harness.ready()
    await harness.supervise(scenario(harness, report))


def main():
    harness = Harness("quick")
    started, report = monotonic(), []
    before = fingerprint(ROOT / "game/server/evennia.db3")
    success = False
    evidence = ROOT / "work/shortcut-v114"
    evidence.mkdir(parents=True, exist_ok=True)
    try:
        harness.prepare()
        print(f"격리 줄임말 smoke: {harness.run_dir}", flush=True)
        harness.start()
        asyncio.run(live(harness, report))
        success = True
    finally:
        harness.stop()
        after = fingerprint(ROOT / "game/server/evennia.db3")
        if before != after:
            raise RuntimeError("플레이 DB fingerprint가 변경되었습니다.")
        result = {"success": success, "seconds": round(monotonic() - started, 3),
                  "steps": report, "development_db_unchanged": True}
        (evidence / "live-shortcuts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if success:
            harness.discard()
            print(json.dumps(result, ensure_ascii=False), flush=True)
        else:
            print(f"실패 DB/로그 보존: {harness.run_dir}", flush=True)


if __name__ == "__main__":
    main()
