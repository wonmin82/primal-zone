"""읽기 전용 source 계획과 검증용 canonical snapshot."""

import json
from collections import Counter
from hashlib import sha256
from math import isfinite

from evennia.objects.models import ObjectDB
from evennia.utils.dbserialize import deserialize

from world.content import ITEMS
from world.content.item_mapping import BOSS_REWARDS, LEGACY_ITEM_MAPPING
from world.item_entities import api
from world.item_entities.models import ItemMigrationLedger
from world.item_runtime import VERSION
from world.loot_assets import normalize_entry
from world.loot_entities.models import CurrencyLoot, LootClaim

PATHS = {"explorer": "typeclasses.explorers.Explorer", "container": "typeclasses.interactables.Container",
         "corpse": "typeclasses.loot.Corpse", "dropped": "typeclasses.loot.DroppedLoot"}


def sources():
    for obj in ObjectDB.objects.filter(db_typeclass_path__in=PATHS.values()).order_by("pk"):
        yield next(kind for kind, path in PATHS.items() if path == obj.db_typeclass_path), obj


def ledger(kind, obj):
    return ItemMigrationLedger.objects.filter(migration_version=VERSION, source_kind=kind, source_identity=obj.pk).first()


def raw_source(kind, obj):
    if kind == "explorer":
        profile = deserialize(obj.db.profile)
        if not isinstance(profile, dict) or not profile:
            raise ValueError("Explorer profile이 없거나 형식이 올바르지 않습니다.")
        value = {key: profile.get(key, {}) for key in ("inventory", "equipment", "storage", "light_sources", "quests")}
        if profile.get("version", 1) < 4:
            from world.quests import progress_defaults

            value["quests"] = progress_defaults()
            for old, flag in {"quest_started": "started", "record_read": "record_read", "generator_fixed": "generator_fixed",
                              "boss_defeated": "boss_defeated", "quest_claimed": "claimed"}.items():
                value["quests"]["radio_tower"][flag] = bool(profile.get(old))
        return value
    return deserialize(obj.db.items if kind == "container" else obj.db.entries) or ({} if kind == "container" else [])


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def target(identity):
    result = LEGACY_ITEM_MAPPING.get(identity, identity)
    if result not in ITEMS:
        raise ValueError(f"unknown legacy item: {identity}")
    return result


def quantities(value):
    if not isinstance(value, dict):
        raise ValueError("아이템 수량은 ID별 dictionary여야 합니다.")
    for identity, amount in value.items():
        target(identity)
        if type(amount) is not int or amount < 0:
            raise ValueError(f"invalid quantity: {identity}={amount}")
    return value


