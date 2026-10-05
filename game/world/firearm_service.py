"""총기 복합 동작. owner와 UUID 집합 lock 후 ItemEntity API로 원자적 변경한다."""

from copy import deepcopy
from time import time

from world import firearms, rules
from world.content import ITEMS
from world.equipment_service import active_weapon_item
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.item_entities.services import (
    carried,
    domain_errors,
    lock_character_items,
    require_native,
    selected,
)
from world.multiplayer import COMBAT_INTERVAL, world_change

STANDARD_MAGAZINES = {"pistol_9mm": "mag_9_standard", "carbine_556": "mag_556_standard",
                      "rifle_762": "mag_762_standard"}
AMMO_DEFINITIONS = {"9mm": "ammo_9", "556mm": "ammo_556", "762mm": "ammo_762"}


def magazine_snapshot(row):
    data = ITEMS[row.definition_id].get("magazine")
    if not data:
        raise rules.RuleError("탄창을 선택하세요.")
    return firearms.MagazineSnapshot(str(row.pk), row.definition_id, row.sequence,
                                     data["family"], data["ammo_type"], data["capacity"], row.state["rounds"])


def loaded_magazine_item(firearm):
    """영속 작업용 row. gameplay는 loaded_magazine()/firearm_snapshot()을 사용한다."""
    return ItemEntity.objects.filter(parent_item_id=api.item_id(firearm), socket="magazine").first()


def loaded_magazine(firearm):
    row = loaded_magazine_item(firearm)
    return magazine_snapshot(row) if row else None


def firearm_snapshot(firearm):
    family = ITEMS[firearm.definition_id].get("firearm_family")
    if not family:
        raise rules.RuleError("총기를 선택하세요.")
    return firearms.FirearmSnapshot(str(firearm.pk), firearm.definition_id, family, loaded_magazine(firearm))


def compatible_magazines(character, firearm):
    family = firearm_snapshot(firearm).family
    return tuple(magazine_snapshot(row) for row in ItemEntity.objects.filter(
        owner_object=character, location_kind="inventory").order_by("sequence")
        if ITEMS[row.definition_id].get("magazine", {}).get("family") == family)


@domain_errors
def create_firearm(definition_id, *, owner_object, mode="no_mag", rounds=None, location_kind="inventory"):
    """획득 형태만 제공한다. 실제 상점·보상·drop·migration에는 아직 연결하지 않는다."""
    if mode not in ("no_mag", "empty", "partial", "full_standard"):
        raise rules.RuleError("총기 획득 형태를 확인하세요.")
    family = ITEMS[definition_id].get("firearm_family")
    if family not in STANDARD_MAGAZINES:
        raise rules.RuleError("등록된 총기 family가 필요합니다.")
    with world_change():
        lock_character_items(owner_object)
        firearm = api.create_item(definition_id, location_kind=location_kind, owner_object=owner_object)
        if mode == "no_mag":
            if rounds is not None:
                raise rules.RuleError("탄창 없는 획득에는 잔탄을 지정할 수 없습니다.")
            return firearm
        identity = STANDARD_MAGAZINES[family]
        capacity = ITEMS[identity]["magazine"]["capacity"]
        if mode == "partial" and (type(rounds) is not int or not 0 < rounds < capacity):
            raise rules.RuleError("부분 탄창의 잔탄은 0과 용량 사이여야 합니다.")
        count = rounds if mode == "partial" else capacity if mode == "full_standard" else 0
        if rounds is not None and mode != "partial":
            raise rules.RuleError("잔탄 지정은 partial 획득에만 사용하세요.")
        api.create_item(identity, location_kind="inside", parent_item=firearm, socket="magazine",
                        state={"rounds": count})
        return firearm


def _owned_firearm(character, locked, item):
    firearm = selected(locked, item)
    carried(character, firearm)
    firearm_snapshot(firearm)
    return firearm


@domain_errors
def reload(character, item, magazine=None, now=None):
    require_native(character)
    now = time() if now is None else now
    with world_change():
        locked = lock_character_items(character)
        firearm = _owned_firearm(character, locked, item)
        snapshot = firearm_snapshot(firearm)
        profile = character.profile()
        if magazine is None:
            candidates = compatible_magazines(character, firearm)
            best = firearms.automatic_magazine(snapshot, candidates)
            if best is None:
                if snapshot.magazine and snapshot.magazine.rounds > 0:
                    return False
                raise rules.RuleError("잔탄이 있는 호환 탄창이 없습니다.")
            replacement = selected(locked, best.identity)
        else:
            replacement = selected(locked, magazine)
            carried(character, replacement, inside=True)
            candidate = magazine_snapshot(replacement)
            if candidate.family != snapshot.family:
                raise rules.RuleError("총기와 탄창 family가 호환되지 않습니다.")
            if snapshot.magazine and candidate.identity == snapshot.magazine.identity:
                return False
            if replacement.location_kind != "inventory" or candidate.rounds <= 0:
                raise rules.RuleError("직접 소지한 잔탄 있는 탄창을 선택하세요.")
        current = loaded_magazine_item(firearm)
        if current:
            api.move_item_tree(current, location_kind="inventory", owner_object=character, operation="unload")
        api.move_item_tree(replacement, location_kind="inside", parent_item=firearm,
                           socket="magazine", operation="load", expected_source=("inventory", character.pk))
        if profile["combat_target"]:
            character.accrue_recovery(profile, now)
            # 아직 도래하지 않은 다음 기회를 대체하고 그 다음 기회까지 기다린다.
            # 사용자가 scheduler와 같은 순간에 명령을 보낼 필요가 없다.
            rules.consume_combat_opportunity(profile, max(now, profile["next_attack_at"]), COMBAT_INTERVAL)
            character.save_profile(profile)
        return True


