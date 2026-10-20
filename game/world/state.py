"""서버 소유 월드 상태의 웹 표시용 스냅샷."""

from time import time

from typeclasses.enemies import room_enemies
from typeclasses.loot import room_loot
from typeclasses.parties import invitation_for, online, party_for, request_for, sessions_ready

from world.content import ENEMIES
from world.multiplayer import object_by_id
from world.targets import labels, room_objects


def player_name(identity):
    player = object_by_id(identity)
    return player.key if player else "탈퇴한 탐사자"


def loot_entries(source, player, now):
    """도메인 presenter가 허용한 항목만 상세 보기에도 제공한다."""
    from world.actions.loot_presentation import visible_entries

    return visible_entries(source, player, now)


def loot_controls(player, now, objects=None):
    """상세 보기와 웹은 동일한 영속 번호·권리·안정 참조를 사용한다."""
    from world.actions.loot_presentation import source_controls

    return source_controls(player, now, objects)


def multiplayer_state(player, now=None):
    now = time() if now is None else now
    from typeclasses.interactables import ActionObject

    from world.doors import web_controls as door_controls
    from world.lifecycle import reconcile_room
    from world.npc_dialogue import accessible as dialogue_accessible
    from world.npc_dialogue import supports as dialogue_supports

    reconcile_room(player.location, now)
    objects = room_objects(player, observed_at=now)
    enemies = [obj for obj in room_enemies(player.location) if obj in objects]
    corpses = [obj for obj in room_loot(player.location) if obj in objects]
    ground = [obj for obj in room_loot(player.location, corpse=False) if obj in objects]
    controls = labels(objects)
    dialogue_controls = labels([obj for obj in objects if dialogue_supports(obj) and obj.access(player, "view")])
    loot = loot_controls(player, now, objects)
    from world.actions.loot_presentation import all_controls
    from world.actions.manifest import get_index
    from world.actions.presentation import action_controls
    from world.selection_numbers.api import descriptor

    action_rows = action_controls(player, get_index(), now)
    loot_actions = all_controls(player, now, objects)

    def object_actions(obj):
        if not getattr(obj, "action_provider_definition", None):
            return obj.web_actions(player, controls[obj.id], now)
        record = descriptor(obj)
        if not record:
            return []
        from world.actions.room_npc_presentation import sort_controls

        rows = [row for row in action_rows
                if row["action"]["roles"]["provider"][0]["identity"] == str(obj.pk)
                and row["action"]["roles"]["provider"][0]["kind"] == "object"]
        if obj.action_provider_definition in ("world.incinerator", "world.container", "world.personal_locker"):
            rows.insert(0, {"label": "봐", "command": controls[obj.id] + " 봐"})
        return sort_controls(obj, rows)

    party = party_for(player)
    party_data = None
    if party:
        state = party.state()
        from typeclasses.explorers import Explorer

        from world.targets import ordered
        player_controls = labels(ordered(Explorer.objects.all()))
        member_controls = labels(ordered([member for identity in state["members"]
                                         if (member := object_by_id(identity))]))
        defender = object_by_id(state["tactics"].get("defender_id"))
        defended_enemy = defender.combat_target() if defender else None
        participants = defended_enemy.active_players() if defended_enemy else []
        default = min(participants, key=lambda obj: (-defended_enemy.db.threat.get(obj.id, 0), obj.id)) if participants else None
        active = bool(default and party.defense_target(defended_enemy, default, participants) == defender)
        leader_online = online(object_by_id(state["leader"]))
        confirmation = player.ndb.party_dissolve_request
        party_data = {
            "id": party.id,
            "leader": state["leader"],
            "leader_name": player_name(state["leader"]),
            "is_leader": state["leader"] == player.id,
            "members": [{"id": key, "name": player_name(key), "label": member_controls.get(key, player_name(key)),
                         "online": online(object_by_id(key))} for key in state["members"]],
            "loot_mode": state["loot_mode"],
            "max_size": 4,
            "leader_online": leader_online,
            "leader_offline_since": state["leader_offline_since"],
            "can_succeed": sessions_ready() and online(player) and state["leader"] != player.pk and not leader_online,
            "defender": {"id": defender.pk, "name": defender.key, "online": online(defender), "active": active} if defender else None,
            "join_requests": [{"id": key, "name": player_name(key), "label": player_controls.get(key, player_name(key)),
                               "expires_at": value["expires_at"]} for key, value in state["join_requests"].items()
                              if now < value["expires_at"]],
            "invitations": [{"id": key, "name": player_name(key), "expires_at": value["expires_at"]}
                            for key, value in state["invitations"].items() if now < value["expires_at"]],
            "confirm_dissolve": bool(confirmation and now < confirmation["expires_at"]
                                     and confirmation["snapshot"] == (party.pk, state["leader"], tuple(state["members"]))),
        }
    invited, invitation = invitation_for(player, now, reconcile=False)
    requested, request = request_for(player, now, reconcile=False)
    return {
        "server_now": now,
        "loot_actions": loot_actions,
        "action_controls": [row for row in action_rows if not (
            row["action"]["roles"].get("provider", [{}])[0].get("kind") == "door" or
            row["action"]["roles"].get("provider", [{}])[0].get("kind") == "object" and
            row["action"]["roles"]["provider"][0]["identity"] in
            {str(obj.pk) for obj in objects if getattr(obj, "action_provider_definition", None)})],
        "enemies": [
            {
                "id": enemy.id,
                "enemy_id": enemy.db.enemy_id,
                "name": enemy.key,
                "label": controls[enemy.id],
                "attack_command": controls[enemy.id] + " 공격",
                "look_command": controls[enemy.id] + " 봐",
                "hp": enemy.db.hp,
                "max_hp": enemy.db.max_hp,
                "state": enemy.db.state,
                "claim": enemy.db.claim,
                "combatants": list(enemy.db.combatants),
                "mode": ENEMIES[enemy.db.enemy_id]["combat_mode"],
                "can_attack": enemy.can_attack(player),
            }
            for enemy in enemies
        ],
        "corpses": [
            {
                "id": corpse.id,
                "name": corpse.key,
                **loot[corpse.id],
                "look_command": loot[corpse.id]["label"] + " 봐",
                "decay_at": corpse.db.decay_at,
            }
            for corpse in corpses
        ],
        "ground_loot": [
            {"id": dropped.id, **loot[dropped.id]} for dropped in ground
        ],
        "interactables": [
            {
                "name": obj.key,
                "label": controls[obj.id],
                "role": obj.semantic_role,
                "actions": object_actions(obj) + (
                    [{"label": "말 걸기", "command": "'" + dialogue_controls[obj.id] + "에게 안녕"}]
                    if dialogue_accessible(player, obj) else []
                ),
                "look_command": controls[obj.id] + " 봐",
            }
            for obj in objects
            if isinstance(obj, ActionObject)
        ] + door_controls(player, now, action_rows=action_rows),
        "party": party_data,
        "invitation": {
            "party_id": invited.id,
            "inviter": player_name(invitation["inviter"]),
            "expires_at": invitation["expires_at"],
        }
        if invited
        else None,
        "join_request": {"party_id": requested.pk, "expires_at": request["expires_at"]} if requested else None,
        "combat_target": player.combat_snapshot(),
    }


def _action_controls(player):
    from world.actions.manifest import get_index
    from world.actions.presentation import action_controls

    return action_controls(player, get_index())
