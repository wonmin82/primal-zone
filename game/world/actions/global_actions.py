"""명시적 명령과 Evennia Exit가 공통 Gateway에 전달하는 전역 행동."""

from world import presentation as view
from world import rules
from world import text as ft
from world.multiplayer import after_change

from .gateway import ActionResult, ResultStatus, emit, execute
from .resolver import ActionInvocation
from .schema import (
    ActionBinding,
    ActionDefinition,
    ArgumentDefinition,
    ContentPackage,
    ExecutionPolicy,
    GlobalSource,
    ReferenceKind,
    RoleDefinition,
    ScopeRoot,
    ServiceDefinition,
    SyntaxVariant,
    VerbDefinition,
)

LOOK_TARGET = RoleDefinition("subject", (
    ReferenceKind.ACTOR, ReferenceKind.ENEMY, ReferenceKind.OBJECT,
    ReferenceKind.CORPSE, ReferenceKind.DOOR, ReferenceKind.ITEM,
), scope_root=ScopeRoot.CALLER, include_carried_inside=True)


def target_action(name, reference):
    from .presentation import reference_json

    return {
        "action_id": "global." + name,
        "variant": "adapter",
        "roles": {"subject": [reference_json(reference)]},
        "arguments": {},
    }


def _item_appearance(caller, item, observed_at):
    from world.content import ITEMS
    from world.equipment_service import selector_label, state_summary
    from world.lighting_service import status as light_status

    definition = ITEMS[item.definition_id]
    detail = (light_status(caller, item, observed_at) if definition.get("light_source") and not item.parent_item_id
              else state_summary(item, observed_at=observed_at))
    return ft.compact(ft.token("item", selector_label(caller, item, with_parents=True)),
                      definition.get("description", "탐사 중 사용하는 물품이다."),
                      detail, definition.get("firearm_family", ""))


def _room_appearance(caller, entity, observed_at):
    from world.state import duel_observation

    return ft.join((caller.at_look(entity, observed_at=observed_at),
                    *duel_observation(entity, caller, observed_at)), "\n")


def _observe_target(caller, entity, kind, observed_at, *, typed=False):
    from world.actions.gateway import target_unavailable

    def unavailable():
        if typed:
            return target_unavailable("global.look_target")
        return rules.RuleError("지금 살펴볼 수 없는 대상입니다.")

    if kind == ReferenceKind.ITEM:
        return _item_appearance(caller, entity, observed_at)
    from world.observation import can_perceive, context_for, perceives

    observation = context_for(caller, observed_at=observed_at)
    if not can_perceive(entity, observation) or (
            getattr(entity, "supports_shared_combat", False) and entity.db.state != "alive"):
        raise unavailable()
    if kind == ReferenceKind.DOOR:
        from world.content.doors import DOORS
        from world.doors import DoorTarget, describe_door, identity_for_exit

        identity = identity_for_exit(entity)
        if identity not in DOORS or not perceives(observation.snapshot, "normal"):
            raise unavailable()
        target = DoorTarget(identity, entity.key, entity.pk)
        return describe_door(caller, target, observed_at)
    return _room_appearance(caller, entity, observed_at)


def prepare_observation(caller, invocation):
    from world.lifecycle import reconcile_room

    if caller.location:
        reconcile_room(caller.location)


def look_target(context):
    from commands.character import time

    entity, = context.roles["subject"]
    reference, = dict(context.invocation.roles)["subject"]
    observed_at = time()
    output = _observe_target(context.caller, entity, reference.kind, observed_at, typed=True)
    after_change(lambda: context.caller.push_state(observed_at=observed_at))
    return ActionResult(messages=(output,))


