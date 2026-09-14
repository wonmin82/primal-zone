# 원시구역 설치 안내

로컬 PC에 게임 서버를 설치하고 웹 브라우저로 접속하는 방법입니다. 아래 설치 명령은 Windows PowerShell 기준입니다. 명령을 한 줄씩 실행하고 성공 여부를 확인한 뒤 다음 단계로 진행하세요.

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

현재는 설치한 PC에서 접속하는 로컬 실행을 기준으로 합니다. 외부 공개 서버 배포는 별도 구성이 필요합니다.

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

## 5. 실행과 접속

서버를 시작합니다.

```powershell
uv run python scripts/dev.py start
```

첫 시작은 초기 준비 때문에 시간이 걸릴 수 있습니다. 시작 완료 후 [로컬 게임 화면](http://127.0.0.1:4001/webclient/)을 엽니다.

1. 탐사자 이름과 비밀번호를 입력합니다.
2. **새 탐사자 만들기**를 선택합니다.
3. 탐사대 부두와 캐릭터 상태가 표시되면 접속 완료입니다.
4. `도움말`을 입력하거나 주변 행동 버튼으로 탐사를 시작합니다.

이미 만든 계정은 **접속하기**로 들어갑니다. 첫 사냥 명령은 [README의 첫 사냥 안내](../README.md#첫-사냥)를 참고합니다.

| 용도 | 기본 주소 |
| --- | --- |
| 게임 웹 화면 | `http://127.0.0.1:4001/webclient/` |
| WebSocket 연결 | `ws://127.0.0.1:4002` |

브라우저는 WebSocket에 자동으로 연결하므로 게임 웹 화면만 열면 됩니다. 기본 설정은 `127.0.0.1`에 바인딩되므로 같은 PC에서만 접속할 수 있습니다.

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

명령이 인식되지 않으면 설치 후 터미널을 새로 열었는지 확인합니다. 게임 페이지나 서버 연결 문제가 발생하면 [테스트 안내의 문제 해결 절차](playtest.md#6-막혔을-때-확인할-사항)를 참고합니다. 실제 사냥·장비·임무·재접속 검증 절차도 같은 문서에 있습니다.
