"""공유 교전, 피해, 기술, 정산과 복구를 실행하는 Combat Domain Service."""

from time import time

from evennia.utils import delay
from evennia.utils.dbserialize import deserialize

from world import presentation as view
from world import recovery, rules
from world import text as ft
from world.combat_contracts import (
    Combatant,
    Encounter,
    apply_tick,
    begin_encounter,
    plan_tick,
    settle_encounter,
)
from world.currency import format_currency
from world.domain_context import combat_timer_context, validate_context
from world.multiplayer import (
    CLAIM_TIMEOUT_SECONDS,
    COMBAT_INTERVAL,
    CORPSE_TTL_SECONDS,
    ENEMY_RECOVERY_DELAY_SECONDS,
    PARTICIPATION_TIMEOUT_SECONDS,
    RESPAWN_DELAY_SECONDS,
    _run_post_commit,
    after_change,
    object_by_id,
    world_change,
)


def deliver_combat_message(recipient, message):
    from world.actions.effects import deliver_read_only

    after_change(lambda: _run_post_commit(lambda: deliver_read_only(lambda: recipient.msg(message))))


def initialize_shared_combat(enemy):
    enemy.db.state = "alive"
    enemy.db.respawn_at = None
    enemy.db.claim = None
    enemy.db.claim_last_activity = 0
    enemy.db.combatants = []
    enemy.db.contribution = {}
    enemy.db.threat = {}
    enemy.db.enemy_round = 0
    enemy.db.next_attack_at = 0
    enemy.db.last_activity = 0
    enemy.db.suppressions = {}


def actor_moved(enemy):
    from world.duel import reconcile as reconcile_duel

    reconcile_duel(enemy)
    if not enemy.supports_shared_combat:
        return
    with world_change(isolate_callbacks=True):
        for identity in list(enemy.db.combatants or []):
            player = object_by_id(identity)
            if player and player.profile().get("combat_target") == enemy.id:
                leave_combat(player)
        enemy.db.suppressions = {}
        reconcile(enemy)


def active_players(enemy):
    return [
        player
        for identity in enemy.db.combatants
        if (player := object_by_id(identity))
        and player.location == enemy.location
        and player.sessions.count()
        and player.profile().get("combat_target") == enemy.id
    ]


def group_for(player):
    from typeclasses.parties import party_for

    party = party_for(player)
    return f"party:{party.id}" if party else f"player:{player.id}"


def can_attack(enemy, player):
    from world.duel import active_for, active_on

    return not active_on(enemy) and not active_for(player) and enemy.shared_combat_active and (
        enemy.combat_profile["combat_mode"] == "public"
        or enemy.db.claim in (None, group_for(player))
    )


def reward_groups(enemy, now):
    groups = {}
    for player in active_players(enemy):
        entry = enemy.db.contribution.get(player.id)
        group = group_for(player)
        if (
            not entry
            or entry["damage"] <= 0
            or now - entry["last_action_at"] > PARTICIPATION_TIMEOUT_SECONDS
        ):
            continue
        if entry["group"] != group:
            continue
        if enemy.combat_profile["combat_mode"] == "claimed" and group != enemy.db.claim:
            continue
        groups.setdefault(group, {})[player.id] = entry["damage"]
    return groups


def scale_boss(enemy, now):
    definition = enemy.combat_profile
    if not definition.get("boss"):
        return
    from world.loot_rules import boss_hp

    participants = sum(len(group) for group in reward_groups(enemy, now).values())
    count = max(enemy.db.scaling_participants or 1, participants)
    maximum = boss_hp(definition["hp"], count)
    enemy.hp += max(0, maximum - enemy.max_hp)
    enemy.max_hp = maximum
    enemy.db.scaling_participants = count


