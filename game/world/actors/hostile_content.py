"""적대 Actor의 정적 정의와 기존 전투 계산용 데이터 조회."""

from types import MappingProxyType

from .schema import (
    ActorDefinition,
    ActorPresentation,
    AttackPhrase,
    Classification,
    CombatNarrationSpec,
)

HOSTILE_ACTORS = MappingProxyType({
    "scavenger": ActorDefinition(
        "scavenger", "어린청소룡", Classification.CREATURE,
        ActorPresentation(
            "작은 몸집의 육식 공룡이다. 날카로운 이빨을 드러내며 주변을 경계한다.",
            "풀 사이를 빠르게 오가며 주변을 살피고 있다.",
            semantic_role="hostile", distant_visible=True, distant_presence="멀리 풀 사이를 오가고 있다.", unit="마리",
        ),
        level=1, capabilities=("combat",),
        combat_narration=CombatNarrationSpec((AttackPhrase("날카로운 이빨", "물었다", "세게 물었다"),)),
        defaults={"state": "alive", "combat_state": {"hp": 24}},
        profiles={"combat": {
            "combat_mode": 'claimed',
            "hp": 24,
            "attack": 5,
            "defense": 0,
            "xp": 22,
            "currency": 8,
        }},
    ),
    "hunter": ActorDefinition(
        "hunter", "갈퀴사냥룡", Classification.CREATURE,
        ActorPresentation(
            "굽은 발톱을 가진 사냥룡이다. 낮게 엎드린 자세로 먹잇감의 움직임을 살핀다.",
            "몸을 낮춘 채 사냥감을 찾아 주변을 맴돌고 있다.",
            semantic_role="hostile", distant_visible=True, distant_presence="멀리 움직이고 있다.", unit="마리",
        ),
        level=2, capabilities=("combat",),
        combat_narration=CombatNarrationSpec((AttackPhrase("날카로운 발톱", "할퀴었다", "깊게 할퀴었다"),)),
        defaults={"state": "alive", "combat_state": {"hp": 45}},
        profiles={"combat": {
            "combat_mode": 'claimed',
            "hp": 45,
            "attack": 9,
            "defense": 2,
            "xp": 38,
            "currency": 14,
        }},
    ),
    "sentinel": ActorDefinition(
        "sentinel", "고장난경비기", Classification.MACHINE,
        ActorPresentation(
            "외장이 부서진 경비 기계다. 감지기가 움직일 때마다 금속 마찰음이 들린다.",
            "금속 마찰음을 내며 감지기를 돌리고 있다.",
            semantic_role="hostile", distant_visible=True, distant_presence="멀리 감지기를 돌리고 있다.", unit="마리",
        ),
        level=3, capabilities=("combat",),
        combat_narration=CombatNarrationSpec((AttackPhrase("금속 몸체", "들이받았다", "거칠게 들이받았다"),)),
        defaults={"state": "alive", "combat_state": {"hp": 65}},
        profiles={"combat": {
            "combat_mode": 'claimed',
            "hp": 65,
            "attack": 11,
            "defense": 5,
            "xp": 55,
            "currency": 20,
        }},
    ),
    "alpha": ActorDefinition(
        "alpha", "능선의우두머리", Classification.CREATURE,
        ActorPresentation(
            "능선을 차지한 거대한 포식자다. 돌진하기 전 몸을 낮추는 습성이 있다.",
            "덩굴 사이를 묵직하게 오가며 능선을 지키고 있다.",
            semantic_role="hostile", distant_visible=True, distant_presence="멀리 덩굴 사이를 오가고 있다.", unit="마리",
            detectability="conspicuous",
        ),
        level=4, capabilities=("combat",),
        combat_narration=CombatNarrationSpec((AttackPhrase("거대한 몸", "덮쳤다", "거세게 덮쳤다"),)),
        defaults={"state": "alive", "combat_state": {"hp": 170}},
        profiles={"combat": {
            "combat_mode": 'public',
            "hp": 170,
            "attack": 17,
            "defense": 6,
            "xp": 130,
            "currency": 50,
            "boss": True,
            "boss_quest": 'radio_tower',
            "special_period": 3,
        }},
    ),
    "dartclaw": ActorDefinition(
        "dartclaw", "날쌘발톱룡", Classification.CREATURE,
        ActorPresentation(
            "낮은 관목 사이를 빠르게 오가며 틈을 노리는 포식자다.",
            "관목 사이를 빠르게 파고들며 사냥감의 틈을 노리고 있다.",
            semantic_role="hostile", distant_visible=True, distant_presence="멀리 수풀 사이를 빠르게 오가고 있다.", unit="마리",
        ),
        level=5, capabilities=("combat",),
        combat_narration=CombatNarrationSpec((AttackPhrase("날카로운 발톱", "할퀴었다", "거세게 할퀴었다"),)),
        defaults={"state": "alive", "combat_state": {"hp": 58}},
        profiles={"combat": {
            "combat_mode": 'claimed',
            "hp": 58,
            "attack": 15,
            "defense": 2,
            "xp": 55,
            "currency": 18,
        }},
    ),
    "shellback": ActorDefinition(
        "shellback", "철갑등짐승", Classification.CREATURE,
        ActorPresentation(
            "등을 덮은 두꺼운 껍질 때문에 묵직한 일격이 필요하다.",
            "물가를 따라 무겁게 움직이고 있다.",
            semantic_role="hostile", distant_visible=True, distant_presence="멀리 천천히 움직이고 있다.", unit="마리",
        ),
        level=6, capabilities=("combat",),
        combat_narration=CombatNarrationSpec((AttackPhrase("육중한 몸", "들이받았다", "강하게 들이받았다"),)),
        defaults={"state": "alive", "combat_state": {"hp": 105}},
        profiles={"combat": {
            "combat_mode": 'claimed',
            "hp": 105,
            "attack": 12,
            "defense": 10,
            "xp": 70,
            "currency": 24,
        }},
    ),
    "stalker": ActorDefinition(
        "stalker", "그늘추적룡", Classification.CREATURE,
        ActorPresentation(
            "거목 그림자 속에서 오래 먹잇감을 쫓는 사냥룡이다.",
            "그늘에 몸을 낮추고 주변의 기척을 살피고 있다.",
            semantic_role="hostile", distant_visible=True, distant_presence="멀리 그늘 사이를 맴돌고 있다.", unit="마리",
        ),
        level=7, capabilities=("combat",),
        combat_narration=CombatNarrationSpec((AttackPhrase("날카로운 이빨", "물었다", "깊게 물었다"),)),
        defaults={"state": "alive", "combat_state": {"hp": 110}},
        profiles={"combat": {
            "combat_mode": 'claimed',
            "hp": 110,
            "attack": 18,
            "defense": 4,
            "xp": 84,
            "currency": 29,
        }},
    ),
    "jungle_apex": ActorDefinition(
        "jungle_apex", "밀림의포식자", Classification.CREATURE,
        ActorPresentation(
            "깊은 숲을 지배하는 거대한 포식자다. 몸을 뒤틀어 도약하기 전에 숨을 고른다.",
            "휘어진 나무 아래를 오가며 둥지를 지키고 있다.",
            semantic_role="hostile", distant_visible=True, distant_presence="멀리 나무 아래를 오가고 있다.", unit="마리",
            detectability="conspicuous",
        ),
        level=10, capabilities=("combat",),
        combat_narration=CombatNarrationSpec((AttackPhrase("거대한 발톱", "할퀴었다", "깊게 할퀴었다"),)),
        defaults={"state": "alive", "combat_state": {"hp": 270}},
        profiles={"combat": {
            "combat_mode": 'public',
            "hp": 270,
            "attack": 20,
            "defense": 8,
            "xp": 155,
            "currency": 58,
            "boss": True,
            "boss_quest": 'deep_jungle',
            "special_period": 4,
            "special_verb": '몸을 날려 덮쳐',
            "telegraph": '숨을 고르며 도약할 자세를 취한다.',
        }},
    ),
})


def enemy_view(identities):
    """전환 중 기존 계산 호출자가 읽는 형태를 Actor 선언에서 파생한다."""
    output = {}
    for identity in identities:
        actor = HOSTILE_ACTORS[identity]
        presentation = actor.presentation
        row = dict(actor.profiles["combat"], name=actor.name,
                   description=presentation.description, presence=presentation.presence,
                   distant_presence=presentation.distant_presence)
        if presentation.detectability != "normal":
            row["detectability"] = presentation.detectability
        output[identity] = row
    return output
