"""서버 소유 월드 상태의 웹 표시용 스냅샷."""

from time import time

from typeclasses.enemies import room_enemies
from typeclasses.loot import recipient_for, room_loot
from typeclasses.parties import invitation_for, party_for

from world.content import ENEMIES, ITEMS
from world.multiplayer import object_by_id


def player_name(identity):
    player = object_by_id(identity)
    return player.key if player else "탈퇴한 탐사자"


def loot_entries(source, player, now):
    return [
        {
            **dict(entry),
            "name": ITEMS[entry["item"]]["name"],
            "assigned_name": player_name(entry["assigned_player"]),
            "protected": now < entry["protection_until"],
            "can_take": bool(recipient_for(entry, player, now)),
        }
        for entry in source.db.entries
    ]


def multiplayer_state(player, now=None):
    now = time() if now is None else now
    party = party_for(player)
    party_data = None
    if party:
        state = party.state()
        party_data = {
            "id": party.id,
            "leader": state["leader"],
            "leader_name": player_name(state["leader"]),
            "is_leader": state["leader"] == player.id,
            "members": [{"id": key, "name": player_name(key)} for key in state["members"]],
            "loot_mode": state["loot_mode"],
        }
    invited, invitation = invitation_for(player, now)
    return {
        "enemies": [
            {
                "id": enemy.id,
                "enemy_id": enemy.db.enemy_id,
                "name": enemy.key,
                "hp": enemy.db.hp,
                "max_hp": enemy.db.max_hp,
                "state": enemy.db.state,
                "claim": enemy.db.claim,
                "combatants": list(enemy.db.combatants),
                "mode": ENEMIES[enemy.db.enemy_id]["combat_mode"],
                "can_attack": enemy.can_attack(player),
            }
            for enemy in room_enemies(player.location)
        ],
        "corpses": [
            {
                "id": corpse.id,
                "name": corpse.key,
                "decay_at": corpse.db.decay_at,
                "loot": loot_entries(corpse, player, now),
            }
            for corpse in room_loot(player.location)
        ],
        "ground_loot": [
            {"id": dropped.id, "loot": loot_entries(dropped, player, now)}
            for dropped in room_loot(player.location, corpse=False)
        ],
        "party": party_data,
        "invitation": {
            "party_id": invited.id,
            "inviter": player_name(invitation["inviter"]),
            "expires_at": invitation["expires_at"],
        }
        if invited
        else None,
        "combat_target": player.combat_snapshot(),
    }
