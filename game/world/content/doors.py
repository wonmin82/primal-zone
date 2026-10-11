"""Issue #49 고정 문 정의. 실제 상태와 설치 시각은 DB가 소유한다."""

DOORS = {
    "hq_admin_door": {
        "name": "관리실 문", "aliases": ["관리실문"],
        "endpoints": (("hq_concourse", "동", "hq_admin_office"), ("hq_admin_office", "서", "hq_concourse")),
        "initial_state": "LOCKED", "lockable": True,
        "key_id": "hq_admin_key", "inside_room_id": "hq_admin_office",
    },
    "recovery_room_door": {
        "name": "회복실 문", "aliases": ["회복실문"],
        "endpoints": (("support_3f_e1", "북", "recovery_room"), ("recovery_room", "남", "support_3f_e1")),
        "initial_state": "OPEN", "lockable": False, "key_id": "", "inside_room_id": "",
    },
}

AUTO_CLOSE_SECONDS = 60
