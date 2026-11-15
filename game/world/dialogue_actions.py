"""공개 발화와 NPC 대화 효과를 같은 Action Gateway에서 실행한다."""

from world import npc_dialogue as dialogue
from world.rules import RuleError

from .actions.gateway import ActionResult, ResultStatus
from .actions.schema import (
    ActionBinding,
    ActionDefinition,
    ArgumentDefinition,
    ContentPackage,
    EffectDefinition,
    ExecutionPolicy,
    GlobalSource,
    ScopeRoot,
    ServiceDefinition,
    SyntaxVariant,
    VerbDefinition,
)


def speech(context):
    request = {}
    caller = context.caller

    def publish(effect):
        if not caller.location:
            raise RuleError("현재 방에서만 말할 수 있습니다.")
        token = effect.arguments.get("token")
        if token is not None and "message" in effect.arguments:
            raise RuleError("대화 입력은 하나만 지정하세요.")
        if token is not None:
            npc, intent = dialogue.resolve_keyword(caller, token, effect.session)
            request.update(npc=npc, intent=intent, selection=token if intent.mutates_state else None)
            original = f"{npc.key}에게 {intent.keyword}"
        else:
            original = dialogue.validate_message(effect.arguments.get("message"))
            explicit, body = dialogue.explicit_target(caller, original)
            request.update(explicit=explicit, body=body)
        dialogue.public_speech(caller, original)
        return ActionResult()

    published = context.effect("speech", publish)
    if published.status != ResultStatus.SUCCESS:
        return ActionResult(published.status, published.messages)

    def read_dialogue(effect):
        def select(caller, npc, intent, **options):
            request.update(npc=npc, intent=intent, options=options)
            if not intent.mutates_state:
                dialogue.execute(caller, npc, intent, **options)

        if "body" in request:
            dialogue.react(caller, request["body"], request["explicit"], invoke=select)
        elif not request["intent"].mutates_state:
            dialogue.execute(caller, request["npc"], request["intent"])
        return ActionResult()

    read = context.effect("read_dialogue", read_dialogue)
    if read.status != ResultStatus.SUCCESS:
        return ActionResult(read.status, read.messages)

    if request.get("intent") and request["intent"].mutates_state:
        def mutate(effect):
            from evennia.objects.models import ObjectDB

            npc_id = request["npc"].pk
            if npc_id is None or not ObjectDB.objects.select_for_update().filter(pk=npc_id).exists():
                raise RuleError("원래 NPC 또는 해당 키워드를 지금 사용할 수 없습니다.")
            if request.get("selection"):
                npc, intent = dialogue.resolve_keyword(caller, request["selection"], effect.session)
                if npc != request["npc"] or intent != request["intent"]:
                    raise RuleError("원래 NPC 또는 해당 키워드를 지금 사용할 수 없습니다.")
            dialogue.execute(caller, request["npc"], request["intent"], selection=request.get("selection"))
            return ActionResult(changed=True)

        changed = context.effect("quest", mutate)
        return ActionResult(changed.status, changed.messages)
    return ActionResult()


PACKAGE = ContentPackage(
    "dialogue.package",
    verbs=(VerbDefinition("dialogue.speech_verb", "공개발화", adapter_only=True),),
    actions=(ActionDefinition(
        "dialogue.speech", "dialogue.speech_verb", (), (SyntaxVariant("speech", "", show_control=False),),
        arguments=(ArgumentDefinition("message", required=False), ArgumentDefinition("token", required=False)),
    ),),
    services=(ServiceDefinition("dialogue.speech_service", speech, effects=(
        EffectDefinition("speech", ExecutionPolicy.READ_ONLY),
        EffectDefinition("read_dialogue", ExecutionPolicy.READ_ONLY),
        EffectDefinition("quest", ExecutionPolicy.STATE_CHANGE),
    )),),
    bindings=(ActionBinding("dialogue.speech_binding", "", "dialogue.speech", "dialogue.speech_service",
                            source=GlobalSource(ScopeRoot.CURRENT_ROOM)),),
)


def invoke(caller, session, *, message=None, token=None):
    from world.actions.gateway import execute
    from world.actions.manifest import get_index
    from world.actions.resolver import ActionInvocation

    arguments = (("token", token),) if token is not None else (("message", message),)
    invocation = ActionInvocation("dialogue.speech", "speech", (), arguments,
                                  origin="web" if token is not None else "text")
    result = execute(caller, session, invocation, get_index())
    if result.status != ResultStatus.SUCCESS:
        raise RuleError(result.messages[-1] if result.messages else "대화를 완료하지 못했습니다.")
    return result
