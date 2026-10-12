"""브라우저 실행의 소유 경계: Windows Job / 식별자가 고정된 POSIX 그룹."""

import ctypes
import json
import os
import select
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from time import monotonic, sleep


class WindowsJob:
    """핸들을 유지하는 Job에만 종료를 요청한다. PID 트리를 재탐색하지 않는다."""

    def __init__(self, name, create=True):
        from ctypes import wintypes as w

        class Limits(ctypes.Structure):
            _fields_ = [('user', ctypes.c_int64), ('job', ctypes.c_int64), ('flags', w.DWORD),
                        ('min', ctypes.c_size_t), ('max', ctypes.c_size_t), ('active', w.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [('basic', Limits), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

        class Accounting(ctypes.Structure):
            _fields_ = [('times', ctypes.c_int64 * 4), ('faults', w.DWORD), ('total', w.DWORD),
                        ('active', w.DWORD), ('terminated', w.DWORD)]

        self.accounting = Accounting
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([w.LPVOID, w.LPCWSTR], w.HANDLE),
            'OpenJobObjectW': ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
            'SetInformationJobObject': ([w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL),
            'QueryInformationJobObject': ([w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, w.LPVOID], w.BOOL),
            'AssignProcessToJobObject': ([w.HANDLE, w.HANDLE], w.BOOL),
            'TerminateJobObject': ([w.HANDLE, w.UINT], w.BOOL),
            'GetCurrentProcess': ([], w.HANDLE),
            'CloseHandle': ([w.HANDLE], w.BOOL),
        }
        for key, (arguments, result) in signatures.items():
            function = getattr(self.api, key)
            function.argtypes, function.restype = arguments, result
        self.handle = (self.api.CreateJobObjectW(None, name) if create else
                       self.api.OpenJobObjectW(0x1F003F, False, name))
        self.check(self.handle)
        if create:
            try:
                if ctypes.get_last_error() == 183:
                    raise RuntimeError('이미 존재하는 Job은 소유 경계로 채택하지 않음')
                limits = Extended()
                limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; breakaway 없음
                self.check(self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits),
                                                           ctypes.sizeof(limits)))
            except BaseException as original:
                try:
                    self.close()
                except BaseException as cleanup:
                    raise BaseExceptionGroup('Job 설정 및 핸들 정리 실패', [original, cleanup]) from original
                raise

    @staticmethod
    def check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    def assign_current(self):
        self.check(self.api.AssignProcessToJobObject(self.handle, self.api.GetCurrentProcess()))

    def active(self):
        info = self.accounting()
        self.check(self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info),
                                                     ctypes.sizeof(info), None))
        return info.active

    def terminate(self):
        self.check(self.api.TerminateJobObject(self.handle, 1))

    def close(self):
        if self.handle:
            self.check(self.api.CloseHandle(self.handle))
            self.handle = None


def until(condition, timeout):
    deadline = monotonic() + timeout
    while not condition():
        if monotonic() >= deadline:
            raise TimeoutError('소유 브라우저 프로세스 정리 Timeout')
        sleep(0.05)


