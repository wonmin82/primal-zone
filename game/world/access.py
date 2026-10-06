"""실제 출입증과 콘텐츠 가용성의 공통 읽기 전용 접근 경계."""

from world.content import ROOMS
from world.navigation import entry_block


def entry_message(character, destination):
    from world.credential_service import has_credential

    zone = destination if isinstance(destination, str) else destination.db.zone_id
    room = ROOMS.get(zone, {})
    access = room.get("access", {})
    credential = access.get("credential")
    if access.get("available") is False:
        if credential and has_credential(character, credential):
            return "출입 권한은 확인되지만 시설은 아직 폐쇄되어 있다."
        return "시설은 아직 폐쇄되어 있다."
    if credential and not has_credential(character, credential):
        from world.content import ITEMS

        return f"{ITEMS[credential]['name']}이 있어야 들어갈 수 있습니다."
    requirement = entry_block(character.profile_snapshot(), zone)
    return requirement["message"] if requirement else None


def can_enter(character, destination):
    return entry_message(character, destination) is None
