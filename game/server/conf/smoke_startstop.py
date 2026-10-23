"""격리 Full 전용 전투 Loot 생성 관측. 운영 hook/도메인 구현은 그대로 위임한다."""

import json
from collections import Counter
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps

from server.conf.at_server_startstop import (  # noqa: F401
    at_server_cold_start,
    at_server_cold_stop,
    at_server_reload_start,
    at_server_reload_stop,
    at_server_start,
    at_server_stop,
)

_death = ContextVar("smoke_loot_death", default=None)


def owned_items(owner):
    from world.item_entities import api
    # archive profile/storage/db.items는 native restart 보존의 증거가 아니다.
    return {str(item.pk): {"definition": item.definition_id, "quantity": item.quantity,
                           "sequence": item.sequence, "location": item.location_kind,
                           "parent": str(item.parent_item_id) if item.parent_item_id else None,
                           "slot": item.slot, "socket": item.socket, "state": item.state}
            for item in api.items_owned_by(owner)}

def owned_loot(source):
    from typeclasses.loot import Corpse
    from world.loot_entities.models import CurrencyLoot, LootClaim
    from world.loot_service import native_source, source_entries
    items = owned_items(source)
    return {
        "corpse": isinstance(source, Corpse), "native": native_source(source),
        "room": source.db_location_id, "entries": source_entries(source),
        "source_spawn": source.db.source_spawn, "source_enemy": source.db.source_enemy,
        "created_at": source.db.created_at if isinstance(source, Corpse) else None,
        "items": items,
        "claims": {str(row.item_entity_id): {
            "id": row.pk, "reserved_party": row.reserved_party_id,
            "reserved_player": row.reserved_player_id, "assigned_player": row.assigned_player_id,
            "protection_until": row.protection_until,
        } for row in LootClaim.objects.filter(item_entity_id__in=items)},
        "currency": {str(row.pk): {
            "quantity": row.quantity, "reserved_party": row.reserved_party_id,
            "reserved_player": row.reserved_player_id, "protection_until": row.protection_until,
            "shares": {str(share.pk): {"player": share.player_id, "remaining": share.remaining_amount}
                       for share in row.shares.all()},
        } for row in CurrencyLoot.objects.filter(owner_object=source)},
    }


def entry_contract(entries):
    """실제 한 번 roll한 반환값과 root별 native 생성을 수량·권리까지 비교한다."""
    from world.content import ITEMS
    from world.loot_assets import normalize_entry

    rows = []
    for raw in entries:
        row = normalize_entry(raw)
        row.pop("acquisition", None)
        amounts = ([row["quantity"]] if row["kind"] == "currency" or ITEMS[row["id"]]["stackable"]
                   else [1] * row["quantity"])
        rows.extend(json.dumps(dict(row, quantity=amount), sort_keys=True) for amount in amounts)
    return Counter(rows)


def assert_generated_tree(entries, source):
    """선언된 firearm 획득 탄창만 child로 허용하고 숨은 inside 복제를 거절한다."""
    from world.content import ITEMS
    from world.firearm_service import STANDARD_MAGAZINES

    expected = Counter()
    for entry in entries:
        if entry.get("kind", "item") != "item":
            continue
        acquisition = entry.get("acquisition", {})
        mode = acquisition.get("mode", "no_mag")
        if not ITEMS[entry["id"]].get("firearm_family") or mode == "no_mag":
            continue
        family = ITEMS[entry["id"]]["firearm_family"]
        magazine = acquisition.get("magazine_definition", STANDARD_MAGAZINES[family])
        capacity = ITEMS[magazine]["magazine"]["capacity"]
        rounds = acquisition["rounds"] if mode == "partial" else capacity if mode == "full_standard" else 0
        expected[(entry["id"], magazine, rounds)] += entry["quantity"]
    actual = Counter()
    for row in source["items"].values():
        if row["parent"] is None:
            assert row["location"] == "corpse_loot", "생성 root 위치 불일치"
            continue
        parent = source["items"].get(row["parent"])
        assert parent and parent["parent"] is None, "선언하지 않은 중첩 child"
        assert (row["quantity"], row["location"], row["slot"], row["socket"]) == (
            1, "inside", None, "magazine"), "선언하지 않은 child 형태"
        assert row["state"].keys() == {"rounds"}, "생성 탄창 state 변경"
        actual[(parent["definition"], row["definition"], row["state"]["rounds"])] += 1
    assert actual == expected, "선언하지 않은 생성 child/탄창"


