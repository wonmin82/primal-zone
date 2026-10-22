"""Smoke 타이밍·DB guard·CLI·실패 정리 계약. 실제 게임 시간 검증은 live 실행이 맡는다."""

import asyncio
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from server.conf.smoke_support import QUICK_TIMING, require_smoke, smoke_timings

from world.timing import PRODUCTION_TIMING, configured_timings

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))
from smoke import route  # noqa: E402

from scripts import dev, smoke_harness  # noqa: E402
from scripts.smoke_closeout import (  # noqa: E402
    Closeout,
    assert_preserved_loot,
    assert_shutdown_items,
    assert_startup_items,
    save_restart_snapshot,
    stop_for_restart,
)
from scripts.smoke_snapshot import read_snapshot_transaction  # noqa: E402


class SmokeContractsTests(TestCase):
    def test_full_combat_uses_actual_client_receive_text_and_pz_log_protocol(self):
        from smoke import Client

        async def exercise(plain_text):
            client = Client("fixture", "unused", "ws://unused", command_timeout=.5)
            client.state = {"combat_target": {"id": 9}, "queued_action": "attack", "player_round": 3,
                            "hp": 80, "mental": 25, "zone": "arena", "inventory": []}
            packets = asyncio.Queue()
            ack_seen = asyncio.Event()

            class Log(io.StringIO):
                def write(self, value):
                    result = super().write(value)
                    if '"phase": "ack"' in value:
                        ack_seen.set()
                    return result

            async def incoming():
                while True:
                    yield await packets.get()

            client.socket = incoming()
            reader = asyncio.create_task(client.receive())
            command, action, acknowledgement = (("붕대 사용", "bandage", "다음 차례에는 공격 대신 붕대를 사용한다.")
                                                if plain_text else ("강타", "heavy", "다음 차례에 강타 행동을 준비한다."))

            async def send(*args):
                if plain_text:
                    packet = ["text", [acknowledgement], {}]
                else:
                    packet = ["pz_log", [{"kind": "info", "segments": [{"text": acknowledgement}]}], {}]
                packets.put_nowait(json.dumps(packet))
                # 응답이 send() 반환 전에 들어온 경우에도 Condition 알림을 놓치지 않는다.
                async with client.changed:
                    while client.messages.empty():
                        await client.changed.wait()

            client.send = AsyncMock(side_effect=send)
            scenario = SimpleNamespace(players=[client, None, None], log=Log(), timeouts=SimpleNamespace(combat=.5))
            pending = asyncio.create_task(Closeout(scenario).combat_action(command, action, acknowledgement))
            try:
                async with asyncio.timeout(.5):
                    await ack_seen.wait()
                self.assertEqual(len(client.semantic_logs), 0 if plain_text else 1)
                consumed = dict(client.state, player_round=4, queued_action="attack")
                packets.put_nowait(json.dumps(["pz_state", [consumed], {}]))
                await pending
                client.send.assert_awaited_once_with("text", [command])
            finally:
                client.closing = True
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)

        asyncio.run(exercise(False))
        asyncio.run(exercise(True))

    def test_full_combat_waits_for_both_ack_channels_and_consumption_without_resending(self):
        from smoke import Client

        async def exercise(already_consumed, plain_text):
            client = Client("fixture", "unused", "ws://unused")
            client.state = {"combat_target": {"id": 9, "hp": 50, "round": 2}, "queued_action": "attack", "player_round": 3,
                            "hp": 80, "mental": 25, "zone": "arena", "inventory": []}
            acknowledgement = ("다음 차례에는 공격 대신 붕대를 사용한다." if plain_text else
                               "다음 차례에 강타 행동을 준비한다.")
            command, action = ("붕대 사용", "bandage") if plain_text else ("강타", "heavy")
            row = {"kind": "info", "segments": [{"text": acknowledgement}]}
            client.semantic_logs = [row]
            client.messages.put_nowait(acknowledgement)
            sent = asyncio.Event()
            client.send = AsyncMock(side_effect=lambda *args: sent.set())
            scenario = SimpleNamespace(players=[client, None, None], log=io.StringIO(),
                                       timeouts=SimpleNamespace(combat=.5))
            closeout = Closeout(scenario)
            pending = asyncio.create_task(closeout.combat_action(command, action, acknowledgement))
            await sent.wait()
            # 이전의 동일 메시지와 무관한 새 state/차례 증가로는 명령 성공을 판정하지 않는다.
            async with client.changed:
                client.state = dict(client.state, player_round=4)
                client.revision += 1
                client.changed.notify_all()
            await asyncio.sleep(0)
            self.assertFalse(pending.done())
            async with client.changed:
                if not plain_text:
                    client.semantic_logs.append(deepcopy(row))
                client.messages.put_nowait(acknowledgement)
                client.state = dict(client.state, queued_action="attack" if already_consumed else action)
                client.changed.notify_all()
            await asyncio.sleep(0)
            self.assertFalse(pending.done())
            async with client.changed:
                client.state = dict(client.state, player_round=5, queued_action="attack",
                                    combat_target={"id": 9, "hp": 42, "round": 3})
                client.changed.notify_all()
            await pending
            client.send.assert_awaited_once_with("text", [command])
            self.assertIn('"phase": "ack"', scenario.log.getvalue())
            self.assertIn('"phase": "consumed-or-finished"', scenario.log.getvalue())
            self.assertNotIn("password", scenario.log.getvalue())

        for consumed in (False, True):
            for plain_text in (False, True):
                asyncio.run(exercise(consumed, plain_text))

    def test_full_combat_preserves_rejections_and_timeout_without_resending(self):
        from smoke import Client

        async def exercise(failure):
            client = Client("fixture", "unused", "ws://unused", command_timeout=.03)
            client.state = {"combat_target": {"id": 9}, "queued_action": "attack", "player_round": 3,
                            "hp": 80, "mental": 25, "zone": "arena", "inventory": []}
            acknowledgement = "다음 차례에는 공격 대신 붕대를 사용한다."
            sent = asyncio.Event()
            client.send = AsyncMock(side_effect=lambda *args: sent.set())
            closeout = Closeout(SimpleNamespace(players=[client, None, None], log=io.StringIO(),
                                                timeouts=SimpleNamespace(combat=.03)))
            pending = asyncio.create_task(closeout.combat_action("붕대 사용", "bandage", acknowledgement))
            await sent.wait()
            async with client.changed:
                if failure == "error":
                    client.semantic_logs.append({"kind": "error", "segments": [{"text": "거절"}]})
                elif failure == "disconnect":
                    client.error = ConnectionError("closed")
                elif failure == "defeat":
                    client.state = dict(client.state, hp=1, zone="infirmary", combat_target=None)
                elif failure == "target-changed":
                    client.state = dict(client.state, combat_target={"id": 10})
                elif failure == "queue-changed":
                    client.messages.put_nowait(acknowledgement)
                    client.state = dict(client.state, queued_action="heavy")
                elif failure == "consume-timeout":
                    client.messages.put_nowait(acknowledgement)
                    client.state = dict(client.state, queued_action="bandage")
                client.changed.notify_all()
            expected = ConnectionError if failure == "disconnect" else (
                TimeoutError if failure in ("ack-timeout", "consume-timeout") else AssertionError)
            with self.assertRaises(expected):
                await pending
            client.send.assert_awaited_once_with("text", ["붕대 사용"])

        for failure in ("error", "disconnect", "defeat", "target-changed", "queue-changed", "ack-timeout", "consume-timeout"):
            asyncio.run(exercise(failure))

    def test_full_combat_distinguishes_battle_end_and_refuses_existing_queue(self):
        from smoke import Client

        async def exercise(ack):
            client = Client("fixture", "unused", "ws://unused")
            client.state = {"combat_target": {"id": 9}, "queued_action": "heavy", "player_round": 3,
                            "hp": 80, "mental": 25, "zone": "arena", "inventory": []}
            client.send = AsyncMock()
            scenario = SimpleNamespace(players=[client, None, None], log=io.StringIO(),
                                       timeouts=SimpleNamespace(combat=.1))
            closeout = Closeout(scenario)
            acknowledgement = "다음 차례에 강타 행동을 준비한다."
            with self.assertRaisesRegex(AssertionError, "이전 예약"):
                await closeout.combat_action("강타", "heavy", acknowledgement)
            client.send.assert_not_awaited()
            client.state["queued_action"] = "attack"
            sent = asyncio.Event()
            client.send.side_effect = lambda *args: sent.set()
            pending = asyncio.create_task(closeout.combat_action("강타", "heavy", acknowledgement))
            await sent.wait()
            if ack:
                async with client.changed:
                    client.semantic_logs.append({"kind": "info", "segments": [{"text": acknowledgement}]})
                    client.messages.put_nowait(acknowledgement)
                    client.state = dict(client.state, queued_action="heavy")
                    client.changed.notify_all()
                await asyncio.sleep(0)
            async with client.changed:
                client.state = dict(client.state, combat_target=None, queued_action="attack")
                client.changed.notify_all()
            await pending
            expected = "consumed-or-finished" if ack else "battle-ended-before-ack"
            self.assertIn(expected, scenario.log.getvalue())
            client.send.assert_awaited_once_with("text", ["강타"])

        asyncio.run(exercise(False))
        asyncio.run(exercise(True))

    def test_full_rest_skips_only_when_both_resources_are_full(self):
        async def exercise(hp, mental):
            player = SimpleNamespace(state={"hp": hp, "mental": mental, "max_hp": 126, "max_mental": 55},
                                     act=AsyncMock())
            closeout = Closeout(SimpleNamespace(players=[player, None, None]))
            await closeout.rest_if_needed()
            if hp == 126 and mental == 55:
                player.act.assert_not_awaited()
            else:
                player.act.assert_awaited_once()
                command, predicate = player.act.await_args.args
                self.assertEqual(command, "침대 휴식")
                self.assertFalse(predicate(player.state))
                self.assertFalse(predicate(dict(player.state, hp=126, mental=54)))
                self.assertTrue(predicate(dict(player.state, hp=126, mental=55)))

        for hp, mental in ((126, 55), (125, 55), (126, 54), (125, 54)):
            asyncio.run(exercise(hp, mental))

    def test_command_state_budget_defaults_and_explicit_timeout_take_precedence(self):
        from smoke import STATE_TIMEOUT, Client

        async def check():
            for configured in (STATE_TIMEOUT, 15):
                client = Client("fixture", "unused", "ws://unused", command_timeout=configured)
                client.revision = 7
                client.send, client.until = AsyncMock(), AsyncMock(return_value={"ok": True})
                predicate = lambda state: state["ok"]  # noqa: E731
                for requested, expected in ((None, configured), (3, 3), (0, 0)):
                    self.assertEqual(await client.act("상태", predicate, timeout=requested), {"ok": True})
                    client.send.assert_awaited_with("text", ["상태"])
                    client.until.assert_awaited_with(predicate, expected, 7)
                client.send.reset_mock()
                client.until.side_effect = TimeoutError("command deadline")
                with self.assertRaisesRegex(TimeoutError, "command deadline"):
                    await client.act("상태", predicate)
                client.send.assert_awaited_once_with("text", ["상태"])
            self.assertEqual(Client("fixture", "unused", "ws://unused").command_timeout, 10)

        asyncio.run(check())

    def test_full_command_budget_does_not_extend_quick_or_other_state_waits(self):
        from smoke import STATE_TIMEOUT, Client, Scenario, Timeouts

        self.assertEqual(STATE_TIMEOUT, 10)
        for mode, expected in (("quick", 10), ("full", 15)):
            scenario = Scenario(SimpleNamespace(mode=mode, ws_url="ws://unused",
                                                credentials=[("fixture", "unused")]), None)
            self.assertEqual(scenario.players[0].command_timeout, expected)
            timings = smoke_timings(mode)
            self.assertEqual(scenario.timeouts, Timeouts(combat=timings["COMBAT_INTERVAL"] * 20 + 10,
                                                         lifecycle=timings["LOOT_PROTECTION_SECONDS"] + 10))

        async def check_action():
            client = Client("fixture", "unused", "ws://unused", command_timeout=15)
            client.send, client.until = AsyncMock(), AsyncMock()
            await client.action({"action_id": "fixture"})
            self.assertEqual(client.until.await_args.args[1], 10)
            direct = Client("fixture", "unused", "ws://unused", command_timeout=15)
            direct.state = {"ready": True}
            with patch("smoke.asyncio.timeout", wraps=asyncio.timeout) as deadline:
                await direct.until(lambda state: state["ready"])
            deadline.assert_called_once_with(10)

        asyncio.run(check_action())

    def test_full_elapsed_uses_actual_clock_and_original_timing_upper_bound(self):
        from smoke import Scenario

        scenario = Scenario(SimpleNamespace(mode="full", ws_url="ws://unused", credentials=[]), None)
        scenario.report = lambda *args: None
        for expected in (30, 45, 120):
            with self.subTest(expected=expected):
                with patch("smoke.monotonic", return_value=100 + expected + 10):
                    scenario.elapsed("production boundary", 100, expected)
                with patch("smoke.monotonic", return_value=100 + expected + 10.001):
                    with self.assertRaises(AssertionError):
                        scenario.elapsed("production boundary", 100, expected)

    def test_recovery_route_opens_closed_door_in_both_directions_before_moving(self):
        player = SimpleNamespace(state={'zone': 'support_3f_e1'})
        commands, opened = [], False

        async def prompt(command):
            nonlocal opened
            commands.append(command)
            self.assertEqual(command, '회복실 문 열어')
            opened = True

        async def act(command, predicate):
            commands.append(command)
            if not opened:
                raise AssertionError('closed recovery door')
            player.state['zone'] = 'recovery_room' if command == '북' else 'support_3f_e1'
            self.assertTrue(predicate(player.state))

        player.expect_prompt, player.act = prompt, act
        asyncio.run(route(player, [('북', 'recovery_room')]))
        opened = False  # 정상 자동 닫힘 후 내부에서도 같은 사용자 경로를 사용한다.
        asyncio.run(route(player, [('남', 'support_3f_e1')]))
        self.assertEqual(commands, ['회복실 문 열어', '북', '회복실 문 열어', '남'])

    def test_recovery_route_keeps_open_command_failure_and_does_not_move(self):
        player = SimpleNamespace(state={'zone': 'support_3f_e1'},
                                 expect_prompt=AsyncMock(side_effect=RuntimeError('open unavailable')),
                                 act=AsyncMock())
        with self.assertRaisesRegex(RuntimeError, 'open unavailable'):
            asyncio.run(route(player, [('북', 'recovery_room')]))
        player.act.assert_not_awaited()
        self.assertEqual(player.state['zone'], 'support_3f_e1')

    def test_route_does_not_adopt_general_or_locked_admin_exit(self):
        player = SimpleNamespace(state={'zone': 'hq_concourse'}, expect_prompt=AsyncMock())
        async def act(command, predicate):
            if command == '동':
                raise RuntimeError('locked admin exit')
            player.state['zone'] = 'dock'
            self.assertTrue(predicate(player.state))
        player.act = act
        asyncio.run(route(player, [('서', 'dock')]))
        player.state['zone'] = 'hq_concourse'
        with self.assertRaisesRegex(RuntimeError, 'locked admin exit'):
            asyncio.run(route(player, [('동', 'hq_admin_office')]))
        player.expect_prompt.assert_not_awaited()

    def test_shutdown_preserves_rows_and_only_settles_enabled_light_power(self):
        from copy import deepcopy

        saved = {"light": {"definition": "flashlight", "quantity": 1, "sequence": 8,
                           "location": "inventory", "parent": None, "slot": None, "socket": None,
                           "state": {"power_type": "battery", "remaining_power": 100,
                                     "enabled": True, "started_at": 10}},
                 "stack": {"definition": "bandage", "quantity": 3, "state": {}}}
        restored = deepcopy(saved)
        restored["light"]["state"].update(enabled=False, started_at=None, remaining_power=85)
        saved["off"] = deepcopy(saved["light"])
        saved["off"]["state"].update(enabled=False, started_at=None)
        restored["off"] = deepcopy(saved["off"])
        assert_shutdown_items(saved, restored, 20, 30)
        for field, value in (("quantity", 2), ("sequence", 9), ("location", "personal_storage"),
                             ("definition", "bandage"), ("parent", "other"),
                             ("slot", "hands"), ("socket", "magazine")):
            broken = deepcopy(restored)
            broken["light"][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                assert_shutdown_items(saved, broken, 20, 30)
        for field, value in (("remaining_power", 95), ("remaining_power", 75),
                             ("enabled", True), ("started_at", 20), ("power_type", "unknown")):
            broken = deepcopy(restored)
            broken["light"]["state"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(AssertionError):
                assert_shutdown_items(saved, broken, 20, 30)
        for identity, field, value in (("stack", "quantity", 2), ("stack", "state", {"changed": True}),
                                       ("stack", "parent", "other"), ("off", "state", {})):
            broken = deepcopy(restored)
            broken[identity][field] = value
            with self.subTest(identity=identity, field=field), self.assertRaises(AssertionError):
                assert_shutdown_items(saved, broken, 20, 30)
        for identity in ("stack", "added"):
            broken = deepcopy(restored)
            if identity == "stack":
                del broken[identity]
            else:
                broken[identity] = deepcopy(restored["stack"])
            with self.subTest(identity=identity), self.assertRaises(AssertionError):
                assert_shutdown_items(saved, broken, 20, 30)

    def test_startup_preserves_items_strictly_without_light_settlement_exception(self):
        from copy import deepcopy

        stopped = {"item": {"definition": "flashlight", "quantity": 1, "sequence": 8,
                             "location": "inventory", "parent": None, "slot": None, "socket": None,
                             "state": {"enabled": False, "started_at": None, "remaining_power": 85}}}
        assert_startup_items(stopped, deepcopy(stopped))
        for field, value in (("quantity", 2), ("sequence", 9), ("location", "personal_storage"),
                             ("parent", "other"), ("state", {"enabled": False, "remaining_power": 80})):
            restored = deepcopy(stopped)
            restored["item"][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                assert_startup_items(stopped, restored)
        with self.assertRaises(AssertionError):
            assert_startup_items(stopped, {})
        # startup은 ON → OFF 정산을 두 번째로 허용하지 않는다.
        live = deepcopy(stopped)
        live["item"]["state"].update(enabled=True, started_at=10)
        with self.assertRaises(AssertionError):
            assert_startup_items(live, stopped)

    def test_full_restart_requests_isolated_shutdown_and_checks_owned_process_exit(self):
        from unittest.mock import Mock

        harness = SimpleNamespace(mode="full", check_alive=Mock(), graceful_stop=Mock())
        order = Mock()
        order.attach_mock(harness.check_alive, "alive")
        order.attach_mock(harness.graceful_stop, "shutdown")
        stop_for_restart(harness)
        self.assertEqual([call[0] for call in order.mock_calls], ["alive", "shutdown"])
        failure = RuntimeError("normal shutdown failed")
        harness.graceful_stop.side_effect = failure
        with self.assertRaises(RuntimeError) as raised:
            stop_for_restart(harness)
        self.assertIs(raised.exception, failure)
        harness.graceful_stop.reset_mock(side_effect=True)
        harness.check_alive.side_effect = RuntimeError("owned process exited")
        with self.assertRaisesRegex(RuntimeError, "owned process exited"):
            stop_for_restart(harness)
        harness.graceful_stop.assert_not_called()
        harness.check_alive.reset_mock(side_effect=True)
        harness.mode = "quick"
        with self.assertRaises(AssertionError):
            stop_for_restart(harness)
        harness.check_alive.assert_not_called()
        harness.graceful_stop.assert_not_called()

        # 위임한 공통 경계도 실제 명령·소유 exit 검사를 보존해야 한다.
        # subprocess와 소유 DB 관측을 대체하므로 서버/DB는 실행하지 않는다.
        with tempfile.TemporaryDirectory() as folder:
            process = Mock()
            process.wait.return_value = 0
            harness = smoke_harness.Harness("full")
            harness.run_dir, harness.env = Path(folder), {"isolated": "yes"}
            harness.processes = [("server", process)]
            handle = Mock()
            harness.handles = [handle]
            with (patch.object(harness, "owned_database_fingerprint") as owned,
                  patch("scripts.smoke_harness.subprocess.run") as command):
                harness.graceful_stop()
                owned.assert_called_once_with()
                arguments = command.call_args.args[0]
                self.assertEqual(arguments, [sys.executable, "-c",
                                             "from evennia.server.evennia_launcher import main; main()",
                                             "stop", "--settings", "settings_smoke"])
                self.assertEqual(command.call_args.kwargs["cwd"], Path(folder) / "game")
                self.assertEqual(command.call_args.kwargs["env"], harness.env)
                self.assertTrue(command.call_args.kwargs["check"])
                process.wait.assert_called_once_with(timeout=smoke_harness.SHUTDOWN_TIMEOUT)
                handle.close.assert_called_once_with()
                process.wait.return_value = 1
                with self.assertRaisesRegex(RuntimeError, "정상 종료"):
                    harness.graceful_stop()
                owned.side_effect = RuntimeError("unowned fixture")
                command.reset_mock()
                with self.assertRaisesRegex(RuntimeError, "unowned fixture"):
                    harness.graceful_stop()
                command.assert_not_called()

    def test_enemy_delay_canonical_setting_precedes_legacy_fallback(self):
        key = "ENEMY_RECOVERY_DELAY_SECONDS"
        self.assertEqual(configured_timings(SimpleNamespace(PRIMAL_ENEMY_RESET_SECONDS=3))[key], 3)
        self.assertEqual(configured_timings(SimpleNamespace(
            PRIMAL_ENEMY_RESET_SECONDS=3, PRIMAL_ENEMY_RECOVERY_DELAY_SECONDS=7))[key], 7)
        self.assertEqual(PRODUCTION_TIMING[key], 15)
        self.assertEqual(QUICK_TIMING[key], 2)

    def test_production_defaults_and_full_timing_are_unchanged(self):
        expected = {
            "COMBAT_INTERVAL": 2.5, "CORPSE_TTL_SECONDS": 30, "RESPAWN_DELAY_SECONDS": 15,
            "LOOT_PROTECTION_SECONDS": 120, "CLAIM_TIMEOUT_SECONDS": 15,
            "PARTICIPATION_TIMEOUT_SECONDS": 15, "ENEMY_RECOVERY_DELAY_SECONDS": 15,
        }
        self.assertEqual(PRODUCTION_TIMING, expected)
        self.assertEqual(configured_timings(SimpleNamespace()), expected)
        self.assertEqual(smoke_timings("full"), expected)
        self.assertEqual(set(QUICK_TIMING), set(expected))
        idle_deadlines = {"COMBAT_INTERVAL", "CLAIM_TIMEOUT_SECONDS", "PARTICIPATION_TIMEOUT_SECONDS"}
        self.assertTrue(all(0 < value < expected[key] for key, value in QUICK_TIMING.items()
                            if key not in idle_deadlines))
        # 처리/화면 전송 지연이 공격 기회보다 길어도 Quick 참가 자격이 사라지지 않는다.
        self.assertEqual({key: QUICK_TIMING[key] for key in idle_deadlines},
                         {key: expected[key] for key in idle_deadlines})
        self.assertGreaterEqual(QUICK_TIMING['CORPSE_TTL_SECONDS'], 10)
        self.assertGreater(QUICK_TIMING['LOOT_PROTECTION_SECONDS'],
                           QUICK_TIMING['CORPSE_TTL_SECONDS'] + QUICK_TIMING['RESPAWN_DELAY_SECONDS'])
        config = SimpleNamespace(**{"PRIMAL_" + key: value for key, value in QUICK_TIMING.items()})
        self.assertEqual(configured_timings(config), smoke_timings("quick"))
        with self.assertRaises(ValueError):
            smoke_timings("invalid")

    def test_guard_rejects_normal_settings_before_fixture_database_access(self):
        with self.assertRaisesRegex(RuntimeError, "marker"):
            require_smoke(SimpleNamespace(PRIMAL_SMOKE=False))

    def test_marker_alone_cannot_authorize_other_database_or_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder).resolve()
            (run / ".primal-smoke").touch()
            config = SimpleNamespace(PRIMAL_SMOKE=True, PRIMAL_SMOKE_RUN_DIR=folder,
                                     GAME_DIR=str(run / "game"), DATABASES={"default": {
                                         "ENGINE": "django.db.backends.sqlite3",
                                         "NAME": str(run / "evennia-smoke.sqlite3")}})
            require_smoke(config)
            for engine, database, game in (
                ("django.db.backends.postgresql", "play", str(run / "game")),
                ("django.db.backends.sqlite3", str(run / "evennia.db3"), str(run / "game")),
                ("django.db.backends.sqlite3", str(run / "evennia-smoke.sqlite3"), str(PROJECT / "game")),
            ):
                with self.subTest(engine=engine, database=database, game=game):
                    bad = SimpleNamespace(**vars(config))
                    bad.DATABASES = {"default": {"ENGINE": engine, "NAME": database}}
                    bad.GAME_DIR = game
                    with self.assertRaises(RuntimeError):
                        require_smoke(bad)
            (run / ".primal-smoke").unlink()
            with self.assertRaises(RuntimeError):
                require_smoke(config)

    def test_smoke_environment_ignores_user_postgres_and_python_settings(self):
        with patch.dict(os.environ, {"PRIMAL_DB_NAME": "do-not-connect", "PRIMAL_DB_PASSWORD": "private",
                                    "DJANGO_SETTINGS_MODULE": "server.conf.settings",
                                    "PYTHONPATH": "unrelated"}):
            env = smoke_harness.smoke_environment(Path("isolated"), "full", {"ws": 12345})
        self.assertFalse(any(key.startswith("PRIMAL_DB_") for key in env))
        self.assertEqual(env["DJANGO_SETTINGS_MODULE"], "server.conf.settings_smoke")
        self.assertEqual(env["PRIMAL_SMOKE_MODE"], "full")
        self.assertEqual(env["PRIMAL_SMOKE_WS"], "12345")

    def test_loaded_smoke_settings_use_marker_sqlite_and_correct_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder).resolve()
            (run / ".primal-smoke").touch()
            game = run / "game"
            shutil.copytree(PROJECT / "game" / "server" / "conf", game / "server" / "conf",
                            ignore=shutil.ignore_patterns("secret_settings.py", "__pycache__"))
            (game / "server" / "conf" / "secret_settings.py").write_text("SECRET_KEY = 'temporary'\n")
            code = ("from django.conf import settings; from world.timing import configured_timings; "
                    "import json; print(json.dumps([settings.PRIMAL_SMOKE, settings.DATABASES, "
                    "configured_timings(settings), settings.NEW_ACCOUNT_REGISTRATION_ENABLED]))")
            for mode in ("quick", "full"):
                env = smoke_harness.smoke_environment(run, mode,
                                                     {"ws": 4102, "http": 4101, "internal": 4105, "amp": 4106})
                env["PYTHONPATH"] += os.pathsep + str(PROJECT / "game")
                output = subprocess.check_output([sys.executable, "-c", code], cwd=game, env=env, text=True)
                marker, databases, timing, registration = json.loads(output.splitlines()[-1])
                self.assertIs(marker, True)
                self.assertEqual(databases["default"]["NAME"], str(run / "evennia-smoke.sqlite3"))
                self.assertEqual(databases["default"]["ENGINE"], "django.db.backends.sqlite3")
                self.assertEqual(databases["default"]["OPTIONS"]["timeout"], 30)
                self.assertEqual(databases["default"]["OPTIONS"]["transaction_mode"], "IMMEDIATE")
                self.assertEqual(timing, smoke_timings(mode))
                self.assertIs(registration, False)

    def test_dev_cli_dispatches_quick_full_and_rejects_test_options(self):
        for command, mode in (("smoke", "quick"), ("smoke-full", "full")):
            with patch.object(sys, "argv", ["dev.py", command]), patch.object(dev, "run") as run:
                dev.main()
                run.assert_called_once_with(str(PROJECT / "scripts" / "smoke.py"), "--mode", mode,
                                            cwd=PROJECT)
            with patch.object(sys, "argv", ["dev.py", command, "--parallel", "2"]):
                with self.assertRaises(SystemExit) as error:
                    dev.main()
                self.assertEqual(error.exception.code, 2)
        with patch.object(sys, "argv", ["dev.py", "smoke-unknown"]):
            with self.assertRaises(SystemExit) as error:
                dev.main()
            self.assertEqual(error.exception.code, 2)

    def test_failure_stops_owned_process_and_next_run_has_clean_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(smoke_harness, "ROOT", Path(folder)):
            parent = Path(folder) / "work" / "smoke"
            parent.mkdir(parents=True)
            previous = None
            for failing in (True, False):
                harness = smoke_harness.Harness("quick")
                harness.run_dir = Path(tempfile.mkdtemp(dir=parent)).resolve()
                (harness.run_dir / ".primal-smoke").touch()
                self.assertNotEqual(harness.run_dir, previous)
                flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {
                    "start_new_session": True}
                process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **flags)
                harness.processes.append(("owned", process))

                async def scenario():
                    if failing:
                        raise AssertionError("harness failure injection")

                try:
                    if failing:
                        with self.assertRaisesRegex(AssertionError, "failure injection"):
                            asyncio.run(harness.supervise(scenario()))
                    else:
                        asyncio.run(harness.supervise(scenario()))
                finally:
                    harness.stop()
                self.assertIsNotNone(process.poll())
                previous = harness.run_dir
                harness.discard()
                self.assertFalse(previous.exists())

    def test_premature_exit_and_unsafe_cleanup_fail_explicitly(self):
        harness = smoke_harness.Harness("quick")
        harness.run_dir = PROJECT
        process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
        process.wait()
        harness.processes.append(("server", process))
        with self.assertRaisesRegex(RuntimeError, "조기 종료"):
            harness.check_alive()
        with self.assertRaisesRegex(RuntimeError, "소유권"):
            harness.discard()



