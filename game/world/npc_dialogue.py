"""공개 NPC 대화. 조회/상태 변경·개인 결과·수신자별 선택 권한을 분리한다."""

import re
import secrets
import unicodedata
from time import time

from evennia.utils.ansi import strip_ansi

from world import rules
from world import text as ft
from world.dialogue_intents import GUIDE_REQUESTS, intents_for, recognize
from world.multiplayer import after_change, object_by_id, world_change
from world.targets import (
    TargetSelector,
    matching,
    names,
    parse_selector,
    room_objects,
    strict_single,
)

CONTEXT_TTL = 180
TOKEN_LIMIT = 256
GUIDE_LIMIT = 32
QUEST_NPCS = {
    "Commander": ("radio_tower", "outpost_supply_pass", rules.commander_talk),
    "Pathfinder": ("deep_jungle", "special_supply_pass", rules.jungle_talk),
}


def validate_message(value):
    if not isinstance(value, str) or any(unicodedata.category(c) in ("Cc", "Cf") for c in value):
        raise rules.RuleError("발화에 개행·제어문자를 사용할 수 없습니다.")
    body = strip_ansi(value.strip())
    if not body:
        raise rules.RuleError("내용을 입력하세요. 예: 안녕 말")
    if len(body) > 300:
        raise rules.RuleError("대화는 300자 이하로 입력하세요.")
    return body


def type_name(npc):
    return npc.typeclass_path.rsplit(".", 1)[-1]


def supports(npc):
    return bool(intents_for(type_name(npc)))


def nearby(caller):
    return [obj for obj in room_objects(caller) if supports(obj) and obj.access(caller, "view")]


def accessible(caller, npc):
    from world.observation import can_perceive, context_for

    return bool(caller.location and npc.location == caller.location and supports(npc)
                and npc.access(caller, "view") and can_perceive(npc, context_for(caller))
                and not caller.profile_snapshot().get("combat_target")
                and (not hasattr(npc, "available") or npc.available(caller)))


def available(caller, npc, intent):
    if not accessible(caller, npc):
        return False
    if intent.availability == "accessible":
        return True
    from world.credential_service import has_credential
    from world.quests import available as quest_available

    quest_id, credential_id, _ = QUEST_NPCS[type_name(npc)]
    profile = caller.profile_snapshot()
    state = profile["quests"][quest_id]
    if not quest_available(profile, quest_id):
        return False
    if intent.availability == "accept":
        return not state["started"] and not state["claimed"]
    if intent.availability == "report":
        return (state["started"] and state["boss_defeated"] and not state["claimed"]
                and (quest_id != "radio_tower" or state["generator_fixed"]))
    return state["claimed"] and not has_credential(caller, credential_id)


def available_intents(caller, npc):
    """실행·강조·개인 안내가 공유하는 SSOT 순서의 활성 Intent."""
    return tuple(item for item in intents_for(type_name(npc)) if available(caller, npc, item))


def available_dialogue_topics(caller, npc):
    return tuple(item for item in available_intents(caller, npc)
                 if not item.mutates_state and item.intent_id != "greeting")[:3]


def explicit_target(caller, original):
    """발화 앞부분의 조사 경계만 검사. 미발견이면 원문을 그대로 돌려준다."""
    pool = nearby(caller)
    known = [name for obj in pool for name in names(obj)]
    words = original.split()
    for position, word in enumerate(words):
        if not word.endswith("에게"):
            continue
        prefix = " ".join([*words[:position], word[:-2]]).strip()
        # 잘못된 0번도 인식된 이름에 한해서 selector의 정상 오류로 끝낸다.
        base = prefix.rsplit(None, 1)
        numbered = len(base) == 2 and (base[-1].lstrip("+-").isdecimal() or base[-1] == "모두")
        base_name = base[0] if numbered else prefix
        if not matching(pool, TargetSelector(base_name)):
            return None, original
        if numbered and base[-1].startswith(("-", "+")):
            raise rules.RuleError("대상 번호는 1 이상의 정수로 지정하세요.")
        selector = parse_selector(prefix, known)
        npc = strict_single(matching(pool, selector), selector, "말")
        body = " ".join(words[position + 1:])
        if not body:
            raise rules.RuleError("NPC에게 할 말을 입력하세요.")
        return npc, body
    return None, original


