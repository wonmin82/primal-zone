"""정산 전용 자원·수량 입력. 일반 stack/loot 수량 문법은 변경하지 않는다."""

from world.content import ITEMS
from world.rules import RuleError
from world.targets import stack_selector


def parse_salvage(value):
    """1개/N개는 정수, 모두는 None. resource 이름은 기존 item selector를 따른다."""
    from world.stack_quantity import parse_stack_quantity

    name, quantity = parse_stack_quantity(value)
    identity, all_items = stack_selector(name, ITEMS, "교환")
    if identity != "scrap":
        raise RuleError("자원 정산은 회수부품만 가능합니다. 회수부품 교환 · 회수부품 모두 교환")
    return None if all_items else quantity
