"""Phase 7B 격리 fixture와 read-only 증거. 실제 개발 DB에서는 실행할 수 없다."""

import argparse
import json
from copy import deepcopy
from time import time

FIXTURE_NAMES = ("검증가", "검증나", "검증다", "검증라")

def initialize():
    from django.conf import settings
    from server.conf.smoke_support import require_smoke

    require_smoke(settings)
    import django

    django.setup()
    import evennia

    evennia._init()


def inspect():
    from evennia.utils.dbserialize import deserialize
    from typeclasses.enemies import Enemy
    from typeclasses.explorers import Explorer
    from world.item_entities.models import ItemMigrationLedger, ItemRuntime, ItemSequence
    from world.item_migration.scan import json_state, raw_source, sources

    return {
        "label": "TEST / LEGACY CORPUS",
        "runtime": list(ItemRuntime.objects.values()),
        "sequence": ItemSequence.objects.get(pk=1).last_value,
        "ledger": list(ItemMigrationLedger.objects.order_by("source_identity").values()),
        "sources": {f"{kind}:{obj.pk}": {"key": obj.key, "raw": raw_source(kind, obj), "native": json_state(obj)}
                    for kind, obj in sources()},
        "players": {obj.key: {"id": obj.pk, "profile": deserialize(obj.db.profile),
                              "native": json_state(obj), "zone": obj.zone}
                    for obj in Explorer.objects.all() if obj.key != "admin"},
        "enemies": {obj.key: {"id": obj.pk, "enemy": obj.db.enemy_id, "hp": obj.db.hp,
                               "max_hp": obj.db.max_hp, "state": obj.db.state,
                               "participants": obj.db.scaling_participants,
                               "combatants": list(obj.db.combatants or []),
                               "contribution": deserialize(obj.db.contribution)} for obj in Enemy.objects.all()},
    }


def prepare_live():
    from typeclasses.explorers import Explorer
    from world import rules

    for player in Explorer.objects.filter(db_key__in=FIXTURE_NAMES):
        profile = player.profile()
        # 준비만 fixture에서 수행한다. 거래/전투/소각/접근 결과는 실제 명령으로 만든다.
        profile["credits"] = 3000
        profile["attributes"]["constitution"]["allocated"] = 20
        profile["hp"] = rules.stats(profile)["max_hp"]
        profile["mental"] = rules.stats(profile)["max_mental"]
        player.save_profile(profile)
    return {"label": "TEST / PHASE 7B", "players": 4}


def prepare_boss():
    from evennia import create_object
    from typeclasses.enemies import Enemy
    from typeclasses.explorers import Explorer
    from world import rules
    from world.bootstrap import get_room
    from world.content import ENEMIES
    from world.item_entities import api
    from world.item_entities.models import ItemEntity

    room = get_room("ridge")
    for player in Explorer.objects.filter(db_key__in=FIXTURE_NAMES):
        player.location = room
        for item in list(ItemEntity.objects.filter(owner_object=player, location_kind="equipment")):
            api.delete_item(item)
        api.create_item("jungle_longblade", owner_object=player, location_kind="equipment", slot="hands")
        api.create_item("heavy_protective_suit", owner_object=player, location_kind="equipment", slot="body")
        api.create_item("bandage", quantity=30, owner_object=player, location_kind="inventory")
        profile = player.profile()
        profile["xp"] = rules.xp_threshold(7)
        profile["attributes"]["constitution"]["allocated"] = 20
        profile["attributes"]["strength"]["allocated"] = 0
        profile["attributes"]["wisdom"]["allocated"] = 4
        profile["hp"] = rules.stats(profile)["max_hp"]
        profile["mental"] = rules.stats(profile)["max_mental"]
        profile["quests"]["radio_tower"].update(started=True, record_read=True, generator_fixed=True)
        player.save_profile(profile)
    for name in ("일인검증우두머리", "이인검증우두머리", "삼인검증우두머리", "사인검증우두머리"):
        enemy = create_object(Enemy, key=name, location=room)
        enemy.db.enemy_id = "alpha"
        enemy.db.hp = enemy.db.max_hp = ENEMIES["alpha"]["hp"]
        enemy.db.scaling_participants = 1
    return {"label": "TEST / PHASE 7B", "prepared": "Lv7/T2 독립 4계정, V1 Boss 4개 (수치 불변)"}


