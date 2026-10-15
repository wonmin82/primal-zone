"""번호 그룹과 소유 관계만 저장한다. 게임 객체와 수량은 기존 모델이 소유한다."""

from django.db import models
from django.db.models import Q


class NumberScope(models.Model):
    scope_id = models.CharField(max_length=180)
    group_id = models.CharField(max_length=180)
    next_number = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("scope_id", "group_id"), name="b1_scope_group_unique"),
            models.CheckConstraint(condition=Q(next_number__gte=1), name="b1_counter_positive"),
        ]


class SelectionNumber(models.Model):
    scope = models.ForeignKey(NumberScope, on_delete=models.PROTECT, related_name="members")
    kind = models.CharField(max_length=20)
    identity = models.CharField(max_length=100)
    number = models.PositiveBigIntegerField()
    name = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("kind", "identity"), name="b1_object_unique"),
            models.UniqueConstraint(fields=("scope", "number"), name="b1_number_unique"),
            models.CheckConstraint(condition=Q(number__gte=1), name="b1_number_positive"),
        ]
