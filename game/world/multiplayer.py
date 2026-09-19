"""공유 상태 변경은 단일 Evennia 서버에서 직렬 실행하고 DB에 원자적으로 저장한다."""

from contextlib import contextmanager
from threading import RLock, local

from django.db import transaction
from evennia.objects.models import ObjectDB

PARTY_MAX_SIZE = 4
PARTY_INVITE_TTL_SECONDS = 60
CLAIM_TIMEOUT_SECONDS = 15
PARTICIPATION_TIMEOUT_SECONDS = 15
CORPSE_TTL_SECONDS = 30
LOOT_PROTECTION_SECONDS = 120
RESPAWN_DELAY_SECONDS = 15
COMBAT_INTERVAL = 2.5
ENEMY_RESET_SECONDS = 15

_lock = RLock()
_context = local()


def after_change(callback):
    """화면 전송과 runtime 작업은 가장 바깥의 변경이 성공한 뒤 실행한다."""
    if getattr(_context, "depth", 0):
        _context.callbacks.append(callback)
    else:
        callback()


@contextmanager
def world_change():
    # 명령과 타이머는 같은 서버 프로세스에서 실행되며 이 구간에서는 yield하지 않는다.
    with _lock:
        outer = not getattr(_context, "depth", 0)
        if outer:
            _context.callbacks = []
        _context.depth = getattr(_context, "depth", 0) + 1
        mark = len(_context.callbacks)
        cached = [(obj, obj.pk) for obj in ObjectDB.get_all_cached_instances()]
        try:
            with transaction.atomic():
                yield
        except Exception:
            del _context.callbacks[mark:]
            # DB rollback만으로 Evennia의 identity/Attribute/room 캐시는 복구되지 않는다.
            from evennia.typeclasses.models import Attribute

            values = dict(Attribute.objects.values_list("pk", "db_value"))
            for attribute in Attribute.get_all_cached_instances():
                if attribute.pk in values:
                    attribute.db_value = values[attribute.pk]
                else:
                    Attribute.flush_cached_instance(attribute)
            existing = set(ObjectDB.objects.values_list("pk", flat=True))
            for obj, identity in cached:
                if identity in existing:
                    obj.pk = identity
                    obj._is_deleted = False
                    obj.attributes.reset_cache()
                    obj.contents_cache.init()
            for obj in ObjectDB.get_all_cached_instances():
                if obj.pk not in existing:
                    ObjectDB.flush_cached_instance(obj)
            raise
        finally:
            _context.depth -= 1
        if outer:
            callbacks, _context.callbacks = _context.callbacks, []
            for callback in callbacks:
                callback()


def object_by_id(identity):
    return ObjectDB.objects.filter(pk=identity).first() if identity else None
