"""개인 관리실 열쇠의 실제 Entity 검증과 무료 발급."""

from django.core.exceptions import ValidationError

from world import rules
from world import text as ft
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.multiplayer import after_change, world_change

KEY_ID = "hq_admin_key"


def owned_key(caller):
    # 고유 범위가 잘못 기록된 열쇠도 정상 부재로 해석해 복제하지 않는다.
    scope = f"{caller.pk}:{KEY_ID}"
    rows = []
    for candidate in ItemEntity.objects.filter(definition_id=KEY_ID):
        direct = candidate.owner_object_id == caller.pk or candidate.unique_scope_key == scope
        try:
            related = candidate.root().owner_object_id == caller.pk
        except ValidationError:
            if direct:
                raise rules.RuleError("열쇠 소유 상태를 확인할 수 없습니다. 관리자에게 문의하세요.") from None
            continue
        if direct or related:
            rows.append(candidate)
    if not rows:
        return None
    if len(rows) != 1:
        raise rules.RuleError("열쇠 소유 상태를 확인할 수 없습니다. 관리자에게 문의하세요.")
    key = rows[0]
    try:
        key.full_clean()
    except ValidationError:
        raise rules.RuleError("열쇠 소유 상태를 확인할 수 없습니다. 관리자에게 문의하세요.") from None
    if key.owner_object_id != caller.pk or key.unique_scope_key != scope or key.location_kind != "inventory":
        raise rules.RuleError("열쇠 소유 상태를 확인할 수 없습니다. 관리자에게 문의하세요.")
    return key


def issue_key(caller, cabinet):
    from world.equipment_service import entity_runtime
    from world.observation import can_perceive, context_for
    with world_change():
        rules.require_peace(caller.profile_snapshot())
        if cabinet.location != caller.location or not can_perceive(cabinet, context_for(caller)):
            raise rules.RuleError("이곳에서 열쇠함을 조사할 수 없습니다.")
        if not entity_runtime(caller):
            raise rules.RuleError("소지품 변환 상태를 확인해야 합니다. 관리자에게 문의하세요.")
        if owned_key(caller):
            raise rules.RuleError("이미 관리실 열쇠를 가지고 있습니다.")
        key = api.create_item(KEY_ID, location_kind="inventory", owner_object=caller)
        message = ft.text(ft.item(KEY_ID), "를 열쇠함에서 꺼내 챙겼다.")
        after_change(lambda: caller.msg(message))
        after_change(caller.push_state)
        return key
