"""Architecture Gate 전용 선언. ACTION_CONTENT_PACKAGES override로만 활성화한다."""

from world.actions.gateway import ActionResult, ResultStatus
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
    VerbDefinition,
)


def record(context, service, quantity=1):
    """격리 fixture의 실제 Attribute 변경으로 완료·중복·rollback을 검증한다."""
    events = list(context.caller.db.action_validation_events or [])
    events.append({"service": service, "variant": context.invocation.variant_id,
                   "roles": {name: [str(entity.pk) for entity in entities]
                             for name, entities in context.roles.items()}, "quantity": quantity})
    context.caller.db.action_validation_events = events
    provider = context.roles["provider"][0]
    if hasattr(provider, "db") and provider.db.validation_refuse:
        return ActionResult(ResultStatus.REFUSED, ("검증 서비스가 요청을 거절했다.",))
    if hasattr(provider, "db") and provider.db.validation_error:
        raise ValueError("통제된 fixture 예외")
    return ActionResult(messages=("검증 행동을 완료했다.",), changed=True)


def inspect_object(context):
    if context.invocation.variant_id == "normal":
        return ActionResult(ResultStatus.CONFIRMATION, ("확정 구문으로 검측하세요.",),
                            confirm_variant="confirmed")
    return record(context, "object")


def inspect_quantity(context):
    return record(context, "quantity", context.arguments["quantity"])


def inspect_item(context):
    return record(context, "item", context.arguments.get("quantity", 1))


def inspect_sources(context):
    return record(context, "sources", len(context.roles["source"]))


OBJECT_PROVIDER = RoleDefinition("provider", (ReferenceKind.OBJECT,))
ITEM_PROVIDER = RoleDefinition("provider", (ReferenceKind.ITEM,))
ITEM_SUBJECT = RoleDefinition("subject", (ReferenceKind.ITEM,),
                              DefaultTargetPolicy.FIRST_LEGACY_ORDER)
SOURCE = RoleDefinition("source", (ReferenceKind.CORPSE,),
                        DefaultTargetPolicy.FIRST_LEGACY_ORDER, allow_all=True)
CORPSE_PROVIDER = RoleDefinition("provider", (ReferenceKind.CORPSE,), allow_all=True)
LOOT_PROVIDER = RoleDefinition("provider", (ReferenceKind.LOOT,))
LOOT_SUBJECT = RoleDefinition("subject", (ReferenceKind.LOOT,), DefaultTargetPolicy.FIRST_LEGACY_ORDER)

PACKAGE = ContentPackage(
    "validation.architecture",
    verbs=(VerbDefinition("validation.measure", "검측", ("계측",), "격리 검증용 측정"),
           VerbDefinition("validation.sources", "채록", summary="격리 검증용 출처 기록"),
           VerbDefinition("validation.loot_measure", "전리검측", summary="격리 전리품 권리 검증")),
    actions=(
        ActionDefinition("validation.loot", "validation.loot_measure", (LOOT_PROVIDER, LOOT_SUBJECT),
                         (SyntaxVariant("normal", r"(?P<subject>.+)"),), provider_from="subject",
                         help="실물 전리품의 권리를 재검증하여 안정 ID를 기록한다."),
        ActionDefinition("validation.object", "validation.measure", (OBJECT_PROVIDER,),
                         (SyntaxVariant("normal", r"(?P<provider>.*)"),
                          SyntaxVariant("confirmed", r"(?P<provider>.*)", "확정", True)),
                         help="검증기와 확정 구문을 지정하여 측정한다.",
                         examples=("검증기 검측", "검증기 검측 확정")),
        ActionDefinition("validation.quantity", "validation.measure", (OBJECT_PROVIDER,),
                         (SyntaxVariant("normal", r"(?P<provider>.+) (?P<quantity>\d+)"),),
                         arguments=(ArgumentDefinition("quantity", int, minimum=1, maximum=5),),
                         help="검증기의 측정 횟수를 지정한다.", examples=("검증기 2 검측",)),
        ActionDefinition("validation.item", "validation.measure", (ITEM_PROVIDER, ITEM_SUBJECT),
                         (SyntaxVariant("normal", r"(?P<subject>.+?)(?: (?P<quantity>\d+)개)?"),),
                         arguments=(ArgumentDefinition("quantity", int, default=1, minimum=1),), provider_from="subject",
                         help="소지한 붕대의 안정 ID를 측정한다.", examples=("붕대 검측",)),
        ActionDefinition("validation.external_sources", "validation.sources", (OBJECT_PROVIDER, SOURCE),
                         (SyntaxVariant("normal", r"(?P<source>.+)에서 (?P<provider>.+)"),
                          SyntaxVariant("all", r"모든 (?P<source>.+)에서 (?P<provider>.+)", all_roles=("source",))),
                         help="검증기에서 출처를 기록한다.", examples=("시체에서 검증기 채록",)),
        ActionDefinition("validation.self_sources", "validation.sources", (CORPSE_PROVIDER, SOURCE),
                         (SyntaxVariant("normal", r"(?P<source>.+)에서"),
                          SyntaxVariant("all", r"모든 (?P<source>.+)에서", all_roles=("source",))), provider_from="source",
                         help="시체 자체의 Service로 출처를 기록한다.",
                         examples=("시체에서 채록", "모든 시체에서 채록")),
    ),
    services=(
        ServiceDefinition("validation.loot_service", inspect_item, (LOOT_PROVIDER, LOOT_SUBJECT)),
        ServiceDefinition("validation.object_service", inspect_object, (OBJECT_PROVIDER,)),
        ServiceDefinition("validation.quantity_service", inspect_quantity, (OBJECT_PROVIDER,)),
        ServiceDefinition("validation.item_service", inspect_item, (ITEM_PROVIDER, ITEM_SUBJECT)),
        ServiceDefinition("validation.external_source_service", inspect_sources, (OBJECT_PROVIDER, SOURCE)),
        ServiceDefinition("validation.self_source_service", inspect_sources, (CORPSE_PROVIDER, SOURCE)),
    ),
    bindings=(
        ActionBinding("validation.loot_binding", "item.bandage", "validation.loot", "validation.loot_service"),
        ActionBinding("validation.object_binding", "validation.instrument", "validation.object", "validation.object_service"),
        ActionBinding("validation.quantity_binding", "validation.instrument", "validation.quantity", "validation.quantity_service"),
        ActionBinding("validation.item_binding", "item.bandage", "validation.item", "validation.item_service"),
        ActionBinding("validation.external_source_binding", "validation.instrument", "validation.external_sources", "validation.external_source_service"),
        ActionBinding("validation.self_source_binding", "validation.corpse", "validation.self_sources", "validation.self_source_service"),
    ),
)
