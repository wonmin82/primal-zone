"""소유권이 필요한 복합 아이템 동작의 공통 owner → UUID lock 경계."""

from django.core.exceptions import ValidationError
from evennia.objects.models import ObjectDB

from world import rules
from world.item_entities import api
from world.item_entities.models import ItemEntity


def lock_character_items(character, extra=()):
    """world_change 내부에서만 사용한다. 빈 inventory/socket 경쟁도 owner lock으로 보호한다."""
    ObjectDB.objects.select_for_update().get(pk=character.pk)
    ids = api.items_owned_by(character).values_list("pk", flat=True)
    return {row.pk: row for row in api.lock_items([*ids, *extra])}


def require_native(character):
    from world.equipment_service import entity_runtime

    if not entity_runtime(character):
        raise rules.RuleError("이 동작은 ItemEntity 아이템에서 지원합니다. 기존 아이템 변환은 Phase 6 대상입니다.")


def carried(character, row, *, inside=False):
    root = row.root()
    if root.owner_object_id != character.pk or root.location_kind not in ("inventory", "equipment"):
        raise rules.RuleError("자신이 소지한 아이템만 사용할 수 있습니다.")
    if not inside and row.location_kind not in ("inventory", "equipment"):
        raise rules.RuleError("직접 소지한 아이템을 선택하세요.")


def selected(locked, item):
    try:
        return locked[api.item_id(item)]
    except (KeyError, ItemEntity.DoesNotExist):
        raise rules.RuleError("자신이 소지한 아이템을 다시 선택하세요.") from None


def domain_errors(function):
    """저장 검증 실패를 명령이 표시할 domain 오류로 변환한다."""
    from functools import wraps

    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValidationError as error:
            raise rules.RuleError(" / ".join(error.messages)) from error
    return wrapped
