"""개인·공용 보관함의 안정 UUID 기반 보관·회수 선언."""

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
)
from world.actions.storage_presentation import render
from world.actions.storage_services import transfer

PROVIDER = RoleDefinition("provider", (ReferenceKind.OBJECT,))
COUNT = ArgumentDefinition("count", default="1")
actions, bindings = [], []
for operation, particle, scope in (("store", "에", TargetScope.CURRENT), ("retrieve", "에서", TargetScope.STORAGE)):
    identity = "storage." + operation
    subject = RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER,
                             allow_all=True, scope=scope,
                             location_kinds=("inventory",) if operation == "store" else ())
    actions.append(ActionDefinition(
        identity, "game." + operation, (PROVIDER, subject),
        (SyntaxVariant("normal", rf"(?P<provider>.+?){particle} (?P<subject>.+?)(?: (?P<count>[0-9]+개|모두))?",
                       all_when=(("subject", "count", "모두"),)),), (COUNT,),
        help="현재 접근할 수 있는 보관함과 물건의 고정 번호·수량을 지정합니다.",
        examples=(f"개인 보관함{particle} 붕대 2 3개 " + ("넣어" if operation == "store" else "꺼내"),)))
    for provider in ("world.container", "world.personal_locker"):
        bindings.append(ActionBinding(identity + "." + provider, provider, identity, "storage.transfer",
                                      (("withdraw", operation == "retrieve"),)))

PACKAGE = ContentPackage("game.storage", actions=tuple(actions), bindings=tuple(bindings),
                         services=(ServiceDefinition("storage.transfer", transfer,
                                   config_schema=(ArgumentDefinition("withdraw", bool),), presenter=render),),
                         dependencies=("game.item_verbs",))
