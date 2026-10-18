"""직접 소지·장착 Root ItemEntity의 소비·장비 선언."""

from world import equipment
from world.actions import item_equipment_services as service
from world.actions.item_equipment_help import SPECS, sections
from world.actions.item_equipment_presentation import render
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

verbs = tuple(VerbDefinition("game." + identity, key, aliases, summary, usage, "아이템·보급", sections(key, usage))
              for identity, key, aliases, usage, summary in SPECS)
actions, bindings = [], []
services = (ServiceDefinition("item_equipment.execute", service.execute,
                              config_schema=(ArgumentDefinition("operation"),), presenter=render),)


def item_pattern(identities):
    names = tuple(dict.fromkeys(name for identity in identities
                                for name in (identity, ITEMS[identity]["name"], *ITEMS[identity].get("aliases", ()))))
    return "(?:" + "|".join(literal(name) for name in names) + r")(?:[0-9]+)?"

for identity, data in ITEMS.items():
    operations = ["information"]
    if identity == "bandage":
        operations.append("use")
    if data.get("consume_action"):
        operations.append({"먹어": "eat", "마셔": "drink"}[data["consume_action"]])
    properties, _modifiers = equipment.definition_parts(identity, data)
    if properties:
        operations.extend(("wield", "unwield", "active_weapon") if properties.get("role") == "weapon" else ("equip", "remove"))
        operations.extend(("advise_equip", "advise_remove") if properties.get("role") == "weapon"
                          else ("advise_wield", "advise_unwield"))
    for operation in operations:
        action_id = "item." + identity + "." + operation
        subject = RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER,
                                 definition_ids=(identity,))
        pattern = (r"(?P<subject>" + item_pattern((identity,)) + r")(?: (?P<count>[0-9]+개|모두))?"
                   if operation == "information" or operation.startswith("advise_")
                   else r"(?P<subject>.+?)(?: (?P<count>[0-9]+개|모두))?")
        actions.append(ActionDefinition(action_id, "game." + operation.removeprefix("advise_"),
            (RoleDefinition("provider", (ReferenceKind.ITEM,)), subject),
            (SyntaxVariant("normal", pattern, show_control=not operation.startswith("advise_")),),
            (ArgumentDefinition("count", default="1"),), provider_from="subject",
            help="잘못된 장비 동사를 효과 없이 거절하고 올바른 동사를 안내합니다." if operation.startswith("advise_") else ""))
        bindings.append(ActionBinding(action_id + ".binding", "item." + identity, action_id,
                                      "item_equipment.execute", (("operation", operation),)))

for magazine, data in ITEMS.items():
    if not data.get("magazine"):
        continue
    family = data["magazine"]["family"]
    identity = "item.inside_information." + magazine
    actions.append(ActionDefinition(identity, "game.information",
        (RoleDefinition("provider", (ReferenceKind.ITEM,)),
         RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER,
                        scope=TargetScope.INSIDE, definition_ids=(magazine,))),
        (SyntaxVariant("normal", r"(?:(?P<provider>.+)의 )?(?P<subject>" + item_pattern((magazine,)) +
                       r")(?: (?P<count>[0-9]+개|모두))?"),), (ArgumentDefinition("count", default="1"),)))
    bindings.extend(ActionBinding(identity + "." + definition, "item." + definition, identity,
                                  "item_equipment.execute", (("operation", "inside_information"),))
                    for definition, data in ITEMS.items() if data.get("firearm_family") == family)

PACKAGE = ContentPackage("game.item_equipment", verbs=verbs, actions=tuple(actions),
                         services=services, bindings=tuple(bindings))
