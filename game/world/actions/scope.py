"""매 명령의 실제 Scope를 재조회한다. CmdSet은 동사만 보관하고 대상 참조는 보관하지 않는다."""

from evennia import CmdSet
from world.actions.manifest import get_index
from world.actions.resolver import provided

CMDSET_KEY = "PrimalActions"


def refresh(caller):
    from commands.action_command import DynamicActionCommand

    index = get_index()
    offered = provided(caller, index)
    verbs = {index.actions[binding.action_id].verb_id for _, binding in offered}
    suffixes_by_verb = {identity: tuple(sorted({variant.suffix for _, binding in offered
                      if index.actions[binding.action_id].verb_id == identity
                      for variant in index.actions[binding.action_id].variants if variant.suffix}))
                      for identity in verbs}
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
