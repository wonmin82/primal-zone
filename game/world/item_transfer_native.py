"""보관·전달·버리기: root UUID와 내부 tree를 그대로 이동한다."""

from world import rules
from world.content import ITEMS
from world.item_entities import api
from world.item_entities.services import domain_errors
from world.multiplayer import world_change
from world.targets import Mode, matching, parse_selector, select


def stored_items(character, container):
    owner = character if container.personal else container
    location = "personal_storage" if container.personal else "shared_storage"
    return list(api.items_in_location(location, owner_object=owner).order_by("sequence"))


def item_names(item):
    definition = ITEMS[item.definition_id]
    return (item.definition_id, definition["name"], *definition.get("aliases", []))


@domain_errors
def transfer(character, value, *, recipient=None, container=None, withdraw=False):
    from evennia import create_object
    from evennia.objects.models import ObjectDB
    from typeclasses.explorers import Explorer
    from typeclasses.interactables import Container
    from typeclasses.loot import DroppedLoot

    from world.observation import can_perceive, context_for

    with world_change():
        rules.require_peace(character.profile_snapshot())
        if not character.location:
            raise rules.RuleError("물건을 옮길 장소가 없습니다.")
        counterpart = recipient or container
        if counterpart:
            if (counterpart.location != character.location or counterpart == character
                    or not can_perceive(counterpart, context_for(character))
                    or not isinstance(counterpart, Explorer if recipient else Container)):
                raise rules.RuleError("같은 장소에서 사용할 수 있는 대상이 아닙니다.")
        if recipient:
            rules.require_peace(recipient.profile_snapshot())
        owners = {obj.pk: obj for obj in (character, counterpart) if obj}
        for identity in sorted(owners):
            ObjectDB.objects.select_for_update().get(pk=identity)
        pool = stored_items(character, container) if withdraw else list(api.items_in_location("inventory", owner_object=character).order_by("sequence"))
        api.lock_items([item.pk for owner in owners.values() for item in api.items_owned_by(owner)])
        selector = parse_selector(value, [name for item in pool for name in item_names(item)])
        rows = select(matching(pool, selector, item_names), selector)
        if selector.mode == Mode.ALL and any(not ITEMS[item.definition_id]["stackable"] for item in rows):
            raise rules.RuleError("스택만 모두 옮길 수 있습니다.")
        identity = rows[0].definition_id
        amount = 0
        if not counterpart:
            destination = create_object(DroppedLoot, key=ITEMS[identity]["name"], location=character.location)
            destination.db.loot_backend = "item_entities"
            destination.db.entries = []
            location, operation = "world_loot", "drop"
        elif container and not withdraw:
            destination = character if container.personal else container
            location, operation = ("personal_storage" if container.personal else "shared_storage"), "store"
        else:
            destination = recipient or character
            location, operation = "inventory", "give" if recipient else "store"
        for item in rows:
            count = item.quantity if selector.mode == Mode.ALL else 1
            moving = api.split_stack(item, count) if count < item.quantity else item
            moved = api.move_item_tree(moving, location_kind=location, owner_object=destination, operation=operation)
            if ITEMS[identity]["stackable"]:
                other = next((row for row in api.items_in_location(location, owner_object=destination).order_by("sequence")
                              if row.pk != moved.pk and api.same_merge_context(moved, row)), None)
                if other:
                    api.merge_stack(moved, other)
            amount += count
        return identity, amount
