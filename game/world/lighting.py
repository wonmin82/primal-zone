"""데이터 아이템 광원과 교체형 전원. 시각 투영은 읽기 전용이며 변경은 명령/생명주기가 소유한다."""

from copy import deepcopy
from math import ceil

from world.content import ITEMS
from world.rules import RuleError, consume, require_peace


def source_names():
    return [name for key, data in ITEMS.items() if data.get("light_source")
            for name in (key, data["name"], *data.get("aliases", []))]


def projected(profile, identity, now):
    state = deepcopy(profile.get("light_sources", {}).get(identity, {}))
    state.setdefault("on", False)
    state.setdefault("power_source", None)
    state.setdefault("charge_seconds", 0)
    state.setdefault("started_at", None)
    if state["on"] and state["started_at"] is not None:
        state["charge_seconds"] = max(0, state["charge_seconds"] - max(0, now - state["started_at"]))
        state["started_at"] = now
    if not profile["inventory"].get(identity, 0) or state["charge_seconds"] <= 0:
        state.update(on=False, power_source=None, charge_seconds=0, started_at=None)
    return state


def discard_device_state_if_unowned(profile, identity):
    """마지막 복사본의 소유권 상실을 확정한다. 시간 투영이나 다른 장치는 건드리지 않는다."""
    if profile["inventory"].get(identity, 0):
        return False
    return profile.get("light_sources", {}).pop(identity, None) is not None


def normalize(profile, now, *, turn_off=False):
    """잔량이 변했다는 이유로 매 tick 저장하지 않는다. 소진/소유권/꺼짐만 확정한다."""
    changed = False
    for identity, saved in list(profile.get("light_sources", {}).items()):
        current = projected(profile, identity, now)
        if turn_off and current["on"]:
            current.update(on=False, started_at=None)
        if not profile["inventory"].get(identity, 0):
            changed |= discard_device_state_if_unowned(profile, identity)
        elif (saved.get("on") and not current["on"]) or (
            saved.get("power_source") and not current["power_source"]
        ):
            profile["light_sources"][identity] = current
            changed = True
    return changed


def require_device(profile, identity):
    if not ITEMS[identity].get("light_source") or profile["inventory"].get(identity, 0) < 1:
        raise RuleError("소지품에 사용할 광원이 없습니다.")


def insert_power(profile, identity, power, now):
    require_peace(profile)
    require_device(profile, identity)
    metadata = ITEMS[power].get("power_source")
    if not metadata or metadata["type"] != ITEMS[identity]["light_source"]["power_type"]:
        raise RuleError(f"{ITEMS[identity]['name']}에는 그 전원 소스를 사용할 수 없습니다.")
    if projected(profile, identity, now)["charge_seconds"] > 0:
        raise RuleError("아직 사용할 수 있는 전원이 들어 있습니다. 모두 사용한 뒤 새 전원을 넣으세요.")
    consume(profile, power)
    profile.setdefault("light_sources", {})[identity] = {
        "on": False, "power_source": power,
        "charge_seconds": metadata["capacity_seconds"], "started_at": None,
    }


def switch(profile, identity, enabled, now):
    require_device(profile, identity)
    state = projected(profile, identity, now)
    if enabled and not state["power_source"]:
        raise RuleError("광원에 전원이 없습니다. '<광원>에 <전원 소스> 넣어'처럼 사용할 전원을 넣으세요.")
    if enabled:
        # 동시에 여러 광원을 켜는 정책은 도입하지 않는다.
        normalize(profile, now, turn_off=True)
    state.update(on=enabled, started_at=now if enabled else None)
    profile.setdefault("light_sources", {})[identity] = state


def display(profile, identity, now):
    state = projected(profile, identity, now)
    power = state["power_source"]
    return {
        "id": identity, "name": ITEMS[identity]["name"], "active": state["on"],
        "power_source": {"id": power, "name": ITEMS[power]["name"]} if power else None,
        "remaining_minutes": ceil(state["charge_seconds"] / 60),
    }


def active_source(profile, now):
    for identity in profile.get("light_sources", {}):
        if identity in ITEMS and ITEMS[identity].get("light_source") and projected(profile, identity, now)["on"]:
            return identity
    return None


def status(profile, identity, now):
    require_device(profile, identity)
    info = display(profile, identity, now)
    lines = [f"상태 {'켜짐' if info['active'] else '꺼짐'}",
             f"전원 {info['power_source']['name'] if info['power_source'] else '없음'}"]
    if info["power_source"]:
        lines.append(f"잔량 약 {info['remaining_minutes']}분")
    return "\n".join(lines)
