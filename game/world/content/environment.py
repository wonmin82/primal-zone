"""시간·기상·빛의 선언형 콘텐츠. 지속 시간은 현실 초 단위다."""

WORLD_TIME_SCALE = 4
INITIAL_GAME_SECONDS = 8 * 3600
PERIODS = {
    "night": {"name": "밤", "light": 0, "sentence": "밤의 어둠이 주변을 덮고 있다."},
    "dawn": {"name": "새벽", "light": 2, "sentence": "새벽빛이 주변으로 번지고 있다."},
    "day": {"name": "낮", "light": 4, "sentence": "낮빛이 주변을 밝히고 있다."},
    "dusk": {"name": "해질녘", "light": 2, "sentence": "해가 기울어 주변이 어스름해진다."},
}
PERIOD_BOUNDARIES = ((0, "night"), (5, "dawn"), (7, "day"), (18, "dusk"), (20, "night"))
MOON_CYCLE_DAYS = 28
MOONS = {
    "new": {"name": "삭", "light": 0},
    "quarter": {"name": "반달", "light": 1},
    "full": {"name": "보름달", "light": 2},
}
EXPOSURES = {"outdoor", "sheltered", "indoor"}
LIGHT_PROFILES = {
    "natural": {"offset": 0},
    "filtered": {"offset": -1},
    "dim": {"fixed": 1},
    "artificial": {"fixed": 3},
}
LIGHT_GRADES = {"bright": "밝음", "normal": "보통", "dim": "어스름", "dark": "어두움"}
VISIBILITIES = {"clear": "좋음", "reduced": "보통", "poor": "나쁨"}
WEATHER_ZONES = {"island": {"name": "탐사 섬", "initial": "clear"}}
WEATHERS = {
    "clear": {
        "name": "맑음",
        "light_modifier": 0,
        "visibility": 0,
        "duration": (1200, 2400),
        "transitions": {"clear": 2, "cloudy": 5, "fog": 1},
        "presence": {
            "outdoor": "하늘이 맑게 개어 있다.",
            "sheltered": "덮개 너머로 맑은 하늘이 보인다.",
            "indoor": "바깥 공기가 잔잔하다.",
        },
    },
    "cloudy": {
        "name": "흐림",
        "light_modifier": -1,
        "visibility": 0,
        "duration": (900, 1800),
        "transitions": {"clear": 3, "cloudy": 2, "rain": 4},
        "presence": {
            "outdoor": "두터운 구름이 하늘을 덮고 있다.",
            "sheltered": "덮개 너머로 흐린 하늘이 보인다.",
            "indoor": "바깥의 흐린 빛이 희미하게 스며든다.",
        },
    },
    "rain": {
        "name": "비",
        "light_modifier": -1,
        "visibility": 1,
        "duration": (600, 1500),
        "transitions": {"cloudy": 4, "rain": 3, "storm": 1},
        "presence": {
            "outdoor": "가느다란 비가 주변을 적시고 있다.",
            "sheltered": "지붕과 나뭇잎 위로 빗소리가 이어진다.",
            "indoor": "바깥에서 빗소리가 희미하게 들려온다.",
        },
    },
    "storm": {
        "name": "폭우",
        "light_modifier": -2,
        "visibility": 2,
        "duration": (300, 900),
        "transitions": {"rain": 5, "cloudy": 1},
        "presence": {
            "outdoor": "거센 빗줄기가 주변을 세차게 두드린다.",
            "sheltered": "덮개 위로 쏟아지는 빗소리가 요란하다.",
            "indoor": "바깥에서 거센 빗소리가 울려온다.",
        },
    },
    "fog": {
        "name": "안개",
        "light_modifier": -1,
        "visibility": 2,
        "duration": (600, 1500),
        "transitions": {"fog": 2, "cloudy": 3, "clear": 3},
        "presence": {
            "outdoor": "낮게 깔린 안개가 주변을 감싼다.",
            "sheltered": "덮개 밖으로 안개가 낮게 흐른다.",
            "indoor": "바깥 풍경이 안개 속에 흐릿하다.",
        },
    },
}
