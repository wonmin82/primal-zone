"""개 suffix 수량과 모두를 분리한다. 숫자가 든 아이템 이름은 그대로 보존한다."""

from world.rules import RuleError


def parse_stack_quantity(value):
    words = value.strip().split()
    quantity = 1
    if words and words[-1] == "모두":
        words.pop()
        quantity = None
    elif words and words[-1].endswith("개"):
        number = words.pop()[:-1]
        if not number.isdecimal() or int(number) <= 0:
            raise RuleError("수량은 1개 이상의 정수로 지정하세요.")
        quantity = int(number)
    if not words or any(word == "모두" or word.endswith("개") for word in words):
        raise RuleError("물건 이름과 수량 또는 '모두' 중 하나를 지정하세요.")
    return " ".join(words), quantity