def plan(kind, obj):
    raw = raw_source(kind, obj)
    existing = list(api.items_owned_by(obj))
    for row in existing:
        target(row.definition_id)
    completed = ledger(kind, obj)
    warnings, expected = [], Counter()
    if completed and completed.completed:
        if completed.source_digest != digest(raw) or completed.expected_state != json_state(obj):
            raise ValueError("completed source의 검증 snapshot이 일치하지 않습니다.")
        return dict(kind=kind, identity=obj.pk, digest=digest(raw), warnings=completed.warnings, completed=True, expected=completed.created_counts)
    if kind in ("corpse", "dropped"):
        native = obj.db.loot_backend == "item_entities"
        assets = bool(existing) or CurrencyLoot.objects.filter(owner_object=obj).exists()
        if native and raw or not native and assets:
            raise ValueError("전리품 backend marker와 실제 legacy/native storage가 일치하지 않습니다.")
        if not native:
            for entry in raw:
                from world.loot_entities.models import validate_time

                validate_time(entry.get("protection_until", 0))
                shares = entry.get("remaining_shares", entry.get("shares", {}))
                if any(type(amount) is not int or amount < 0 for amount in shares.values()):
                    raise ValueError("invalid currency share amount")
                item = normalize_entry(entry)
                if type(item["quantity"]) is not int or item["quantity"] <= 0:
                    raise ValueError("전리품 수량은 양의 정수여야 합니다.")
                if item["kind"] == "item":
                    definition = ITEMS[target(item["id"])]
                    expected["items"] += 1 if definition["stackable"] else item["quantity"]
                    if definition.get("firearm_family"):
                        expected["items"] += item["quantity"]
                    expected["claims"] += (1 if definition["stackable"] else item["quantity"]) if item["protection_until"] or any(item.get(key) for key in ("reserved_party", "reserved_player", "assigned_player")) else 0
                elif item["kind"] == "currency":
                    if sum(item["remaining_shares"].values()) > item["quantity"]:
                        raise ValueError("화폐 지분 합계가 전리품 수량을 초과합니다.")
                    expected["currency"] += 1
                    expected["shares"] += len(item["eligible_players"])
                else:
                    raise ValueError("XP 등 지원하지 않는 전리품 entry입니다.")
                for key in ("reserved_party", "reserved_player", "assigned_player"):
                    if item.get(key) and not ObjectDB.objects.filter(pk=item[key]).exists():
                        raise ValueError(f"missing recipient/reference: {item[key]}")
                for identity in item.get("eligible_players", []):
                    if not ObjectDB.objects.filter(pk=identity).exists():
                        raise ValueError(f"missing recipient: {identity}")
    elif kind == "container":
        if existing and quantities(raw):
            raise ValueError("공용 보관함에 legacy/native 데이터가 동시에 존재합니다.")
        for identity, amount in quantities(raw).items():
            definition = ITEMS[target(identity)]
            expected["items"] += (1 if amount and definition["stackable"] else amount) + (amount if definition.get("firearm_family") else 0)
    else:
        native = obj.db.equipment_backend == "item_entities"
        if native and (raw["inventory"] or any(raw["equipment"].values()) or raw["storage"] or raw["light_sources"]):
            raise ValueError("native 캐릭터에 변환 ledger 없는 legacy item blob이 존재합니다.")
        if not native and any(ITEMS[target(row.definition_id)].get("item_type") != "credential"
                              and row.definition_id not in BOSS_REWARDS.values() for row in existing):
            raise ValueError("legacy 캐릭터에 entitlement 이외 native 아이템이 존재합니다.")
        if not native:
            inventory = dict(quantities(raw["inventory"]))
            for identity in raw["equipment"].values():
                if identity:
                    target(identity)
                    if inventory.get(identity, 0) == 0:
                        inventory[identity] = 1
                        warnings.append(f"장착 수량 누락 복원: {identity}")
            for values in (inventory, quantities(raw["storage"])):
                for identity, amount in values.items():
                    definition = ITEMS[target(identity)]
                    expected["items"] += (1 if amount and definition["stackable"] else amount) + (amount if definition.get("firearm_family") else 0)
            enabled = [identity for identity, state in raw["light_sources"].items() if state.get("on")]
            from world.item_states import state_errors
            from world.lighting import projected

            for identity, saved_light in raw["light_sources"].items():
                definition = ITEMS[target(identity)]
                if not definition.get("light_source"):
                    raise ValueError("광원 정의가 아닌 legacy light state입니다.")
                power = saved_light.get("charge_seconds", 0)
                started = saved_light.get("started_at")
                if (type(saved_light.get("on", False)) is not bool
                        or type(power) not in (int, float) or not isfinite(power) or power < 0
                        or started is not None and (type(started) not in (int, float) or not isfinite(started) or started < 0)):
                    raise ValueError("invalid legacy flashlight state")
                state = projected(raw, identity, 0)
                errors = state_errors(definition, {"power_type": definition["light_source"]["power_type"],
                                                  "remaining_power": state["charge_seconds"], "enabled": bool(state["on"]),
                                                  "started_at": state["started_at"] if state["on"] else None})
                if errors:
                    raise ValueError("; ".join(errors))
            if len(enabled) > 1:
                warnings.append("복수 ON 광원을 legacy 순서의 첫 유효 광원 하나로 정규화합니다.")
        for quest, reward in BOSS_REWARDS.items():
            if raw["quests"].get(quest, {}).get("claimed"):
                credential = "outpost_supply_pass" if quest == "radio_tower" else "special_supply_pass"
                expected["items"] += sum(not any(row.definition_id == identity for row in existing) for identity in (credential, reward))
    return dict(kind=kind, identity=obj.pk, digest=digest(raw), warnings=warnings, completed=False, expected=dict(expected))


def native_state(obj):
    items = list(api.items_owned_by(obj))
    ids = [row.pk for row in items]
    return {
        "items": [{"id": str(row.pk), "definition": row.definition_id, "quantity": row.quantity, "location": row.location_kind,
                   "owner": row.owner_object_id, "parent": str(row.parent_item_id) if row.parent_item_id else None,
                   "slot": row.slot, "socket": row.socket, "state": row.state, "sequence": row.sequence, "unique_scope": row.unique_scope_key} for row in items],
        "claims": list(LootClaim.objects.filter(item_entity_id__in=ids).order_by("item_entity__sequence").values("item_entity_id", "reserved_party_id", "reserved_player_id", "assigned_player_id", "protection_until")),
        "currency": [dict(id=row.pk, quantity=row.quantity, reserved_party=row.reserved_party_id, reserved_player=row.reserved_player_id,
                          protection_until=row.protection_until, shares=list(row.shares.order_by("player_id").values_list("player_id", "remaining_amount")))
                     for row in CurrencyLoot.objects.filter(owner_object=obj).order_by("pk")],
        "active_weapon": obj.db.active_weapon_item_id, "active_light": obj.db.active_light_item_id,
        "equipment_backend": obj.db.equipment_backend, "loot_backend": obj.db.loot_backend,
        "item_runtime_version": obj.db.item_runtime_version,
    }


def json_state(obj):
    return json.loads(json.dumps(native_state(obj), default=str))
