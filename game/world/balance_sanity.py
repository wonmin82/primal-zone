"""작은 deterministic sanity 계산. 전투·경제 확정값을 수정하지 않는다."""

from copy import deepcopy
from math import ceil

from world import equipment, rules
from world.content import ENEMIES, ITEMS
from world.content.economy import SALVAGE_CREDIT_RATE
from world.content.loot_v1 import LOOT


def build(level, identities):
    items = tuple(equipment.item_snapshot(identity, ITEMS[identity], item_id=str(index), sequence=index)
                  for index, identity in enumerate(identities, 1))
    snapshot = equipment.EquipmentSnapshot(items, items, next(item.identity for item in items if item.role == "weapon"))
    profile = equipment.EquipmentProfile(rules.new_profile(), snapshot)
    profile["xp"] = rules.xp_threshold(level)
    profile["attributes"]["strength"]["allocated"] = 4 if level == 4 else 6
    profile["attributes"]["constitution"]["allocated"] = 4 if level == 4 else 6
    profile["skills"].update(attack=level, heavy=level, shooting=level, insight=2, defense=level)
    profile.update(hp=rules.stats(profile)["max_hp"], mental=rules.stats(profile)["max_mental"], combat_target=1)
    return profile


class MeanRoll:
    def randint(self, low, high):
        return (low + high) / 2


def opportunities(profile, enemy, skill=False):
    profile = deepcopy(profile)
    hp = ENEMIES[enemy]["hp"]
    for index in range(100):
        now = index * 2.5
        if skill and now >= profile.get("heavy_ready_at", 0) and profile["mental"] >= 8:
            profile["queued_action"] = "heavy"
        damage, _ = rules.player_attack(profile, enemy, now, 2.5, MeanRoll())
        hp -= damage
        if hp <= 0:
            return index + 1
    return 100


def expected_loot_value(enemy):
    loot = LOOT[enemy]
    value = ENEMIES[enemy]["currency"]
    chance, choices = loot.get("resource", (0, ()))
    for identity, weight in choices:
        low, high = loot.get("quantities", {}).get(identity, (1, 1))
        # 회수부품의 실제 정산 가치도 반영한다.
        price = ITEMS[identity].get("resale_unit_value", ITEMS[identity].get("value", 0) // 2) if identity != "scrap" else SALVAGE_CREDIT_RATE
        value += chance * weight * (low + high) / 2 * price
    for identity, chance in loot.get("special", ()):
        resale = ITEMS[identity]["resale_unit_value"]
        if identity in loot.get("firearms", {}):
            magazine, low, high = loot["firearms"][identity]
            ammo = next(data for data in ITEMS.values() if data.get("ammo_type") == ITEMS[magazine]["magazine"]["ammo_type"])
            resale += ITEMS[magazine]["resale_unit_value"] + (low + high) / 2 * ammo["resale_unit_value"]
        value += chance * resale
    return round(value, 3)


def report():
    ridge = build(4, ("cutting_machete", "reinforced_vest", "security_goggles", "shock_absorbing_gloves", "reinforced_explorer_pants"))
    jungle = build(7, ("jungle_longblade", "tactical_protective_suit", "tracking_goggles", "strike_assist_gloves", "medical_tactical_belt", "marsh_protective_pants", "stabilizing_boots"))
    hand = {}
    for label, identities in {"2H": ("pioneer_spear",), "1H+shield": ("cutting_machete", "folding_shield"),
                              "1H+offhand": ("cutting_machete", "portable_analyzer"), "1H+1H": ("cutting_machete", "scout_pistol")}.items():
        profile = build(4, (*identities, "reinforced_vest"))
        hand[label] = {key: rules.stats(profile)[key] for key in ("attack", "defense", "max_hp")}
    carbine = build(4, ("guard_carbine", "reinforced_vest"))
    damage, _ = rules.player_attack(carbine, "sentinel", 0, 2.5, MeanRoll())
    shots = ceil(ENEMIES["sentinel"]["hp"] / damage)
    penetration = {str(defense): {str(p): rules.apply_defense(30, defense, p) for p in (0, .1, .3)} for defense in (0, 2, 10)}
    return {"ridge_basic": opportunities(ridge, "alpha"), "ridge_skill": opportunities(ridge, "alpha", True),
            "jungle_basic": opportunities(jungle, "jungle_apex"), "jungle_skill": opportunities(jungle, "jungle_apex", True),
            "hands": hand, "penetration": penetration, "carbine_shots": shots, "carbine_ammo_cost": shots * 3,
            "carbine_income_ratio": round(shots * 3 / expected_loot_value("sentinel"), 3),
            "loot_ev": {identity: expected_loot_value(identity) for identity in LOOT if not ENEMIES[identity].get("boss")}}
