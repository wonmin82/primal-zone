"""DB 비의존 시설 저장 형식. 조회용 정규화는 원본을 변경하지 않는다."""

from copy import deepcopy

from world.content.facilities import FACILITIES

FACILITY_STATE_VERSION = 1


def new_facility_state():
    return {
        "version": FACILITY_STATE_VERSION,
        "states": {identity: definition["default"] for identity, definition in FACILITIES.items()},
    }


def normalize_facility_state(state):
    if state is None:
        return new_facility_state()
    version = state.get("version", 0)
    if type(version) is not int or not 0 <= version <= FACILITY_STATE_VERSION:
        raise ValueError(f"지원하지 않는 시설 저장 버전입니다: {version!r}")
    values = state if version == 0 else state["states"]
    result = new_facility_state()
    # 알 수 없는 기존 ID도 보존한다. 현재 조명은 선언된 ID만 참조한다.
    result["states"].update(deepcopy(values))
    if any(type(value) is not bool for value in result["states"].values()):
        raise ValueError("시설 상태는 참/거짓 값이어야 합니다.")
    return result