def clear_context(caller):
    caller.ndb.npc_dialogue_context = None


def current_context(caller, now=None):
    now = time() if now is None else now
    context = caller.ndb.npc_dialogue_context
    if not context:
        return None
    npc = object_by_id(context["npc_id"])
    if (not npc or context["location_id"] != getattr(caller.location, "id", None)
            or not 0 <= now - context["at"] < CONTEXT_TTL or not accessible(caller, npc)):
        guides = dict(caller.ndb.npc_dialogue_guides or {})
        guides.pop(context["npc_id"], None)
        caller.ndb.npc_dialogue_guides = guides
        clear_context(caller)
        return None
    return context


def remember(caller, npc, intent):
    caller.ndb.npc_dialogue_context = {
        "npc_id": npc.id, "intent_id": intent.intent_id,
        "active_keywords": tuple(item.keyword for item in available_intents(caller, npc)),
        "at": time(), "location_id": caller.location.id, "failures": 0,
    }


def choose(caller, body, explicit=None):
    pool = nearby(caller)
    if explicit:
        context = current_context(caller)
        if context and context["npc_id"] != explicit.id:
            clear_context(caller)
        return explicit, recognize(intents_for(type_name(explicit)), body)
    context = current_context(caller)
    if context:
        npc = object_by_id(context["npc_id"])
        intent = recognize(intents_for(type_name(npc)), body)
        if intent:
            return npc, intent
        if body in ("그다음은요", "다음", "그 다음은요"):
            # 후속 질문은 이전 Intent의 읽기 전용 화제만 연결한다.
            intents = {item.intent_id: item for item in intents_for(type_name(npc))}
            previous = intents[context["intent_id"]]
            followup = next((intents[key] for key in previous.next_topics
                            if not intents[key].mutates_state and available(caller, npc, intents[key])), None)
            return npc, followup or (previous if not previous.mutates_state else intents["greeting"])
    candidates = [(npc, recognize(intents_for(type_name(npc)), body)) for npc in pool]
    candidates = [(npc, intent) for npc, intent in candidates if intent]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        caller.msg("이 화제를 다루는 NPC가 여러 명입니다. 'NPC이름에게 " + body + "처럼 상대를 지정하세요.")
    elif context and contextual_question(body):
        return object_by_id(context["npc_id"]), None
    return None, None


def contextual_question(body):
    """지시어를 포함한 짧은 후속 질문만 문맥에 연결한다. 일반 채팅은 그대로 둔다."""
    return bool("에게" not in body
                and re.match(r"^(?:그건|그것|그거|그게|그러면|그럼|그래서|이건|이것|이거|무슨 뜻)", body)
                and re.search(r"(?:[?？]|(?:나요|까요|가요|인지요|는지요)[.!]?)$", body))


def token_store(caller):
    now = time()
    store = dict(caller.ndb.npc_dialogue_tokens or {})
    store = {key: value for key, value in store.items() if value["expires_at"] > now}
    caller.ndb.npc_dialogue_tokens = store
    return store


def issue_token(caller, npc, intent):
    store = token_store(caller)
    while len(store) >= TOKEN_LIMIT:
        del store[next(iter(store))]
    token = secrets.token_urlsafe(24)
    now = time()
    store[token] = {"character_id": caller.id, "npc_id": npc.id, "intent_id": intent.intent_id,
                    "keyword": intent.keyword, "issued_at": now, "expires_at": now + CONTEXT_TTL}
    caller.ndb.npc_dialogue_tokens = store
    return token


