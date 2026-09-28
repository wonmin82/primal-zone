"""임무 기반 진입 조건의 읽기 전용 판정. 이동과 관찰은 차단 결과를 따로 사용한다."""

from world.content import OPPOSITES, ROOMS


def blocked_exit_message(zone, direction):
    """폐쇄 방향은 목적지 없이 콘텐츠 문구만 반환한다. 실제 출구 alias를 재사용한다."""
    direction = direction.strip().lower()
    for key, message in ROOMS.get(zone, {}).get("blocked_exits", {}).items():
        if direction in (key, OPPOSITES.get(key)):
            return message
    return None


def entry_block(profile, destination_zone):
    requirement = ROOMS.get(destination_zone, {}).get("requires")
    if requirement and not profile.get("quests", {}).get(requirement["quest"], {}).get(
        requirement["flag"], False
    ):
        return requirement
    return None
