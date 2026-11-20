"""일반 공격 문구에서 공통 템플릿과 충돌하는 형식을 검증한다."""

import re

# '회로'처럼 명사 자체가 '로'로 끝날 수 있으므로 알려진 수단 명사의 조사 결합만 검사한다.
_INSTRUMENT_HEADS = ("가시", "꼬리", "몸체", "발톱", "이빨")


def is_instrument(value):
    if type(value) is not str or not re.fullmatch(r"[가-힣]+(?: [가-힣]+)*", value):
        return False
    head = value.rsplit(" ", 1)[-1]
    if head == "로" or head.endswith("으로"):
        return False
    return not (head.endswith("로") and head[:-1].endswith(_INSTRUMENT_HEADS))


def is_attack_verb(value):
    if type(value) is not str or not re.fullmatch(r"[가-힣]+(?: [가-힣]+)*", value):
        return False
    # 템플릿이 목적어와 문장부호를 붙이므로 문구는 평서형 과거 서술어로 끝낸다.
    if len(value) < 2 or not value.endswith("다") or (ord(value[-2]) - ord("가")) % 28 != 20:
        return False
    # 달리기와 기존 자동사·피동 패턴을 거절한다. 어휘의 의미는 완성 문장으로도 확인한다.
    *modifiers, predicate = value.split()
    if predicate == "달렸다" or predicate.endswith(("쓰러졌다", "넘어졌다", "당했다")):
        return False
    return not any(word.endswith(("을", "를")) for word in modifiers)
