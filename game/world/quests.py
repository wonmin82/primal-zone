"""지역 임무의 저장 필드와 표시 순서. 조건식 언어 대신 명시적 진행 상태를 쓴다."""

QUESTS = {
    "radio_tower": {
        "name": "통신탑 복구",
        "visible_from_start": True,
        "steps": (
            ("started", "commander", "npc", "에게 임무 수령"),
            ("record_read", "maintenance_log", "object", " 확인"),
            ("generator_fixed", "generator", "object", " 복구"),
            ("boss_defeated", "alpha", "hostile", " 처치"),
            ("claimed", "commander", "npc", "에게 보고"),
        ),
        "hints": (
            "부두에서 '윤대장 대화'로 임무를 받으세요.",
            "관리동에서 '정비기록 조사'. 사냥으로 장비와 회수부품 3개를 준비하세요.",
            "회수부품 3개를 모아 발전실에서 '발전기 수리'.",
            "능선의 우두머리를 처치하세요. 강화 장비와 붕대를 권장합니다.",
            "부두로 귀환하여 '윤대장 대화'로 보상을 받으세요.",
            "통신탑 복구 완료 · 첫 탐사를 완수했습니다.",
        ),
    },
    "deep_jungle": {
        "name": "깊은 밀림 조사",
        "requires": ("radio_tower", "claimed"),
        "steps": (
            ("started", "pathfinder", "npc", "에게 탐사 의뢰"),
            ("watch_marked", "watch_marker", "object", " 확인"),
            ("road_marked", "water_marker", "object", " 확인"),
            ("gate_open", "signal_device", "object", " 가동"),
            ("boss_defeated", "jungle_apex", "hostile", " 처치"),
            ("claimed", "pathfinder", "npc", "에게 보고"),
        ),
        "hints": (
            "밀림 입구에서 '선발대 길잡이 대화'로 탐사를 시작하세요.",
            "관측소의 관측 표식과 수몰 도로의 수위 표식을 조사하세요.",
            "수몰 도로의 수위 표식을 조사하세요.",
            "거목 군락의 신호 장치를 조사하세요.",
            "포식자 둥지의 우두머리를 처치하세요.",
            "밀림 입구로 돌아가 선발대 길잡이에게 보고하세요.",
            "깊은 밀림 조사를 마쳤습니다.",
        ),
    },
}


def progress_defaults():
    return {
        identity: {flag: False for flag, *_ in data["steps"]} for identity, data in QUESTS.items()
    }


def next_step(profile, identity):
    state = profile["quests"][identity]
    return next(
        (
            index
            for index, (flag, *_rest) in enumerate(QUESTS[identity]["steps"])
            if not state[flag]
        ),
        len(QUESTS[identity]["steps"]),
    )


def available(profile, identity):
    requirement = QUESTS[identity].get("requires")
    return not requirement or profile["quests"][requirement[0]][requirement[1]]


def current_hint(profile):
    for identity, data in QUESTS.items():
        if available(profile, identity) and not profile["quests"][identity]["claimed"]:
            return data["hints"][next_step(profile, identity)]
    last = next(reversed(QUESTS))
    return QUESTS[last]["hints"][-1]
