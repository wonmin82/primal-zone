"""M04 운영 총기·탄창·광원 선언. 내부 부품은 Root Provider의 대상이다."""

from world.actions.firearm_lighting_help import HELP, sections
from world.actions.firearm_lighting_presentation import render
from world.actions.firearm_lighting_services import execute
from world.actions.room_npc_content import literal
from world.actions.schema import (
    ActionBinding,
    ActionDefinition,
    ArgumentDefinition,
    ContentPackage,
    DefaultTargetPolicy,
    ReferenceKind,
    RoleDefinition,
    ServiceDefinition,
    SyntaxVariant,
    TargetScope,
    VerbDefinition,
)
from world.content import ITEMS

verbs = tuple(VerbDefinition("game." + key, name, summary=summary, usage=usage,
                             category="이동·탐사" if key.startswith("light_") else "아이템·보급",
                             help_sections=sections(usage))
              for key, (name, usage, summary) in HELP.items())
actions, bindings = [], []
PROVIDER = RoleDefinition("provider", (ReferenceKind.ITEM,))


def role(name, definitions, *, inside=False, required=True):
    return RoleDefinition(name, (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER,
                          required=required, scope=TargetScope.INSIDE if inside else TargetScope.CURRENT,
                          definition_ids=tuple(definitions))


def declare(identity, verb, definitions, pattern, operation, roles=(), arguments=()):
    identity = "item_ops." + identity
    actions.append(ActionDefinition(identity, "game." + verb, (PROVIDER, *roles),
                                    (SyntaxVariant("normal", pattern),), arguments,
                                    help="실제 소지 UUID와 현재 접근 가능한 내부 부품을 검증하여 조작합니다."))
    bindings.extend(ActionBinding(identity + "." + definition, "item." + definition,
                                  identity, "item_ops.execute", (("operation", operation),))
                    for definition in definitions)


guns = tuple(key for key, data in ITEMS.items() if data.get("firearm_family"))
magazines = tuple(key for key, data in ITEMS.items() if data.get("magazine"))
ammo = tuple(key for key, data in ITEMS.items() if data.get("ammo_type"))
lights = tuple(key for key, data in ITEMS.items() if data.get("light_source"))
power = tuple(key for key, data in ITEMS.items() if data.get("power_source"))
AMMO_INVENTORY = RoleDefinition("source", (ReferenceKind.INVENTORY,), required=False, definition_ids=ammo)
AMMO_SNAPSHOT = (ArgumentDefinition("snapshot", default=""),)

declare("reload", "reload", guns, r"(?P<provider>.+)", "reload")
declare("load", "load", guns, r"(?P<provider>.+)에 (?P<source>.+)", "load",
        (RoleDefinition("source", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER,
                        scope=TargetScope.CARRIED_AND_INSIDE, definition_ids=magazines),))
declare("fill", "fill", magazines, r"(?P<provider>.+)", "fill", (AMMO_INVENTORY,), AMMO_SNAPSHOT)
declare("inside_fill", "fill", guns, r"(?:(?P<provider>.+)의 )?(?P<subject>.+)", "fill",
        (role("subject", magazines, inside=True), AMMO_INVENTORY), AMMO_SNAPSHOT)
declare("ammo_insert", "store", magazines, r"(?P<provider>.+)에 (?P<source>.+)", "ammo_insert", (role("source", ammo),))
declare("inside_ammo_insert", "store", guns, r"(?:(?P<provider>.+)의 )?(?P<subject>.+)에 (?P<source>.+)", "ammo_insert",
        (role("subject", magazines, inside=True), role("source", ammo)))
declare("magazine_remove", "retrieve", guns, r"(?P<provider>.+)에서 탄창", "magazine_remove",
        (role("subject", magazines, inside=True, required=False),))
for definition in ammo:
    data = ITEMS[definition]
    names = (definition, data["name"], *data.get("aliases", ()))
    pattern = "(?:" + "|".join(literal(name) for name in names) + ")"
    arguments = (ArgumentDefinition("ammo", default=definition, choices=(definition,)),)
    declare("ammo_remove." + definition, "retrieve", magazines,
            r"(?P<provider>.+)에서 " + pattern, "ammo_remove", arguments=arguments)
    declare("inside_ammo_remove." + definition, "retrieve", guns,
            r"(?:(?P<provider>.+)의 )?(?P<subject>.+)에서 " + pattern, "ammo_remove",
            (role("subject", magazines, inside=True),), arguments)
for operation in ("light_on", "light_off", "light_status"):
    declare(operation, operation, lights, r"(?P<provider>.+)", operation)
declare("power_insert", "store", lights, r"(?P<provider>.+)에 (?P<source>.+)", "power_insert",
        (role("source", power),))

PACKAGE = ContentPackage("game.firearm_lighting", verbs, tuple(actions),
                         (ServiceDefinition("item_ops.execute", execute,
                                            config_schema=(ArgumentDefinition("operation"),), presenter=render),),
                         tuple(bindings), dependencies=("game.item_verbs",))
