"""월드 전리품의 읽기 전용 호환 계층. legacy item entry도 같은 asset으로 읽는다."""

from copy import deepcopy

from world import text as ft
from world.content import ITEMS
from world.content.economy import CURRENCY
from world.currency import format_currency


def normalize_entry(entry):
    result = deepcopy(dict(entry))
    result.setdefault("kind", "item")
    result.setdefault("id", result.get("item"))
    result.pop("item", None)
    for field in ("reserved_party", "reserved_player", "assigned_player"):
        result.setdefault(field, None)
    result.setdefault("protection_until", 0)
    if result["kind"] == "currency":
        # PR 초기 shares는 당시 남아 있던 키로만 자격을 복원할 수 있다.
        legacy = result.pop("shares", {})
        remaining = result.get("remaining_shares", legacy)
        result["remaining_shares"] = {int(key): value for key, value in remaining.items() if value > 0}
        result["eligible_players"] = sorted({int(key) for key in result.get("eligible_players", legacy or remaining)})
    return result


def currency_payouts(entry, amount, caller_id, now):
    """트리거 자격과 별개로, 아직 지급할 몫만 금액 배분의 weight로 사용한다."""
    from world import rules

    entry = normalize_entry(entry)
    if type(amount) is not int or amount <= 0 or amount > entry["quantity"]:
        raise rules.RuleError("선택한 전리품의 보급칩이 부족합니다.")
    if now >= entry["protection_until"]:
        return {caller_id: amount}
    shares = entry["remaining_shares"]
    if sum(shares.values()) != entry["quantity"]:
        raise rules.RuleError("보급칩 분배 권리를 확인할 수 없습니다.")
    return rules.weighted_split(amount, shares)


def asset_name(entry):
    return CURRENCY["name"] if entry["kind"] == "currency" else ITEMS[entry["id"]]["name"]


def asset_text(entry):
    return (ft.token("reward", format_currency(entry["quantity"]))
            if entry["kind"] == "currency" else ft.text(ft.item(entry["id"]), f" ×{entry['quantity']}"))
