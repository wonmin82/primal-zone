"""아이템 operation의 단일 판정. 알려지지 않은 행동은 기본 거절한다."""

from world.content import ITEMS

# equip/unequip/load/unload는 root 행동이며 이전·처분은 내부 물품 보호도 검사한다.
# 새 행동은 policy 허용 여부와 함께 트리 적용 범위를 먼저 정의해야 한다.
TREE_OPERATION_SCOPES = {
    "equip": "root",
    "unequip": "root",
    "give": "tree",
    "drop": "tree",
    "store": "tree",
    "sell": "tree",
    "burn": "tree",
    "loot": "tree",
    "consume": "tree",
    "load": "root",
    "unload": "root",
}


def can_item_operation(item, operation):
    if not isinstance(operation, str) or operation not in TREE_OPERATION_SCOPES:
        return False
    identity = item if isinstance(item, str) else item.definition_id
    if (not isinstance(item, str) and operation in ("sell", "burn")
            and ITEMS.get(identity, {}).get("firearm_family")
            and item.children.filter(socket="magazine").exists()):
        return False
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
    from world.equipment import definition_errors as equipment_errors
    from world.item_states import definition_errors as state_errors

    if definition.get("item_type") == "credential":
        if (definition.get("stackable") is not False or definition.get("max_stack") != 1
                or definition.get("unique_per_owner") is not True):
            issues.append(f"{identity}: 출입증은 수량 1의 소유자별 고유 아이템이어야 합니다.")
        if not isinstance(policy, dict) or any(policy.get(key) is not (key == "burn")
                                               for key in TREE_OPERATION_SCOPES):
            issues.append(f"{identity}: 출입증은 소각만 허용합니다.")
        if not definition.get("credential_properties", {}).get("quest"):
            issues.append(f"{identity}: 출입증 재발급 임무가 필요합니다.")

    return issues + equipment_errors(identity, definition) + state_errors(identity, definition)
