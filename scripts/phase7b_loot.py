"""실제 네 session에서 native 실물/화폐 권리와 production 만료를 검증한다."""

import asyncio
import json
from time import monotonic, time

from phase7b import fixture
from smoke import Client, count_item, route


async def run(harness):
    prepared = fixture(harness, "loot")
    original = next(row["native"] for row in prepared["snapshot"]["sources"].values()
                    if row["key"] == "권리검증시체")
    item = original["items"][0]
    claim = original["claims"][0]
    currency_owner = next(int(key.split(":")[1]) for key, source in prepared["snapshot"]["sources"].items()
                          if source["key"] == "분배검증칩")
    harness.start()
    await harness.ready()
    players = [Client(name, password, harness.ws_url) for name, password in harness.credentials]
    evidence = []
    start = monotonic()

    def record(case, **values):
        row = {"case": case, "PASS": True, **values}
        evidence.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    try:
        await asyncio.gather(*(player.open() for player in players))
        await asyncio.gather(*(route(player, (("남", "hq_concourse"), ("서", "dock"))) for player in players))
        a, b, c, d = players
        before = count_item(a.state, "bandage")
        source_label = next(row["label"] for row in a.state["corpses"] if row["name"] == "권리검증시체")
        await d.expect_text(source_label + "에서 붕대 가져", "보호된 전리품")
        await a.act(source_label + "에서 붕대 가져", lambda s: count_item(s, "bandage") == before + 1)
        partial = fixture(harness, "inspect")
        remaining = next(row for source in partial["sources"].values() for row in source["native"]["items"] if row["id"] == item["id"])
        assert remaining["quantity"] == 5 and remaining["sequence"] == item["sequence"]
        assert not partial["players"][a.name]["native"]["claims"]
        record("partial physical", added=1, remainder=5, source_uuid_sequence_preserved=True, inventory_claim_removed=True)
        credits = [player.state["credits"] for player in players]
        await d.expect_text("모두 가져", "보호된 전리품")
        await a.act("2칩 가져")
        await b.until(lambda s: s["credits"] == credits[1] + 2)
        assert a.state["credits"] == credits[0]
        await b.act("5칩 가져", lambda s: s["credits"] == credits[1] + 7)
        await b.close()
        await a.act("5칩 가져")
        paid = fixture(harness, "inspect")
        assert paid["players"][b.name]["profile"]["credits"] == credits[1] + 12
        currency = next(source["native"]["currency"][0] for source in paid["sources"].values() if source["key"] == "분배검증칩")
        assert currency["quantity"] == 8 and sum(amount for _, amount in currency["shares"]) == 8
        assert (paid["players"][a.name]["id"], 0) in map(tuple, currency["shares"])
        other_label = next(row["label"] for row in a.state["corpses"] if row["name"] == "다른분배칩")
        await a.expect_text(other_label + "에서 모두 가져", "보호된 전리품")
        record("currency allocation", original=20, online_paid=7, offline_paid=5, remaining=8, zero_share_trigger=True, different_group_blocked=True)
        await a.until(lambda s: not any(row["name"] == "권리검증시체" for row in s["corpses"]), 100)
        decayed = fixture(harness, "inspect")
        ground = next(source["native"] for source in decayed["sources"].values()
                      if any(row["id"] == item["id"] for row in source["native"]["items"]))
        moved = next(row for row in ground["items"] if row["id"] == item["id"])
        assert moved["location"] == "world_loot" and moved["quantity"] == 5
        assert moved["sequence"] == item["sequence"] and moved["state"] == item["state"]
        assert ground["claims"] == [claim]
        record("corpse to ground", uuid_quantity_sequence_state_claim_deadline_preserved=True)
        # 절대 보호 기한을 실제 production 시간으로 기다린다. fixture 시간을 바꾸지 않는다.
        await d.until(lambda s: any(row["id"] == currency_owner and all(not entry["protected"] for entry in row["loot"])
                                    for row in s["ground_loot"]), max(1, prepared["deadline"] - time()) + 15)
        await d.act("8칩 가져", lambda s: s["credits"] == credits[3] + 8)
        await d.act("붕대 모두 가져", lambda s: count_item(s, "bandage") == before + 5)
        final = fixture(harness, "inspect")
        assert not any(row["id"] == item["id"] for source in final["sources"].values() for row in source["native"]["items"])
        record("protection expiry", outsider_paid=8, outsider_physical=5, total_currency=20, deadline_seconds=120)
    finally:
        messages = {player.name: list(player.messages._queue)[-8:] for player in players}
        await asyncio.gather(*(player.close() for player in players), return_exceptions=True)
        (harness.run_dir / "loot-evidence.json").write_text(json.dumps(
            {"seconds": monotonic() - start, "cases": evidence, "last_messages": messages,
             "last_states": [player.summary() for player in players]}, ensure_ascii=False, default=str), encoding="utf-8")
