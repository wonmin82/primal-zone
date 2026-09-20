"""초기 성장 데이터. 기본 무료 기술은 기존 솔로 성능을 보존한다."""

ATTRIBUTES = {
    "strength": {"name": "힘", "description": "투자 2점마다 공격 +1"},
    "agility": {"name": "민첩", "description": "투자 3점마다 방어 +1"},
    "constitution": {"name": "체질", "description": "투자 1점마다 최대 HP +4"},
    "wisdom": {"name": "지혜", "description": "투자 1점마다 붕대 회복 +2"},
}
PROFICIENCIES = {"weapon": "무기", "defense": "방어", "medicine": "응급처치"}
PROFICIENCY_MAX_RANK = 10
PROFICIENCY_XP_PER_RANK = 20
SAFE_HEAL_TRAINING_CAP = 2
SKILLS = {
    "heavy": {
        "id": "heavy",
        "name": "강타",
        "description": "다음 공격의 피해 배율 증가",
        "max_rank": 3,
        "base_rank": 1,
        "requirements": {2: 1, 3: 3},
        "point_cost": {2: 1, 3: 2},
        "credit_cost": {2: 4, 3: 8},
        "cooldown": 7.5,
        "action_type": "heavy",
        "related_proficiency": "weapon",
    },
    "guard": {
        "id": "guard",
        "name": "방어",
        "description": "기본 공격을 유지하며 다음 피해 감소",
        "max_rank": 3,
        "base_rank": 1,
        "requirements": {2: 1, 3: 3},
        "point_cost": {2: 1, 3: 2},
        "credit_cost": {2: 4, 3: 8},
        "cooldown": 0,
        "action_type": "guard",
        "related_proficiency": "defense",
    },
    "heal": {
        "id": "heal",
        "name": "응급치료",
        "description": "붕대 회복량 증가; 전투 중 기본 공격 대체",
        "max_rank": 3,
        "base_rank": 1,
        "requirements": {2: 1, 3: 3},
        "point_cost": {2: 1, 3: 2},
        "credit_cost": {2: 4, 3: 8},
        "cooldown": 0,
        "action_type": "heal",
        "related_proficiency": "medicine",
    },
}
