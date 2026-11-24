"""공개 전리품의 표시와 회수 문법을 안정 참조와 별도로 계산한다."""

from dataclasses import dataclass
from time import time

from world.actions.loot_resolution import (
    entry_records,
    make_invocation,
    read_loot_rights,
    read_recipients,
)
from world.actions.presentation import reference_json
from world.currency import format_currency
from world.loot_assets import asset_name
from world.selection_display import displays, room_snapshot
from world.selection_numbers.api import descriptor, numbered_records


def ground_lookup_objects(caller, objects, query, now):
    """일반 관찰에서 읽을 수 있는 물품에 해당하는 바닥 출처 이름만 제공한다."""
    from typeclasses.loot import DroppedLoot, readable_entry_flags
    from world.item_runtime import maintenance, native_runtime
    from world.loot_service import loot_snapshots, native_source
    from world.observation import can_inspect_loot, context_for
    from world.targets import names, normalized

    raw = normalized(query)
    ground = [obj for obj in objects if isinstance(obj, DroppedLoot)
              and any(raw.startswith(normalized(name)) for name in names(obj))]
    allowed = set()
    if ground and can_inspect_loot(context_for(caller, observed_at=now)):
        if native_runtime() and not maintenance.get():
            ground = [obj for obj in ground if native_source(obj)]
        snapshots = loot_snapshots(ground)
        pairs = [(obj.pk, entry) for obj in ground for row in snapshots[obj.pk].entries
                 for entry in [row.as_entry()] if normalized(asset_name(entry)) == normalized(obj.key)]
        flags = readable_entry_flags((entry for _, entry in pairs), caller, now)
        allowed = {pk for (pk, _), readable in zip(pairs, flags) if readable}
    return [obj for obj in objects if not isinstance(obj, DroppedLoot) or obj.pk in allowed]


def payload(caller, selections, *, quantity=0, now=None, display=None):
    from world.loot_service import native_source

    selections = tuple(selections or ())
    if not selections:
        return None
    if display is None:
        sources = {source.pk: source for source, _ in selections}
        source_records = {pk: descriptor(source) for pk, source in sources.items() if native_source(source)}
        entry_rows = entry_records(selections)
        valid = {record.reference: record for record in numbered_records(
            (*source_records.values(), *entry_rows.values())
        )}
    else:
        source_records, entry_rows, valid = display.sources, display.entry_records, display.valid
    source_refs, subject_refs = [], []
    for source, entry in selections:
        original = source_records.get(source.pk)
        selected = entry_rows.get((source.pk, entry))
        if original is None or original.reference not in valid or selected is None or selected.reference not in valid:
            return None
        source_refs.append(original.reference)
        subject_refs.append(selected.reference)
    rights = ({"party": display.party, "recipients": display.recipients}
              if display is not None and display.caller is caller and display.now == now else {})
    invocation = make_invocation(
        caller, selections, quantity=quantity, now=now,
        references=(tuple(dict.fromkeys(source_refs)), tuple(subject_refs)),
        **rights,
    )
    return {"action_id": invocation.action_id, "variant": invocation.variant_id,
            "roles": {name: [reference_json(ref) for ref in refs] for name, refs in invocation.roles},
            "arguments": dict(invocation.arguments)}


@dataclass
class _LootDisplay:
    caller: object
    now: float
    room: object
    corpses: tuple
    ground: tuple
    snapshots: dict
    sources: dict
    entry_records: dict
    valid: dict
    allowed: dict
    accessible: frozenset
    selection_records: tuple
    labels: dict
    entries: dict
    obscured: bool
    party: object
    recipients: dict

    def selections(self, sources):
        return [(source, entry) for source in sources
                if (snapshot := self.snapshots.get(source.pk)) is not None and snapshot.native
                for entry in self.allowed[source.pk]]

    def valid_command(self, text, expected, quantity):
        from world.actions.loot_resolution import select_loot
        from world.rules import RuleError

        try:
            actual, count = select_loot(
                self.caller, text, now=self.now, sources=self.sources, entries=self.entries,
                records=self.selection_records, accessible=self.accessible,
                party=self.party, recipients=self.recipients,
            )
        except RuleError:
            return False
        return tuple(actual) == expected and count == quantity

    def command(self, source, entries, *, all_entries=False):
        from typeclasses.loot import Corpse

        if not entries:
            return ""
        source_record = self.sources.get(source.pk)
        if source_record is None or source_record.number is None:
            return ""
        prefixes = ("",)
        if isinstance(source, Corpse):
            prefixes = tuple(name + "에서 " for name in _selection_names(source_record))
        if all_entries:
            texts = ("모두",)
        else:
            record = self.entry_records.get((source.pk, entries[0]))
            record = self.valid.get(record.reference) if record else None
            if record is None:
                return ""
            texts = _selection_names(record)
        expected = tuple((source.pk, entry) for entry in entries)
        for prefix in prefixes:
            for name in texts:
                text = prefix + name
                if self.valid_command(text, expected, 0 if all_entries else 1):
                    return text + " 가져"
        return ""


def _selection_names(record):
    from world.targets import exact_selector

    return f"{record.name} {record.number}", exact_selector(record.name, record.number)