def engage(enemy, player, now=None):
    from world.duel import active_for, active_on

    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        if active_on(enemy) or active_for(player):
            raise rules.RuleError("대련 중에는 일반 교전을 시작할 수 없습니다.")
        reconcile(enemy, now)
        if enemy.db.state != "alive":
            raise rules.RuleError("아직 다시 나타나지 않은 적입니다.")
        if not enemy.shared_combat_active or player.location != enemy.location or not player.sessions.count():
            raise rules.RuleError("현재 전투에 참가할 수 없습니다.")
        profile = player.profile()
        from world.observation import can_perceive, context_for

        if profile.get("combat_target") != enemy.id and not can_perceive(enemy, context_for(player, observed_at=now)):
            raise rules.RuleError("지금은 그 상대를 식별할 수 없습니다. 광원을 사용하세요.")
        if profile.get("combat_target") not in (None, enemy.id):
            raise rules.RuleError("현재 상대에게서 먼저 도망하세요.")
        if not can_attack(enemy, player):
            owner = "다른 일행" if str(enemy.db.claim).startswith("party:") else "다른 탐사자"
            raise rules.RuleError(
                f"{enemy.key}{ft.particle(enemy.key, '은/는')} {owner}와 교전 중입니다."
            )
        if enemy.combat_profile["combat_mode"] == "claimed" and not enemy.db.claim:
            enemy.db.claim = group_for(player)
        if player.id not in enemy.db.combatants:
            player.accrue_recovery(profile, now)
            enemy.db.combatants = [*enemy.db.combatants, player.id]
            encounter = dict(enemy.db.encounter_state or {})
            if encounter.get("state") == "active":
                encounter["participants"] = tuple(dict.fromkeys((*encounter["participants"], str(player.pk))))
                enemy.db.encounter_state = encounter
            else:
                begin_encounter(enemy, (enemy, player))
            profile.update(
                combat_target=enemy.id,
                queued_action="attack",
                next_attack_at=max(profile["next_attack_at"], now + COMBAT_INTERVAL),
            )
            player.save_profile(profile)
            enemy.db.recovery_ready_at = None
            if not enemy.db.next_attack_at:
                enemy.db.next_attack_at = now + COMBAT_INTERVAL
                _reserve_tick(enemy, enemy.db.combat_generation, enemy.db.next_attack_at)
        if len(enemy.db.combatants) == 1 and not enemy.db.claim_last_activity:
            enemy.db.claim_last_activity = now
            enemy.db.last_activity = now
    after_change(player.schedule_combat)
    after_change(lambda: schedule_combat(enemy))


def _end_abandoned_encounter(enemy):
    state = enemy.db.encounter_state or {}
    if enemy.db.state != "alive" or enemy.hp <= 0 or state.get("state") != "active":
        return
    settle_encounter(Encounter(enemy, state["generation"]), {"kind": "disengaged"}, lambda _: None)
    enemy.db.next_attack_at = 0


def remove_combatant(enemy, player, now=None):
    now = time() if now is None else now
    enemy.db.combatants = [identity for identity in enemy.db.combatants if identity != player.id]
    threat = deserialize(enemy.db.threat)
    threat.pop(player.id, None)
    enemy.db.threat = threat
    contribution = deserialize(enemy.db.contribution)
    contribution.pop(player.id, None)
    enemy.db.contribution = contribution
    if not enemy.db.combatants:
        _end_abandoned_encounter(enemy)
        enemy.db.suppressions = {}
        enemy.db.recovery_ready_at = now + ENEMY_RECOVERY_DELAY_SECONDS
        state = deserialize(enemy.db.recovery) or recovery.initialize(now)
        # 재교전 중의 시간은 회복량에 더하지 않고 앞 구간의 소수 기여는 보존한다.
        recovery.accrue(state, now, {})
        enemy.db.recovery = state
        enemy.db.claim = None
        enemy.db.claim_last_activity = 0
        after_change(lambda: stop_combat_timer(enemy))
    after_change(lambda: schedule_lifecycle(enemy))


