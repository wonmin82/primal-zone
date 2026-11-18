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


class Coalition:
    def __init__(self):
        self.api = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.api.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                         ctypes.c_void_p, ctypes.c_int]
        self.api.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
        self.api.coalition_info_resource_usage.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
        self.api.proc_signal_with_audittoken.argtypes = [ctypes.c_void_p, ctypes.c_int]

    def pidinfo(self, pid, flavor, layout):
        ctypes.set_errno(0)
        data = ctypes.create_string_buffer(layout.size)
        size = self.api.proc_pidinfo(pid, flavor, 0, data, len(data))
        if size == len(data):
            return layout.unpack(data)
        if size == 0 and ctypes.get_errno() in GONE:
            return None
        raise RuntimeError('macOS 프로세스 식별 정보 조회 실패')

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
        token = (ctypes.c_uint32 * 8)(0, 0, 0, 0, 0, pid, 0, version)
        ctypes.set_errno(0)
        if self.api.proc_signal_with_audittoken(token, signum) == 0:
            return True
        if ctypes.get_errno() == errno.ESRCH:
            return False
        raise OSError(ctypes.get_errno(), 'macOS 소유 프로세스 신호 실패')

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
        forced = 0
        while True:
            poll()
            if self.count(coalition) == int(guardian is not None):
                return forced
            if monotonic() >= final:
                raise TimeoutError('macOS coalition 소유 자손 종료 미확인')
            signum = signal.SIGTERM if monotonic() < deadline else signal.SIGKILL
            for pid in self.pids():
                if not pid or (guardian and pid == guardian[0]):
                    continue
                identity = self.member(pid, coalition)
                if identity is None or (identity, signum) in signaled:
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
        if self.connection is not None:
            try:
                self.connection.sendall(f'{timeout}\n'.encode())
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.connection.settimeout(max(5, timeout+3))
            try:
                if self.connection.recv(1):
                    raise RuntimeError('macOS 브라우저 정리 제어 응답 불일치')
            except ConnectionResetError:
                pass
            self.connection.close()
            self.connection = None
        if self.coalition is not None and self.registered:
            reason = None
            if not self.proof.exists():
                # Guardian이 사라져도 독립적으로 등록한 coalition의 자손만 회수한다.
                reason = 'guardian-proof-missing'
            else:
                # 소켓 EOF와 커널의 guardian task 회수 사이에는 짧은 경합이 가능하다.
                deadline = monotonic() + 2
                while self.api.count(self.coalition) != 0:
                    if monotonic() >= deadline:
                        reason = 'coalition-not-empty'
                        break
                    sleep(0.05)
            if reason:
                forced = self.api.drain(self.coalition, timeout)
                write_result(self.proof, {'stopped': False, 'forced': forced, 'active': 0, 'error': reason})
        if self.registered:
            if (launchctl('bootout', self.target)
                    and launchctl('print', self.target) != BOOTSTRAP_UNKNOWN_SERVICE):
                raise RuntimeError('macOS 소유 launchd 작업 해제 실패')
            self.registered = False
        if self.coalition is None:
            return 0  # 소유권 검증/설정 전에는 Node를 시작할 수 없다.
        proof = json.loads(self.proof.read_text(encoding='utf-8'))
        if proof.get('stopped') is not True or proof.get('active') != 0:
            raise RuntimeError('macOS 브라우저 보호 프로세스 정리 증거 없음')
        return proof['forced']


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
