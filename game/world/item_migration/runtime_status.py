"""별도 reactor에서 Evennia launcher AMP 상태를 확인하는 read-only probe."""

import json
import os
import subprocess


def runtime_processes():
    """Portal이 끊긴 orphan Server도 차단한다. PID 파일은 사용하지 않는다.

    다른 world의 Evennia도 보수적으로 차단한다. process 목록을 읽을 수 없거나
    Python command line을 확인할 수 없으면 offline 증명이 아니므로 실패한다.
    """
    if os.name == "nt":
        result = subprocess.run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
            "ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -match '^(python|twistd|evennia)' } | "
            "Select-Object ProcessId,CommandLine)",
        ], capture_output=True, text=True, encoding="utf-8", timeout=10, check=True)
        rows = json.loads(result.stdout)
        commands = [row["CommandLine"] for row in rows]
    else:
        result = subprocess.run(["ps", "-eo", "comm=,args="], capture_output=True,
                                text=True, timeout=10, check=True)
        commands = [line.split(None, 1)[1] for line in result.stdout.splitlines()
                    if line.split() and line.split()[0].startswith(("python", "twistd", "evennia"))]
    if not commands or any(not command for command in commands):
        raise ValueError("Python process command line을 확인할 수 없습니다.")
    return [command for command in commands if any(path in command.lower().replace("\\", "/")
            for path in ("evennia/server/server.py", "evennia/server/portal/portal.py"))]


def failed_status(failure):
    from twisted.internet.error import ConnectionRefusedError

    # Upstream query_status는 모든 errback을 NOT RUNNING으로 출력한다.
    # 연결 거절만 정지 후보이며 timeout/프로토콜 오류는 정지로 해석하지 않는다.
    if failure.check(ConnectionRefusedError):
        return {"portal": False, "server": False, "proof": "connection-refused"}
    return {"error": f"Evennia AMP status 조회 실패: {failure.type.__name__} ({failure.value})"}


def main():
    from evennia.server import evennia_launcher as launcher
    from twisted.internet import reactor

    # 현재 management command와 동일한 settings/GAME_DIR. DB 검사나 world 초기화는 하지 않는다.
    launcher.SETTINGS_DOTPATH = os.environ["DJANGO_SETTINGS_MODULE"]
    launcher.init_game_directory(os.getcwd(), check_db=False)
    # Windows의 연결 거절 통지가 upstream 기본 2초보다 늦을 수 있다.
    # 게임 timing/settings는 그대로 두고 이 read-only probe만 10초까지 기다린다.
    launcher.AMP_CONNECT_TIMEOUT = 10
    outcome = {}
    deadline = None

    def finish(value):
        if outcome:
            return
        outcome.update(value)
        if deadline is not None and deadline.active():
            deadline.cancel()
        reactor.stop()

    def received(response):
        try:
            portal, server, *_ = launcher._parse_status(response)
            if type(portal) is not bool or type(server) is not bool:
                raise ValueError("잘못된 AMP status")
            finish({"portal": portal, "server": server, "proof": "amp"})
        except Exception:
            finish({"error": "AMP status 응답을 해석할 수 없습니다."})

    def failed(failure):
        finish(failed_status(failure))

    # 연결은 되었지만 AMP 응답이 없는 경우에도 child 자체가 종료한다.
    # Windows venv launcher 부모만 outer timeout으로 kill하고 child를 남기지 않는다.
    deadline = reactor.callLater(12, finish, {"error": "Evennia AMP status 응답 timeout"})
    reactor.callWhenRunning(launcher.send_instruction, launcher.PSTATUS, None, received, failed)
    reactor.run()
    if not outcome.get("error") and outcome.get("portal") is False and outcome.get("server") is False:
        try:
            if runtime_processes():
                outcome["error"] = "Evennia Portal/Server process가 실행 중입니다."
        except Exception:
            outcome["error"] = "Evennia process 정지 여부를 확인할 수 없습니다."
    print(json.dumps(outcome))


if __name__ == "__main__":
    main()