def reconcile(enemy, now=None):
    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        # The old unowned effect cannot be assigned to a source safely.
        enemy.attributes.remove("suppression")
        if enemy.db.claim and now - enemy.db.claim_last_activity >= CLAIM_TIMEOUT_SECONDS:
            for player in active_players(enemy):
                leave_combat(player, now=now)
            enemy.db.claim = None
            enemy.db.claim_last_activity = 0
        active = active_players(enemy) if enemy.shared_combat_active else []
        active_ids = [player.id for player in active]
        for identity in list(enemy.db.combatants):
            if identity not in active_ids:
                player = object_by_id(identity)
                if player and player.profile().get("combat_target") == enemy.id:
                    leave_combat(player, now=now)
                elif player:
                    remove_combatant(enemy, player, now=now)
                else:
                    enemy.db.combatants = [key for key in enemy.db.combatants if key != identity]
        if not enemy.db.combatants:
            _end_abandoned_encounter(enemy)
            enemy.db.suppressions = {}
            enemy.db.claim = None
            enemy.db.claim_last_activity = 0
            enemy.db.threat = {}
            if enemy.db.state == "alive" and enemy.db.last_activity and enemy.db.recovery is None:
                enemy.db.recovery = recovery.initialize(enemy.db.last_activity)
                enemy.db.recovery_ready_at = enemy.db.last_activity + ENEMY_RECOVERY_DELAY_SECONDS
        if (
            not enemy.db.combatants
            and enemy.db.last_activity
            and now >= (enemy.db.recovery_ready_at or enemy.db.last_activity + ENEMY_RECOVERY_DELAY_SECONDS)
        ):
            if enemy.db.state == "alive":
                enemy.db.enemy_round = 0
                enemy.db.next_attack_at = 0
                enemy.db.threat = {}
                enemy.db.contribution = {}
                enemy.db.last_activity = 0
        if enemy.db.state == "alive" and not enemy.db.combatants and 0 < enemy.hp < enemy.max_hp:
            state = deserialize(enemy.db.recovery)
            ready_at = enemy.db.recovery_ready_at
            if state is None:
                start = enemy.db.last_activity or now
                state = recovery.initialize(start)
                ready_at = start + ENEMY_RECOVERY_DELAY_SECONDS
                enemy.db.recovery_ready_at = ready_at
            recovery.accrue(state, now, {}, [{"started_at": ready_at or now,
                "expires_at": max(now, ready_at or now) + 1,
                "hp_per_minute": recovery.enemy_rate(enemy.max_hp)}])
            resources = {"hp": enemy.hp, "mental": 0, "recovery": state}
            recovery.commit(resources, {"max_hp": enemy.max_hp, "max_mental": 0})
            enemy.hp = resources["hp"]
            enemy.db.recovery = state
        if enemy.db.state == "alive" and not enemy.db.combatants and not enemy.db.contribution and enemy.hp == enemy.max_hp:
            enemy.db.scaling_participants = 1
            enemy.max_hp = enemy.combat_profile["hp"]
            enemy.hp = enemy.max_hp
        if enemy.db.state == "respawning" and enemy.db.respawn_at <= now:
            enemy.db.suppressions = {}
            enemy.db.combat_lifecycle = (enemy.db.combat_lifecycle or 0) + 1
            enemy.db.state = "alive"
            enemy.db.scaling_participants = 1
            enemy.max_hp = enemy.combat_profile["hp"]
            enemy.hp = enemy.max_hp
            enemy.db.respawn_at = None
            enemy.db.enemy_round = 0
            enemy.db.next_attack_at = 0
            enemy.db.last_activity = 0
            enemy.db.contribution = {}
            enemy.db.threat = {}
            enemy.db.recovery = None
            enemy.db.recovery_ready_at = None
    after_change(lambda: schedule_lifecycle(enemy))