class SmokeFirstBossPreparationTests(TestCase):
    def preparation(self, xp=291, *, reward=None, defeat=False, unavailable=False):
        from world.content import ENEMIES, ROOMS
        from world.rules import level_of

        player = SimpleNamespace(state={"xp": xp, "level": level_of({"xp": xp}), "zone": "marsh",
                                        "combat_target": None, "hp": 100, "max_hp": 100,
                                        "mental": 0, "player_round": 0, "inventory": []})
        commands, waits, reports = [], [], []

        async def act(command, predicate=lambda s: True):
            commands.append(command)
            state = player.state
            if command in ("남", "동"):
                state['zone'] = ROOMS[state['zone']]['exits'][command]
                enemy = ENEMIES[ROOMS[state['zone']]['enemies'][0]]
                state['enemies'] = [dict(enemy, can_attack=True)]
            elif command.endswith(' 공격'):
                self.assertEqual(command, state['enemies'][0]['name'] + ' 공격')
                state['combat_target'] = {"id": 1}
            else:
                self.assertEqual(command, '시체에서 모두 가져')
            self.assertTrue(predicate(state))

        async def until(predicate, *args):
            state = player.state
            if state['combat_target'] is not None:
                state['combat_target'] = None
                state['xp'] += state['enemies'][0]['xp'] if reward is None else reward
                state['level'] = level_of(state)
                if defeat:
                    state['zone'] = 'infirmary'
            else:
                waits.append(state['zone'])
                enemy = state['enemies'][0]
                for invalid in ([], [dict(enemy, name='다른적')], [dict(enemy, hp=0)],
                                [dict(enemy, can_attack=False)]):
                    self.assertFalse(predicate(dict(state, enemies=invalid)))
                if unavailable:
                    raise TimeoutError('기존 유한 상태 대기 종료')
            self.assertTrue(predicate(state))
            return state

        player.act, player.until = act, until
        scenario = SimpleNamespace(players=[player, None, None], timeouts=SimpleNamespace(combat=.1),
                                   report=lambda *args: reports.append(args))
        return Closeout(scenario), commands, waits, reports

    def test_first_boss_preparation_uses_public_fixed_route_kills_and_loot(self):
        closeout, commands, waits, reports = self.preparation()
        asyncio.run(closeout.prepare_first_boss_level())
        self.assertEqual(commands, ['남', '갈퀴사냥룡 공격', '시체에서 모두 가져',
                                    '남', '어린청소룡 공격', '시체에서 모두 가져',
                                    '동', '어린청소룡 공격', '시체에서 모두 가져'])
        self.assertEqual(waits, ['trail', 'grass', 'wreck'])
        self.assertEqual((closeout.first.state['xp'], closeout.first.state['level']), (373, 5))
        self.assertIn('XP 291→329 / Lv.4→4', reports[0][1])
        self.assertIn('XP 351→373 / Lv.4→5', reports[-1][1])

    def test_first_boss_preparation_stops_when_level_is_sufficient(self):
        for xp, hunts in ((360, 0), (340, 1), (320, 2)):
            with self.subTest(xp=xp):
                closeout, commands, waits, reports = self.preparation(xp)
                asyncio.run(closeout.prepare_first_boss_level())
                self.assertEqual(len(commands), hunts * 3)
                self.assertEqual(len(waits), hunts)
                self.assertEqual(len(reports), hunts)
                self.assertGreaterEqual(closeout.first.state['level'], 5)

    def test_first_boss_preparation_preserves_failure_boundaries_without_retry(self):
        for options, error, commands_count in (
            ({'reward': 0}, AssertionError, 2),
            ({'defeat': True}, AssertionError, 2),
            ({'unavailable': True}, TimeoutError, 1),
            ({'reward': 1}, AssertionError, 9),
        ):
            with self.subTest(options=options):
                closeout, commands, waits, reports = self.preparation(**options)
                with self.assertRaises(error):
                    asyncio.run(closeout.prepare_first_boss_level())
                self.assertEqual(len(commands), commands_count)
                self.assertLessEqual(len(waits), 3)
        self.assertEqual(len(reports), 3)
        self.assertEqual(closeout.first.state['xp'], 294)


