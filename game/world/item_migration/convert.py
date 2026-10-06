"""source 하나의 원자적 변환. 운영 CLI와 fixture만 호출한다."""

from collections import Counter
from copy import deepcopy

from django.utils import timezone
from evennia.objects.models import ObjectDB
from evennia.utils.dbserialize import deserialize

from world.content import ITEMS
from world.content.item_mapping import BOSS_REWARDS
from world.item_entities import api
from world.item_entities.models import ItemMigrationLedger, ItemSequence
from world.item_runtime import VERSION
from world.loot_entities.models import CurrencyLoot, CurrencyLootShare, LootClaim
from world.multiplayer import world_change

from .scan import entitlement_grants, json_state, ledger, plan, raw_source, target


def create(identity, amount, owner, location):
    from world.firearm_service import create_firearm

    definition = ITEMS[identity]
    result = []
    for quantity in ([amount] if definition["stackable"] else [1] * amount):
        if not quantity:
            continue
        result.append(create_firearm(identity, owner_object=owner, location_kind=location, mode="full_standard")
                      if definition.get("firearm_family") else
                      api.create_item(identity, quantity=quantity, location_kind=location, owner_object=owner))
    return result


def convert_explorer(obj, raw, now, was_native):
    from world.lighting import projected

    saved_profile = deserialize(obj.db.profile)
    obj.db.equipment_backend = "item_entities"
    if not was_native:
        inventory = dict(raw["inventory"])
        for identity in raw["equipment"].values():
            if identity and not inventory.get(identity):
                inventory[identity] = 1
        for identity, amount in inventory.items():
            create(target(identity), amount, obj, "inventory")
        for identity, amount in raw["storage"].items():
            create(target(identity), amount, obj, "personal_storage")
        for legacy_slot, identity in raw["equipment"].items():
            if not identity:
                continue
            slot = "hands" if legacy_slot == "weapon" else "body" if legacy_slot == "armor" else legacy_slot
            row = next(item for item in api.items_owned_by(obj) if item.definition_id == target(identity) and item.location_kind == "inventory")
            api.move_item_tree(row, location_kind="equipment", owner_object=obj, slot=slot)
        active = None
        for identity in raw["light_sources"]:
            rows = [item for item in api.items_owned_by(obj) if item.definition_id == target(identity) and item.location_kind == "inventory"]
            if not rows:
                continue
            current = projected(raw, identity, now)
            enabled = bool(current["on"] and active is None)
            state = dict(power_type=ITEMS[target(identity)]["light_source"]["power_type"],
                         remaining_power=current["charge_seconds"], enabled=enabled, started_at=now if enabled else None)
            api.update_item_state(rows[0], state)
            if enabled:
                active = str(rows[0].pk)
        obj.db.active_light_item_id = active
        from world.equipment_service import reconcile_references

        reconcile_references(obj)
    for quest, identity in BOSS_REWARDS.items():
        if raw["quests"].get(quest, {}).get("claimed"):
            credential = "outpost_supply_pass" if quest == "radio_tower" else "special_supply_pass"
            for reward in (identity, credential):
                if not any(row.definition_id == reward for row in api.items_owned_by(obj)):
                    api.create_item(reward, location_kind="inventory", owner_object=obj)
    owned = Counter()
    for row in api.items_owned_by(obj):
        owned[row.definition_id] += row.quantity
    for identity, amount in entitlement_grants(raw, owned).items():
        api.create_item(identity, quantity=amount, location_kind="inventory", owner_object=obj)
    # recovery hook의 계산용 profile을 legacy blob에 쓰지 않는다. entitlement도 quest 기록을 바꾸지 않는다.
    obj.db.profile = saved_profile


def convert_source(kind, obj, now):
    with world_change():
        ObjectDB.objects.select_for_update().get(pk=obj.pk)
        proposal = plan(kind, obj)
        previous = ledger(kind, obj)
        if previous and previous.completed:
            if previous.source_digest != proposal["digest"] or previous.expected_state != json_state(obj):
                raise ValueError("completed source의 legacy/native 상태가 검증 snapshot과 다릅니다.")
            return {**proposal, "skipped": True}
        raw = deepcopy(raw_source(kind, obj))
        native_origin = bool(obj.db.equipment_backend == "item_entities") if kind == "explorer" else bool(obj.db.loot_backend == "item_entities") if kind in ("corpse", "dropped") else bool(api.items_owned_by(obj).exists())
        before = ItemSequence.objects.get(pk=1).last_value
        existing = api.lock_items(api.items_owned_by(obj).values_list("pk", flat=True))
        # native identity/state/tree는 그대로 보존하고 이전 definition ID만 중앙 mapping으로 치환한다.
        for row in sorted(existing, key=lambda row: row.sequence):
            identity = target(row.definition_id)
            if identity != row.definition_id:
                row.definition_id = identity
                row.save()
        if kind == "explorer":
            convert_explorer(obj, raw, now, obj.db.equipment_backend == "item_entities")
            obj.db.item_runtime_version = VERSION
        elif kind == "container":
            if not existing:
                for identity, amount in raw.items():
                    create(target(identity), amount, obj, "shared_storage")
        elif obj.db.loot_backend != "item_entities":
            from world.loot_assets import normalize_entry
            from world.loot_service import populate_source

            entries = []
            for source_entry in raw:
                entry = normalize_entry(source_entry)
                if entry["kind"] == "item":
                    entry["id"] = target(entry["id"])
                    if ITEMS[entry["id"]].get("firearm_family"):
                        entry["acquisition"] = {"mode": "full_standard"}
                entries.append(entry)
            # 명시적인 변환에서만 blob을 잠시 분리하고 같은 transaction 안에서 원형을 보존한다.
            obj.db.entries = []
            populate_source(obj, entries)
            obj.db.entries = raw
        counts = {"native_origin": native_origin, "observed_at": now,
                  "items": ItemSequence.objects.get(pk=1).last_value - before,
                  "claims": LootClaim.objects.filter(item_entity__owner_object=obj).count(),
                  "currency": CurrencyLoot.objects.filter(owner_object=obj).count(),
                  "shares": CurrencyLootShare.objects.filter(currency_loot__owner_object=obj).count()}
        ItemMigrationLedger.objects.create(migration_version=VERSION, source_kind=kind, source_identity=obj.pk,
                                           completed=True, completed_at=timezone.now(), source_digest=proposal["digest"],
                                           expected_state=json_state(obj), created_counts=counts, warnings=proposal["warnings"])
        return {**proposal, "created": counts}
