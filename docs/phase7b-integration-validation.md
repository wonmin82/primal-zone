# Phase 7B 통합 검증 시나리오

지원 대상은 SQLite + single Evennia server다. 모든 서버·계정·DB는 격리 fixture이며 실제 운영 데이터가 아니다. 준비금·장비·완료 직전 quest flag는 test fixture에서 구성하고 결과는 실제 서버 명령으로 만든다. Production 가격·전투·loot timer·balance는 변경하지 않는다.

## 재현 명령

저장소 루트에서 아래를 실행한다. 성공 DB는 owned process 종료 뒤 삭제하고 비밀이 없는 관찰 결과를 `work/phase7b/evidence/<run-id>/`에 보존한다. 실패 DB와 로그는 원인 분석용으로 남긴다.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py multiplayer
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py loot
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py items
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py valid
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py warning
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py invalid
```

Browser는 `serve --keep-fixture` 또는 `serve-reports --keep-fixture`의 localhost HTTP `/webclient/`를 사용한다. 실행이 출력한 private credentials file은 로컬 로그인에만 사용하고 문서·커밋·증거 export에 포함하지 않는다. 터미널 Enter로 종료하면 해당 Harness가 소유한 Portal/Server만 정리한다. 실제 OS IME는 사람이 조합·Backspace·Enter·빠른 입력을 확인한다.

## 실제 Chrome UI 관찰

| 시작 상태 | 실행한 command/action | 관찰 결과 및 기대 결과 | 결과 |
| --- | --- | --- | --- |
| 격리 native Explorer, desktop 로그인 | 소지품/장비/상태, 방향·승강기 버튼 | starter·장비·잔액·현재 방과 prompt가 서버 결과와 일치 | PASS |
| 1층 보급품점, 3000칩 준비금 | 상품·손전등 구매·건전지 구매·붕대 3개 판매 | 35/8/10/5/3 가격, 35+8 차감과 판매15 지급 | PASS |
| 실제 구매한 손전등/건전지 | 건전지 넣기·켜기·확인·끄기 버튼 | 전원 삽입 후 ON/잔량 표시·OFF | PASS |
| 기본 병기점 | 경비카빈 구매·가치·loaded 판매 | package200, standard20/20, loaded 판매 거절 | PASS |
| 총기/탄창 | 탄창 꺼내기·잔탄 꺼내기·채우기·재장전 | loose20↔mag20 이동, 잔탄 포함 매입가42 | PASS |
| Chrome viewport390×844 | 카빈탄 구매·3개 판매·모두 판매 | 20발60칩, 3+17개 판매20칩, 버튼과 입력 접근 가능 | PASS |
| 좁은 보관실 | 개인 벌목도 입출고·loaded carbine 공용 입출고 | 장비와 20/20 magazine tree 유지, inventory/보관 화면 일치 | PASS |
| 초지·경비카빈 장착 | 실제 사냥 버튼·시체 보기·회수 버튼 | shot마다 잔탄 감소·XP22·8칩 회수, 좁은 화면에서도 조작 가능 | PASS |
| 통신탑 보고 준비 완료, 미claimed | 윤대장 대화 버튼 | XP100·100칩·붕대3·전초 출입증·능선포식자표식 표시 | PASS |
| 전초 출입증 보유 | 전초 장비고 진입·소각 1차·1개 확정·정상 확정 | 진입 가능, 1차/수량 confirmation mutation 없음, 정확한 확정만 삭제 | PASS |
| 출입증 소각 뒤 | 재진입·윤대장 재대화 | 진입 차단·무료 출입증 재발급, unique/reward 재지급 메시지 없음 | PASS |
| 깊은 밀림 보고 준비 완료, 미claimed, narrow | 선발대 길잡이 대화 | XP120·120칩·붕대3·특수 출입증·포식자비늘장식 표시 | PASS |
| 특수 출입증만 보유 | reserved 남쪽·전초 북쪽 진입 | reserved 정확한 폐쇄 문구, 특수 pass는 전초 pass 대체 불가 | PASS |
| 특수 출입증 소각 뒤 | 길잡이 재대화 | 특수 출입증만 무료 재발급, unique 반복 지급 메시지 없음 | PASS |

390px viewport의 실제 content width375px에서 body scrollWidth375px로 가로 overflow가 없고 input/button 접근을 확인했다. 실제 모바일 Safari/device와 모든 브라우저 조합을 검증했다는 뜻은 아니다. Quest 보고 경계는 fixture로 준비했으며 자연스러운 두 quest 전체 progression은 production-timing Full smoke가 검사한다.

사용자는 Windows/Chrome 격리 화면에서 OS 한글 IME가 정상임을 확인했다. 안내한 명령은 `소지품`, `상태`, `어린청소룡 공격`, `시체에서 모두 가져`, `탐사용손전등 켜`, `무기상 상품`과 조합 중 Backspace·Enter·빠른 입력이다. 사용자 응답은 전체 정상 확인이며 명령별 전송 횟수나 OS/browser 세부 버전 로그는 수집하지 않았다. 자동 text injection 결과와 구분한다.

## 실제 네 session multiplayer

Lv7/T2 fixture와 production V1 Boss 정의를 사용했다. 공격/HP/타이머를 바꾸지 않고 관찰 창을 확보하는 일반 build를 구성했다.

| 시나리오 | 실제 관찰 | 결과 |
| --- | --- | --- |
| A가 B/C/D 초대·각 session 수락 | 네 독립 account의 party 구성 | PASS |
| Boss1/2/3/4 eligible | maxHP170/297/425/552, multiplier1/1.75/2.5/3.25의 정수 HP 표현 | PASS |
| XP | 1인130, 2인65/65, 3인44/43/43, 4인33/33/32/32, 각 encounter 합130 | PASS |
| 피해 후 C/D late join | max297→552, 기존 damage 지워지지 않음. 관찰 사이 추가 공격 가능 | PASS |
| D 이탈 | 같은 encounter max552 유지·downscale 없음 | PASS |
| kick/leave/위임/cleanup | 실제 party 명령으로 종료 | PASS |
| 첫 Boss 다음 encounter | respawn max170 baseline 복원 | PASS |

Eligible은 명령을 보낸 시점이 아니라 기존 reward participation의 실제 첫 피해 이후다. Live 관찰 사이 추가 공격 때문에 정확한 HP 증가분 대입은 기존 deterministic integration 회귀와 함께 판단한다. Attack scaling 없음·정확한 late join 산술·participant monotonic 회귀도 전체 자동 검증에 포함됐다.

## 실제 loot lifecycle

6개 protected bandage 중 assigned A가 1개 회수하고 remainder5의 UUID/sequence/claim을 확인했다. Inventory fragment의 claim은 제거된다. Stored corpse fixture의 decay deadline90초는 네 session 준비 시간을 위한 저장 상태이며 신규 corpse production TTL30초의 검증은 Full smoke와 구분한다. Decay 후 동일 UUID/quantity/state/claim/deadline을 가진 world_loot를 검사했다.

Currency20의 A share0/B share20에서 실제 A2칩+B5칩+A5칩 회수를 실행했다. A는 zero-share eligible trigger이고 B가 총12칩을 받으며 마지막5칩은 offline B에게 지급됐다. Source/share remainder8을 확인했다. 다른 recipient group의 currency 회수는 거절됐다. 실제 절대 보호기한120초 뒤 outsider D가8칩과 bandage5를 회수해 원 currency20을 보존했다. 이것은 SQLite 순차 명령·offline 지급 검증이며 DB-engine 동시 race 검증은 아니다.

## Corpus와 post-cutover

[Canonical Legacy Migration Corpus](phase7-legacy-migration-corpus.md)에 구성·warning/error·CLI 순서를 기록했다. Valid cutover 후 실제 네 account 로그인, 장비·보관·광원·source/sink shop·탄창/탄약·Credential 소각/차단/재발급을 실행하고 archived inventory/equipment/storage/light_sources 불변을 확인했다.

최종 보강된 valid post-cutover58.696초 실행에서 고유 보상의 personal storage를 허용하고 shared/give/drop/sell/burn을 거절한 뒤 UUID/sequence/state를 비교했다. Migrated firearm loot의 동일 tree 회수·zero-share currency trigger2칩 지급, migration 정비부품3개→발전기 수리→최초 cache→정비부품0개 유지/붕대2개·탐사인식표 지급/일반 scrap20개 보존을 실제 명령으로 연결했다. 모든 archived item field는 불변이었다.

별도 실제 서버 `items` 실행41.845초에서 복수 flashlight 중 한 개만 ON→OFF, 빈 경비카빈의 공격 기회 소비·damage0·mental/cooldown 불변, automatic reload의 잔탄9 우선 선택을 검사했다. Loaded 총기는 inventory로 해제해도 구조상 burn이 거절된다. 탄창 분리 뒤 잔탄9 magazine과 firearm body를 소각해 magazine row/rounds가 사라지고 loose ammo·credits가 늘지 않는 것을 확인했다.

## 제한 사항

Actual OS IME는 사용자 확인, browser는 Chrome desktop/narrow, multiplayer는 SQLite 단일 서버의 독립 session이다. PostgreSQL contention·multi-server·실제 mobile device는 미검증이다. 경비카빈 ammo/gross≈44.6%, full balance simulation·fresh operational DB·Item System V1 closeout은 Phase 7C로 남긴다.
