"""Lighting facade. legacy와 Entity가 각자의 SSOT 하나만 읽고 변경한다."""

from time import time
from uuid import UUID

from world import lighting, rules
from world.content import ITEMS
from world.equipment_service import entity_runtime, resolve_item, selector_label
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.item_entities.services import carried, domain_errors, lock_character_items, selected
from world.multiplayer import world_change


def reference_row(reference):
    try:
        identity = UUID(str(reference))
    except (ValueError, TypeError, AttributeError):
        return None
    return ItemEntity.objects.filter(pk=identity).first()


def lighting_snapshot(character, profile=None, now=None):
    now = time() if now is None else now
    if not entity_runtime(character):
        return lighting.legacy_snapshot(profile if profile is not None else character.profile_snapshot(), now)
    rows = list(api.items_owned_by(character))
    counts, items = {}, []
    for row in rows:
        definition = ITEMS[row.definition_id]
        if not definition.get("light_source"):
            continue
        if row.root().location_kind not in ("inventory", "equipment"):
            continue
        counts[row.definition_id] = counts.get(row.definition_id, 0) + 1
        label = definition["name"] + (f" {counts[row.definition_id]}" if counts[row.definition_id] > 1 else "")
        if row.location_kind != "inventory":
            continue
        state = lighting.project_power(row.state, now)
        active = (str(row.pk) == character.db.active_light_item_id and state["enabled"]
                  and state["remaining_power"] > 0)
        items.append(lighting.LightItem(row.definition_id, str(row.pk), row.sequence, label,
                                        state["remaining_power"], active, state["power_type"],
                                        capacity=definition["light_source"].get("max_power_seconds", 1800)))
    return lighting.LightSnapshot(tuple(items), next((item for item in items if item.enabled), None), "item_entities")


def _settle(row, now, *, turn_off=False):
    state = lighting.project_power(row.state, now)
    if turn_off:
        state.update(enabled=False, started_at=None)
    if row.state != state:
        api.update_item_state(row, state)
    return state


def reconcile_locked(character, now=None, *, turn_off=False, previous_owned_id=None):
    """공통 item 변경의 owner·아이템 lock 안에서 참조와 전원을 함께 정산한다."""
    now = time() if now is None else now
    reference = character.db.active_light_item_id
    row = reference_row(reference) if reference else None
    valid = bool(row and row.owner_object_id == character.pk and row.location_kind == "inventory"
                 and ITEMS[row.definition_id].get("light_source") and row.state.get("enabled"))
    if row and ITEMS[row.definition_id].get("light_source") and (
            row.owner_object_id == character.pk or str(row.pk) == previous_owned_id):
        projected = lighting.project_power(row.state, now)
        # 주기적인 관찰은 소진/참조 변경만 확정한다. 정상 ON의 경과는 저장하지 않는다.
        if turn_off or not valid or not projected["enabled"]:
            _settle(row, now, turn_off=turn_off or not valid)
        valid = valid and projected["enabled"]
    if turn_off or not valid:
        character.db.active_light_item_id = None
    # owner·UUID lock이 확보된 직접 inventory만 정규화한다. 다른 owner의 참조는 수정하지 않는다.
    for light in ItemEntity.objects.filter(owner_object=character, location_kind="inventory"):
        if (ITEMS[light.definition_id].get("light_source") and light.state.get("enabled")
                and (turn_off or not valid or light.pk != row.pk)):
            _settle(light, now, turn_off=True)


@domain_errors
def reconcile(character, now=None, *, turn_off=False):
    if not entity_runtime(character):
        with world_change():
            profile = character.profile_snapshot()
            changed = lighting.normalize(profile, time() if now is None else now, turn_off=turn_off)
            if changed:
                character.save_profile(profile)
            return changed
    with world_change():
        # 이동 직전 owner가 참조한 row도 포함한다. 훼손된 참조는 읽기에서 무시하고 여기서 정리한다.
        lock_character_items(character)
        old = character.db.active_light_item_id
        reconcile_locked(character, now, turn_off=turn_off)
        return old is not None and character.db.active_light_item_id is None


