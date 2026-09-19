"""공유 상태 변경은 단일 Evennia 서버에서 직렬 실행하고 DB에 원자적으로 저장한다."""

from contextlib import contextmanager
from threading import RLock

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


@contextmanager
def world_change():
    # 명령과 타이머는 같은 서버 프로세스에서 실행되며 이 구간에서는 yield하지 않는다.
    with _lock, transaction.atomic():
        yield


def object_by_id(identity):
    return ObjectDB.objects.filter(pk=identity).first() if identity else None