def receive_attack(enemy, player, now=None, rng=None):
    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        reconcile(enemy, now)
        if not enemy.shared_combat_active or player not in active_players(enemy):
            leave_combat(player)
            return
        profile = player.profile()
        if now < profile["next_attack_at"]:
            return
        player.accrue_recovery(profile, now)
        recipient = player
        recipient_profile = None
        error = None
        if profile["queued_action"] == "heal":
            from world.skill_services import heal_target

            try:
                recipient = heal_target(player, profile.get("heal_target"))
                if recipient is not player:
                    recipient_profile = recipient.profile()
                    recipient.accrue_recovery(recipient_profile, now)
            except rules.RuleError as failure:
                error = str(failure)
        if error:
            profile.update(queued_action="attack", next_attack_at=now + COMBAT_INTERVAL)
            profile["player_round"] += 1
            damage, outcome = 0, {"action": "error", "message": error}
        else:
            from world.firearm_service import player_attack

            damage, outcome = player_attack(
                player, profile, enemy.combat_definition_id, now, COMBAT_INTERVAL, rng, recipient_profile
            )
        profile["heal_target"] = None
        if recipient_profile is not None and outcome["action"] == "heal":
            recipient.save_profile(recipient_profile)
            outcome["recipient"] = recipient.key
            deliver_combat_message(recipient, f"{player.key}의 치료로 HP {outcome['amount']}을 회복했다.")
        # 현재 공격의 기여를 먼저 등록해 late join의 증가분도 사망 판정 전에 적용한다.
        contribution = deserialize(enemy.db.contribution)
        previous = contribution.get(player.id, {"damage": 0})
        contribution[player.id] = {"damage": previous["damage"] + damage,
                                   "last_action_at": now, "group": group_for(player)}
        enemy.db.contribution = contribution
        scale_boss(enemy, now)
        actual = min(enemy.hp, damage)
        contribution[player.id]["damage"] = previous["damage"] + actual
        enemy.db.contribution = contribution
        damage = actual
        Combatant(enemy).apply(lambda state: state.update(hp=state["hp"] - damage))
        if "suppression" in outcome:
            from world.progression import apply_suppression

            effects, status = apply_suppression(
                deserialize(enemy.db.suppressions), player.id, outcome["suppression"]["rank"],
                bool(enemy.combat_profile.get("boss")), effect=outcome["suppression"],
            )
            enemy.db.suppressions = effects
            outcome["suppression"] = effects[str(player.id)]
            outcome["suppression_status"] = status
        enemy.db.last_activity = now
        enemy.db.claim_last_activity = now
        threat = deserialize(enemy.db.threat)
        threat[player.id] = threat.get(player.id, 0) + damage
        enemy.db.threat = threat
        player.save_profile(profile)
        message = view.outgoing_attack(profile, enemy.key, outcome, damage)
        deliver_combat_message(player, message)
        if enemy.hp <= 0:
            _finish_death(enemy, now, rng)
    after_change(lambda: broadcast_state(enemy))


def duel_round(actor, player, state, now, rng):
    """공통 공격·장비·자원 정책을 대련의 전투 상태에 적용한다."""
    from world.firearm_service import player_attack
    from world.progression import apply_suppression, combined_suppression, consume_suppressions

    profile = player.profile()
    player.accrue_recovery(profile, now)
    transient = {key: profile[key] for key in (
        "hp", "combat_target", "queued_action", "insight", "next_attack_at", "player_round",
    )}
    hp_recovery = {key: profile["recovery"][key]["hp"] for key in ("ready", "credit")}
    profile.update(hp=state["player_hp"], combat_target=actor.pk,
                   queued_action=state["queued_skill"], insight=state["insight"])
    enemy_profile = actor.combat_profile
    damage, outcome = player_attack(
        player, profile, actor.combat_definition_id, now, COMBAT_INTERVAL, rng, enemy_profile=enemy_profile,
    )
    state["actor_hp"] -= min(state["actor_hp"], damage)
    state["queued_skill"] = "attack"
    state["insight"] = profile["insight"]
    publish_attack = view.outgoing_attack(profile, actor.key, outcome, damage)
    deliver_combat_message(player, publish_attack)
    effects = state["suppressions"]
    if "suppression" in outcome:
        effect = outcome["suppression"]
        effects, _ = apply_suppression(effects, player.pk, effect["rank"], bool(enemy_profile.get("boss")),
                                       effect=effect)
    kind = None
    if state["actor_hp"] <= 0:
        kind = "victory"
    else:
        state["enemy_round"] += 1
        reduction = combined_suppression(effects, bool(enemy_profile.get("boss")))
        result = rules.enemy_attack(profile, actor.combat_definition_id, state["enemy_round"], now, rng,
                                    reduction, enemy_profile=enemy_profile)
        state["suppressions"] = consume_suppressions(effects)
        deliver_combat_message(player, f"{actor.key}의 반격으로 대련 체력 {result['damage']}을 잃었습니다.")
        if result["defeated"]:
            kind = "defeat"
    state["player_hp"] = max(0, profile["hp"])
    # 공용 HP·전투 회차는 그대로 두고 실제 사용한 자원과 장비 상태를 저장한다.
    profile.update(transient)
    for key, value in hp_recovery.items():
        profile["recovery"][key]["hp"] = value
    player.save_profile(profile)
    return kind


