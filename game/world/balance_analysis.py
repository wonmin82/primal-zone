"""Phase 7C 재현용 pure 분석. 피해/성장/회복/가격은 실제 규칙을 호출한다.

DB/scheduler simulation이 아니다. 동시 tick은 player-first/enemy-first를 번갈아
계산하고 seed별 전투 variation을 기록한다. Reload 성공은 전투 기회 하나를 소비한다.
"""

from math import ceil
from random import Random
from statistics import mean

from world import equipment, recovery, rules
from world import progression as pg
from world.balance_sanity import expected_loot_value
from world.content import ENEMIES, ITEMS
from world.final_content import package_costs
from world.firearms import STANDARD_MAGAZINES
from world.loot_rules import boss_hp
from world.timing import PRODUCTION_TIMING

INTERVAL = PRODUCTION_TIMING["COMBAT_INTERVAL"]


def build_specs():
    specs = {"minimal": {"level": 1, "gear": ("explorer_machete", "expedition_workwear"),
                         "attributes": {}, "skills": {}, "policy": "basic"}}
    for tier, level in ((1, 4), (2, 7)):
        common = (("reinforced_vest", "shock_absorbing_gloves", "non_slip_boots", "expedition_tag")
                  if tier == 1 else ("tactical_protective_suit", "strike_assist_gloves", "stabilizing_boots", "expedition_tag"))
        blade = "cutting_machete" if tier == 1 else "jungle_longblade"
        hands = {"balanced": (blade,), "2h": ("pioneer_spear" if tier == 1 else "shattering_spear",),
                 "shield": (blade, "folding_shield" if tier == 1 else "composite_shield"),
                 "firearm": ("guard_carbine" if tier == 1 else "exploration_carbine",),
                 "pistol": ("scout_pistol" if tier == 1 else "tactical_pistol", "folding_shield" if tier == 1 else "composite_shield"),
                 "support": (blade, "portable_analyzer" if tier == 1 else "emergency_injector")}
        for role, hand in hands.items():
            attrs = {"strength": 4, "constitution": 6 if tier == 1 else 12}
            ranks = {"attack": 2 if tier == 1 else 3, "defense": 2 if tier == 1 else 3,
                     "shooting" if role in ("firearm", "pistol") else "heavy": 2 if tier == 1 else 3}
            gear = (*hand, *common)
            if role == "support":
                attrs = {"constitution": 6 if tier == 1 else 8, "wisdom": 4 if tier == 1 else 8}
                ranks = {"heal": 2 if tier == 1 else 3, "breathing": 2, "defense": 2 if tier == 1 else 3}
                gear = (*hand, common[0], "emergency_belt" if tier == 1 else "medical_tactical_belt",
                        "survival_module" if tier == 1 else "mental_stability_module", "expedition_tag")
            specs[f"t{tier}_{role}"] = {"level": level, "gear": gear, "attributes": attrs,
                                       "skills": ranks, "policy": "firearm" if role == "pistol" else role}
    return specs


def build(spec):
    items = tuple(equipment.item_snapshot(identity, ITEMS[identity], item_id=str(index), sequence=index)
                  for index, identity in enumerate(spec["gear"], 1))
    equipment.validate_loadout(items)
    snapshot = equipment.EquipmentSnapshot(items, items, next(item.identity for item in items if item.role == "weapon"))
    profile = equipment.EquipmentProfile(rules.new_profile(), snapshot)
    profile["xp"] = rules.xp_threshold(spec["level"])
    for attribute, value in spec["attributes"].items():
        profile["attributes"][attribute]["allocated"] = value
    profile["skills"].update(spec["skills"])
    assert sum(spec["attributes"].values()) <= pg.attribute_points(spec["level"])
    assert sum(rank - 1 for rank in spec["skills"].values()) <= spec["level"] - 1
    profile.update(hp=rules.stats(profile)["max_hp"], mental=rules.stats(profile)["max_mental"], combat_target=1)
    profile["inventory"]["bandage"] = 8
    profile["recovery"] = recovery.initialize(0)
    return profile


