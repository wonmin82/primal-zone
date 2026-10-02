"""보급칩 표시와 금액 검증. 플레이어 잔액은 credits를 그대로 사용한다."""

from world.content.economy import CURRENCY


def format_currency(amount):
    return f"{amount}{CURRENCY['unit']}"


def currency_names():
    return (CURRENCY["name"], *CURRENCY["aliases"])


def is_currency(name):
    return name.strip() in currency_names()


def currency_request(selector):
    """공통 selector가 분리한 이름에서 금액만 읽는다. None 반환은 아이템 입력이다."""
    from world.rules import RuleError
    from world.targets import Mode

    name = selector.name.strip()
    if is_currency(name):
        return (None if selector.mode == Mode.ALL else 1, selector)
    if not name.endswith(CURRENCY["unit"]):
        return None
    number = name[:-len(CURRENCY["unit"])]
    if not number.isascii() or not number.isdecimal() or int(number) <= 0:
        raise RuleError("보급칩 금액은 1 이상의 정수로 지정하세요.")
    if selector.mode != Mode.DEFAULT:
        raise RuleError("금액과 번호/모두를 함께 지정할 수 없습니다.")
    return int(number), selector


def spend_currency(profile, amount=None):
    from world.rules import RuleError, require_peace

    require_peace(profile)
    amount = profile["credits"] if amount is None else amount
    if type(amount) is not int or amount <= 0:
        raise RuleError("보급칩 금액은 1 이상의 정수로 지정하세요.")
    if profile["credits"] < amount:
        raise RuleError("보급칩이 부족합니다.")
    profile["credits"] -= amount
    return amount
