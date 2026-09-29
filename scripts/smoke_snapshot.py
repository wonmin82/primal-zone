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
    from world.bootstrap import get_room, stale_definitions
    from world.environment_state import lifecycle_script

    script = lifecycle_script()
    return {
        "players": {player.key: {"profile": player.profile_snapshot(), "zone": player.zone,
                                  "home": player.home.db.zone_id, "id": player.id}
                    for player in Explorer.objects.all() if player.key != "admin"},
        "elevator": get_room("support_elevator").db.current_stop,
        "box": deserialize(search_tag("shared_container", category="primal_interactable")[0].db.items),
        "facilities": deserialize(script.db.facilities),
        "clock": deserialize(script.db.environment)["clock"],
        "enemies": {str(enemy.id): {"state": enemy.db.state, "combatants": list(enemy.db.combatants or []),
                                    "claim": deserialize(enemy.db.claim)} for enemy in Enemy.objects.all()},
        "loot": {str(obj.id): {"corpse": isinstance(obj, Corpse), "entries": deserialize(obj.db.entries)}
                 for model in (Corpse, DroppedLoot) for obj in model.objects.all()},
        "stale": stale_definitions(),
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False))
