# 원시구역 · Primal Zone

사냥하고 장비를 모으며, 잊힌 섬을 탐험하는 한국어 웹 MUD.
사냥·장비·성장을 우선하고, 모든 주요 임무를 혼자 진행할 수 있도록 만든다.

## 현재 구현

- 브라우저 가입·접속, 한글 이름과 명령어, 같은 방에서의 채팅
- 연결된 장소 8개, 일반 적 3종, 보스 1종
- 2.5초 간격 자동 기본 공격, 강타·방어·붕대 회복·도주
- 레벨 1~10, 장비 드롭·착용, NPC 구매와 확정 재료 교환
- 정비기록 조사 → 발전기 복구 → 보스 처치 → 보고로 끝나는 솔로 임무
- 캐릭터·소지품·교전·임무 저장과 재접속
- 반응형 상태창, 주변 행동 버튼, 장비창, 명령어 기록

현재는 로컬에서 실행하는 첫 플레이 버전이다. 파티 공동 전투, 거래, 두 번째 지역, 외부 배포는 아직 구현하지 않았다.

## 실행

Python 3.13과 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 사용한다.
저장소 루트에서 실행:

```sh
uv sync --locked --python 3.13
uv run python scripts/dev.py setup
uv run python scripts/dev.py start
```

[로컬 게임 화면](http://127.0.0.1:4001/webclient/)을 열고, 이름과 비밀번호를 정한 뒤 **새 탐사자 만들기**를 선택한다.
첫 서버 시작은 초기 설정 때문에 약간 기다려야 할 수 있다.

이미 가상환경이 구성된 Windows에서는 uv 대신 다음처럼 실행할 수 있다:

```powershell
.\.venv\Scripts\python.exe scripts/dev.py start
```

접속 포트는 HTTP 4001, WebSocket 4002이며 기본값으로 이 PC에서만 접속할 수 있다.
setup은 비밀번호 접속이 비활성화된 로컬 admin 계정을 준비한다.
관리 기능이 필요할 때만 'uv run python scripts/dev.py admin-password'로 직접 비밀번호를 설정한다.
게임 테스트는 별도의 일반 탐사자 계정으로 진행한다.

## 첫 사냥

```text
대화 윤대장
북
공격 어린청소룡
강타
가방
착용 강철마체테
```

드롭을 얻지 못했다면 부두에서 장비를 구매하거나 회수부품으로 교환할 수 있다.
'도움말', '임무', '지도'로 진행 방법을 확인한다. 휴식·상점은 부두에서 이용할 수 있다.
전체 임무 경로와 검증 항목은 [플레이테스트 안내](docs/playtest.md)에 있다.

## 개발

```sh
uv run python scripts/dev.py check
uv run python scripts/dev.py test
uv run python scripts/dev.py reload
uv run python scripts/dev.py stop
```

CSS·JavaScript 변경 후에는 'game' 폴더에서 'uv run python -m evennia collectstatic --noinput'을 실행하고 브라우저를 새로고침한다.
테스트는 별도 테스트 DB를 사용하며 플레이 DB를 지우지 않는다.
게임 규칙 테스트와 Evennia 통합 테스트를 GitHub Actions에서도 실행한다.

실행 중인 로컬 서버의 실제 가입·사냥·장비·재접속 흐름은 다음 명령으로 검사한다:

```sh
uv run python scripts/smoke.py
```

이 검사는 일반 권한의 테스트 계정 1개를 로컬 DB에 남긴다.
짧은 시간에 반복 가입하면 엔진의 가입 횟수 제한에 걸릴 수 있다.

## 기술과 데이터

- Python 3.13 / Evennia 6.1.0 / SQLite
- HTML·CSS·JavaScript / Evennia WebSocket 프로토콜
- 의존성 고정: pyproject.toml, uv.lock
- 로컬 DB: game/server/evennia.db3
- 로컬 비밀 설정: game/server/conf/secret_settings.py

DB·비밀 설정·로그·가상환경은 Git에 포함하지 않는다.
PostgreSQL 전환용 환경변수는 설정 파일에 준비되어 있으며, 실제 운영 구성은 후속 단계에서 검증한다.
[구조와 설계 결정](docs/architecture.md)을 참고한다.
