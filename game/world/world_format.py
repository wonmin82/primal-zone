"""Fresh-only Actor 월드의 전체 READY 판정. PR-A는 운영 기동 경로를 변경하지 않는다."""

from uuid import UUID, uuid4

from django.db import connection
from evennia import create_script
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.scripts.models import ScriptDB
from evennia.scripts.scripts import DefaultScript
from evennia.typeclasses.tags import Tag

from world.multiplayer import world_change
from world.rules import RuleError

FORMAT_VERSION = 1
FORMAT_KEY = "primal_actor_world_format"


class WorldFormat(DefaultScript):
    def at_script_creation(self):
        self.key = FORMAT_KEY
        self.persistent = True
        self.interval = -1


def _models():
    from world.door_entities.models import Door, DoorInstallation
    from world.item_entities.models import (
        ItemEntity,
        ItemMigrationLedger,
        ItemRuntime,
        ItemSequence,
    )
    from world.loot_entities.models import CurrencyLoot, CurrencyLootShare, LootClaim
    from world.selection_numbers.models import NumberScope, SelectionNumber

    return (AccountDB, ObjectDB, ScriptDB, Tag, ItemEntity, ItemRuntime, ItemSequence, ItemMigrationLedger,
            CurrencyLoot, CurrencyLootShare, LootClaim, NumberScope, SelectionNumber, Door, DoorInstallation)


def assert_fresh():
    """실제 Schema·Object·관리 Tag·native 상태·부분 초기화 흔적을 읽고 기존 DB를 거절한다."""
    models = _models()
    if connection.vendor != "sqlite" or not {model._meta.db_table for model in models} <= set(connection.introspection.table_names()):
        raise RuleError("Actor World Format은 준비된 SQLite Schema가 필요합니다.")
    for model in models:
        if model is AccountDB:
            if model.objects.exclude(pk=1, is_superuser=True).exists():
                raise RuleError("기존 사용자 계정이 있는 DB는 Fresh로 초기화할 수 없습니다.")
        elif model.__name__ == "ItemSequence":
            if model.objects.exclude(pk=1, last_value=0).exists():
                raise RuleError("기존 아이템 순번이 있는 DB는 Fresh로 초기화할 수 없습니다.")
        elif model is Tag:
            if model.objects.filter(db_category__startswith="primal_").exists():
                raise RuleError("관리 Tag가 있는 기존 또는 부분 초기화 DB입니다.")
        elif model.objects.exists():
            raise RuleError("기존 데이터가 있는 DB는 자동 초기화·변환하지 않습니다.")


def _marker():
    markers = list(ScriptDB.objects.filter(db_key=FORMAT_KEY))
    if len(markers) > 1:
        raise RuleError("중복된 World Format marker입니다.")
    return markers[0] if markers else None


def require_ready(audit):
    marker = _marker()
    try:
        valid_id = marker is not None and UUID(marker.db.world_id).hex == marker.db.world_id
    except (ValueError, TypeError, AttributeError):
        valid_id = False
    if (not valid_id or type(marker.db.version) is not int or marker.db.version != FORMAT_VERSION or marker.db.status != "ready"
            or not isinstance(marker, WorldFormat)):
        raise RuleError("지원하지 않거나 손상·미완료된 Actor World Format입니다.")
    from world.item_runtime import native_runtime

    if not native_runtime() or not callable(audit) or tuple(audit()):
        raise RuleError("World Format의 도메인 무결성 검증에 실패했습니다.")
    return marker


def initialize_world(build, audit):
    """초기화 전체가 하나의 변경 단위다. 재실행은 실제 무결성만 검사하고 상태를 덮지 않는다."""
    with world_change():
        if _marker() is not None:
            return require_ready(audit)
        assert_fresh()
        marker = create_script(WorldFormat)
        marker.db.version = FORMAT_VERSION
        marker.db.world_id = uuid4().hex
        marker.db.status = "initializing"
        build()
        marker.db.status = "ready"
        return require_ready(audit)
