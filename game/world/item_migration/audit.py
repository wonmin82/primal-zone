"""legacy source와 native 변환 결과의 독립 수량·장비·권리 대조."""

from collections import Counter

from world.content import ITEMS
from world.content.item_mapping import BOSS_REWARDS, FIXED_DISCOVERY_REWARDS
from world.firearms import STANDARD_MAGAZINES
from world.item_entities import api
from world.loot_assets import normalize_entry
from world.loot_entities.models import CurrencyLoot, LootClaim

from .scan import raw_source, target


def conversion_errors(kind, obj, record):
    if record.created_counts.get("native_origin"):
        return []  # 기존 native 구조는 UUID/state/tree snapshot과 full_clean으로 검증한다.
    raw = raw_source(kind, obj)
    rows = list(api.items_owned_by(obj))
    roots = [row for row in rows if row.parent_item_id is None]
    expected, actual = Counter(), Counter()
    for row in roots:
        actual[(row.definition_id, row.location_kind, row.slot)] += row.quantity
    if kind == "explorer":
        inventory = Counter(raw["inventory"])
        for identity in raw["equipment"].values():
            if identity and not inventory[identity]:
                inventory[identity] = 1
        for identity, quantity in inventory.items():
            expected[(target(identity), "inventory", None)] += quantity
        for slot, identity in raw["equipment"].items():
            if identity:
                definition = target(identity)
                expected[(definition, "inventory", None)] -= 1
                expected[(definition, "equipment", {"weapon": "hands", "armor": "body"}.get(slot, slot))] += 1
        for identity, quantity in raw["storage"].items():
            expected[(target(identity), "personal_storage", None)] += quantity
        # Phase 5 출입증은 이미 Entity일 수 있다. entitlement는 owner scope 전체를 검사한다.
        for row in roots:
            if ITEMS[row.definition_id].get("item_type") == "credential" or row.definition_id in BOSS_REWARDS.values():
                expected[(row.definition_id, row.location_kind, row.slot)] += 1
            elif row.definition_id in (*FIXED_DISCOVERY_REWARDS.values(), "generator_repair_part"):
                key = (row.definition_id, row.location_kind, row.slot)
                expected[key] = max(expected[key], actual[key])
        for quest, identity in BOSS_REWARDS.items():
            if raw["quests"].get(quest, {}).get("claimed") and not any(row.definition_id == identity for row in roots):
                expected[(identity, "inventory", None)] += 1
    elif kind == "container":
        for identity, quantity in raw.items():
            expected[(target(identity), "shared_storage", None)] += quantity
    else:
        location = "corpse_loot" if kind == "corpse" else "world_loot"
        expected_claims, actual_claims = [], []
        expected_currency, actual_currency = [], []
        for value in raw:
            entry = normalize_entry(value)
            rights = (entry["reserved_party"], entry["reserved_player"], entry["assigned_player"], entry["protection_until"])
            if entry["kind"] == "item":
                identity = target(entry["id"])
                expected[(identity, location, None)] += entry["quantity"]
                if any(rights):
                    parts = [entry["quantity"]] if ITEMS[identity]["stackable"] else [1] * entry["quantity"]
                    expected_claims.extend((identity, amount, *rights) for amount in parts)
            else:
                shares = tuple(sorted((player, entry["remaining_shares"].get(player, 0)) for player in entry["eligible_players"]))
                expected_currency.append((entry["quantity"], rights[0], rights[1], rights[3], shares))
        for row in roots:
            claim = LootClaim.objects.filter(item_entity=row).first()
            if claim:
                actual_claims.append((row.definition_id, row.quantity, claim.reserved_party_id, claim.reserved_player_id, claim.assigned_player_id, claim.protection_until))
        for currency in CurrencyLoot.objects.filter(owner_object=obj):
            actual_currency.append((currency.quantity, currency.reserved_party_id, currency.reserved_player_id, currency.protection_until,
                                    tuple(currency.shares.order_by("player_id").values_list("player_id", "remaining_amount"))))
        if Counter(expected_claims) != Counter(actual_claims) or Counter(expected_currency) != Counter(actual_currency):
            return ["legacy/native 전리품 보호·배정·화폐 지분 불일치"]
    errors = [] if +expected == +actual else ["legacy/native root 수량·장비·보관 위치 불일치"]
    for row in roots:
        family = ITEMS[row.definition_id].get("firearm_family")
        if family:
            magazine = row.children.filter(socket="magazine").first()
            definition = STANDARD_MAGAZINES[family]
            if magazine is None or magazine.definition_id != definition or magazine.state != {"rounds": ITEMS[definition]["magazine"]["capacity"]}:
                errors.append("legacy firearm의 standard full magazine 불일치")
    if kind == "explorer":
        from world.lighting import projected

        active = None
        for identity in raw["light_sources"]:
            candidates = [row for row in roots if row.definition_id == target(identity) and row.location_kind == "inventory"]
            if not candidates:
                continue
            projected_state = projected(raw, identity, record.created_counts["observed_at"])
            enabled = bool(projected_state["on"] and active is None)
            first = candidates[0]
            if first.state["remaining_power"] != projected_state["charge_seconds"] or first.state["enabled"] != enabled:
                errors.append("legacy flashlight power/ON 변환 불일치")
            if enabled:
                active = str(first.pk)
        if obj.db.active_light_item_id != active:
            errors.append("legacy flashlight active reference 불일치")
    return errors
