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


def look(context):
    from commands.character import time

    caller = context.caller
    messages = []
    from typeclasses.exits import Exit
    from typeclasses.loot import Corpse
    from world.content import ITEMS
    from world.lifecycle import reconcile_room
    from world.target_presentation import corpse_overview
    from world.targets import Mode, item_selector, names, parse_selector, resolve, room_objects

    name = context.arguments.get("query", "").strip()
    observed_at = time()
    from world.content.economy import CURRENCY
    from world.currency import is_currency

    if is_currency(name):
        messages.append(ft.compact(CURRENCY["name"], CURRENCY["description"]))
        return ActionResult(messages=messages)
    if name and caller.location:
        from world.doors import look_door
        try:
            door_output = look_door(caller, name, observed_at)
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
        objects = room_objects(caller, observed_at=observed_at)
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
                        [caller.at_look(obj, observed_at=observed_at) for obj in selected],
                        "\n\n",
                    )
                messages.append(output)
            else:
                from world.equipment_service import (
                    entity_runtime,
                    resolve_item,
                    selector_label,
                    state_summary,
                )

                if entity_runtime(caller):
                    from world.lighting_service import status as light_status

                    item = resolve_item(caller, name, "봐")
                    identity = item.definition_id
                    detail = light_status(caller, item, observed_at) if ITEMS[identity].get("light_source") else state_summary(item)
                    messages.append(ft.compact(ft.token("item", selector_label(caller, item)),
                                               ITEMS[identity].get("description", "탐사 중 사용하는 물품이다."),
                                               detail, ITEMS[identity].get("firearm_family", "")))
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
    if not any([command.access(caller, "cmd") for command in selected.create_exit_cmdset(selected) if command.is_exit]):
        raise rules.RuleError("출구를 이용할 수 없습니다.")
    if not selected.access(caller, "traverse"):
        if selected.db.err_traverse:
            return ActionResult(messages=(selected.db.err_traverse,))
        after_change(lambda: selected.at_failed_traverse(caller))
        return ActionResult()
    origin = caller.location
    selected.at_traverse(caller, selected.destination)
    from evennia.server.signals import SIGNAL_EXIT_TRAVERSED

    after_change(lambda: SIGNAL_EXIT_TRAVERSED.send(sender=selected, traverser=caller))
    return ActionResult(changed=caller.location != origin)


def web_combat_target(context):
    refs = context.roles.get("subject", ())
    if context.invocation.origin != "web":
        return None
    if len(refs) != 1 or context.arguments.get("query"):
        raise rules.RuleError("원래 전투 대상을 지정하세요.")
    enemy = refs[0]
    if (not enemy.shared_combat_active
            or context.arguments.get("generation") != (enemy.db.combat_generation or 0)):
        raise rules.RuleError("원래 전투 대상의 상태가 바뀌었습니다.")
    return enemy


def attack(context):
    from typeclasses.actors import Actor

    caller = context.caller
    query = context.arguments["query"]
    from world.lifecycle import reconcile_room
    from world.targets import names, parse_selector, resolve, room_objects

    name = query.strip()
    current = caller.combat_target()
    reconcile_room(caller.location)
    enemy = web_combat_target(context)
    if enemy:
        caller.start_combat(enemy)
        return ActionResult(changed=True)
    objects = room_objects(caller)
    enemy = (
        resolve(
            objects,
            parse_selector(name, [n for obj in objects for n in names(obj)]),
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
        selector = parse_selector(query, [name for obj in pool for name in names(obj)])
        # 일행공격의 무번호 복수 후보 거절은 일반 공격의 기본 첫 대상과 다르다.
        if selector.mode == Mode.DEFAULT:
            matches = matching(pool, selector)
            exact = [obj for obj in matches if normalized(obj.key) == normalized(selector.name)]
            strict_single(exact or matches, selector, "일행공격")
        target = resolve_target(pool, selector, caller, "일행공격")[0]
    party.attack(caller, target)
    return ActionResult(changed=True)



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
COMBAT_ACTIONS = {"attack", "party_attack"}
DECLARATIONS = (
    ("look", look, ExecutionPolicy.STATE_CHANGE, (QUERY,)),
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
                                   (COMBAT_TARGET,) if key in COMBAT_ACTIONS else (),
                                   (SyntaxVariant("adapter", "", show_control=False),),
                                   arguments=(*arguments, COMBAT_GENERATION) if key in COMBAT_ACTIONS else arguments)
                  for key, _, _, arguments in DECLARATIONS),
    services=tuple(ServiceDefinition("global." + key + "_service", handler, policy=policy)
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
