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
        result["shares"] = {int(key): value for key, value in result.get("shares", {}).items()}
    return result


def asset_name(entry):
    return CURRENCY["name"] if entry["kind"] == "currency" else ITEMS[entry["id"]]["name"]


def asset_text(entry):
    return (ft.token("reward", format_currency(entry["quantity"]))
            if entry["kind"] == "currency" else ft.text(ft.item(entry["id"]), f" ×{entry['quantity']}"))
