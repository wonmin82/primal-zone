"""DB/Evennia와 분리된 공용 시계·기상 계산과 immutable 관찰 snapshot."""

from copy import deepcopy
from dataclasses import dataclass
from random import Random

from world.content import REGIONS, ROOM_REGION, ROOMS
from world.content.environment import (
    INITIAL_GAME_SECONDS,
    LIGHT_GRADES,
    LIGHT_PROFILES,
    MOON_CYCLE_DAYS,
    MOONS,
    PERIOD_BOUNDARIES,
    PERIODS,
    VISIBILITIES,
    WEATHER_ZONES,
    WEATHERS,
    WORLD_TIME_SCALE,
)

MAX_CATCHUP_TRANSITIONS = 256
ENVIRONMENT_VERSION = 1


def normalize_state(state):
    """version 없는 초기 PR 저장값을 보존하며 정규화한다. 미래 형식은 덮어쓰지 않는다."""
    version = state.get("version", 0)
    if type(version) is not int or not 0 <= version <= ENVIRONMENT_VERSION:
        raise ValueError(f"지원하지 않는 Environment 저장 버전입니다: {version!r}")
    result = deepcopy(state)
    result["version"] = ENVIRONMENT_VERSION
    return result


def game_seconds(clock, now):
    return max(0, clock["game_epoch"] + (now - clock["real_epoch"]) * clock["time_scale"])


def period_at(seconds):
    hour = int(seconds // 3600) % 24
    return next(period for start, period in reversed(PERIOD_BOUNDARIES) if hour >= start)


def moon_at(day):
    phase = (day - 1) % MOON_CYCLE_DAYS
    return "new" if phase < 4 or phase >= 24 else "full" if 11 <= phase < 18 else "quarter"


def new_environment(now, rng=None):
    rng = rng if rng is not None else Random()
    return {
        "version": ENVIRONMENT_VERSION,
        "clock": {
            "real_epoch": now,
            "game_epoch": INITIAL_GAME_SECONDS,
            "time_scale": WORLD_TIME_SCALE,
        },
        "period": period_at(INITIAL_GAME_SECONDS),
        "zones": {
            zone: {
                "weather": data["initial"],
                "started_at": now,
                "next_change_at": now + rng.uniform(*WEATHERS[data["initial"]]["duration"]),
                "seed": rng.getrandbits(64),
                "step": 0,
            }
            for zone, data in WEATHER_ZONES.items()
        },
    }


def reconcile(state, now, rng=None):
    """사본만 갱신한다. RNG seed/순번은 저장되어 재시작·호출 간격에 독립적이다."""
    result = normalize_state(state)
    for zone, data in result["zones"].items():
        steps = 0
        while now >= data["next_change_at"]:
            generator = rng if rng is not None else Random(data["seed"] + data["step"])
            transitions = WEATHERS[data["weather"]]["transitions"]
            weather = generator.choices(list(transitions), weights=list(transitions.values()), k=1)[
                0
            ]
            started = data["next_change_at"]
            steps += 1
            # 매우 긴 오프라인 간격은 이력을 재생하지 않고 최종 유효 구간으로 복구한다.
            if steps >= MAX_CATCHUP_TRANSITIONS:
                started = now
            data.update(
                weather=weather,
                started_at=started,
                next_change_at=started + generator.uniform(*WEATHERS[weather]["duration"]),
                step=data["step"] + 1,
            )
        # 신규 weather zone은 초기화 경로에서만 추가한다.
    result["period"] = period_at(game_seconds(result["clock"], now))
    return result


@dataclass(frozen=True)
class EnvironmentSnapshot:
    observed_at: float
    game_day: int
    game_hour: int
    game_minute: int
    period: str
    weather_zone: str
    weather: str
    moon_phase: str
    moon_light: int
    exposure: str
    light_profile: str
    ambient_light: str
    visibility: str
    facility_light: int = 0


def snapshot(state, zone, observed_at, facility_light=0):
    return state_snapshot(reconcile(state, observed_at), zone, observed_at, facility_light)


def state_snapshot(state, zone, observed_at, facility_light=0):
    """알림 전/후 비교용: 같은 시각에서 저장된 period/weather를 진행시키지 않고 읽는다."""
    current = normalize_state(state)
    seconds = game_seconds(current["clock"], observed_at)
    day = int(seconds // 86400) + 1
    period = current["period"]
    moon = moon_at(day)
    moon_light = MOONS[moon]["light"] if period == "night" else 0
    weather_zone = REGIONS[ROOM_REGION[zone]]["weather_zone"]
    weather = current["zones"][weather_zone]["weather"]
    exposure, profile = (ROOMS[zone][key] for key in ("exposure", "light_profile"))
    light = LIGHT_PROFILES[profile]
    score = light.get(
        "fixed",
        PERIODS[period]["light"]
        + moon_light
        + WEATHERS[weather]["light_modifier"]
        + light.get("offset", 0),
    )
    score = max(score, facility_light)
    grade = "bright" if score >= 4 else "normal" if score >= 3 else "dim" if score >= 1 else "dark"
    weather_visibility = WEATHERS[weather]["visibility"] if exposure != "indoor" else 0
    visibility = max(weather_visibility, {"bright": 0, "normal": 0, "dim": 1, "dark": 2}[grade])
    return EnvironmentSnapshot(
        observed_at,
        day,
        int(seconds // 3600) % 24,
        int(seconds // 60) % 60,
        period,
        weather_zone,
        weather,
        moon,
        moon_light,
        exposure,
        profile,
        grade,
        ("clear", "reduced", "poor")[visibility],
        facility_light,
    )


def description(environment):
    """환경만 1~2문장으로 표현한다. 객체나 플레이어 상태를 읽지 않는다."""
    first = WEATHERS[environment.weather]["presence"][environment.exposure]
    if environment.facility_light:
        second = "시설 조명이 주변을 비추고 있다."
    elif environment.light_profile in ("dim", "artificial"):
        second = (
            "실내에는 어스름한 빛이 머문다."
            if environment.light_profile == "dim"
            else "조명이 주변을 비추고 있다."
        )
    elif (
        environment.period == "night" and environment.moon_light and environment.weather == "clear"
    ):
        second = f"{MOONS[environment.moon_phase]['name']}의 빛이 어둠 속에 은은하게 비친다."
    else:
        second = PERIODS[environment.period]["sentence"]
    return first + " " + second


def display(environment):
    """웹과 날씨 명령이 동일한 ID/표시명을 사용한다."""
    return {
        "observed_at": environment.observed_at,
        "game_day": environment.game_day,
        "time": f"{environment.game_hour:02}:{environment.game_minute:02}",
        **{
            key: {"id": value, "name": definitions[value]["name"]}
            for key, value, definitions in (
                ("period", environment.period, PERIODS),
                ("weather", environment.weather, WEATHERS),
                ("moon", environment.moon_phase, MOONS),
                ("weather_zone", environment.weather_zone, WEATHER_ZONES),
            )
        },
        "light": {"id": environment.ambient_light, "name": LIGHT_GRADES[environment.ambient_light]},
        "visibility": {"id": environment.visibility, "name": VISIBILITIES[environment.visibility]},
        "exposure": environment.exposure,
        "light_profile": environment.light_profile,
    }
