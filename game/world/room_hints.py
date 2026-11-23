"""방 안내의 stable 대상 참조를 현재 관찰 범위 안에서 렌더링한다."""

from world.content import ROOMS

LIMITED_GUIDANCE = "작은 흔적을 식별하기 어렵다. 광원을 사용해 주변을 살펴보자."


def render(context, *, objects=None, snapshot=None, action_rows=None):
    from world.selection_display import provider_command, room_snapshot
    from world.targets import room_objects

    room = context.room
    hints = ROOMS.get(room.db.zone_id if room else None, {}).get("hints", [])
    rendered = []
    clear = context.snapshot.effective_visibility == "clear"
    if not hints:
        return "" if clear else LIMITED_GUIDANCE
    objects = room_objects(context.viewer, room, context.observed_at) if objects is None else objects
    snapshot = room_snapshot(context.viewer, context.observed_at, objects=objects) if snapshot is None else snapshot
    for hint in hints:
        if "text" in hint:
            if clear:
                rendered.append(hint["text"])
            continue
        identity = hint["target"]
        if "intent" in hint:
            from world.dialogue_intents import intents_for
            from world.npc_dialogue import dialogue_target_text, supports, type_name

            dialogue_pool = [obj for obj in objects if supports(obj)]
            for obj in dialogue_pool:
                if not (
                    obj.tags.has(identity, category="primal_actor_spawn")
                    or obj.tags.has(identity, category="primal_interactable")
                ):
                    continue
                intent = next((item for item in intents_for(type_name(obj))
                               if item.intent_id == hint["intent"]), None)
                if intent and (target := dialogue_target_text(context.viewer, obj, pool=dialogue_pool,
                                                             records=snapshot.records)):
                    rendered.append(f"'{target}에게 {intent.keyword}")
            continue
        action = hint["action"]
        from world.actions.presentation import provider_verbs

        for obj in objects:
            if (obj.tags.has(identity, category="primal_interactable")
                    or obj.tags.has(identity, category="primal_actor_spawn")) and action in provider_verbs(
                        context.viewer, obj, context.observed_at, verb_key=action, rows=action_rows):
                record = snapshot.records.get(snapshot.references.get(obj.pk))
                if command := provider_command(context.viewer, record, action, lambda target: target):
                    rendered.append(command)
    if rendered:
        return " · ".join(rendered)
    if not clear:
        return LIMITED_GUIDANCE
    return ""
