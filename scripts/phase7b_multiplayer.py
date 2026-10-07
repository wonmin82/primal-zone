"""네 독립 WebSocket session의 V1 Boss/party E2E. SQLite 단일 서버 검증이다."""

import asyncio
import json
from time import monotonic

from phase7b import fixture
from smoke import Client, route


async def run(harness):
    fixture(harness, "boss")
    harness.start()
    await harness.ready()
    players = [Client(name, password, harness.ws_url) for name, password in harness.credentials]
    started = monotonic()
    evidence = []

    def boss(player, name):
        return next(row for row in player.state["enemies"] if row["name"] == name)

    def record(case, **values):
        row = {"case": case, "PASS": True, **values}
        evidence.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    async def join(leader, member):
        await leader.expect_text(member.name + " 파티초대", "초대를 보냈다")
        await member.expect_text("파티수락", "합류했다")
        await leader.act("파티")

    async def fight(name, participants, maximum):
        for player in participants:
            while player.state["hp"] < player.state["max_hp"] * .95:
                hp = player.state["hp"]
                await player.act("붕대 사용", lambda s, hp=hp: s["hp"] > hp)
        xp = [player.state["xp"] for player in players]
        for player in participants:
            await player.act(name + " 공격", lambda s: s["combat_target"] is not None)
        await participants[0].until(lambda s: boss(participants[0], name)["max_hp"] == maximum, 20)
        record(name + " scaling", maximum=maximum, participants=len(participants))
        await participants[0].until(lambda s: s["combat_target"] is None, 120)
        for player in participants:
            await player.until(lambda s: s["combat_target"] is None)
            await player.act("상태")
        gained = [player.state["xp"] - old for player, old in zip(players, xp)]
        assert sum(gained) == 130, gained
        assert all(gained[players.index(player)] > 0 for player in participants)
        record(name + " XP", gained=gained, total=sum(gained))

    try:
        for player in players:
            await player.open()
            await route(player, (("남", "hq_concourse"), ("서", "dock"), ("북", "grass"),
                                 ("북", "trail"), ("북", "marsh"), ("북", "ridge")))
        a, b, c, d = players
        await fight("일인검증우두머리", [a], 170)
        await join(a, b)
        await fight("이인검증우두머리", [a, b], 297)
        await join(a, c)
        await fight("삼인검증우두머리", [a, b, c], 425)
        await join(a, d)
        for player in players:
            while player.state["hp"] < player.state["max_hp"] * .95:
                hp = player.state["hp"]
                await player.act("붕대 사용", lambda s, hp=hp: s["hp"] > hp)
        xp = [player.state["xp"] for player in players]
        name = "사인검증우두머리"
        for player in (a, b):
            await player.act(name + " 공격", lambda s: s["combat_target"] is not None)
        await a.until(lambda s: boss(a, name)["max_hp"] == 297, 20)
        old = dict(boss(a, name))
        assert old["hp"] < old["max_hp"]
        # 두 late join 요청을 독립 session에서 함께 보낸다. 별도 3인 encounter에서
        # 2.50x는 이미 검사했다. 여기서는 상태 push 대기 중 처치를 피한다.
        await asyncio.gather(*(player.act(name + " 공격", lambda s: s["combat_target"] is not None, timeout=30)
                               for player in (c, d)))
        await a.until(lambda s: boss(a, name)["max_hp"] == 552, 20)
        new = dict(boss(a, name))
        # 증가분만 더해진다. 기다리는 동안 실제 공격이 더 들어올 수 있다.
        assert new["max_hp"] - new["hp"] >= old["max_hp"] - old["hp"]
        record("late join", old=old, new=new, damage_not_erased=True)
        record("4-player scaling", maximum=552)
        await d.act("도망", lambda s: s["combat_target"] is None, timeout=30)
        await d.until(lambda s: boss(d, name)["max_hp"] == 552, 20)
        assert boss(d, name)["max_hp"] == 552
        record("participant leave", maximum=552, no_downscale=True)
        # 같은 encounter에서 재참여해 reward snapshot의 4명 XP를 확인한다.
        if d.state["zone"] != "ridge":
            await d.act("북", lambda s: s["zone"] == "ridge")
        await d.act(name + " 공격", lambda s: s["combat_target"] is not None)
        await a.until(lambda s: s["combat_target"] is None, 120)
        for player in players:
            await player.act("상태")
        gained = [player.state["xp"] - old for player, old in zip(players, xp)]
        assert sum(gained) == 130 and all(amount > 0 for amount in gained), gained
        record("4-player XP", gained=gained, total=130)
        await a.expect_text(d.name + " 파티제외", "제외되었다")
        await c.expect_text("파티탈퇴", "떠났다")
        await a.expect_text(b.name + " 파티장위임", "파티장을 맡았다")
        await a.expect_text("파티탈퇴", "떠났다")
        await b.expect_text("파티탈퇴", "떠났다")
        record("party lifecycle", invite_accept_kick_leave_leader_cleanup=True)
        # 첫 Boss는 나머지 세 전투 중 production corpse/respawn 시간을 경과했다.
        await a.until(lambda s: any(row["name"] == "일인검증우두머리" and row["state"] == "alive"
                                   for row in s["enemies"]), 70)
        assert boss(a, "일인검증우두머리")["max_hp"] == 170
        record("next encounter reset", maximum=170)
    finally:
        messages = {player.name: list(player.messages._queue)[-8:] for player in players}
        await asyncio.gather(*(player.close() for player in players), return_exceptions=True)
        (harness.run_dir / "multiplayer-evidence.json").write_text(
            json.dumps({"seconds": monotonic() - started, "cases": evidence,
                        "last_states": [player.summary() for player in players], "last_messages": messages},
                       ensure_ascii=False, default=str), encoding="utf-8")
