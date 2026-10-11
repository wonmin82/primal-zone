"""서버 소유 월드 상태의 웹 표시용 스냅샷."""

from time import time

from typeclasses.enemies import room_enemies
from typeclasses.loot import can_take_entry, room_loot
from typeclasses.parties import invitation_for, online, party_for, request_for

from world.content import ENEMIES
from world.currency import currency_names, format_currency
from world.loot_assets import asset_name, asset_text
from world.loot_service import source_entries
from world.multiplayer import object_by_id
from world.targets import labels, room_objects


def player_name(identity):
    player = object_by_id(identity)
    return player.key if player else "탈퇴한 탐사자"


def loot_entries(source, player, now):
    from world.observation import can_inspect_loot, context_for

    if not can_inspect_loot(context_for(player, observed_at=now)):
        return []
    return [
        {
            **entry,
            "name": asset_name(entry),
            "amount_label": format_currency(entry["quantity"]) if entry["kind"] == "currency" else f"×{entry['quantity']}",
            "display_label": str(asset_text(entry)),
            "assigned_name": " · ".join(player_name(identity) for identity in entry["remaining_shares"]) if entry["kind"] == "currency" else player_name(entry["assigned_player"]),
            "protected": now < entry["protection_until"],
            "can_take": can_take_entry(entry, player, now),
        }
        for entry in source_entries(source)
    ]


def loot_controls(player, now, objects=None):
    """상세 보기와 웹 control이 동일한 현재 출처/entry 번호를 사용한다."""
    from world.observation import can_inspect_loot, context_for

    inspectable = can_inspect_loot(context_for(player, observed_at=now))
    objects = room_objects(player, observed_at=now) if objects is None else objects
    corpses = [obj for obj in room_loot(player.location) if obj in objects]
    ground = [obj for obj in room_loot(player.location, corpse=False) if obj in objects]
    corpse_controls = labels(corpses, lambda obj: "시체")
    ground_entries = [(obj, i, entry) for obj in ground for i, entry in enumerate(source_entries(obj))]

    def with_loot_controls(source):
        entries = loot_entries(source, player, now)
        pool = (
            [(source, i, entry) for i, entry in enumerate(source_entries(source))]
            if source in corpses
            else ground_entries
        )
        for index, entry in enumerate(entries):
            peers = [(obj, i) for obj, i, e in pool if (e["kind"], e["id"]) == (entry["kind"], entry["id"])
                     and (entry["kind"] != "currency" or can_take_entry(e, player, now))]
            suffix = f" {peers.index((source, index)) + 1}" if len(peers) > 1 and (source, index) in peers else ""
            target = (currency_names()[1] if entry["kind"] == "currency" else entry["name"]) + suffix
            prefix = corpse_controls[source.id] + "에서 " if source in corpses else ""
            entry.update(label=target, take_target=target,
                         display_label=entry["amount_label"] if entry["kind"] == "currency" else target + " " + entry["amount_label"],
                         take_command=prefix + target + " 가져")
        return entries

    return {
        **{
            source.id: {
                "label": corpse_controls[source.id],
                "take_command": corpse_controls[source.id] + "에서 모두 가져",
                "loot": with_loot_controls(source),
                "loot_obscured": not inspectable,
            }
            for source in corpses
        },
        **{source.id: {"loot": with_loot_controls(source)} for source in ground},
    }


def multiplayer_state(player, now=None):
    now = time() if now is None else now
    from typeclasses.interactables import ActionObject

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

    party = party_for(player)
    party_data = None
    if party:
        party.reconcile(now)
        state = party.state()
        from typeclasses.explorers import Explorer

        from world.targets import ordered
        player_controls = labels(ordered(Explorer.objects.all()))
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
            "members": [{"id": key, "name": player_name(key), "label": player_controls.get(key, player_name(key)),
                         "online": online(object_by_id(key))} for key in state["members"]],
            "loot_mode": state["loot_mode"],
            "max_size": 4,
            "leader_online": leader_online,
            "leader_offline_since": state["leader_offline_since"],
            "can_succeed": online(player) and state["leader"] != player.pk and not leader_online,
            "defender": {"id": defender.pk, "name": defender.key, "online": online(defender), "active": active} if defender else None,
            "join_requests": [{"id": key, "name": player_name(key), "label": player_controls.get(key, player_name(key)),
                               "expires_at": value["expires_at"]} for key, value in state["join_requests"].items()],
            "invitations": [{"id": key, "name": player_name(key), "expires_at": value["expires_at"]}
                            for key, value in state["invitations"].items()],
            "confirm_dissolve": bool(confirmation and now < confirmation["expires_at"]
                                     and confirmation["snapshot"] == (party.pk, state["leader"], tuple(state["members"]))),
        }
    invited, invitation = invitation_for(player, now)
    requested, request = request_for(player, now)
    return {
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
                "actions": obj.web_actions(player, controls[obj.id], now) + (
                    [{"label": "말 걸기", "command": "'" + dialogue_controls[obj.id] + "에게 안녕"}]
                    if dialogue_accessible(player, obj) else []
                ),
                "look_command": controls[obj.id] + " 봐",
            }
            for obj in objects
            if isinstance(obj, ActionObject)
        ],
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
