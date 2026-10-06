"""계산용 수량 snapshot과 Entity mutation. legacy 필드에는 결과를 저장하지 않는다."""

from collections import Counter
from copy import deepcopy

from world.content import ITEMS
from world.item_entities import api

LEGACY_FIELDS = ("inventory", "equipment", "storage", "light_sources")


def counts(character):
    result = Counter()
    for row in api.items_owned_by(character):
        if row.location_kind in ("inventory", "equipment"):
            result[row.definition_id] += row.quantity
    return dict(result)


def bind(character, profile):
    from evennia.utils.dbserialize import deserialize

    archived = deserialize(character.db.profile) or {}
    profile.legacy_item_fields = {key: deepcopy(archived.get(key)) for key in LEGACY_FIELDS}
    profile.item_baseline = dict(sum((Counter({item.definition_id: item.quantity})
                                     for item in profile.equipment_context.carried
                                     if item.location in ("inventory", "equipment")), Counter()))
    profile.item_operations = {}
    profile["inventory"] = deepcopy(profile.item_baseline)
    profile["equipment"] = {}
    profile["storage"] = {}
    profile["light_sources"] = {}
    return profile


def grant(character, identity, quantity=1, *, location="inventory"):
    if ITEMS[identity].get("firearm_family"):
        from world.firearm_service import create_firearm

        return [create_firearm(identity, owner_object=character, location_kind=location, mode="full_standard") for _ in range(quantity)]
    created = []
    for amount in ([quantity] if ITEMS[identity]["stackable"] else [1] * quantity):
        row = api.create_item(identity, quantity=amount, location_kind=location, owner_object=character)
        destinations = list(api.items_in_location(location, owner_object=character))
        destination = next((other for other in destinations if ITEMS[identity]["stackable"] and other.pk != row.pk and api.same_merge_context(row, other)), None)
        if destination:
            row = api.merge_stack(row, destination)
        created.append(row)
    return created


def consume(character, identity, quantity, *, operation="consume"):
    from world.item_entities.services import lock_character_items
    from world.multiplayer import world_change
    from world.rules import RuleError

    with world_change():
        locked = lock_character_items(character)
        rows = sorted((row for row in locked.values() if row.definition_id == identity and row.location_kind == "inventory"), key=lambda row: row.sequence)
        if type(quantity) is not int or quantity <= 0 or sum(row.quantity for row in rows) < quantity:
            raise RuleError("소모할 물품이 부족합니다.")
        for row in rows:
            amount = min(quantity, row.quantity)
            api._check_tree_operation(row, (), operation)
            if amount == row.quantity:
                api.delete_item(row, operation=operation)
            else:
                row.quantity -= amount
                row.save()
            quantity -= amount
            if not quantity:
                break


def persist_calculation(character, profile):
    """pure rules의 수량 delta만 owner lock 안에서 적용하고 보존 blob은 원형으로 저장한다."""
    from world.item_entities.services import lock_character_items
    from world.rules import RuleError

    before = profile.item_baseline if hasattr(profile, "item_baseline") else counts(character)
    after = profile["inventory"]
    changes = {identity: after.get(identity, 0) - before.get(identity, 0) for identity in set(before) | set(after)}
    if any(changes.values()):
        lock_character_items(character)
        current = counts(character)
        if any(delta and current.get(identity, 0) != before.get(identity, 0) for identity, delta in changes.items()):
            raise RuleError("소지품이 변경되었습니다. 다시 시도하세요.")
    for identity, delta in changes.items():
        if delta < 0:
            consume(character, identity, -delta, operation=profile.item_operations.get(identity, "consume"))
        elif delta > 0:
            grant(character, identity, delta)
    saved = deepcopy(dict(profile))
    for key, value in profile.legacy_item_fields.items():
        if value is None:
            saved.pop(key, None)
        else:
            saved[key] = value
    profile.item_baseline = deepcopy(after)
    return saved
