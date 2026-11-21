"""웹 지도 요청의 공개, 수명주기, 권한 및 실제 월드 회귀."""

from dataclasses import replace
from json import dumps
from time import time
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from typeclasses.explorers import Explorer
from world.content import REGIONS, ROOMS
from world.map_commands import map_text
from world.map_layout import LayoutUnrepresentable
from world.map_metadata import catalog
from world.minimap_presentation import web_map
from world.minimap_sessions import _watch, reset, state_fields

from tests.base import WorldCommandTest


class MinimapTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["support_roof"]
        self.session = self.connect_character(self.char1)
        self.session.protocol_key = "websocket"
        self.send = self.enterContext(patch.object(self.session, "msg"))
        self.schedule = self.enterContext(patch("twisted.internet.reactor.callLater"))
        # 미니맵의 지연 검사만 직접 실행한다. 테스트가 실제 reactor를 실행하지 않는다.
        self.schedule.return_value.active.return_value = True
        self.enterContext(patch("world.minimap_sessions.REQUEST_INTERVAL", 0))
        self.addCleanup(reset, self.session)

    def send_map(self, **payload):
        from server.conf.primal_inputfuncs import pz_map

        pz_map(self.session, payload)
        return self.send.call_args.kwargs["pz_map"][0][0]

    def test_web_uses_identical_semantic_text_for_every_actual_room(self):
        self.assertEqual(len(self.rooms), 67)
        self.char1.change(lambda p: p.update(visited=list(ROOMS)))
        for zone, room in self.rooms.items():
            with self.subTest(zone=zone):
                self.char1.location = room
                terminal = map_text(self.char1, "")
                messages = terminal if isinstance(terminal, list) else [terminal]
                payload = web_map(self.char1)
                self.assertEqual(payload["messages"], [
                    {"kind": msg.kind, "segments": msg.segments} for msg in messages
                ])
                self.assertIn(ROOMS[zone]["name"], payload["summary"])
                self.assertNotIn(zone, dumps(payload, ensure_ascii=False))
                self.assertEqual(bool(payload["sheet"]), catalog().room_sheet[zone] is not None)
                self.assertLessEqual(len(payload["centers"]), 60 * 24)
        self.assertEqual(len(REGIONS), 3)

    def test_request_is_session_targeted_reads_only_and_ignores_replay(self):
        from server.conf.primal_inputfuncs import pz_map

        other = self.connect_character(self.char2)
        with patch.object(other, "msg") as outsider, patch.object(self.char1, "push_state") as push:
            with CaptureQueriesContext(connection) as queries:
                payload = self.send_map(id=1)
            self.assertFalse(any(not item["sql"].lstrip().startswith("SELECT") for item in queries))
            self.assertEqual(set(payload), {"messages", "sheets", "sheet", "centers", "summary",
                                            "partial", "id", "revision", "owner"})
            self.send.reset_mock()
            pz_map(self.session, {"id": 1})
            pz_map(self.session, {"id": 2, "viewer": self.char2.pk})
            self.session.logged_in = False
            pz_map(self.session, {"id": 2})
            self.session.logged_in = True
            with patch.object(self.char1.sessions, "all", return_value=[]):
                pz_map(self.session, {"id": 2})
            self.send.assert_not_called()
            push.assert_not_called()
            outsider.assert_not_called()

    def test_public_names_only_and_private_changes_do_not_change_wire_result(self):
        secret = "support_roof_ne"
        hidden = self.rooms[secret]
        move = next(obj for obj in self.char1.location.exits if obj.key == "북동")
        move.locks.add("view:false()")
        baseline = self.send_map(id=1)
        updated = replace(catalog(), positions={secret: ("support_roof", (88, 88))})
        with patch.dict(ROOMS[secret], name="비공개 구조 변경"):
            with patch("world.map_commands.catalog", return_value=updated):
                changed = self.send_map(id=2)
        self.assertEqual({**baseline, "id": 2}, changed)
        self.assertNotIn(secret, dumps(changed))
        self.assertNotIn(hidden.key, changed["summary"])
        for index, query in enumerate(({"sheet": "deep_jungle"}, {"center": hidden.key},
                                       {"center": secret}, {"center": "다른곳 / " + hidden.key}), 3):
            result = self.send_map(id=index, **query)
            self.assertFalse(result["centers"])
            self.assertFalse(result.get("sheet"))
            self.assertNotIn(hidden.key, result["summary"])

    def test_scope_changes_and_public_permission_revocation_only_then_refetch(self):
        visited = ["support_roof_ne"]
        self.char1.change(lambda p: p.update(visited=visited))
        baseline = state_fields(self.char1, self.session, visited, [], [], True)
        first = self.send_map(id=1)
        self.assertIn(self.rooms[visited[0]].key, first["centers"])
        with patch("world.minimap_presentation.project") as projection, patch(
            "world.minimap_sessions._public_access",
        ) as access:
            for _ in range(8):
                self.assertEqual(baseline, state_fields(self.char1, self.session, visited, [], [], True))
            projection.assert_not_called()
            access.assert_not_called()
        self.rooms[visited[0]].locks.add("view:false()")
        _watch(self.session, self.session.primal_minimap)
        revision = self.send.call_args.kwargs["pz_map_state"][0][0]["revision"]
        self.assertNotEqual(first["revision"], revision)
        second = self.send_map(id=2)
        self.assertEqual(second["revision"], revision)
        self.assertNotIn(self.rooms[visited[0]].key, second["centers"])
        self.rooms[visited[0]].locks.add("view:all()")
        _watch(self.session, self.session.primal_minimap)
        restored = self.send_map(id=3)
        self.assertNotEqual(restored["revision"], second["revision"])
        self.assertIn(self.rooms[visited[0]].key, restored["centers"])
        door_change = state_fields(self.char1, self.session, visited, [], ["동"], True)
        self.assertNotEqual(door_change["minimap_revision"], restored["revision"])

    def test_center_names_are_disambiguated_only_in_the_requested_sheet(self):
        roof = "support_roof_ne"
        floor = "support_5f_c"
        self.char1.change(lambda profile: profile.update(visited=[roof, floor]))
        with patch.dict(ROOMS[roof], name="중앙 복도"), patch.dict(ROOMS[floor], name="중앙 복도"):
            automatic = self.send_map(id=1)
            ambiguous = self.send_map(id=2, center="중앙 복도")
            self.assertIn("여러 곳", ambiguous["summary"])
            scoped = self.send_map(id=3, sheet=automatic["sheet"], center="중앙 복도")
        self.assertEqual(scoped["sheet"], automatic["sheet"])
        self.assertTrue(any(message["kind"] == "map" for message in scoped["messages"]))

    def test_unsubscribe_cancels_permission_watch_and_pending_request(self):
        from server.conf.primal_inputfuncs import pz_map

        self.send_map(id=1)
        entry = self.session.primal_minimap
        self.assertTrue(entry.checks)
        timer = entry.timer
        with patch("world.minimap_sessions.REQUEST_INTERVAL", 1):
            pz_map(self.session, {"id": 2})
        pending = entry.pending
        pz_map(self.session, {"subscribe": False})
        timer.cancel.assert_called()
        pending.cancel.assert_called()
        self.assertIsNone(entry.timer)
        self.assertIsNone(entry.pending)
        self.assertFalse(entry.checks)

    def test_failed_permission_recheck_invalidates_display_without_error_details(self):
        first = self.send_map(id=1)
        entry = self.session.primal_minimap
        self.assertTrue(entry.checks)
        with patch("world.minimap_sessions._public_access", side_effect=RuntimeError("서버 내부 정보")):
            with self.assertLogs("world.minimap_sessions", level="ERROR"):
                _watch(self.session, entry)
        signal = self.send.call_args.kwargs["pz_map_state"][0][0]
        self.assertEqual(set(signal), {"owner", "revision"})
        self.assertNotEqual(signal["revision"], first["revision"])
        self.assertFalse(entry.checks)

    def test_fast_requests_coalesce_and_deliver_only_latest(self):
        from server.conf.primal_inputfuncs import pz_map

        self.send_map(id=1)
        self.send.reset_mock()
        with patch("world.minimap_sessions.REQUEST_INTERVAL", 1):
            pz_map(self.session, {"id": 2})
            _, callback, *args = self.schedule.call_args.args
            pz_map(self.session, {"id": 3})
            _, latest, *latest_args = self.schedule.call_args.args
        callback(*args)
        self.send.assert_not_called()
        latest(*latest_args)
        self.assertEqual(self.send.call_args.kwargs["pz_map"][0][0]["id"], 3)

    def test_prevent_late_response_after_puppet_loss(self):
        from server.conf.primal_inputfuncs import pz_map

        def lose_puppet(*args, **kwargs):
            self.session.puppet = None
            return {"messages": [{"kind": "map", "segments": []}]}

        with patch("world.minimap_presentation.web_map", side_effect=lose_puppet):
            pz_map(self.session, {"id": 1})
        self.send.assert_not_called()
        self.session.puppet = self.char1
        previous = state_fields(self.char1, self.session, [], [], [], True)
        reset(self.session)
        self.assertIn("pz_map_reset", self.send.call_args.kwargs)
        self.assertNotEqual(previous["minimap_owner"],
                            state_fields(self.char1, self.session, [], [], [], True)["minimap_owner"])

    def test_error_payload_uses_existing_safe_failures(self):
        with patch("world.map_commands.layout", side_effect=LayoutUnrepresentable("내부 식별자")):
            result = self.send_map(id=1)
        self.assertEqual(result["messages"][0]["kind"], "error")
        self.assertIn("정확하게 표시할 수 없습니다", result["summary"])
        self.assertNotIn("내부 식별자", result["summary"])
        door = next(exit for exit in self.char1.location.exits if exit.key == "북동")
        door.destination = self.rooms["dock"]
        result = self.send_map(id=2)
        self.assertIn("정확하게 표시할 수 없습니다", result["summary"])
        self.assertNotIn("support_roof", dumps(result))

    def test_current_observed_door_marker_and_remote_sheet(self):
        self.char1.location = self.rooms["hq_concourse"]
        self.char1.change(lambda p: p.update(visited=["hq_admin_office", "dock"]))
        current = web_map(self.char1, now=time())
        glyphs = "".join(seg["text"] for row in current["messages"] if row["kind"] == "map"
                         for seg in row["segments"])
        self.assertIn("×", glyphs)
        self.assertIn("+", glyphs)
        remote = web_map(self.char1, sheet=REGIONS["outpost"]["name"])
        glyphs = "".join(seg["text"] for row in remote["messages"] if row["kind"] == "map"
                         for seg in row["segments"])
        self.assertNotIn("@", glyphs)
