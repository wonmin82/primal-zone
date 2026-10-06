"""격리형 Quick Live Smoke / production-timing Full Gameplay E2E."""

import argparse
import asyncio
import json
import sys
import traceback
from dataclasses import dataclass
from time import monotonic

from smoke_harness import ROOT, Harness, fingerprint
from websockets.asyncio.client import connect

sys.path.insert(0, str(ROOT / "game"))
from server.conf.smoke_support import smoke_timings  # noqa: E402
from world.recovery import RECOVERY_INTERVAL  # noqa: E402

AUTH_TIMEOUT = 15
STATE_TIMEOUT = 10
TIMING_TOLERANCE = 1.5


@dataclass(frozen=True)
class Timeouts:
    combat: float
    lifecycle: float

    @classmethod
    def for_mode(cls, mode):
        timings = smoke_timings(mode)
        return cls(combat=timings["COMBAT_INTERVAL"] * 20 + STATE_TIMEOUT,
                   lifecycle=timings["LOOT_PROTECTION_SECONDS"] + STATE_TIMEOUT)


class Client:
    def __init__(self, name, password, url):
        self.name, self.password, self.url = name, password, url
        self.socket = self.reader = self.state = None
        self.revision = 0
        self.changed = asyncio.Condition()
        self.messages = asyncio.Queue()
        self.prompts = asyncio.Queue()
        self.error = None
        self.closing = False
        self.received = []
        self.connected = asyncio.Event()

    async def open(self):
        self.state, self.error, self.closing = None, None, False
        self.connected.clear()
        self.socket = await connect(self.url, subprotocols=["v1.evennia.com"],
                                    open_timeout=AUTH_TIMEOUT)
        self.reader = asyncio.create_task(self.receive())
        # WebSocket handshake와 Portal→Server session 등록 완료는 서로 다르다.
        # 실제 연결 안내를 받은 뒤 인증한다. 고정 sleep/인증 재시도는 하지 않는다.
        async with asyncio.timeout(AUTH_TIMEOUT):
            await self.connected.wait()
        if self.error:
            raise self.error
        await self.send("pz_auth", [{"mode": "login", "username": self.name,
                                    "password": self.password}])
        return await self.until(lambda state: state["name"] == self.name, AUTH_TIMEOUT)

    async def receive(self):
        try:
            async for raw in self.socket:
                kind, args, _ = json.loads(raw)
                self.received = (self.received + [kind])[-10:]
                async with self.changed:
                    if kind == "pz_auth" and not args[0]["ok"]:
                        self.error = AssertionError("fixture login 실패: " + args[0]["message"])
                    elif kind == "pz_state":
                        self.state = args[0]
                        self.revision += 1
                    elif kind == "pz_log":
                        if args[0].get("kind") == "prompt":
                            self.prompts.put_nowait(args[0])
                        self.messages.put_nowait(
                            "".join(part["text"] for part in args[0]["segments"]))
                    elif kind == "text":
                        self.messages.put_nowait(args[0])
                        self.connected.set()
                    self.changed.notify_all()
        except Exception as error:
            self.error = error
        finally:
            async with self.changed:
                if not self.closing and not self.error:
                    self.error = ConnectionError("WebSocket이 조기에 종료되었습니다.")
                self.connected.set()
                self.changed.notify_all()

    async def send(self, kind, args):
        await self.socket.send(json.dumps([kind, args, {}], ensure_ascii=False))

    async def until(self, predicate, timeout=STATE_TIMEOUT, after=-1):
        async with asyncio.timeout(timeout), self.changed:
            while not self.state or self.revision <= after or not predicate(self.state):
                if self.error:
                    raise self.error
                await self.changed.wait()
            return self.state

    async def act(self, text, predicate=lambda state: True, timeout=STATE_TIMEOUT):
        before = self.revision
        await self.send("text", [text])
        return await self.until(predicate, timeout, before)

    async def expect_text(self, command, expected):
        while not self.messages.empty():
            self.messages.get_nowait()
        await self.send("text", [command])
        async with asyncio.timeout(STATE_TIMEOUT):
            while expected not in await self.messages.get():
                pass

    async def expect_prompt(self, command):
        while not self.prompts.empty():
            self.prompts.get_nowait()
        await self.send("text", [command])
        async with asyncio.timeout(STATE_TIMEOUT):
            return await self.prompts.get()

    def summary(self):
        return {"player": self.name, "revision": self.revision,
                "received": self.received, "error": str(self.error) if self.error else None,
                "state": {key: self.state.get(key) for key in
                          ("zone", "hp", "mental", "xp", "credits", "combat_target")} if self.state else None}

    async def close(self):
        self.closing = True
        if self.socket:
            await self.socket.close()
        if self.reader:
            await self.reader


