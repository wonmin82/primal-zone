"""Empty SQLite → supported register → 실제 gameplay → 정상 restart/relogin.

Migration command와 기존 DB 복사는 사용하지 않는다. 준비금만 grind를 단축한다.
실제 수리/전투/보고/출입증/ItemEntity는 모두 정상 서버 명령으로 만든다.
"""

import asyncio
import json
import shutil
import subprocess
import sys
from time import monotonic

from smoke import AUTH_TIMEOUT, STATE_TIMEOUT, Client, Scenario, count_item, route
from smoke_closeout import Closeout, stop_for_restart
from smoke_harness import ROOT, Harness, fingerprint
from websockets.asyncio.client import connect


class FreshClient(Client):
    registered = False

    async def open(self):
        if self.registered:
            return await super().open()
        self.state, self.error, self.closing = None, None, False
        self.connected.clear()
        self.socket = await connect(self.url, subprotocols=["v1.evennia.com"], open_timeout=AUTH_TIMEOUT)
        self.reader = asyncio.create_task(self.receive())
        async with asyncio.timeout(AUTH_TIMEOUT):
            await self.connected.wait()
        await self.send("pz_auth", [{"mode": "register", "username": self.name, "password": self.password}])
        await self.until(lambda s: s["name"] == self.name, AUTH_TIMEOUT)
        self.registered = True
        return self.state

    async def act(self, text, predicate=lambda state: True, timeout=STATE_TIMEOUT):
        try:
            return await super().act(text, predicate, timeout)
        except TimeoutError as error:
            observed = []
            while not self.messages.empty():
                observed = (observed + [self.messages.get_nowait()])[-5:]
            raise AssertionError((text, self.summary(), observed)) from error


class FreshCloseout(Closeout):
    def __init__(self, scenario):
        self.scenario = scenario
        self.first, self.second = scenario.players
        # Fresh는 공개 가입 제한을 유지한다. 재사용하는 progression/restart에
        # outsider fixture는 필요하지 않으며 다른 Closeout 시나리오는 호출하지 않는다.
        self.outsider = None


def fixture(harness, action):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/phase7c_fresh_fixture.py"), action],
                            cwd=harness.run_dir / "game", env=harness.env, capture_output=True,
                            text=True, encoding="utf-8", timeout=120, check=True)
    return json.loads(result.stdout.splitlines()[-1])


