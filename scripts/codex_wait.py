"""허용된 장기 검사와 CI 대기를 독립 Worker에 맡기는 CLI."""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import codex_watch as watch

DEFAULT_TIMEOUTS = {"test": 1800, "smoke": 900, "smoke-full": 2700, "ci": 2700, "release": 5400}
_workers = {}


def lookup_attempt(repo, run_id):
    query = subprocess.run(["gh", "run", "view", str(run_id), "--repo", repo, "--json", "attempt"],
                           capture_output=True, timeout=10, check=False)
    if query.returncode:
        raise ValueError("CI Attempt 사전 조회 실패")
    attempt = json.loads(query.stdout).get("attempt")
    if not isinstance(attempt, int) or attempt < 1:
        raise ValueError("CI Attempt 응답 오류")
    return attempt


def validate_request(root, *, kind, thread=None, timeout=None, ready_timeout=5, command="test",
                     labels=(), parallel=None, reverse=False, repo=None, run_id=None, sha=None,
                     attempt=None, pr=None, release=False):
    root = watch.repository_root(root)
    if kind not in {"local", "ci"}:
        raise ValueError("지원하지 않는 검사 종류입니다.")
    if command not in {"test", "smoke", "smoke-full"}:
        raise ValueError("test/smoke/smoke-full만 허용합니다.")
    if thread is not None and (not thread or len(thread) > 200 or thread.startswith("-") or any(ord(c) < 32 for c in thread)):
        raise ValueError("잘못된 thread입니다.")
    timeout = timeout if timeout is not None else DEFAULT_TIMEOUTS[command if kind == "local" else "release" if release else "ci"]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (timeout, ready_timeout)):
        raise ValueError("Timeout은 유한한 양수여야 합니다.")
    request = {"repository": str(root), "kind": kind, "thread": thread, "timeout": timeout,
               "python": sys.executable,
               "ready_timeout": ready_timeout}
    if kind == "local":
        if command not in {"test", "smoke", "smoke-full"}:
            raise ValueError("test/smoke/smoke-full만 허용합니다.")
        if command != "test" and (labels or parallel is not None or reverse):
            raise ValueError("labels/parallel/reverse는 test에만 사용할 수 있습니다.")
        if parallel is not None and (not isinstance(parallel, int) or parallel < 1):
            raise ValueError("parallel은 양의 정수여야 합니다.")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", label) for label in labels):
            raise ValueError("테스트 label은 Python 경로여야 합니다.")
        request.update(command=command, labels=list(labels), parallel=parallel, reverse=reverse,
                       baseline=watch.snapshot(root))
    else:
        if repo is None:
            remote = watch.git(root, "remote", "get-url", "origin").decode().strip()
            match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", remote)
            repo = match.group(1) if match else None
        if not repo or not watch.REPO_PATTERN.fullmatch(repo):
            raise ValueError("--repo owner/name이 필요합니다.")
        if not isinstance(run_id, int) or run_id < 1 or not re.fullmatch(r"[0-9a-fA-F]{40}", sha or ""):
            raise ValueError("양의 Run ID와 전체40자리 SHA가 필요합니다.")
        if any(value is not None and (not isinstance(value, int) or value < 1) for value in (attempt, pr)):
            raise ValueError("Attempt/PR은 양의 정수여야 합니다.")
        if attempt is None:
            attempt = lookup_attempt(repo, run_id)
        request.update(repo=repo, run_id=run_id, sha=sha.lower(), attempt=attempt, pr=pr)
    identity = {k: v for k, v in request.items() if k not in {"thread", "ready_timeout"}}
    request["key"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return request


def status(root, job_id):
    directory = watch.job_directory(root, job_id)
    child = _workers.get(job_id)
    if child is not None and child.poll() is not None:
        del _workers[job_id]
    try:
        request = watch.read_json(directory / "request.json")
        watch.validate_saved_request(request)
        if request.get("job_id") != job_id or request.get("repository") != str(Path(root).resolve()):
            raise ValueError("Job 소유 정보 불일치")
        result_path = directory / "result.json"
        if result_path.exists():
            result = watch.read_json(result_path)
            if result.get("nonce") != request.get("nonce") or result.get("job_id") != job_id or result.get("status") not in watch.TERMINAL:
                raise ValueError("결과 형식/소유 정보 오류")
            elapsed = result.get("elapsed_seconds")
            if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError("결과 실행시간 오류")
            if result["status"] == "PASSED" and (result.get("exit_code") != 0 or result.get("cleanup_verified") is not True):
                raise ValueError("성공 결과의 종료 코드/정리 근거 오류")
            expected = (("repo", "run_id", "attempt", "sha", "pr") if request["kind"] == "ci" else
                        ("repository", "python", "command", "labels", "parallel", "reverse"))
            target = result.get("target")
            if result["status"] not in {"ERROR", "TIMED_OUT"} or result.get("phase") not in {"worker_start", "READY"}:
                if result.get("kind") != request["kind"] or not isinstance(target, dict) or target != {name: request.get(name) for name in expected}:
                    raise ValueError("결과 검증 대상 오류")
            if result["status"] == "PASSED":
                if not isinstance(result.get("finished_at"), (int, float)) or not math.isfinite(result["finished_at"]) or result["finished_at"] <= 0:
                    raise ValueError("성공 결과의 완료 시각 누락")
                if request["kind"] == "local":
                    if result.get("baseline") != request["baseline"] or result.get("final_baseline") != request["baseline"] or result.get("test_status") != "PASSED":
                        raise ValueError("성공 결과의 실제 검증 기준 누락")
                else:
                    run = result.get("run")
                    if not isinstance(run, dict) or any(run.get(key) != value for key, value in
                            {"databaseId": request["run_id"], "attempt": request["attempt"], "headSha": request["sha"], "status": "completed", "conclusion": "success"}.items()):
                        raise ValueError("성공 결과의 실제 Run 근거 누락")
            return {**result, "notification": watch.read_json(directory / "notification.json"),
                    "result_path": str(result_path)}
        state = watch.read_json(directory / "state.json")
        if state.get("job_id") != job_id or state.get("nonce") != request.get("nonce") or state.get("status") not in watch.STATES or not isinstance(state.get("ready"), bool):
            raise ValueError("상태 형식/소유 정보 오류")
        if state["status"] in watch.TERMINAL:
            return {"job_id": job_id, "status": "INTERRUPTED", "result_missing": True,
                    "error": "최종 상태만 있고 결과가 없습니다."}
        if state["status"] == "RUNNING" and (not isinstance(state.get("worker_pid"), int) or not isinstance(state.get("worker_identity"), str) or not state["worker_identity"]):
            raise ValueError("Worker 실행 식별 정보 누락")
        if state.get("worker_pid"):
            alive = watch.identity_alive(state["worker_pid"], state.get("worker_identity"))
        else:
            alive = (time.time() < request["ready_deadline"] and
                     watch.identity_alive(request["parent_pid"], request.get("parent_identity")))
        if not alive:
            return {"job_id": job_id, "status": "INTERRUPTED", "result_missing": True,
                    "cleanup_verified": False, "error": "Worker 최종 결과가 없습니다. 프로세스 생존을 추정하지 않습니다."}
        return {**state, "result_path": str(result_path)}
    except (OSError, ValueError, KeyError) as error:
        return {"job_id": job_id, "status": "ERROR", "error": str(error)}


def spawn_worker(request, registration):
    """호출자가 등록 잠금을 유지한 동안 한 번만 Worker를 만든다."""
    root = Path(request["repository"])
    job_id = uuid.uuid4().hex
    directory = watch.job_directory(root, job_id)
    directory.mkdir()
    request = {**request, "job_id": job_id, "nonce": uuid.uuid4().hex,
               "parent_pid": os.getpid(), "parent_identity": watch.process_identity(os.getpid()),
               "ready_deadline": time.time() + request["ready_timeout"]}
    watch.atomic_json(directory / "request.json", request)
    watch.atomic_json(directory / "state.json", {"job_id": job_id, "nonce": request["nonce"],
                                                "status": "STARTING", "ready": False})
    watch.atomic_json(directory / "notification.json", {"status": "NOT_REQUESTED", "attempted": False,
                                                       "session_resumed": "UNVERIFIED"})
    (directory / "output.log").touch()
    watch.atomic_json(registration, {"job_id": job_id})
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                "close_fds": True} if os.name == "nt" else {"start_new_session": True, "close_fds": True})
    try:
        with (directory / "output.log").open("ab") as log:
            _workers[job_id] = subprocess.Popen([sys.executable, str(Path(__file__).with_name("codex_watch.py")),
                                               str(root), job_id], stdin=subprocess.DEVNULL, stdout=log,
                                              stderr=subprocess.STDOUT, cwd=root, **options)
    except OSError as error:
        result = {"job_id": job_id, "nonce": request["nonce"], "status": "ERROR", "exit_code": None,
                  "elapsed_seconds": 0, "error": str(error), "phase": "worker_start"}
        watch.atomic_json(directory / "result.json", result)
        registration.unlink()
        return result
    return request


