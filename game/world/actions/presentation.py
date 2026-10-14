"""공통 선언의 순수 Help/웹 표현. 번호 할당·게임 효과·확정 토큰 발급을 하지 않는다."""

from collections import Counter

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


def action_controls(caller, index):
    from dataclasses import replace

    pairs = provided(caller, index)
    records = {ref: descriptor(resolve_reference(ref)) for ref, _ in pairs}
    counts = Counter((record.scope_id, record.group_id) for record in records.values() if record)
    controls = []
    for reference, binding in pairs:
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
        target = label(replace(record, number=number_for(reference)), counts[(record.scope_id, record.group_id)]) if record else "대상"
        for variant in action.variants:
            # 확인은 먼저 서버의 정상 요청이 발급한 토큰으로만 한다.
            if variant.confirmation_required:
                continue
            controls.append({"label": target + " " + index.verbs[action.verb_id].key,
                             "description": action.help,
                             "action": {"action_id": action.id, "variant": variant.id,
                                        "roles": roles, "arguments": arguments}})
    return controls