def finish_death(enemy, now, rng=None):
    with world_change(isolate_callbacks=True):
        return _finish_death(enemy, now, rng)


def _finish_death(enemy, now, rng=None):
    if enemy.db.state != "alive" or enemy.hp > 0:
        return
    state = enemy.db.encounter_state or {}
    encounter = (Encounter(enemy, state["generation"]) if state.get("state") == "active"
                 else begin_encounter(enemy, (enemy, *active_players(enemy))))
    return settle_encounter(encounter, {"kind": "death"}, lambda _: _settle_death(enemy, now, rng))


def _settle_death(enemy, now, rng):
    from typeclasses.loot import Corpse

    groups = reward_groups(enemy, now)
    fallen = ft.text(
        ft.named("hostile", enemy.key, "이/가"), " 더는 버티지 못하고 바닥에 쓰러졌다."
    )
    for participant in active_players(enemy):
        deliver_combat_message(participant, fallen)
    enemy.db.state = "respawning"
    enemy.db.suppressions = {}
    enemy.db.respawn_at = now + CORPSE_TTL_SECONDS + RESPAWN_DELAY_SECONDS
    definition = enemy.combat_profile
    for identity, xp in rules.reward_allocation(
        definition["xp"], groups
    ).items():
        player = object_by_id(identity)
        profile = player.profile()
        player.accrue_recovery(profile, now)
        rules.gain_xp(profile, xp)
        profile["kills"] += 1
        if definition.get("boss_quest"):
            profile["quests"][definition["boss_quest"]]["boss_defeated"] = True
        player.save_profile(profile)
        message = view.reward(xp)
        deliver_combat_message(player, message)
    Corpse.from_enemy(enemy, groups, now, rng)
    for player in active_players(enemy):
        leave_combat(player, now=now)
    after_change(lambda: stop_combat_timer(enemy))
    after_change(lambda: schedule_lifecycle(enemy))


def enemy_tick(enemy, now=None, rng=None):
    now = time() if now is None else now
    with world_change(isolate_callbacks=True):
        reconcile(enemy, now)
        players = active_players(enemy)
        if not enemy.shared_combat_active or not players or now < enemy.db.next_attack_at:
            return
        target = min(players, key=lambda player: (-enemy.db.threat.get(player.id, 0), player.id))
        from typeclasses.parties import party_for
        party = party_for(target)
        if party:
            target = party.defense_target(enemy, target, players)
        enemy.db.enemy_round += 1
        enemy.db.next_attack_at = now + COMBAT_INTERVAL
        result_profile = target.profile()
        target.accrue_recovery(result_profile, now)
        from world.progression import combined_suppression, consume_suppressions

        effects = deserialize(enemy.db.suppressions)
        reduction = combined_suppression(effects, bool(enemy.combat_profile.get("boss")))
        enemy.db.suppressions = consume_suppressions(effects)
        result = rules.enemy_attack(
            result_profile, enemy.combat_definition_id, enemy.db.enemy_round, now, rng, reduction
        )
        lost = rules.apply_defeat(result_profile) if result["defeated"] else 0
        target.save_profile(result_profile)
        message = ft.text(
            ft.named("hostile", enemy.key, "이/가"),
            f" {enemy.combat_profile.get('special_verb', '거세게 돌진해')} "
            if result["charged"] else " 달려들어 ",
            f"{result['damage']}의 피해를 입혔다.",
        )
        deliver_combat_message(target, message)
        if result["defeated"]:
            from world.bootstrap import get_room

            leave_combat(target, now=now)
            destination = get_room("infirmary")
            rescue = (
                "탐사대가 본부 3층 의무실로 구조했습니다.\n"
                + (f"{format_currency(lost)}을 잃었습니다.\n" if lost else "")
                + f"응급 처치로 체력 {rules.DEFEAT_RECOVERY_HP}을 회복했습니다. 추가 회복이 필요합니다."
            )
            deliver_combat_message(target, rescue)
            if destination is None or not target.move_to(destination, quiet=True, move_type="defeat"):
                raise RuntimeError("패배 후 의무실 이동을 완료하지 못했습니다.")
            after_change(target.request_prompt)
        if rules.boss_telegraph(enemy.combat_definition_id, enemy.db.enemy_round):
            for player in active_players(enemy):
                message = ft.text(
                    ft.token("warning", "! "),
                    ft.named("hostile", enemy.key, "이/가"),
                    " ",
                    enemy.combat_profile.get("telegraph", "몸을 낮추고 돌진할 자세를 취한다."),
                )
                deliver_combat_message(player, message)
    after_change(lambda: broadcast_state(enemy))


