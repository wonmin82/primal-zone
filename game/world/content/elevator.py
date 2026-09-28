"""지원동 공용 승강기의 정류 층과 표시명 SSOT."""

ELEVATOR_ROOM = "support_elevator"
ELEVATOR_STOPS = {
    "1f": {"label": "1층", "room": "support_1f_c"},
    "2f": {"label": "2층", "room": "support_2f_c"},
    "3f": {"label": "3층", "room": "support_3f_c"},
    "roof": {"label": "옥상", "room": "support_roof"},
}
ELEVATOR_DEFAULT_STOP = "1f"