def select_look_reference(caller, selector, observed_at):
    from typeclasses.loot import DroppedLoot
    from world.doors import door_rows_by_endpoint
    from world.equipment_service import entity_runtime
    from world.item_entities.api import carried_items
    from world.observation import context_for, perceives
    from world.selection_numbers.api import descriptor, numbered_records
    from world.targets import room_objects

    entities = [entity for entity in room_objects(caller, observed_at=observed_at)
                if not isinstance(entity, DroppedLoot)]
    doors_by_endpoint = door_rows_by_endpoint(entities)
    if entity_runtime(caller):
        entities.extend(carried_items(caller))
    candidates = {record.reference: (record, entity) for entity in entities
                  if (record := descriptor(entity, doors_by_endpoint=doors_by_endpoint)) is not None
                  and record.reference.kind in LOOK_TARGET.kinds
                  and record.name == selector.name}
    doors = [ref for ref in candidates if ref.kind == ReferenceKind.DOOR]
    if doors and not perceives(context_for(caller, observed_at=observed_at).snapshot, "normal"):
        for ref in doors:
            del candidates[ref]
    matches = [record.reference for record in numbered_records([record for record, _ in candidates.values()])
               if record.number == selector.index]
    if len(matches) != 1:
        raise rules.RuleError("지금 살펴볼 수 없는 대상입니다." if not matches else
                              "여러 범위의 대상이 이 이름과 번호에 일치합니다.")
    reference, = matches
    return reference, candidates[reference][1]


def look(context):
    from commands.character import time

    caller = context.caller
    messages = []
    from typeclasses.exits import Exit
    from typeclasses.loot import Corpse
    from world.content import ITEMS
    from world.lifecycle import reconcile_room
    from world.target_presentation import corpse_overview
    from world.targets import (
        Mode,
        item_selector,
        names,
        parse_exact_selector,
        parse_selector,
        resolve,
        room_objects,
    )

    name = context.arguments.get("query", "").strip()
    observed_at = time()
    from world.content.economy import CURRENCY
    from world.currency import is_currency

    exact = parse_exact_selector(name)
    if exact:
        if caller.location:
            reconcile_room(caller.location, observed_at)
        try:
            reference, entity = select_look_reference(caller, exact, observed_at)
            messages.append(_observe_target(caller, entity, reference.kind, observed_at))
        except rules.RuleError as error:
            messages.append(ft.token("error", str(error)))
        after_change(lambda: caller.push_state(observed_at=observed_at))
        return ActionResult(messages=messages)

    if is_currency(name):
        messages.append(ft.compact(CURRENCY["name"], CURRENCY["description"]))
        return ActionResult(messages=messages)
    if name and caller.location:
        from world.doors import look_door
        try:
            # 인용처럼 생긴 무효 입력도 현재 방과 소지품의 실제 이름일 수 있다.
            door_output = None if name.startswith('"') else look_door(caller, name, observed_at)
        except rules.RuleError as error:
            messages.append(ft.text(ft.token("error", str(error)), kind="error"))
            return ActionResult(messages=messages)
        if door_output is not None:
            messages.append(door_output)
            return ActionResult(messages=messages)
        from world.navigation import blocked_exit_message

        message = blocked_exit_message(caller.zone, name)
        if message:
            messages.append(ft.text(message))
            return ActionResult(messages=messages)
        # 실제 Exit도 같은 selector로 선택한다. 관찰만 할 때는 로컬 갱신/at_desc도 실행하지 않는다.
        from world.targets import matching, ordered, visible

        objects = ordered([obj for obj in caller.location.exits if visible(obj, caller)])

        try:
            selector = parse_selector(name, [n for obj in objects for n in names(obj)])
        except rules.RuleError:
            selector = None  # 소지품의 실제 이름도 포함하는 기존 봐 경로에서 검증한다.
        candidates = matching(objects, selector) if selector else []
        if candidates and all([isinstance(obj, Exit) for obj in candidates]):
            try:
                selected = resolve(objects, selector, caller)
                messages.append(
                    ft.join(
                        [obj.return_appearance(caller, observed_at=observed_at) for obj in selected],
                        "\n\n",
                    )
                )
            except rules.RuleError as error:
                messages.append(ft.token("error", str(error)))
            return ActionResult(messages=messages)
        reconcile_room(caller.location, observed_at)
        from world.actions.loot_presentation import ground_lookup_objects

        objects = ground_lookup_objects(
            caller, room_objects(caller, observed_at=observed_at), name, observed_at,
        )
        profile = caller.profile_snapshot()
        inventory = {
            key: ITEMS[key]
            for key, count in profile["inventory"].items()
            if count > 0
        }
        try:
            selector = parse_selector(
                name,
                [n for obj in objects for n in names(obj)]
                + [n for key, data in inventory.items() for n in (key, data["name"])],
                b1=True,
                literal_names=[obj.key for obj in objects] + [data["name"] for data in inventory.values()],
            )
            if matching(objects, selector):
                selected = resolve(objects, selector, caller, observed_at=observed_at)
                if selector.mode == Mode.ALL and all([isinstance(obj, Corpse) for obj in selected]):
                    output = corpse_overview(
                        selected,
                        caller,
                        observed_at,
                        pool=[obj for obj in objects if isinstance(obj, Corpse)],
                    )
                else:
                    output = ft.join(
                        [_room_appearance(caller, obj, observed_at) for obj in selected],
                        "\n\n",
                    )
                messages.append(output)
            else:
                from world.equipment_service import entity_runtime, resolve_item

                if entity_runtime(caller):
                    item = resolve_item(caller, name, "봐")
                    messages.append(_item_appearance(caller, item, observed_at))
                    after_change(lambda: caller.push_state(observed_at=observed_at))
                    return ActionResult(messages=messages)
                identity = item_selector(name, inventory, "봐")
                from world import lighting

                status = lighting.status(profile, identity, observed_at) if ITEMS[identity].get("light_source") else None
                messages.append(view.item_appearance(identity, light_status=status))
        except rules.RuleError as error:
            messages.append(ft.token("error", str(error)))
            after_change(lambda: caller.push_state(observed_at=observed_at))
            return ActionResult(messages=messages)
        after_change(lambda: caller.push_state(observed_at=observed_at))
        return ActionResult(messages=messages)
    if caller.location:
        messages.append(caller.at_look(caller.location, observed_at=observed_at))
    else:
        target = caller.search(name) if name else None
        if target is not None:
            messages.append(caller.at_look(target))
        elif not name:
            messages.append("You have no location to look at!")
    after_change(lambda: caller.push_state(observed_at=observed_at))
    return ActionResult(messages=messages)


