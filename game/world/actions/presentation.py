"""공통 선언의 순수 Help/웹 표현. 번호 할당·게임 효과·확정 토큰 발급을 하지 않는다."""

from contextvars import ContextVar
from dataclasses import dataclass, field

from world.actions.presentation_context import (
    observation_snapshot,
    presentation_scope,
    profile_snapshot,
    scoped_reads,
)
from world.actions.resolver import cached_item_scopes, provided
from world.actions.schema import ReferenceKind, TargetReference, TargetScope
from world.selection_display import displays, room_snapshot
from world.selection_numbers.api import SelectionRecord, descriptor, numbered_records

_current_labels = ContextVar("action_selection_labels", default=None)


@dataclass(frozen=True)
class ItemActionControl:
    """Validated sale or storage candidate shared by text examples and web controls."""

    label: str
    description: str
    action_id: str
    variant: str
    provider: TargetReference
    subject: SelectionRecord
    count: str

    def as_web(self):
        return {"label": self.label, "description": self.description,
                "action": {"action_id": self.action_id, "variant": self.variant,
                           "roles": {"provider": [reference_json(self.provider)],
                                     "subject": [reference_json(self.subject.reference)]},
                           "arguments": {"count": self.count}}}


@dataclass
class _DisplayContexts:
    caller: object
    rooms: dict = field(default_factory=dict)
    scopes: dict = field(default_factory=dict)
    carried: dict | None = None

    def room_at(self, observed_at):
        caller = self.caller
        key = (caller.db_location_id, observed_at)
        if key not in self.rooms:
            observation = None if observed_at is None else observation_snapshot(caller, observed_at)
            self.rooms[key] = room_snapshot(caller, observed_at, observation=observation)
        return self.rooms[key]

    def for_scope(self, scope):
        if scope.startswith(("character:", "inside:")):
            return self.carried_scopes().get(scope, {})
        if scope not in self.scopes:
            self.scopes[scope] = displays(_scope_records(self.caller, scope))
        return self.scopes[scope]

    def carried_scopes(self):
        if self.carried is None:
            self.carried = _carried_labels(self.caller)
        return self.carried


def _carried_labels(caller):
    from collections import defaultdict

    from world.item_entities.api import carried_items

    records = [record for item in carried_items(caller) if (record := descriptor(item))]
    valid = {record.reference: record for record in numbered_records(records)}
    scopes = defaultdict(dict)
    for reference, label in displays(valid.get(record.reference, record) for record in records).items():
        scopes[reference.scope_id][reference] = label
    return scopes


def _scope_records(caller, scope):
    from world.item_entities.models import ItemEntity
    from world.selection_numbers.api import records_for

    kind, _, identity = scope.partition(":")
    if kind in ("personal_storage", "shared_storage"):
        # 보관함과 현재 소지품 접근은 Storage Role이 먼저 확정한다.
        if kind == "personal_storage" and identity != str(caller.pk):
            return ()
        entities = ItemEntity.objects.filter(owner_object_id=identity, location_kind=kind)
    else:
        return records_for(caller, scope_ids=(scope,))
    records = [record for entity in entities if (record := descriptor(entity))]
    valid = {record.reference: record for record in numbered_records(records)}
    return tuple(valid.get(record.reference, record) for record in records)


def target_label(caller, reference, observed_at=None):
    from world.actions.schema import ReferenceKind

    if reference.kind == ReferenceKind.ROOM:
        room = caller.location
        record = descriptor(room) if room else None
        return record.name if record and record.reference == reference else None
    contexts = _current_labels.get()
    if contexts is None or contexts.caller is not caller:
        contexts = _DisplayContexts(caller)
    if reference.scope_id.startswith("room:"):
        room = contexts.room_at(observed_at)
        if reference not in room.records:
            return None
        return room.labels[int(reference.identity)]
    return contexts.for_scope(reference.scope_id).get(reference)


def reference_json(reference):
    return {"kind": str(reference.kind), "identity": reference.identity, "scope_id": reference.scope_id}


def help_entries(index, verb_id=None):
    return tuple({"verb": index.verbs[action.verb_id].key,
                  "aliases": index.verbs[action.verb_id].aliases,
                  "description": action.help, "examples": action.examples,
                  "variants": tuple(v.suffix for v in action.variants)}
                 for action in index.actions.values() if action.public and not index.verbs[action.verb_id].adapter_only and
                 (verb_id is None or action.verb_id == verb_id))


def help_metadata(index):
    """공개 Action을 가진 Verb 선언만 도움말에 제공한다. Scope/효과 조회는 없다."""
    from dataclasses import replace

    public = {action.verb_id for action in index.actions.values() if action.public}
    entries = []
    for identity, verb in index.verbs.items():
        if identity not in public or verb.adapter_only:
            continue
        suffixes = {variant.suffix for action in index.actions.values()
                    if action.public and action.verb_id == identity
                    for variant in action.variants if variant.suffix}
        aliases = (*verb.aliases, *(key + " " + suffix for suffix in sorted(suffixes)
                                    for key in (verb.key, *verb.aliases)))
        entries.append(replace(verb, aliases=aliases))
    return tuple(entries)


def action_controls(caller, index, observed_at=None, *, provider_reference=None, verb_key=None, snapshot=None):
    return [row.as_web() if isinstance(row, ItemActionControl) else row for row in
            _presented_controls(caller, index, observed_at, provider_reference=provider_reference,
                                verb_key=verb_key, snapshot=snapshot)]


