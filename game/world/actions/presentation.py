"""공통 선언의 순수 Help/웹 표현. 번호 할당·게임 효과·확정 토큰 발급을 하지 않는다."""

from world.actions.presentation_context import presentation_scope, profile_snapshot
from world.actions.resolver import provided
from world.selection_numbers.api import descriptor, label, number_for, resolve_reference


def reference_json(reference):
    return {"kind": str(reference.kind), "identity": reference.identity, "scope_id": reference.scope_id}


def help_entries(index, verb_id=None):
    return tuple({"verb": index.verbs[action.verb_id].key,
                  "aliases": index.verbs[action.verb_id].aliases,
                  "description": action.help, "examples": action.examples,
                  "variants": tuple(v.suffix for v in action.variants)}
                 for action in index.actions.values() if action.public and
                 (verb_id is None or action.verb_id == verb_id))


def help_metadata(index):
    """공개 Action을 가진 Verb 선언만 도움말에 제공한다. Scope/효과 조회는 없다."""
    from dataclasses import replace

    public = {action.verb_id for action in index.actions.values() if action.public}
    entries = []
    for identity, verb in index.verbs.items():
        if identity not in public:
            continue
        suffixes = {variant.suffix for action in index.actions.values()
                    if action.public and action.verb_id == identity
                    for variant in action.variants if variant.suffix}
        aliases = (*verb.aliases, *(key + " " + suffix for suffix in sorted(suffixes)
                                    for key in (verb.key, *verb.aliases)))
        entries.append(replace(verb, aliases=aliases))
    return tuple(entries)


def action_controls(caller, index, observed_at=None, *, provider_reference=None, verb_key=None):
    with presentation_scope(caller):
        return _action_controls(caller, index, observed_at,
                                provider_reference=provider_reference, verb_key=verb_key)


def _action_controls(caller, index, observed_at, *, provider_reference, verb_key):
    from dataclasses import replace

    pairs = provided(caller, index)
    if provider_reference is not None:
        pairs = tuple((reference, binding) for reference, binding in pairs if reference == provider_reference)
    if verb_key is not None:
        pairs = tuple((reference, binding) for reference, binding in pairs
                      if index.verbs[index.actions[binding.action_id].verb_id].key == verb_key)
    records = {ref: descriptor(resolve_reference(ref)) for ref, _ in pairs if ref is not None}
    controls = []
    for reference, binding in pairs:
        provider = resolve_reference(reference) if reference is not None else None
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
        record = records.get(reference)
        target = label(replace(record, number=number_for(reference))) if record else ""
        for variant in action.variants:
            # 확인은 먼저 서버의 정상 요청이 발급한 토큰으로만 한다.
            if variant.confirmation_required or not variant.show_control:
                continue
            controls.append({"label": (target + " " + index.verbs[action.verb_id].key).strip(),
                             "description": action.help,
                             "action": {"action_id": action.id, "variant": variant.id,
                                        "roles": roles, "arguments": arguments}})
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


def provider_verbs(caller, provider, observed_at=None, *, verb_key=None):
    """정적 도움말과 달리 지금 실제 제공되는 행동만 안내한다."""
    from world.actions.manifest import get_index

    index = get_index()
    return tuple(dict.fromkeys(index.verbs[index.actions[row["action"]["action_id"]].verb_id].key
                               for row in provider_controls(caller, provider, observed_at, verb_key=verb_key)))