def response(caller, npc, intent):
    """원문을 한 번 확정한다. 수신자별 상태로 대사를 다시 생성하지 않는다."""
    kind = type_name(npc)
    if intent.handler == "greet":
        if kind == "Commander":
            return "잘 왔네. 통신탑을 되찾을 〈임무〉와 〈진행〉을 알려 주겠네."
        if kind == "Pathfinder":
            return "밀림의 탐사로를 살펴 주세요. 〈임무〉와 〈지역〉을 안내하겠습니다."
        topic = intents_for(kind)[1]
        return (npc.db.dialogue or npc.description) + f" 〈{topic.keyword}〉을 물어보세요."
    if kind in QUEST_NPCS:
        quest_id, credential_id, _ = QUEST_NPCS[kind]
        from world.content import ITEMS
        from world.quests import QUESTS, next_step

        if intent.intent_id == "mission":
            detail = ("정비기록을 확인하고 발전기를 복구한 뒤 능선 우두머리를 처치하게." if kind == "Commander"
                      else "관측소와 수몰 도로의 표식을 확인하고 신호 장치를 가동한 뒤 포식자를 처치해 주세요.")
            return detail + " 〈수락〉으로 시작하고 〈진행〉으로 목표를 확인하세요."
        if intent.intent_id == "progress":
            return QUESTS[quest_id]["hints"][next_step(caller.profile_snapshot(), quest_id)] + " 〈보고〉 조건을 확인하세요."
        if intent.intent_id == "region":
            return ("초지·수송차·관리동·발전실·능선이 첫 탐사로네." if kind == "Commander"
                    else "관측소와 수몰 도로에서 좌표를 맞춰 거목 군락을 지나 연구구역으로 가세요.") + " 〈임무〉를 물어보세요."
        if intent.intent_id == "credential":
            return f"최종 보고를 마치면 {ITEMS[credential_id]['name']}을 지급합니다. 분실·소각 후에는 무료 〈재발급〉이 가능합니다."
    if intent.handler == "training":
        offer, commands = npc.training_offer()
        return (npc.db.dialogue or npc.description) + " " + offer + " 서비스 명령: " + " · ".join(commands)
    if intent.handler == "supply":
        from world.content import ITEMS, SHOP_CATALOGS

        products = " · ".join(ITEMS[item]["name"] for item in SHOP_CATALOGS[npc.db.shop_id]["purchase_catalog"])
        return "필요한 물품과 구매 단위는 판매 목록을 살펴보세요. " + products + " / 목록 · 사 · 가치 · 팔아를 사용하세요."
    if intent.handler == "medical":
        return "의무실의 회복은 자신만 HP를 회복하며 보급칩을 받습니다. H=회복 HP, L=레벨, 비용=max(1, ceil((2*H+(L if L<100 else 2*L))/10))칩입니다. 20 회복처럼 요청하세요. 3층 회복실 침대 휴식은 무료로 HP·정신력을 모두 회복합니다."
    if intent.handler == "settlement":
        from world.content import SALVAGE_CREDIT_RATE

        return f"회수부품 1개는 {SALVAGE_CREDIT_RATE}칩입니다. 환율 · 회수부품 모두 교환 명령으로 정산하세요."
    raise rules.RuleError("지원하지 않는 대화 화제입니다.")


def keyword_guide(recipient, npc, active, *, force=False):
    from world.targets import labels

    now = time()
    present = {obj.id for obj in recipient.location.contents if supports(obj)} if recipient.location else set()
    store = {key: row for key, row in dict(recipient.ndb.npc_dialogue_guides or {}).items()
             if key in present and row["location_id"] == getattr(recipient.location, "id", None)
             and 0 <= now - row["at"] < CONTEXT_TTL}
    words = tuple(dict.fromkeys(item.keyword for item in active if item.intent_id != "greeting"))
    target = labels(nearby(recipient)).get(npc.id, npc.key)
    previous = store.get(npc.id)
    if force or not previous or previous["keywords"] != words or previous["target"] != target:
        recipient.msg("현재 사용 가능: " + " · ".join(f"'{target}에게 {word}" for word in words)
                      if words else "현재 사용 가능: 없음 (NPC 식별·접근·비전투 조건을 확인하세요.)")
        store.pop(npc.id, None)
        while len(store) >= GUIDE_LIMIT:
            del store[next(iter(store))]
        store[npc.id] = {"keywords": words, "target": target, "at": now,
                         "location_id": getattr(recipient.location, "id", None)}
    recipient.ndb.npc_dialogue_guides = store


