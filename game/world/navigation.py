"""임무 기반 진입 조건의 읽기 전용 판정. 이동과 관찰은 차단 결과를 따로 사용한다."""

from world.content import ROOMS


def entry_block(profile, destination_zone):
    requirement = ROOMS.get(destination_zone, {}).get("requires")
    if requirement and not profile.get("quests", {}).get(requirement["quest"], {}).get(
        requirement["flag"], False
    ):
        return requirement
    return None
