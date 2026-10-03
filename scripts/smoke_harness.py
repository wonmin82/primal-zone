"""한 실행이 소유한 DB와 foreground Evennia Portal/Server만 관리한다."""

import asyncio
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from time import monotonic
from urllib.request import urlopen

from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
SERVER_READY_TIMEOUT = 60
SETUP_TIMEOUT = 120
SHUTDOWN_TIMEOUT = 15


def fingerprint(path):
    if not path.exists():
        return None
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def smoke_environment(run, mode, ports):
    # 사용자 DB/PYTHONPATH/설정이 격리 환경으로 유입되지 않게 한다.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PRIMAL_DB_", "PRIMAL_SMOKE_"))}
    env.update(PYTHONUTF8="1", PYTHONUNBUFFERED="1", PYTHONPATH=str(run / "game"),
               DJANGO_SETTINGS_MODULE="server.conf.settings_smoke",
               PRIMAL_SMOKE_RUN_DIR=str(run), PRIMAL_SMOKE_MODE=mode)
    for name, port in ports.items():
        env["PRIMAL_SMOKE_" + name.upper()] = str(port)
    return env


class Harness:
    def __init__(self, mode):
        self.mode = mode
        self.run_dir = None
        self.processes = []
        self.handles = []
        self.ports = {}
        self.reservations = []
        self.restarting = False
        self.credentials = [(name, secrets.token_urlsafe(24))
                            for name in ("검증가", "검증나", "검증다")]

    def prepare(self):
        parent = ROOT / "work" / "smoke"
        parent.mkdir(parents=True, exist_ok=True)
        self.run_dir = Path(tempfile.mkdtemp(prefix=self.mode + "-", dir=parent)).resolve()
        (self.run_dir / ".primal-smoke").touch()
        game = self.run_dir / "game"
        for folder in ("commands", "typeclasses", "world", "web", "server/conf"):
            shutil.copytree(ROOT / "game" / folder, game / folder,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "secret_settings.py"))
        (game / "server" / "logs").mkdir()
        (game / "server" / "conf" / "secret_settings.py").write_text(
            f"SECRET_KEY = {secrets.token_urlsafe(48)!r}\n", encoding="utf-8")
        # OS가 고른 서로 다른 포트를 setup 중 예약한다. 다른 서버를 종료하지 않는다.
        for name in ("http", "internal", "ws", "amp"):
            reservation = socket.socket()
            reservation.bind(("127.0.0.1", 0))
            self.ports[name] = reservation.getsockname()[1]
            self.reservations.append(reservation)
        self.env = smoke_environment(self.run_dir, self.mode, self.ports)
        with (self.run_dir / "setup.log").open("w", encoding="utf-8") as log:
            subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke_setup.py")],
                           cwd=game, env=self.env, input=json.dumps(self.credentials), text=True,
                           stdout=log, stderr=subprocess.STDOUT, timeout=SETUP_TIMEOUT, check=True)

    def start(self):
        library = Path(importlib.util.find_spec("evennia").origin).parent
        for reservation in self.reservations:
            reservation.close()
        self.reservations.clear()
        # Launcher의 daemon/자동 재시작을 쓰지 않아 두 프로세스의 실제 exit를 추적한다.
        for name, module in (("portal", "server/portal/portal.py"), ("server", "server/server.py")):
            log = (self.run_dir / f"{name}.log").open("a", encoding="utf-8")
            self.handles.append(log)
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {
                "start_new_session": True}
            args = [sys.executable, "-c", "from twisted.scripts.twistd import run; run()",
                    "--nodaemon", "--logfile=-", f"--python={library / module}"]
            if os.name != "nt":
                args.append(f"--pidfile={self.run_dir / (name + '.pid')}")
            process = subprocess.Popen(args, cwd=self.run_dir / "game", env=self.env,
                                       stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, **flags)
            self.processes.append((name, process))

    def check_alive(self):
        for name, process in self.processes:
            if process.poll() is not None:
                raise RuntimeError(f"{name} 조기 종료 ({process.returncode}), 로그: "
                                   f"{self.run_dir / (name + '.log')}")

    async def ready(self):
        deadline = monotonic() + SERVER_READY_TIMEOUT
        url = f"http://127.0.0.1:{self.ports['http']}/"

        def http_ready():
            with urlopen(url, timeout=3) as response:
                return response.status == 200

        while monotonic() < deadline:
            self.check_alive()
            try:
                if await asyncio.to_thread(http_ready):
                    async with connect(self.ws_url, subprotocols=["v1.evennia.com"], open_timeout=1):
                        return
            except (OSError, TimeoutError):
                pass
            await asyncio.sleep(0.2)
        raise TimeoutError(f"서버 readiness 실패, 로그: {self.run_dir}")

    @property
    def ws_url(self):
        return f"ws://127.0.0.1:{self.ports['ws']}"

    async def supervise(self, scenario):
        async def monitor():
            while True:
                if not self.restarting:
                    self.check_alive()
                await asyncio.sleep(0.2)

        work, health = asyncio.create_task(scenario), asyncio.create_task(monitor())
        try:
            done, _ = await asyncio.wait((work, health), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
        finally:
            for task in (work, health):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, health, return_exceptions=True)

    async def restart(self):
        """같은 DB/설정/포트에서 소유한 Portal과 Server를 실제로 재시작한다."""
        self.restarting = True
        try:
            await asyncio.to_thread(self.stop)
            self.processes.clear()
            self.handles.clear()
            # 실행 중 checkpoint와 종료 사이에도 정상 전투 라운드가 진행될 수 있다.
            # 실제 프로세스 종료 시점의 DB를 재시작 보존 검사의 기준으로 삼는다.
            stopped = await asyncio.to_thread(self.checkpoint)
            self.start()
            await self.ready()
            return stopped
        finally:
            self.restarting = False

    def checkpoint(self):
        output = subprocess.check_output(
            [sys.executable, str(ROOT / "scripts" / "smoke_snapshot.py")],
            cwd=self.run_dir / "game", env=self.env, text=True, timeout=SETUP_TIMEOUT)
        return json.loads(output.splitlines()[-1])

    def stop(self):
        failures = []
        for name, process in reversed(self.processes):
            try:
                if process.poll() is None:
                    if os.name == "nt":
                        process.terminate()
                    else:
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=SHUTDOWN_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        if os.name == "nt":
                            process.kill()
                        else:
                            os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=SHUTDOWN_TIMEOUT)
                if process.poll() is None:
                    failures.append(name)
            except (OSError, subprocess.TimeoutExpired) as error:
                failures.append(f"{name}: {error}")
        for handle in self.handles:
            handle.close()
        for reservation in self.reservations:
            reservation.close()
        if failures:
            raise RuntimeError("smoke process cleanup 실패: " + ", ".join(failures))

    def discard(self):
        # 생성한 정확한 경로만 제거한다. 외부 경로·상위 디렉터리 삭제는 차단한다.
        parent = (ROOT / "work" / "smoke").resolve()
        if (self.run_dir.parent != parent or not (self.run_dir / ".primal-smoke").is_file()
                or any(process.poll() is None for _, process in self.processes)):
            raise RuntimeError("소유권/프로세스 확인 없이 smoke 디렉터리를 삭제할 수 없습니다.")
        shutil.rmtree(self.run_dir)
