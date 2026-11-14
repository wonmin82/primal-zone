"""이전 월드에서 적 실물을 식별하는 읽기 전용 Typeclass."""

from evennia.objects.objects import DefaultObject


class Enemy(DefaultObject):
    """이전 Spawn 감사와 번호 기록의 타입 식별에 사용한다."""
