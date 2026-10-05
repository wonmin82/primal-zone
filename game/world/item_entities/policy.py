"""아이템 operation의 단일 판정. 알려지지 않은 행동은 기본 거절한다."""

from world.content import ITEMS


def can_item_operation(item, operation):
    identity = item if isinstance(item, str) else item.definition_id
    return ITEMS.get(identity, {}).get("operation_policy", {}).get(operation) is True


def definition_errors(identity, definition):
    issues = []
    for field in ("stackable", "unique_per_owner"):
        if type(definition.get(field)) is not bool:
            issues.append(f"{identity}: {field}는 참/거짓이어야 합니다.")
    maximum = definition.get("max_stack")
    if maximum is not None and (type(maximum) is not int or maximum < 1):
        issues.append(f"{identity}: max_stack은 None 또는 양의 정수여야 합니다.")
    if definition.get("unique_per_owner") and definition.get("stackable"):
        issues.append(f"{identity}: 소유자별 고유 아이템은 스택일 수 없습니다.")
    if not isinstance(definition.get("item_type"), str) or not definition["item_type"].strip():
        issues.append(f"{identity}: item_type이 비어 있습니다.")
    policy = definition.get("operation_policy")
    if not isinstance(policy, dict) or any(
        not isinstance(key, str) or not key.strip() or type(value) is not bool
        for key, value in (policy.items() if isinstance(policy, dict) else ())
    ):
        issues.append(f"{identity}: operation_policy는 행동별 참/거짓이어야 합니다.")
    return issues