def broadcast(caller, npc, raw, *, guide_requested=False):

    from typeclasses.explorers import Explorer

    intents = {item.keyword: item for item in intents_for(type_name(npc))}
    # 같은 raw를 사용하면서 수신자마다 새 Text와 선택 토큰을 만든다.
    for recipient in tuple(caller.location.contents):
        if not isinstance(recipient, Explorer):
            continue
        parts = [ft.token("npc", npc.key), ": "]
        active = available_intents(recipient, npc)
        active_ids = {item.intent_id for item in active}
        for part in re.split(r"(〈[^〉]+〉)", raw):
            intent = intents.get(part[1:-1]) if part.startswith("〈") and part.endswith("〉") else None
            if intent:
                enabled = intent.intent_id in active_ids
                selection = issue_token(recipient, npc, intent) if enabled else None
                parts.append(ft.dialogue_keyword(intent.keyword, intent.kind, selection))
            else:
                parts.append(part)
        recipient.msg(ft.text(*parts, kind="chat"))
        keyword_guide(recipient, npc, active, force=guide_requested and recipient.id == caller.id)


def public_speech(caller, original):
    message = ft.text(ft.token("player", caller.key), ": ", original, kind="chat")
    for recipient in tuple(caller.location.contents):
        recipient.msg(message)


def deliver(caller, npc, intent, raw, personal="", selection=None, *, guide_requested=False):
    if selection:
        store = token_store(caller)
        store.pop(selection, None)
        caller.ndb.npc_dialogue_tokens = store
    remember(caller, npc, intent)
    broadcast(caller, npc, raw, guide_requested=guide_requested)
    if personal:
        caller.msg(ft.text(ft.token("reward", personal)))
    if not caller.ndb.npc_dialogue_guided:
        caller.ndb.npc_dialogue_guided = True
        caller.msg("대사의 꺾쇠 안 단어로 NPC에게 말할 수 있습니다. 화제 안내 말로 현재 입력을 다시 확인하세요. 개인 메시지는 대화를 사용하세요.")


def execute(caller, npc, intent, *, selection=None, guide_requested=False):
    if not available(caller, npc, intent):
        raise rules.RuleError("지금은 이 NPC의 해당 키워드를 사용할 수 없습니다. 위치·시야·비전투·임무 조건을 확인하세요.")
    if not intent.mutates_state:
        deliver(caller, npc, intent, response(caller, npc, intent), guide_requested=guide_requested)
        return
    from world.content import ITEMS
    from world.credential_service import issuer_talk, reissue_credential

    with world_change():
        if not available(caller, npc, intent):
            raise rules.RuleError("현재 상태에서 사용할 수 없는 행동입니다.")
        quest_id, credential_id, operation = QUEST_NPCS[type_name(npc)]
        if intent.intent_id == "reissue":
            reissue_credential(caller, credential_id)
            raw = "출입증을 무료로 재발급했습니다. 〈출입증〉 안내를 확인하세요."
            personal = ITEMS[credential_id]["name"] + "을 무료로 재발급받았다."
        else:
            before = caller.profile_snapshot()

            def guarded(profile):
                state = profile["quests"][quest_id]
                if intent.intent_id == "accept" and (state["started"] or state["claimed"]):
                    raise rules.RuleError("이미 수락한 임무입니다.")
                if intent.intent_id == "report" and not (state["started"] and state["boss_defeated"] and not state["claimed"]):
                    raise rules.RuleError("최종 보고 조건을 충족하지 않았습니다.")
                return operation(profile)

            result, granted, boss_granted = issuer_talk(caller, credential_id, guarded)
            if result != ("start" if intent.intent_id == "accept" else "complete"):
                raise rules.RuleError("임무 상태 변경을 완료하지 못했습니다.")
            raw = ("임무를 맡겼습니다. 〈진행〉으로 다음 목표를 확인하세요." if result == "start"
                   else "탐사를 마쳤습니다. 수고했습니다. 〈출입증〉을 안내하겠습니다.")
            personal = ""
            if result == "complete":
                from world.content.item_mapping import BOSS_REWARDS

                after = caller.profile_snapshot()
                personal = f"경험치 {after['xp'] - before['xp']}, 보급칩 {after['credits'] - before['credits']}개, 붕대 3개를 받았다."
                if granted:
                    personal += " " + ITEMS[credential_id]["name"] + "을 받았다."
                if boss_granted:
                    personal += " " + ITEMS[BOSS_REWARDS[quest_id]]["name"] + "을 받았다."
        after_change(lambda: deliver(caller, npc, intent, raw, personal, selection))


