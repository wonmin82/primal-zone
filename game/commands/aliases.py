"""게임이 제공하는 고정 단축어. 개인 줄임말과 별개의 입력 SSOT."""

from world.content.directions import DIRECTION_SHORTCUTS

INFORMATION_SHORTCUTS = {"상": "점수", "능": "능력", "기": "기술", "장": "장비", "소": "가진거"}
LOOT_SHORTCUTS = {"시": "시체에서 모두 가져", **{f"시{i}": f"시체 {i}에서 모두 가져" for i in range(2, 6)}}
SHORTCUTS = {**DIRECTION_SHORTCUTS, **INFORMATION_SHORTCUTS, **LOOT_SHORTCUTS}

# 테스트·내부 인자형 전역 정의 기반. 기본 글로벌 입력의 SSOT는 SHORTCUTS 그대로다.
ARGUMENT_SHORTCUTS = {}
