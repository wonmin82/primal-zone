"""순수 스택 이동 규칙과 영속 소유자를 연결하는 transaction 경계."""

from time import time

from evennia.utils.dbserialize import deserialize

from world import rules
from world.content.economy import CURRENCY
from world.currency import spend_currency
from world.multiplayer import world_change


def transfer_currency(caller, amount=None, recipient=None):
    from typeclasses.explorers import Explorer
    from typeclasses.loot import create_dropped_loot

    from world.observation import can_perceive, context_for

    with world_change():
        profile = caller.profile()
        if not caller.location:
            raise rules.RuleError("보급칩을 옮길 장소가 없습니다.")
        other = None
        if recipient is not None:
            if (not isinstance(recipient, Explorer) or recipient == caller
                    or recipient.location != caller.location or not can_perceive(recipient, context_for(caller))):
                raise rules.RuleError("같은 장소의 다른 탐사자에게만 보급칩을 줄 수 있습니다.")
            other = recipient.profile()
            rules.require_peace(other)
        quantity = spend_currency(profile, amount)
        caller.save_profile(profile)
        if recipient is not None:
            other["credits"] += quantity
            recipient.save_profile(other)
        else:
            create_dropped_loot(caller.location, [{"kind": "currency", "id": CURRENCY["id"],
                                "quantity": quantity, "shares": {}, "protection_until": 0}])
        return quantity


def transfer(caller, item_id, *, all_items=False, recipient=None, container=None, withdraw=False):
    from typeclasses.explorers import Explorer
    from typeclasses.interactables import Container
    from typeclasses.loot import create_dropped_loot

    from world.lighting import normalize
    from world.observation import can_perceive, context_for

    with world_change():
        profile = caller.profile()
        rules.require_peace(profile)
        if not caller.location:
            raise rules.RuleError("물건을 옮길 장소가 없습니다.")
        other = None
        if recipient is not None:
            if (
                not isinstance(recipient, Explorer)
                or recipient == caller
                or recipient.location != caller.location
                or not can_perceive(recipient, context_for(caller))
            ):
                raise rules.RuleError("같은 장소의 다른 탐사자에게만 물건을 줄 수 있습니다.")
            other = recipient.profile()
            rules.require_peace(other)
            contents = other["inventory"]
        elif container is not None:
            if (
                not isinstance(container, Container)
                or container.location != caller.location
                or not can_perceive(container, context_for(caller))
            ):
                raise rules.RuleError("이곳에서 사용할 수 있는 보관함이 아닙니다.")
            contents = profile["storage"] if container.personal else deserialize(container.db.items)
        else:
            contents = {}
        source, destination = (
            (contents, profile["inventory"]) if withdraw else (profile["inventory"], contents)
        )
        quantity = rules.move_item(
            source,
            destination,
            item_id,
            all_items=all_items,
            equipment=None if withdraw else profile["equipment"],
        )
        lost_power = item_id in profile.get("light_sources", {}) and not profile["inventory"].get(item_id)
        normalize(profile, time())
        caller.save_profile(profile)
        if recipient is not None:
            recipient.save_profile(other)
        elif container is not None:
            if not container.personal:
                container.db.items = contents
        else:
            create_dropped_loot(
                caller.location,
                [
                    {
                        "item": item_id,
                        "quantity": quantity,
                        "reserved_party": None,
                        "reserved_player": None,
                        "assigned_player": None,
                        "protection_until": 0,
                    }
                ],
            )
        if lost_power:
            from world.multiplayer import after_change

            after_change(lambda: caller.msg("마지막 광원을 옮겨 내부 전원 상태를 비웠다. 남은 전원은 폐기된다."))
        return quantity
