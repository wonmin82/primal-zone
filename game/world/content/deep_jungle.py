"""두 번째 탐사 지역: 깊은 밀림."""

from world.actors.hostile_content import enemy_view

ENEMIES = enemy_view(('dartclaw', 'shellback', 'stalker', 'jungle_apex'))

ROOMS = {
    "jungle_edge": {
        "name": "밀림 입구",
        "exposure": "outdoor",
        "light_profile": "filtered",
        "enemies": ["dartclaw"],
        "desc": "통신탑 뒤편 길이 빽빽한 밀림으로 이어진다. 선발대가 남긴 발자국이 젖은 흙 위에 남아 있다.",
        "hints": [{"target": "pathfinder", "intent": "greeting"}],
        "exits": {"남": "ridge", "북": "jungle_watch", "동": "jungle_road", "서": "jungle_fen"},
        "requires": {
            "quest": "radio_tower",
            "flag": "claimed",
            "message": "먼저 통신탑 복구 임무를 마치고 윤대장에게 보고하세요.",
            "observe_message": "이어지는 길 너머는 아직 자세히 살펴볼 수 없다.",
        },
    },
    "jungle_watch": {
        "name": "버려진 관측소",
        "exposure": "sheltered",
        "light_profile": "natural",
        "enemies": ["dartclaw"],
        "desc": "나무 위 관측소가 덩굴에 뒤덮인 채 기울어 있다. 무너진 난간 사이로 주변 밀림이 내려다보인다.",
        "hints": [{"target": "watch_marker", "action": "조사"}],
        "exits": {"남": "jungle_edge", "동": "jungle_grove"},
    },
    "jungle_road": {
        "name": "수몰된 도로",
        "exposure": "outdoor",
        "light_profile": "natural",
        "enemies": ["shellback"],
        "desc": "옛 도로가 검은 물 아래로 반쯤 잠겨 있다. 갈라진 노면 사이로 물풀과 진흙이 쌓여 있다.",
        "hints": [{"target": "water_marker", "action": "조사"}],
        "exits": {"서": "jungle_edge", "북": "jungle_grove"},
    },
    "jungle_fen": {
        "name": "늪지 샛길",
        "exposure": "outdoor",
        "light_profile": "filtered",
        "enemies": ["stalker"],
        "desc": "검은 물 사이로 좁은 진흙길이 갈라진다. 썩은 나무뿌리와 물풀이 물가를 뒤덮고 있다.",
        "hints": [{"target": "jungle_cache", "action": "조사"}],
        "exits": {"동": "jungle_edge"},
    },
    "jungle_grove": {
        "name": "거목 군락",
        "exposure": "outdoor",
        "light_profile": "filtered",
        "enemies": ["shellback", "stalker"],
        "desc": "거목 뿌리 사이에서 관측소와 도로의 흔적이 만난다. 숲 안쪽으로 이어지는 문틀에는 덩굴과 녹이 깊이 엉겨 있다.",
        "hints": [{"target": "signal_device", "action": "조사"}],
        "exits": {"서": "jungle_watch", "남": "jungle_road", "북": "jungle_gate"},
    },
    "jungle_gate": {
        "name": "연구구역 외곽",
        "exposure": "outdoor",
        "light_profile": "natural",
        "enemies": ["stalker"],
        "desc": "낡은 문 너머로 무너진 연구시설의 외벽이 이어진다. 숲 안쪽에는 부러진 나무와 깊게 패인 흙길이 남아 있다.",
        "hints": [{"text": "둥지로 들어가기 전 장비와 붕대를 확인하자."}],
        "exits": {"남": "jungle_grove", "북": "jungle_nest"},
        "requires": {
            "quest": "deep_jungle",
            "flag": "gate_open",
            "message": "연구구역 문이 닫혀 있습니다. 두 탐사 표식을 확인하고 거목의 신호 장치를 조사하세요.",
            "observe_message": "난 길은 닫힌 출입문에 막혀 있다.",
        },
    },
    "jungle_nest": {
        "name": "포식자 둥지",
        "exposure": "sheltered",
        "light_profile": "filtered",
        "enemies": ["jungle_apex"],
        "desc": "휘어진 나무 아래에 거대한 둥지가 있다. 바닥에는 오래된 탐사대 장비가 흩어져 있다.",
        "hints": [{"text": "포식자가 숨을 고르면 견제와 치료를 준비하자."}],
        "exits": {"남": "jungle_gate"},
    },
}
