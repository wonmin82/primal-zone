"""시계방향 순서·영문 별칭·반대 방향·3×3 좌표의 단일 정의."""

DIRECTIONS = {
    "북": {"alias": "n", "opposite": "남", "row": 0, "column": 1},
    "북동": {"alias": "ne", "opposite": "남서", "row": 0, "column": 2},
    "동": {"alias": "e", "opposite": "서", "row": 1, "column": 2},
    "남동": {"alias": "se", "opposite": "북서", "row": 2, "column": 2},
    "남": {"alias": "s", "opposite": "북", "row": 2, "column": 1},
    "남서": {"alias": "sw", "opposite": "북동", "row": 2, "column": 0},
    "서": {"alias": "w", "opposite": "동", "row": 1, "column": 0},
    "북서": {"alias": "nw", "opposite": "남동", "row": 0, "column": 0},
}
DIRECTION_ORDER = tuple(DIRECTIONS)
DIRECTION_ALIASES = {key: data["alias"] for key, data in DIRECTIONS.items()}
OPPOSITE_DIRECTIONS = {key: data["opposite"] for key, data in DIRECTIONS.items()}


def ordered_directions(values):
    """정식 방향은 시계방향, 기타 출구는 원래 순서를 유지한다."""
    return [key for key in DIRECTION_ORDER if key in values] + [key for key in values if key not in DIRECTIONS]