@domain_errors
def switch(character, item, enabled, now=None):
    now = time() if now is None else now
    if not entity_runtime(character):
        return character.change(lambda profile: lighting.switch(profile, item, enabled, now))
    with world_change():
        locked = lock_character_items(character)
        row = selected(locked, item)
        carried(character, row)
        if row.location_kind != "inventory" or not ITEMS[row.definition_id].get("light_source"):
            raise rules.RuleError("소지한 휴대 광원을 선택하세요.")
        state = lighting.project_power(row.state, now)
        if enabled and state["remaining_power"] <= 0:
            raise rules.RuleError("먼저 호환 전원을 넣으세요.")
        if enabled:
            # 모든 ON row를 정리하여 훼손된 참조가 있어도 only-one-ON을 복구한다.
            for light in locked.values():
                if ITEMS[light.definition_id].get("light_source") and light.state.get("enabled"):
                    _settle(light, now, turn_off=True)
        state.update(enabled=enabled, started_at=now if enabled else None)
        api.update_item_state(row, state)
        if enabled:
            character.db.active_light_item_id = str(row.pk)
        elif character.db.active_light_item_id == str(row.pk):
            character.db.active_light_item_id = None


@domain_errors
def insert_power(character, item, power, now=None):
    now = time() if now is None else now
    if not entity_runtime(character):
        return character.change(lambda profile: lighting.insert_power(profile, item, power, now))
    with world_change():
        locked = lock_character_items(character)
        rules.require_peace(character.profile())
        row, battery = selected(locked, item), selected(locked, power)
        carried(character, row)
        carried(character, battery)
        definition, source = ITEMS[row.definition_id], ITEMS[battery.definition_id].get("power_source")
        if (row.location_kind != "inventory" or battery.location_kind != "inventory"
                or not definition.get("light_source") or not source
                or source["type"] != definition["light_source"]["power_type"]):
            raise rules.RuleError("광원과 전원이 호환되지 않습니다.")
        state = lighting.project_power(row.state, now)
        if state["remaining_power"] > 0:
            raise rules.RuleError("아직 사용할 수 있는 전원이 남아 있습니다.")
        api._check_operation(battery, "consume")
        if battery.quantity == 1:
            api.delete_item(battery, operation="consume")
        else:
            battery.quantity -= 1
            battery.save()
        state.update(remaining_power=source["capacity_seconds"], enabled=False, started_at=None)
        api.update_item_state(row, state)
        if character.db.active_light_item_id == str(row.pk):
            character.db.active_light_item_id = None


def status(character, item, now=None):
    now = time() if now is None else now
    if not entity_runtime(character):
        return lighting.status(character.profile_snapshot(), item, now)
    selected_item = next((entry for entry in lighting_snapshot(character, now=now).items
                          if entry.identity == str(api.item_id(item))), None)
    if selected_item is None:
        raise rules.RuleError("소지한 광원을 선택하세요.")
    return (f"상태 {'켜짐' if selected_item.enabled else '꺼짐'}\n"
            f"전원 {lighting.snapshot_display(selected_item)['power_source']['name'] if selected_item.remaining_power > 0 else '없음'}\n"
            f"잔량 약 {lighting.snapshot_display(selected_item)['remaining_minutes']}분")


def resolve_light(character, value, action):
    if entity_runtime(character):
        item = resolve_item(character, value, action)
    else:
        from world.targets import stack_selector

        item, _ = stack_selector(value, ITEMS, action, allow_all=False)
    identity = item.definition_id if isinstance(item, ItemEntity) else item
    if not ITEMS[identity].get("light_source"):
        raise rules.RuleError("휴대 광원을 선택하세요.")
    return item, selector_label(character, item)
