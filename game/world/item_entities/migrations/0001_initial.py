# Django 6.0.8로 생성한 아이템 영속 기반의 초기 schema.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("objects", "0013_defaultobject_alter_objectdb_id_defaultcharacter_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ItemSequence",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("last_value", models.PositiveBigIntegerField(default=0)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("id", 1)), name="item_sequence_singleton"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ItemEntity",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("definition_id", models.CharField(max_length=80)),
                ("quantity", models.PositiveBigIntegerField(default=1)),
                (
                    "location_kind",
                    models.CharField(
                        choices=[
                            ("inventory", "소지품"),
                            ("equipment", "장비"),
                            ("personal_storage", "개인 보관"),
                            ("shared_storage", "공용 보관"),
                            ("world_loot", "바닥 전리품"),
                            ("corpse_loot", "시체 전리품"),
                            ("inside", "아이템 내부"),
                        ],
                        max_length=20,
                    ),
                ),
                ("slot", models.CharField(blank=True, max_length=40, null=True)),
                ("socket", models.CharField(blank=True, max_length=40, null=True)),
                ("state", models.JSONField(blank=True, default=dict)),
                ("sequence", models.PositiveBigIntegerField(editable=False, unique=True)),
                (
                    "unique_scope_key",
                    models.CharField(blank=True, max_length=160, null=True, unique=True),
                ),
                (
                    "owner_object",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="item_entities",
                        to="objects.objectdb",
                    ),
                ),
                (
                    "parent_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="children",
                        to="item_entities.itementity",
                    ),
                ),
            ],
            options={
                "ordering": ["sequence"],
                "indexes": [
                    models.Index(
                        fields=["owner_object", "location_kind", "sequence"],
                        name="item_owner_location_seq",
                    ),
                    models.Index(fields=["definition_id", "sequence"], name="item_definition_seq"),
                    models.Index(fields=["parent_item", "socket"], name="item_parent_socket"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("quantity__gte", 1)), name="item_quantity_positive"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("sequence__gte", 1)), name="item_sequence_positive"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                (
                                    "location_kind__in",
                                    [
                                        "inventory",
                                        "personal_storage",
                                        "shared_storage",
                                        "world_loot",
                                        "corpse_loot",
                                    ],
                                ),
                                ("owner_object__isnull", False),
                                ("parent_item__isnull", True),
                                ("slot__isnull", True),
                                ("socket__isnull", True),
                            ),
                            models.Q(
                                ("location_kind", "equipment"),
                                ("owner_object__isnull", False),
                                ("parent_item__isnull", True),
                                ("slot__isnull", False),
                                ("socket__isnull", True),
                                models.Q(("slot", ""), _negated=True),
                            ),
                            models.Q(
                                ("location_kind", "inside"),
                                ("owner_object__isnull", True),
                                ("parent_item__isnull", False),
                                ("slot__isnull", True),
                                ("socket__isnull", False),
                                models.Q(("socket", ""), _negated=True),
                            ),
                            _connector="OR",
                        ),
                        name="item_canonical_location",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("parent_item", models.F("id")), _negated=True),
                        name="item_not_own_parent",
                    ),
                ],
            },
        ),
    ]
