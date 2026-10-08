"""격리 서버의 restart 검증용 read-only persistent snapshot. 비밀번호는 조회하지 않는다."""

import json


def snapshot():
    from django.conf import settings
    from server.conf.smoke_support import require_smoke

    require_smoke(settings)
    import django

    django.setup()
    import evennia

    evennia._init()
    from evennia import search_tag
    from evennia.utils.dbserialize import deserialize
    from typeclasses.enemies import Enemy
    from typeclasses.explorers import Explorer
    from typeclasses.loot import Corpse, DroppedLoot
    from world.bootstrap import stale_definitions
    from world.environment_state import lifecycle_script
    from world.item_entities import api
    from world.loot_service import source_entries

    def owned_items(owner):
        # archive profile/storage/db.items는 native restart 보존의 증거가 아니다.
        return {str(item.pk): {"definition": item.definition_id, "quantity": item.quantity,
                               "sequence": item.sequence, "location": item.location_kind,
                               "parent": str(item.parent_item_id) if item.parent_item_id else None,
                               "slot": item.slot, "socket": item.socket, "state": item.state}
                for item in api.items_owned_by(owner)}

    from time import time

    observed_at = time()
    script = lifecycle_script()
    return {
        "observed_at": observed_at,
        "players": {player.key: {"profile": player.profile_snapshot(), "zone": player.zone,
                                  "home": player.home.db.zone_id, "id": player.id,
                                  "active_weapon": player.db.active_weapon_item_id,
                                  "active_light": player.db.active_light_item_id,
                                  "items": owned_items(player)}
                    for player in Explorer.objects.all() if player.key != "admin"},
        "box": owned_items(search_tag("shared_container", category="primal_interactable")[0]),
        "facilities": deserialize(script.db.facilities),
        "clock": deserialize(script.db.environment)["clock"],
        "enemies": {str(enemy.id): {"state": enemy.db.state, "combatants": list(enemy.db.combatants or []),
                                    "claim": deserialize(enemy.db.claim)} for enemy in Enemy.objects.all()},
        "loot": {str(obj.id): {"corpse": isinstance(obj, Corpse), "entries": source_entries(obj)}
                 for model in (Corpse, DroppedLoot) for obj in model.objects.all()},
        "stale": stale_definitions(),
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False))