def count_item(state, item):
    return sum(entry["count"] for entry in state["inventory"] if entry["id"] == item)


async def route(player, steps):
    for command, zone in steps:
        await player.act(command, lambda state, zone=zone: state["zone"] == zone)


class Scenario:
    def __init__(self, harness, log):
        self.harness, self.log = harness, log
        self.phase = "auth"
        self.players = [Client(name, password, harness.ws_url)
                        for name, password in harness.credentials]
        self.timings = smoke_timings(harness.mode)
        self.timeouts = Timeouts.for_mode(harness.mode)

    def report(self, phase, result):
        line = f"PASS [{phase}] {result}"
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()

    def elapsed(self, name, since, expected):
        duration = monotonic() - since
        if self.harness.mode == "full":
            assert expected - TIMING_TOLERANCE <= duration <= expected + STATE_TIMEOUT, (
                name, duration, expected)
        self.report("timing", f"{name}: {duration:.3f}s (configured {expected}s)")

    async def run(self):
        first, second, outsider = self.players
        try:
            for player in self.players:
                await player.open()
                assert player.state["zone"] == "staging_room"
                assert player.state["party"] is None and player.state["combat_target"] is None
                assert player.state["max_mental"] == 40 and 10 <= player.state["mental"] <= 40
            self.report("auth", "fixture login / 출정 대기실")
            for raw in ("상태", "", "   ", "없는명령", "접속자"):
                prompt = await first.expect_prompt(raw)
                assert prompt["kind"] == "prompt"
                assert "".join(part["text"] for part in prompt["segments"]).endswith(" ] >")
            self.report("prompt", "일반/계정/실패 명령과 빈·공백 Enter의 실제 semantic prompt")
            for player in self.players:
                await route(player, (("남", "hq_concourse"), ("서", "dock")))
            await first.act("윤대장 대화", lambda state: "정비기록" in state["quest"])
            self.phase = "party"
            await first.act(second.name + " 파티초대", lambda state: state["party"] is not None)
            await second.until(lambda state: state["invitation"] is not None)
            await second.act("파티수락", lambda state: state["party"] is not None)
            self.report("party", "invite / accept")
            for player in self.players:
                await route(player, (("북", "grass"),))
            self.phase = "combat"
            enemy_id = first.state["enemies"][0]["id"]
            started = monotonic()
            await first.act("어린청소룡 사냥", lambda state: state["combat_target"] is not None)
            # 단축 전투에서 두 번째 플레이어의 화면 전송을 기다리는 사이 적이 죽지 않도록
            # 참여와 outsider 거절 요청을 같은 시점에 보낸다. 권한은 서버가 판정한다.
            await asyncio.gather(
                second.act("어린청소룡 사냥", lambda state: state["combat_target"] is not None),
                outsider.expect_text("어린청소룡 사냥", "다른 파티"),
            )
            await first.until(lambda state: state["player_round"] >= 1, self.timeouts.combat)
            first_round = monotonic() - started
            if self.harness.mode == "full":
                assert first_round >= self.timings["COMBAT_INTERVAL"] - 0.5, first_round
            self.report("combat", f"claim outsider 거절 / actual first round {first_round:.3f}s")
            for player in (first, second):
                await player.until(lambda state: state["xp"] == 11 and state["combat_target"] is None,
                                   self.timeouts.combat)
                assert player.state["credits"] == 150
            self.report("combat", "shared enemy defeated / 양쪽 참여 보상")
            self.phase = "corpse"
            await first.until(lambda state: bool(state["corpses"]))
            death_seen = monotonic()
            corpse_id = first.state["corpses"][0]["id"]
            await second.until(lambda state: any(c["id"] == corpse_id for c in state["corpses"]))
            physical = [entry for entry in second.state["corpses"][0]["loot"] if entry["kind"] == "item"]
            assert all(entry["assigned_name"] == first.name and entry["can_take"] and entry["protected"] for entry in physical)
            await outsider.until(lambda state: bool(state["corpses"]))
            await outsider.expect_text("시체에서 모두 가져", "보호된 전리품")
            # 권한을 확인하고 남겨 두어 같은 시체의 ground 전환을 검증한다.
            await first.act("시체에서 2칩 가져", lambda state: state["credits"] == 151)
            await second.until(lambda state: state["credits"] == 151)
            self.report("corpse", "currency 즉시 지급 없음 / 부분 회수 1칩씩 분배 / outsider blocked")
            self.phase = "lifecycle"
            await outsider.until(lambda state: not state["corpses"] and bool(state["ground_loot"]),
                                 self.timeouts.lifecycle)
            self.elapsed("corpse → ground", death_seen, self.timings["CORPSE_TTL_SECONDS"])
            assert any(entry["protected"] for ground in outsider.state["ground_loot"]
                       for entry in ground["loot"])
            await outsider.expect_text("모두 가져", "보호된 전리품")
            self.report("lifecycle", "ground loot / protection 유지")
            self.phase = "respawn"
            await outsider.until(lambda state: any(e["id"] == enemy_id and e["hp"] == e["max_hp"]
                                                  and e["can_attack"] for e in state["enemies"]),
                                 self.timeouts.lifecycle)
            self.elapsed("enemy respawn", death_seen,
                         self.timings["CORPSE_TTL_SECONDS"] + self.timings["RESPAWN_DELAY_SECONDS"])
            self.report("respawn", "같은 spawn / max HP / attack 가능")
            self.phase = "protection"
            await outsider.until(lambda state: bool(state["ground_loot"]) and all(
                not entry["protected"] for ground in state["ground_loot"] for entry in ground["loot"]),
                self.timeouts.lifecycle)
            self.elapsed("loot protection expiry", death_seen, self.timings["LOOT_PROTECTION_SECONDS"])
            await outsider.act("모두 가져", lambda state: not state["ground_loot"])
            assert outsider.state["credits"] == 156
            self.report("protection", "outsider blocked → allowed / 미회수 6칩 자유 획득")
            self.phase = "shop"
            await route(first, (("귀환", "support_roof"), ("승강기", "support_elevator")))
            await first.act("3층", lambda state: state["zone"] == "support_3f_c")
            await route(first, (("동", "support_3f_e1"),
                                ("북", "weapon_shop")))
            assert any(obj["name"] == "무기상" for obj in first.state["interactables"])
            await first.expect_text("무기상 상품", "55칩")
            before_credits = first.state["credits"]
            # RNG drop은 남겨 둔 ground에서 outsider만 회수한다. 구매 결과는 미리 지급하지 않는다.
            assert count_item(first.state, "cutting_machete") == 0
            await first.act("무기상에게 절단마체테 구매", lambda state: count_item(state, "cutting_machete") == 1)
            assert first.state["credits"] == before_credits - 55
            await first.expect_text("절단마체테 가치", "매입가는 27칩")
            single_sale = next(action for obj in first.state["interactables"] for action in obj["actions"]
                               if action["label"] == "절단마체테 · 27칩 판매")
            assert single_sale["command"].endswith("절단마체테 판매")
            await first.act(single_sale["command"], lambda state: count_item(state, "cutting_machete") == 0)
            assert first.state["credits"] == before_credits - 28
            await first.act("무기상에게 절단마체테 구매", lambda state: count_item(state, "cutting_machete") == 1)
            self.report("shop", "옥상 귀환 / 승강기 / 가치·구매·판매 / 재구매")
            self.phase = "persistence"
            saved = {key: first.state[key] for key in
                     ("name", "xp", "credits", "inventory", "quest")}
            saved_resources = {key: first.state[key] for key in ("hp", "mental")}
            first.closing = True
            await first.send("text", ["종료"])
            await asyncio.wait_for(first.socket.wait_closed(), STATE_TIMEOUT)
            await first.close()
            await first.open()
            assert first.state["zone"] == "staging_room"
            assert saved == {key: first.state[key] for key in saved}
            assert all(value <= first.state[key] <= first.state["max_" + key]
                       for key, value in saved_resources.items())
            await first.expect_prompt("접속자")
            # 빠른 CI에서는 전체 흐름이 첫 지급 전에 끝날 수 있다. 부분 경계의
            # 소수 기여까지 쌓여 정수가 지급되는 실제 상태를 두 경계 안에서 기다린다.
            await first.until(lambda state: state["mental"] > 10,
                              RECOVERY_INTERVAL * 2 + STATE_TIMEOUT)
            assert first.state["mental"] > 10
            self.report("recovery", "10초 경계의 실제 정신력 회복 / 재로그인 회복·진행 보존")
            self.report("persistence", "종료 명령 / fixture relogin / prompt 복원 / 대기실 및 진행 보존")
            if self.harness.mode == "full":
                from smoke_closeout import Closeout

                await Closeout(self).run()
        except BaseException:
            details = {"mode": self.harness.mode, "scenario": self.phase,
                       "players": [player.summary() for player in self.players],
                       "server_logs": str(self.harness.run_dir)}
            message = json.dumps(details, ensure_ascii=False)
            print("FAIL " + message, flush=True)
            self.log.write("FAIL " + message + "\n")
            raise
        finally:
            await asyncio.gather(*(player.close() for player in self.players))


