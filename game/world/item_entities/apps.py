"""아이템 영속 모델의 Django 앱 등록."""

from django.apps import AppConfig


class ItemEntitiesConfig(AppConfig):
    name = "world.item_entities"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "실물 아이템"
