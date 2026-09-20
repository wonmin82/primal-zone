"""실행 중인 로컬 서버의 공유 사냥 검사. 일반 계정 3개를 남긴다.

비밀번호는 메모리에서만 생성한다. 플레이 DB를 초기화하지 않는다.
"""

import asyncio
import json
import secrets

from websockets.asyncio.client import connect


class Client:
    def __init__(self, name, password):
        self.name, self.password = name, password
        self.socket = self.reader = self.state = None
        self.revision = 0
        self.changed = asyncio.Condition()
        self.messages = asyncio.Queue()
        self.error = None

    async def open(self, mode="register"):
        self.state, self.error = None, None
        self.socket = await connect("ws://127.0.0.1:4002", subprotocols=["v1.evennia.com"])
        self.reader = asyncio.create_task(self.receive())
        await self.send(
            "pz_auth", [{"mode": mode, "username": self.name, "password": self.password}]
        )
        return await self.until(lambda state: state["name"] == self.name)

    async def receive(self):
        try:
            async for raw in self.socket:
                kind, args, _ = json.loads(raw)
                async with self.changed:
                    if kind == "pz_auth" and not args[0]["ok"]:
                        self.error = AssertionError(args[0]["message"])
                    elif kind == "pz_state":
                        self.state = args[0]
                        self.revision += 1
                    elif kind == "text":
                        self.messages.put_nowait(args[0])
                    self.changed.notify_all()
        except Exception as error:
            async with self.changed:
                self.error = error
                self.changed.notify_all()

    async def send(self, kind, args):
        await self.socket.send(json.dumps([kind, args, {}], ensure_ascii=False))

    async def until(self, predicate, timeout=30, after=-1):
        async with asyncio.timeout(timeout), self.changed:
            while not self.state or self.revision <= after or not predicate(self.state):
                if self.error:
                    raise self.error
                await self.changed.wait()
            return self.state

    async def act(self, text, predicate=lambda state: True, timeout=30):
        before = self.revision
        await self.send("text", [text])
        return await self.until(predicate, timeout, before)

    async def expect_text(self, command, expected, timeout=20):
        while not self.messages.empty():
            self.messages.get_nowait()
        await self.send("text", [command])
        async with asyncio.timeout(timeout):
            while expected not in await self.messages.get():
                pass

    async def fight(self):
        await self.until(
            lambda state: any(
                e["enemy_id"] == "scavenger" and e["can_attack"] for e in state["enemies"]
            ),
            timeout=65,
        )
        before_xp = self.state["xp"]
        await self.act("어린청소룡 사냥", lambda state: state["combat_target"] is not None)
        while self.state["combat_target"]:
            turn = self.state["player_round"]
            if self.state["heavy_ready"]:
                await self.send("text", ["강타"])
            await self.until(
                lambda state: state["combat_target"] is None or state["player_round"] > turn
            )
        assert self.state["xp"] > before_xp

    async def close(self):
        if self.socket:
            await self.socket.close()
        if self.reader:
            await self.reader


def count_item(state, item):
    return sum(entry["count"] for entry in state["inventory"] if entry["id"] == item)