def install_observer():
    from django.conf import settings

    from server.conf.smoke_support import require_smoke

    require_smoke(settings)
    if settings.PRIMAL_SMOKE_MODE != "full":
        return
    from django.db import connection
    from evennia.utils.dbserialize import deserialize
    from typeclasses import loot
    from typeclasses.enemies import Enemy
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot

    if getattr(Enemy._finish_death, "_smoke_observer", False):
        return
    original_build, original_death = loot.build_entries, Enemy._finish_death

    @wraps(original_build)
    def observed_build(enemy, groups, now, rng=None):
        entries = original_build(enemy, groups, now, rng)
        event = _death.get()
        if event is not None:
            assert event["enemy"] == enemy.pk and event["at"] == now, "다른 death의 loot 생성"
            assert groups and not event["rolls"], "한 death의 중복 loot roll"
            event["rolls"].append(deepcopy(entries))
        return entries

    @wraps(original_death)
    def observed_death(enemy, now, rng=None):
        if enemy.db.state != "alive" or enemy.db.hp > 0:
            return original_death(enemy, now, rng)
        assert connection.in_atomic_block, "death 관측은 기존 world_change 안에서만 허용"
        assert _death.get() is None, "death 관측 중첩 금지"
        old_corpses = set(loot.Corpse.objects.all().values_list("pk", flat=True))
        old_items = set(ItemEntity.objects.values_list("pk", flat=True))
        old_currency = set(CurrencyLoot.objects.values_list("pk", flat=True))
        event = {"enemy": enemy.pk, "at": now, "rolls": []}
        token = _death.set(event)
        try:
            result = original_death(enemy, now, rng)
        finally:
            _death.reset(token)
        assert enemy.db.state == "respawning" and len(event["rolls"]) == 1, "정상 death/roll 증거 없음"
        created = list(loot.Corpse.objects.all().exclude(pk__in=old_corpses))
        assert len(created) == 1, ("한 death의 corpse 생성 수 불일치", sorted(old_corpses), [obj.pk for obj in created])
        corpse = created[0]
        source = owned_loot(corpse)
        assert source["native"] and source["created_at"] == now, "native death source 불일치"
        assert (source["room"], source["source_spawn"], source["source_enemy"]) == (
            enemy.db_location_id, enemy.db.spawn_id, enemy.db.enemy_id), "death source 출처 불일치"
        assert entry_contract(event["rolls"][0]) == entry_contract(source["entries"]), "roll/native 생성 계약 불일치"
        assert_generated_tree(event["rolls"][0], source)
        assert not old_items.intersection(ItemEntity.objects.filter(owner_object=corpse).values_list("pk", flat=True))
        assert not old_currency.intersection(CurrencyLoot.objects.filter(owner_object=corpse).values_list("pk", flat=True))
        assert set(ItemEntity.objects.values_list("pk", flat=True)) - old_items == set(
            ItemEntity.objects.filter(owner_object=corpse).values_list("pk", flat=True)), "death 밖 신규 item 생성"
        assert set(CurrencyLoot.objects.values_list("pk", flat=True)) - old_currency == set(
            CurrencyLoot.objects.filter(owner_object=corpse).values_list("pk", flat=True)), "death 밖 신규 currency 생성"
        # 같은 transaction의 Attribute: 실패/rollback 때 자산과 함께 사라진다.
        births = list(deserialize(enemy.db.smoke_loot_births) or [])
        births.append({"at": now, "source_id": str(corpse.pk), "source": source})
        enemy.db.smoke_loot_births = births
        return result

    observed_death._smoke_observer = True
    loot.build_entries, Enemy._finish_death = observed_build, observed_death


def at_server_init():
    from server.conf import at_server_startstop

    install_observer()
    at_server_startstop.at_server_init()
