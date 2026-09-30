"""Full 전용 본부·현재 두 임무·실제 restart 연결 검증. Quick 경로는 확장하지 않는다."""

import asyncio
from time import monotonic

from smoke import count_item, route


class Closeout:
    def __init__(self, scenario):
        self.scenario = scenario
        self.first, self.second, self.outsider = scenario.players

    async def floor(self, player, stop, zone):
        await player.act("승강기", lambda s: s["zone"] == "support_elevator")
        await player.act(stop, lambda s: s["zone"] == zone)

    async def dock(self, player):
        await player.act("귀환", lambda s: s["zone"] == "support_roof")
        await self.floor(player, "1층", "support_1f_c")
        await route(player, (("북", "hq_concourse"), ("서", "dock")))

    async def kill(self, enemy_name):
        player = self.first
        xp = player.state["xp"]
        await player.act(enemy_name + " 공격", lambda s: s["combat_target"] is not None)
        await player.until(lambda s: s["combat_target"] is None and s["xp"] > xp,
                           self.scenario.timeouts.combat)

    async def run(self):
        self.scenario.phase = "hq-closeout"
        player = self.first
        await self.dock(player)
        await route(player, (("동", "hq_concourse"), ("남", "support_1f_c"),
                             ("서", "support_1f_w1"), ("북", "storage_room")))
        for name in ("보관상자", "개인 보관함"):
            before = count_item(player.state, "bandage")
            await player.act(name + "에 붕대 넣어", lambda s: count_item(s, "bandage") == before - 1)
            await player.act(name + "에서 붕대 꺼내", lambda s: count_item(s, "bandage") == before)
            await player.act(name + "에 붕대 넣어", lambda s: count_item(s, "bandage") == before - 1)
        await route(player, (("남", "support_1f_w1"), ("서", "support_1f_w2"), ("북", "salvage_office")))
        await player.expect_text("정산관 환율", "10크레딧")
        before = player.state["credits"]
        await player.act("정산관에게 회수부품 7개 교환", lambda s: s["credits"] == before + 70)
        assert count_item(player.state, "scrap") == 3
        await route(player, (("남", "support_1f_w2"), ("동", "support_1f_w1"), ("동", "support_1f_c")))
        await self.floor(player, "2층", "support_2f_c")
        await route(player, (("동", "support_2f_e1"), ("북", "training_room")))
        assert player.state["training_available"]
        await player.act("강타 배워", lambda s: any(skill["id"] == "heavy" and skill["rank"] == 2
                                                  for skill in s["growth"]["skills"]))
        await route(player, (("남", "support_2f_e1"), ("서", "support_2f_c"),
                             ("서", "support_2f_w1"), ("북", "infirmary")))
        await player.act("의무관 진료", lambda s: s["hp"] == s["max_hp"])
        self.scenario.phase = "defeat"
        outsider = self.outsider
        before = outsider.state["credits"]
        await outsider.act("어린청소룡 공격", lambda s: s["combat_target"] is not None)
        await outsider.until(lambda s: s["zone"] == "infirmary" and s["combat_target"] is None,
                             self.scenario.timeouts.combat)
        assert outsider.state["hp"] == 1 and outsider.state["credits"] == before - min(before, 10)
        await outsider.act("침대 휴식", lambda s: s["hp"] == s["max_hp"])
        self.scenario.report("defeat", "actual enemy → infirmary / HP 1 / 최대 10C / Bed full heal")
        self.scenario.phase = "hq-closeout"
        await player.act("귀환", lambda s: s["zone"] == "support_roof")
        await self.floor(player, "1층", "support_1f_c")
        await route(player, (("동", "support_1f_e1"), ("북", "supply_shop")))
        for command, item in (("붕대 구매", "bandage"), ("탐사용손전등 구매", "flashlight"), ("건전지 구매", "battery")):
            before = count_item(player.state, item)
            await player.act(command, lambda s, item=item, before=before: count_item(s, item) == before + 1)
        await player.expect_text("탐사용손전등에 건전지 넣어", "넣")
        await player.act("탐사용손전등 켜")
        await route(player, (("남", "support_1f_e1"), ("서", "support_1f_c")))
        await self.floor(player, "3층", "support_3f_c")
        await route(player, (("서", "support_3f_w1"), ("북", "armor_shop")))
        await player.act("강화조끼 구매", lambda s: count_item(s, "armor") == 1)
        await player.act("강철마체테 무장", lambda s: s["equipment"]["weapon"] == "강철마체테")
        await player.act("강화조끼 착용", lambda s: s["equipment"]["armor"] == "강화조끼")
        self.scenario.report("hq", "보관/정산/훈련/Doctor/Bed/귀환/승강기/3종 상점 실제 연결")
        await self.progression()
        await self.restart()

    async def progression(self):
        self.scenario.phase = "progression"
        player = self.first
        await self.dock(player)
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh")))
        await player.expect_text("북", "발전기")
        await route(player, (("남", "trail"), ("동", "office")))
        await player.act("정비기록 조사", lambda s: "발전기 수리" in s["quest"])
        await route(player, (("동", "generator"),))
        await player.act("발전기 수리", lambda s: count_item(s, "scrap") == 0)
        await route(player, (("서", "office"), ("서", "trail"), ("북", "marsh"), ("북", "ridge")))
        await self.kill("능선의우두머리")
        await player.expect_text("북", "보고")
        await self.dock(player)
        await player.act("윤대장 대화", lambda s: "선발대 길잡이" in s["quest"])
        self.scenario.report("quest", "정비기록/부품 3개 수리/첫 gate/alpha/윤대장 보고")
        await route(player, (("북", "grass"), ("북", "trail"), ("북", "marsh"),
                             ("북", "ridge"), ("북", "jungle_edge")))
        await player.act("선발대 길잡이 대화", lambda s: "관측소" in s["quest"])
        await route(player, (("북", "jungle_watch"),))
        await player.act("관측 표식 조사", lambda s: "수위 표식" in s["quest"])
        await route(player, (("남", "jungle_edge"), ("동", "jungle_road")))
        await player.act("수위 표식 조사", lambda s: count_item(s, "jungle_cell") == 1)
        await route(player, (("북", "jungle_grove"),))
        await player.expect_text("북", "닫혀")
        await player.act("신호 장치 조사", lambda s: count_item(s, "jungle_cell") == 0)
        await route(player, (("북", "jungle_gate"), ("북", "jungle_nest")))
        await self.kill("밀림의포식자")
        await route(player, (("남", "jungle_gate"), ("남", "jungle_grove"),
                             ("남", "jungle_road"), ("서", "jungle_edge")))
        await player.act("선발대 길잡이 대화", lambda s: s["quest"] == "깊은 밀림 조사를 마쳤습니다.")
        self.scenario.report("progression", "두 표식/신호전지/두 번째 gate/jungle apex/최종 보고 완료")

    async def restart(self):
        self.scenario.phase = "restart"
        player = self.first
        await player.act("귀환", lambda s: s["zone"] == "support_roof")
        await player.act("승강기", lambda s: s["zone"] == "support_elevator")
        await player.act("3층", lambda s: s["zone"] == "support_3f_c")
        await player.act("승강기", lambda s: s["zone"] == "support_elevator")
        await self.second.act("어린청소룡 공격", lambda s: s["combat_target"] is not None)
        before = await asyncio.to_thread(self.scenario.harness.checkpoint)
        assert before["players"][self.second.name]["profile"]["combat_target"] is not None
        assert before["facilities"]["states"]["outpost_power"] and before["loot"]
        await self.scenario.harness.restart()
        await asyncio.gather(*(client.close() for client in self.scenario.players))
        for client in self.scenario.players:
            await client.open()
        after = await asyncio.to_thread(self.scenario.harness.checkpoint)
        preserved = ("xp", "credits", "inventory", "equipment", "storage", "attributes", "skills",
                     "proficiencies", "quests", "discoveries", "visited")
        for name, saved in before["players"].items():
            restored = after["players"][name]
            assert saved["id"] == restored["id"] and restored["zone"] == "staging_room"
            assert restored["home"] == "dock" and restored["profile"]["combat_target"] is None
            assert {key: saved["profile"][key] for key in preserved} == {
                key: restored["profile"][key] for key in preserved}
        assert after["players"][player.name]["profile"]["hp"] == before["players"][player.name]["profile"]["hp"]
        assert before["box"] == after["box"] and before["facilities"] == after["facilities"]
        assert before["clock"] == after["clock"] and before["elevator"] == after["elevator"] == "3f"
        assert not after["stale"] and all(not e["combatants"] and not e["claim"] for e in after["enemies"].values())
        assert player.state["party"]["id"] == self.second.state["party"]["id"]
        # 이미 만료한 시체는 ground로, 남은 시체는 실제 callback으로 재예약되어야 한다.
        await route(player, (("남", "hq_concourse"), ("남", "support_1f_c")))
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
