"""방 안내의 stable 대상 참조를 현재 관찰 범위 안에서 렌더링한다."""

from world.content import ROOMS
from world.observation import can_perceive
from world.targets import ordered

LIMITED_GUIDANCE = "작은 흔적을 식별하기 어렵다. 광원을 사용해 주변을 살펴보자."


def render(context):
    from typeclasses.interactables import INTERACTABLES

    room = context.room
    hints = ROOMS.get(room.db.zone_id if room else None, {}).get("hints", [])
    rendered = []
    clear = context.snapshot.effective_visibility == "clear"
    objects = ordered(room.contents) if room else []
    for hint in hints:
        if "text" in hint:
            if clear:
                rendered.append(hint["text"])
            continue
        identity = hint["target"]
        if "intent" in hint:
            from world.dialogue_intents import intents_for
            from world.npc_dialogue import supports
            from world.targets import labels

            dialogue_labels = labels([obj for obj in objects if supports(obj)
                                      and obj.access(context.viewer, "view") and can_perceive(obj, context)])
            for obj in objects:
                if not obj.tags.has(identity, category="primal_interactable") or not can_perceive(obj, context):
                    continue
                intent = next((item for item in intents_for(INTERACTABLES[identity]["typeclass"])
                               if item.intent_id == hint["intent"]), None)
                if intent and obj.id in dialogue_labels:
                    rendered.append(f"'{dialogue_labels[obj.id]}에게 {intent.keyword}")
            continue
        action = hint["action"]
        if any(obj.tags.has(identity, category="primal_interactable")
               and can_perceive(obj, context) and obj.supports_action(action)
               and (action not in ("회복", "휴식", "환율", "목록") or obj.available(context.viewer, observed_at=context.observed_at))
               for obj in objects):
            rendered.append(f"{INTERACTABLES[identity]['name']} {action}")
    if rendered:
        return " · ".join(rendered)
    if not clear:
        return LIMITED_GUIDANCE
    return ""