def choose_action(profile, policy, now, recipient):
    candidates = []
    if policy == "support":
        if recipient["hp"] < rules.stats(recipient)["max_hp"] * .7:
            candidates.append("heal")
        if profile["mental"] < pg.mental_cost("heal", rules.level_of(profile)) * 2:
            candidates.append("breathing")
    if policy != "basic":
        if profile["hp"] < rules.stats(profile)["max_hp"] * .45:
            candidates.append("bandage")
        if policy != "support":
            candidates.append("shooting" if policy == "firearm" else "heavy")
    for action in candidates:
        try:
            rules.validate_skill_action(profile, action, now, recipient if action == "heal" else None)
            return action
        except rules.RuleError:
            pass
    return "attack"


def fight(specs, enemy, seed=0):
    """Seed를 고정하고 최고 누적 피해의 위협 대상에 실제 enemy_attack을 적용한다."""
    profiles = [build(spec) for spec in specs]
    rng = Random(seed)
    maximum = boss_hp(ENEMIES[enemy]["hp"], len(specs)) if ENEMIES[enemy].get("boss") else ENEMIES[enemy]["hp"]
    hp, threat, shots, incoming = maximum, [0] * len(specs), [0] * len(specs), [0] * len(specs)
    mental, healed, reloads = [0] * len(specs), [0] * len(specs), [0] * len(specs)
    ammo = []
    for profile in profiles:
        family = equipment.context(profile).active.firearm_family
        ammo.append(ITEMS[STANDARD_MAGAZINES[family]]["magazine"]["capacity"] if family else None)
    attacks, round_index = 0, 0
    for round_index in range(1, 201):
        now = round_index * INTERVAL
        for profile in profiles:
            recovery.accrue_player(profile, rules.stats(profile), {}, ITEMS, now)
            recovery.commit(profile, rules.stats(profile))

        def enemy_turn():
            nonlocal attacks
            live = [index for index, profile in enumerate(profiles) if profile["hp"] > 0]
            if live and hp > 0:
                index = min(live, key=lambda i: (-threat[i], i))
                attacks += 1
                outcome = rules.enemy_attack(profiles[index], enemy, attacks, now, rng)
                incoming[index] += outcome["damage"]

        if seed % 2:
            enemy_turn()
        for index, (profile, spec) in enumerate(zip(profiles, specs)):
            if hp <= 0 or profile["hp"] <= 0:
                continue
            recipient = min((p for p in profiles if p["hp"] > 0), key=lambda p: p["hp"] / rules.stats(p)["max_hp"])
            action = choose_action(profile, spec["policy"], now, recipient)
            profile["queued_action"] = action
            if ammo[index] == 0 and action in ("attack", "shooting"):
                family = equipment.context(profile).active.firearm_family
                ammo[index] = ITEMS[STANDARD_MAGAZINES[family]]["magazine"]["capacity"]
                reloads[index] += 1
                rules.consume_combat_opportunity(profile, now, INTERVAL)
                continue
            damage, outcome = rules.player_attack(profile, enemy, now, INTERVAL, rng,
                                                 recipient if action == "heal" else None)
            mental[index] += outcome.get("cost", 0) if action in ("heal", "breathing") else (
                pg.mental_cost(action, spec["level"]) if outcome["action"] == action else 0)
            healed[index] += outcome.get("amount", 0) if action in ("heal", "bandage") else 0
            if outcome.get("shot_fired"):
                ammo[index] -= 1
                shots[index] += 1
            threat[index] += min(hp, damage)
            hp -= damage
        if not seed % 2:
            enemy_turn()
        if hp <= 0 or all(profile["hp"] <= 0 for profile in profiles):
            break
    ammo_cost = 0
    for index, profile in enumerate(profiles):
        family = equipment.context(profile).active.firearm_family
        if family:
            ammo_type = ITEMS[STANDARD_MAGAZINES[family]]["magazine"]["ammo_type"]
            unit = next(value["purchase_unit_value"] for value in ITEMS.values() if value.get("ammo_type") == ammo_type)
            ammo_cost += shots[index] * unit
    bandages = sum(8 - p["inventory"].get("bandage", 0) for p in profiles)
    return {"won": hp <= 0, "seconds": round_index * INTERVAL, "rounds": round_index, "enemy_attacks": attacks,
            "shots": sum(shots), "reloads": sum(reloads), "ammo_cost": ammo_cost, "bandages": bandages,
            "incoming": sum(incoming), "mental_spent": sum(mental), "healed": sum(healed),
            "hp_remaining": [max(0, p["hp"]) for p in profiles],
            "net": (expected_loot_value(enemy) if hp <= 0 else 0) - ammo_cost - bandages * rules.purchase_price("bandage")}


