"""공통 선언의 순수 Help/웹 표현. 번호 할당·게임 효과·확정 토큰 발급을 하지 않는다."""

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


def action_controls(caller, index, observed_at=None):
    from dataclasses import replace

    pairs = provided(caller, index)
    records = {ref: descriptor(resolve_reference(ref)) for ref, _ in pairs}
    controls = []
    for reference, binding in pairs:
        service = index.services[binding.service_id]
        if service.presenter is not None:
            controls.extend(service.presenter(caller, index, reference, binding, observed_at))
            continue
        action = index.actions[binding.action_id]
        roles = {"provider": [reference_json(reference)]}
        if action.provider_from:
            roles[action.provider_from] = [reference_json(reference)]
        if any(role.required and role.name not in roles for role in action.roles):
            continue
        arguments = {arg.name: arg.default for arg in action.arguments if arg.default is not None}
        if any(arg.required and arg.name not in arguments for arg in action.arguments):
            continue
        record = records[reference]
        target = label(replace(record, number=number_for(reference))) if record else "대상"
        for variant in action.variants:
            # 확인은 먼저 서버의 정상 요청이 발급한 토큰으로만 한다.
            if variant.confirmation_required or not variant.show_control:
                continue
            controls.append({"label": target + " " + index.verbs[action.verb_id].key,
                             "description": action.help,
                             "action": {"action_id": action.id, "variant": variant.id,
                                        "roles": roles, "arguments": arguments}})
    return controls
