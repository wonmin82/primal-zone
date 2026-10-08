"""실제 서버에서 빈 총기·자동 재장전·소각·복수 광원 경계를 검사한다."""

import json
from time import monotonic

from phase7b import fixture
from smoke import Client, count_item, route, travel_to


async def run(harness):
    prepared = fixture(harness, "items")
    harness.start()
    await harness.ready()
    player = Client(*harness.credentials[0], harness.ws_url)
    start, evidence = monotonic(), []

    def record(case, **values):
        evidence.append({"case": case, "PASS": True, **values})
        print(json.dumps(evidence[-1], ensure_ascii=False), flush=True)

    def native():
        return fixture(harness, "inspect")["players"][player.name]

    try:
        await player.open()
        await player.act("탐사용손전등 1 켜")
        await player.act("탐사용손전등 2 켜")
        lights = [row for row in native()["native"]["items"] if row["definition"] == "flashlight"]
        assert sum(row["state"]["enabled"] for row in lights) == 1
        await player.act("탐사용손전등 2 꺼")
        assert not any(row["state"]["enabled"] for row in native()["native"]["items"] if row["definition"] == "flashlight")
        record("portable light", only_one_on=True, off=True)
        await route(player, (("남", "hq_concourse"), ("서", "dock"), ("북", "grass")))
        profile = native()["profile"]
        await player.act("어린청소룡 공격", lambda s: s["combat_target"] is not None)
        await player.until(lambda s: any("탄" in str(message) for message in list(player.messages._queue)), timeout=20)
        empty = native()["profile"]
        assert empty["player_round"] > profile["player_round"]
        assert (empty["mental"], empty["skill_ready_at"]) == (profile["mental"], profile["skill_ready_at"])
        assert next(row for row in player.state["enemies"] if row["name"] == "어린청소룡")["hp"] == 24
        await player.act("도망", lambda s: s["combat_target"] is None, timeout=30)
        record("empty firearm", opportunity_consumed=True, mental_cooldown_unchanged=True, damage=0)
        await player.act("경비카빈 재장전")
        rows = native()["native"]["items"]
        gun = next(row for row in rows if row["definition"] == "guard_carbine")
        loaded = next(row for row in rows if row["parent"] == gun["id"])
        assert loaded["state"]["rounds"] == 9
        record("automatic reload", highest_rounds=9)
        await travel_to(player, "salvage_office")
        credits = player.state["credits"]
        ammo = count_item(player.state, "ammo_556")
        await player.act("경비카빈 해제")
        await player.expect_text("경비카빈 소각", "탄창을 먼저 분리")
        await player.act("경비카빈에서 탄창 꺼내")
        # sequence 기반 local index를 사용해 방금 분리한 잔탄 9발 탄창을 고른다.
        magazines = sorted((row for row in native()["native"]["items"] if row["definition"] == "mag_556_standard"), key=lambda row: row["sequence"])
        index = next(i for i, row in enumerate(magazines, 1) if row["id"] == loaded["id"])
        await player.act(f"5.56mm 표준탄창 {index} 소각")
        await player.act("경비카빈 소각", lambda s: count_item(s, "guard_carbine") == 0)
        assert player.state["credits"] == credits and count_item(player.state, "ammo_556") == ammo
        assert loaded["id"] not in {row["id"] for row in native()["native"]["items"]}
        record("firearm/magazine burn", loaded_rejected=True, unloaded_body_burn=True, rounds_destroyed=9, loose_ammo_returned=0, credits_paid=0)
        assert prepared["players"][player.name]["native"]["items"]
    finally:
        await player.close()
        (harness.run_dir / "items-evidence.json").write_text(json.dumps({
            "seconds": monotonic() - start, "cases": evidence, "last_messages": list(player.messages._queue)[-12:]
        }, ensure_ascii=False, default=str), encoding="utf-8")
