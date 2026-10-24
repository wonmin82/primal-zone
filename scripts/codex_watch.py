"""Codex와 독립적으로 검사를 기다리고 소유 실행 결과만 보존한다."""

import contextlib
import ctypes
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

TERMINAL = {"PASSED", "FAILED", "CANCELLED", "TIMED_OUT", "STALE", "INTERRUPTED", "ERROR"}
STATES = TERMINAL | {"STARTING", "RUNNING"}
JOB_PATTERN = re.compile(r"[0-9a-f]{32}")
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SOURCE_SUFFIXES = {".py", ".js", ".cjs", ".mjs", ".json", ".toml", ".yaml", ".yml",
                   ".md", ".csv", ".txt", ".html", ".css", ".ini", ".cfg", ".lock"}


def atomic_json(path, value):
    """완성되지 않은 JSON을 독자가 관측하지 않도록 같은 디렉터리에서 교체한다."""
    path = Path(path)
    temporary = path.with_name(".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    path = Path(path)
    if path.is_symlink() or path.is_junction():
        raise ValueError("JSON 링크 파일을 읽지 않습니다.")
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("JSON object가 필요합니다.")
    return value


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)


def repository_root(directory):
    return Path(git(directory, "rev-parse", "--show-toplevel").decode().strip()).resolve()


def safe_source(name, *, untracked=False):
    """비밀·플레이 DB·로그는 열지 않으며 관련 소스/설정만 내용 지문에 포함한다."""
    path = Path(name)
    lower = name.lower().replace("\\", "/")
    parts = lower.split("/")
    if any(part in {".git", ".venv", "node_modules", "work", "logs", ".static", ".aws", ".ssh", "secrets", "credentials"} for part in parts):
        return False
    secret_modules = {"secret_settings.py", "secrets.py", "credentials.py", "credential.py", "passwords.py", "tokens.py"}
    if path.name.lower() in secret_modules or (path.suffix != ".py" and any(
            word in path.name.lower() for word in ("secret", "credential", "password", "token"))):
        return False
    if path.name.lower() in {"auth.json", "auth.yaml", "auth.yml", "auth.toml", "auth.ini"}:
        return False
    if path.name.startswith(".env") or path.suffix.lower() in {".db", ".db3", ".sqlite", ".sqlite3", ".log", ".pem", ".key", ".cert"}:
        return False
    if untracked and not (parts[0] in {"game", "scripts", "docs", ".github", ".codex"}
                          or path.name in {"AGENTS.md", "README.md", ".gitignore", "pyproject.toml", "uv.lock", "package.json", "package-lock.json"}):
        return False
    return path.suffix.lower() in SOURCE_SUFFIXES or path.name == ".gitignore"


def snapshot(root):
    root = Path(root).resolve()
    tracked = set(git(root, "ls-files", "--cached", "-z").split(b"\0"))
    files = tracked | set(git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0"))
    digest = hashlib.sha256()
    count = 0
    for encoded in sorted(files):
        if not encoded:
            continue
        name = os.fsdecode(encoded)
        if not safe_source(name, untracked=encoded not in tracked):
            continue
        path = root / name
        digest.update(encoded + b"\0")
        if path.is_symlink() or path.is_junction() or any(parent.is_symlink() or parent.is_junction() for parent in path.parents if parent != root):
            # 링크가 가리키는 외부 파일/비밀을 읽지 않는다.
            digest.update(b"SYMLINK\0" + (os.fsencode(os.readlink(path)) if path.is_symlink() else b"PARENT"))
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"MISSING")
        digest.update(b"\0")
        count += 1
    branch = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short", "-q", "HEAD"],
                            capture_output=True, check=False)
    return {"repository": str(root), "branch": branch.stdout.decode().strip() or None,
            "head": git(root, "rev-parse", "HEAD").decode().strip(),
            "fingerprint": digest.hexdigest(), "source_files": count}


def work_root(root):
    root = Path(root).resolve()
    target = root / "work" / "codex-watch"
    for parent in (root / "work", target):
        if parent.is_symlink() or parent.is_junction() or parent.resolve() != parent:
            raise ValueError("감시기 경로에 symlink/junction을 사용할 수 없습니다.")
        parent.mkdir(exist_ok=True)
    return target


