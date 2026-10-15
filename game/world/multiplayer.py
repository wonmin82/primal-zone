"""공유 상태 변경은 단일 Evennia 서버에서 직렬 실행하고 DB에 원자적으로 저장한다."""

from contextlib import contextmanager
from threading import RLock, local

from django.conf import settings
from django.db import transaction
from evennia.objects.models import ObjectDB
from evennia.scripts.models import ScriptDB

from world.timing import configured_timings

PARTY_MAX_SIZE = 4
PARTY_INVITE_TTL_SECONDS = 60
_timing = configured_timings(settings)
CLAIM_TIMEOUT_SECONDS = _timing["CLAIM_TIMEOUT_SECONDS"]
PARTICIPATION_TIMEOUT_SECONDS = _timing["PARTICIPATION_TIMEOUT_SECONDS"]
CORPSE_TTL_SECONDS = _timing["CORPSE_TTL_SECONDS"]
LOOT_PROTECTION_SECONDS = _timing["LOOT_PROTECTION_SECONDS"]
RESPAWN_DELAY_SECONDS = _timing["RESPAWN_DELAY_SECONDS"]
COMBAT_INTERVAL = _timing["COMBAT_INTERVAL"]
ENEMY_RECOVERY_DELAY_SECONDS = _timing["ENEMY_RECOVERY_DELAY_SECONDS"]
ENEMY_RESET_SECONDS = ENEMY_RECOVERY_DELAY_SECONDS  # 기존 import만 지원하는 호환 alias

_lock = RLock()
_context = local()


def after_change(callback):
    """화면 전송과 runtime 작업은 가장 바깥의 변경이 성공한 뒤 실행한다."""
    if getattr(_context, "depth", 0):
        _context.callbacks.append(callback)
    else:
        callback()


def before_commit(key, callback):
    """최종 실물 집합으로 변경을 확정한다. 독립 DB 커밋이나 on_commit 쓰기는 금지한다."""
    if not getattr(_context, "depth", 0):
        raise RuntimeError("최종 변경 예약은 world_change 안에서만 가능합니다.")
    _context.finalizers[key] = callback


def pending_commit(key):
    return getattr(_context, "finalizers", {}).get(key)


@contextmanager
def world_change():
    # 명령과 타이머는 같은 서버 프로세스에서 실행되며 이 구간에서는 yield하지 않는다.
    with _lock:
        outer = not getattr(_context, "depth", 0)
        if outer:
            _context.callbacks = []
            _context.finalizers = {}
        _context.depth = getattr(_context, "depth", 0) + 1
        mark = len(_context.callbacks)
        finalizers = dict(_context.finalizers)
        cached = [(obj, obj.pk) for obj in ObjectDB.get_all_cached_instances()]
        try:
            with transaction.atomic():
                yield
                if outer:
                    for finalizer in tuple(_context.finalizers.values()):
                        finalizer()
        except Exception:
            del _context.callbacks[mark:]
            _context.finalizers = finalizers
            # DB rollback만으로 Evennia의 identity/Attribute/room 캐시는 복구되지 않는다.
            from evennia.typeclasses.models import Attribute

            values = dict(Attribute.objects.values_list("pk", "db_value"))
            for attribute in Attribute.get_all_cached_instances():
                if attribute.pk in values:
                    attribute.db_value = values[attribute.pk]
                else:
                    Attribute.flush_cached_instance(attribute)
            fields = [field.attname for field in ObjectDB._meta.concrete_fields]
            restored = {row[0]: dict(zip(fields, row, strict=True))
                        for row in ObjectDB.objects.values_list(*fields)}
            locations = {identity: row["db_location_id"] for identity, row in restored.items()}
            existing = set(locations)
            for obj, identity in cached:
                if identity in existing:
                    obj.pk = identity
                    obj._is_deleted = False
                    # 실패한 move_to가 바꾼 FK/관계 캐시도 DB의 rollback 위치로 복구한다.
                    for name, value in restored[identity].items():
                        setattr(obj, name, value)
                    obj._state.fields_cache.clear()
                    obj.attributes.reset_cache()
            for obj, identity in cached:
                if identity in existing:
                    obj.contents_cache.init()
            for obj in ObjectDB.get_all_cached_instances():
                if obj.pk not in existing:
                    ObjectDB.flush_cached_instance(obj)
            # 공용 환경/시설도 Script attribute cache를 사용한다.
            script_ids = set(ScriptDB.objects.values_list("pk", flat=True))
            for script in ScriptDB.get_all_cached_instances():
                if script.pk in script_ids:
                    script.attributes.reset_cache()
                else:
                    ScriptDB.flush_cached_instance(script)
            raise
        finally:
            _context.depth -= 1
        if outer:
            _context.finalizers = {}
            callbacks, _context.callbacks = _context.callbacks, []
            for callback in callbacks:
                callback()


def object_by_id(identity):
    return ObjectDB.objects.filter(pk=identity).first() if identity else None
