"""API smoke test against a running LOCAL game server; creates a test account.

Run: uv run python scripts/smoke.py
The generated password is never printed or written to a file. Test accounts stay
in the local development DB, with normal player permissions.
"""

import asyncio
import json
import secrets

from websockets.asyncio.client import connect


class Client:
    def __init__(self, name, password):
        self.name, self.password = name, password
        self.socket = None
        self.state = None

    async def open(self, mode="register"):
        self.socket = await connect("ws://127.0.0.1:4002", subprotocols=["v1.evennia.com"])
        await self.send(
            "pz_auth", [{"mode": mode, "username": self.name, "password": self.password}]
        )
        return await self.until(lambda state: state["name"] == self.name)

    async def send(self, kind, args):
        await self.socket.send(json.dumps([kind, args, {}], ensure_ascii=False))

    async def until(self, predicate, timeout=20):
        async with asyncio.timeout(timeout):
            while True:
                kind, args, _ = json.loads(await self.socket.recv())
                if kind == "pz_auth" and not args[0]["ok"]:
                    raise AssertionError(args[0]["message"])
                if kind == "pz_state":
                    self.state = args[0]
                    if predicate(self.state):
                        return self.state

    async def act(self, text, predicate=lambda state: True):
        await self.send("text", [text])
        return await self.until(predicate)

    async def expect_text(self, command, expected, timeout=20):
        await self.send("text", [command])
        async with asyncio.timeout(timeout):
            while True:
                kind, args, _ = json.loads(await self.socket.recv())
                if kind == "pz_state":
                    self.state = args[0]
                if kind == "text" and expected in args[0]:
                    return

    async def fight(self):
        before_xp = self.state["xp"]
        await self.act("어린청소룡 공격", lambda state: state["encounter"] is not None)
        while self.state["encounter"]:
            turn = self.state["encounter"]["round"]
            if turn + 1 >= self.state["encounter"]["heavy_ready"]:
                await self.send("text", ["강타"])
            await self.until(
                lambda state: state["encounter"] is None or state["encounter"]["round"] > turn
            )
        assert self.state["xp"] > before_xp

    async def close(self):
        if self.socket:
            await self.socket.close()


async def main():
    name = "검증" + secrets.token_hex(3)
    player = Client(name, secrets.token_urlsafe(24))
    try:
        await player.open()
        assert player.state["name"] == name
        print("PASS: Korean registration and initial state", flush=True)
        await player.expect_text("공격 어린청소룡", "대상 뒤에 행동")
        for command, content in (
            ("안녕  여러분 말", "안녕  여러분"),
            ("'어린청소룡 공격", "어린청소룡 공격"),
            ("'안녕하세요 말", "안녕하세요 말"),
        ):
            await player.expect_text(command, f"{name}: {content}")
        await player.act("상태")
        assert player.state["encounter"] is None
        print("PASS: suffix commands and both chat forms without accidental combat", flush=True)
        await player.act("윤대장 대화", lambda state: "정비기록" in state["quest"])
        await player.act("북", lambda state: state["zone"] == "grass")
        for index in range(6):
            await player.fight()
            print(f"PASS: real combat and loot {index + 1}/6", flush=True)
            await player.act("귀환", lambda state: state["zone"] == "dock")
            await player.act("휴식", lambda state: state["hp"] == state["max_hp"])
            if index < 5:
                await player.act("북", lambda state: state["zone"] == "grass")
        has_blade = any(item["id"] == "blade" for item in player.state["inventory"])
        if not has_blade:
            await player.act(
                "강철마체테 교환",
                lambda state: any(item["id"] == "blade" for item in state["inventory"]),
            )
        before_attack = player.state["attack"]
        await player.act("강철마체테 착용", lambda state: state["attack"] > before_attack)
        print("PASS: equipped weapon changes server stats", flush=True)
        await player.act("북", lambda state: state["zone"] == "grass")
        await player.act("북", lambda state: state["zone"] == "trail")
        await player.act("동", lambda state: state["zone"] == "office")
        await player.act("정비기록 조사", lambda state: "발전기 수리" in state["quest"])
        saved = player.state.copy()
        await player.close()
        await player.open("login")
        for key in ("name", "zone", "hp", "xp", "credits", "inventory", "quest"):
            assert player.state[key] == saved[key], key
        print("PASS: reconnect preserves location, inventory, gear and quest", flush=True)
        print("SMOKE OK", flush=True)
    finally:
        await player.close()


if __name__ == "__main__":
    asyncio.run(main())