def job_directory(root, job_id):
    if not JOB_PATTERN.fullmatch(job_id):
        raise ValueError("잘못된 Job ID입니다.")
    directory = work_root(root) / job_id
    if directory.is_symlink() or directory.is_junction() or directory.resolve().parent != work_root(root):
        raise ValueError("Job 경로가 소유 범위를 벗어났습니다.")
    return directory


@contextlib.contextmanager
def registry_lock(root):
    path = work_root(root) / ".registry.lock"
    if path.is_symlink() or path.is_junction():
        raise ValueError("등록 잠금 링크를 열지 않습니다.")
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def windows_kernel():
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "GetCurrentProcess": ([], w.HANDLE),
        "GetProcessTimes": ([w.HANDLE, w.LPVOID, w.LPVOID, w.LPVOID, w.LPVOID], w.BOOL),
        "GetExitCodeProcess": ([w.HANDLE, w.LPVOID], w.BOOL),
        "CreateJobObjectW": ([w.LPVOID, w.LPCWSTR], w.HANDLE),
        "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL),
        "QueryInformationJobObject": ([w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, w.LPVOID], w.BOOL),
        "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
        "IsProcessInJob": ([w.HANDLE, w.HANDLE, w.LPVOID], w.BOOL),
        "TerminateProcess": ([w.HANDLE, w.UINT], w.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        getattr(kernel, name).argtypes = arguments
        getattr(kernel, name).restype = result
    return kernel


def process_identity(pid):
    """PID 재사용을 시작 시각으로 구분한다. 확인할 수 없으면 살아 있다고 추정하지 않는다."""
    try:
        if os.name == "nt":
            from ctypes import wintypes
            kernel = windows_kernel()
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                creation, exit_time, user, system = (wintypes.FILETIME() for _ in range(4))
                if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                                              ctypes.byref(system), ctypes.byref(user)):
                    return None
                code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                    return None
                return f"{creation.dwHighDateTime}:{creation.dwLowDateTime}"
            finally:
                kernel.CloseHandle(handle)
        if sys.platform.startswith("linux"):
            stat = Path(f"/proc/{pid}/stat").read_text()
            tail = stat[stat.rfind(")") + 2:].split()
            return None if tail[0] == "Z" else tail[19]
        result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart=", "-o", "stat="],
                                capture_output=True, text=True, timeout=2, check=False)
        text = result.stdout.strip()
        return text.rsplit(None, 1)[0] if result.returncode == 0 and text and "Z" not in text.split()[-1] else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def identity_alive(pid, identity):
    return isinstance(pid, int) and bool(identity) and process_identity(pid) == identity


