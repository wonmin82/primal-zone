# 원시구역 · Primal Zone

사냥하고 장비를 모으며, 잊힌 섬을 탐험하는 한국어 명령 기반 웹 MUD.
주요 탐험과 임무는 혼자 진행할 수 있으며, 다른 탐사자와 파티를 맺어 공유 월드에서 함께 사냥할 수 있다.

## 주요 기능

| 분야 | 플레이할 수 있는 내용 |
| --- | --- |
| 탐험과 월드 | 전초구역과 깊은 밀림, 지상 5층·옥상 본부, 8방향·수직 이동, 지도·인접 장소 정찰, 두 솔로 임무 |
| 전투와 성장 | 실시간 자동 공격, 강타·사격·간파·견제·치료·호흡, 특성 배분·기술 훈련, Lv.133까지 성장과 무료 재훈련 |
| 장비와 경제 | 무기·방어구·주무기 선택, 탄창·탄약, 아이템 드롭, 보급칩 상점·판매·자원 정산, 공용·개인 보관 |
| 멀티플레이어 | 최대 4인 파티, 일반 적 점유, 여러 그룹이 참여하는 공용 보스, 참여 보상·순번 전리품·보호된 바닥 물건 |
| 명령과 개인 줄임말 | 한국어 대상·행동 입력, 분류별 도움말, 고정 단축어, 캐릭터별 줄임말·변수와 여러 명령의 순차 실행 |
| 환경과 화면 | 공용 시간·날씨·달·밝기에 따른 시야, 손전등·시설 조명, 자연회복, 반응형 상태창·행동 버튼·명령 기록 |

캐릭터의 성장·소지품·임무·방문 기록과 파티·월드 상태를 저장한다.
현재는 로컬/LAN에서 실행하는 플레이 버전이며 **SQLite + 단일 Evennia 서버**를 지원한다.
양방향 안전 거래창, PostgreSQL 운영, 여러 게임 서버가 같은 월드를 쓰는 구성과 외부 production 배포는 현재 지원 범위에 포함하지 않는다.
개발 완료 내역과 검증의 범위는 [작업·검증 이력](docs/CODEX_TASK_STATE.md), [통합 audit](docs/phase7-final-integration-audit.md)에 있다.

<a id="실행"></a>

## 빠른 시작