def prepare_loot():
    from evennia import create_object
    from typeclasses.explorers import Explorer
    from typeclasses.loot import Corpse, DroppedLoot
    from world.bootstrap import get_room
    from world.loot_service import populate_source

    players = list(Explorer.objects.filter(db_key__in=FIXTURE_NAMES).order_by("pk"))
    a, b, c, _ = players
    deadline = time() + 120
    corpse = create_object(Corpse, key="권리검증시체", location=get_room("dock"))
    corpse.db.created_at = time()
    # 이미 저장된 corpse deadline을 가진 격리 fixture다. 신규 생성 TTL(30초)은
    # Full smoke에서 검사한다. 여기서는 네 session 준비와 권리 관찰 시간을 확보한다.
    corpse.db.decay_at = corpse.db.created_at + 90
    populate_source(corpse, [{"kind": "item", "id": "bandage", "quantity": 6,
                             "reserved_player": a.pk, "assigned_player": a.pk,
                             "protection_until": deadline}])
    for name, quantity, eligible, shares in (("분배검증칩", 20, [a.pk, b.pk], {a.pk: 0, b.pk: 20}),
                                            ("다른분배칩", 8, [c.pk], {c.pk: 8})):
        source = create_object(DroppedLoot if name == "분배검증칩" else Corpse,
                               key=name, location=get_room("dock"))
        if name != "분배검증칩":
            source.db.decay_at = time() + 3600
        populate_source(source, [{"kind": "currency", "id": "chip", "quantity": quantity,
                                 "eligible_players": eligible, "remaining_shares": shares,
                                 "protection_until": deadline}])
    return {"label": "TEST / PHASE 7B", "deadline": deadline, "snapshot": inspect()}


def prepare_reports():
    from typeclasses.explorers import Explorer

    for name, quest in (("검증나", "radio_tower"), ("검증다", "deep_jungle")):
        player = Explorer.objects.get(db_key=name)
        profile = player.profile()
        profile["quests"]["radio_tower"].update(started=True, record_read=True, generator_fixed=True,
                                               boss_defeated=True, claimed=quest == "deep_jungle")
        if quest == "deep_jungle":
            profile["quests"][quest].update(started=True, boss_defeated=True)
        player.save_profile(profile)
    return {"label": "TEST / PHASE 7B", "prepared": "두 issuer의 first final-report 경계 (보상 자체는 지급하지 않음)"}


def prepare_items():
    from typeclasses.explorers import Explorer
    from world.content import ITEMS
    from world.equipment_service import equip_item
    from world.firearm_service import create_firearm
    from world.item_entities import api

    prepare_live()
    player = Explorer.objects.get(db_key=FIXTURE_NAMES[0])
    gun = create_firearm("guard_carbine", owner_object=player, mode="empty")
    equip_item(player, gun)
    for rounds in (3, 9):
        api.create_item("mag_556_standard", owner_object=player, location_kind="inventory", state={"rounds": rounds})
    for _ in range(2):
        api.create_item("flashlight", owner_object=player, location_kind="inventory", state={
            "power_type": ITEMS["flashlight"]["light_source"]["power_type"], "remaining_power": 1800, "enabled": False, "started_at": None})
    return inspect()


