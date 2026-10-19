"""M05: 시체·바닥 출처와 안정 Loot Entry를 결합하는 운영 Action."""

from commands.help_contracts import command_sections
from world.actions.loot_presentation import render
from world.actions.loot_resolution import resolve
from world.actions.loot_services import lock, prepare, take
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

SOURCE = RoleDefinition("source", (ReferenceKind.CORPSE, ReferenceKind.OBJECT),
                        DefaultTargetPolicy.FIRST_LEGACY_ORDER, allow_all=True)
PROVIDER = RoleDefinition("provider", SOURCE.kinds, allow_all=True)
SUBJECT = RoleDefinition("subject", (ReferenceKind.LOOT, ReferenceKind.CURRENCY),
                         allow_all=True, scope=TargetScope.SOURCE, scope_from="source")
PACKAGE = ContentPackage(
    "game.loot",
    verbs=(VerbDefinition("game.take", "가져", ("집",), "권한에 따라 배정된 전리품을 분배합니다.",
                          "시체에서 모두 가져 · 시체 2에서 모두 가져 · 모든 시체에서 회수부품 모두 가져 · 회수부품 2 가져 · 회수부품 모두 가져 · 시체에서 20칩 가져 · 칩 2 가져 · 칩 모두 가져 · 모두 가져",
                          "아이템·보급", command_sections("가져")),),
    actions=(ActionDefinition("loot.take", "game.take", (PROVIDER, SOURCE, SUBJECT),
                              (SyntaxVariant("take", r".*", show_control=False),),
                              (ArgumentDefinition("quantity", int, default=0, minimum=0),
                               ArgumentDefinition("snapshot")), provider_from="source",
                              help="고정 번호로 전리품의 출처와 항목을 지정합니다. 집 별칭과 시 단축어를 사용할 수 있습니다.",
                              examples=("시체에서 모두 가져", "시체 2에서 모두 가져", "칩 모두 가져"),
                              text_resolver=resolve, max_references=4096, max_payload_bytes=262144),),
    services=(ServiceDefinition("loot.pickup", take, presenter=render, locker=lock, prepare=prepare),),
    bindings=tuple(ActionBinding("loot.take." + kind, "loot." + kind, "loot.take", "loot.pickup")
                   for kind in ("corpse", "ground")),
)
