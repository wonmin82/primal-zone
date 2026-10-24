"""50-C 초기 조건만 구성한다. 서버 시작 후 게임 행동을 대체하지 않는다."""

import json
import os
import sys
from time import time

from smoke_setup import setup


def prepare(credentials):
    setup(credentials)
    from evennia import create_object
    from typeclasses.explorers import Explorer
    from typeclasses.loot import Corpse
    from typeclasses.parties import Party
    from world import rules
    from world.item_entities import api
    from world.loot_service import create_claim, create_currency, populate_source

    scenario = os.environ["PRIMAL_INTEGRATION_SCENARIO"]
    from typeclasses.zone_rooms import ZoneRoom
    rooms = {room.db.zone_id: room for room in ZoneRoom.objects.all()}
    players = [Explorer.objects.get(db_key=name) for name, _ in credentials]
    starts = {"E2E-02": "dock", "E2E-03": "weapon_shop", "E2E-04": "infirmary",
              "E2E-05": "dock", "E2E-06": "grass", "E2E-07": "dock",
              "E2E-08": "hq_lounge", "E2E-09": "hq_concourse", "E2E-10": "hq_concourse",
              "E2E-11": "dock", "E2E-12": "hq_lounge", "E2E-13": "dock",
              "TIMING-DOOR": "hq_lounge", "TIMING-PARTY": "dock"}
    for player in players:
        player.location = rooms[starts.get(scenario, "staging_room")]
        p = player.profile()
        p.update(credits=2000, hp=rules.stats(p)["max_hp"], mental=rules.stats(p)["max_mental"])
        player.save_profile(p)
    if scenario == "E2E-02":
        # 이전 탐사에서 보스 처치까지 끝낸 미수락 fixture. 수락/부품 획득/수리/
        # 보고/출입증 재발급은 테스트가 실제 UI로 수행한다. 보스 전투는 E2E-06.
        p = players[0].profile()
        p["quests"]["radio_tower"]["boss_defeated"] = True
        players[0].save_profile(p)
        api.create_item("generator_repair_part", quantity=3, location_kind="inventory", owner_object=players[0])
        p = players[1].profile()
        p["quests"]["radio_tower"].update(started=True, record_read=True, generator_fixed=True, boss_defeated=True, claimed=True)
        players[1].save_profile(p)  # 분실 상태의 출입증은 실제 재발급 명령으로 만든다.
    if scenario == "E2E-04":
        p = players[0].profile()
        p.update(hp=p["hp"] - 20, mental=1)
        players[0].save_profile(p)
    if scenario == "E2E-10":
        from typeclasses.enemies import Enemy
        from world.content import ENEMIES
        from world.equipment_service import equip_item, unequip_item
        for cls, key in [('Commander', '검증대장'), ('Doctor', '검증의무관')]:
            create_object('typeclasses.interactables.'+cls, key=key, location=rooms['hq_concourse'])
        enemy = create_object(Enemy, key='검증사냥룡', location=rooms['hq_concourse'])
        enemy.db.enemy_id = 'hunter'
        enemy.db.hp = enemy.db.max_hp = ENEMIES['hunter']['hp']
        enemy.db.spawn_id = 'integration-combat-fixture'
        body = api.items_in_location('equipment', owner_object=players[0]).get(slot='body')
        unequip_item(players[0], body)
        armor = api.create_item('heavy_protective_suit', location_kind='inventory', owner_object=players[0])
        equip_item(players[0], armor)
    if scenario == 'TIMING-PARTY':
        from typeclasses.loot import DroppedLoot
        party = create_object(Party, key='실시간 승계 검증 일행')
        state = party.state()
        state.update(leader=players[0].pk, members=[p.pk for p in players[:2]], created_at=time())
        party.db.state = state
        for player in players[:2]:
            player.db.party_id = party.pk
        ground = create_object(DroppedLoot, key='승계 권리 fixture', location=rooms['dock'])
        populate_source(ground, [])
        row = api.create_item('bandage', quantity=2, location_kind='world_loot', owner_object=ground)
        create_claim(row, reserved_party=party, assigned_player=players[0], protection_until=time()+1200)
        # 미래 보호 시각의 저장 fixture. 운영60/600초 상수·tick은 그대로다.
    if scenario in ("E2E-07", "E2E-12", "E2E-13"):
        # 공개 회수는 Native A/B 실물을 사용한다. E2E-12만 읽기 전용
        # historical Legacy fixture를 함께 두어 재시작 시 보존을 검증한다.
        # 이 프로세스는 setup()의 marker/DB 검사를 통과한 새 격리 DB만 소유한다.
        from django.conf import settings
        from world.item_entities.models import ItemEntity, ItemRuntime
        settings.ITEM_MIGRATION_AUDIT = True
        if scenario == "E2E-12":
            ItemRuntime.objects.all().delete()
            legacy = players[1]
            ItemEntity.objects.filter(owner_object=legacy).delete()
            legacy.db.equipment_backend = 'legacy'
            legacy.db.active_weapon_item_id = None
            legacy.db.active_light_item_id = None
            p = rules.new_profile()
            p.update(credits=2000)
            legacy.db.profile = p
            # 재시작 비교용 실제 UUID/inside/ground Scope. 시작 후 변경은 공개
            # 명령만 사용한다. Container 기능을 새로 추가하는 fixture가 아니다.
            from typeclasses.loot import DroppedLoot
            parent = api.create_item("bandage", quantity=1, location_kind="inventory", owner_object=players[0])
            api.create_item("water", quantity=3, location_kind="inside", parent_item=parent, socket="supplies")
            ground = create_object(DroppedLoot, key="영속 바닥 fixture", location=rooms["hq_concourse"])
            populate_source(ground, [])
            api.create_item("bandage", quantity=2, location_kind="world_loot", owner_object=ground)
            create_currency(ground, 17, shares={players[0]: 7, players[1]: 10}, protection_until=time()+600)
        party = None
        if scenario == "E2E-07":
            party = create_object(Party, key="통합 검증 일행")
            state = party.state()
            state.update(leader=players[0].pk, members=[p.pk for p in players[:2]], created_at=time())
            party.db.state = state
            for player in players[:2]:
                player.db.party_id = party.pk
        for native in (False, True):
            corpse = create_object(Corpse, key="Legacy 검증 시체" if not native and scenario == "E2E-12" else "Native 검증 시체", location=players[0].location)
            corpse.db.decay_at = time() + 600
            if native:
                populate_source(corpse, [])
                row = api.create_item("bandage", quantity=2, location_kind="corpse_loot", owner_object=corpse)
                create_claim(row, reserved_player=players[0] if not party else None, reserved_party=party,
                             assigned_player=players[0], protection_until=time() + 300)
                create_currency(corpse, 20, shares={players[0]: 6, players[1]: 14},
                                reserved_party=party, protection_until=time()+300)
            elif scenario == "E2E-12":
                corpse.db.entries = [{"kind": "item", "id": "water", "quantity": 1,
                                      "assigned_player": players[1].pk, "reserved_player": players[1].pk if not party else None,
                                      "reserved_party": party.pk if party else None, "protection_until": time() + 300}]
            else:
                populate_source(corpse, [])
                row = api.create_item("water", quantity=1, location_kind="corpse_loot", owner_object=corpse)
                create_claim(row, reserved_player=players[1] if not party else None, reserved_party=party,
                             assigned_player=players[1], protection_until=time() + 300)


    if scenario == "E2E-12":
        # 이 경합을 커밋한 바로 이 DB를 서버가 열고 정상 복원/재시작한다.
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from django.db import connections
        from evennia.objects.objects import DefaultRoom
        from world.multiplayer import world_change
        from world.selection_numbers.api import descriptor, number_for
        from world.selection_numbers.models import NumberScope

        race_room = create_object(DefaultRoom, key="Phase3 경합 방")

        def create_corpse():
            return create_object(Corpse, key="영속 경합 시체", location=race_room,
                                 attributes=[("decay_at", time() + 600)])

        original = create_corpse()
        original_ref = descriptor(original).reference
        shared = connections["default"]
        shared.inc_thread_sharing()
        barrier = Barrier(2)

        def create_after_barrier(remove):
            connections["default"] = shared
            barrier.wait(timeout=10)
            with world_change():
                if remove:
                    original.delete()
                result = create_corpse()
            return descriptor(result).reference

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(create_after_barrier, True)
                second = pool.submit(create_after_barrier, False)
                references = (first.result(timeout=20), second.result(timeout=20))
        finally:
            shared.dec_thread_sharing()
        assert number_for(original_ref) is None
        assert sorted(number_for(ref) for ref in references) == [2, 3]
        scope = NumberScope.objects.get(scope_id=f"room:{race_room.pk}", group_id="world:corpse")
        assert scope.next_number == 4
        race_room.db.phase3_race = {"removed": original_ref.identity,
                                   "survivors": [ref.identity for ref in references],
                                   "scope": scope.pk, "next_number": 4}


if __name__ == "__main__":
    prepare(json.load(sys.stdin))