def say(caller, value):
    original = validate_message(value)
    if not caller.location:
        raise rules.RuleError("현재 방에서만 말할 수 있습니다.")
    explicit, body = explicit_target(caller, original)
    public_speech(caller, original)
    npc, intent = choose(caller, body, explicit)
    if not npc:
        return
    if not intent:
        if not accessible(caller, npc):
            caller.msg("지금은 이 NPC에게 질문할 수 없습니다. 위치·시야·비전투 조건을 확인하세요.")
            return
        context = current_context(caller)
        if context and context["npc_id"] == npc.id:
            context["failures"] += 1
            caller.ndb.npc_dialogue_context = context
            if not explicit and context["failures"] > 1:
                return
        topics = available_dialogue_topics(caller, npc)
        opening = {"Commander": "무엇을 묻는지 잘 모르겠군.",
                   "Pathfinder": "그 질문은 잘 이해하지 못했습니다.",
                   "Shopkeeper": "어떤 물품 이야기인지 잘 모르겠어요.",
                   "Doctor": "어떤 의료 안내가 필요한지 잘 모르겠습니다.",
                   "SettlementOfficer": "어떤 정산 안내를 원하시는지 잘 모르겠습니다."}.get(
                       type_name(npc), "어떤 훈련 안내가 필요한지 잘 모르겠습니다.")
        guidance = (" " + " · ".join(f"〈{item.keyword}〉" for item in topics) + "에 관해 물어보세요."
                    if topics else " 지금은 이곳에서 더 안내할 내용이 없습니다.")
        broadcast(caller, npc, opening + guidance, guide_requested=True)
        return
    execute(caller, npc, intent, guide_requested=" ".join(body.split()) in GUIDE_REQUESTS)


def select_keyword(caller, token, session):
    """인증된 수신 캐릭터가 원래 NPC/Intent를 실행한다. fallback은 없다."""
    if (not session or not session.logged_in or session.get_puppet() != caller
            or session not in caller.sessions.all() or session.get_account() != caller.account):
        raise rules.RuleError("현재 캐릭터를 제어하는 세션에서만 선택할 수 있습니다.")
    if not isinstance(token, str) or len(token) > 128:
        raise rules.RuleError("잘못된 대화 선택입니다.")
    row = token_store(caller).get(token)
    if not row or row["character_id"] != caller.id or not row["issued_at"] <= time() < row["expires_at"]:
        raise rules.RuleError("대화 선택이 만료되었거나 유효하지 않습니다. NPC에게 다시 말을 걸어 주세요.")
    npc = object_by_id(row["npc_id"])
    intent = next((item for item in intents_for(type_name(npc)) if item.intent_id == row["intent_id"] and item.keyword == row["keyword"]), None) if npc else None
    if not npc or not intent or not available(caller, npc, intent):
        raise rules.RuleError("원래 NPC 또는 해당 키워드를 지금 사용할 수 없습니다.")
    public_speech(caller, f"{npc.key}에게 {intent.keyword}")
    execute(caller, npc, intent, selection=token if intent.mutates_state else None)


def discovery(npc, caller):
    from world.targets import labels

    target = labels(nearby(caller)).get(npc.id, npc.key)
    topics = " · ".join(item.keyword for item in intents_for(type_name(npc)) if not item.mutates_state)
    return f"말 걸기: '{target}에게 안녕 · {target}에게 안녕 말 / 화제: {topics}"
