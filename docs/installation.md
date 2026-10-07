# 원시구역 설치 안내

로컬 PC에 게임 서버를 설치하고 웹 브라우저로 접속하는 방법입니다. 아래 설치 명령은 Windows PowerShell 기준입니다. 명령을 한 줄씩 실행하고 성공 여부를 확인한 뒤 다음 단계로 진행하세요.

## Fresh installation과 legacy upgrade

현재 프로젝트에는 보존·전환해야 할 실제 플레이 DB가 없습니다. 새 플레이의 기본 운영 경로는 **fresh empty SQLite + single Evennia server**입니다. 아래 1~6절은 fresh installation을 설명합니다. 개발 DB 파일이 있으면 빈 DB로 오인하거나 삭제하지 마세요.

Fresh 경로는 빈 DB → `dev.py setup`의 Django schema 생성 → 첫 `dev.py start`의 `initialize_fresh()` → `ItemRuntime.version=1` → native world bootstrap → 새 Explorer 생성입니다. Starter ItemEntity를 직접 만들며 legacy inventory를 생성한 뒤 변환하지 않습니다. Fresh DB에서는 `migrate-items --apply`/`--cutover`를 실행하지 않습니다.

과거 개발 DB·구버전 설치본·오래된 백업이 있는 경우만 **legacy compatibility upgrade**를 사용합니다. Server/Portal 정지 → backup → code update → dependency sync → schema migration → maintenance mode → `migrate-items --dry-run` → `--apply` → `--verify` → `--cutover` → maintenance 해제 → server start 순서입니다. 정확한 명령·warning 처리·retry/rollback 경계는 [아이템 migration 운영 절차](item-migration.md)를 따릅니다. 기존 DB는 startup/login 시 자동 변환하지 않으며 cutover 전 일반 runtime은 migration-required로 거절합니다.

Migration tooling은 fresh install 필수 단계가 아니라 historical DB upgrade/backup restoration/regression 대상입니다. PostgreSQL은 [향후 전환 계획](postgresql-transition.md)이며 현재 지원 topology와 [Phase 7](phase7-final-integration-audit.md) 완료 조건에 포함하지 않습니다.

## 필요한 환경

| 항목 | 필요한 환경과 역할 |
| --- | --- |
| 운영체제 | Windows에서 로컬 실행을 확인했습니다. Linux는 GitHub Actions에서 자동 검사를 수행합니다. macOS의 실제 실행은 아직 검증하지 않았습니다. |
| 터미널 | Windows에서는 PowerShell을 사용합니다. |
| Git | 저장소 다운로드와 코드 업데이트에 사용합니다. |
| uv | Python과 프로젝트 의존성을 설치·관리합니다. |
| Python | **3.13.x**가 필요합니다. 프로젝트의 지원 범위는 `>=3.13,<3.14`입니다. |
| 브라우저 | JavaScript와 WebSocket을 지원하는 브라우저가 필요합니다. |
| 인터넷 | 최초 설치 시 저장소, Python과 의존성을 다운로드하는 데 필요합니다. |
| 데이터베이스 | 기본값은 SQLite이며 별도의 DB 서버 설치가 필요하지 않습니다. |

Evennia 등 Python 의존성은 `uv.lock`에 맞춰 자동으로 설치됩니다. Node.js와 npm은 로컬 설치에 필요하지 않습니다. GitHub Actions의 Node.js는 CI에서 사용하는 Action의 실행 환경입니다.

설치한 PC와 LAN에서 접속할 수 있는 기본 실행을 제공합니다. 외부 공개 서버 운영에 필요한 인증서·프록시 등은 별도 구성이 필요합니다.

## 1. Git과 uv 설치

