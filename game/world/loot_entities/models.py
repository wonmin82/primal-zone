"""전리품 관계는 명시적으로 정리한다. 플레이어/공간 삭제로 권리를 잃지 않는다."""

from math import isfinite

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum


def validate_time(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValidationError("보호 기한은 유한한 0 이상의 시각이어야 합니다.")


class Reservation(models.Model):
    # 마지막 멤버 탈퇴 시 Party가 삭제되는 기존 의미를 유지한다.
    # 배정된 player/화폐 share와 보호 기한은 그대로 남는다.
    reserved_party = models.ForeignKey("objects.ObjectDB", null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="+")
    reserved_player = models.ForeignKey("objects.ObjectDB", null=True, blank=True,
                                        on_delete=models.PROTECT, related_name="+")
    protection_until = models.FloatField(default=0, validators=[validate_time])

    class Meta:
        abstract = True

    def clean(self):
        from typeclasses.explorers import Explorer
        from typeclasses.parties import Party

        validate_time(self.protection_until)
        if self.reserved_party_id and not isinstance(self.reserved_party, Party):
            raise ValidationError({"reserved_party": "파티만 보호권을 가질 수 있습니다."})
        for field in ("reserved_player", "assigned_player"):
            if getattr(self, field + "_id", None) and not isinstance(getattr(self, field), Explorer):
                raise ValidationError({field: "탐사자 참조가 필요합니다."})

    def save(self, *args, **kwargs):
        for field in ("quantity", "remaining_amount"):
            value = getattr(self, field, None)
            if value is not None and (type(value) is not int or value < (1 if field == "quantity" else 0)):
                raise ValidationError({field: "수량은 유효한 정수여야 합니다."})
        self.full_clean()
        return super().save(*args, **kwargs)


class LootClaim(Reservation):
    item_entity = models.OneToOneField("item_entities.ItemEntity", on_delete=models.PROTECT,
                                       related_name="loot_claim")
    assigned_player = models.ForeignKey("objects.ObjectDB", null=True, blank=True,
                                        on_delete=models.PROTECT, related_name="+")

    def clean(self):
        super().clean()
        from world.item_entities.models import ItemEntity

        item = ItemEntity.objects.filter(pk=self.item_entity_id).first()
        if item is None:
            raise ValidationError({"item_entity": "실물 전리품이 없습니다."})
        if item.parent_item_id is not None or item.location_kind not in ("corpse_loot", "world_loot"):
            raise ValidationError({"item_entity": "권리는 시체/바닥의 실물 root에만 연결합니다."})


class CurrencyLoot(Reservation):
    owner_object = models.ForeignKey("objects.ObjectDB", on_delete=models.PROTECT,
                                     related_name="currency_loot")
    quantity = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["pk"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="currency_loot_positive")]

    def clean(self):
        from typeclasses.loot import Corpse, DroppedLoot

        super().clean()
        if not isinstance(self.owner_object, (Corpse, DroppedLoot)):
            raise ValidationError({"owner_object": "화폐 전리품은 시체/바닥 공간에 속해야 합니다."})
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValidationError({"quantity": "화폐 수량은 양의 정수여야 합니다."})
        total = self.shares.aggregate(total=Sum("remaining_amount"))["total"] if self.pk else 0
        if (total or 0) > self.quantity:
            raise ValidationError("잔여 지분 합이 화폐 전리품 수량을 초과합니다.")


class CurrencyLootShare(models.Model):
    currency_loot = models.ForeignKey(CurrencyLoot, on_delete=models.PROTECT, related_name="shares")
    player = models.ForeignKey("objects.ObjectDB", on_delete=models.PROTECT, related_name="+")
    # 0인 행도 원래 참여자의 지급 요청 자격을 보존한다.
    remaining_amount = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["player_id"]
        constraints = [
            models.UniqueConstraint(fields=["currency_loot", "player"], name="currency_share_player_unique"),
            models.CheckConstraint(condition=Q(remaining_amount__gte=0), name="currency_share_nonnegative"),
        ]

    def clean(self):
        from typeclasses.explorers import Explorer

        if not isinstance(self.player, Explorer):
            raise ValidationError({"player": "탐사자 참조가 필요합니다."})
        if type(self.remaining_amount) is not int or self.remaining_amount < 0:
            raise ValidationError({"remaining_amount": "잔여 지분은 0 이상의 정수여야 합니다."})
        parent = CurrencyLoot.objects.filter(pk=self.currency_loot_id).first()
        if parent is None:
            raise ValidationError({"currency_loot": "화폐 전리품이 없습니다."})
        others = parent.shares.exclude(pk=self.pk).aggregate(total=Sum("remaining_amount"))["total"] or 0
        if others + self.remaining_amount > parent.quantity:
            raise ValidationError("잔여 지분 합이 화폐 전리품 수량을 초과합니다.")

    def save(self, *args, **kwargs):
        if type(self.remaining_amount) is not int or self.remaining_amount < 0:
            raise ValidationError({"remaining_amount": "잔여 지분은 0 이상의 정수여야 합니다."})
        self.full_clean()
        return super().save(*args, **kwargs)
