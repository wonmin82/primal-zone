"""본부의 stable Room 구조. 서비스 존재는 실제 객체로 표현한다."""

from .directions import OPPOSITE_DIRECTIONS
from .elevator import ELEVATOR_ROOM, ELEVATOR_STOPS

ROOF_SIDES = {
    "북": "support_roof_n",
    "북동": "support_roof_ne",
    "동": "support_roof_e",
    "남동": "support_roof_se",
    "남": "support_roof_s",
    "남서": "support_roof_sw",
    "서": "support_roof_w",
    "북서": "support_roof_nw",
}
ROOF_ROOMS = {"support_roof", *ROOF_SIDES.values()}

ROOMS = {
    "staging_room": {
        "name": "출정 대기실",
        "desc": "출정을 기다리는 탐사자들을 위한 대기실이다. 벽을 따라 낡은 의자와 보급 상자가 놓여 있다.\n"
        "남쪽 문 너머로 본부의 분주한 소리가 들려온다.",
        "exits": {"남": "hq_concourse"},
    },
    "hq_concourse": {
        "name": "본부 중앙홀",
        "desc": "높은 천장 아래로 본부의 넓은 중앙홀이 펼쳐진다. 북쪽 문은 출정 대기실로 이어진다.\n"
        "서쪽 통로에서는 바닷바람이 들어오고, 남쪽으로는 지원동의 긴 복도가 이어진다.",
        "exits": {"북": "staging_room", "서": "dock", "남": "support_1f_c"},
    },
    "support_1f_w2": {
        "name": "지원동 1층 서쪽 끝 복도",
        "desc": "지원동 1층 복도가 서쪽 벽 앞에서 끝난다. 북쪽에는 넓은 업무 공간으로 통하는 문이 있다.",
        "exits": {"동": "support_1f_w1", "북": "salvage_office"},
        "blocked_exits": {"남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_1f_w1": {
        "name": "지원동 1층 서쪽 복도",
        "desc": "낡은 바닥 타일을 따라 지원동 1층의 복도가 동서로 이어진다. 북쪽 문에는 보관실 표지가 붙어 있다.",
        "exits": {"서": "support_1f_w2", "동": "support_1f_c", "북": "storage_room"},
        "blocked_exits": {"남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_1f_c": {
        "name": "지원동 1층 중앙 복도",
        "desc": "지원동 1층의 중앙에서 복도가 동서로 뻗어 있다. 북쪽 통로는 본부 중앙홀로 이어진다.",
        "exits": {"서": "support_1f_w1", "동": "support_1f_e1", "북": "hq_concourse"},
        "blocked_exits": {"남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_1f_e1": {
        "name": "지원동 1층 동쪽 복도",
        "desc": "지원동 1층의 복도가 동서로 길게 이어진다. 북쪽 문에는 보급품 상점 표지가 걸려 있다.",
        "exits": {"서": "support_1f_c", "동": "support_1f_e2", "북": "supply_shop"},
        "blocked_exits": {"남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_1f_e2": {
        "name": "지원동 1층 동쪽 끝 복도",
        "desc": "지원동 1층의 동쪽 끝이다. 동쪽 벽 앞에 오래된 안내판이 놓여 있다.",
        "exits": {"서": "support_1f_e1"},
        "blocked_exits": {"북": "북쪽 출입문은 현재 폐쇄되어 있다.", "남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_2f_w2": {
        "name": "지원동 2층 서쪽 끝 복도",
        "desc": "지원동 2층의 복도가 서쪽 벽에서 끝난다. 벽 아래로 오래된 배관이 이어진다.",
        "exits": {"동": "support_2f_w1"},
        "blocked_exits": {"북": "북쪽 출입문은 현재 폐쇄되어 있다.", "남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_2f_w1": {
        "name": "지원동 2층 서쪽 복도",
        "desc": "지원동 2층의 복도가 동서로 이어진다. 북쪽 문에는 의무실 표지가 붙어 있다.",
        "exits": {"서": "support_2f_w2", "동": "support_2f_c", "북": "infirmary"},
        "blocked_exits": {"남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_2f_c": {
        "name": "지원동 2층 중앙 복도",
        "desc": "지원동 2층의 중앙 복도다. 동쪽과 서쪽으로 난 복도가 비슷한 폭으로 이어진다.",
        "exits": {"서": "support_2f_w1", "동": "support_2f_e1"},
        "blocked_exits": {"북": "북쪽 출입문은 현재 폐쇄되어 있다.", "남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_2f_e1": {
        "name": "지원동 2층 동쪽 복도",
        "desc": "지원동 2층의 동쪽 복도다. 북쪽의 넓은 문에는 훈련실 표지가 걸려 있다.",
        "exits": {"서": "support_2f_c", "동": "support_2f_e2", "북": "training_room"},
        "blocked_exits": {"남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_2f_e2": {
        "name": "지원동 2층 동쪽 끝 복도",
        "desc": "지원동 2층의 복도가 동쪽 벽 앞에서 끝난다. 벽에는 지워진 안내문의 흔적이 남아 있다.",
        "exits": {"서": "support_2f_e1"},
        "blocked_exits": {"북": "북쪽 출입문은 현재 폐쇄되어 있다.", "남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_3f_w2": {
        "name": "지원동 3층 서쪽 끝 복도",
        "desc": "지원동 3층의 서쪽 끝이다. 낡은 걸레받이가 벽의 가장자리를 따라 이어진다.",
        "exits": {"동": "support_3f_w1"},
        "blocked_exits": {"북": "북쪽 출입문은 현재 폐쇄되어 있다.", "남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_3f_w1": {
        "name": "지원동 3층 서쪽 복도",
        "desc": "지원동 3층의 복도가 동서로 이어진다. 북쪽 문에는 방어구점 표지가 붙어 있다.",
        "exits": {"서": "support_3f_w2", "동": "support_3f_c", "북": "armor_shop"},
        "blocked_exits": {"남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_3f_c": {
        "name": "지원동 3층 중앙 복도",
        "desc": "지원동 3층의 중앙이다. 곧게 뻗은 복도가 동쪽과 서쪽으로 나뉜다.",
        "exits": {"서": "support_3f_w1", "동": "support_3f_e1"},
        "blocked_exits": {"북": "북쪽 출입문은 현재 폐쇄되어 있다.", "남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_3f_e1": {
        "name": "지원동 3층 동쪽 복도",
        "desc": "지원동 3층의 동쪽 복도다. 북쪽 문에는 무기점 표지가 걸려 있다.",
        "exits": {"서": "support_3f_c", "동": "support_3f_e2", "북": "weapon_shop"},
        "blocked_exits": {"남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "support_3f_e2": {
        "name": "지원동 3층 동쪽 끝 복도",
        "desc": "지원동 3층의 복도가 동쪽 벽에서 끝난다. 벽을 따라 가느다란 균열이 남아 있다.",
        "exits": {"서": "support_3f_e1"},
        "blocked_exits": {"북": "북쪽 출입문은 현재 폐쇄되어 있다.", "남": "남쪽 출입문은 현재 폐쇄되어 있다."},
    },
    "salvage_office": {
        "name": "자원 정산소",
        "hints": [{"target": "salvage_officer", "action": "환율"}],
        "desc": "넓은 작업대와 비어 있는 금속 선반이 놓인 업무 공간이다. 남쪽 문은 1층 복도로 이어진다.",
        "exits": {"남": "support_1f_w2"},
    },
    "storage_room": {
        "name": "보관실",
        "desc": "두꺼운 벽으로 둘러싸인 보관 공간이다. 벽을 따라 빈 선반이 줄지어 있고 남쪽으로 문이 나 있다.",
        "exits": {"남": "support_1f_w1"},
    },
    "supply_shop": {
        "name": "보급품 상점",
        "hints": [{"target": "supply_shopkeeper", "action": "상품"}],
        "desc": "낮은 진열대와 비어 있는 판매대가 놓인 공간이다. 남쪽 문 너머로 1층 복도가 이어진다.",
        "exits": {"남": "support_1f_e1"},
    },
    "infirmary": {
        "name": "의무실",
        "desc": "밝은 타일로 마감된 넓은 공간이다. 벽의 수납장은 비어 있고 남쪽 문은 2층 복도로 이어진다.",
        "exits": {"남": "support_2f_w1"},
        "hints": [{"target": "doctor", "action": "진료"}, {"target": "infirmary_bed", "action": "휴식"}],
    },
    "training_room": {
        "name": "훈련실",
        "desc": "단단한 바닥에 옛 훈련 구획의 선이 남아 있다. 남쪽 문 너머로 2층 복도가 보인다.",
        "exits": {"남": "support_2f_e1"},
    },
    "armor_shop": {
        "name": "방어구점",
        "hints": [{"target": "armor_shopkeeper", "action": "상품"}],
        "desc": "빈 진열대가 벽을 따라 놓여 있다. 남쪽 출입문은 지원동 3층의 서쪽 복도로 이어진다.",
        "exits": {"남": "support_3f_w1"},
    },
    "weapon_shop": {
        "name": "무기점",
        "hints": [{"target": "weapon_shopkeeper", "action": "상품"}],
        "desc": "튼튼한 판매대와 비어 있는 장비 걸이가 놓인 공간이다. 남쪽 문은 3층의 동쪽 복도로 이어진다.",
        "exits": {"남": "support_3f_e1"},
    },
    "support_roof": {
        "name": "지원동 옥상",
        "desc": "콘크리트 난간이 지원동의 옥상을 둘러싸고 있다. 낡은 바닥 너머로 본부의 지붕과 섬의 숲이 보인다.",
        "exits": dict(ROOF_SIDES),
    },
    ELEVATOR_ROOM: {
        "name": "지원동 승강기",
        "desc": "금속 벽으로 둘러싸인 승강기다. 조작반에는 "
        + ", ".join(stop["label"] for stop in ELEVATOR_STOPS.values()) + " 버튼이 있다.",
        "exits": {},
    },
}

for zone, name, corridor, description in (
    ("tactics_room", "전술훈련실", "support_2f_w2", "모래판과 낡은 지형 모형이 낮은 탁자 위에 놓여 있다. 벽에 걸린 표적에는 전술 연습의 흔적이 남아 있다."),
    ("training_office", "훈련관리실", "support_2f_c", "훈련 기록과 빈 신청서가 책상 위에 정돈되어 있다. 벽의 안내판에는 훈련 일정이 붙어 있다."),
    ("shooting_range", "사격장", "support_2f_e2", "두꺼운 방음벽 안쪽으로 사격선과 표적이 나란히 놓여 있다. 모래를 채운 둔덕이 표적 뒤를 막고 있다."),
):
    ROOMS[zone] = {"name": name, "desc": description + " 북쪽 문은 지원동 2층 복도로 이어진다.", "exits": {"북": corridor}}
    ROOMS[corridor]["desc"] += f" 남쪽 문에는 {name} 표지가 붙어 있다."
    ROOMS[corridor]["exits"]["남"] = zone
    ROOMS[corridor]["blocked_exits"].pop("남")


for direction, name, desc in (
    ("북", "북쪽 전망 구역", "난간 너머로 본부 진입로가 내려다보인다. 바닥의 마모된 선을 따라 옥상 중앙으로 돌아갈 수 있다."),
    ("북동", "북동쪽 설비 구역", "낡은 설비 덮개가 콘크리트 받침 위에 놓여 있다. 배관 사이로 옥상 중앙이 보인다."),
    ("동", "동쪽 난간", "높은 난간 너머로 숲의 가장자리가 펼쳐진다. 탁 트인 바닥이 옥상 중앙으로 이어진다."),
    ("남동", "남동쪽 급수 설비", "두꺼운 급수관이 물탱크 아래로 이어진다. 설비 옆의 넓은 공간을 통해 중앙으로 돌아갈 수 있다."),
    ("남", "남쪽 전망 구역", "섬의 남쪽 수평선이 본부 지붕 너머로 보인다. 옥상 중앙까지 평평한 바닥이 이어진다."),
    ("남서", "남서쪽 환기 구역", "금속 환기구가 낮은 받침 위에 줄지어 있다. 그 사이로 중앙에 이르는 빈 공간이 남아 있다."),
    ("서", "서쪽 난간", "난간 아래로 부두의 윤곽이 보인다. 낡은 바닥을 따라 옥상 중앙으로 돌아갈 수 있다."),
    ("북서", "북서쪽 통신 설비", "짧은 안테나와 밀폐된 통신함이 놓여 있다. 케이블 덮개 옆으로 중앙에 이르는 공간이 열려 있다."),
):
    ROOMS[ROOF_SIDES[direction]] = {
        "name": name, "desc": desc,
        "exits": {OPPOSITE_DIRECTIONS[direction]: "support_roof"},
    }

# 진행 권한과 가용성은 공간에만 둔다. 남쪽 예약 시설도 실제 목적지를 갖는다.
for zone, name, corridor, direction, credential, available in (
    ("outpost_equipment", "전초 장비고", "support_3f_w2", "북", "outpost_supply_pass", True),
    ("outpost_weapon", "전초 병기고", "support_3f_e2", "북", "outpost_supply_pass", True),
    ("reserved_equipment", "다음 단계 장비고", "support_3f_w2", "남", "special_supply_pass", False),
    ("reserved_weapon", "다음 단계 병기고", "support_3f_e2", "남", "special_supply_pass", False),
):
    ROOMS[zone] = {"name": name, "desc": f"{name}의 출입문 너머로 장비 보급 시설이 보인다.",
                   "exits": {OPPOSITE_DIRECTIONS[direction]: corridor},
                   "access": {"available": available, "credential": credential}}
    ROOMS[corridor]["exits"][direction] = zone
    ROOMS[corridor]["blocked_exits"].pop(direction)
    ROOMS[corridor]["desc"] += f" {direction}쪽에는 {name} 출입문이 있다."
ROOMS["armor_shop"]["name"] = "3F 서쪽 기본 장비점"
ROOMS["weapon_shop"]["name"] = "3F 동쪽 기본 병기점"
ROOMS["supply_shop"]["name"] = "1F 보급품 상점"
ROOMS["outpost_equipment"]["hints"] = [{"target": "outpost_equipment_shopkeeper", "action": "상품"}]
ROOMS["outpost_weapon"]["hints"] = [{"target": "outpost_weapon_shopkeeper", "action": "상품"}]

for room in ROOMS.values():
    room.update(safe=True, enemies=[], exposure="indoor", light_profile="artificial")
for zone in ROOF_ROOMS:
    ROOMS[zone].update(exposure="outdoor", light_profile="natural")
    ROOMS[zone]["recovery"] = {"mental_per_minute": 2}

ROOMS["infirmary"]["recovery"] = {"hp_per_minute": 6, "mental_per_minute": 2}
ROOMS["hq_concourse"]["recovery"] = {"hp_per_minute": 2, "mental_per_minute": 2}