def _presented_controls(caller, index, observed_at=None, *, provider_reference=None, verb_key=None, snapshot=None):
    labels = _DisplayContexts(caller)
    if snapshot is not None:
        labels.rooms[caller.db_location_id, observed_at] = snapshot
    token = _current_labels.set(labels)
    try:
        with presentation_scope(caller):
            return _action_controls(caller, index, observed_at,
                                    provider_reference=provider_reference, verb_key=verb_key)
    finally:
        _current_labels.reset(token)


def _action_controls(caller, index, observed_at, *, provider_reference, verb_key):
    items = scoped_reads(caller, observed_at)
    pairs = provided(caller, index, item_entities=items.entities, provider_entities=items.entities,
                     get_observation=lambda: observation_snapshot(caller, observed_at))
    if provider_reference is not None:
        pairs = tuple((reference, binding) for reference, binding in pairs if reference == provider_reference)
    if verb_key is not None:
        pairs = tuple((reference, binding) for reference, binding in pairs
                      if index.verbs[index.actions[binding.action_id].verb_id].key == verb_key)
    # 이미 제공·가시성이 검증된 소지 Root의 Inside Scope를 함께 읽는다.
    inside_scopes = {
        f"inside:{reference.identity}" for reference, binding in pairs
        if reference is not None and reference.kind == ReferenceKind.ITEM
        and any([role.kinds == (ReferenceKind.ITEM,) and role.scope_from == "provider"
                and role.scope in (TargetScope.INSIDE, TargetScope.CARRIED_AND_INSIDE)
                and not role.include_carried_inside for role in index.actions[binding.action_id].roles])
    }
    if len(inside_scopes) > 1:
        cached_item_scopes(caller, inside_scopes, items.records, items.entities)
    controls = []
    for reference, binding in pairs:
        target = target_label(caller, reference, observed_at) if reference is not None else ""
        if target is None:
            continue
        provider = None
        if reference is not None:
            provider = items.resolve_entity(reference)
        service = index.services[binding.service_id]
        config = {argument.name: argument.default for argument in service.config_schema if argument.default is not None}
        config.update(binding.config)
        if hasattr(provider, "access") and not all(provider.access(caller, access)
                                                   for access in ("view", config.get("access", "call"))):
            continue
        if config.get("peaceful"):
            from world.rules import RuleError, require_peace

            try:
                require_peace(profile_snapshot(caller))
            except RuleError:
                continue
        if service.presenter is not None:
            controls.extend(service.presenter(caller, index, reference, binding, observed_at))
            continue
        action = index.actions[binding.action_id]
        roles = {"provider": [reference_json(reference)]} if reference is not None else {}
        if action.provider_from:
            roles[action.provider_from] = [reference_json(reference)]
        if any(role.required and role.name not in roles for role in action.roles):
            continue
        arguments = {arg.name: arg.default for arg in action.arguments if arg.default is not None}
        if any(arg.required and arg.name not in arguments for arg in action.arguments):
            continue
        for variant in action.variants:
            # 확인은 먼저 서버의 정상 요청이 발급한 토큰으로만 한다.
            if variant.confirmation_required or not variant.show_control:
                continue
            controls.append({"label": (target + " " + index.verbs[action.verb_id].key).strip(),
                             "description": action.help,
                             "action": {"action_id": action.id, "variant": variant.id,
                                        "roles": roles, "arguments": arguments}})
    if provider_reference is None and verb_key is None and any([
        reference is None and binding.action_id == "global.look_target" for reference, binding in pairs
    ]):
        from world.actions.global_actions import target_action

        controls.extend([{"label": f"{label} 봐", "action": target_action("look_target", reference)}
                         for scope, targets in _current_labels.get().carried_scopes().items()
                         if scope.startswith("inside:")
                         for reference, label in targets.items() if label is not None])
    return controls


def _for_provider(rows, reference):
    if reference is None:
        return []
    serialized = reference_json(reference)
    return [row for row in rows if (row.provider == reference if isinstance(row, ItemActionControl)
            else row.get("action", {}).get("roles", {}).get("provider") == [serialized])]


def provider_action_rows(caller, provider, observed_at=None, *, verb_key=None, snapshot=None):
    """Keep the validated item records available to text examples."""
    from world.actions.manifest import get_index

    if snapshot is not None:
        reference = snapshot.references.get(provider.pk)
    else:
        record = descriptor(provider)
        reference = record.reference if record else None
    if reference is None:
        return []
    rows = _presented_controls(caller, get_index(), observed_at, provider_reference=reference,
                               verb_key=verb_key, snapshot=snapshot)
    return _for_provider(rows, reference)


def provider_controls(caller, provider, observed_at=None, *, rows=None, verb_key=None):
    """객체 상세와 웹이 동일한 현재 Binding·Presenter 결과를 사용한다."""
    if rows is None:
        rows = provider_action_rows(caller, provider, observed_at, verb_key=verb_key)
    else:
        record = descriptor(provider)
        rows = _for_provider(rows, record.reference if record else None)
    return [row.as_web() if isinstance(row, ItemActionControl) else row for row in rows]


def provider_verbs(caller, provider, observed_at=None, *, verb_key=None, rows=None):
    """정적 도움말과 달리 지금 실제 제공되는 행동만 안내한다."""
    from world.actions.manifest import get_index

    index = get_index()
    if rows is None:
        rows = provider_action_rows(caller, provider, observed_at, verb_key=verb_key)
    else:
        record = descriptor(provider)
        rows = _for_provider(rows, record.reference if record else None)
    verbs = (index.verbs[index.actions[row.action_id if isinstance(row, ItemActionControl)
                                    else row["action"]["action_id"]].verb_id].key for row in rows)
    return tuple(dict.fromkeys(verb for verb in verbs if verb_key is None or verb == verb_key))
