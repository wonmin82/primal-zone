"""Phase 3 확장성 전용 콘텐츠. 운영 manifest에는 등록하지 않는다."""

from typeclasses.interactables import ActionObject
from world.actions.gateway import ActionResult, ResultStatus
from world.actions.schema import (
    ActionBinding,
    ActionDefinition,
    ArgumentDefinition,
    ContentPackage,
    ReferenceKind,
    RoleDefinition,
    ServiceDefinition,
    SyntaxVariant,
    VerbDefinition,
)
from world.rules import RuleError

PROVIDER = RoleDefinition("provider", (ReferenceKind.OBJECT,))


class ExtensionBroker(ActionObject):
    """실제 방에 배치하는 테스트 전용 NPC. 운영 서비스·경제와 분리한다."""

    semantic_role = "npc"
    detectability = "conspicuous"
    presence = "격리 검증용 예치 원장을 관리하고 있다."


def deposit(context):
    """지갑에서 NPC의 사용자별 예치 원장으로 실제 저장 금액을 이동한다."""
    npc = context.roles["provider"][0]
    if npc.db.phase3_client_id != context.caller.pk:
        raise RuleError("이 중개인의 의뢰인이 아닙니다.")
    profile = context.caller.profile_snapshot()
    amount = context.arguments["quantity"]
    if profile["credits"] < amount:
        raise RuleError("예치할 보급칩이 부족합니다.")
    profile["credits"] -= amount
    context.caller.save_profile(profile)
    npc.db.phase3_escrow = int(npc.db.phase3_escrow or 0) + amount
    npc.db.phase3_receipt = {"owner": context.caller.pk, "amount": amount}
    if npc.db.phase3_fail:
        raise ValueError("격리 확장성 fixture의 저장 후 실패")
    return ActionResult(messages=("보급칩을 예치했다.",), changed=True)


def withdraw(context):
    """반환은 확인 뒤 원장을 소진하고 지갑을 복구하는 별도 Service다."""
    npc = context.roles["provider"][0]
    if npc.db.phase3_client_id != context.caller.pk:
        raise RuleError("이 중개인의 의뢰인이 아닙니다.")
    amount = int(npc.db.phase3_escrow or 0)
    if amount <= 0:
        raise RuleError("반환할 예치금이 없습니다.")
    if context.invocation.variant_id == "normal":
        return ActionResult(ResultStatus.CONFIRMATION, ("예치금을 반환할까요?",),
                            confirm_variant="confirmed")
    profile = context.caller.profile_snapshot()
    profile["credits"] += amount
    context.caller.save_profile(profile)
    npc.db.phase3_escrow = 0
    npc.db.phase3_receipt = None
    return ActionResult(messages=("예치금을 반환했다.",), changed=True)


PACKAGE = ContentPackage(
    "phase3.extension",
    verbs=(VerbDefinition("phase3.mediate", "조율", ("중개",),
                          "격리 중개인의 예치와 반환", category="시설",
                          usage="<중개인> 예치 <금액> 조율 / <중개인> 반환 조율"),),
    actions=(
        ActionDefinition("phase3.deposit", "phase3.mediate", (PROVIDER,),
                         (SyntaxVariant("normal", r"(?P<provider>.*?) 예치 (?P<quantity>\d+)"),),
                         arguments=(ArgumentDefinition("quantity", int, minimum=1),),
                         help="의뢰인의 보급칩을 중개인의 원장으로 예치한다.",
                         examples=("중개인 예치 7 조율",)),
        ActionDefinition("phase3.withdraw", "phase3.mediate", (PROVIDER,),
                         (SyntaxVariant("normal", r"(?P<provider>.*?) 반환"),
                          SyntaxVariant("confirmed", r"(?P<provider>.*?) 반환", "확정", True)),
                         help="현재 중개인의 예치금을 확인 후 반환한다.",
                         examples=("중개인 반환 조율", "중개인 반환 조율 확정")),
    ),
    services=(ServiceDefinition("phase3.deposit_service", deposit, (PROVIDER,)),
              ServiceDefinition("phase3.withdraw_service", withdraw, (PROVIDER,))),
    bindings=tuple(ActionBinding(f"phase3.{name}_{provider}", f"phase3.{provider}",
                                 f"phase3.{name}", f"phase3.{name}_service")
                   for provider in ("broker", "second_broker")
                   for name in ("deposit", "withdraw")),
)