@domain_errors
def unload_magazine(character, item):
    require_native(character)
    with world_change():
        locked = lock_character_items(character)
        rules.require_peace(character.profile())
        firearm = _owned_firearm(character, locked, item)
        magazine = loaded_magazine_item(firearm)
        if magazine is None:
            raise rules.RuleError("삽입된 탄창이 없습니다.")
        return api.move_item_tree(magazine, location_kind="inventory", owner_object=character, operation="unload")


def _owned_magazine(character, locked, item):
    magazine = selected(locked, item)
    carried(character, magazine, inside=True)
    if magazine.location_kind == "inside" and magazine.socket != "magazine":
        raise rules.RuleError("소지하거나 자신의 총기에 삽입한 탄창을 선택하세요.")
    magazine_snapshot(magazine)
    return magazine


@domain_errors
def load_ammo(character, item, ammo=None):
    require_native(character)
    with world_change():
        locked = lock_character_items(character)
        rules.require_peace(character.profile())
        magazine = _owned_magazine(character, locked, item)
        snapshot = magazine_snapshot(magazine)
        if ammo is None:
            sources = [row for row in locked.values() if row.location_kind == "inventory"
                       and ITEMS[row.definition_id].get("ammo_type") == snapshot.ammo_type]
            sources.sort(key=lambda row: row.sequence)
        else:
            source = selected(locked, ammo)
            carried(character, source)
            sources = [source]
        if not sources:
            raise rules.RuleError("호환하는 소지 탄약이 없습니다.")
        if snapshot.rounds == snapshot.capacity:
            raise rules.RuleError("탄창이 이미 가득 찼습니다.")
        count = 0
        api._check_operation(magazine, "load")
        for source in sources:
            if source.location_kind != "inventory" or ITEMS[source.definition_id].get("ammo_type") != snapshot.ammo_type:
                raise rules.RuleError("탄창과 탄약이 호환되지 않습니다.")
            api._check_operation(source, "load")
            amount = min(source.quantity, snapshot.capacity - snapshot.rounds - count)
            if not amount:
                break
            count += amount
            if amount == source.quantity:
                api.delete_item(source, operation="load")
            else:
                source.quantity -= amount
                source.save()
        api.update_item_state(magazine, {**magazine.state, "rounds": snapshot.rounds + count})
        return count


@domain_errors
def unload_ammo(character, item, ammo_type=None):
    require_native(character)
    with world_change():
        locked = lock_character_items(character)
        rules.require_peace(character.profile())
        magazine = _owned_magazine(character, locked, item)
        snapshot = magazine_snapshot(magazine)
        if ammo_type is not None and ammo_type != snapshot.ammo_type:
            raise rules.RuleError("탄창의 탄종과 다릅니다. V1은 잔탄을 전량 꺼냅니다.")
        if not snapshot.rounds:
            raise rules.RuleError("꺼낼 잔탄이 없습니다.")
        api._check_operation(magazine, "unload")
        identity = AMMO_DEFINITIONS[snapshot.ammo_type]
        api.update_item_state(magazine, {**magazine.state, "rounds": 0})
        loose = api.create_item(identity, location_kind="inventory", owner_object=character, quantity=snapshot.rounds)
        destinations = sorted((row for row in locked.values() if api.same_merge_context(loose, row)),
                              key=lambda row: row.sequence)
        if destinations:
            api.merge_stack(loose, destinations[0])
        return snapshot.rounds


def consume_shot(magazine, outcome):
    """damage/hit와 독립된 실제 shot 계약. 호출자의 world_change 안에서만 사용한다."""
    from django.db import connection

    if not connection.in_atomic_block:
        raise RuntimeError("발사와 탄약 감소는 같은 transaction이어야 합니다.")
    if not outcome.get("shot_fired"):
        return
    if magazine is None or magazine.state["rounds"] <= 0:
        raise rules.RuleError("발사할 탄약이 없습니다.")
    row = api.update_item_state(magazine, {**magazine.state, "rounds": magazine.state["rounds"] - 1})
    magazine.state = row.state


def player_attack(character, profile, enemy_id, now, interval, rng=None, target_profile=None):
    """pure combat 결과와 magazine 감소를 하나의 원자적 경계로 묶는다."""
    from world.equipment_service import entity_runtime

    before = deepcopy(dict(profile))
    target_before = deepcopy(dict(target_profile)) if target_profile is not None else None
    try:
        with world_change():
            if not entity_runtime(character):
                return rules.player_attack(profile, enemy_id, now, interval, rng, target_profile)
            lock_character_items(character)
            from world.equipment_service import equipment_snapshot

            profile.equipment_context = equipment_snapshot(character)
            firearm = active_weapon_item(character)
            magazine = None
            available = True
            if firearm and profile.equipment_context.active.weapon_type == "firearm":
                magazine = loaded_magazine_item(firearm)
                available = magazine is not None and magazine.state["rounds"] > 0
            damage, outcome = rules.player_attack(profile, enemy_id, now, interval, rng, target_profile,
                                                   shot_available=available)
            consume_shot(magazine, outcome)
            return damage, outcome
    except Exception:
        profile.clear()
        profile.update(before)
        if target_profile is not None:
            target_profile.clear()
            target_profile.update(target_before)
        raise