def schedule_combat(enemy):
    if not enemy.shared_combat_active or not active_players(enemy) or enemy.ndb.combat_task:
        return
    generation = enemy.db.combat_generation
    if generation is None:
        return
    encounter = Encounter(enemy, generation)
    pending = encounter.state.get("pending")
    if pending and not pending["completed"]:
        _schedule_reserved_tick(encounter, pending["operation_id"], pending["due_at"])


def _reserve_tick(enemy, generation, due_at):
    plan_tick(Encounter(enemy, generation), operation_id=f"tick:{due_at}", due_at=due_at,
              trigger=_schedule_reserved_tick)


def _schedule_reserved_tick(encounter, operation_id, due_at):
    enemy = encounter.owner
    state = enemy.db.encounter_state or {}
    pending = state.get("pending") or {}
    if (state.get("state") == "active" and state.get("generation") == encounter.generation
            and pending.get("operation_id") == operation_id and not pending.get("completed")
            and pending.get("due_at") == due_at == enemy.db.next_attack_at
            and enemy.shared_combat_active and not enemy.ndb.combat_task):
        _schedule_tick(enemy, encounter.generation, due_at)


def _schedule_tick(enemy, generation, due_at):
    enemy.ndb.combat_task = delay(max(0.05, due_at - time()), enemy.combat_tick, generation, due_at)


def combat_tick(enemy, generation, due_at):
    if generation is None or generation != enemy.db.combat_generation or due_at != enemy.db.next_attack_at:
        return
    encounter = Encounter(enemy, generation)
    state = encounter.state
    pending = state.get("pending") or {}
    operation_id = f"tick:{due_at}"
    if (state.get("state") != "active" or state.get("generation") != generation
            or pending.get("operation_id") != operation_id or pending.get("due_at") != due_at
            or pending.get("completed")):
        return
    enemy.ndb.combat_task = None
    now = time()
    if now >= due_at:
        context = combat_timer_context(
            enemy, operation_id=operation_id, domain_scope=encounter.identity, generation=generation, clock=lambda: now,
        )
        with world_change(isolate_callbacks=True):
            apply_tick(encounter, context, lambda _: enemy_tick(enemy, now=now))
            deadline = enemy.db.next_attack_at
            if enemy.shared_combat_active and active_players(enemy) and deadline > now:
                _reserve_tick(enemy, generation, deadline)
    schedule_combat(enemy)


def stop_combat_timer(enemy):
    task = enemy.ndb.combat_task
    enemy.ndb.combat_task = None
    if task:
        task.remove()


def schedule_lifecycle(enemy):
    deadline = (
        enemy.db.respawn_at
        if enemy.db.state == "respawning"
        else recovery.next_boundary(max(time(), enemy.db.recovery_ready_at or time()))
        if not enemy.db.combatants and enemy.db.state == "alive" and 0 < enemy.hp < enemy.max_hp
        and enemy.location and any(getattr(obj, "push_state", None) and obj.sessions.count()
                                  for obj in enemy.location.contents)
        else None
    )
    reservation = (enemy.db.combat_generation, deadline) if deadline else None
    if enemy.ndb.lifecycle_task and enemy.ndb.lifecycle_reservation != reservation:
        enemy.ndb.lifecycle_task.remove()
        enemy.ndb.lifecycle_task = None
        enemy.ndb.lifecycle_reservation = None
    if reservation and not enemy.ndb.lifecycle_task:
        enemy.ndb.lifecycle_reservation = reservation
        enemy.ndb.lifecycle_task = delay(
            max(0.05, deadline - time()), enemy.lifecycle_tick, *reservation,
        )


def lifecycle_tick(enemy, generation, deadline):
    if enemy.ndb.lifecycle_reservation != (generation, deadline):
        return
    enemy.ndb.lifecycle_task = None
    enemy.ndb.lifecycle_reservation = None
    if enemy.db.combat_generation != generation:
        schedule_lifecycle(enemy)
        return
    reconcile(enemy)
    broadcast_state(enemy)