def subreaper():
    """Playwright의 detached Chromium도 부모 종료 뒤 이 보호 프로세스가 입양한다."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Linux 소유 자식 입양 설정 실패')


def reap_children(node, timeout):
    """입양된 실제 자식에 열린 pidfd만 사용. 다른 그룹/PID 재사용과 무관하다."""
    handles = {}
    forced = 0
    deadline = monotonic() + timeout
    final = deadline + max(timeout, 2)
    try:
        while True:
            node.poll()  # 원본 Node 종료 코드는 Popen이 관리한다.
            children = Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split()
            for value in children:
                pid = int(value)
                if pid in handles:
                    continue
                fd = None
                try:
                    fd = os.pidfd_open(pid)
                    # fd를 연 뒤에도 커널의 현재 부모 관계를 확인한다.
                    status = Path(f'/proc/{pid}/status').read_text()
                    if f'PPid:\t{os.getpid()}\n' not in status:
                        os.close(fd)
                        continue
                    handles[pid] = fd
                    signal.pidfd_send_signal(fd, signal.SIGTERM)
                except (ProcessLookupError, FileNotFoundError):
                    if fd is not None and pid not in handles:
                        os.close(fd)
                    continue
            for pid, fd in list(handles.items()):
                if select.select([fd], [], [], 0)[0]:
                    os.close(fd)
                    del handles[pid]
                    if pid != node.pid:
                        try:
                            os.waitpid(pid, os.WNOHANG)
                        except ChildProcessError:
                            pass
            node.poll()
            if not handles and not Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip():
                return forced
            if monotonic() >= deadline:
                for fd in handles.values():
                    try:
                        signal.pidfd_send_signal(fd, signal.SIGKILL)
                        forced += 1
                    except ProcessLookupError:
                        pass
                deadline = final + 1  # 각 핸들에 대한 강제 신호는 한 단계로 제한한다.
            if monotonic() >= final:
                raise TimeoutError('Linux 입양 자식 종료 확인 실패')
            sleep(0.05)
    finally:
        for fd in handles.values():
            os.close(fd)


class OwnedBrowser:
    """자식 생성 전에 소유권을 확정하는 작은 보호 프로세스를 실행한다."""

    def __init__(self, command, *, cwd, env, stdout, control):
        self.control = Path(control)
        self.ready = self.control.with_suffix('.ready')
        if self.control.exists() or self.ready.exists():
            raise RuntimeError('기존 실행의 소유권/결과 파일을 재사용하지 않음')
        self.returncode = None
        self.stopped = False
        self.job = None
        if os.name != 'nt' and sys.platform != 'linux':
            raise RuntimeError('현재 브라우저 소유 수명 검증은 Windows/Linux만 지원함')
        name = 'PrimalBrowser-' + uuid.uuid4().hex if os.name == 'nt' else '-'
        if os.name == 'nt':
            self.job = WindowsJob(name)
        try:
            self.process = subprocess.Popen(
                [sys._base_executable, str(Path(__file__).resolve()), str(self.control), name, *command],
                cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=stdout, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
            until(lambda: self.ready.exists() or self.process.poll() is not None, 10)
            if not self.ready.exists():
                raise RuntimeError('브라우저 소유권 등록 실패: 자식 실행을 허용하지 않음')
        except BaseException as original:
            try:
                if hasattr(self, 'process'):
                    # ready 이전 오류도 이 Popen 핸들/아직 살아 있는 독립 그룹만 정리한다.
                    if self.process.poll() is None:
                        if self.job:
                            self.process.terminate()
                        elif os.getpgid(self.process.pid) == self.process.pid:
                            os.killpg(self.process.pid, signal.SIGKILL)
                        self.process.wait(timeout=5)
                    self.process.stdin.close()
                if self.job:
                    if self.job.active():
                        self.job.terminate()
                        until(lambda: self.job.active() == 0, 5)
                    self.job.close()
            except BaseException as cleanup:
                raise BaseExceptionGroup('실행 시작 및 소유 경계 정리 실패', [original, cleanup]) from original
            raise

    def wait(self, timeout):
        deadline = monotonic() + timeout
        while not self.control.exists():
            if self.process.poll() is not None:
                raise RuntimeError('브라우저 보호 프로세스 조기 종료: 소유권/실행 결과 미확인')
            if monotonic() >= deadline:
                raise subprocess.TimeoutExpired('owned-browser', timeout)
            sleep(0.05)
        result = json.loads(self.control.read_text(encoding='utf-8'))
        if 'error' in result:
            raise RuntimeError('브라우저 프로세스 시작/소유권 등록 실패')
        self.returncode = result['code']
        return self.returncode

    def stop(self, timeout=5):
        if self.stopped:
            return
        if self.job:
            # 부모 종료와 무관하게 Job 전체의 실제 active count를 검사한다.
            if self.job.active():
                if self.process.poll() is None:
                    try:
                        self.process.send_signal(signal.CTRL_BREAK_EVENT)
                    except OSError:
                        # 콘솔 부재/부모 종료 경합에서도 핸들이 보증한 Job을 정리한다.
                        pass
                    try:
                        until(lambda: self.job.active() == 0, timeout)
                    except TimeoutError:
                        pass
                if self.job.active():
                    self.job.terminate()
                    until(lambda: self.job.active() == 0, timeout)
            self.process.wait(timeout=timeout)
            self.process.stdin.close()
            self.job.close()
        else:
            # 보호 프로세스가 살아 있는 동안 PGID를 다른 실행이 재사용할 수 없다.
            proof = self.control.with_suffix('.clean')
            if self.process.poll() is not None and not proof.exists():
                raise RuntimeError('POSIX 소유 그룹 식별자 보호 실패: 그룹에 신호를 보내지 않음')
            if self.process.poll() is None and os.getpgid(self.process.pid) != self.process.pid:
                raise RuntimeError('POSIX 소유 그룹 불일치')
            if not self.process.stdin.closed:
                try:
                    if self.process.poll() is None and not proof.exists():
                        self.process.stdin.write((str(timeout)+'\n').encode())
                        self.process.stdin.flush()
                except BrokenPipeError:
                    self.process.wait(timeout=max(5, timeout * 2 + 3))
                    if not proof.exists():
                        raise
                finally:
                    try:
                        self.process.stdin.close()
                    except BrokenPipeError:
                        self.process.wait(timeout=max(5, timeout * 2 + 3))
                        if not proof.exists():
                            raise
            self.process.wait(timeout=max(5, timeout * 2 + 3))
            if not proof.exists():
                raise RuntimeError('Linux 소유 자식 정리 증거 없음')
            verified = json.loads(proof.read_text(encoding='utf-8'))
            if verified.get('stopped') is not True:
                raise RuntimeError('Linux 소유 자식 정리 미완료')
            self.forced_count = verified['forced']
        self.stopped = True


def guardian(control, name, command):
    # 아직 자식이 없는 단계에서 Job 등록. 기존 외부 Job과 충돌하면 fail-closed.
    job = None
    process = None
    try:
        if os.name == 'nt':
            job = WindowsJob(name, create=False)
            job.assign_current()
            # 실행기만 마지막 Job 핸들을 보유한다. 실행기 소실 시 kill-on-close도 유효하다.
            job.close()
            job = None
        else:
            signal.signal(signal.SIGTERM, lambda *_: None)
            subreaper()
        # 자식 실행 전에 소유권/신호 handler가 확정됐다는 rendezvous.
        control.with_suffix('.ready').touch()
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL)
        if os.name != 'nt':
            reported = False
            while True:
                code = process.poll()
                if code is not None and not reported:
                    temporary = control.with_suffix('.tmp')
                    temporary.write_text(json.dumps({'code': code}), encoding='utf-8')
                    temporary.replace(control)
                    reported = True
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    request = sys.stdin.buffer.readline().decode().strip()
                    timeout = min(15, max(0, float(request))) if request else 5
                    forced = reap_children(process, timeout)
                    control.with_suffix('.clean').write_text(json.dumps({'stopped': True, 'forced': forced}), encoding='utf-8')
                    if not reported:
                        control.write_text(json.dumps({'code': process.returncode}), encoding='utf-8')
                    return 0
        code = process.wait()
        temporary = control.with_suffix('.tmp')
        temporary.write_text(json.dumps({'code': code}), encoding='utf-8')
        temporary.replace(control)
    except BaseException:
        control.write_text(json.dumps({'error': 'launch-failed'}), encoding='utf-8')
        if job:
            job.close()
        if os.name != 'nt' and process is None:
            # 등록/exec 시작 실패: 생성된 자식이 없는 경계를 별도로 증명한다.
            control.with_suffix('.clean').write_text(json.dumps({'stopped': True, 'forced': 0}), encoding='utf-8')
        return 1
    if job:
        job.close()


if __name__ == '__main__':
    raise SystemExit(guardian(Path(sys.argv[1]), sys.argv[2], sys.argv[3:]))