def help_page(context):
    from commands.account_commands import Who
    from commands.help_pages import help_page, root_page
    from commands.registry import COMMANDS

    commands = [cls for cls in [*COMMANDS, Who] if getattr(cls, "input_style", None)]
    query = context.arguments.get("query", "").strip()
    page = help_page(query, commands) if query else root_page()
    if page is None:
        raise rules.RuleError("등록된 명령을 찾을 수 없습니다. '도움'에서 확인하세요.")
    return ActionResult(messages=(page,))


def status(context):
    caller = context.caller
    return ActionResult(messages=(view.status(caller.key, caller.profile_snapshot()),))


def return_home(context):
    from world.bootstrap import get_room

    caller = context.caller
    rules.require_peace(caller.profile_snapshot())
    return ActionResult(changed=bool(caller.move_to(get_room("support_roof"), quiet=True)))


def traverse(context):
    from typeclasses.exits import Exit

    caller = context.caller
    identity = context.arguments["exit_id"]
    selected = Exit.objects.select_for_update().filter(pk=identity, db_location_id=caller.db_location_id).first()
    if caller.location is None or selected is None or not selected.destination:
        raise rules.RuleError("출구를 이용할 수 없습니다.")
    if context.invocation.origin == "web" and not selected.access(caller, "view"):
        raise rules.RuleError("출구를 이용할 수 없습니다.")
    if not any([command.access(caller, "cmd") for command in selected.create_exit_cmdset(selected) if command.is_exit]):
        raise rules.RuleError("출구를 이용할 수 없습니다.")
    if not selected.access(caller, "traverse"):
        if selected.db.err_traverse:
            return ActionResult(ResultStatus.REFUSED, messages=(selected.db.err_traverse,))
        selected.at_failed_traverse(caller)
        return ActionResult(ResultStatus.REFUSED)
    origin = caller.location
    destination = selected.destination
    traversed = selected.at_traverse(caller, destination)
    # Evennia의 기본 at_traverse는 성공해도 값을 반환하지 않는다.
    if traversed is False or caller.location == origin or caller.location != destination:
        return ActionResult(ResultStatus.REFUSED)

    from evennia.server.signals import SIGNAL_EXIT_TRAVERSED

    after_change(lambda: SIGNAL_EXIT_TRAVERSED.send(sender=selected, traverser=caller))
    return ActionResult(changed=True)


