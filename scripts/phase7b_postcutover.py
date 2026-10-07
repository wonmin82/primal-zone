"""Canonical valid corpus를 전환한 실제 서버에서 native 명령을 실행한다."""

import asyncio
import json
from time import monotonic

from phase7b import fixture
from smoke import Client, count_item, route


async def run(harness):
    secret = harness.run_dir / "game/server/conf/secret_settings.py"
    with secret.open("a", encoding="utf-8") as output:
        output.write("ITEM_MAINTENANCE = False\nITEM_MIGRATION_AUDIT = False\n")
    before = fixture(harness, "inspect")
    harness.start()
    await harness.ready()
    players = [Client(name, password, harness.ws_url) for name, password in harness.credentials]
    evidence = []
    start = monotonic()

    def record(case, **values):
        evidence.append({"case": case, "PASS": True, **values})
        print(json.dumps(evidence[-1], ensure_ascii=False), flush=True)

    try:
        for player in players:
            await player.open()
            await player.act("소지품")
            await player.act("장비")
        a, b, c, d = players
        assert count_item(a.state, "cutting_machete") == 2
        assert count_item(d.state, "guard_carbine") == 2
        assert count_item(b.state, "outpost_supply_pass") == 1
        record("native login/inventory/equipment", accounts=4, legacy_mapping=True)
        for player in (a, b):
            await route(player, (("남", "hq_concourse"), ("남", "support_1f_c"),
                                 ("서", "support_1f_w1"), ("북", "storage_room")))
        old = count_item(a.state, "bandage")
        await a.act("보관상자에 붕대 넣어", lambda s: count_item(s, "bandage") == old - 1)
        other = count_item(b.state, "bandage")
        await b.act("보관상자에서 붕대 꺼내", lambda s: count_item(s, "bandage") == other + 1)
        old = count_item(a.state, "jungle_longblade")
        await a.act("개인 보관함에서 정글장도 꺼내", lambda s: count_item(s, "jungle_longblade") == old + 1)
        await b.act("개인 보관함에 능선포식자표식 넣어", lambda s: count_item(s, "ridge_predator_mark") == 0)
        await b.act("개인 보관함에서 능선포식자표식 꺼내", lambda s: count_item(s, "ridge_predator_mark") == 1)
        await b.expect_text("보관상자에 능선포식자표식 넣어", "다른 소유자")
        await b.expect_text("검증가에게 능선포식자표식 줘", "다른 소유자")
        await b.expect_text("능선포식자표식 버려", "다른 소유자")
        record("storage", transferable_cross_owner=True, unique_personal=True, unique_shared_rejected=True)
        await a.act("탐사용손전등 켜")
        await a.act("탐사용손전등 확인")
        await a.act("탐사용손전등 꺼")
        record("migrated light", on_inspect_off=True)
        await route(b, (("남", "support_1f_w1"), ("서", "support_1f_w2"), ("북", "salvage_office")))
        await b.expect_text("능선포식자표식 소각", "해당 행동")
        old = count_item(b.state, "outpost_supply_pass")
        await b.expect_text("전초 보급구역 출입증 소각", "소각 확정")
        await b.act("소지품")
        assert count_item(b.state, "outpost_supply_pass") == old
        reward_before = (b.state["xp"], b.state["credits"], count_item(b.state, "bandage"), count_item(b.state, "ridge_predator_mark"))
        await b.act("전초 보급구역 출입증 소각 확정", lambda s: count_item(s, "outpost_supply_pass") == 0)
        await route(b, (("남", "support_1f_w2"), ("동", "support_1f_w1"), ("동", "support_1f_c")))
        await b.act("승강기", lambda s: s["zone"] == "support_elevator")
        await b.act("3층", lambda s: s["zone"] == "support_3f_c")
        await route(b, (("서", "support_3f_w1"), ("서", "support_3f_w2")))
        await b.expect_text("북", "출입증")
        assert b.state["zone"] == "support_3f_w2"
        await b.act("귀환", lambda s: s["zone"] == "support_roof")
        await b.act("승강기", lambda s: s["zone"] == "support_elevator")
        await b.act("1층", lambda s: s["zone"] == "support_1f_c")
        await route(b, (("북", "hq_concourse"), ("서", "dock")))
        await b.act("윤대장 대화", lambda s: count_item(s, "outpost_supply_pass") == 1)
        assert reward_before == (b.state["xp"], b.state["credits"], count_item(b.state, "bandage"), count_item(b.state, "ridge_predator_mark"))
        await route(b, (("동", "hq_concourse"), ("남", "support_1f_c")))
        await b.act("승강기", lambda s: s["zone"] == "support_elevator")
        await b.act("3층", lambda s: s["zone"] == "support_3f_c")
        await route(b, (("서", "support_3f_w1"), ("서", "support_3f_w2"), ("북", "outpost_equipment")))
        await b.expect_text("능선포식자표식 판매", "매매할 수 없는")
        await b.act("소지품")
        assert count_item(b.state, "ridge_predator_mark") == 1
        unique_before = [row for row in before["players"][b.name]["native"]["items"]
                         if row["definition"] == "ridge_predator_mark"]
        unique_after = [row for row in fixture(harness, "inspect")["players"][b.name]["native"]["items"]
                        if row["definition"] == "ridge_predator_mark"]
        assert unique_before == unique_after
        record("Boss unique policy", personal_storage=True, shared_give_drop_sell_burn_rejected=True,
               identity_sequence_state_preserved=True)
        record("credential", first_no_mutation=True, burn_blocks_entry=True, reissue_no_repeat_rewards=True, entry_restored=True)
        # Shop source/sink는 archived inventory를 갱신하지 않는다.
        await route(b, (("남", "support_3f_w2"), ("동", "support_3f_w1"), ("동", "support_3f_c"),
                        ("동", "support_3f_e1"), ("북", "weapon_shop")))
        credits = b.state["credits"]
        await b.act("경비카빈 구매", lambda s: count_item(s, "guard_carbine") == 1)
        assert b.state["credits"] == credits - 200
        await b.expect_text("경비카빈 판매", "탄창을 먼저 분리")
        await b.act("경비카빈에서 탄창 꺼내")
        await b.act("5.56mm 표준탄창에서 카빈탄 꺼내", lambda s: count_item(s, "ammo_556") == 20)
        await b.act("5.56mm 표준탄창 채워", lambda s: count_item(s, "ammo_556") == 0)
        await b.act("경비카빈 재장전")
        await b.act("경비카빈에서 탄창 꺼내")
        await b.expect_text("5.56mm 표준탄창 판매", "잔탄 20발")
        await b.act("경비카빈 판매", lambda s: count_item(s, "guard_carbine") == 0)
        record("shop/firearm", package=200, included_rounds=20, loaded_sell_rejected=True, residual_resale=True)
        await route(a, (("남", "support_1f_w1"), ("동", "support_1f_c"),
                        ("북", "hq_concourse"), ("서", "dock")))
        recipient_credits = fixture(harness, "inspect")["players"][b.name]["profile"]["credits"]
        await a.act("2칩 가져")
        await a.act("시체에서 경비카빈 가져", lambda s: count_item(s, "guard_carbine") == 1)
        picked = fixture(harness, "inspect")
        assert picked["players"][b.name]["profile"]["credits"] == recipient_credits + 2
        old_tree = next(row["native"]["items"] for row in before["sources"].values()
                        if row["key"] == "TEST LEGACY CORPUS 시체")
        picked_ids = {row["id"] for row in old_tree}
        tree = [row for row in picked["players"][a.name]["native"]["items"] if row["id"] in picked_ids]
        assert len(tree) == len(old_tree)
        assert [(row["id"], row["sequence"], row["parent"], row["state"]) for row in tree] == [
            (row["id"], row["sequence"], row["parent"], row["state"]) for row in old_tree]
        record("migrated loot", firearm_identity_tree_state_preserved=True, zero_share_trigger_paid=2)
        await a.act("탐사용손전등 켜")
        await a.act("윤대장 대화")
        await route(a, (("북", "grass"), ("북", "trail"), ("동", "office")))
        await a.act("정비기록 조사")
        await route(a, (("동", "generator"),))
        await a.act("발전기 수리", lambda s: count_item(s, "generator_repair_part") == 0)
        await route(a, (("서", "office"), ("서", "trail"), ("남", "grass"), ("동", "wreck")))
        bandages = count_item(a.state, "bandage")
        await a.act("보급상자 조사", lambda s: count_item(s, "bandage") == bandages + 2)
        assert count_item(a.state, "generator_repair_part") == 0 and count_item(a.state, "expedition_tag") == 1
        assert count_item(a.state, "scrap") == 20
        record("migration repair then first cache", repair_regrant=0, bandage_granted=2,
               expedition_tag=1, economic_scrap_preserved=20)
        after = fixture(harness, "inspect")
        for name, row in before["players"].items():
            assert after["players"][name]["native"]["item_runtime_version"] == 1
            for key in ("inventory", "equipment", "storage", "light_sources"):
                assert row["profile"].get(key) == after["players"][name]["profile"].get(key), (name, key, "legacy mutation")
        record("archive preservation", legacy_inventory_equipment_storage_lights_unchanged=True)
    finally:
        messages = {player.name: list(player.messages._queue)[-8:] for player in players}
        await asyncio.gather(*(player.close() for player in players), return_exceptions=True)
        (harness.run_dir / "post-cutover-evidence.json").write_text(json.dumps(
            {"seconds": monotonic() - start, "cases": evidence, "last_messages": messages,
             "last_states": [player.summary() for player in players]}, ensure_ascii=False, default=str), encoding="utf-8")
