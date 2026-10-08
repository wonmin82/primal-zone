"""본부 공용 승강기의 정류 층과 표시명 SSOT."""

ELEVATOR_ROOM = "support_elevator"
ELEVATOR_STOPS = {
    "1f": {"label": "1층", "room": "hq_concourse"},
    "2f": {"label": "2층", "room": "support_2f_c"},
    "3f": {"label": "3층", "room": "support_3f_c"},
    "4f": {"label": "4층", "room": "support_4f_c"},
    "5f": {"label": "5층", "room": "support_5f_c"},
    "roof": {"label": "옥상", "room": "support_roof"},
}
ELEVATOR_DEFAULT_STOP = "1f"