def build_corpus(kind):
    from django.conf import settings
    from evennia import create_object
    from typeclasses.explorers import Explorer
    from typeclasses.interactables import Container
    from typeclasses.loot import Corpse, DroppedLoot
    from world import rules
    from world.bootstrap import get_room
    from world.item_entities import api
    from world.item_entities.models import ItemEntity, ItemMigrationLedger, ItemRuntime
    from world.item_migration.workflow import migration_context

    settings.ITEM_MIGRATION_AUDIT = True
    players = list(Explorer.objects.filter(db_key__in=FIXTURE_NAMES).order_by("pk"))
    assert len(players) == 4
    assert not ItemMigrationLedger.objects.exists()
    # 이 builder가 받은 새 격리 fixture만 historical 상태로 구성한다.
    ItemEntity.objects.filter(owner_object__in=players).delete()
    ItemRuntime.objects.update_or_create(pk=1, defaults={"version": 0})
    for player in players:
        player.db.equipment_backend = "legacy"
        player.db.item_runtime_version = None
        player.db.active_weapon_item_id = None
        player.db.active_light_item_id = None
        profile = rules.new_profile()
        profile.update(inventory={}, equipment={}, storage={}, light_sources={}, credits=1000)
        player.db.profile = profile

    a, b, c, d = players
    profile = deepcopy(a.db.profile)
    profile.update(inventory={"machete": 1, "blade": 2, "spear": 1, "vest": 1, "leather_suit": 1,
                              "flashlight": 2, "bandage": 4, "scrap": 20},
                   equipment={"weapon": "blade", "armor": "vest"},
                   storage={"jungle_blade": 1, "tactical_vest": 1, "battery": 2},
                   light_sources={"flashlight": {"on": True, "charge_seconds": 1800, "started_at": time()}})
    a.db.profile = profile
    profile = deepcopy(b.db.profile)
    profile["quests"]["radio_tower"].update(started=True, record_read=True, generator_fixed=True,
                                            boss_defeated=True, claimed=True)
    profile["discoveries"]["supply_cache"] = True
    b.db.profile = profile
    profile = deepcopy(c.db.profile)
    profile["quests"]["deep_jungle"]["claimed"] = True
    profile["quests"]["radio_tower"]["generator_fixed"] = True
    profile["discoveries"]["jungle_cache"] = True
    c.db.profile = profile
    profile = deepcopy(d.db.profile)
    profile.update(inventory={"carbine": 2, "heavy_carbine": 1, "armor": 1, "heavy_suit": 1},
                   equipment={"weapon": "carbine", "armor": "armor"})
    d.db.profile = profile

    with migration_context():
        # Entitlement 이외 native rows는 독립 native source에 둔다.
        native = create_object(Explorer, key="보존검증", location=get_room("storage_room"), home=get_room("dock"))
        native.db.equipment_backend = "item_entities"
        native.db.profile = {**rules.new_profile(), "inventory": {}, "equipment": {}, "storage": {}, "light_sources": {}}
        from world.firearm_service import create_firearm

        create_firearm("guard_carbine", owner_object=native, location_kind="inventory", mode="full_standard")
        api.create_item("outpost_supply_pass", owner_object=b, location_kind="inventory")
        api.create_item("expedition_tag", owner_object=b, location_kind="personal_storage")
        api.create_item("predator_scale_charm", owner_object=c, location_kind="personal_storage")
        historical = create_object(Explorer, key="구형탐사", location=get_room("dock"), home=get_room("dock"))
        historical.db.profile = {**rules.new_profile(), "version": 3, "inventory": {}, "equipment": {},
                                 "storage": {}, "light_sources": {}, "quests": {},
                                 "discoveries": {"jungle_cache": True}, "cache_claimed": True,
                                 "generator_fixed": True}
        shared = create_object(Container, key="TEST LEGACY CORPUS 공용함", location=get_room("storage_room"))
        shared.db.items = {"armor": 1, "bandage": 5}
        corpse = create_object(Corpse, key="TEST LEGACY CORPUS 시체", location=get_room("dock"))
        corpse.db.loot_backend = "legacy"
        corpse.db.decay_at = time() + 3600
        corpse.db.entries = [{"kind": "item", "id": "carbine", "quantity": 1,
                              "reserved_player": a.pk, "assigned_player": a.pk,
                              "protection_until": 2000000000}]
        ground = create_object(DroppedLoot, key="TEST LEGACY CORPUS 화폐", location=get_room("dock"))
        ground.db.loot_backend = "legacy"
        ground.db.entries = [{"kind": "currency", "id": "chip", "quantity": 20,
                              "reserved_player": a.pk, "eligible_players": [a.pk, b.pk],
                              "remaining_shares": {a.pk: 0, b.pk: 20}, "protection_until": 2000000000}]
    if kind == "warning":
        profile = deepcopy(a.db.profile)
        profile["equipment"]["weapon"] = "spear"
        profile["inventory"]["spear"] = 0
        a.db.profile = profile
    if kind == "invalid":
        profile = deepcopy(d.db.profile)
        profile["inventory"]["unknown_historical_item"] = 1
        d.db.profile = profile
    return inspect()


def alter_corpus(action):
    from typeclasses.explorers import Explorer
    from world.item_entities.models import ItemEntity

    if action == "repair-invalid":
        player = Explorer.objects.get(db_key="검증라")
        profile = deepcopy(player.db.profile)
        profile["inventory"].pop("unknown_historical_item")
        player.db.profile = profile
    else:
        player = Explorer.objects.get(db_key="검증가")
        ItemEntity.objects.filter(owner_object=player, definition_id="bandage").update(
            quantity=5 if action == "corrupt" else 4)
    return inspect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("inspect", "live", "boss", "loot", "reports", "items", "valid", "warning", "invalid", "repair-invalid", "corrupt", "restore"))
    args = parser.parse_args()
    initialize()
    result = (inspect() if args.action == "inspect" else prepare_live() if args.action == "live" else prepare_boss() if args.action == "boss" else prepare_loot() if args.action == "loot" else prepare_reports() if args.action == "reports" else prepare_items() if args.action == "items" else
              build_corpus(args.action) if args.action in ("valid", "warning", "invalid") else alter_corpus(args.action))
    print(json.dumps(result, ensure_ascii=False, default=str))
