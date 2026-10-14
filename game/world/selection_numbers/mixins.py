"""실물 생성/이동/삭제와 번호를 하나의 world_change에 묶는다."""

from world.multiplayer import world_change

from .mode import enabled


class NumberedObjectMixin:
    def save(self, *args, **kwargs):
        if not enabled():
            return super().save(*args, **kwargs)
        with world_change():
            result = super().save(*args, **kwargs)
            from .api import schedule_object

            if self.pk:
                schedule_object(self.pk)
            return result

    def move_to(self, *args, **kwargs):
        with world_change():
            return super().move_to(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with world_change():
            self.ndb.selection_deleting = True
            try:
                return super().delete(*args, **kwargs)
            finally:
                self.ndb.selection_deleting = False
