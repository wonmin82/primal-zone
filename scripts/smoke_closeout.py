"""Full 전용 본부·현재 두 임무·실제 restart 연결 검증. Quick 경로는 확장하지 않는다."""

import asyncio
import json
from copy import deepcopy
from time import monotonic

from smoke import count_item, route, travel_to
from world.content import ITEMS
from world.lighting import project_power
from world.rules import purchase_price


def assert_shutdown_items(saved, restored, before_at, stopped_at):
    """Live → shutdown: 켜진 광원의 OFF/시간 정산만 허용한다."""
    assert saved.keys() == restored.keys(), "재시작 item identity 변경"
    for identity, old in saved.items():
        new = restored[identity]
        assert {k: v for k, v in old.items() if k != "state"} == {
            k: v for k, v in new.items() if k != "state"}, identity
        if ITEMS[old["definition"]].get("light_source") and old["state"].get("enabled"):
            state = new["state"]
            expected = dict(old["state"], enabled=False, started_at=None,
                            remaining_power=state["remaining_power"])
            assert state == expected, (identity, "광원 OFF 정산 외 state 변경", state)
            lower = project_power(old["state"], stopped_at)["remaining_power"]
            upper = project_power(old["state"], before_at)["remaining_power"]
            assert lower <= state["remaining_power"] <= upper, (identity, "광원 잔량", lower, state, upper)
        else:
            assert old["state"] == new["state"], (identity, "state 변경")


def assert_startup_items(stopped, restored):
    """Shutdown 정산 이후 startup/relogin은 item 전체를 그대로 보존한다."""
    assert stopped == restored, "startup/relogin item 변경"


def assert_preserved_loot(before, final, *, stopped=None, after=None, require_decay=True):
    """Native identity/tree/권리를 보존하며 기한이 지난 item claim 삭제만 허용한다."""
    assert before["observed_at"] <= before["completed_at"] <= final["observed_at"] <= final["completed_at"], \
        "snapshot 관측 시각 순서 오류"

    def indexed(snapshot, field):
        rows = {}
        for source_id, source in snapshot["loot"].items():
            assert source["native"] is True, "Full restart는 native loot만 검증한다"
            for identity, row in source[field].items():
                assert identity not in rows, (field, identity, "native identity 중복")
                rows[identity] = (source_id, source, row)
        return rows

    def check_source(old_id, old, new_id, new):
        assert old["room"] == new["room"], "loot room 변경"
        if old["corpse"] and new["corpse"] and not require_decay:
            assert old_id == new_id, "미만료 corpse source 변경"
        elif old["corpse"]:
            assert not new["corpse"], "시체 callback 이후 ground 이동 누락"
            assert new_id not in before["loot"], "시체 entry가 기존 source를 재사용함"
        else:
            assert old_id == new_id and not new["corpse"], "ground source 변경"

    # 신규 ID는 before→stopped 사이 실제 death wrapper가 원 roll과 대조한 ledger만 허용한다.
    # startup/relogin/이후 이동은 전투가 없으므로 새 birth가 하나라도 있으면 실패한다.
    original_before = before
    births_before, births_final = before.get("loot_births", {}), final.get("loot_births", {})
    if stopped is not None or after is not None:
        assert stopped is not None and after is not None, "restart 관측 단계 누락"
        assert stopped.get("loot_births", {}) == after.get("loot_births", {}) == births_final, \
            "startup 이후 death ledger 변경"
    additions = []
    for enemy_id in births_before.keys() | births_final.keys():
        old, new = births_before.get(enemy_id, []), births_final.get(enemy_id, [])
        assert new[:len(old)] == old, "기존 death ledger 변경/소실"
        extra = new[len(old):]
        if extra:
            assert len(extra) == 1, "한 restart 구간 enemy의 중복 death"
            enemy = original_before.get("enemies", {}).get(enemy_id)
            assert enemy and enemy["state"] == "alive" and enemy["combatants"], "관측 전투가 없는 신규 death"
            assert stopped is not None and after is not None, "신규 death의 stopped/after 증거 없음"
            assert stopped.get("loot_births", {}) == after.get("loot_births", {}) == births_final, \
                "startup 이후 신규 death ledger"
            event = extra[0]
            source = event["source"]
            assert original_before["observed_at"] <= event["at"] <= stopped["completed_at"], "death 관측 범위 오류"
            assert source["corpse"] and source["native"] and source["created_at"] == event["at"]
            assert source["room"] == enemy["room"], "death room 변경"
            additions.append(event)
    if additions:
        before = deepcopy(before)
        old_item_ids, old_currency_ids = indexed(before, "items"), indexed(before, "currency")
        for event in additions:
            source_id, source = event["source_id"], event["source"]
            assert source_id not in before["loot"], "death가 기존 source를 재승인함"
            assert not old_item_ids.keys() & source["items"].keys(), "death가 기존 item을 재승인함"
            assert not old_currency_ids.keys() & source["currency"].keys(), "death가 기존 currency를 재승인함"
            before["loot"][source_id] = source
            old_item_ids, old_currency_ids = indexed(before, "items"), indexed(before, "currency")

    old_items, new_items = indexed(before, "items"), indexed(final, "items")
    old_currency, new_currency = indexed(before, "currency"), indexed(final, "currency")
    assert indexed(original_before, "items") or indexed(original_before, "currency"), "native loot 보존 검사의 기존 asset이 없음"
    assert old_items.keys() == new_items.keys(), "출처 없는 신규 native item 또는 기존 item 소실"
    assert old_currency.keys() == new_currency.keys(), "출처 없는 신규 native currency 또는 기존 currency 소실"
    expired = 0
    decay_destinations = {}
    decay_roots = set()

    def record_decay_entry(source_id, field, identity, *, root):
        if root:
            assert source_id not in decay_roots, "서로 다른 시체 entry가 한 ground source로 병합됨"
            decay_roots.add(source_id)
        destination = decay_destinations.setdefault(source_id, {"items": set(), "currency": set()})
        destination[field].add(identity)

    for identity, (source_id, source, item) in old_items.items():
        assert identity in new_items, (identity, "native item 소실")
        new_id, new_source, restored = new_items[identity]
        check_source(source_id, source, new_id, new_source)
        if item["parent"] is not None:
            assert old_items[item["parent"]][0] == source_id, (identity, "기존 tree source 불일치")
            assert new_items[item["parent"]][0] == new_id, (identity, "복원 tree source 불일치")
        if source["corpse"] and not new_source["corpse"]:
            record_decay_entry(new_id, "items", identity, root=item["parent"] is None)
        expected = dict(item)
        if source["corpse"] and not new_source["corpse"] and item["parent"] is None:
            assert item["location"] == "corpse_loot", (identity, "잘못된 corpse root 위치")
            expected["location"] = "world_loot"
        assert restored == expected, (identity, "native item 수량/state/tree 변경")
        claim = source["claims"].get(identity)
        new_claim = new_source["claims"].get(identity)
        if claim is not None and new_claim is None:
            assert claim["protection_until"] <= final["completed_at"], (identity, "미만료 claim 소실")
            expired += 1
        else:
            assert claim == new_claim, (identity, "claim identity/권리 변경")
    for identity, (source_id, source, currency) in old_currency.items():
        assert identity in new_currency, (identity, "native currency 소실")
        new_id, new_source, restored = new_currency[identity]
        check_source(source_id, source, new_id, new_source)
        assert currency == restored, (identity, "currency 수량/권리/share 변경")
        if source["corpse"] and not new_source["corpse"]:
            record_decay_entry(new_id, "currency", identity, root=True)
    for source_id, expected in decay_destinations.items():
        for field in ("items", "currency"):
            assert final["loot"][source_id][field].keys() == expected[field], \
                (source_id, field, "시체 entry의 새 source에 다른 asset이 병합됨")
    return {"items": len(old_items), "currency": len(old_currency), "expired_claims": expired}


