"""일반 공격 문구에서 공통 템플릿과 충돌하는 형식을 검증한다."""

import re


def is_instrument(value):
    # '로'는 '회로' 같은 명사에도 쓰인다. 수단에 쓰는 명사와 결합한 명확한 사례만 막는다.
    return (type(value) is str and re.fullmatch(r"[가-힣]+(?: [가-힣]+)*", value) is not None
            and not value.endswith(("으로", "이빨로", "몸체로")))


def is_attack_verb(value):
    if type(value) is not str or not re.fullmatch(r"[가-힣]+(?: [가-힣]+)*", value):
        return False
    # 템플릿이 목적어와 문장부호를 붙이므로 문구는 평서형 과거 서술어로 끝낸다.
    if len(value) < 2 or not value.endswith("다") or (ord(value[-2]) - ord("가")) % 28 != 20:
        return False
    # 대표적인 자동사와 피동 표현을 거절한다. 목적어와의 자연스러움은 완성 문장으로도 확인한다.
    if value.endswith(("쓰러졌다", "넘어졌다", "당했다")):
        return False
    return not any(word.endswith(("을", "를")) for word in value.split()[:-1])
