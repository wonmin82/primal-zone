"""ORM 변경만 예약한다. 조회 신호로 번호를 초기화하지 않는다."""

from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save

from .mode import enabled


def attribute_saving(sender, instance, **kwargs):
    """외부 Attribute UPDATE도 불변 그룹 검사를 DB 저장 이전에 수행한다."""
    if not enabled() or not instance.pk or instance.db_key not in ("selection_group_id", "selection_definition_id", "action_provider_id", "enemy_id"):
        return
    from evennia.objects.models import ObjectDB
    from evennia.typeclasses.models import Attribute
    from evennia.utils.dbserialize import deserialize
    from typeclasses.enemies import Enemy
    from typeclasses.loot import Corpse

    from .models import SelectionNumber

    old_value = Attribute.objects.filter(pk=instance.pk).values_list("db_value", flat=True).first()
    for owner in ObjectDB.objects.filter(db_attributes=instance):
        row = SelectionNumber.objects.filter(identity=str(owner.pk), kind__in=("object", "enemy", "corpse", "door")).select_related("scope").first()
        if not row:
            continue
        values = {key: deserialize(value) for key, value in owner.db_attributes.values_list("db_key", "db_value")}
        values[instance.db_key] = deserialize(instance.db_value)
        group = values.get("selection_group_id")
        if not group:
            if isinstance(owner, Enemy):
                group = "enemy:" + str(values.get("enemy_id"))
            elif isinstance(owner, Corpse):
                group = "world:corpse"
            elif row.kind == "door":
                group = "world:door"
            else:
                definition = values.get("selection_definition_id") or values.get("action_provider_id")
                if not definition:
                    identities = owner.tags.get(category="primal_interactable", return_list=True)
                    if len(identities) == 1:
                        definition = "interactable:" + identities[0]
                group = f"definition:{definition}" if definition else f"typeclass:{owner.db_typeclass_path}"
        if group != row.scope.group_id:
            instance.db_value = old_value
            owner.attributes.reset_cache()
            raise ValidationError("선택 그룹 변경에는 명시적인 마이그레이션이 필요합니다.")


def protect_removal(owner, keys):
    if not enabled():
        return
    from .models import SelectionNumber

    if owner.ndb.selection_deleting or not SelectionNumber.objects.filter(identity=str(owner.pk),
            kind__in=("object", "enemy", "corpse", "door")).exists():
        return
    changes_group = ("selection_group_id" in keys or "enemy_id" in keys
                     or not owner.db.selection_group_id and ("selection_definition_id" in keys
                     or not owner.db.selection_definition_id and "action_provider_id" in keys))
    if changes_group:
        owner.attributes.reset_cache()
        raise ValidationError("사용 중인 선택 그룹 메타데이터는 명시적 변환 없이 제거할 수 없습니다.")


def attribute_removing(sender, instance, **kwargs):
    if not enabled():
        instance._b1_owners = ()
        return
    if instance.db_key not in ("selection_group_id", "selection_definition_id", "action_provider_id", "enemy_id",
                               "selection_unique_names", "legacy_singleton_suffix_1"):
        instance._b1_owners = ()
        return
    from evennia.objects.models import ObjectDB

    owners = tuple(ObjectDB.objects.filter(db_attributes=instance))
    for owner in owners:
        protect_removal(owner, {instance.db_key})
    instance._b1_owners = owners


def attribute_removed(sender, instance, **kwargs):
    from evennia.objects.models import ObjectDB

    for owner in getattr(instance, "_b1_owners", ()):
        changed(ObjectDB, owner)


def changed(sender, instance, **kwargs):
    if not enabled():
        return
    from evennia.objects.models import ObjectDB

    from world.door_entities.models import Door
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot
    from world.multiplayer import world_change

    from .api import schedule, schedule_item, schedule_object

    if kwargs.get("raw"):
        return
    if isinstance(instance, ObjectDB):
        from .mixins import NumberedObjectMixin
        if not isinstance(instance, NumberedObjectMixin) and not instance.db.action_provider_id:
            return
    with world_change():
        if isinstance(instance, ItemEntity):
            schedule_item(instance.pk)
        elif isinstance(instance, CurrencyLoot):
            schedule("currency", instance.pk)
        elif isinstance(instance, Door):
            for identity in (instance.exit_a_id, instance.exit_b_id):
                schedule("door", identity)
        elif isinstance(instance, ObjectDB):
            schedule_object(instance.pk)


def metadata_changed(sender, instance, action, reverse, pk_set, **kwargs):
    from evennia.objects.models import ObjectDB
    from evennia.typeclasses.models import Attribute

    if not reverse and isinstance(instance, ObjectDB) and action in ("pre_remove", "pre_clear"):
        attributes = instance.db_attributes.all()
        if action == "pre_remove":
            attributes = attributes.filter(pk__in=pk_set)
        protect_removal(instance, set(attributes.values_list("db_key", flat=True)))
    if action in ("post_add", "post_remove", "post_clear") and not reverse and isinstance(instance, ObjectDB):
        keys = ("selection_group_id", "selection_definition_id", "action_provider_id", "enemy_id",
                "selection_unique_names", "legacy_singleton_suffix_1")
        if action != "post_add" or Attribute.objects.filter(pk__in=pk_set, db_key__in=keys).exists():
            changed(ObjectDB, instance)


def attribute_changed(sender, instance, **kwargs):
    if instance.db_key not in ("selection_group_id", "selection_definition_id", "action_provider_id",
                               "enemy_id", "selection_unique_names", "legacy_singleton_suffix_1"):
        return
    from evennia.objects.models import ObjectDB

    for owner in ObjectDB.objects.filter(db_attributes=instance):
        changed(ObjectDB, owner)


def connect():
    from evennia.objects.models import ObjectDB
    from evennia.typeclasses.models import Attribute

    from world.door_entities.models import Door
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot

    for model in (ObjectDB, ItemEntity, CurrencyLoot, Door):
        for event in (post_save, post_delete):
            event.connect(changed, sender=model, weak=False,
                          dispatch_uid=f"b1:{event}:{model._meta.label}")
    post_save.connect(attribute_changed, sender=Attribute, weak=False, dispatch_uid="b1:metadata")
    pre_save.connect(attribute_saving, sender=Attribute, weak=False, dispatch_uid="b1:metadata-before-save")
    pre_delete.connect(attribute_removing, sender=Attribute, weak=False, dispatch_uid="b1:metadata-remove")
    post_delete.connect(attribute_removed, sender=Attribute, weak=False, dispatch_uid="b1:metadata-removed")
    m2m_changed.connect(metadata_changed, sender=ObjectDB.db_attributes.through,
                        weak=False, dispatch_uid="b1:attribute-owner")