async def live(harness):
    await harness.ready()
    with (harness.run_dir / "client.log").open("w", encoding="utf-8") as log:
        await harness.supervise(Scenario(harness, log).run())


def main():
    parser = argparse.ArgumentParser(description="격리형 실제 Evennia/WebSocket smoke")
    parser.add_argument("--mode", choices=("quick", "full"), default="quick")
    args = parser.parse_args()
    harness = Harness(args.mode)
    started = monotonic()
    play_db = ROOT / "game" / "server" / "evennia.db3"
    before = fingerprint(play_db)
    print(f"SMOKE {args.mode.upper()} — isolated SQLite / fixture accounts / actual scheduler", flush=True)
    success = False
    try:
        harness.prepare()
        print(f"환경: {harness.run_dir}, 전용 포트: {harness.ports}", flush=True)
        harness.start()
        asyncio.run(live(harness))
        success = True
    except BaseException:
        if harness.run_dir:
            print(f"실패 진단 DB/로그 보존: {harness.run_dir}", flush=True)
            (harness.run_dir / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        try:
            harness.stop()
        except BaseException:
            print(f"process cleanup 실패 — DB/로그 보존: {harness.run_dir}", flush=True)
            raise
        after = fingerprint(play_db)
        if before != after:
            raise RuntimeError("일반 플레이 SQLite의 hash/mtime/size가 변경되었습니다.")
        print("PASS [isolation] play DB SHA256 / mtime_ns / size unchanged: "
              + json.dumps(after), flush=True)
        if success:
            harness.discard()
            print(f"PASS [{args.mode}] 완료 / process stop / temp cleanup: "
                  f"{monotonic() - started:.3f}s", flush=True)


if __name__ == "__main__":
    main()
