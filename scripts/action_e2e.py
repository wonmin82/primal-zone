"""실제 Portal/Server/인증 WebSocket의 Action 수직 경로와 재시작 영속성을 검증한다."""

import asyncio
import json
import subprocess
import sys

from smoke_harness import ROOT, Harness
from websockets.asyncio.client import connect


class Client:
    def __init__(self, harness):
        self.harness = harness
        self.socket = None
        self.state = None

    async def wait(self, predicate):
        async with asyncio.timeout(15):
            while True:
                kind, args, _ = json.loads(await self.socket.recv())
                if kind == "pz_state":
                    self.state = args[0]
                if kind == "pz_log" and args[0].get("kind") == "error":
                    text = "".join(segment["text"] for segment in args[0].get("segments", ()))
                    categories = ("세션", "추가 입력", "선택할 수", "제공자", "권한", "동기 완료", "처리 중 오류", "대상 수")
                    category = next((value for value in categories if value in text), "uncategorized")
                    raise AssertionError("Action protocol error category: " + category)
                if predicate(kind, args):
                    return args[0] if args else None

    async def send(self, kind, payload):
        await self.socket.send(json.dumps([kind, [payload], {}], ensure_ascii=False))

    async def open(self):
        self.socket = await connect(f"ws://127.0.0.1:{self.harness.ports['ws']}/",
                                    subprotocols=["v1.evennia.com"])
        await self.wait(lambda kind, args: kind == "text")
        name, password = self.harness.credentials[0]
        await self.send("pz_auth", {"mode": "login", "username": name, "password": password})
        await self.wait(lambda kind, args: kind == "pz_state")
        await self.prompt()

    async def prompt(self):
        return await self.wait(lambda kind, args: kind == "pz_log" and args[0].get("kind") == "prompt")

    async def completion(self):
        await self.wait(lambda kind, args: kind == "text" and "검증 행동을 완료했다." in args[0] or
                        kind == "pz_log" and any("검증 행동을 완료했다." in segment["text"]
                                                  for segment in args[0].get("segments", ())))
        await self.prompt()

    async def close(self):
        if self.socket:
            await self.socket.close()


def snapshot(harness):
    output = subprocess.check_output([sys.executable, str(ROOT / "scripts/action_fixture.py"), "snapshot"],
                                     cwd=harness.run_dir / "game", env=harness.env,
                                     text=True, encoding="utf-8", timeout=30)
    return json.loads(output.splitlines()[-1])


async def scenario(harness):
    await harness.ready()
    client = Client(harness)
    try:
        await client.open()
        control = next(row["action"] for row in client.state["action_controls"]
                       if row["action"]["action_id"] == "validation.object")
        stable = control["roles"]["provider"][0]
        await client.send("text", "검증기 1 2 검측")
        await client.completion()
        first = await asyncio.to_thread(snapshot, harness)
        assert len(first["events"]) == 1 and first["events"][0]["quantity"] == 2
        assert first["events"][0]["roles"]["provider"] == [stable["identity"]]
        await client.send("pz_action", {**control, "request_id": "normal-1"})
        confirmation = await client.wait(lambda kind, args: kind == "pz_action_result")
        await client.prompt()
        confirmed = {**confirmation["action"], "request_id": "confirmed-1"}
        assert confirmed["roles"]["provider"][0] == stable
        await client.send("pz_action", confirmed)
        await client.completion()
        await client.send("pz_action", confirmed)
        second = await asyncio.to_thread(snapshot, harness)
        assert len(second["events"]) == 2 and second["issues"] == 0
        assert second["events"][1]["roles"]["provider"] == [stable["identity"]]
        assert second["number"] == first["number"] == 1
        await client.close()
        await harness.restart()
        await client.open()
        restarted = next(row["action"] for row in client.state["action_controls"]
                         if row["action"]["action_id"] == "validation.object")
        assert restarted["roles"]["provider"][0] == stable
        persisted = await asyncio.to_thread(snapshot, harness)
        assert persisted == second
        print("PASS Action E2E: actual text / stable-ID web / confirmation / replay / server restart", flush=True)
    finally:
        await client.close()


def main():
    harness = Harness("quick")
    before = None
    success = False
    try:
        harness.prepare(ROOT / "scripts/action_fixture.py")
        before = harness.owned_database_fingerprint()
        harness.start()
        asyncio.run(harness.supervise(scenario(harness)))
        success = True
    finally:
        harness.stop()
        after = harness.owned_database_fingerprint() if before is not None else None
        print(json.dumps({"owned_test_db_before": before, "owned_test_db_after": after}), flush=True)
        if success:
            harness.discard()
            print("PASS owned process cleanup / isolated fixture cleanup / production DB not accessed", flush=True)
        elif harness.run_dir:
            print(f"FAIL diagnostic fixture retained: {harness.run_dir}", flush=True)


if __name__ == "__main__":
    main()
