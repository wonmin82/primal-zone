"""치료 대상 검증과 단일 transaction. 명령과 자동 전투가 공유한다."""

from time import time

from world import presentation as view
from world import rules
from world.multiplayer import after_change, object_by_id, world_change
from world.targets import names, parse_selector, resolve, room_objects


def heal_target(caller, identity=None):
    from typeclasses.explorers import Explorer
    from typeclasses.parties import party_for

    target = object_by_id(identity) if identity and identity != caller.id else caller
    if target is caller:
        return target
    party = party_for(caller)
    if not isinstance(target, Explorer) or target.location != caller.location or not party or party_for(target) != party:
        raise rules.RuleError("같은 방의 파티원만 치료할 수 있다.")
    from world.observation import can_perceive, context_for

    if not can_perceive(target, context_for(caller)):
        raise rules.RuleError("지금은 치료할 동료를 식별할 수 없다.")
    return target


def use_support(caller, action, name=""):
    now = time()
    with world_change():
        target = caller
        if action == "heal" and name.strip():
            from typeclasses.explorers import Explorer

            objects = [obj for obj in room_objects(caller) if isinstance(obj, Explorer)]
            target = resolve(objects, parse_selector(name, [n for obj in objects for n in names(obj)]), caller, "치료")[0]
            target = heal_target(caller, target.id)
        profile = caller.profile()
        caller.accrue_recovery(profile, now)
        target_profile = profile if target is caller else target.profile()
        if target is not caller:
            target.accrue_recovery(target_profile, now)
        if profile.get("combat_target"):
            rules.queue_action(profile, action, now, target_profile)
            profile["heal_target"] = target.id if action == "heal" else None
            caller.save_profile(profile)
            message = "다음 차례에는 공격 대신 " + ("붕대를 사용한다." if action == "bandage" else {"heal": "치료한다.", "breathing": "호흡을 가다듬는다."}[action])
            after_change(lambda: caller.msg(message))
        else:
            outcome = rules.support_action(profile, action, now, target_profile)
            caller.save_profile(profile)
            if target is not caller:
                target.save_profile(target_profile)
                after_change(lambda: target.msg(f"{caller.key}의 치료로 HP {outcome['amount']}을 회복했다."))
            message = view.support_result(outcome, target.key if target is not caller else None)
            after_change(lambda: caller.msg(message))
