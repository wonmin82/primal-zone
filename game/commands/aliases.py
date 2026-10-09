"""게임이 제공하는 고정 단축어. 개인 줄임말과 별개의 입력 SSOT."""

from world.content.directions import DIRECTION_SHORTCUTS

INFORMATION_SHORTCUTS = {"상": "상태", "능": "능력", "기": "기술", "장": "장비", "소": "소지품"}
SHORTCUTS = {**DIRECTION_SHORTCUTS, **INFORMATION_SHORTCUTS}

# 테스트·내부 인자형 전역 정의 기반. 기본 글로벌 입력의 SSOT는 SHORTCUTS 그대로다.
ARGUMENT_SHORTCUTS = {}
