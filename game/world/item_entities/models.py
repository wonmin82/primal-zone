"""정적 정의를 참조하는 실물 아이템과 삭제 후에도 유지되는 순번 발급기."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from world.content import ITEMS


class ItemSequence(models.Model):
    """migration에서 준비하는 단일 row. 발급은 item transaction 안에서만 수행한다."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_value = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="item_sequence_singleton")]


class ItemMigrationLedger(models.Model):
    """명시적 maintenance 변환의 source별 완료·검증 증거."""

    migration_version = models.PositiveIntegerField()
    source_kind = models.CharField(max_length=40)
    source_identity = models.PositiveBigIntegerField()
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True)
    source_digest = models.CharField(max_length=64)
    expected_state = models.JSONField(default=dict)
    created_counts = models.JSONField(default=dict)
    warnings = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("migration_version", "source_kind", "source_identity"), name="item_migration_source_unique")]


class ItemRuntime(models.Model):
    """source ledger와 별개인 전역 runtime 전환 version."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="item_runtime_singleton")]


class ItemEntity(models.Model):
    class Location(models.TextChoices):
        INVENTORY = "inventory", "소지품"
        EQUIPMENT = "equipment", "장비"
        PERSONAL_STORAGE = "personal_storage", "개인 보관"
        SHARED_STORAGE = "shared_storage", "공용 보관"
        WORLD_LOOT = "world_loot", "바닥 전리품"
        CORPSE_LOOT = "corpse_loot", "시체 전리품"
        INSIDE = "inside", "아이템 내부"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition_id = models.CharField(max_length=80)
    quantity = models.PositiveBigIntegerField(default=1)
    location_kind = models.CharField(max_length=20, choices=Location.choices)
    owner_object = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="item_entities",
    )
    parent_item = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    slot = models.CharField(max_length=40, null=True, blank=True)
    socket = models.CharField(max_length=40, null=True, blank=True)
    state = models.JSONField(default=dict, blank=True)
    sequence = models.PositiveBigIntegerField(unique=True, editable=False)
    unique_scope_key = models.CharField(max_length=160, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["sequence"]
        indexes = [
            models.Index(
                fields=["owner_object", "location_kind", "sequence"], name="item_owner_location_seq"
            ),
            models.Index(fields=["definition_id", "sequence"], name="item_definition_seq"),
            models.Index(fields=["parent_item", "socket"], name="item_parent_socket"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["parent_item", "socket"], condition=Q(socket="magazine"),
                                    name="item_one_magazine_socket"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="item_quantity_positive"),
            models.CheckConstraint(condition=Q(sequence__gte=1), name="item_sequence_positive"),
            models.CheckConstraint(
                condition=(
                    Q(
                        location_kind__in=[
                            "inventory",
                            "personal_storage",
                            "shared_storage",
                            "world_loot",
                            "corpse_loot",
                        ],
                        owner_object__isnull=False,
                        parent_item__isnull=True,
                        slot__isnull=True,
                        socket__isnull=True,
                    )
                    | (
                        Q(
                            location_kind="equipment",
                            owner_object__isnull=False,
                            parent_item__isnull=True,
                            slot__isnull=False,
                            socket__isnull=True,
                        )
                        & ~Q(slot="")
                    )
                    | (
                        Q(
                            location_kind="inside",
                            owner_object__isnull=True,
                            parent_item__isnull=False,
                            slot__isnull=True,
                            socket__isnull=False,
                        )
                        & ~Q(socket="")
                    )
                ),
                name="item_canonical_location",
            ),
            models.CheckConstraint(
                condition=~Q(parent_item=models.F("id")), name="item_not_own_parent"
            ),
        ]

    def root(self):
        """순환을 검출하면서 inside의 실제 소유 위치를 읽는다."""
        node, visited = self, set()
        while True:
            if node.pk in visited:
                raise ValidationError({"parent_item": "아이템의 부모 참조가 순환합니다."})
            visited.add(node.pk)
            if node.parent_item_id is None:
                return node
            try:
                node = node.parent_item
            except type(self).DoesNotExist:
                raise ValidationError({"parent_item": "부모 아이템이 없습니다."}) from None

    def scope_key(self):
        if ITEMS.get(self.definition_id, {}).get("unique_per_owner"):
            root = self.root()
            if root.owner_object_id is not None:
                return f"{root.owner_object_id}:{self.definition_id}"
        return None

    def clean(self):
        from typeclasses.explorers import Explorer
        from typeclasses.interactables import Container
        from typeclasses.loot import Corpse, DroppedLoot

        from world.item_entities.policy import definition_errors

        definition = ITEMS.get(self.definition_id)
        if definition is None:
            raise ValidationError({"definition_id": "등록되지 않은 아이템 정의입니다."})
        issues = definition_errors(self.definition_id, definition)
        if issues:
            raise ValidationError({"definition_id": issues})
        if type(self.quantity) is not int or self.quantity < 1:
            raise ValidationError({"quantity": "수량은 양의 정수여야 합니다."})
        if not definition["stackable"] and self.quantity != 1:
            raise ValidationError({"quantity": "개별 아이템의 수량은 1이어야 합니다."})
        maximum = definition["max_stack"]
        if maximum is not None and self.quantity > maximum:
            raise ValidationError({"quantity": "스택 최대 수량을 초과했습니다."})
        if not isinstance(self.state, dict):
            raise ValidationError({"state": "아이템 상태는 JSON 객체여야 합니다."})
        from world.item_states import state_errors

        issues = state_errors(definition, self.state)
        if issues:
            raise ValidationError({"state": issues})
        if self.socket == "magazine" and self.parent_item_id is not None:
            parent = ITEMS[self.parent_item.definition_id]
            magazine = definition.get("magazine", {})
            if (not parent.get("firearm_family")
                    or magazine.get("family") != parent["firearm_family"]):
                raise ValidationError({"parent_item": "총기와 탄창 family가 호환되지 않습니다."})
            if self.parent_item.children.filter(socket="magazine").exclude(pk=self.pk).exists():
                raise ValidationError({"socket": "총기에 이미 탄창이 삽입되어 있습니다."})
        self.root()
        if self.pk and (self.parent_item_id is not None or self.location_kind not in ("corpse_loot", "world_loot")):
            from world.loot_entities.models import LootClaim

            if LootClaim.objects.filter(item_entity_id=self.pk).exists():
                raise ValidationError("전리품 권리를 정리한 뒤 소지품/보관 위치로 이동해야 합니다.")
        if self.owner_object_id is not None:
            expected = {
                self.Location.INVENTORY: Explorer,
                self.Location.EQUIPMENT: Explorer,
                self.Location.PERSONAL_STORAGE: Explorer,
                self.Location.SHARED_STORAGE: Container,
                self.Location.WORLD_LOOT: DroppedLoot,
                self.Location.CORPSE_LOOT: Corpse,
            }.get(self.location_kind)
            owner = self.owner_object
            if (
                expected is None
                or not isinstance(owner, expected)
                or (self.location_kind == self.Location.SHARED_STORAGE and owner.personal)
            ):
                raise ValidationError(
                    {"owner_object": "해당 위치의 소유자 유형이 올바르지 않습니다."}
                )
        if self.unique_scope_key != self.scope_key():
            raise ValidationError(
                {"unique_scope_key": "현재 소유자와 고유 아이템 범위가 일치하지 않습니다."}
            )
        if self.location_kind == self.Location.EQUIPMENT and self.owner_object_id is not None:
            from world.equipment_service import validate_equipment_row

            validate_equipment_row(self)
        saved = type(self).objects.filter(pk=self.pk).values("sequence", "definition_id").first()
        from world.content.item_mapping import LEGACY_ITEM_MAPPING
        from world.item_runtime import maintenance

        definition_conversion = bool(saved and maintenance.get() and LEGACY_ITEM_MAPPING.get(saved["definition_id"]) == self.definition_id)
        if saved and (
            saved["sequence"] != self.sequence or saved["definition_id"] != self.definition_id and not definition_conversion
        ):
            raise ValidationError("생성된 아이템의 정의와 순번은 변경할 수 없습니다.")

    def save(self, *args, **kwargs):
        # Django의 IntegerField 정규화가 True/소수/문자열을 정수로 바꾸기 전에 검사한다.
        if type(self.quantity) is not int or self.quantity < 1:
            raise ValidationError({"quantity": "수량은 양의 정수여야 합니다."})
        self.unique_scope_key = self.scope_key()
        self.full_clean()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"unique_scope_key"}
        return super().save(*args, **kwargs)