class SmokeLootPreservationTests(TestCase):
    def setUp(self):
        item = {"definition": "bandage", "quantity": 2, "sequence": 7,
                "location": "corpse_loot", "parent": None, "slot": None, "socket": None,
                "state": {"quality": "saved"}}
        claim = {"id": 21, "reserved_party": 3, "reserved_player": None,
                 "assigned_player": 8, "protection_until": 50}
        source = {"native": True, "corpse": True, "room": 4, "entries": [],
                  "items": {"root": item, "duplicate": dict(item, sequence=8),
                            "child": dict(item, sequence=9, location="inside", parent="root")},
                  "claims": {"root": claim, "duplicate": dict(claim, id=22, protection_until=100)},
                  "currency": {"31": {"quantity": 5, "reserved_party": 3, "reserved_player": None,
                                      "protection_until": 50,
                                      "shares": {"41": {"player": 8, "remaining": 5},
                                                 "42": {"player": 9, "remaining": 0}}}}}
        ground = dict(deepcopy(source), corpse=False, items={"ground": dict(item, location="world_loot")},
                      claims={}, currency={})
        self.before = {"observed_at": 10, "completed_at": 11, "loot": {"1": source, "2": ground}}
        self.final = {"observed_at": 59, "completed_at": 60, "loot": {"2": deepcopy(ground)}}
        for source_id, roots, currencies in (("3", ("root", "child"), {}),
                                            ("4", ("duplicate",), {}), ("5", (), source["currency"])):
            restored = deepcopy(source)
            restored.update(corpse=False, items={key: deepcopy(source["items"][key]) for key in roots},
                            claims={key: deepcopy(source["claims"][key]) for key in roots
                                    if key in source["claims"]}, currency=deepcopy(currencies))
            for row in restored["items"].values():
                if row["parent"] is None:
                    row["location"] = "world_loot"
            self.final["loot"][source_id] = restored

    def test_preserves_native_duplicates_tree_rights_and_new_combat_loot(self):
        self.final["loot"]["6"] = dict(deepcopy(self.final["loot"]["2"]),
                                         items={"new": deepcopy(self.final["loot"]["2"]["items"]["ground"])})
        self.assertEqual(assert_preserved_loot(self.before, self.final),
                         {"items": 4, "currency": 1, "expired_claims": 0})

    def test_decay_rejects_existing_sources_and_entry_merges(self):
        for destination in ("1", "2"):
            final = deepcopy(self.final)
            moved = final["loot"].pop("3")
            if destination in final["loot"]:
                final["loot"][destination]["items"].update(moved["items"])
                final["loot"][destination]["claims"].update(moved["claims"])
            else:
                final["loot"][destination] = moved
            with self.subTest(existing=destination), self.assertRaises(AssertionError):
                assert_preserved_loot(self.before, final)
        for source_id in ("4", "5"):
            final = deepcopy(self.final)
            merged = final["loot"].pop(source_id)
            for field in ("items", "claims", "currency"):
                final["loot"]["3"][field].update(merged[field])
            with self.subTest(merged=source_id), self.assertRaises(AssertionError):
                assert_preserved_loot(self.before, final)
        final = deepcopy(self.final)
        final["loot"]["3"]["items"]["new-unrelated-root"] = deepcopy(final["loot"]["3"]["items"]["root"])
        with self.assertRaises(AssertionError):
            assert_preserved_loot(self.before, final)

    def test_snapshot_read_transaction_is_deferred_and_rolled_back_without_database_access(self):
        from unittest.mock import MagicMock

        connection = MagicMock(vendor="sqlite", in_atomic_block=False)
        connection.get_autocommit.return_value = True
        cursor = connection.cursor.return_value.__enter__.return_value
        with read_snapshot_transaction(connection):
            cursor.execute.assert_called_once_with("BEGIN DEFERRED")
            connection.rollback.assert_not_called()
        connection.rollback.assert_called_once_with()
        connection.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "projection failure"):
            with read_snapshot_transaction(connection):
                raise RuntimeError("projection failure")
        connection.rollback.assert_called_once_with()
        for vendor, autocommit, atomic in (("postgresql", True, False), ("sqlite", False, False),
                                           ("sqlite", True, True)):
            connection.reset_mock()
            connection.vendor, connection.in_atomic_block = vendor, atomic
            connection.get_autocommit.return_value = autocommit
            with self.subTest(vendor=vendor, autocommit=autocommit, atomic=atomic), self.assertRaises(AssertionError):
                with read_snapshot_transaction(connection):
                    self.fail("잘못된 transaction 경계로 진입함")
            connection.cursor.assert_not_called()

    def test_item_identity_loss_replacement_and_duplicate_are_rejected(self):
        for mutation in ("missing", "replacement", "duplicate"):
            final = deepcopy(self.final)
            items = final["loot"]["4"]["items"]
            if mutation == "missing":
                items.clear()
            elif mutation == "replacement":
                items["other-uuid"] = items.pop("duplicate")
            else:
                final["loot"]["2"]["items"]["duplicate"] = deepcopy(items["duplicate"])
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                assert_preserved_loot(self.before, final)

    def test_item_state_quantity_and_tree_mutations_are_rejected(self):
        for field, value in (("definition", "scrap"), ("quantity", 1), ("sequence", 99),
                             ("state", {}), ("parent", "duplicate"), ("location", "inventory"),
                             ("slot", "hands"), ("socket", "power")):
            final = deepcopy(self.final)
            final["loot"]["3"]["items"]["child"][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                assert_preserved_loot(self.before, final)
        final = deepcopy(self.final)
        final["loot"]["4"]["items"]["child"] = final["loot"]["3"]["items"].pop("child")
        with self.assertRaises(AssertionError):
            assert_preserved_loot(self.before, final)

    def test_wrong_room_ground_source_and_unfinished_corpse_are_rejected(self):
        for source_id, field, value in (("3", "room", 99), ("2", "room", 99), ("3", "corpse", True)):
            final = deepcopy(self.final)
            final["loot"][source_id][field] = value
            with self.subTest(source=source_id, field=field), self.assertRaises(AssertionError):
                assert_preserved_loot(self.before, final)
        final = deepcopy(self.final)
        final["loot"]["other-source"] = final["loot"].pop("2")
        with self.assertRaises(AssertionError):
            assert_preserved_loot(self.before, final)

    def test_claim_expiry_uses_snapshot_completion_and_rejects_other_changes(self):
        for deadline in (0, 10, 59, 60):
            before, final = deepcopy(self.before), deepcopy(self.final)
            before["loot"]["1"]["claims"]["root"]["protection_until"] = deadline
            del final["loot"]["3"]["claims"]["root"]
            with self.subTest(deadline=deadline):
                self.assertEqual(assert_preserved_loot(before, final)["expired_claims"], 1)
        final = deepcopy(self.final)
        del final["loot"]["4"]["claims"]["duplicate"]
        with self.assertRaises(AssertionError):
            assert_preserved_loot(self.before, final)
        for field, value in (("id", 99), ("reserved_party", None), ("reserved_player", 9),
                             ("assigned_player", 9), ("protection_until", 0)):
            final = deepcopy(self.final)
            final["loot"]["3"]["claims"]["root"][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                assert_preserved_loot(self.before, final)
        final = deepcopy(self.final)
        final["loot"]["2"]["claims"]["ground"] = deepcopy(final["loot"]["3"]["claims"]["root"])
        with self.assertRaises(AssertionError):
            assert_preserved_loot(self.before, final)

    def test_currency_identity_reservation_and_zero_share_eligibility_are_preserved(self):
        for mutation in ("missing", "replacement", "quantity", "deadline", "party", "player",
                         "zero-share", "amount", "share-player", "share-id"):
            final = deepcopy(self.final)
            currency = final["loot"]["5"]["currency"]
            row = currency["31"]
            if mutation == "missing":
                currency.clear()
            elif mutation == "replacement":
                currency["32"] = currency.pop("31")
            elif mutation == "quantity":
                row["quantity"] = 4
            elif mutation == "deadline":
                row["protection_until"] = 0
            elif mutation == "party":
                row["reserved_party"] = None
            elif mutation == "player":
                row["reserved_player"] = 8
            elif mutation == "zero-share":
                del row["shares"]["42"]
            elif mutation == "amount":
                row["shares"]["41"]["remaining"] = 4
            elif mutation == "share-player":
                row["shares"]["42"]["player"] = 10
            elif mutation == "share-id":
                row["shares"]["43"] = row["shares"].pop("42")
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                assert_preserved_loot(self.before, final)

    def test_restart_snapshot_storage_checks_ownership_and_uses_exclusive_creation(self):
        from unittest.mock import MagicMock, Mock

        path = MagicMock()
        harness = SimpleNamespace(mode="full", run_dir=path, owned_database_fingerprint=Mock())
        for label in ("before", "stopped", "after", "final"):
            save_restart_snapshot(harness, label, {"fixture": "한글"})
            path.__truediv__.assert_called_with(f"restart-{label}.json")
            path.__truediv__.return_value.open.assert_called_with("x", encoding="utf-8")
        self.assertEqual(harness.owned_database_fingerprint.call_count, 4)
        path.reset_mock()
        harness.owned_database_fingerprint.side_effect = RuntimeError("unowned")
        with self.assertRaisesRegex(RuntimeError, "unowned"):
            save_restart_snapshot(harness, "final", {})
        path.__truediv__.assert_not_called()
        harness.mode = "quick"
        with self.assertRaises(AssertionError):
            save_restart_snapshot(harness, "before", {})
        harness.mode = "full"
        with self.assertRaises(AssertionError):
            save_restart_snapshot(harness, "../escape", {})
        path.__truediv__.assert_not_called()

    def test_legacy_empty_and_invalid_observation_bounds_cannot_pass(self):
        for snapshot in ("before", "final"):
            before, final = deepcopy(self.before), deepcopy(self.final)
            (before if snapshot == "before" else final)["loot"]["2"]["native"] = False
            with self.subTest(snapshot=snapshot), self.assertRaises(AssertionError):
                assert_preserved_loot(before, final)
        with self.assertRaises(AssertionError):
            assert_preserved_loot(dict(self.before, loot={}), self.final)
        for started, completed in ((9, 60), (60, 59)):
            with self.subTest(started=started, completed=completed), self.assertRaises(AssertionError):
                assert_preserved_loot(self.before, dict(self.final, observed_at=started, completed_at=completed))


class SmokeRestartTests(TestCase):
    def test_full_boss_purchase_accepts_boots_previously_obtained_by_drop(self):
        class PurchaseObserved(Exception):
            pass

        from world.rules import purchase_price

        player = SimpleNamespace(state={"credits": 10000, "inventory": [
            {"id": "folding_shield", "count": 1, "identity": "shield-uuid", "selector": "접이식방패 1"},
            {"id": "non_slip_boots", "count": 1, "identity": "dropped-boots-uuid",
             "selector": "미끄럼방지탐사화 1"}]}, semantic_logs=[])

        async def act(command, predicate):
            if command == "미끄럼방지탐사화 사":
                player.state["inventory"].append({"id": "non_slip_boots", "count": 1,
                                                  "identity": "purchased-boots-uuid",
                                                  "selector": "미끄럼방지탐사화 2"})
                player.state["credits"] -= purchase_price("non_slip_boots")
                self.assertTrue(predicate(player.state), "기존 drop 1개 + 정상 구매 1개를 허용해야 한다")
                raise PurchaseObserved

        player.act = act
        closeout = Closeout(SimpleNamespace(players=(player, None, None)))
        with patch.object(closeout, "floor", new_callable=AsyncMock), patch(
            "scripts.smoke_closeout.travel_to", new_callable=AsyncMock
        ), self.assertRaises(PurchaseObserved):
            asyncio.run(closeout.prepare_boss())
        self.assertEqual(player.state["inventory"][1]["identity"], "dropped-boots-uuid")
        self.assertEqual(player.state["inventory"][1]["count"], 1)
        self.assertEqual(player.state["credits"], 10000 - purchase_price("non_slip_boots"))

    def test_restart_reuses_directory_database_and_ports_without_fixture_reset(self):
        harness = smoke_harness.Harness("full")
        harness.run_dir = Path("same-isolated-db")
        harness.env = {"PRIMAL_SMOKE_MODE": "full"}
        harness.ports = {"ws": 12345}
        events = []
        stopped = {"players": {"fixture": {"profile": {"xp": 12}}}}

        def checkpoint():
            events.append("checkpoint")
            return stopped

        async def ready():
            self.assertTrue(harness.restarting)
            events.append("ready")

        with patch.object(harness, "graceful_stop", side_effect=lambda: events.append("graceful_stop")), patch.object(
            harness, "start", side_effect=lambda: events.append("start")
        ), patch.object(harness, "ready", side_effect=ready), patch.object(
            harness, "checkpoint", side_effect=checkpoint
        ), patch.object(harness, "prepare") as prepare:
            self.assertEqual(asyncio.run(harness.restart()), stopped)
        self.assertEqual(events, ["graceful_stop", "checkpoint", "start", "ready"])
        self.assertEqual(harness.run_dir, Path("same-isolated-db"))
        self.assertEqual(harness.ports, {"ws": 12345})
        self.assertEqual(harness.env, {"PRIMAL_SMOKE_MODE": "full"})
        self.assertFalse(harness.restarting)
        prepare.assert_not_called()

    def test_restart_failure_restores_premature_exit_monitoring(self):
        harness = smoke_harness.Harness("full")
        with patch.object(harness, "graceful_stop") as shutdown, patch.object(harness, "checkpoint", return_value={}), patch.object(
            harness, "start", side_effect=RuntimeError("start failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                asyncio.run(harness.restart())
        shutdown.assert_called_once_with()
        self.assertFalse(harness.restarting)
