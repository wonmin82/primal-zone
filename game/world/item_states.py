"""상태·중첩 아이템의 순수 정의 및 저장 검증. 영속 계층은 오류 목록을 사용한다."""

from math import isfinite

FIREARM_FAMILIES = {"pistol_9mm": "9mm", "carbine_556": "556mm", "rifle_762": "762mm"}
POWER_TYPES = {"flashlight_battery"}


def number(value):
    return type(value) in (int, float) and isfinite(value)


def default_state(definition):
    if definition.get("light_source"):
        return {"power_type": definition["light_source"].get("power_type"),
                "remaining_power": 0, "enabled": False, "started_at": None}
    if definition.get("magazine"):
        return {"rounds": 0}
    return {}


def definition_errors(identity, definition):
    errors = []
    family = definition.get("firearm_family")
    if family is not None:
        from world.equipment import definition_parts

        properties, _ = definition_parts(identity, definition)
        if not isinstance(family, str) or family not in FIREARM_FAMILIES or not isinstance(properties, dict) or properties.get("weapon_type") != "firearm":
            errors.append("총기 family 또는 weapon_type이 올바르지 않습니다.")
    magazine = definition.get("magazine")
    if magazine is not None:
        if (not isinstance(magazine, dict) or not isinstance(magazine.get("family"), str)
                or magazine.get("family") not in FIREARM_FAMILIES
                or FIREARM_FAMILIES.get(magazine.get("family")) != magazine.get("ammo_type")
                or type(magazine.get("capacity")) is not int or magazine["capacity"] <= 0
                or definition.get("stackable") is not False):
            errors.append("탄창 family·탄종·용량·비스택 정의를 확인하세요.")
    if "ammo_type" in definition and (not isinstance(definition["ammo_type"], str)
                                      or definition["ammo_type"] not in FIREARM_FAMILIES.values()
                                      or definition.get("stackable") is not True):
        errors.append("탄약은 등록된 탄종의 스택이어야 합니다.")
    light = definition.get("light_source")
    if light is not None and (not isinstance(light, dict) or not isinstance(light.get("power_type"), str)
                  or light.get("power_type") not in POWER_TYPES or definition.get("stackable") is not False
                  or not number(light.get("max_power_seconds", 1800)) or light.get("max_power_seconds", 1800) <= 0):
        errors.append("휴대 광원의 전원 종류·비스택 정의를 확인하세요.")
    return [f"{identity}: {error}" for error in errors]


def state_errors(definition, state):
    errors = []
    if definition.get("light_source"):
        power, started = state.get("remaining_power"), state.get("started_at")
        if (state.get("power_type") != definition["light_source"]["power_type"]
                or not number(power) or not 0 <= power <= definition["light_source"].get("max_power_seconds", 1800)
                or type(state.get("enabled")) is not bool
                or (started is not None and not number(started))
                or (state.get("enabled") and (not number(power) or power <= 0 or started is None))
                or (not state.get("enabled") and started is not None)):
            errors.append("광원 전원·잔량(초)·켜짐·시작 시각이 올바르지 않습니다.")
    if definition.get("magazine"):
        rounds = state.get("rounds")
        if type(rounds) is not int or not 0 <= rounds <= definition["magazine"]["capacity"]:
            errors.append("탄창 잔탄은 용량 이내의 0 이상 정수여야 합니다.")
    if definition.get("firearm_family") and any(key in state for key in ("rounds", "ammo_count")):
        errors.append("총기의 잔탄은 삽입된 탄창에만 저장합니다.")
    return errors