def broadcast_state(enemy):
    if enemy.location:
        for obj in enemy.location.contents:
            if hasattr(obj, "push_state"):
                _run_post_commit(obj.push_state)


def combat_target(player):
    from typeclasses.actors import Actor

    enemy = object_by_id(player.profile_snapshot().get("combat_target"))
    return enemy if isinstance(enemy, Actor) and enemy.supports_shared_combat else None


def combat_snapshot(player):
    enemy = combat_target(player)
    if not enemy or not enemy.shared_combat_active:
        return None
    return {
        "id": enemy.id,
        "enemy": enemy.combat_definition_id,
        "name": enemy.key,
        "hp": enemy.hp,
        "max_hp": enemy.max_hp,
        "round": enemy.db.enemy_round,
        "state": enemy.db.state,
        "telegraph": rules.boss_telegraph(enemy.combat_definition_id, enemy.db.enemy_round),
    }


def start_combat(player, enemy_id):
    from world.lifecycle import reconcile_room

    reconcile_room(player.location)

    enemies = room_enemies(player.location)
    enemy = enemy_id if enemy_id in enemies else next(
        (obj for obj in enemies if obj.combat_definition_id == enemy_id), None
    )
    if not enemy:
        raise rules.RuleError("이곳에는 공격할 수 있는 상대가 없습니다.")
    engage(enemy, player)
    message = ft.text(
        ft.named("hostile", enemy.key, "과/와"),
        " 교전을 시작했다. 기본 공격은 2.5초마다 이어진다.",
    )
    deliver_combat_message(player, message)
    after_change(player.push_state)


def leave_combat(player, now=None):
    with world_change():
        enemy = combat_target(player)
        if enemy:
            remove_combatant(enemy, player, now=now)
        after_change(player.stop_combat_timer)
        profile = player.profile()
        if profile.get("combat_target"):
            player.accrue_recovery(profile, now)
            profile.update(combat_target=None, queued_action="attack", insight=None, heal_target=None)
            player.save_profile(profile)


def combat_reservation(player):
    profile = player.profile_snapshot()
    enemy = combat_target(player)
    return (profile.get("combat_target"), enemy.db.combat_generation if enemy else None,
            profile["next_attack_at"])


def player_combat_tick(player, target_id, generation, due_at, *, now):
    reservation = (target_id, generation, due_at)
    if player.ndb.combat_reservation != reservation:
        return
    player.ndb.combat_task = None
    player.ndb.combat_reservation = None
    current = combat_reservation(player)
    if current[0] != target_id or current[2] != due_at or current[1] not in (generation, None):
        player.schedule_combat()
        return
    enemy = combat_target(player)
    if enemy is None or not player.sessions.count():
        leave_combat(player, now=now)
        return
    if now >= due_at:
        encounter = Encounter(enemy, generation)
        with world_change(isolate_callbacks=True):
            state = encounter.state
            if (state.get("state") == "active" and state.get("generation") == generation
                    and str(player.pk) in state["participants"]):
                context = combat_timer_context(
                    player, target=enemy, operation_id=f"player:{player.pk}:tick:{due_at}",
                    domain_scope=encounter.identity, generation=generation, clock=lambda: now,
                )
                validate_context(
                    context, "combat.tick", actor=player, target=enemy, domain_scope=encounter.identity,
                    generation=generation, permission=lambda _: combat_reservation(player) == reservation,
                )
                receive_attack(enemy, player, now=now)
            else:
                leave_combat(player, now=now)
    player.schedule_combat()


def resolve_combat_round(player, rng=None, now=None):
    enemy = combat_target(player)
    if enemy:
        receive_attack(enemy, player, now=now, rng=rng)
    else:
        leave_combat(player)


def room_enemies(room, alive_only=True):
    from typeclasses.actors import Actor

    from world.targets import ordered

    if not room:
        return []
    return ordered(
        [
            obj
            for obj in room.contents
            if isinstance(obj, Actor) and obj.supports_shared_combat and (not alive_only or obj.shared_combat_active)
        ]
    )
