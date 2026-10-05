"""공용 환경과 관찰자 광원을 합성한다. 권한과 콘텐츠 노출 정책을 시야로 우회하지 않는다."""

from dataclasses import dataclass
from time import time

from world.content import ITEMS
from world.content.environment import LIGHT_GRADES, VISIBILITIES
from world.lighting import legacy_snapshot, snapshot_display

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
    lights: object | None = None


def observe(environment, profile, observed_at, distance=0, lights=None):
    """순수 계산: 전원 잔량도 사본에서 투영하며 profile/Environment를 바꾸지 않는다."""
    ambient_light = environment.ambient_light if environment else "normal"
    visibility = environment.visibility if environment else "clear"
    lights = lights if lights is not None else legacy_snapshot(profile, observed_at)
    identity = lights.active.definition_id if lights.active else None
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
    from world.lighting_service import lighting_snapshot

    lights = lighting_snapshot(viewer, profile, now)
    return ObservationContext(viewer, room, environment, now, distance,
                              observe(environment, profile, now, distance, lights), lights)


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
    lights = context.lights or legacy_snapshot(profile, context.observed_at)
    selected = lights.active or next(iter(lights.items), None)
    return {
        "effective_light": {"id": sight.effective_light, "name": LIGHT_GRADES[sight.effective_light]},
        "effective_visibility": {"id": sight.effective_visibility, "name": VISIBILITIES[sight.effective_visibility]},
        "light_source": snapshot_display(selected) if selected else None,
    }