def web_combat_target(context):
    refs = context.roles.get("subject", ())
    if context.invocation.origin != "web":
        return None
    if len(refs) != 1 or context.arguments.get("query"):
        raise rules.RuleError("원래 전투 대상을 지정하세요.")
    enemy = refs[0]
    if (not enemy.shared_combat_active
            or context.arguments.get("generation") != (enemy.db.combat_generation or 0)
            or context.arguments.get("lifecycle") != (enemy.db.combat_lifecycle or 0)):
        raise rules.RuleError("원래 전투 대상의 상태가 바뀌었습니다.")
    return enemy


def attack(context):
    from typeclasses.actors import Actor

    caller = context.caller
    query = context.arguments["query"]
    from world.lifecycle import reconcile_room
    from world.targets import names, parse_selector, resolve, room_objects

    enemy = web_combat_target(context)
    if enemy:
        caller.start_combat(enemy)
        return ActionResult(changed=True)
    name = query.strip()
    current = caller.combat_target()
    reconcile_room(caller.location)
    objects = room_objects(caller)
    enemy = (
        resolve(
            objects,
            parse_selector(name, [n for obj in objects for n in names(obj)], b1=True,
                           literal_names=[obj.key for obj in objects]),
            caller,
            "때려",
            lambda obj: isinstance(obj, Actor) and obj.shared_combat_active,
        )[0]
        if name
        else current
    )
    if not enemy:
        raise rules.RuleError("사용법: 어린청소룡 때려 · '봐'로 사냥 대상을 확인하세요.")
    caller.start_combat(enemy)
    return ActionResult(changed=True)



QUEUED_ATTACK_NAMES = {"heavy": "강타", "shooting": "쏴", "insight": "간파", "suppress": "견제"}


def queue_attack(context):
    skill = context.arguments["skill"]
    context.caller.change(lambda profile: rules.queue_action(profile, skill))
    return ActionResult(messages=(ft.text("다음 차례에 ", ft.token("command", QUEUED_ATTACK_NAMES[skill]),
                                          " 행동을 준비한다."),), changed=True)


def support(context):
    from world.skill_services import use_support

    use_support(context.caller, context.arguments["skill"], context.arguments["query"])
    return ActionResult(changed=True)


def flee(context):
    caller = context.caller
    if not caller.profile_snapshot().get("combat_target"):
        raise rules.RuleError("진행 중인 교전이 없습니다.")
    caller.leave_combat()
    return ActionResult(messages=("교전을 끝냈습니다. 적은 일정 시간 아무도 싸우지 않으면 회복합니다.",),
                        changed=True)


def party_attack(context):
    from typeclasses.actors import Actor

    caller = context.caller
    query = context.arguments["query"]
    from commands.party import required
    from world.targets import (
        Mode,
        matching,
        matching_formal_names,
        names,
        normalized,
        parse_selector,
        room_objects,
        strict_single,
    )
    from world.targets import resolve as resolve_target

    party = required(caller)
    party.require_leader(caller)
    target = web_combat_target(context) or caller.combat_target()
    if query.strip():
        pool = [obj for obj in room_objects(caller) if isinstance(obj, Actor) and obj.supports_shared_combat]
        selector = parse_selector(query, [name for obj in pool for name in names(obj)], b1=True,
                                  literal_names=[obj.key for obj in pool])
        # 일행공격의 무번호 복수 후보 거절은 일반 공격의 기본 첫 대상과 다르다.
        if selector.mode == Mode.DEFAULT:
            matches = matching(pool, selector)
            formal = matching_formal_names(matches, normalized(selector.name), lambda obj: obj.key)
            strict_single(formal or matches, selector, "일행공격")
        target = resolve_target(pool, selector, caller, "일행공격")[0]
    party.attack(caller, target)
    return ActionResult(changed=True)


DUEL_SKILLS = {
    "기본공격": "attack",
    **{label: key for key, label in QUEUED_ATTACK_NAMES.items()},
    "치료": "heal",
    "호흡": "breathing",
}


