"""공통 선언의 순수 Help/웹 표현. 번호 할당·게임 효과·확정 토큰 발급을 하지 않는다."""

from contextvars import ContextVar
from dataclasses import dataclass, field

from world.actions.presentation_context import (
    item_presentation,
    presentation_scope,
    profile_snapshot,
)
from world.actions.resolver import provided
from world.actions.schema import ReferenceKind
from world.selection_display import displays, room_snapshot
from world.selection_numbers.api import descriptor, numbered_records, resolve_reference

_current_labels = ContextVar("action_selection_labels", default=None)


@dataclass
class _DisplayContexts:
    caller: object
    room: object
    scopes: dict = field(default_factory=dict)
    carried: dict | None = None

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
        contexts = _DisplayContexts(caller, room_snapshot(caller, observed_at) if reference.scope_id.startswith("room:") else None)
    if reference.scope_id.startswith("room:"):
        if contexts.room is None:
            contexts.room = room_snapshot(caller, observed_at)
        if reference not in contexts.room.records:
            return None
        return contexts.room.labels[int(reference.identity)]
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
    token = _current_labels.set(_DisplayContexts(caller, snapshot))
    try:
        with presentation_scope(caller):
            return _action_controls(caller, index, observed_at,
                                    provider_reference=provider_reference, verb_key=verb_key)
    finally:
        _current_labels.reset(token)


def _action_controls(caller, index, observed_at, *, provider_reference, verb_key):
    items = item_presentation(caller, observed_at)
    pairs = provided(caller, index, item_entities=items.entities)
    if provider_reference is not None:
        pairs = tuple((reference, binding) for reference, binding in pairs if reference == provider_reference)
    if verb_key is not None:
        pairs = tuple((reference, binding) for reference, binding in pairs
                      if index.verbs[index.actions[binding.action_id].verb_id].key == verb_key)
    controls = []
    for reference, binding in pairs:
        target = target_label(caller, reference, observed_at) if reference is not None else ""
        if target is None:
            continue
        provider = None
        if reference is not None:
            provider = items.item(reference) if reference.kind == ReferenceKind.ITEM else resolve_reference(reference)
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


def provider_controls(caller, provider, observed_at=None, *, rows=None, verb_key=None):
    """객체 상세와 웹이 동일한 현재 Binding·Presenter 결과를 사용한다."""
    from world.actions.manifest import get_index

    record = descriptor(provider)
    if record is None:
        return []
    reference = reference_json(record.reference)
    if rows is None:
        rows = action_controls(caller, get_index(), observed_at,
                               provider_reference=record.reference, verb_key=verb_key)
    return [row for row in rows if row.get("action", {}).get("roles", {}).get("provider") == [reference]]


def provider_verbs(caller, provider, observed_at=None, *, verb_key=None, rows=None):
    """정적 도움말과 달리 지금 실제 제공되는 행동만 안내한다."""
    from world.actions.manifest import get_index

    index = get_index()
    verbs = (index.verbs[index.actions[row["action"]["action_id"]].verb_id].key
             for row in provider_controls(caller, provider, observed_at, verb_key=verb_key, rows=rows))
    return tuple(dict.fromkeys(verb for verb in verbs if verb_key is None or verb == verb_key))
