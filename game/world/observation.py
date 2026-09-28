"""공용 환경과 관찰자 광원을 합성한다. 권한과 콘텐츠 노출 정책을 시야로 우회하지 않는다."""

from dataclasses import dataclass
from time import time

from world.content import ITEMS
from world.content.environment import LIGHT_GRADES, VISIBILITIES
from world.lighting import active_source
from world.lighting import display as light_display

VISIBILITY_RANK = {"clear": 0, "reduced": 1, "poor": 2}
LIGHT_RANK = {"bright": 0, "normal": 1, "dim": 2, "dark": 3}
DETECTABILITY_LIMIT = {"conspicuous": 2, "normal": 1, "subtle": 0}


@dataclass(frozen=True)
class ObservationSnapshot:
    ambient_light: str
    effective_light: str
    ambient_visibility: str
    effective_visibility: str
    light_source: str | None = None


@dataclass(frozen=True)
class ObservationContext:
    viewer: object
    room: object
    environment: object
    observed_at: float
    distance: int = 0
    snapshot: ObservationSnapshot | None = None


def observe(environment, profile, observed_at, distance=0):
    """순수 계산: 전원 잔량도 사본에서 투영하며 profile/Environment를 바꾸지 않는다."""
    ambient_light = environment.ambient_light if environment else "normal"
    visibility = environment.visibility if environment else "clear"
    identity = active_source(profile, observed_at)
    strength = 0
    if identity:
        source = ITEMS[identity]["light_source"]
        if distance <= source["range"]:
            strength = max(0, source["strength"] - distance)
        if not strength:
            identity = None
    light_rank = max(0, LIGHT_RANK[ambient_light] - strength)
    sight_rank = max(0, VISIBILITY_RANK[visibility] - strength)
    return ObservationSnapshot(
        ambient_light, tuple(LIGHT_RANK)[light_rank], visibility,
        tuple(VISIBILITY_RANK)[sight_rank], identity,
    )


def context_for(viewer, room=None, observed_at=None, distance=0, *, environment=None):
    from world.environment_state import snapshot_for

    room = viewer.location if room is None else room
    now = time() if observed_at is None else observed_at
    environment = snapshot_for(room, now) if environment is None else environment
    profile = viewer.profile_snapshot() if hasattr(viewer, "profile_snapshot") else {"inventory": {}}
    return ObservationContext(viewer, room, environment, now, distance,
                              observe(environment, profile, now, distance))


def perceives(snapshot, detectability):
    return VISIBILITY_RANK[snapshot.effective_visibility] <= DETECTABILITY_LIMIT.get(detectability, -1)


def can_perceive(obj, context):
    if obj.location != context.room or not obj.access(context.viewer, "view"):
        return False
    if obj.destination:  # 이동 방향은 어둠 속에서도 인지한다.
        return True
    detectability = (obj.db.detectability if obj.attributes.has("detectability")
                     else getattr(obj, "detectability", "normal"))
    return perceives(context.snapshot, detectability)


def can_inspect_loot(context):
    return perceives(context.snapshot, "subtle")


def display(context, profile):
    sight = context.snapshot
    light_ids = [key for key, count in profile["inventory"].items()
                 if count > 0 and ITEMS[key].get("light_source")]
    identity = sight.light_source or next(iter(light_ids), None)
    return {
        "effective_light": {"id": sight.effective_light, "name": LIGHT_GRADES[sight.effective_light]},
        "effective_visibility": {"id": sight.effective_visibility, "name": VISIBILITIES[sight.effective_visibility]},
        "light_source": light_display(profile, identity, context.observed_at) if identity else None,
    }
