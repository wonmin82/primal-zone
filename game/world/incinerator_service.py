"""소각기의 same-room 검증과 명시적 출입증 확정 소각."""

from world import rules
from world.content import ITEMS
from world.credential_service import credential_items
from world.equipment_service import entity_runtime, resolve_item
from world.item_entities import api
from world.item_entities.policy import can_item_operation
from world.item_entities.services import domain_errors, lock_character_items, selected
from world.multiplayer import world_change
from world.stack_quantity import parse_stack_quantity
from world.targets import (
    item_selector,
    matching,
    parse_selector,
    require_single,
    room_objects,
    select,
)


@domain_errors
def incinerate(character, value, *, confirmed=False):
    from typeclasses.interactables import Incinerator

    name, quantity = parse_stack_quantity(value)
    with world_change():
        locked = lock_character_items(character)
        if not any(isinstance(obj, Incinerator) for obj in room_objects(character)):
            raise rules.RuleError("이곳에서 소각기를 식별할 수 없습니다.")
        rules.require_peace(character.profile_snapshot())
        credentials = credential_items(character)
        try:
            def names(row):
                definition = ITEMS[row.definition_id]
                return (row.definition_id, definition["name"], *definition.get("aliases", ()))

            selector = parse_selector(name, [name for row in credentials for name in names(row)])
            require_single(selector, "소각")
            item = select(matching(credentials, selector, names), selector)[0]
        except rules.RuleError:
            item = resolve_item(character, name, "소각") if entity_runtime(character) else item_selector(name, ITEMS, "소각")
        identity = item.definition_id if hasattr(item, "definition_id") else item
        if ITEMS[identity]["item_type"] == "credential":
            if quantity != 1:
                raise rules.RuleError("출입증 하나를 지정해 소각 확정하세요.")
            if not confirmed:
                return f"출입 권한을 잃습니다. 삭제하려면 {ITEMS[identity]['name']} 소각 확정"
        elif confirmed:
            raise rules.RuleError("소각 확정은 출입증에만 사용합니다.")
        if hasattr(item, "definition_id"):
            row = selected(locked, item)
            if row.location_kind != "inventory" or row.owner_object_id != character.pk:
                raise rules.RuleError("직접 소지한 물건만 소각할 수 있습니다.")
            if not ITEMS[identity]["stackable"] and quantity != 1:
                raise rules.RuleError("스택만 수량 또는 모두 소각할 수 있습니다.")
            count = row.quantity if quantity is None else quantity
            api.destroy_quantity(row, count, operation="burn")
        else:
            if not can_item_operation(identity, "burn"):
                raise rules.RuleError("이 물건은 소각할 수 없습니다.")

            def burn(profile):
                available = profile["inventory"].get(identity, 0) - sum(
                    identity == entry for entry in profile["equipment"].values())
                count = available if quantity is None else quantity
                if type(count) is not int or not 0 < count <= available:
                    raise rules.RuleError("소각할 수량이 부족합니다. 장비는 먼저 해제하세요.")
                rules.consume(profile, identity, count)
                from world.lighting import discard_device_state_if_unowned

                discard_device_state_if_unowned(profile, identity)
                return count

            count = character.change(burn)
        return f"{ITEMS[identity]['name']} {count}개를 소각했다."