처음 설치한다면 [설치 및 서버 운영 안내](docs/installation.md)를 먼저 읽는다.
Git, **Python 3.13**, [uv](https://docs.astral.sh/uv/getting-started/installation/)가 필요하다.
저장소 루트에서 다음 명령을 차례로 실행한다.

```sh
uv sync --locked --python 3.13
uv run python scripts/dev.py setup
uv run python scripts/dev.py start
```

1. [로컬 게임 화면](http://127.0.0.1:8701/webclient/)을 연다.
2. 이름과 비밀번호를 정하고 **새 탐사자 만들기**를 선택한다.
3. 기존 계정은 **접속하기**로 들어간다. 첫 서버 시작에는 초기 준비 시간이 필요할 수 있다.

이미 가상환경이 있는 Windows에서는 uv 대신 다음처럼 실행할 수 있다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py start
```

새 빈 DB는 아이템 시스템을 직접 초기화한다. 구버전 DB·백업은 자동 변환되지 않으므로 서버 시작 전에 [legacy migration 절차](docs/item-migration.md)를 따른다.
**기존 DB를 삭제하거나 덮어쓰지 않는다.** `setup`은 아이템 데이터 migration을 수행하지 않는다.

기본 접속 서비스는 IPv4 `0.0.0.0`에 열리므로 방화벽·NAT 설정에 따라 LAN이나 외부에 노출될 수 있다.
Telnet 8700은 평문이며 웹 HTTP/WS도 TLS를 제공하지 않는다.
서비스별 포트·bind, SSL/SSH 키·인증서, 로컬 전용 설정은 [설치 안내의 네트워크 절](docs/installation.md#네트워크와-자동-생성-키)을 따른다.

`setup`이 준비하는 로컬 `admin`은 비밀번호 접속이 비활성화되어 있다.
관리 기능이 필요할 때만 `uv run python scripts/dev.py admin-password`로 비밀번호를 설정하고, 플레이는 별도 일반 탐사자 계정을 사용한다.

## 게임 플레이 시작

### 명령과 도움말

명령은 **대상 + 행동** 순서다. 대상 이름에 공백을 넣을 수 있고 행동 앞에는 공백을 둔다.
`북`, `상태`, `강타`처럼 대상 없는 명령은 그대로 입력한다.
`어린청소룡 공격`은 지원하지만 `공격 어린청소룡` 같은 전치형 게임 입력은 지원하지 않는다.

| 목적 | 입력 예시 |
| --- | --- |
| 관찰·이동 | `보기`, `북 보기`, `북`, `출구`, `지도` |
| 전투·회수 | `어린청소룡 공격`, `강타`, `붕대 사용`, `도망`, `시체에서 모두 가져` |
| 정보·임무 | `상태`, `소지품`, `장비`, `임무` |
| 채팅 | `안녕하세요 말` 또는 `'안녕하세요` |
| 도움말 | `도움말`, `입력 도움말`, `전투 도움말`, `공격 도움말` |

채팅은 같은 방에 전달되며 작은따옴표는 앞에 하나만 붙인다.
웹 주변 행동 버튼도 같은 서버 명령을 실행한다.
대상 번호·전리품 배정·회복과 장비 조작은 [플레이 가이드](docs/gameplay.md)에서 확인한다.

### 첫 사냥

새 탐사자는 **출정 대기실**에서 시작한다. 다음 경로는 중앙 로비 → 부두 → 바람 부는 초지다.
명령은 한 줄씩 입력하고, 공격 뒤에는 처치 메시지를 확인한 다음 회수한다.

```text
도움말
남
서
윤대장 대화
북
어린청소룡 공격
시체에서 모두 가져
소지품
```

초지의 적이 다른 그룹과 교전 중이거나 재생성 대기 중이면 기다린다.
어둡거나 시야가 나쁘면 적·전리품을 식별하지 못할 수 있다. [손전등 확보 안내](docs/gameplay.md#날씨시간조명손전등)를 따른다.
경험치는 처치 즉시 받지만 보급칩과 아이템은 직접 회수해야 한다.
이후에는 `임무`로 목표를 확인하고 [본부·탐사 안내](docs/gameplay.md#본부와-탐사-지역)를 따라 장비와 회복을 준비한다.

### 여러 명령과 개인 줄임말

`단축어`로 게임의 고정 입력을 조회한다. `상`은 `상태`, `소`는 `소지품`, `ㅂ`은 `북`이다.
고정 단축어는 입력 전체가 일치할 때 적용하며 개인 줄임말과 구분한다.

```text
상태, 장비, 소지품 해
점검 상태, 장비, 소지품 해 줄임말
점검
정찰 $1 보기, 상태 해 줄임말
북 정찰
점검 줄임말
점검 해지
```

묶음은 앞선 명령이 끝난 뒤 현재 장소·상태에서 다음 명령을 실행한다.
일반 명령 실패는 다음으로 진행하고 줄임말 구조·확장 오류는 남은 실행을 중단한다. 완료한 동작은 되돌리지 않는다.
개인 줄임말 v1.14의 변수·한도·삭제·실행 계약은 [상세 안내](docs/command-shortcuts.md), 플레이 예시는 [가이드](docs/gameplay.md#개인-줄임말과-묶음-명령)를 따른다.

## 개발 및 테스트

저장소 루트에서 실행한다.

```sh
uv run python scripts/dev.py check
uv run python scripts/dev.py test
uv run python scripts/dev.py smoke
uv run python scripts/dev.py reload
uv run python scripts/dev.py stop
```

| 명령 | 역할 |
| --- | --- |
| `check` | Ruff로 코드를 검사한다. |
| `test` | 순수 규칙과 Evennia 통합 테스트를 실행한다. |
| `smoke` | 격리 서버·SQLite·fixture 계정으로 실제 WebSocket·scheduler 연결을 빠르게 검사한다. |
| `reload` | 실행 중인 게임 Server의 코드를 다시 불러온다. Portal listener 설정 변경은 stop/start가 필요하다. |
| `stop` | 실행 중인 서버를 종료한다. |

병렬·선별 테스트, DB 격리, Quick/Full smoke 차이, 수동 확인과 과거 CI·실패 이력은 [테스트 안내](docs/playtest.md#6-자동-테스트-실행)에 있다.
검사는 플레이 DB와 운영 인증 설정을 보존한다. 브라우저 화면·실제 한글 IME 확인은 자동 테스트와 별도로 수행한다.

<a id="개발"></a>

### 정적 파일 수집

CSS·JavaScript·글꼴을 수정하면 **`game` 디렉터리에서** 다음 명령을 실행한 뒤 브라우저를 새로고침한다.

```sh
uv run python -m evennia collectstatic --noinput
```

<a id="기술과-데이터"></a>

## 기술 스택과 지원 환경

| 구성 | 기준 |
| --- | --- |
| 언어·엔진 | Python 3.13.x (`>=3.13,<3.14`), Evennia 6.1.0 |
| 데이터베이스 | SQLite, 단일 게임 서버 |
| 웹 | HTML·CSS·JavaScript, Evennia WebSocket 프로토콜 |
| 환경 관리 | uv, [pyproject.toml](pyproject.toml)·[uv.lock](uv.lock)의 의존성 고정 |
| 확인된 환경 | Windows 로컬 실행, Linux GitHub Actions 자동 검사. macOS 실제 실행은 미검증 |

로컬 플레이 DB는 `game/server/evennia.db3`, 비밀 설정은 `game/server/conf/secret_settings.py`다.
DB·비밀 설정·로그·가상환경·수집된 정적 파일은 소스 관리에 포함하지 않는다.
PostgreSQL은 [향후 전환 계획](docs/postgresql-transition.md)이며 현재 운영 지원을 뜻하지 않는다.
일반 플레이 아이템은 ItemEntity 기반이다. 저장·권한·기존 데이터 호환 정책은 [구조 문서](docs/architecture.md)를 따른다.

Neo둥근모 Code v1.601을 **SIL Open Font License 1.1**로 자체 제공한다.
[글꼴 출처](game/web/static/webclient/fonts/neodgm/SOURCE.md)와 [라이선스](game/web/static/webclient/fonts/neodgm/LICENSE.txt)를 함께 배포한다. 별도 npm 빌드나 CDN은 필요하지 않다.

## 문서 안내

| 문서 | 역할 |
| --- | --- |
| [설치 및 서버 운영](docs/installation.md) | 설치·시작·네트워크·데이터 보관 |
| [플레이 가이드](docs/gameplay.md) | 명령·사냥·회복·장비·경제·파티·환경·임무 |
| [개인 줄임말과 묶음 명령](docs/command-shortcuts.md) | v1.14 공식 문법·변수·부분 실행·제한 |
| [최종 콘텐츠](docs/final-content.md) | 장비·상점·적·가격·드롭·획득처 |
| [성장과 전투](docs/progression.md) | 레벨·특성·기술·재훈련·호환 정책 |
| [구조와 설계 결정](docs/architecture.md) | 저장·전투·입력·환경·UI의 기술 계약 |
| [테스트 안내](docs/playtest.md) | 자동 검사·격리 서버·수동 시나리오·실행 이력 |
| [개발 작업 및 검증 이력](docs/CODEX_TASK_STATE.md) | 현재 마감 상태와 과거 개발·검증 기록 |

세부 설계: [장비](docs/equipment.md) · [광원·총기](docs/lighting-firearms.md) · [전리품](docs/loot-claims.md) · [출입증·상점](docs/credentials-access-shops.md) · [본부 배치](docs/headquarters-redesign.md) · [아이템 migration](docs/item-migration.md) · [텍스트 출력 예](docs/text-examples.md).

<a id="현재-구현"></a>
<a id="장비와-획득-경로"></a>
<a id="두-번째-탐사-지역"></a>
<a id="동적-환경"></a>
<a id="대상-선택과-전리품-회수"></a>
<a id="화폐와-회수-자원-정산"></a>
<a id="본부-npc-상점"></a>
<a id="출입증과-소각"></a>
<a id="의료와-복귀"></a>
<a id="정신력과-자연회복"></a>
<a id="성장과-재훈련"></a>
<a id="물건-사용과-보관"></a>
<a id="탐사-기록과-정보-조회"></a>
<a id="탐사-광원과-시설-조명"></a>

기존 README의 상세 플레이 항목은 [플레이 가이드](docs/gameplay.md)로 모았다. 장비의 확정 수치는 [최종 콘텐츠](docs/final-content.md), 개발 이력은 [작업 상태](docs/CODEX_TASK_STATE.md)에서 확인한다.