def save_restart_snapshot(harness, label, snapshot):
    """소유한 격리 실행 경로에만 fixture snapshot을 배타적으로 저장한다."""
    assert harness.mode == "full"
    assert label in {"before", "stopped", "after", "final"}
    harness.owned_database_fingerprint()
    with (harness.run_dir / f"restart-{label}.json").open("x", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)


def stop_for_restart(harness):
    """Full 전용: 격리 Portal의 정상 종료를 요청하고 owned process exit를 확인한다."""
    assert harness.mode == "full"
    harness.check_alive()
    harness.graceful_stop()


class Closeout:
    def __init__(self, scenario):
        self.scenario = scenario
        self.first, self.second, self.outsider = scenario.players

    async def equipment_change(self, definition, *, equip=True, identity=None):
        """공개 selector 실행을 같은 Native UUID의 장착 상태·주무기·표시와 연결한다."""
        player = self.first
        candidates = [row for row in player.state["inventory"] if row["id"] == definition
                      and (identity is None or row["identity"] == identity)]
        assert len(candidates) == 1, (definition, identity, "Full 장비 UUID가 유일하지 않음", candidates)
        selected = candidates[0]
        identity, slot = selected["identity"], selected["slot"]
        assert identity and selected["count"] == 1 and selected["equipped"] is not equip
        action = selected["equip_action"] if equip else selected["remove_action"]

        def changed(state):
            rows = [row for row in state["inventory"] if row["identity"] == identity]
            return len(rows) == 1 and rows[0]["equipped"] is equip and (
                not selected["weapon"] or rows[0]["active_weapon"] is equip)

        await player.act(f"{selected['selector']} {action}", changed)
        current = next(row for row in player.state["inventory"] if row["identity"] == identity)
        assert current["id"] == definition and current["count"] == 1
        assert current["selector"] == selected["selector"], "장착 전후 B-1 번호 변경"
        equipped = [row for row in player.state["inventory"] if row["equipped"] and row["slot"] == slot]
        expected = " · ".join(
            row["selector"] + (" [주무기]" if row["active_weapon"] else "")
            + (f" · {row['state_summary']}" if row["state_summary"] else "")
            for row in equipped
        ) or None
        assert player.state["equipment"][slot] == expected, (slot, expected, player.state["equipment"][slot])
        saved = (await asyncio.to_thread(self.scenario.harness.checkpoint))["players"][player.name]
        item = saved["items"][identity]
        assert item["definition"] == definition and item["quantity"] == 1
        assert item["location"] == ("equipment" if equip else "inventory")
        assert item["slot"] == (slot if equip else None)
        if selected["weapon"]:
            assert saved["active_weapon"] == (identity if equip else None)

    async def floor(self, player, stop, zone):
        await player.act("승강기", lambda s: s["zone"] == "support_elevator")
        await player.act(stop, lambda s: s["zone"] == zone)

    async def dock(self, player):
        await player.act("귀환", lambda s: s["zone"] == "support_roof")
        await self.floor(player, "1층", "hq_concourse")
        await travel_to(player, 'dock')

    async def kill(self, enemy_name):
        player = self.first
        xp = player.state["xp"]
        await player.act(enemy_name + " 공격", lambda s: s["combat_target"] is not None)
        while player.state["combat_target"] is not None:
            state = player.state
            turn = state["player_round"]
            enemy = next((e for e in state['enemies'] if e['name'] == enemy_name), {})
            # 예고가 회복/강타 기회를 계속 가로채지 않도록 생존과 공격을 우선한다.
            if state["hp"] < state["max_hp"] * .55 and count_item(state, "bandage"):
                await self.combat_action("붕대 사용", "bandage", "다음 차례에는 공격 대신 붕대를 사용한다.")
            elif state["mental"] >= 8 and state["heavy_ready"]:
                await self.combat_action("강타", "heavy", "다음 차례에 강타 행동을 준비한다.")
            elif enemy.get('telegraph') and state['mental'] >= 6:
                await self.combat_action("견제", "suppress", "다음 차례에 견제 행동을 준비한다.")
            else:
                await player.until(lambda s: s["combat_target"] is None or s["player_round"] > turn,
                                   self.scenario.timeouts.combat)
        assert player.state["xp"] > xp and player.state["zone"] != "infirmary"

    def combat_diagnostic(self, command, phase):
        state = self.first.state
        target = state.get("combat_target") or {}
        line = json.dumps({"command": command, "phase": phase,
                           "player_round": state.get("player_round"), "queue": state.get("queued_action"),
                           "hp": state.get("hp"), "mental": state.get("mental"),
                           "bandages": count_item(state, "bandage"),
                           "target_hp": target.get("hp"), "target_round": target.get("round")}, ensure_ascii=False)
        self.scenario.log.write("OBSERVED [combat] " + line + "\n")
        self.scenario.log.flush()

    async def combat_action(self, command, action, acknowledgement):
        """Full에서 예약 성공 응답과 이후 차례 소비를 구분하여 한 번만 전송한다."""
        player = self.first
        assert player.state["combat_target"] is not None and player.state["queued_action"] == "attack", \
            "이전 예약이 남은 상태에서는 후속 전투 명령을 보내지 않는다"
        previous_logs = tuple(player.semantic_logs)
        old_logs = {id(row) for row in previous_logs}
        # pz_log는 semantic_logs와 messages 양쪽에, 일반 text(붕대 예약)는
        # messages에만 들어간다. 전송 전 응답은 두 채널에서 모두 분리한다.
        while not player.messages.empty():
            player.messages.get_nowait()
        acknowledged = False
        target_id = player.state["combat_target"]["id"]
        self.combat_diagnostic(command, "send")

        def check():
            nonlocal acknowledged
            if player.error:
                raise player.error
            state = player.state
            assert state["hp"] > 0 and state["zone"] != "infirmary", "예약 행동 대기 중 패배"
            assert state["combat_target"] is None or state["combat_target"]["id"] == target_id, \
                "예약 행동 대기 중 대상 변경"
            fresh = [row for row in player.semantic_logs if id(row) not in old_logs]
            assert not any(row.get("kind") == "error" for row in fresh), (command, "전투 명령 오류 응답")
            while not player.messages.empty():
                message = player.messages.get_nowait()
                acknowledged = acknowledged or acknowledgement in message
            return acknowledged

        try:
            await player.send("text", [command])
            async with asyncio.timeout(player.command_timeout), player.changed:
                while not check():
                    if player.state["combat_target"] is None:
                        self.combat_diagnostic(command, "battle-ended-before-ack")
                        return
                    await player.changed.wait()
            self.combat_diagnostic(command, "ack")
            # Client가 state/log의 전체 수신 순서를 저장하지 않으므로 이미 소비된 경합은
            # ack 시점 이후 자연 차례를 보수적으로 기다린다. 명령을 다시 보내지 않는다.
            acknowledged_round = player.state["player_round"]
            async with asyncio.timeout(self.scenario.timeouts.combat), player.changed:
                while True:
                    check()
                    state = player.state
                    if state["combat_target"] is None:
                        break
                    assert state["queued_action"] in ("attack", action), "예약 행동이 다른 행동으로 변경됨"
                    if state["queued_action"] == "attack" and state["player_round"] > acknowledged_round:
                        break
                    await player.changed.wait()
            self.combat_diagnostic(command, "consumed-or-finished")
        except BaseException:
            self.combat_diagnostic(command, "failed")
            raise

    async def run(self):
        await self.enemy_recovery()
        self.scenario.phase = "hq-closeout"
        player = self.first
        await self.dock(player)
        await travel_to(player, 'storage_room')
        for name in ("보관상자", "개인 보관함"):
            before = count_item(player.state, "bandage")
            await player.act(name + "에 붕대 넣어", lambda s: count_item(s, "bandage") == before - 1)
            await player.act(name + "에서 붕대 꺼내", lambda s: count_item(s, "bandage") == before)
            await player.act(name + "에 붕대 넣어", lambda s: count_item(s, "bandage") == before - 1)
        await travel_to(player, 'salvage_office')
        await player.expect_text("정산관 환율", "10칩")
        before = player.state["credits"]
        await player.act("정산관에게 회수부품 7개 교환", lambda s: s["credits"] == before + 70)
        assert count_item(player.state, "scrap") == 3
        await travel_to(player, 'hq_concourse')
        await self.floor(player, "4층", "support_4f_c")
        await travel_to(player, 'training_room')
        assert player.state["training_available"]
        # Lv.1 has no earned upgrade. Training becomes available after real XP gains.
        await player.expect_text("강타 배워", "남은 기술 훈련")
        await travel_to(player, 'infirmary')
        await player.act("의무관 회복", lambda s: s["hp"] == s["max_hp"])
        self.scenario.phase = "defeat"
        outsider = self.outsider
        await route(outsider, (("북", "trail"),))
        before = outsider.state["credits"]
        await outsider.act("갈퀴사냥룡 공격", lambda s: s["combat_target"] is not None)
        await outsider.until(lambda s: s["zone"] == "infirmary" and s["combat_target"] is None,
                             self.scenario.timeouts.combat)
        assert outsider.state["hp"] == 1 and outsider.state["credits"] == before - min(before, 10)
        await travel_to(outsider, "recovery_room")
        await outsider.act("침대 휴식", lambda s: s["hp"] == s["max_hp"] and s["mental"] == s["max_mental"])
        self.scenario.report("defeat", "actual enemy → infirmary / HP 1 / 최대 10칩 / Bed HP·정신력 full")
        self.scenario.phase = "hq-closeout"
        await player.act("귀환", lambda s: s["zone"] == "support_roof")
        await self.floor(player, "1층", "hq_concourse")
        await travel_to(player, 'supply_shop')
        for command, item in (("붕대 사", "bandage"), ("탐사용손전등 사", "flashlight"), ("건전지 사", "battery")):
            before = count_item(player.state, item)
            await player.act(command, lambda s, item=item, before=before: count_item(s, item) == before + 1)
        await player.expect_text("탐사용손전등에 건전지 넣어", "넣")
        await player.act("탐사용손전등 켜")
        await travel_to(player, 'hq_concourse')
        await self.floor(player, "5층", "support_5f_c")
        await travel_to(player, 'armor_shop')
        await player.act("강화방호조끼 사", lambda s: count_item(s, "reinforced_vest") == 1)
        # 격리 smoke fixture는 준비 단계에서 기본 손 무기를 명시 해제한다.
        assert player.state["equipment"]["hands"] is None
        await self.equipment_change("cutting_machete")
        await self.equipment_change("expedition_workwear", equip=False)
        await self.equipment_change("reinforced_vest")
        self.scenario.report("hq", "보관/정산/훈련/Doctor/Bed/귀환/승강기/3종 상점 실제 연결")
        await self.progression()
        await self.restart()

    async def enemy_recovery(self):
        self.scenario.phase = "enemy-recovery"
        player = self.second
        enemy = player.state["enemies"][0]
        before_round = player.state["player_round"]
        await player.act("어린청소룡 공격", lambda s: s["combat_target"] is not None)
        await player.until(lambda s: s["player_round"] > before_round, self.scenario.timeouts.combat)
        await player.act("도망", lambda s: s["combat_target"] is None)
        damaged = next(e for e in player.state["enemies"] if e["id"] == enemy["id"])["hp"]
        started = monotonic()
        await player.until(lambda s: any(e["id"] == enemy["id"] and e["hp"] > damaged
                                        for e in s["enemies"]), 35)
        restored = next(e for e in player.state["enemies"] if e["id"] == enemy["id"])["hp"]
        elapsed = monotonic() - started
        assert elapsed >= 15 - 1.5 and damaged < restored < enemy["max_hp"]
        await player.act("어린청소룡 공격", lambda s: s["combat_target"] is not None)
        assert next(e for e in player.state["enemies"] if e["id"] == enemy["id"])["hp"] == restored
        await player.act("도망", lambda s: s["combat_target"] is None)
        self.scenario.report("enemy-recovery", f"15초 유예 / 점진 회복 {damaged}→{restored} / 재교전 HP 보존 ({elapsed:.3f}s)")

    async def progression(self):
        self.scenario.phase = "progression"
        player = self.first
        await self.dock(player)
        await route(player, (("북", "grass"), ("동", "wreck")))
        await player.act("보급상자 조사", lambda s: count_item(s, "generator_repair_part") == 3)
        await route(player, (("서", "grass"), ("북", "trail"), ("북", "marsh")))
        await player.expect_text("북", "발전기")
        await route(player, (("남", "trail"), ("동", "office")))
        await player.act("정비기록 조사", lambda s: "발전기 수리" in s["quest"])
        await route(player, (("동", "generator"),))
        await player.act("발전기 수리", lambda s: count_item(s, "generator_repair_part") == 0)
        # Earn the first boss's preparation level through real kills, not an oversized HP fixture.
        await self.kill('고장난경비기')
        await player.act('시체에서 모두 가져')
        await route(player, (("서", "office"), ("서", "trail")))
        await self.kill('갈퀴사냥룡')
        await player.act('시체에서 모두 가져')
        await route(player, (("남", "grass"),))
        await self.kill('어린청소룡')
        await player.act('시체에서 모두 가져')
        await route(player, (("동", "wreck"),))
        await self.kill('어린청소룡')
        await player.act('시체에서 모두 가져')
        # 연속 출정의 누적 소모는 실제 의료 서비스로 회복한다. 수치·fixture를 바꾸지 않는다.
        await player.act("귀환", lambda s: s["zone"] == "support_roof")
        await self.floor(player, "3층", "support_3f_c")
        await travel_to(player, 'infirmary')
        if player.state['hp'] < player.state['max_hp'] or player.state['mental'] < player.state['max_mental']:
            await travel_to(player, 'recovery_room')
            await player.act('침대 휴식', lambda s: s['hp'] == s['max_hp'] and s['mental'] == s['max_mental'])
        self.scenario.report('expedition-recovery', '연속 사냥 후 실제 3층 침대 회복 / 전투 수치·fixture 변경 없음')
        await self.dock(player)
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh")))
        await self.kill('갈퀴사냥룡')
        await player.act('시체에서 모두 가져')
        await self.kill('고장난경비기')
        await player.act('시체에서 모두 가져')
        assert player.state['level'] >= 4
        await self.prepare_first_boss_level()
        await self.prepare_boss()
        await self.dock(player)
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh"), ("북", "ridge")))
        await self.kill("능선의우두머리")
        await player.act('시체에서 모두 가져')
        await player.expect_text("북", "보고")
        await self.dock(player)
        await player.act("윤대장에게 보고 말", lambda s: "선발대 길잡이" in s["quest"])
        self.scenario.report("quest", "정비기록/부품 3개 수리/첫 gate/alpha/윤대장 보고")
        await self.prepare_boss(advanced=True)
        await self.dock(player)
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh"),
                             ("북", "ridge"), ("북", "jungle_edge")))
        await player.act("선발대 길잡이에게 수락 말", lambda s: "관측소" in s["quest"])
        await route(player, (("북", "jungle_watch"),))
        await player.act("관측 표식 조사", lambda s: "수위 표식" in s["quest"])
        # Full은 실제 XP로 Lv7 준비를 만든다. 기능 E2E를 Lv6의 근소한 전투
        # 승패에 의존시키지 않으며 확정 수치나 fixture XP를 바꾸지 않는다.
        await self.kill("날쌘발톱룡")
        await player.act("시체에서 모두 가져")
        await route(player, (("남", "jungle_edge"), ("동", "jungle_road")))
        await player.act("수위 표식 조사", lambda s: count_item(s, "jungle_cell") == 1)
        await route(player, (("북", "jungle_grove"),))
        await self.kill("그늘추적룡")
        await player.act("시체에서 모두 가져")
        await player.expect_text("북", "닫혀")
        await player.act("신호 장치 조사", lambda s: count_item(s, "jungle_cell") == 0)
        assert player.state["level"] >= 7
        await self.restock_boss(advanced=True, target_rank=3)
        await self.dock(player)
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh"),
                             ("북", "ridge"), ("북", "jungle_edge"), ("동", "jungle_road"),
                             ("북", "jungle_grove")))
        await route(player, (("북", "jungle_gate"), ("북", "jungle_nest")))
        await self.kill("밀림의포식자")
        await route(player, (("남", "jungle_gate"), ("남", "jungle_grove"),
                             ("남", "jungle_road"), ("서", "jungle_edge")))
        await player.act("선발대 길잡이에게 보고 말", lambda s: s["quest"] == "깊은 밀림 조사를 마쳤습니다.")
        self.scenario.report("progression", "두 표식/신호전지/두 번째 gate/jungle apex/최종 보고 완료")
        await self.dock(player)
        await travel_to(player, 'hq_concourse')
        await self.floor(player, "4층", "support_4f_c")
        await travel_to(player, 'training_room')
        rank = next(skill["rank"] for skill in player.state["growth"]["skills"] if skill["id"] == "heavy")
        await player.act("타격교관에게 강타 배워", lambda s: any(skill["id"] == "heavy" and skill["rank"] == rank + 1 for skill in s["growth"]["skills"]))
        self.scenario.report("training", "Lv.1 훈련 없음 / 실제 임무 XP 이후 NPC Rank +1 / 무료")

    async def prepare_first_boss_level(self):
        """Full 첫 보스의 Lv5 준비를 고정 경로의 공개 사냥 최대 세 번으로 마친다."""
        player = self.first
        if player.state['level'] >= 5:
            return
        assert player.state['zone'] == 'marsh', '첫 보스 추가 사냥 시작 위치 불일치'
        for steps, enemy_name in (
            ((("남", "trail"),), '갈퀴사냥룡'),
            ((("남", "grass"),), '어린청소룡'),
            ((("동", "wreck"),), '어린청소룡'),
        ):
            await route(player, steps)
            # 재등장하지 않은 적을 대체하거나 production 시간을 바꾸지 않는다.
            await player.until(lambda s: any(e['name'] == enemy_name and e['hp'] > 0 and e['can_attack']
                                            for e in s['enemies']))
            before_xp, before_level = player.state['xp'], player.state['level']
            await self.kill(enemy_name)
            await player.act('시체에서 모두 가져')
            self.scenario.report('first-boss-level',
                                 f"{player.state['zone']} {enemy_name} 실제 사냥/시체 회수 / "
                                 f"XP {before_xp}→{player.state['xp']} / "
                                 f"Lv.{before_level}→{player.state['level']}")
            if player.state['level'] >= 5:
                return
        assert player.state['level'] >= 5, ('첫 보스 유한 사냥 후 Lv5 미달', player.state['xp'], player.state['level'])

    async def prepare_boss(self, advanced=False):
        player = self.first
        await player.act('귀환', lambda s: s['zone'] == 'support_roof')
        await self.floor(player, '5층', 'support_5f_c')
        await travel_to(player, 'weapon_shop')
        if not count_item(player.state, 'folding_shield'):
            await player.act('접이식방패 사', lambda s: count_item(s, 'folding_shield') == 1)
            await self.equipment_change('folding_shield')
        if advanced:
            # 첫 보고의 실제 출입증으로 열린 전초 병기고에서 T2를 구매한다.
            await travel_to(player, 'outpost_weapon')
            await player.act('정글장도 사', lambda s: count_item(s, 'jungle_longblade') == 1)
            await self.equipment_change('cutting_machete', equip=False)
            await self.equipment_change('jungle_longblade')
        if advanced:
            await player.act('귀환', lambda s: s['zone'] == 'support_roof')
            await self.floor(player, '5층', 'support_5f_c')
            await travel_to(player, 'outpost_equipment')
            await self.equipment_change('reinforced_vest', equip=False)
            await player.act('강화방호조끼 팔아', lambda s: count_item(s, 'reinforced_vest') == 0)
            await player.act('전술방호복 사', lambda s: count_item(s, 'tactical_protective_suit') == 1)
            await self.equipment_change('tactical_protective_suit')
        else:
            await travel_to(player, 'armor_shop')

            def boots_snapshot(state):
                return {"items": {row["identity"]: row["count"] for row in state["inventory"]
                                  if row["id"] == "non_slip_boots"}, "credits": state["credits"]}

            before = boots_snapshot(player.state)
            boots = sum(before["items"].values())
            prior_logs = tuple(player.semantic_logs)
            try:
                await player.act('미끄럼방지탐사화 사', lambda s: count_item(s, 'non_slip_boots') == boots + 1)
            except TimeoutError as error:
                # 이번 공개 구매 뒤의 semantic 거절만 남긴다. 인증 요청/원문 로그는 수집하지 않는다.
                refusals = ["".join(part["text"] for part in log["segments"])
                            for log in player.semantic_logs
                            if not any(log is prior for prior in prior_logs) and log.get("kind") == "error"]
                raise AssertionError({"operation": "Full boots purchase", "before": before,
                                      "after": boots_snapshot(player.state), "refusals": refusals[-3:]}) from error
            after = boots_snapshot(player.state)
            added = set(after["items"]) - set(before["items"])
            assert len(added) == 1 and after["items"][next(iter(added))] == 1, (before, after)
            assert {identity: after["items"].get(identity) for identity in before["items"]} == before["items"]
            assert after["credits"] == before["credits"] - purchase_price("non_slip_boots"), (before, after)
            await self.equipment_change('non_slip_boots', identity=next(iter(added)))
        if count_item(player.state, 'expedition_tag') and not player.state['equipment']['neck']:
            await self.equipment_change('expedition_tag')
        await self.restock_boss(advanced=advanced)

    async def restock_boss(self, advanced=False, target_rank=2):
        """현재 보유 장비를 유지하고 실제 상점·교관·침대로 다시 준비한다."""
        player = self.first
        await player.act('귀환', lambda s: s['zone'] == 'support_roof')
        await self.floor(player, '1층', 'hq_concourse')
        await travel_to(player, 'supply_shop')
        while count_item(player.state, 'bandage') < 8:
            before = count_item(player.state, 'bandage')
            assert player.state['credits'] >= ITEMS['bandage']['value'], (
                'Full 보스 준비금 부족', player.state['credits'], before)
            await player.act('붕대 사', lambda s: count_item(s, 'bandage') == before + 1)
        await travel_to(player, 'hq_concourse')
        await self.floor(player, '4층', 'support_4f_c')
        await travel_to(player, 'training_room')
        strength = next(attribute['allocated'] for attribute in player.state['growth']['attributes']
                        if attribute['id'] == 'strength')
        remaining = player.state['growth']['attribute_points']
        amount = min(remaining, max(0, 4 - strength))
        if amount:
            await player.act(f'힘 {amount} 배분', lambda s: any(
                a['id'] == 'strength' and a['allocated'] == strength + amount
                for a in s['growth']['attributes']))
        while (rank := next(skill['rank'] for skill in player.state['growth']['skills'] if skill['id'] == 'heavy')) < target_rank:
            await player.act('타격교관에게 강타 배워', lambda s: any(
                skill['id'] == 'heavy' and skill['rank'] == rank + 1 for skill in s['growth']['skills']))
        await travel_to(player, 'survival_training_room')
        remaining = player.state['growth']['attribute_points']
        if remaining:
            constitution = next(a['allocated'] for a in player.state['growth']['attributes']
                                if a['id'] == 'constitution')
            await player.act(f'체질 {remaining} 배분', lambda s: any(
                a['id'] == 'constitution' and a['allocated'] == constitution + remaining
                for a in s['growth']['attributes']))
        assert player.state['growth']['attribute_points'] == 0
        self.scenario.report('boss-preparation',
                             f"{'T2' if advanced else 'T1'} 실제 구매/장착·교관 배분·강타 훈련 / "
                             f"Lv.{player.state['level']} HP {player.state['max_hp']}")
        await travel_to(player, 'infirmary')
        await travel_to(player, 'recovery_room')
        await self.rest_if_needed()

    async def rest_if_needed(self):
        player = self.first
        if player.state['hp'] == player.state['max_hp'] and player.state['mental'] == player.state['max_mental']:
            return
        await player.act('침대 휴식', lambda s: s['hp'] == s['max_hp'] and s['mental'] == s['max_mental'])

    async def restart(self):
        self.scenario.phase = "restart"
        player = self.first
        await player.act("귀환", lambda s: s["zone"] == "support_roof")
        await player.act("승강기", lambda s: s["zone"] == "support_elevator")
        await player.act("3층", lambda s: s["zone"] == "support_3f_c")
        await player.act("승강기", lambda s: s["zone"] == "support_elevator")
        # Lv1 검증나도 청소룡을 snapshot subprocess 초기화 중 처치할 수 있다.
        # 실제 이동/교전으로 더 오래 유지되는 전투를 준비하고 아래 DB 전제를 유지한다.
        await route(self.second, (("북", "trail"),))
        await self.second.act("갈퀴사냥룡 공격", lambda s: s["combat_target"] is not None)
        # before: live server의 shutdown 직전 DB. 실제 ON 광원/주무기가 전제다.
        before = await asyncio.to_thread(self.scenario.harness.checkpoint)
        save_restart_snapshot(self.scenario.harness, "before", before)
        assert before["players"][self.second.name]["profile"]["combat_target"] is not None
        assert before["facilities"]["states"]["outpost_power"] and before["loot"]
        live = before["players"][player.name]
        light_id = live["active_light"]
        assert light_id is not None and light_id in live["items"], "live active light 없음"
        light = live["items"][light_id]
        assert ITEMS[light["definition"]].get("light_source") and light["state"]["enabled"]
        assert live["active_weapon"] is not None and live["active_weapon"] in live["items"]
        harness = self.scenario.harness
        harness.restarting = True
        try:
            assert harness.mode == "full"
            harness.check_alive()
            # restart 자체가 정상 AMP 종료·stopped checkpoint·동일 DB 재시작을 수행한다.
            # stopped: 정상 shutdown 완료 후 DB. after: startup + relogin 후 DB.
            stopped = await harness.restart()
            save_restart_snapshot(harness, "stopped", stopped)
        finally:
            harness.restarting = False
        assert_preserved_loot(before, stopped, stopped=stopped, after=stopped, require_decay=False)
        assert before["players"].keys() == stopped["players"].keys()
        for name, saved in before["players"].items():
            settled = stopped["players"][name]
            assert_shutdown_items(saved["items"], settled["items"],
                                  before["observed_at"], stopped["observed_at"])
            assert saved["active_weapon"] == settled["active_weapon"], name
            assert settled["active_light"] is None, name
        settled_light = stopped["players"][player.name]["items"][light_id]["state"]
        self.scenario.report("shutdown-items", f"live light ON/active UUID → OFF/None / "
                             f"power {light['state']['remaining_power']:.3f}→"
                             f"{settled_light['remaining_power']:.3f} (project_power 범위 내) / "
                             "일반 item·tree·주무기 불변")
        await asyncio.gather(*(client.close() for client in self.scenario.players))
        for client in self.scenario.players:
            await client.open()
        after = await asyncio.to_thread(self.scenario.harness.checkpoint)
        save_restart_snapshot(harness, "after", after)
        assert stopped.get("loot_births", {}) == after.get("loot_births", {}), "startup 신규 death"
        assert_preserved_loot(stopped, after, require_decay=False)
        assert stopped["players"].keys() == after["players"].keys()
        preserved = ("xp", "credits", "inventory", "equipment", "storage", "attributes", "skills",
                     "skill_ready_at", "quests", "discoveries", "visited")
        for name, saved in stopped["players"].items():
            restored = after["players"][name]
            assert saved["id"] == restored["id"] and restored["zone"] == "staging_room"
            assert restored["home"] == "dock" and restored["profile"]["combat_target"] is None
            assert_startup_items(saved["items"], restored["items"])
            assert saved["active_weapon"] == restored["active_weapon"], name
            assert restored["active_light"] is None, name
            assert {key: saved["profile"][key] for key in preserved} == {
                key: restored["profile"][key] for key in preserved}, name
        self.scenario.report("startup-items", "stopped → after UUID/quantity/sequence/tree/state 엄격 보존 / "
                             "active_light None / active_weapon 보존 / relogin 성공")
        for name, saved in stopped["players"].items():
            for key in ("hp", "mental"):
                assert after["players"][name]["profile"][key] >= saved["profile"][key]
        assert before["box"] == after["box"] and before["facilities"] == after["facilities"]
        assert before["clock"] == after["clock"]
        assert not after["stale"] and all(not e["combatants"] and not e["claim"] for e in after["enemies"].values())
        assert player.state["party"]["id"] == self.second.state["party"]["id"]
        # 이미 만료한 시체는 ground로, 남은 시체는 실제 callback으로 재예약되어야 한다.
        await travel_to(player, 'hq_concourse')
        await self.floor(player, "3층", "support_3f_c")
        pending_corpses = {identity for identity, loot in stopped["loot"].items() if loot["corpse"]}
        pending_enemies = {identity for identity, enemy in stopped["enemies"].items() if enemy["state"] != "alive"}
        deadline = monotonic() + self.scenario.timings["CORPSE_TTL_SECONDS"] + self.scenario.timings["RESPAWN_DELAY_SECONDS"] + 10
        while True:
            final = await asyncio.to_thread(self.scenario.harness.checkpoint)
            corpses = {identity for identity, loot in final["loot"].items() if loot["corpse"]}
            if not (pending_corpses & corpses) and all(
                final["enemies"][identity]["state"] == "alive" for identity in pending_enemies
            ):
                break
            if monotonic() >= deadline:
                save_restart_snapshot(harness, "final", final)
                raise TimeoutError("restart 후 실제 corpse/respawn callback이 완료되지 않았습니다.")
            await asyncio.sleep(1)  # 실제 DB predicate polling; future reconcile/delay mock 없음
        save_restart_snapshot(harness, "final", final)
        assert after.get("loot_births", {}) == final.get("loot_births", {}), "startup 이후 신규 death"
        assert_preserved_loot(after, final)
        loot_summary = assert_preserved_loot(before, final, stopped=stopped, after=after)
        self.scenario.report("restart-loot", f"native item {loot_summary['items']} / "
                             f"currency {loot_summary['currency']} 보존 / "
                             f"만료 claim 삭제 {loot_summary['expired_claims']}")
        self.scenario.report("restart", "actual Portal+Server / 같은 DB / relogin / profile·party·world 보존 / combat·claim 정리")