def validate_saved_request(request):
    """정상 JSON이라도 허용된 검사 외 명령으로 변조/손상된 요청은 실행하지 않는다."""
    for name in ("repository", "python", "job_id", "nonce", "key"):
        if not isinstance(request.get(name), str) or not request[name]:
            raise ValueError("저장 요청 필수 식별 정보 누락")
    if Path(request["python"]).resolve() != Path(sys.executable).resolve():
        raise ValueError("요청 Python과 Worker Python이 다릅니다.")
    if not JOB_PATTERN.fullmatch(request.get("job_id", "")) or not JOB_PATTERN.fullmatch(request.get("nonce", "")):
        raise ValueError("Job 식별자 오류")
    if not re.fullmatch(r"[0-9a-f]{64}", request.get("key", "")):
        raise ValueError("등록 식별자 오류")
    if not all(isinstance(request.get(name), (int, float)) and math.isfinite(request[name]) and request[name] > 0
               for name in ("timeout", "ready_timeout", "ready_deadline")):
        raise ValueError("저장된 Timeout 오류")
    if request.get("thread") is not None and (not isinstance(request["thread"], str) or not request["thread"]
            or len(request["thread"]) > 200 or request["thread"].startswith("-") or any(ord(c) < 32 for c in request["thread"])):
        raise ValueError("저장된 알림 대상 오류")
    if request.get("kind") == "local":
        baseline = request.get("baseline")
        if not isinstance(baseline, dict) or baseline.get("repository") != request["repository"]:
            raise ValueError("저장된 검증 기준 누락")
        if not isinstance(baseline.get("head"), str) or not re.fullmatch(r"[0-9a-f]{40}", baseline["head"]):
            raise ValueError("저장된 Git HEAD 오류")
        if not isinstance(baseline.get("fingerprint"), str) or not re.fullmatch(r"[0-9a-f]{64}", baseline["fingerprint"]):
            raise ValueError("저장된 소스 지문 오류")
        if not isinstance(baseline.get("source_files"), int) or baseline["source_files"] < 0 or baseline.get("branch") is not None and not isinstance(baseline["branch"], str):
            raise ValueError("저장된 소스/브랜치 정보 오류")
        command, labels = request.get("command"), request.get("labels")
        if command not in {"test", "smoke", "smoke-full"} or not isinstance(labels, list):
            raise ValueError("허용되지 않은 저장 검사 명령")
        if any(not isinstance(label, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", label) for label in labels):
            raise ValueError("저장된 테스트 label 오류")
        parallel = request.get("parallel")
        if parallel is not None and (not isinstance(parallel, int) or parallel < 1):
            raise ValueError("저장된 parallel 오류")
        if command != "test" and (labels or parallel is not None or request.get("reverse")):
            raise ValueError("저장된 검사 인자 오류")
    elif request.get("kind") == "ci":
        if not isinstance(request.get("repo"), str) or not isinstance(request.get("sha"), str) or not REPO_PATTERN.fullmatch(request["repo"]) or not re.fullmatch(r"[0-9a-f]{40}", request["sha"]):
            raise ValueError("저장된 CI 대상 오류")
        if any(not isinstance(request.get(name), int) or request[name] < 1 for name in ("run_id", "attempt")):
            raise ValueError("저장된 Run/Attempt 오류")
        if request.get("pr") is not None and (not isinstance(request["pr"], int) or request["pr"] < 1):
            raise ValueError("저장된 PR 오류")
    else:
        raise ValueError("저장된 검사 종류 오류")


class WindowsJob:
    """Worker와 그 자손만 포함하는 kill-on-close Job Object. 다른 프로세스 검색/종료 없음."""

    def __init__(self):
        from ctypes import wintypes

        class BASIC(ctypes.Structure):
            _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                        ("Flags", wintypes.DWORD), ("MinWS", ctypes.c_size_t),
                        ("MaxWS", ctypes.c_size_t), ("Active", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("Priority", wintypes.DWORD),
                        ("Scheduling", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("Basic", BASIC), ("IO", IO), ("ProcessMemory", ctypes.c_size_t),
                        ("JobMemory", ctypes.c_size_t), ("PeakProcess", ctypes.c_size_t), ("PeakJob", ctypes.c_size_t)]

        self.kernel = windows_kernel()
        self.handle = self.kernel.CreateJobObjectW(None, None)
        info = EXTENDED()
        info.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "소유 Job Object 초기화 실패")
        if not self.kernel.AssignProcessToJobObject(self.handle, self.kernel.GetCurrentProcess()):
            raise OSError(ctypes.get_last_error(), "Worker Job Object 할당 실패")

    def children(self):
        # QueryInformationJobObject의 process ID list는 pointer-width 정수다.
        buffer = ctypes.create_string_buffer(8 + 4096 * ctypes.sizeof(ctypes.c_size_t))
        if not self.kernel.QueryInformationJobObject(self.handle, 3, buffer, len(buffer), None):
            raise OSError(ctypes.get_last_error(), "소유 프로세스 목록 확인 실패")
        count = ctypes.c_uint32.from_buffer(buffer, 4).value
        values = (ctypes.c_size_t * count).from_buffer(buffer, 8)
        return [int(pid) for pid in values if pid != os.getpid()]

    def cleanup(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            children = self.children()
            if not children:
                return True
            for pid in children:
                handle = self.kernel.OpenProcess(0x0001 | 0x1000, False, pid)
                if handle:
                    try:
                        member = ctypes.c_int()
                        if self.kernel.IsProcessInJob(handle, self.handle, ctypes.byref(member)) and member.value:
                            self.kernel.TerminateProcess(handle, 1)
                    finally:
                        self.kernel.CloseHandle(handle)
            time.sleep(0.01)
        return not self.children()


class StopRequested(Exception):
    def __init__(self, state):
        self.state = state


def enable_subreaper():
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        if libc.prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "소유 자손 입양 초기화 실패")


class PosixTree:
    """소유 ancestry와 시작 identity를 추적한다. Smoke의 별도 session 자손도 포함한다."""

    def __init__(self):
        self.known = {}

    def observe(self):
        if sys.platform.startswith("linux"):
            queue = [os.getpid(), *self.known]
            seen = set()
            while queue:
                parent = queue.pop()
                if parent in seen:
                    continue
                seen.add(parent)
                if parent != os.getpid() and process_identity(parent) != self.known.get(parent):
                    continue
                try:
                    children = Path(f"/proc/{parent}/task/{parent}/children").read_text().split()
                except FileNotFoundError:
                    continue
                for child in children:
                    pid = int(child)
                    identity = process_identity(pid)
                    if identity:
                        self.known[pid] = identity
                        queue.append(pid)
        else:
            listing = subprocess.check_output(["ps", "-axo", "pid=,ppid=,lstart="], text=True)
            entries = [line.split(None, 2) for line in listing.splitlines() if line.strip()]
            parents = {os.getpid()} | {pid for pid, token in self.known.items() if process_identity(pid) == token}
            changed = True
            while changed:
                changed = False
                for pid_text, parent_text, _ in entries:
                    pid = int(pid_text)
                    if int(parent_text) in parents and pid not in parents:
                        identity = process_identity(pid)
                        if identity:
                            self.known[pid] = identity
                            parents.add(pid)
                            changed = True

    def cleanup(self, *, popen_pid):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.observe()
            alive = []
            for pid, identity in list(self.known.items()):
                if process_identity(pid) == identity:
                    alive.append(pid)
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if pid != popen_pid:
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        pass
            if not alive:
                self.known.clear()
                return True
            time.sleep(0.01)
        return False


class Execution:
    def __init__(self, directory, request, windows_job=None, *, honour_cancel=True):
        self.directory, self.request, self.windows_job = directory, request, windows_job
        self.deadline = time.monotonic() + request["timeout"]
        self.process = None
        self.process_group = None
        self.cleanup_verified = True
        self.tree = PosixTree() if os.name != "nt" else None
        self.last_exit_code = None
        self.honour_cancel = honour_cancel

    def check(self):
        if self.honour_cancel and (self.directory / "cancel").exists():
            raise StopRequested("CANCELLED")
        if time.monotonic() >= self.deadline:
            raise StopRequested("TIMED_OUT")

    def cleanup(self):
        if self.windows_job:
            self.cleanup_verified = self.windows_job.cleanup()
        elif self.process_group is not None:
            self.tree.observe()
            try:
                # 그룹 leader의 시작 identity가 바뀐 경우 새 그룹을 종료하지 않는다.
                if self.process and identity_alive(self.process.pid, self.tree.known.get(self.process.pid)):
                    os.killpg(self.process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                self.cleanup_verified = False
            if self.process:
                self.process.wait(timeout=3)
            self.cleanup_verified = self.cleanup_verified and self.tree.cleanup(popen_pid=self.process.pid)
            self.process_group = None
        if self.process:
            self.process.wait(timeout=3)
            self.last_exit_code = self.process.returncode
            self.process = None
        return self.cleanup_verified

    def run(self, args, *, capture=False):
        self.check()
        with (self.directory / "output.log").open("ab") as output:
            options = {"start_new_session": True} if os.name != "nt" else {}
            self.process = subprocess.Popen(args, cwd=self.request["repository"], stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE if capture else output,
                                            stderr=subprocess.PIPE if capture else subprocess.STDOUT,
                                            env={**os.environ, "PYTHONUTF8": "1"}, **options)
            self.process_group = self.process.pid if os.name != "nt" else None
            if self.tree:
                self.tree.known[self.process.pid] = process_identity(self.process.pid)
            try:
                while True:
                    if self.tree:
                        self.tree.observe()
                    self.check()
                    try:
                        stdout, stderr = self.process.communicate(timeout=0.03)
                        code = self.process.returncode
                        self.last_exit_code = code
                        break
                    except subprocess.TimeoutExpired:
                        continue
            except BaseException:
                self.cleanup()
                raise
            if not self.cleanup():
                raise RuntimeError("소유 자식 프로세스 정리를 확인하지 못했습니다.")
            return code, stdout or b"", stderr or b""


def gh_json(execution, args):
    code, stdout, _ = execution.run(["gh", *args], capture=True)
    if code:
        raise RuntimeError(f"GitHub 조회 오류(exit {code})")
    try:
        value = json.loads(stdout)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("GitHub 응답 JSON 오류") from error
    if not isinstance(value, dict):
        raise RuntimeError("GitHub 응답 형식 오류")
    return value


def ci_run(execution):
    request = execution.request
    args = ["run", "view", str(request["run_id"]), "--repo", request["repo"], "--json",
            "databaseId,attempt,headSha,status,conclusion,url"]
    first = gh_json(execution, args)
    attempt = request.get("attempt") or first.get("attempt")

    def matches(value):
        return (value.get("databaseId") == request["run_id"] and value.get("attempt") == attempt
                and value.get("headSha") == request["sha"])

    def pr_matches():
        if not request.get("pr"):
            return True
        value = gh_json(execution, ["pr", "view", str(request["pr"]), "--repo", request["repo"], "--json", "headRefOid"])
        return value.get("headRefOid") == request["sha"]

    if not matches(first) or not pr_matches():
        return {"status": "STALE", "exit_code": None, "run": first, "attempt": attempt}
    watch_code = None
    if first.get("status") != "completed":
        watch_code, _, _ = execution.run(["gh", "run", "watch", str(request["run_id"]), "--repo",
                                         request["repo"], "--exit-status", "--interval", "15"])
    final = gh_json(execution, args)
    result = {"run": final, "attempt": attempt, "watch_exit_code": watch_code,
              "exit_code": None, "scope": "specified_run_only"}
    if not matches(final) or not pr_matches():
        return {**result, "status": "STALE"}
    if final.get("status") != "completed":
        return {**result, "status": "ERROR", "error": "대기 종료 후 Run이 완료되지 않았습니다."}
    conclusion = final.get("conclusion")
    status = "PASSED" if conclusion == "success" else "CANCELLED" if conclusion == "cancelled" else "TIMED_OUT" if conclusion == "timed_out" else "FAILED"
    return {**result, "status": status, "exit_code": 0 if status == "PASSED" else 1}


def notify(directory, request, result, *, execution=None):
    path = directory / "notification.json"
    # 미확정/실패도 재전송하지 않는다. status가 결과 복구 경로다.
    current = read_json(path)
    if current.get("attempted") or not request.get("thread"):
        return
    notification = {"status": "FAILED", "attempted": True, "session_resumed": "UNVERIFIED"}
    atomic_json(path, notification)
    if sys.platform == "darwin":
        atomic_json(path, {**notification, "status": "UNSUPPORTED", "reason": "macOS 프로세스 소유 경계 미확인"})
        return
    if execution is None:
        atomic_json(path, {**notification, "status": "UNSUPPORTED", "reason": "프로세스 소유 경계 초기화 미완료"})
        return
    executable = shutil.which("codex.exe" if os.name == "nt" else "codex")
    if not executable:
        atomic_json(path, {**notification, "status": "UNSUPPORTED"})
        return
    guard = Execution(directory, {**request, "timeout": 15}, execution.windows_job, honour_cancel=False)
    final = notification
    try:
        guard.deadline = time.monotonic() + 5
        help_code, stdout, _ = guard.run([executable, "queue", "--help"], capture=True)
        help_text = stdout.decode(errors="replace")
        if help_code or "--thread" not in help_text or "--message" not in help_text:
            atomic_json(path, {**notification, "status": "UNSUPPORTED"})
            return
        # 외부 로그/오류 원문은 지시문에 넣지 않는다.
        message = (f"Codex watch: job={request['job_id']} status={result['status']} "
                   f"exit_code={result.get('exit_code')} elapsed={result['elapsed_seconds']:.3f}s "
                   f"result={directory / 'result.json'}")
        guard.deadline = time.monotonic() + 10
        code, _, _ = guard.run([executable, "queue", "--thread", request["thread"], "--message", message], capture=True)
        final = {**notification, "status": "ACCEPTED_UNCONFIRMED" if code == 0 else "FAILED", "queue_exit_code": code}
    except (OSError, RuntimeError, StopRequested, subprocess.SubprocessError):
        final = notification
    finally:
        try:
            verified = guard.cleanup()
        except (OSError, RuntimeError, subprocess.SubprocessError):
            verified = False
        if not verified:
            final = {**final, "status": "FAILED", "reason": "알림 소유 자손 정리 미확인"}
        # 미지원 help도 여기에서 정리 상태를 기록하며 결과 파일은 변경하지 않는다.
        if read_json(path).get("status") == "UNSUPPORTED" and verified:
            final = {**notification, "status": "UNSUPPORTED"}
        atomic_json(path, {**final, "cleanup_verified": verified})


def release_registration(root, request):
    with registry_lock(root):
        index = work_root(root) / (".active-" + request["key"] + ".json")
        try:
            if read_json(index).get("job_id") == request["job_id"]:
                index.unlink()
        except FileNotFoundError:
            pass


def finish(directory, request, result, started, *, execution=None):
    target_fields = (("repo", "run_id", "attempt", "sha", "pr") if request["kind"] == "ci" else
                     ("repository", "python", "command", "labels", "parallel", "reverse"))
    result = {**result, "job_id": request["job_id"], "nonce": request["nonce"],
              "kind": request["kind"], "elapsed_seconds": round(time.monotonic() - started, 3),
              "finished_at": time.time(), "baseline": request.get("baseline"),
              "worker_pid": os.getpid(), "worker_identity": process_identity(os.getpid()) if sys.platform != "darwin" else None,
              "target": {name: request.get(name) for name in target_fields}}
    atomic_json(directory / "result.json", result)
    atomic_json(directory / "state.json", {"status": result["status"], "ready": result.get("ready", False),
                                           "job_id": request["job_id"], "nonce": request["nonce"]})
    release_registration(request["repository"], request)
    notify(directory, request, result, execution=execution)


def run_worker(root, job_id):
    directory = job_directory(root, job_id)
    request = read_json(directory / "request.json")
    if request.get("job_id") != job_id or Path(request["repository"]).resolve() != Path(root).resolve():
        raise ValueError("Job 소유 정보가 일치하지 않습니다.")
    started = time.monotonic()
    execution = None
    ready = False
    try:
        validate_saved_request(request)
        if sys.platform == "darwin":
            result = {"status": "ERROR", "exit_code": None, "phase": "platform_initialization",
                      "platform": "darwin", "test_status": "NOT_STARTED", "cleanup_verified": False,
                      "error": "macOS의 별도 session 자손 소유권을 확인할 수 없어 검사 실행 전에 중단합니다."}
            result["ready"] = False
            finish(directory, request, result, started)
            return
        if time.time() >= request["ready_deadline"] or (directory / "cancel").exists():
            raise StopRequested("TIMED_OUT")
        job = WindowsJob() if os.name == "nt" else None
        if os.name != "nt":
            enable_subreaper()
        identity = process_identity(os.getpid())
        if not identity:
            raise RuntimeError("Worker 시작 정보를 확인할 수 없습니다.")
        execution = Execution(directory, request, job)
        atomic_json(directory / "state.json", {"status": "RUNNING", "ready": True,
                                               "worker_pid": os.getpid(), "worker_identity": identity,
                                               "job_id": job_id, "nonce": request["nonce"]})
        ready = True
        if time.time() >= request["ready_deadline"]:
            raise StopRequested("TIMED_OUT")
        execution.check()
        if request["kind"] == "local":
            before = snapshot(root)
            if before != request["baseline"]:
                result = {"status": "STALE", "exit_code": None, "test_status": "NOT_STARTED"}
            else:
                command = [sys.executable, str(Path(root) / "scripts" / "dev.py"), request["command"],
                           *request["labels"]]
                if request.get("parallel"):
                    command += ["--parallel", str(request["parallel"])]
                if request.get("reverse"):
                    command.append("--reverse")
                code, _, _ = execution.run(command)
                after = snapshot(root)
                actual = "PASSED" if code == 0 else "FAILED"
                result = {"status": actual if after == before else "STALE", "test_status": actual,
                          "exit_code": code, "final_baseline": after}
        else:
            result = ci_run(execution)
    except StopRequested as error:
        result = {"status": error.state, "exit_code": execution.last_exit_code if execution else None}
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        result = {"status": "ERROR", "exit_code": execution.last_exit_code if execution and request["kind"] == "local" else None,
                  "error": str(error)}
        if request["kind"] == "local":
            result["test_status"] = ("NOT_STARTED" if result["exit_code"] is None else
                                     "PASSED" if result["exit_code"] == 0 else "FAILED")
    finally:
        if execution:
            try:
                verified = execution.cleanup()
            except (OSError, subprocess.SubprocessError):
                verified = False
            if not verified:
                result = {**result, "original_status": result["status"], "status": "ERROR",
                          "error": "소유 자식 프로세스 정리를 확인하지 못했습니다."}
            result["cleanup_verified"] = verified
    result["ready"] = ready
    finish(directory, request, result, started, execution=execution)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Worker는 codex_wait.py에서 시작합니다.")
    run_worker(Path(sys.argv[1]), sys.argv[2])