def duel_target(context):
    from world.selection_numbers.api import resolve_reference

    from .resolver import select_role

    targets = context.roles.get("subject", ())
    query = context.arguments.get("query", "")
    if context.invocation.origin == "web":
        if len(targets) != 1 or query:
            raise rules.RuleError("원래 대련 상대를 지정하세요.")
        return targets[0]
    if not query.strip():
        raise rules.RuleError("대련 상대의 이름을 입력하세요.")
    reference, = select_role(context.caller, COMBAT_TARGET, query)
    actor = resolve_reference(reference)
    if actor is None:
        raise rules.RuleError("대련 상대의 위치가 바뀌었습니다.")
    return actor


def duel_start(context):
    from world import duel

    actor = duel_target(context)
    generation = context.arguments.get("generation")
    if context.invocation.origin == "web" and generation is None:
        raise rules.RuleError("대련 상대의 현재 상태를 다시 확인하세요.")
    duel.start(actor, context.caller, expected_generation=generation)
    return ActionResult(changed=True)


def duel_encounter(context, actor):
    from world import duel

    if context.invocation.origin == "web":
        identity = context.arguments.get("encounter_id")
        if not identity:
            raise rules.RuleError("원래 대련을 지정하세요.")
        return identity
    status = duel.projection(actor, context.caller)
    if status is None or status["state"] != "active" or not status["participant"]:
        raise rules.RuleError("참가 중인 대련이 없습니다.")
    return status["identity"]


def duel_act(context):
    from world import duel

    actor = duel_target(context)
    changed = duel.act(actor, context.caller, duel_encounter(context, actor), skill=context.arguments["skill"])
    return ActionResult(changed=changed)


def duel_surrender(context):
    from world import duel

    actor = duel_target(context)
    changed = duel.surrender(actor, context.caller, duel_encounter(context, actor))
    return ActionResult(changed=changed)



def party_defender(context):
    from commands.party import required
    from world.multiplayer import object_by_id

    party = required(context.caller)
    defender = object_by_id(party.state()["tactics"].get("defender_id"))
    return ActionResult(messages=(ft.text("방어 담당: ", ft.token("player", defender.key) if defender else "없음"),))


def party_defense(context):
    from commands.party import member, required

    caller = context.caller
    query = context.arguments["query"]
    party = required(caller)
    party.set_defender(caller, None if query.strip() == "해제" else member(caller, query))
    return ActionResult(changed=True)


def transfer_item(context):
    from typeclasses.explorers import Explorer
    from world.currency import currency_names, currency_request, format_currency
    from world.equipment_service import entity_runtime
    from world.item_transfer_native import transfer
    from world.item_transfers import transfer_currency
    from world.targets import names, parse_relation, parse_selector, resolve, room_objects

    caller = context.caller
    query = context.arguments["query"]
    if not entity_runtime(caller):
        raise rules.RuleError("Native 아이템 소지 상태를 확인할 수 없습니다.")
    recipient = None
    if context.invocation.action_id == "global.give":
        objects = room_objects(caller)
        selector, query = parse_relation(query, "에게", [name for obj in objects for name in names(obj)])
        recipient = resolve(objects, selector, caller, "줘", lambda obj: isinstance(obj, Explorer))[0]

    currency = currency_request(parse_selector(query, currency_names()))
    if currency:
        if currency[1].index:
            raise rules.RuleError("보유 보급칩은 번호 없이 금액 또는 모두로 지정하세요.")
        quantity = transfer_currency(caller, currency[0], recipient)
        item = ft.token("reward", format_currency(quantity))
        particle = "을"
    else:
        identity, quantity = transfer(caller, query, recipient=recipient)
        item = ft.text(ft.item(identity), f" {quantity}개")
        particle = "를"
    if recipient is None:
        message = ft.text(item, particle, " 바닥에 내려놓았다. 다른 탐사자도 가져갈 수 있다.")
    else:
        message = ft.text(ft.token("player", recipient.key), "에게 ", item, particle, " 건넸다.")
        notice = ft.text(ft.token("player", caller.key), "에게서 ", item, particle, " 받았다.")
        after_change(lambda: recipient.msg(notice))
    return ActionResult(messages=(message,), changed=True)