def await_ready(request, duplicate):
    root, job_id = Path(request["repository"]), request["job_id"]
    directory = watch.job_directory(root, job_id)
    while time.time() < request["ready_deadline"]:
        value = status(root, job_id)
        if value.get("ready") or value["status"] in watch.TERMINAL - {"INTERRUPTED"}:
            return {"job_id": job_id, "status": value["status"], "ready": value.get("ready", False), "duplicate": duplicate}
        time.sleep(0.01)
    value = status(root, job_id)
    if value.get("ready") or value["status"] in watch.TERMINAL - {"INTERRUPTED"}:
        return {"job_id": job_id, "status": value["status"], "ready": value.get("ready", False), "duplicate": duplicate}
    if duplicate:
        return {"job_id": job_id, "status": "TIMED_OUT", "ready": False, "duplicate": True,
                "error": "원래 Worker의 READY를 확인하지 못했습니다. 원 작업 결과는 덮어쓰지 않습니다."}
    # 늦게 뜬 Worker는 deadline/cancel을 확인하고 검사 실행 전에 종료한다.
    (directory / "cancel").touch()
    result = {"job_id": job_id, "nonce": request["nonce"], "status": "TIMED_OUT", "ready": False,
              "exit_code": None, "elapsed_seconds": request["ready_timeout"], "phase": "READY"}
    watch.atomic_json(directory / "result.json", result)
    watch.atomic_json(directory / "state.json", result)
    watch.release_registration(root, request)
    return {"job_id": job_id, "status": "TIMED_OUT", "ready": False,
            "error": "READY 제한시간 초과. status로 Worker의 최종 정리를 확인하세요."}