Git이 없다면 [Git 공식 다운로드 페이지](https://git-scm.com/downloads)에서 설치합니다.

Windows에서 WinGet을 사용할 수 있다면 PowerShell에서 uv를 설치합니다.

```powershell
winget install --id astral-sh.uv -e
```

WinGet을 사용할 수 없거나 다른 설치 방법이 필요하면 [uv 공식 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)를 참고합니다.

설치 후 PowerShell을 새로 열고 두 명령이 인식되는지 확인합니다.

```powershell
git --version
uv --version
```

## 2. 저장소 다운로드

프로젝트를 보관할 폴더에서 실행합니다.

```powershell
git clone https://github.com/wonmin82/primal-zone.git
cd primal-zone
```

이후 명령은 `pyproject.toml`과 `scripts` 폴더가 있는 저장소 루트에서 실행합니다.

## 3. Python과 의존성 설치

```powershell
uv python install 3.13
uv sync --locked --python 3.13
```

uv로 Python을 설치할 수 있으므로 별도의 Python 설치 프로그램을 먼저 실행할 필요는 없습니다. 자세한 내용은 [uv의 Python 설치 안내](https://docs.astral.sh/uv/guides/install-python/)를 참고합니다.

`uv sync`는 프로젝트의 `.venv` 가상환경을 만들고 잠금 파일에 지정된 의존성을 설치합니다. 이후 `uv run`을 사용하면 가상환경을 직접 활성화하지 않아도 됩니다.

설치된 프로젝트 Python 버전을 확인합니다.

```powershell
uv run python --version
```

`Python 3.13.x`가 출력되면 됩니다.

## 4. 초기 설정

```powershell
uv run python scripts/dev.py setup
```

이 명령은 다음 작업을 수행합니다.

- 로컬 비밀 설정과 로그 디렉터리 준비
- 데이터베이스 테이블 생성·갱신
- 최초 설치 시 관리자 계정 준비
- 웹 화면에 필요한 정적 파일 수집

관리자 계정 `admin`은 최초 생성 시 비밀번호 로그인이 비활성화됩니다. 일반 플레이에는 다음 단계에서 별도의 탐사자 계정을 만듭니다.

`setup` 자체는 아이템 data migration이나 global cutover를 실행하지 않습니다. 실제 빈 world 확인과 native runtime marker 초기화·world bootstrap은 다음 단계의 첫 서버 시작에서 수행합니다.

## 5. 실행과 접속

서버를 시작합니다.

```powershell
uv run python scripts/dev.py start
```

첫 시작은 초기 준비 때문에 시간이 걸릴 수 있습니다. 시작 완료 후 [로컬 게임 화면](http://127.0.0.1:8701/webclient/)을 엽니다.

1. 탐사자 이름과 비밀번호를 입력합니다.
2. **새 탐사자 만들기**를 선택합니다.
3. 출정 대기실과 캐릭터 상태가 표시되면 접속 완료입니다.
4. `도움말`을 입력하거나 주변 행동 버튼으로 탐사를 시작합니다.

이미 만든 계정은 **접속하기**로 들어갑니다. 첫 사냥 명령은 [README의 첫 사냥 안내](../README.md#첫-사냥)를 참고합니다.

| 용도 | 기본 주소 |
| --- | --- |
| 게임 웹 화면 | `http://127.0.0.1:8701/webclient/` |
| WebSocket 연결 | `ws://127.0.0.1:8702` |

브라우저는 WebSocket에 자동으로 연결하므로 게임 웹 화면만 열면 됩니다. LAN 접속은 `http://<서버의 LAN-IP>:8701/webclient/`를 엽니다. WebSocket은 해당 hostname의 8702 포트를 사용합니다.

### 네트워크와 자동 생성 키

| 서비스 | 기본 포트 | 기본 bind |
| --- | --- | --- |
| Telnet | TCP 8700 | IPv4 `0.0.0.0` |
| Web | TCP 8701 | IPv4 `0.0.0.0` |
| WebSocket | TCP 8702 | IPv4 `0.0.0.0` |
| Telnet SSL | TCP 8703 | IPv4 `0.0.0.0` |
| SSH | TCP 8704 | IPv4 `0.0.0.0` |

`0.0.0.0`은 모든 IPv4 인터페이스를 뜻하며 접속할 HTTP Host 값이 아닙니다. `ALLOWED_HOSTS = ["*"]`는 LAN IP와 hostname을 허용합니다. OS 방화벽이 허용하면 LAN의 다른 장치가 접속할 수 있고, NAT/포트포워딩을 따로 구성하면 외부 네트워크에도 노출될 수 있습니다. TCP 8700 Telnet은 평문이며 Web의 HTTP/WS도 TLS를 제공하지 않습니다. 외부 운영용 HTTPS/WSS·공인 인증서는 별도로 구성합니다. 프로젝트는 방화벽이나 공유기를 변경하지 않습니다.

Evennia 6.1의 SSL·SSH 서비스에 필요한 Twisted `conch`/`tls` 선택 의존성(PyOpenSSL·cryptography·bcrypt·service-identity 등)은 `uv.lock`으로 설치합니다. 최초 **Portal cold start**에서 Evennia가 기존 issuer 설정으로 self-signed SSL 인증서와 SSH host key를 생성합니다. 인증서 신뢰 설정은 사용하는 클라이언트의 정책을 따릅니다.

- SSL: `game/server/ssl.key`, `game/server/ssl-public.key`, `game/server/ssl.cert`
- SSH: `game/server/ssh-private.key`, `game/server/ssh-public.key`

다섯 파일은 명시적으로 Git에서 제외됩니다. 개인 키 내용은 로그·문서·커밋에 넣지 않고, 이미 생성된 키는 재시작 시 재사용합니다. 설정을 바꾼 뒤 Server reload만 하면 Portal listener는 바뀌지 않으므로 `scripts/dev.py stop` 후 `start`로 다시 시작합니다. 다른 서버가 같은 포트를 사용 중이면 먼저 해당 서버를 확인합니다.

기존 4000번대의 로컬 앱 포트 충돌을 피하기 위해 접속 포트를 네 자리 연속 대역 8700~8704로 옮겼습니다. 내부 HTTP는 8705, AMP는 8706이며 loopback 연결을 유지합니다. 2026-10-04 확인한 [IANA 등록표](https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv)에서 8700~8709는 미할당입니다. 임의의 다른 프로그램과 영구적으로 충돌하지 않는 포트는 없으므로 기동 전 실제 점유 상태를 확인합니다. OS 동적 포트 범위·방화벽은 변경하지 않습니다.

PC 안에서만 실행하려면 Git 제외 `game/server/conf/secret_settings.py`에서 필요한 서비스의 `*_INTERFACES`를 `["127.0.0.1"]`, `WEBSOCKET_CLIENT_INTERFACE`를 `"127.0.0.1"`, `ALLOWED_HOSTS`를 `["localhost", "127.0.0.1", "[::1]"]`로 override할 수 있습니다. 서비스를 사용하지 않으면 해당 `*_ENABLED`를 `False`로 override합니다. AMP와 내부 Web 연결은 공개 접속 포트와 별개이며 loopback 연결을 유지합니다.

서버를 종료할 때는 다음 명령을 사용합니다.

```powershell
uv run python scripts/dev.py stop
```

다음 실행부터는 의존성 설치와 초기 설정을 반복하지 않고 `start`로 시작하면 됩니다. 코드를 업데이트했다면 해당 변경의 의존성·DB·정적 파일 갱신 안내도 확인합니다.

## 6. 설치 확인과 데이터 보관

설치 후 자동 검사를 실행할 수 있습니다.

```powershell
uv run python scripts/dev.py check
uv run python scripts/dev.py test
```

코드 검사에서 `All checks passed!`, 규칙·통합 테스트에서 각각 `OK`가 출력되는지 확인합니다. 테스트는 별도 테스트 DB를 사용합니다.

| 경로 | 내용 |
| --- | --- |
| `.venv/` | 프로젝트 Python 가상환경 |
| `game/server/evennia.db3` | 계정과 플레이 진행 데이터 |
| `game/server/conf/secret_settings.py` | 로컬 비밀 설정 |
| `game/server/logs/` | 서버 로그 |

플레이 기록을 보존하려면 DB를 삭제하거나 덮어쓰지 않습니다. 비밀 설정과 DB는 Git에 올리지 않습니다.

명령이 인식되지 않으면 설치 후 터미널을 새로 열었는지 확인합니다. 게임 페이지나 서버 연결 문제가 발생하면 [테스트 안내의 문제 해결 절차](playtest.md#7-막혔을-때-확인할-사항)를 참고합니다. 실제 사냥·장비·임무·재접속 검증 절차도 같은 문서에 있습니다.
