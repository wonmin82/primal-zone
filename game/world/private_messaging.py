"""플레이어 비공개 메시지 SSOT. 본문은 저장하지 않고 수락 후 전송을 시도한다."""

from evennia.utils.dbserialize import deserialize

from world import rules
from world import text as ft
from world.multiplayer import after_change, object_by_id, world_change
from world.npc_dialogue import validate_message
from world.targets import matching, names, ordered, parse_selector, strict_single

BLOCK_LIMIT = 100
ATTRIBUTE = "private_messaging"


def state(character):
    raw = deserialize(character.attributes.get(ATTRIBUTE))
    if raw is None:
        return {"version": 1, "last_private_peer_id": None, "blocked_character_ids": []}
    if (not isinstance(raw, dict) or raw.get("version") != 1
            or not isinstance(raw.get("blocked_character_ids"), list)
            or any(type(identity) is not int or identity <= 0 for identity in raw["blocked_character_ids"])
            or len(raw["blocked_character_ids"]) > BLOCK_LIMIT
            or (raw.get("last_private_peer_id") is not None and
                (type(raw["last_private_peer_id"]) is not int or raw["last_private_peer_id"] <= 0))):
        raise rules.RuleError("개인 메시지 저장 상태를 확인할 수 없습니다. 관리자에게 문의하세요.")
    return {"version": 1, "last_private_peer_id": raw.get("last_private_peer_id"),
            "blocked_character_ids": list(raw["blocked_character_ids"])}


def players():
    from typeclasses.explorers import Explorer

    return ordered(Explorer.objects.all())


def resolve_player(value):
    pool = players()
    selector = parse_selector(value, [name for obj in pool for name in names(obj)])
    return strict_single(matching(pool, selector), selector, "대화")


def split_message(arguments):
    """실제 이름/별칭의 가장 긴 접두 선택자 뒤를 원문 메시지로 보존한다."""
    import re

    pool = players()
    known = [name for obj in pool for name in names(obj)]
    candidates = []
    for boundary in re.finditer(r"\s+", arguments.strip()):
        prefix = arguments[:boundary.start()].strip()
        try:
            selector = parse_selector(prefix, known)
        except rules.RuleError:
            continue
        matches = matching(pool, selector)
        if matches:
            candidates.append((boundary.end(), selector, matches))
    if not candidates:
        raise rules.RuleError("플레이어 이름과 내용을 입력하세요. 예: 철수 안녕하세요 대화")
    offset, selector, matches = candidates[-1]
    return strict_single(matches, selector, "대화"), arguments[offset:]


def accepted_delivery(sender, recipient, body):
    """DB 수락 완료와 실제 열람은 다르다. 네트워크 오류는 수락을 롤백하지 않는다."""
    from evennia.utils import logger

    for character, value in (
        (recipient, ft.text("[개인] ", ft.token("player", sender.key), " → 나: ", body, kind="chat")),
        (sender, ft.text("[개인] 나 → ", ft.token("player", recipient.key), ": ", body, kind="chat")),
    ):
        try:
            character.msg(value)
        except Exception:
            logger.log_trace("개인 메시지 전송 시도 실패 (본문 미기록)")


def send(sender, recipient, value):
    from typeclasses.explorers import Explorer

    body = validate_message(value)
    with world_change():
        if (not isinstance(recipient, Explorer) or not recipient.pk or sender.id == recipient.id
                or not recipient.sessions.count()):
            raise rules.RuleError("온라인인 다른 플레이어에게만 개인 메시지를 보낼 수 있습니다.")
        own, other = state(sender), state(recipient)
        if sender.id in other["blocked_character_ids"]:
            # 온라인/수신 상태를 구체적인 차단 여부로 노출하지 않는다.
            raise rules.RuleError("현재 이 상대에게 메시지를 전달할 수 없습니다.")
        own["last_private_peer_id"], other["last_private_peer_id"] = recipient.id, sender.id
        sender.attributes.add(ATTRIBUTE, own)
        recipient.attributes.add(ATTRIBUTE, other)
        after_change(lambda: accepted_delivery(sender, recipient, body))


def reply(sender, body):
    recipient = object_by_id(state(sender)["last_private_peer_id"])
    if not recipient:
        raise rules.RuleError("최근 개인 메시지 상대가 없거나 더 이상 존재하지 않습니다.")
    send(sender, recipient, body)


def toggle_block(caller, selector):
    target = resolve_player(selector)
    if target.id == caller.id:
        raise rules.RuleError("자신을 차단할 수 없습니다.")
    with world_change():
        current = state(caller)
        blocked = current["blocked_character_ids"]
        if target.id in blocked:
            blocked.remove(target.id)
            enabled = False
        else:
            if len(blocked) >= BLOCK_LIMIT:
                raise rules.RuleError("차단 목록은 100명까지 등록할 수 있습니다.")
            blocked.append(target.id)
            enabled = True
        caller.attributes.add(ATTRIBUTE, current)
        after_change(lambda: caller.msg(f"{target.key}의 개인 메시지 수신 차단을 {'설정' if enabled else '해제'}했습니다."))


def blocked_list(caller):
    identities = state(caller)["blocked_character_ids"]
    values = [object_by_id(identity) for identity in identities]
    return "차단 목록: " + (" · ".join(obj.key if obj else "삭제된 캐릭터" for obj in values) or "없음")
