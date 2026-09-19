# 원시구역 · Primal Zone

사냥하고 장비를 모으며, 잊힌 섬을 탐험하는 한국어 웹 MUD.
사냥·장비·성장을 우선하고, 모든 주요 임무를 혼자 진행할 수 있도록 만든다.

## 현재 구현

- 브라우저 가입·접속, 한글 이름과 명령어, 같은 방에서의 채팅
- 연결된 장소 8개, 일반 적 3종, 보스 1종
- 2.5초 간격 자동 기본 공격, 강타·방어·붕대 회복·도주
- 레벨 1~10, 장비 드롭·착용, NPC 구매와 확정 재료 교환
- 정비기록 조사 → 발전기 복구 → 보스 처치 → 보고로 끝나는 솔로 임무
- 최대 4인 파티, 일반 적 점유, 공용 보스와 참여 기반 보상
- 공유 시체·순번 전리품·보호된 바닥 아이템과 시간 기반 재생성
- 캐릭터·소지품·파티·월드·임무 저장과 재접속
- 반응형 상태창, 파티·전리품 버튼, 장비창, 명령어 기록과 자체 제공 DOS풍 한글 폰트

현재는 로컬에서 실행하는 첫 플레이 버전이다. 거래, 두 번째 지역, 외부 배포는 아직 구현하지 않았다.

## 실행

처음 설치한다면 [설치 안내](docs/installation.md)에서 필요한 환경, Git·uv 설치, 저장소 다운로드와 초기 설정부터 확인한다.

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

명령은 `대상 + 행동` 순서로 입력한다. 예: `붕대 구매`, `강철 마체테 착용`, `윤대장 대화`.
대상 이름의 공백은 허용하며, 행동 앞에는 공백을 둔다. `북`, `상태`, `강타`처럼 대상이 없는 명령은 그대로 사용한다.
기존 `공격 어린청소룡`처럼 행동을 앞에 쓰는 게임 명령은 지원하지 않는다. 별칭도 `어린청소룡 attack`처럼 뒤에 쓴다.

채팅은 `안녕하세요 말` 또는 `'안녕하세요`로 입력한다. 작은따옴표는 앞에 하나만 붙이며, 이후 내용은 명령어가 포함되어도 모두 채팅으로 처리한다.
예를 들어 `'안녕하세요 말`은 마지막 `말`까지 전송한다. 같은 장소에만 전달되며, 채팅 내용은 1~300자다.

```text
윤대장 대화
북
어린청소룡 공격
강타
시체에서 모두 가져
가방
강철마체테 착용
```

처치 시 경험치·크레딧은 즉시 받지만 아이템은 `시체에서 모두 가져`로 회수한다. 30초 후 시체의 남은 아이템은 바닥으로 이동하며 `모두 가져`로 회수할 수 있다. 처치 후 120초간 배정 권한이 유지되고, 적은 45초 후 다시 나타난다.

`친구이름 파티초대` → 상대의 `파티수락`으로 함께 사냥할 수 있다. `파티`, `파티거절`, `친구이름 파티제외`, `친구이름 파티장위임`, `파티탈퇴`를 지원한다. 기본 전리품 분배는 참여자 순번이며, 파티원 누구나 회수를 요청해도 아이템은 배정된 탐사자에게 들어간다. 일반 적은 다른 그룹의 공격을 거부하고 보스는 여러 그룹이 참여할 수 있다.

드롭을 얻지 못했다면 부두에서 장비를 구매하거나 회수부품으로 교환할 수 있다.
'도움말', '임무', '지도'로 진행 방법을 확인한다. 휴식·상점은 부두에서 이용할 수 있다.
접속 준비, 전체 임무 경로, 기능별 정상 결과, 자동 테스트와 결과 기록 방법은 [테스트 안내](docs/playtest.md)에 있다.

## 개발

```sh
uv run python scripts/dev.py check
uv run python scripts/dev.py test
uv run python scripts/dev.py reload
uv run python scripts/dev.py stop
```

CSS·JavaScript·글꼴 변경 후에는 'game' 폴더에서 'uv run python -m evennia collectstatic --noinput'을 실행하고 브라우저를 새로고침한다.
테스트는 별도 테스트 DB를 사용하며 플레이 DB를 지우지 않는다.
게임 규칙 테스트와 Evennia 통합 테스트를 GitHub Actions에서도 실행한다.

실행 중인 로컬 서버의 실제 가입·사냥·장비·재접속 흐름은 다음 명령으로 검사한다:

```sh
uv run python scripts/smoke.py
```

이 검사는 일반 권한의 테스트 계정 3개를 로컬 DB에 남긴다.
기본 가입 제한을 지키기 위해 세 번째 가입 전에 610초 기다린다. 앞선 실행의 제한에 걸리면 한 번 더 기다리므로 전체 검사는 약 13~25분 걸릴 수 있다.

## 기술과 데이터

- Python 3.13 / Evennia 6.1.0 / SQLite
- HTML·CSS·JavaScript / Evennia WebSocket 프로토콜
- 의존성 고정: pyproject.toml, uv.lock
- 로컬 DB: game/server/evennia.db3
- 로컬 비밀 설정: game/server/conf/secret_settings.py

DB·비밀 설정·로그·가상환경은 Git에 포함하지 않는다.
PostgreSQL 전환용 환경변수는 설정 파일에 준비되어 있으며, 실제 운영 구성은 후속 단계에서 검증한다.
[구조와 설계 결정](docs/architecture.md)을 참고한다. 기존 개인 교전의 적 HP는 새 공유 적으로 옮기지 않으며, 성장·장비·소지품·임무 기록은 유지한다.

Neo둥근모 Code v1.601을 SIL Open Font License 1.1로 자체 제공한다. [글꼴 출처](game/web/static/webclient/fonts/neodgm/SOURCE.md)와 [라이선스](game/web/static/webclient/fonts/neodgm/LICENSE.txt)를 함께 배포한다.
