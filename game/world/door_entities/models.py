"""기존 Exit를 재생성하지 않는 단일 Door 상태와 별도 설치 이력."""

from django.db import models


class Door(models.Model):
    door_id = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=100)
    aliases = models.JSONField(default=list)
    room_a = models.CharField(max_length=80)
    room_b = models.CharField(max_length=80)
    exit_a = models.OneToOneField("objects.ObjectDB", on_delete=models.PROTECT, related_name="door_endpoint_a")
    exit_b = models.OneToOneField("objects.ObjectDB", on_delete=models.PROTECT, related_name="door_endpoint_b")
    direction_a = models.CharField(max_length=30)
    direction_b = models.CharField(max_length=30)
    state = models.CharField(max_length=10, choices=[(s, s) for s in ("OPEN", "CLOSED", "LOCKED")])
    lockable = models.BooleanField(default=False)
    key_id = models.CharField(max_length=80, blank=True)
    inside_room_id = models.CharField(max_length=80, blank=True)
    auto_close_at = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(exit_a=models.F("exit_b")), name="door_distinct_exits"),
        ]


class DoorInstallation(models.Model):
    # Door 삭제 이후에도 PK/endpoint와 설치 시각이 남아 신규 설치와 소실을 구분한다.
    door_id = models.CharField(max_length=80, unique=True)
    door_pk = models.PositiveBigIntegerField()
    installed_at = models.FloatField()
    endpoints = models.JSONField()
