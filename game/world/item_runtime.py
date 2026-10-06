"""전역 cutover 방어선. 변환은 명시적 maintenance 경계에서만 허용한다."""

from contextvars import ContextVar

from django.conf import settings

VERSION = 1
maintenance = ContextVar("item_maintenance", default=False)


def native_runtime():
    from world.item_entities.models import ItemRuntime

    return ItemRuntime.objects.filter(pk=1, version=VERSION).exists()


def require_runtime():
    if maintenance.get() or getattr(settings, "ITEM_MIGRATION_AUDIT", False):
        return
    if not native_runtime():
        from world.rules import RuleError

        raise RuleError("Item runtime migration required: maintenance에서 dry-run/apply/verify/cutover를 완료하세요.")


def initialize_fresh(exclude=None):
    """실제 빈 world만 직접 native로 시작한다. 기존 world에서는 자동 변환하지 않는다."""
    from evennia.objects.models import ObjectDB

    from world.item_entities.models import ItemEntity, ItemRuntime
    from world.loot_entities.models import CurrencyLoot
    from world.multiplayer import world_change

    if maintenance.get() or getattr(settings, "ITEM_MIGRATION_AUDIT", False):
        return False
    with world_change():
        if native_runtime():
            return True
        sources = ObjectDB.objects.filter(db_typeclass_path__in=(
            "typeclasses.explorers.Explorer", "typeclasses.interactables.Container",
            "typeclasses.interactables.PersonalLocker", "typeclasses.loot.Corpse", "typeclasses.loot.DroppedLoot"))
        if exclude:
            sources = sources.exclude(pk=exclude.pk)
        if sources.exists() or ItemEntity.objects.exists() or CurrencyLoot.objects.exists():
            return False
        ItemRuntime.objects.update_or_create(pk=1, defaults={"version": VERSION})
        return True
