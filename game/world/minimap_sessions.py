"""세션별 미니맵 요청과 공개 권한 무효화. 지도 데이터는 저장하지 않는다."""

from dataclasses import dataclass, field
from logging import getLogger
from secrets import token_urlsafe
from time import monotonic
from unicodedata import category

from world import rules
from world.actions.gateway import require_session

logger = getLogger(__name__)
WEB_PROTOCOLS = ("websocket", "webclient/websocket")
RECHECK_SECONDS = 1
REQUEST_INTERVAL = 0.05


def _new_token():
    return token_urlsafe(12)


def _public_access(obj, viewer):
    return not getattr(obj, "_is_deleted", False) and bool(obj.access(viewer, "view"))


@dataclass
class MapSession:
    viewer: object
    owner: str = field(default_factory=_new_token)
    revision: str = field(default_factory=_new_token)
    facts: tuple | None = None
    checks: dict = field(default_factory=dict)
    sheet_checks: list = field(default_factory=list)
    timer: object = None
    pending: object = None
    request_id: int = 0
    last_request: float = float("-inf")

    def stop(self):
        if self.timer is not None and self.timer.active():
            self.timer.cancel()
        self.timer = None
        self.checks.clear()
        self.sheet_checks.clear()

    def cancel_request(self):
        if self.pending is not None and self.pending.active():
            self.pending.cancel()
        self.pending = None

    def invalidate(self):
        self.stop()
        self.cancel_request()
        self.revision = _new_token()

    def changed(self):
        try:
            return any(
                previous != _public_access(obj, self.viewer)
                for obj, previous in self.checks.values()
            ) or any(
                previous != any(_public_access(room, self.viewer) for room in rooms)
                for rooms, previous in self.sheet_checks
            )
        except Exception:
            logger.exception("미니맵 공개 범위를 다시 확인할 수 없습니다.")
            return True


def _session(viewer, session):
    entry = getattr(session, "primal_minimap", None)
    if entry is None or entry.viewer is not viewer:
        if entry is not None:
            entry.stop()
            entry.cancel_request()
        entry = session.primal_minimap = MapSession(viewer)
    return entry


def reset(session):
    entry = getattr(session, "primal_minimap", None)
    if entry is not None:
        entry.stop()
        entry.cancel_request()
        session.primal_minimap = None
        session.msg(pz_map_reset=([], {}))


def state_fields(viewer, session, visited, exits, doors, sees_doors):
    entry = _session(viewer, session)
    facts = (viewer.zone, frozenset(visited), tuple(
        exit["name"] for exit in exits if exit["exists"]
    ), tuple(doors) if sees_doors else ())
    # push_state는 전투 등 지도와 무관한 변경에도 호출된다. 임의 view Lock의
    # 재확인은 열린 지도의 타이머가 전담하고, 여기서는 지도 관련 상태만 비교한다.
    if entry.facts is not None and facts != entry.facts:
        entry.invalidate()
    entry.facts = facts
    return {"minimap_revision": entry.revision, "minimap_owner": entry.owner}


def _watch(session, entry):
    from twisted.internet import reactor

    entry.timer = None
    if getattr(session, "primal_minimap", None) is not entry:
        return
    try:
        require_session(entry.viewer, session)
    except rules.RuleError:
        reset(session)
        return
    if entry.changed():
        entry.invalidate()
        session.msg(pz_map_state=([{"revision": entry.revision, "owner": entry.owner}], {}))
    elif entry.checks or entry.sheet_checks:
        entry.timer = reactor.callLater(RECHECK_SECONDS, _watch, session, entry)


def _label(payload, name):
    value = payload.get(name)
    if value is None:
        return None
    if (not isinstance(value, str) or not 1 <= len(value) <= 128 or not value.strip()
            or "/" in value or any(category(char).startswith("C") for char in value)):
        raise ValueError
    return value


def request(viewer, session, payload):
    if session.protocol_key not in WEB_PROTOCOLS or not isinstance(payload, dict):
        return
    try:
        require_session(viewer, session)
    except rules.RuleError:
        return
    entry = _session(viewer, session)
    if payload == {"subscribe": False}:
        entry.stop()
        entry.cancel_request()
        return
    if payload.keys() - {"id", "sheet", "center"}:
        return
    request_id = payload.get("id")
    if type(request_id) is not int or not entry.request_id < request_id <= 2**53 - 1:
        return
    entry.request_id = request_id
    entry.cancel_request()
    remaining = REQUEST_INTERVAL - (monotonic() - entry.last_request)
    if remaining > 0:
        from twisted.internet import reactor

        entry.pending = reactor.callLater(remaining, _deliver, session, entry, request_id, payload)
    else:
        _deliver(session, entry, request_id, payload)


def _deliver(session, entry, request_id, payload):
    from world import text as ft
    from world.minimap_presentation import web_map

    if getattr(session, "primal_minimap", None) is not entry or entry.request_id != request_id:
        return
    entry.pending = None
    viewer = entry.viewer
    try:
        require_session(viewer, session)
    except rules.RuleError:
        reset(session)
        return
    checks = {}
    sheet_checks = []

    def check(obj, caller):
        if obj.pk not in checks:
            allowed = _public_access(obj, caller)
            checks[obj.pk] = (obj, allowed)
        return checks[obj.pk][1]

    def check_sheet(rooms, caller):
        # 공개 Sheet 이름은 해당 Sheet에 보이는 장소가 한 곳이라도 있는지에만 의존한다.
        allowed = any(_public_access(room, caller) for room in rooms)
        sheet_checks.append((rooms, allowed))
        return allowed

    try:
        sheet, center = _label(payload, "sheet"), _label(payload, "center")
    except ValueError:
        message = "지도 조회 이름을 확인하세요."
        result = {"messages": [{"kind": "error", "segments": ft.token("warning", message).segments}],
                  "sheets": [], "centers": [], "summary": message}
    else:
        entry.last_request = monotonic()
        result = web_map(viewer, sheet=sheet, center=center, view_check=check, sheet_check=check_sheet)

    try:
        require_session(viewer, session)
    except rules.RuleError:
        return
    if getattr(session, "primal_minimap", None) is not entry or entry.request_id != request_id:
        return
    entry.stop()
    entry.checks = checks
    entry.sheet_checks = sheet_checks
    if checks or sheet_checks:
        from twisted.internet import reactor

        entry.timer = reactor.callLater(RECHECK_SECONDS, _watch, session, entry)
    session.msg(pz_map=([{**result, "id": request_id, "revision": entry.revision,
                          "owner": entry.owner}], {}))
