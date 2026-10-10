"""NPC 화제·행동의 선언형 SSOT. DB/Evennia와 무관한 인식·무결성 계약."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    intent_id: str
    keyword: str
    aliases: tuple = ()
    kind: str = "topic"
    priority: int = 10
    availability: str = "accessible"
    handler: str = "describe"
    next_topics: tuple = ()
    mutates_state: bool = False


GUIDE_REQUESTS = ("화제 안내", "사용 가능한 화제")
GREETING = Intent("greeting", "안녕", ("안녕하세요", "반갑습니다", *GUIDE_REQUESTS), priority=100, handler="greet")
MISSION = (
    GREETING,
    Intent("mission", "임무", ("의뢰",), next_topics=("accept", "progress")),
    Intent("progress", "진행", ("진행 상황", "목표"), next_topics=("report",)),
    Intent("region", "지역", ("통신탑", "밀림")),
    Intent("credential", "출입증", next_topics=("reissue",)),
    Intent("accept", "수락", ("수락하겠습니다",), "action", 90, "accept", "accept", ("progress",), True),
    Intent("report", "보고", ("보고하겠습니다",), "action", 90, "report", "report", ("credential",), True),
    Intent("reissue", "재발급", ("재발급해주세요",), "action", 90, "reissue", "reissue", (), True),
)
SERVICE_INTENTS = {
    "SkillTrainer": (GREETING, Intent("training", "훈련", ("기술",), handler="training")),
    "AttributeTrainer": (GREETING, Intent("training", "훈련", ("특성", "배분"), handler="training")),
    "TrainingManager": (GREETING, Intent("training", "훈련", ("재훈련", "재분배"), handler="training")),
    "Shopkeeper": (GREETING, Intent("supply", "보급", ("물품", "상점", "가격", "거래"), handler="supply")),
    "Doctor": (GREETING, Intent("medical", "의료", ("회복", "비용"), handler="medical")),
    "SettlementOfficer": (GREETING, Intent("settlement", "정산", ("회수부품", "환율", "교환"), handler="settlement")),
    "Commander": MISSION,
    "Pathfinder": MISSION,
}


def intents_for(type_name):
    return SERVICE_INTENTS.get(type_name, ())


def recognize(intents, body):
    """황금색 행동은 등록된 완전 일치만 허용한다. 질문 패턴은 화제에만 적용한다."""
    value = re.sub(r"\s+", " ", body.strip()).casefold()
    for intent in sorted(intents, key=lambda item: -item.priority):
        if value in {intent.keyword.casefold(), *(alias.casefold() for alias in intent.aliases)}:
            return intent
    for intent in intents:
        if intent.mutates_state:
            continue
        for word in (intent.keyword, *intent.aliases):
            if re.fullmatch(re.escape(word) + r"(?:은|는|이|가|에 대해)? ?(?:뭔가요|알려주세요|알려 주세요|설명해 주세요|어떻게 되나요)[?.!]*", value):
                return intent
    return None


def intent_errors(type_name, intents=None):
    intents = intents_for(type_name) if intents is None else intents
    issues, words, identities = [], set(), {item.intent_id for item in intents}
    if len(identities) != len(intents):
        issues.append(f"{type_name}: Intent ID 중복")
    for intent in intents:
        for word in (intent.keyword, *intent.aliases):
            key = word.casefold()
            if key in words:
                issues.append(f"{type_name}: 키워드 충돌: {word}")
            words.add(key)
        if intent.kind not in ("topic", "action") or intent.mutates_state != (intent.kind == "action"):
            issues.append(f"{type_name}: Intent 종류/변경 계약 오류")
        if any(topic not in identities for topic in intent.next_topics):
            issues.append(f"{type_name}: 미등록 후속 화제")
        if intent.handler not in {"describe", "greet", "accept", "report", "reissue", "training", "supply", "medical", "settlement"}:
            issues.append(f"{type_name}: 미등록 handler")
        if intent.availability not in {"accessible", "accept", "report", "reissue"}:
            issues.append(f"{type_name}: 미등록 availability")
    return issues