QUERY = ArgumentDefinition("query", default="")
COMBAT_TARGET = RoleDefinition("subject", (ReferenceKind.ACTOR,), required=False, scope_root=ScopeRoot.CURRENT_ROOM)
COMBAT_GENERATION = ArgumentDefinition("generation", int, required=False, minimum=0)
COMBAT_LIFECYCLE = ArgumentDefinition("lifecycle", int, required=False, minimum=0)
COMBAT_ACTIONS = {"attack", "party_attack"}
DUEL_ACTIONS = {"duel_start", "duel_act", "duel_surrender"}
DUEL_ID = ArgumentDefinition("encounter_id", required=False)
DECLARATIONS = (
    ("look", look, ExecutionPolicy.STATE_CHANGE, (QUERY,)),
    ("look_target", look_target, ExecutionPolicy.STATE_CHANGE, ()),
    ("help", help_page, ExecutionPolicy.READ_ONLY, (QUERY,)),
    ("status", status, ExecutionPolicy.READ_ONLY, ()),
    ("return", return_home, ExecutionPolicy.STATE_CHANGE, ()),
    ("attack", attack, ExecutionPolicy.STATE_CHANGE, (QUERY,)),
    ("queue_attack", queue_attack, ExecutionPolicy.STATE_CHANGE,
     (ArgumentDefinition("skill", choices=tuple(QUEUED_ATTACK_NAMES)),)),
    ("support", support, ExecutionPolicy.STATE_CHANGE,
     (ArgumentDefinition("skill", choices=("heal", "breathing")), QUERY)),
    ("flee", flee, ExecutionPolicy.STATE_CHANGE, ()),
    ("party_attack", party_attack, ExecutionPolicy.STATE_CHANGE, (QUERY,)),
    ("duel_start", duel_start, ExecutionPolicy.STATE_CHANGE, (QUERY, COMBAT_GENERATION)),
    ("duel_act", duel_act, ExecutionPolicy.STATE_CHANGE,
     (QUERY, DUEL_ID, ArgumentDefinition("skill", default="attack", choices=tuple(DUEL_SKILLS.values())))),
    ("duel_surrender", duel_surrender, ExecutionPolicy.STATE_CHANGE, (QUERY, DUEL_ID)),
    ("party_defense", party_defense, ExecutionPolicy.STATE_CHANGE, (QUERY,)),
    ("party_defender", party_defender, ExecutionPolicy.READ_ONLY, (QUERY,)),
    ("drop", transfer_item, ExecutionPolicy.STATE_CHANGE, (QUERY,)),
    ("give", transfer_item, ExecutionPolicy.STATE_CHANGE, (QUERY,)),
    ("traverse", traverse, ExecutionPolicy.STATE_CHANGE, (ArgumentDefinition("exit_id", int, minimum=1),)),
)
PACKAGE = ContentPackage(
    "game.global_actions",
    verbs=tuple(VerbDefinition("global." + key + "_verb", "전역-" + key, adapter_only=True)
                for key, _, _, _ in DECLARATIONS),
    actions=tuple(ActionDefinition("global." + key, "global." + key + "_verb",
                                   (LOOK_TARGET,) if key == "look_target" else
                                   (COMBAT_TARGET,) if key in COMBAT_ACTIONS | DUEL_ACTIONS else (),
                                   (SyntaxVariant("adapter", "", show_control=False),),
                                   arguments=(*arguments, COMBAT_GENERATION, COMBAT_LIFECYCLE)
                                   if key in COMBAT_ACTIONS else arguments)
                  for key, _, _, arguments in DECLARATIONS),
    services=tuple(ServiceDefinition("global." + key + "_service", handler, policy=policy,
                                     prepare=prepare_observation if key == "look_target" else None)
                   for key, handler, policy, _ in DECLARATIONS),
    bindings=tuple(ActionBinding("global." + key + "_binding", "", "global." + key,
                                 "global." + key + "_service", source=GlobalSource(ScopeRoot.CALLER))
                   for key, _, _, _ in DECLARATIONS),
)


def invoke(caller, session, name, **arguments):
    from .manifest import get_index

    invocation = ActionInvocation("global." + name, "adapter", (), tuple(arguments.items()), "text")
    result = execute(caller, session, invocation, get_index())
    emit(caller, session, invocation, result)
    if name == "status" and result.status == ResultStatus.SUCCESS:
        after_change(caller.push_state)
    return result