async def main():
    suffix = secrets.token_hex(3)
    players = [
        Client(prefix + suffix, secrets.token_urlsafe(24))
        for prefix in ("검증가", "검증나", "검증다")
    ]
    first, second, outsider = players
    try:
        for index, player in enumerate(players):
            if index == 2:
                print("WAIT: 기본 가입 제한(600초당 2개)에 따라 610초 대기", flush=True)
                await asyncio.sleep(610)
            try:
                await player.open()
            except AssertionError as error:
                if "creating too many accounts" not in str(error):
                    raise
                await player.close()
                print("WAIT: 앞선 가입 검사 제한이 만료되도록 610초 대기", flush=True)
                await asyncio.sleep(610)
                await player.open()
        print("PASS: 한글 일반 계정 3개 가입", flush=True)
        await first.expect_text("공격 어린청소룡", "대상 뒤에 행동")
        for text in ("안녕하세요 말", "'어린청소룡 공격"):
            await first.expect_text(text, first.name + ":")
        await first.act("윤대장 대화", lambda state: "정비기록" in state["quest"])
        await first.act(second.name + " 파티초대", lambda state: state["party"] is not None)
        await second.until(lambda state: state["invitation"] is not None)
        await second.act("파티수락", lambda state: state["party"] is not None)
        for player in players:
            await player.act("북", lambda state: state["zone"] == "grass")
        await first.until(lambda state: bool(state["enemies"]), timeout=65)
        await first.act("어린청소룡 사냥", lambda state: state["combat_target"] is not None)
        await second.act("어린청소룡 사냥", lambda state: state["combat_target"] is not None)
        await outsider.expect_text("어린청소룡 사냥", "다른 파티")
        for player in (first, second):
            await player.until(lambda state: state["xp"] == 11 and state["combat_target"] is None)
            assert player.state["credits"] == 24
        await outsider.expect_text("시체에서 모두 가져", "보호된 전리품")
        await second.act(
            "시체에서 모두 가져",
            lambda state: all(not corpse["loot"] for corpse in state["corpses"]),
        )
        await first.until(lambda state: count_item(state, "scrap") == 1)
        assert count_item(second.state, "scrap") == 0
        print("PASS: 파티·점유 거부·참여 보상·시체·순번 회수", flush=True)
        await first.act("파티탈퇴", lambda state: state["party"] is None)
        await second.until(lambda state: state["party"]["is_leader"])
        await outsider.act("동", lambda state: state["zone"] == "wreck")
        for index in range(5):
            await first.act("귀환", lambda state: state["zone"] == "dock")
            await first.act("휴식", lambda state: state["hp"] == state["max_hp"])
            await first.act("북", lambda state: state["zone"] == "grass")
            if index % 2 == 0:
                await first.act("동", lambda state: state["zone"] == "wreck")
            await first.fight()
            if index:
                await first.act(
                    "시체에서 모두 가져",
                    lambda state: all(not corpse["loot"] for corpse in state["corpses"]),
                )
            print(f"PASS: 솔로 공유 적 사냥·재생성 {index + 1}/5", flush=True)
        await outsider.until(lambda state: bool(state["ground_loot"]), timeout=40)
        protected = any(
            entry["protected"]
            for source in outsider.state["ground_loot"]
            for entry in source["loot"]
        )
        if protected:
            await outsider.expect_text("모두 가져", "보호된 전리품")
        await outsider.until(
            lambda state: any(
                not entry["protected"]
                for source in state["ground_loot"]
                for entry in source["loot"]
            ),
            timeout=135,
        )
        await outsider.act("모두 가져", lambda state: count_item(state, "scrap") > 0)
        print("PASS: 시체 소멸·바닥 전리품·보호 만료 후 외부 회수", flush=True)
        await first.act("귀환", lambda state: state["zone"] == "dock")
        if not count_item(first.state, "blade"):
            await first.act("강철마체테 구매", lambda state: count_item(state, "blade") > 0)
        before_attack = first.state["attack"]
        await first.act("강철마체테 착용", lambda state: state["attack"] > before_attack)
        for direction, zone in (("북", "grass"), ("북", "trail"), ("동", "office")):
            await first.act(direction, lambda state, zone=zone: state["zone"] == zone)
        await first.act("정비기록 조사", lambda state: "발전기 수리" in state["quest"])
        saved = first.state.copy()
        await first.close()
        await first.open("login")
        for key in ("name", "zone", "hp", "xp", "credits", "inventory", "quest"):
            assert first.state[key] == saved[key], key
        print("PASS: 장비 능력치·탐험·재접속 저장", flush=True)
        print("SMOKE OK (전체 보스 임무와 OS IME 검사는 별도)", flush=True)
    finally:
        for player in players:
            await player.close()


if __name__ == "__main__":
    asyncio.run(main())