def evidence(harness, name, value):
    (harness.run_dir / (name + "-evidence.json")).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class FreshScenario(Scenario):
    def __init__(self, harness, log):
        super().__init__(harness, log)
        # 실제 공개 가입 제한(같은 IP에서 10분당 2개)을 유지한다. fresh 검증에는
        # 두 일반 계정이면 충분하며 세 번째 fixture 계정을 우회 생성하지 않는다.
        self.players = [FreshClient(name, password, harness.ws_url) for name, password in harness.credentials[:2]]

    async def run(self):
        closeout = FreshCloseout(self)
        first, second = self.players
        try:
            boot = await asyncio.to_thread(fixture, self.harness, "inspect")
            assert boot["runtime"][0]["version"] == 1 and boot["ledger_count"] == 0
            assert boot["accounts"] == ["admin"]
            evidence(self.harness, "first-boot", boot)
            self.report("fresh-first-boot", "schema → 실제 first Server initialization / native runtime 1 / ledger 0 / 일반 계정 0")
            for player in self.players:
                await player.open()
                assert player.state["zone"] == "staging_room" and player.state["credits"] == 20
                assert player.state["xp"] == 0 and player.state["max_hp"] == 60
                assert count_item(player.state, "bandage") == 3
            starter = await asyncio.to_thread(fixture, self.harness, "inspect")
            for player in self.players:
                saved = starter["players"][player.name]
                assert saved["runtime_version"] == 1 and all(v is None for v in saved["legacy"].values())
                gear = {i["definition_id"]: i for i in saved["items"]}
                assert set(gear) == {"explorer_machete", "expedition_workwear", "bandage"}
                for identity, slot in (("explorer_machete", "hands"), ("expedition_workwear", "body")):
                    item = gear[identity]
                    assert item["quantity"] == 1 and item["location_kind"] == "equipment" and item["slot"] == slot
                    assert item["sequence"] > 0 and item["owner_object_id"] == saved["id"]
                assert gear["bandage"]["quantity"] == 3 and gear["bandage"]["location_kind"] == "inventory"
            evidence(self.harness, "registered-starters", starter)
            self.report("fresh-register", "실제 pz_auth register 2계정 / 정상 Explorer / starter UUID·sequence·owner·equipment / legacy blob 없음")
            # 외부 fixture write는 정상 offline 경계에서만 한다. live Attribute cache와
            # DB가 갈라지지 않게 종료 후 칩만 지급하고 정상 login으로 다시 읽는다.
            harness = self.harness
            harness.restarting = True
            try:
                await asyncio.gather(*(p.close() for p in self.players))
                await asyncio.to_thread(stop_for_restart, harness)
                evidence(harness, "grind-funding", await asyncio.to_thread(fixture, harness, "fund"))
                await harness.restart()
                for player in self.players:
                    await player.open()
            finally:
                harness.restarting = False
            await first.act("상태", lambda s: s["credits"] == 920)
            for player in self.players:
                for command in ("소지품", "장비", "상태"):
                    await player.act(command)
                await route(player, (("남", "hq_concourse"), ("서", "dock")))
            await first.act("윤대장 대화", lambda s: "정비기록" in s["quest"])
            await first.act(second.name + " 파티초대", lambda s: s["party"] is not None)
            await second.until(lambda s: s["invitation"] is not None)
            await second.act("파티수락", lambda s: s["party"] is not None)
            await route(second, (("북", "grass"),))
            await first.act("귀환", lambda s: s["zone"] == "support_roof")
            await closeout.floor(first, "1층", "support_1f_c")
            await route(first, (("서", "support_1f_w1"), ("북", "storage_room")))
            for name in ("개인 보관함", "보관상자"):
                before = count_item(first.state, "bandage")
                await first.act(name + "에 붕대 넣어", lambda s: count_item(s, "bandage") == before - 1)
                await first.act(name + "에서 붕대 꺼내", lambda s: count_item(s, "bandage") == before)
                await first.act(name + "에 붕대 넣어", lambda s: count_item(s, "bandage") == before - 1)
            self.report("fresh-storage", "정상 personal/shared 입출고 / 각 1개를 남겨 restart 보존 검사")
            await route(first, (("남", "support_1f_w1"), ("동", "support_1f_c"), ("동", "support_1f_e1"), ("북", "supply_shop")))
            await first.expect_text("상품", "35칩")
            for command, item in (("탐사용손전등 구매", "flashlight"), ("건전지 구매", "battery")):
                before = count_item(first.state, item)
                await first.act(command, lambda s, item=item, before=before: count_item(s, item) == before + 1)
            await first.expect_text("탐사용손전등에 건전지 넣어", "넣")
            await first.act("탐사용손전등 켜")
            await first.act("탐사용손전등 꺼")
            await first.act("탐사용손전등 켜")
            self.report("fresh-light", "실제 구매·battery 삽입·ON/OFF/ON")
            await route(first, (("남", "support_1f_e1"), ("서", "support_1f_c")))
            await closeout.floor(first, "2층", "support_2f_c")
            await route(first, (("서", "support_2f_w1"), ("북", "infirmary")))
            await first.act("체질 4 배분", lambda s: s["max_hp"] == 76)
            await first.act("침대 휴식", lambda s: s["hp"] == s["max_hp"])
            await first.act("귀환", lambda s: s["zone"] == "support_roof")
            await closeout.floor(first, "3층", "support_3f_c")
            await route(first, (("동", "support_3f_e1"), ("북", "weapon_shop")))
            await first.act("탐사용 벌목도 해제", lambda s: s["equipment"]["hands"] is None)
            for name, identity in (("경비카빈", "guard_carbine"), ("카빈표준", "mag_556_standard"), ("카빈탄", "ammo_556"), ("절단마체테", "cutting_machete")):
                await first.act(name + " 구매", lambda s, identity=identity: count_item(s, identity) > 0)
            self.report("fresh-firearm-buy", "실제 package와 spare magazine·20발 bundle 구매")
            purchased = await asyncio.to_thread(fixture, self.harness, "inspect")
            owned = purchased["players"][first.name]["items"]
            gun = next(i for i in owned if i["definition_id"] == "guard_carbine")
            loaded = next(i for i in owned if i["parent_item_id"] == gun["id"])
            assert loaded["definition_id"] == "mag_556_standard" and loaded["state"]["rounds"] == 20
            evidence(self.harness, "full-package", purchased)
            await first.expect_text("경비카빈에서 탄창 꺼내", "탄창을 꺼냈다")
            await first.expect_text("카빈표준 1에서 카빈탄 꺼내", "20발")
            await first.expect_text("카빈표준 1 채워", "20발")
            await first.expect_text("카빈표준 2 채워", "20발")
            await first.expect_text("경비카빈에 카빈표준 1 장전", "장전")
            await first.act("경비카빈 무장", lambda s: "경비카빈" in s["equipment"]["hands"])
            await closeout.dock(first)
            await route(first, (("북", "grass"),))
            await first.act("어린청소룡 공격", lambda s: s["combat_target"] is not None)
            await first.until(lambda s: s["combat_target"] is None and s["xp"] > 0, self.timeouts.combat)
            await first.act("시체에서 모두 가져")
            fired = await asyncio.to_thread(fixture, self.harness, "inspect")
            fired_mag = next(i for i in fired["players"][first.name]["items"] if i["id"] == loaded["id"])
            assert 0 < fired_mag["state"]["rounds"] < 20
            evidence(self.harness, "shot-consumption", fired)
            await first.expect_text("경비카빈 재장전", "재장전했다")
            await first.act("경비카빈 해제", lambda s: s["equipment"]["hands"] is None)
            await first.act("절단마체테 무장", lambda s: "절단마체테" in s["equipment"]["hands"])
            self.report("fresh-firearm", "탄창 분리·loose 회수·채움·장전·실제 발사·재장전 / corpse currency 회수")
            await first.act("귀환", lambda s: s["zone"] == "support_roof")
            await closeout.floor(first, "3층", "support_3f_c")
            await route(first, (("서", "support_3f_w1"), ("북", "armor_shop")))
            await first.act("강화방호조끼 구매", lambda s: count_item(s, "reinforced_vest") == 1)
            await first.act("탐사대 작업복 벗어", lambda s: s["equipment"]["body"] is None)
            await first.act("강화방호조끼 착용", lambda s: s["equipment"]["body"] == "강화방호조끼")
            await first.act("탐사대 작업복 판매", lambda s: count_item(s, "expedition_workwear") == 0)
            # 실제 첫 청소룡 XP22는 아직 Lv1이다. 초기 준비에서 Rank2를 요구하지
            # 않고 progression의 실제 XP 이후 기존 prepare_boss가 훈련한다.
            await closeout.restock_boss(target_rank=1)
            await closeout.progression()
            completed = await asyncio.to_thread(fixture, self.harness, "inspect")
            definitions = {i["definition_id"] for i in completed["players"][first.name]["items"]}
            assert {"outpost_supply_pass", "special_supply_pass", "ridge_predator_mark", "predator_scale_charm"} <= definitions
            assert completed["ledger_count"] == 0
            evidence(self.harness, "gameplay-completed", completed)
            self.report("fresh-reports", "두 실제 보스·보고·고유 보상·Credential / 전초 접근 / migration ledger 0")
            await closeout.restart()
            final = await asyncio.to_thread(fixture, self.harness, "inspect")
            assert final["runtime"][0]["version"] == 1 and final["ledger_count"] == 0
            evidence(self.harness, "final", final)
        finally:
            await asyncio.gather(*(p.close() for p in self.players), return_exceptions=True)


