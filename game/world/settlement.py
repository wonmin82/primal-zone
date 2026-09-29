"""정산 전용 자원·수량 입력. 일반 stack/loot 수량 문법은 변경하지 않는다."""

from world.content import ITEMS
from world.rules import RuleError
from world.targets import stack_selector


def parse_salvage(value):
    """1개/N개는 정수, 모두는 None. resource 이름은 기존 item selector를 따른다."""
    words = value.strip().split()
    quantity = 1
    explicit_quantity = bool(words and words[-1].endswith("개"))
    if explicit_quantity:
        number = words.pop()[:-1]
        try:
            if not number.isdecimal():
                raise ValueError
            quantity = int(number)
            if quantity <= 0:
                raise ValueError
        except ValueError:
            raise RuleError("정산 수량은 1개 이상의 정수로 지정하세요.") from None
    identity, all_items = stack_selector(" ".join(words), ITEMS, "교환")
    if identity != "scrap":
        raise RuleError("자원 정산은 회수부품만 가능합니다. 회수부품 교환 · 회수부품 모두 교환")
    if all_items and explicit_quantity:
        raise RuleError("정산 수량과 '모두' 중 하나만 지정하세요.")
    return None if all_items else quantity
