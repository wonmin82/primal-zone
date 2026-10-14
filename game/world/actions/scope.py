"""매 명령의 실제 Scope를 재조회한다. CmdSet은 동사만 보관하고 대상 참조는 보관하지 않는다."""

from evennia import CmdSet
from world.actions.manifest import get_index
from world.actions.resolver import provided

CMDSET_KEY = "PrimalActions"


def refresh(caller):
    from commands.action_command import DynamicActionCommand

    index = get_index()
    # 입력 전용 Replace의 낮은 우선순위를 Dynamic CmdSet이 덮지 않는다.
    if any(cmdset and cmdset.mergetype == "Replace" for owner in (caller, caller.account) if owner
           for cmdset in owner.cmdset.cmdset_stack):
        caller.cmdset.remove(CMDSET_KEY)
        caller.ndb.action_scope_signature = None
        return
    offered = provided(caller, index)
    verbs = {index.actions[binding.action_id].verb_id for _, binding in offered}
    current_protected = set()
    for cmdset in caller.cmdset.cmdset_stack:
        if cmdset and cmdset.key != CMDSET_KEY:
            current_protected.update(key.casefold() for key in cmdset.get_all_cmd_keys_and_aliases())
    if caller.location:
        for obj in caller.location.contents:
            if obj.destination:
                current_protected.update(key.casefold() for key in (obj.key, *obj.aliases.all()))
    verbs = {identity for identity in verbs if not current_protected.intersection(
             key.casefold() for key in (index.verbs[identity].key, *index.verbs[identity].aliases))}
    suffixes_by_verb = {identity: tuple(sorted({variant.suffix for _, binding in offered
                      if index.actions[binding.action_id].verb_id == identity
                      for variant in index.actions[binding.action_id].variants if variant.suffix}))
                      for identity in verbs}
    suffixes_by_verb = {identity: suffixes for identity, suffixes in suffixes_by_verb.items()
                       if not current_protected.intersection(
                           (key + " " + suffix).casefold() for key in
                           (index.verbs[identity].key, *index.verbs[identity].aliases) for suffix in suffixes)}
    verbs = set(suffixes_by_verb)
    signature = (id(index), tuple(sorted(suffixes_by_verb.items())))
    if caller.ndb.action_scope_signature == signature:
        return
    caller.cmdset.remove(CMDSET_KEY)
    if verbs:
        cmdset = CmdSet(key=CMDSET_KEY)
        cmdset.priority = 10
        cmdset.duplicates = False
        for identity in sorted(verbs):
            verb = index.verbs[identity]
            suffixes = suffixes_by_verb[identity]
            aliases = (*verb.aliases, *(key + " " + suffix for key in (verb.key, *verb.aliases) for suffix in sorted(suffixes)))
            command = DynamicActionCommand(key=verb.key, aliases=aliases)
            command.verb_id = identity
            cmdset.add(command)
        caller.cmdset.add(cmdset, persistent=False)
    caller.ndb.action_scope_signature = signature


def invalidate(caller):
    caller.ndb.action_scope_signature = None