async def main():
    harness = Harness("full")
    before = fingerprint(ROOT / "game/server/evennia.db3")
    started, success = monotonic(), False
    destination = ROOT / "work/phase7c/fresh-evidence"
    try:
        await asyncio.to_thread(harness.prepare, ROOT / "scripts/phase7c_fresh_setup.py")
        schema = await asyncio.to_thread(fixture, harness, "inspect")
        assert schema["runtime"] == [] and schema["ledger_count"] == 0 and not schema["players"]
        evidence(harness, "schema-only", schema)
        harness.start()
        await harness.ready()
        with (harness.run_dir / "fresh.log").open("w", encoding="utf-8") as log:
            await harness.supervise(FreshScenario(harness, log).run())
        success = True
    finally:
        await asyncio.to_thread(harness.stop)
        after = fingerprint(ROOT / "game/server/evennia.db3")
        assert before == after, "기존 개발 DB가 변경되었습니다."
        if harness.run_dir:
            destination = destination / harness.run_dir.name
            destination.mkdir(parents=True, exist_ok=True)
            for pattern in ("*-evidence.json", "fresh.log", "restart-stop.log"):
                for path in harness.run_dir.glob(pattern):
                    shutil.copy2(path, destination / path.name)
            evidence(harness, "run", {"success": success, "seconds": round(monotonic() - started, 3),
                                      "db_before": before, "db_after": after, "migration_commands_used": False,
                                      "run_dir": str(harness.run_dir)})
            shutil.copy2(harness.run_dir / "run-evidence.json", destination / "run-evidence.json")
            print(json.dumps({"success": success, "evidence": str(destination),
                              "seconds": round(monotonic() - started, 3)}, ensure_ascii=False), flush=True)
            if success:
                harness.discard()


if __name__ == "__main__":
    asyncio.run(main())
