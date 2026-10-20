"""Loot의 존재·획득 권한을 구분하지 않는 제한된 공개 오류 계약."""

from world.rules import RuleError


class LootUnavailable(RuleError):
    def __init__(self):
        super().__init__("지금 선택할 수 없는 전리품입니다.")
