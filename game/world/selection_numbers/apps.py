from django.apps import AppConfig


class SelectionNumbersConfig(AppConfig):
    name = "world.selection_numbers"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "영속 선택 번호"

    def ready(self):
        from world.selection_numbers.signals import connect

        connect()
