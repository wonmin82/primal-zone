"""Full 전용 본부·현재 두 임무·실제 restart 연결 검증. Quick 경로는 확장하지 않는다."""

import asyncio
import subprocess
import sys
from time import monotonic

from smoke import count_item, route, travel_to
from world.content import ITEMS
from world.lighting import project_power


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


def stop_for_restart(harness):
    """Full 전용: 격리 Portal의 정상 종료를 요청하고 owned process exit를 확인한다."""
    from smoke_harness import SHUTDOWN_TIMEOUT

    assert harness.mode == "full"
    harness.check_alive()
    with (harness.run_dir / "restart-stop.log").open("w", encoding="utf-8") as log:
        subprocess.run([sys.executable, "-m", "evennia", "stop", "--settings", "settings_smoke"],
                       cwd=harness.run_dir / "game", env=harness.env, stdout=log,
                       stderr=subprocess.STDOUT, timeout=SHUTDOWN_TIMEOUT, check=True)
    for name, process in harness.processes:
        assert process.wait(timeout=SHUTDOWN_TIMEOUT) == 0, (name, "정상 shutdown 실패")


class Closeout:
    def __init__(self, scenario):
        self.scenario = scenario
        self.first, self.second, self.outsider = scenario.players

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
                await player.act("붕대 사용")
            elif state["mental"] >= 8 and state["heavy_ready"]:
                await player.act("강타")
            elif enemy.get('telegraph') and state['mental'] >= 6:
                await player.act('견제')
            await player.until(lambda s: s["combat_target"] is None or s["player_round"] > turn,
                               self.scenario.timeouts.combat)
        assert player.state["xp"] > xp and player.state["zone"] != "infirmary"

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
        await player.act("의무관 진료", lambda s: s["hp"] == s["max_hp"])
        self.scenario.phase = "defeat"
        outsider = self.outsider
        await route(outsider, (("북", "trail"),))
        before = outsider.state["credits"]
        await outsider.act("갈퀴사냥룡 공격", lambda s: s["combat_target"] is not None)
        await outsider.until(lambda s: s["zone"] == "infirmary" and s["combat_target"] is None,
                             self.scenario.timeouts.combat)
        assert outsider.state["hp"] == 1 and outsider.state["credits"] == before - min(before, 10)
        await outsider.act("침대 휴식", lambda s: s["hp"] == s["max_hp"] and s["mental"] == s["max_mental"])
        self.scenario.report("defeat", "actual enemy → infirmary / HP 1 / 최대 10칩 / Bed HP·정신력 full")
        self.scenario.phase = "hq-closeout"
        await player.act("귀환", lambda s: s["zone"] == "support_roof")
        await self.floor(player, "1층", "hq_concourse")
        await travel_to(player, 'supply_shop')
        for command, item in (("붕대 구매", "bandage"), ("탐사용손전등 구매", "flashlight"), ("건전지 구매", "battery")):
            before = count_item(player.state, item)
            await player.act(command, lambda s, item=item, before=before: count_item(s, item) == before + 1)
        await player.expect_text("탐사용손전등에 건전지 넣어", "넣")
        await player.act("탐사용손전등 켜")
        await travel_to(player, 'hq_concourse')
        await self.floor(player, "5층", "support_5f_c")
        await travel_to(player, 'armor_shop')
        await player.act("강화방호조끼 구매", lambda s: count_item(s, "reinforced_vest") == 1)
        # 격리 smoke fixture는 준비 단계에서 기본 손 무기를 명시 해제한다.
        assert player.state["equipment"]["hands"] is None
        await player.act("절단마체테 무장", lambda s: s["equipment"]["hands"] == "절단마체테 [주무기]")
        await player.act("탐사대 작업복 벗어", lambda s: s["equipment"]["body"] is None)
        await player.act("강화방호조끼 착용", lambda s: s["equipment"]["body"] == "강화방호조끼")
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
            await player.act('침대 휴식', lambda s: s['hp'] == s['max_hp'] and s['mental'] == s['max_mental'])
        self.scenario.report('expedition-recovery', '연속 사냥 후 실제 3층 침대 회복 / 전투 수치·fixture 변경 없음')
        await self.dock(player)
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh")))
        await self.kill('갈퀴사냥룡')
        await player.act('시체에서 모두 가져')
        await self.kill('고장난경비기')
        await player.act('시체에서 모두 가져')
        assert player.state['level'] >= 4
        await self.prepare_boss()
        await self.dock(player)
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh"), ("북", "ridge")))
        await self.kill("능선의우두머리")
        await player.act('시체에서 모두 가져')
        await player.expect_text("북", "보고")
        await self.dock(player)
        await player.act("윤대장 대화", lambda s: "선발대 길잡이" in s["quest"])
        self.scenario.report("quest", "정비기록/부품 3개 수리/첫 gate/alpha/윤대장 보고")
        await self.prepare_boss(advanced=True)
        await self.dock(player)
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh"),
                             ("북", "ridge"), ("북", "jungle_edge")))
        await player.act("선발대 길잡이 대화", lambda s: "관측소" in s["quest"])
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
        await player.act("선발대 길잡이 대화", lambda s: s["quest"] == "깊은 밀림 조사를 마쳤습니다.")
        self.scenario.report("progression", "두 표식/신호전지/두 번째 gate/jungle apex/최종 보고 완료")
        await self.dock(player)
        await travel_to(player, 'hq_concourse')
        await self.floor(player, "4층", "support_4f_c")
        await travel_to(player, 'training_room')
        rank = next(skill["rank"] for skill in player.state["growth"]["skills"] if skill["id"] == "heavy")
        await player.act("타격교관에게 강타 배워", lambda s: any(skill["id"] == "heavy" and skill["rank"] == rank + 1 for skill in s["growth"]["skills"]))
        self.scenario.report("training", "Lv.1 훈련 없음 / 실제 임무 XP 이후 NPC Rank +1 / 무료")

    async def prepare_boss(self, advanced=False):
        player = self.first
        await player.act('귀환', lambda s: s['zone'] == 'support_roof')
        await self.floor(player, '5층', 'support_5f_c')
        await travel_to(player, 'weapon_shop')
        if not count_item(player.state, 'folding_shield'):
            await player.act('접이식방패 구매', lambda s: count_item(s, 'folding_shield') == 1)
            await player.act('접이식방패 착용', lambda s: '접이식방패' in s['equipment']['hands'])
        if advanced:
            # 첫 보고의 실제 출입증으로 열린 전초 병기고에서 T2를 구매한다.
            await travel_to(player, 'outpost_weapon')
            await player.act('정글장도 구매', lambda s: count_item(s, 'jungle_longblade') == 1)
            await player.act('절단마체테 해제', lambda s: '절단마체테' not in s['equipment']['hands'])
            await player.act('정글장도 무장', lambda s: '정글장도 [주무기]' in s['equipment']['hands'])
        if advanced:
            await player.act('귀환', lambda s: s['zone'] == 'support_roof')
            await self.floor(player, '5층', 'support_5f_c')
            await travel_to(player, 'outpost_equipment')
            await player.act('강화방호조끼 벗어', lambda s: s['equipment']['body'] is None)
            await player.act('강화방호조끼 판매', lambda s: count_item(s, 'reinforced_vest') == 0)
            await player.act('전술방호복 구매', lambda s: count_item(s, 'tactical_protective_suit') == 1)
            await player.act('전술방호복 착용', lambda s: s['equipment']['body'] == '전술방호복')
        else:
            await travel_to(player, 'armor_shop')
            boots = count_item(player.state, 'non_slip_boots')
            await player.act('미끄럼방지탐사화 구매', lambda s: count_item(s, 'non_slip_boots') == boots + 1)
            await player.act('미끄럼방지탐사화 착용', lambda s: s['equipment']['feet'] == '미끄럼방지탐사화')
        if count_item(player.state, 'expedition_tag') and not player.state['equipment']['neck']:
            await player.act('탐사인식표 착용', lambda s: s['equipment']['neck'] == '탐사인식표')
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
            await player.act('붕대 구매', lambda s: count_item(s, 'bandage') == before + 1)
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
            # Windows terminate는 callback을 건너뛴다. 실제 at_server_shutdown을 거친다.
            await asyncio.to_thread(stop_for_restart, harness)
            # stopped: 정상 shutdown 완료 후 DB. after: startup + relogin 후 DB.
            stopped = await harness.restart()
        finally:
            harness.restarting = False
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
        assert before["clock"] == after["clock"] and before["elevator"] == after["elevator"] == "3f"
        assert not after["stale"] and all(not e["combatants"] and not e["claim"] for e in after["enemies"].values())
        assert player.state["party"]["id"] == self.second.state["party"]["id"]
        # 이미 만료한 시체는 ground로, 남은 시체는 실제 callback으로 재예약되어야 한다.
        await travel_to(player, 'hq_concourse')
        await self.floor(player, "3층", "support_3f_c")
        old_entries = [entry for loot in before["loot"].values() for entry in loot["entries"]]
        pending_corpses = {identity for identity, loot in before["loot"].items() if loot["corpse"]}
        pending_enemies = {identity for identity, enemy in before["enemies"].items() if enemy["state"] != "alive"}
        deadline = monotonic() + self.scenario.timings["CORPSE_TTL_SECONDS"] + self.scenario.timings["RESPAWN_DELAY_SECONDS"] + 10
        while True:
            final = await asyncio.to_thread(self.scenario.harness.checkpoint)
            corpses = {identity for identity, loot in final["loot"].items() if loot["corpse"]}
            if not (pending_corpses & corpses) and all(
                final["enemies"][identity]["state"] == "alive" for identity in pending_enemies
            ):
                break
            if monotonic() >= deadline:
                raise TimeoutError("restart 후 실제 corpse/respawn callback이 완료되지 않았습니다.")
            await asyncio.sleep(1)  # 실제 DB predicate polling; future reconcile/delay mock 없음
        assert all(entry in [e for loot in final["loot"].values() for e in loot["entries"]] for entry in old_entries)
        self.scenario.report("restart", "actual Portal+Server / 같은 DB / relogin / profile·party·world 보존 / combat·claim 정리")
