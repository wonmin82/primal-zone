"""새 선언형 World Provider의 영속 생명주기 경계."""

from evennia.objects.objects import DefaultObject
from world.selection_numbers.mixins import NumberedObjectMixin


class ActionProviderObject(NumberedObjectMixin, DefaultObject):
    """생성·직접 위치 저장·move_to·삭제를 번호와 같은 변경 단위로 처리한다."""
