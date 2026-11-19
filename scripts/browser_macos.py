"""macOS 브라우저의 일회성 launchd 리소스 coalition과 종료 증거."""

import ctypes
import errno
import json
import os
import plistlib
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from time import monotonic, sleep

# XNU proc_info_private.h / sys/coalition.h. ABI 또는 권한이 다르면 실행을 거부한다.
PROC_PIDUNIQIDENTIFIERINFO = 17
PROC_PIDCOALITIONINFO = 20
PROC_ALL_PIDS = 1
LOCAL_PEERTOKEN = 6
SOL_LOCAL = 0
BOOTSTRAP_UNKNOWN_SERVICE = 113
GONE = (errno.ESRCH, errno.ENOENT)
AuditToken = ctypes.c_uint32 * 8


class Coalition:
    def __init__(self):
        self.api = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.api.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                         ctypes.c_void_p, ctypes.c_int]
        self.api.proc_pidinfo.restype = ctypes.c_int
        self.api.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
        self.api.proc_listpids.restype = ctypes.c_int
        self.api.coalition_info_resource_usage.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
        self.api.proc_signal_with_audittoken.argtypes = [ctypes.POINTER(AuditToken), ctypes.c_int]
        self.api.proc_signal_with_audittoken.restype = ctypes.c_int

    def pidinfo(self, pid, flavor, layout):
        ctypes.set_errno(0)
        data = ctypes.create_string_buffer(layout.size)
        size = self.api.proc_pidinfo(pid, flavor, 0, data, len(data))
        if size == len(data):
            return layout.unpack(data)
        if size == 0:
            error = ctypes.get_errno()
            if error in GONE:
                return None
            if error:
                raise OSError(error, 'macOS 프로세스 식별 정보 조회 실패')
        raise RuntimeError('macOS 프로세스 식별 정보 크기 불일치')

    def identity(self, pid):
        info = self.pidinfo(pid, PROC_PIDUNIQIDENTIFIERINFO, struct.Struct('@16xQQII16x'))
        return (pid, info[2]) if info else None

    def group(self, pid):
        info = self.pidinfo(pid, PROC_PIDCOALITIONINFO, struct.Struct('@Q32x'))
        return info[0] if info else None

    def count(self, coalition):
        # 구조체 선두의 tasks_started, tasks_exited만 사용한다. 두 값은 한 조회에서 읽는다.
        usage = (ctypes.c_uint64 * 256)()
        if self.api.coalition_info_resource_usage(coalition, usage, ctypes.sizeof(usage)) != 0:
            raise RuntimeError('macOS coalition 활성 작업 수 조회 실패')
        return usage[0] - usage[1]

    def pids(self):
        size = self.api.proc_listpids(PROC_ALL_PIDS, 0, None, 0)
        if size <= 0:
            raise RuntimeError('macOS 프로세스 목록 크기 조회 실패')
        data = (ctypes.c_int * (size // ctypes.sizeof(ctypes.c_int) + 64))()
        used = self.api.proc_listpids(PROC_ALL_PIDS, 0, data, ctypes.sizeof(data))
        if not 0 < used < ctypes.sizeof(data) or used % ctypes.sizeof(ctypes.c_int):
            raise RuntimeError('macOS 프로세스 목록 불완전')
        return data[:used // ctypes.sizeof(ctypes.c_int)]

    def send(self, identity, signum):
        # XNU가 PID와 generation을 함께 검증한 proc에만 신호를 보낸다.
        pid, version = identity
        token = AuditToken(0, 0, 0, 0, 0, pid, 0, version)
        # libproc는 syscall의 errno를 양의 반환값으로 변환한다.
        result = self.api.proc_signal_with_audittoken(ctypes.byref(token), signum)
        if result == 0:
            return True
        if result == errno.ESRCH:
            return False
        if result < 0:
            raise RuntimeError(f'macOS 신호 API 반환 규약 불일치 ({result})')
        raise OSError(result, 'macOS 소유 프로세스 신호 실패')

    def member(self, pid, coalition):
        # 두 조회 사이 PID가 교체되었다면 coalition 관측과 다른 정체성을 결합하지 않는다.
        first = self.identity(pid)
        if first and self.group(pid) == coalition and self.identity(pid) == first:
            return first
        return None

    def drain(self, coalition, timeout, *, guardian=None, poll=lambda: None):
        deadline = monotonic() + timeout
        final = deadline + 2
        signaled = set()
        known_pids = set()
        denied = set()
        forced = 0
        while True:
            poll()
            active = self.count(coalition)
            expected = int(guardian is not None)
            if active == expected:
                return forced
            if monotonic() >= final:
                raise TimeoutError(f'macOS coalition 소유 자손 종료 미확인: 활성 {active - expected}, '
                                   f'조회 제한 {len(denied)}건(이전 소유 PID {len(denied & known_pids)}건)')
            denied.clear()
            signum = signal.SIGTERM if monotonic() < deadline else signal.SIGKILL
            for pid in self.pids():
                if not pid or (guardian and pid == guardian[0]):
                    continue
                try:
                    identity = self.member(pid, coalition)
                except PermissionError:
                    # 이 PID에 신호를 보내지 않는다. 목록과 독립된 active 수가 종료 판정을 맡는다.
                    denied.add(pid)
                    continue
                if identity is None:
                    continue
                known_pids.add(pid)
                if (identity, signum) in signaled:
                    continue
                if self.send(identity, signum):
                    signaled.add((identity, signum))
                    forced += signum == signal.SIGKILL
            sleep(0.05)


def write_result(path, payload):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload), encoding='utf-8')
    temporary.replace(path)


def launchctl(*args):
    return subprocess.run(['/bin/launchctl', *args], stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode


def peer_identity(connection):
    token = struct.unpack('@8I', connection.getsockopt(SOL_LOCAL, LOCAL_PEERTOKEN, 32))
    return token[5], token[7]


class MacBrowser:
    """전용 launchd 작업을 만들고 연결이 인증된 뒤에만 Node 설정을 전달한다."""

    def __init__(self, command, *, cwd, env, stdout, control):
        self.control = control.resolve()
        self.proof = self.control.with_suffix('.clean')
        self.api = Coalition()
        self.coalition = None
        self.guardian = None
        self.connection = None
        self.registered = False
        self.stop_error = None
        self.disconnect = None
        self.forced = None  # 실행기가 활성 작업 수 0을 확인한 뒤에만 기록한다.
        self.guardian_forced = False
        domain = f'gui/{os.getuid()}'
        label = 'org.primalzone.browser.' + uuid.uuid4().hex
        self.target = f'{domain}/{label}'
        try:
            # sockaddr_un 길이 제한. 실행 환경은 launchd 설정에 저장하지 않는다.
            with tempfile.TemporaryDirectory(prefix='primal-browser-', dir='/tmp') as directory:
                address = str(Path(directory)/'control')
                plist = Path(directory)/'job.plist'
                with socket.socket(socket.AF_UNIX) as listener:
                    listener.bind(address)
                    listener.listen(1)
                    listener.settimeout(8)
                    with plist.open('xb') as file:
                        plistlib.dump({'Label': label, 'RunAtLoad': True, 'AbandonProcessGroup': True,
                                       'ProgramArguments': [sys._base_executable, str(Path(__file__).resolve()), address]},
                                      file)
                    try:
                        if launchctl('bootstrap', domain, str(plist)) != 0:
                            raise RuntimeError('macOS launchd 브라우저 작업 등록 실패')
                    finally:
                        # bootstrap 응답과 인터럽트가 경합해도 등록된 자기 label을 회수한다.
                        self.registered = True
                    self.connection, _ = listener.accept()
                self.connection.settimeout(8)
                peer = peer_identity(self.connection)
                pid = peer[0]
                coalition = self.api.group(pid)
                if (coalition is None or coalition <= 1 or self.api.member(pid, coalition) != peer
                        or coalition == self.api.group(os.getpid())
                        or self.api.count(coalition) != 1):
                    raise RuntimeError('macOS 전용 coalition 소유권 확인 실패')
                self.guardian, self.coalition = peer, coalition
                # stdout 파일 핸들과 실행 환경은 권한이 제한된 소켓을 통해서만 전달한다.
                socket.send_fds(self.connection, [b'B'], [stdout.fileno()])
                payload = [str(self.control), coalition, os.fspath(cwd), command, env]
                self.connection.sendall(json.dumps(payload).encode() + b'\n')
                if self.connection.recv(1) != b'R':
                    raise RuntimeError('macOS 브라우저 보호 프로세스 준비 실패')
        except BaseException as original:
            try:
                self.stop(1)
            except BaseException as cleanup:
                raise BaseExceptionGroup('macOS 시작 및 소유 경계 정리 실패', [original, cleanup]) from original
            raise

    def result(self, timeout):
        connection = self.connection
        deadline = monotonic() + timeout
        while not self.control.exists():
            if connection is None or select.select([connection], [], [], max(0, min(0.05, deadline-monotonic())))[0]:
                if not self.control.exists():
                    raise RuntimeError('macOS 브라우저 보호 프로세스 조기 종료: 실행 결과 미확인')
            if monotonic() >= deadline and not self.control.exists():
                raise subprocess.TimeoutExpired('owned-browser', timeout)
        return json.loads(self.control.read_text(encoding='utf-8'))

    def stop(self, timeout):
        errors = []
        if self.connection is not None:
            connection = self.connection
            self.connection = None
            try:
                self.disconnect = self._request_stop(connection, timeout)
            except BaseException as error:
                self.stop_error = error
            try:
                connection.close()
            except BaseException as error:
                if self.stop_error is None:
                    self.stop_error = error
                else:
                    errors.append(error)

        try:
            if self.coalition is not None and self.forced is None:
                self._verify_stop(timeout)
            if self.registered:
                # 종료 증거를 얻기 전에는 재시도에 필요한 coalition 등록을 유지한다.
                launchctl('bootout', self.target)
                if launchctl('print', self.target) != BOOTSTRAP_UNKNOWN_SERVICE:
                    raise RuntimeError('macOS 소유 launchd 작업 해제 실패')
                self.registered = False
        except BaseException as error:
            errors.append(error)
            if self.disconnect is not None and self.forced is None and self.stop_error is None:
                errors.insert(0, self.disconnect)

        if self.stop_error is not None:
            errors.insert(0, self.stop_error)
            if self.forced is not None:
                try:
                    # Guardian의 .clean은 변경하지 않고 독립 복구의 근거만 별도 저장한다.
                    write_result(self.control.with_suffix('.recovery.json'), {
                        'stopped': False, 'active': 0, 'forced': self.forced,
                        'guardian_forced': self.guardian_forced, 'job_removed': not self.registered,
                    })
                except BaseException as error:
                    errors.append(error)
        if len(errors) > 1:
            raise BaseExceptionGroup('macOS 브라우저 종료 및 복구 실패', errors)
        if errors:
            raise errors[0]
        return self.forced if self.forced is not None else 0

    @staticmethod
    def _request_stop(connection, timeout):
        # 시작 단계 소켓에도 적용하며 쓰기와 응답 대기 양쪽에 제한을 둔다.
        connection.settimeout(max(5, timeout + 3))
        try:
            connection.sendall(f'{timeout}\n'.encode())
            if connection.recv(1):
                raise RuntimeError('macOS 브라우저 정리 제어 응답 불일치')
            # EOF는 Guardian 종료의 후보이며 .clean과 커널 작업 수를 별도 확인한다.
        except TimeoutError as error:
            raise TimeoutError('macOS 브라우저 정리 제어 Timeout') from error
        except (BrokenPipeError, ConnectionResetError) as error:
            # Node 시작 실패처럼 Guardian이 증거를 쓰고 먼저 종료한 경우도 있다.
            return error

    def _verify_stop(self, timeout):
        if self.stop_error is None:
            try:
                proof = json.loads(self.proof.read_text(encoding='utf-8'))
                if (proof['stopped'] is not True or proof['active'] != 0
                        or type(proof['forced']) is not int or proof['forced'] < 0):
                    raise ValueError('정리 증거 값 불일치')
            except (OSError, ValueError, TypeError, KeyError) as error:
                self.stop_error = RuntimeError('macOS 브라우저 보호 프로세스 정리 증거 없음')
                self.stop_error.__cause__ = self.disconnect or error
            else:
                # EOF 직후에는 Guardian task의 커널 회수가 진행 중일 수 있다.
                deadline = monotonic() + 2
                while self.api.count(self.coalition) != 0:
                    if monotonic() >= deadline:
                        self.stop_error = RuntimeError('macOS 정리 증거와 실제 coalition 작업 수 불일치')
                        self.stop_error.__cause__ = self.disconnect
                        break
                    sleep(0.05)
                else:
                    self.forced = proof['forced']
                    return

        # 등록 때 확인한 Guardian의 PID 세대를 사용한다. 새 프로세스에 신호를 보낼 수 없다.
        if not self.guardian_forced:
            self.guardian_forced = self.api.send(self.guardian, signal.SIGKILL)
        self.forced = self.api.drain(self.coalition, timeout)


def guardian(address):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.connect(address)
        marker, descriptors, _, _ = socket.recv_fds(connection, 1, 1)
        if marker != b'B' or len(descriptors) != 1:
            for fd in descriptors:
                os.close(fd)
            return 1
        with os.fdopen(descriptors[0], 'wb') as stdout, connection.makefile('rb', buffering=0) as requests:
            config = requests.readline()
            if not config:
                return 1
            control, coalition, cwd, command, env = json.loads(config)
            control = Path(control)
            api = Coalition()
            own = api.member(os.getpid(), coalition)
            if not own or api.count(coalition) != 1:
                return 1
            # Guardian은 제어 소켓으로 정리한다. exec된 Node에는 기본 SIGTERM 동작을 넘긴다.
            signal.signal(signal.SIGTERM, lambda *_: None)
            write_result(control.with_suffix('.ready'), {'coalition': coalition, 'guardian': own[0]})
            connection.sendall(b'R')
            process = None
            reported = False
            try:
                process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                           stdout=stdout, stderr=subprocess.STDOUT)
                while not select.select([connection], [], [], 0.05)[0]:
                    if not reported and process.poll() is not None:
                        write_result(control, {'code': process.returncode})
                        reported = True
                request = requests.readline()
                timeout = min(15, max(0, float(request))) if request.strip() else 5
            except BaseException:
                timeout = 1
                write_result(control, {'error': 'launch-failed'})
                reported = True
            forced = api.drain(coalition, timeout, guardian=own, poll=process.poll if process else lambda: None)
            if process:
                process.wait(timeout=2)
                if not reported:
                    write_result(control, {'code': process.returncode})
            write_result(control.with_suffix('.clean'), {'stopped': True, 'forced': forced, 'active': 0})
    return 0


if __name__ == '__main__':
    raise SystemExit(guardian(sys.argv[1]))