def start(request):
    root = Path(request["repository"])
    duplicate = False
    with watch.registry_lock(root):
        registration = watch.work_root(root) / (".active-" + request["key"] + ".json")
        if registration.exists():
            old = watch.read_json(registration)
            existing = status(root, old["job_id"])
            if existing["status"] in {"STARTING", "RUNNING"}:
                request = watch.read_json(watch.job_directory(root, old["job_id"]) / "request.json")
                duplicate = True
            elif existing["status"] in {"ERROR", "INTERRUPTED"}:
                raise ValueError("활성 등록/정리를 확인할 수 없습니다. 기존 Job을 수동 확인하세요.")
        if not duplicate:
            request = spawn_worker(request, registration)
            if request.get("status") == "ERROR":
                return request
    return await_ready(request, duplicate)


def cancel(root, job_id):
    value = status(root, job_id)
    if value["status"] in {"STARTING", "RUNNING"}:
        (watch.job_directory(root, job_id) / "cancel").touch()
        return {"job_id": job_id, "status": value["status"], "cancel_requested": True,
                "remote_run_cancelled": False}
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="kind", required=True)
    local = commands.add_parser("local")
    local.add_argument("--command", choices=("test", "smoke", "smoke-full"), default="test")
    local.add_argument("labels", nargs="*")
    local.add_argument("--parallel", type=int)
    local.add_argument("--reverse", action="store_true")
    ci = commands.add_parser("ci")
    ci.add_argument("--repo")
    ci.add_argument("--run-id", type=int, required=True)
    ci.add_argument("--sha", required=True)
    ci.add_argument("--attempt", type=int)
    ci.add_argument("--pr", type=int)
    ci.add_argument("--release", action="store_true")
    for command in (local, ci):
        command.add_argument("--thread")
        command.add_argument("--timeout", type=float)
        command.add_argument("--ready-timeout", type=float, default=5)
    for name in ("status", "cancel"):
        commands.add_parser(name).add_argument("job_id")
    args = vars(parser.parse_args(argv))
    try:
        root = watch.repository_root(Path.cwd())
        kind = args.pop("kind")
        if kind in {"status", "cancel"}:
            result = (status if kind == "status" else cancel)(root, args["job_id"])
        else:
            result = start(validate_request(root, kind=kind, **args))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] in {"STARTING", "RUNNING", "PASSED"} else 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