def summary(specs, enemy, samples):
    rows = [fight(specs, enemy, seed) for seed in range(samples)]
    result = {key: round(mean(row[key] for row in rows), 3) for key in
              ("seconds", "rounds", "enemy_attacks", "shots", "reloads", "ammo_cost", "bandages", "incoming", "mental_spent", "healed", "net")}
    result["win_rate"] = round(mean(row["won"] for row in rows), 3)
    result["seconds_p10_p90"] = [sorted(row["seconds"] for row in rows)[int((samples - 1) * p)] for p in (.1, .9)]
    result["hp_remaining"] = [round(mean(row["hp_remaining"][i] for row in rows), 3) for i in range(len(specs))]
    result["gross_ev"] = expected_loot_value(enemy)
    result["ammo_gross_ratio"] = round(result["ammo_cost"] / result["gross_ev"], 3)
    values = [rules.stats(build(spec)) for spec in specs]
    rates = [recovery.player_rates(v, snapshot=equipment.context(build(spec))) for spec, v in zip(specs, values)]
    result["hp_loss_ratio"] = round(result["incoming"] / sum(v["max_hp"] for v in values), 3)
    result["hp_downtime_minutes"] = round(mean(max(0, values[i]["max_hp"] - result["hp_remaining"][i]) / rates[i]["hp"] for i in range(len(specs))), 3)
    result["mental_recovery_minutes"] = round(result["mental_spent"] / sum(rate["mental"] for rate in rates), 3)
    groups = {"party": {i: 1 for i in range(len(specs))}}
    result["xp_shares"] = rules.reward_allocation(ENEMIES[enemy]["xp"], groups)
    result["currency_shares"] = rules.reward_allocation(ENEMIES[enemy]["currency"], groups)
    return result


def report(samples=64):
    specs = build_specs()
    builds, fights = {}, {}
    for label, spec in specs.items():
        profile = build(spec)
        values = rules.stats(profile)
        rates = recovery.player_rates(values, snapshot=equipment.context(profile))
        naked = recovery.player_rates(values)
        cost = sum(rules.purchase_price(identity) for identity in spec["gear"] if not ITEMS[identity].get("field_only")
                   and identity not in ("expedition_tag", "explorer_machete", "expedition_workwear"))
        builds[label] = {**spec, "stats": values, "purchase_cost": cost, "idle_rates": rates, "without_recovery_gear": naked,
                         "full_recovery_minutes": {key: round(values["max_" + key] / rate, 2) for key, rate in rates.items()}}
        targets = ("scavenger", "hunter") if label == "minimal" else (
            ("scavenger", "hunter", "sentinel", "alpha") if spec["level"] == 4 else ("dartclaw", "shellback", "stalker", "jungle_apex"))
        fights[label] = {enemy: summary([spec], enemy, samples) for enemy in targets}
    parties = {}
    for tier, boss in ((1, "alpha"), (2, "jungle_apex")):
        members = [specs[f"t{tier}_{role}"] for role in ("shield", "2h", "firearm", "support")]
        parties[boss] = {str(n): summary(members[:n], boss, samples) for n in (2, 3, 4)}
    gross = {enemy: expected_loot_value(enemy) for enemy in ENEMIES}
    costs = {"t1_essential": sum(rules.purchase_price(i) for i in ("cutting_machete", "light_protective_suit")),
             "t1_balanced": builds["t1_balanced"]["purchase_cost"], "t2_balanced": builds["t2_balanced"]["purchase_cost"],
             "t1_firearm_entry": rules.purchase_price("guard_carbine") + rules.purchase_price("mag_556_standard") + rules.purchase_price("ammo_556") + rules.purchase_price("reinforced_vest")}
    return {"samples": samples, "method": "seed0..n-1 / alternating tick order / actual pure rules / 8-bandage cap / no travel or reload latency",
            "builds": builds, "fights": fights, "parties": parties, "loot_ev": gross, "progression_costs": costs,
            "kills_at_gross_ev": {name: {enemy: ceil(cost / gross[enemy]) for enemy in ("scavenger", "sentinel", "stalker")}
                                  for name, cost in costs.items()},
            "packages": {identity: package_costs(identity) for identity, definition in ITEMS.items() if definition.get("firearm_family")}}
