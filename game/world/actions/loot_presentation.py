"""Loot 표시 번호와 권리 노출을 분리하고 동일 선택의 Typed 요청을 만든다."""

from dataclasses import replace
from time import time

from world.actions.loot_resolution import entry_reference, make_invocation
from world.actions.presentation import reference_json
from world.currency import format_currency
from world.loot_assets import asset_name
from world.selection_numbers.api import descriptor, label, number_for, resolve_reference


def _numbered_target(record):
    """표시 이름과 달리 실행 안내는 현재 실물의 저장 번호가 있어야 한다."""
    number = number_for(record.reference) if record is not None else None
    return label(replace(record, number=number)) if record is not None and number is not None else None


def payload(caller, selections, *, quantity=0, now=None):
    from world.loot_service import native_source
    from world.rules import RuleError

    selections = tuple(selections or ())
    if not selections:
        return None
    # ALL의 일부만 골라 서명하면 텍스트 ALL과 다른 부분 회수가 된다.
    # 권한 필터를 통과한 원 후보 전체가 유효할 때만 동일 선택을 제공한다.
    for source in {source.pk: source for source, _ in selections}.values():
        record = descriptor(source)
        if not native_source(source) or record is None or number_for(record.reference) is None:
            return None
    for _, selected in selections:
        try:
            reference = entry_reference(selected)
        except RuleError:
            return None
        if number_for(reference) is None:
            return None
    invocation = make_invocation(caller, selections, quantity=quantity, now=now)
    return {"action_id": invocation.action_id, "variant": invocation.variant_id,
            "roles": {name: [reference_json(ref) for ref in refs] for name, refs in invocation.roles},
            "arguments": dict(invocation.arguments)}


def visible_entries(source, caller, now=None):
    from typeclasses.loot import Corpse, can_take_entry
    from world.loot_service import loot_snapshot
    from world.multiplayer import object_by_id
    from world.observation import can_inspect_loot, can_perceive, context_for

    now = time() if now is None else now
    context = context_for(caller, observed_at=now)
    if source.location != caller.location or not can_inspect_loot(context) or not can_perceive(source, context):
        return []
    rows = []
    snapshot = loot_snapshot(source)
    source_record = descriptor(source)
    source_target = _numbered_target(source_record)
    if snapshot.native and source_target is None:
        return []
    for selected in snapshot.entries:
        entry = selected.as_entry()
        if not can_take_entry(entry, caller, now):
            continue
        if snapshot.native:
            reference = entry_reference(selected)
            target = _numbered_target(descriptor(resolve_reference(reference)))
            if target is None:
                continue
            action = payload(caller, [(source, selected)], quantity=1, now=now)
            if action is None:
                continue
        else:
            # 과거 blob은 읽기 전용으로만 표시한다. 배열 위치를 영속 ID/번호로 가장하지 않는다.
            target = asset_name(entry)
            action = None
        amount = format_currency(entry["quantity"]) if entry["kind"] == "currency" else f"×{entry['quantity']}"
        assigned = [object_by_id(identity) for identity in entry.get("remaining_shares", {})] if entry["kind"] == "currency" else [object_by_id(entry["assigned_player"])]
        prefix = source_target + "에서 " if isinstance(source, Corpse) and source_target is not None else ""
        rows.append({**entry, "name": asset_name(entry), "label": target, "take_target": target,
                     "amount_label": amount, "display_label": amount if entry["kind"] == "currency" else target + " " + amount,
                     "assigned_name": " · ".join(player.key if player else "탈퇴한 탐사자" for player in assigned),
                     "protected": now < entry["protection_until"], "can_take": True,
                     "take_command": prefix + target + " 가져" if snapshot.native else "",
                     "action": action})
    return rows


def _sources(caller, now, objects=None):
    from typeclasses.loot import room_loot
    from world.targets import room_objects

    objects = room_objects(caller, observed_at=now) if objects is None else objects
    return ([source for source in room_loot(caller.location) if source in objects],
            [source for source in room_loot(caller.location, corpse=False) if source in objects])


def _selections(caller, sources, now):
    from typeclasses.loot import can_take_entry
    from world.loot_service import loot_snapshot
    from world.observation import can_inspect_loot, context_for

    if not can_inspect_loot(context_for(caller, observed_at=now)):
        return []
    return [(source, entry) for source in sources for snapshot in [loot_snapshot(source)]
            if snapshot.native for entry in snapshot.entries if can_take_entry(entry.as_entry(), caller, now)]


def source_controls(caller, now=None, objects=None):
    from typeclasses.loot import Corpse
    from world.loot_service import native_source
    from world.observation import can_inspect_loot, context_for

    now = time() if now is None else now
    corpses, ground = _sources(caller, now, objects)
    output = {}
    for source in (*corpses, *ground):
        record = descriptor(source)
        target = _numbered_target(record)
        source_label = (target if target is not None else "시체 (선택 번호 확인 불가)") if isinstance(source, Corpse) else "바닥 전리품"
        selections = _selections(caller, [source], now)
        action = payload(caller, selections, now=now)
        output[source.pk] = {"label": source_label,
                             "take_command": ((source_label + "에서 모두 가져" if isinstance(source, Corpse) else "모두 가져")
                                              if native_source(source) and target is not None and (not selections or action is not None) else ""),
                             "take_action": action,
                             "loot": visible_entries(source, caller, now),
                             "loot_obscured": not can_inspect_loot(context_for(caller, observed_at=now))}
    return output


def all_controls(caller, now=None, objects=None):
    now = time() if now is None else now
    corpses, ground = _sources(caller, now, objects)
    return {"corpses": payload(caller, _selections(caller, corpses, now), now=now),
            "ground": payload(caller, _selections(caller, ground, now), now=now)}


def render(caller, index, reference, binding, observed_at=None):
    # Loot 자체 패널이 Entry와 전체 버튼을 표시한다. 공통 목록에 중복 제공하지 않는다.
    return []