def _assigned_ids(entry):
    if entry.kind == "currency":
        return tuple(identity for identity, amount in entry.shares if amount > 0)
    return (entry.assigned_player,)


def loot_display(caller, now=None, objects=None, *, snapshot=None):
    from typeclasses.loot import Corpse, DroppedLoot, can_take_entry
    from world.loot_service import loot_snapshots
    from world.observation import can_inspect_loot, context_for
    from world.targets import room_objects

    now = time() if now is None else now
    objects = tuple(room_objects(caller, observed_at=now) if objects is None else objects)
    room = room_snapshot(caller, now, objects=objects) if snapshot is None else snapshot
    corpses = tuple(source for source in objects if source.is_typeclass(Corpse, exact=True))
    ground = tuple(source for source in objects if source.is_typeclass(DroppedLoot, exact=True))
    sources = (*corpses, *ground)
    obscured = not can_inspect_loot(context_for(caller, observed_at=now))
    snapshots = loot_snapshots(sources) if not obscured else {}
    party, recipients = read_loot_rights(
        caller, (entry for value in snapshots.values() for entry in value.entries), now)
    allowed = {pk: tuple(entry for entry in value.entries if can_take_entry(
        entry.as_entry(), caller, now, party=party, recipients=recipients))
               for pk, value in snapshots.items()}
    recipients.update(read_recipients(
        identity for rows in allowed.values() for entry in rows for identity in _assigned_ids(entry)
        if identity not in recipients
    ))
    pairs = tuple((source, entry) for source in sources
                  if (value := snapshots.get(source.pk)) is not None and value.native for entry in value.entries)
    entry_rows = entry_records(pairs)
    valid = dict(room.records)
    valid.update((record.reference, record) for record in numbered_records(entry_rows.values()))
    source_records = {source.pk: valid.get(current.reference, current) for source in sources
                      if (current := descriptor(source)) is not None}
    allowed_records = [valid.get(record.reference, record) for (pk, entry), record in entry_rows.items()
                       if entry in allowed[pk]]
    entries = {pk: tuple((entry, record.reference if (record := entry_rows.get((pk, entry))) else None)
                         for entry in value.entries) for pk, value in snapshots.items() if value.native}
    return _LootDisplay(
        caller, now, room, corpses, ground, snapshots, source_records, entry_rows, valid, allowed,
        frozenset(record.reference for record in allowed_records),
        tuple(valid.get(record.reference, record) for record in entry_rows.values()),
        displays(allowed_records), entries, obscured, party, recipients,
    )


def visible_entries(source, caller, now=None, *, display=None):
    display = loot_display(caller, now) if display is None else display
    now = display.now
    snapshot = display.snapshots.get(source.pk)
    if snapshot is None or (snapshot.native and source.pk not in display.room.references):
        return []
    rows = []
    for selected in display.allowed[source.pk]:
        entry = selected.as_entry()
        action = None
        command = ""
        if snapshot.native:
            record = display.entry_records.get((source.pk, selected))
            target = display.labels.get(record.reference) if record else None
            if target is None:
                continue
            action = payload(caller, [(source, selected)], quantity=1, now=now, display=display)
            if action is None:
                continue
            command = display.command(source, (selected,))
        else:
            # 과거 blob은 읽기 전용이며 순서를 영속 번호로 사용하지 않는다.
            target = asset_name(entry)
        currency = entry["kind"] == "currency"
        amount = format_currency(entry["quantity"]) if currency else f"×{entry['quantity']}"
        assigned = [display.recipients.get(identity) for identity in _assigned_ids(selected)]
        display_label = amount if currency and target == asset_name(entry) else target + " " + amount
        rows.append({**entry, "name": asset_name(entry), "label": target, "take_target": target,
                     "amount_label": amount, "display_label": display_label,
                     "assigned_name": " · ".join(player.key if player else "탈퇴한 탐사자" for player in assigned),
                     "protected": now < entry["protection_until"], "can_take": True,
                     "take_command": command, "action": action})
    return rows


def source_controls(caller, now=None, objects=None, *, snapshot=None, display=None):
    from typeclasses.loot import Corpse

    display = loot_display(caller, now, objects, snapshot=snapshot) if display is None else display
    output = {}
    for source in (*display.corpses, *display.ground):
        label = display.room.labels[source.pk]
        if label is None:
            name = "시체" if isinstance(source, Corpse) else source.get_display_name(caller)
            label = f"{name} (선택 번호 확인 불가)"
        selections = display.selections((source,))
        action = payload(caller, selections, now=display.now, display=display)
        output[source.pk] = {"label": label,
                             "take_command": display.command(source, tuple(entry for _, entry in selections),
                                                             all_entries=True) if action else "",
                             "take_action": action,
                             "loot": visible_entries(source, caller, display=display),
                             "loot_obscured": display.obscured}
    return output


def all_controls(caller, now=None, objects=None, *, snapshot=None, display=None):
    display = loot_display(caller, now, objects, snapshot=snapshot) if display is None else display
    return {key: payload(caller, display.selections(sources), now=display.now, display=display)
            for key, sources in (("corpses", display.corpses), ("ground", display.ground))}


def render(caller, index, reference, binding, observed_at=None):
    # Loot 자체 패널이 Entry와 전체 버튼을 표시한다. 공통 목록에 중복 제공하지 않는다.
    return []
