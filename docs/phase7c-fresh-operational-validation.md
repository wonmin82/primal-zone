# Phase 7C fresh native 운영 경로 검증

## 목적과 지원 경계

새 empty SQLite에서 schema → 실제 Evennia first initialization → native ItemRuntime → 신규 계정 → gameplay → 정상 restart/relogin을 확인한다. 지원 topology는 SQLite + single Evennia server다. 검증 DB를 실제 장기 플레이 DB로 채택하지 않는다. 기존 개발 DB나 legacy corpus를 복사하지 않고 `migrate-items`의 네 mode 모두 사용하지 않는다.

## 재현

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/phase7c_fresh.py
```

기존 Harness가 소유한 `work/smoke/full-*` 폴더·독립 SQLite·loopback 전용 포트·owned Portal/Server를 사용한다. `.phase7c-fresh` marker로 별도 fixture write를 제한한다. 정상 성공 시 DB와 비밀 설정을 삭제하고 비밀 없는 snapshot·로그는 `work/phase7c/fresh-evidence/`에 남긴다. 실패 시 소유 process는 종료하고 분석용 격리 DB/로그를 보존한다. Binary DB와 비밀번호는 Git에 넣지 않는다.

## Setup / first boot

`phase7c_fresh_setup.py`는 격리 복사본의 실제 `dev.py setup()`을 호출한다. Evennia launcher가 DJANGO settings 환경을 덮어쓰므로 migrate/collectstatic에 명시적 `--settings settings_smoke`를 전달하는 adapter만 사용한다. Schema 직후 runtime row 없음·ledger0·Explorer0을 assert한다. Bootstrap admin은 비밀번호 로그인 불가 상태다.

첫 실제 Server가 upstream `create_objects`, `at_initial_setup`, `collectstatic`을 실행한다. Foreground Harness에는 launcher daemon 재시작 관리자가 없어 private `phase7c_initial_setup`은 upstream의 최초 자동 reset 요청만 생략한다. World/bootstrap/ItemRuntime/Explorer 생성 hook은 그대로 실행한다. TEST_ENVIRONMENT 우회는 사용하지 않고 뒤의 실제 정상 shutdown/start/relogin에서 restart contract를 검증한다. 이 adapter는 격리 settings에만 적용하며 일반 설치 설정을 바꾸지 않는다.

실제 first boot에서 ItemRuntime.version1·ledger0·일반 계정0을 확인한다. WebSocket `pz_auth(mode="register")`로 일반 계정2개를 생성한다. 공개 가입 throttle(같은 IP10분당2개)은 유지하며 fixture API로 우회하지 않는다. 출정 대기실·XP0·20칩·HP60·starter 벌목도/hands·작업복/body·붕대3개를 assert한다. UUID·sequence·quantity·owner·canonical location/slot와 native runtime marker를 snapshot으로 남기며 archived inventory/equipment/storage/light_sources가 없음을 확인한다.

## Grind 단축과 실제 gameplay

Starter 증거를 확보한 뒤 정상 offline 경계에서 검증가에게 준비금900칩을 한 번만 지급한다. XP·특성·기술·quest·discovery·아이템·Credential·Boss unique는 fixture에서 지급하지 않는다. 동일 DB 재접속으로 준비금을 읽으며 이는 신규 player의 실제 시작 자금20칩과 구분한다. 준비금은 반복 grind만 단축하며 경제 pacing은 별도 [분석](phase7c-balance-analysis.md)에서 측정한다.

실제 명령으로 소지품/장비/상태·이동·파티·상품·구매·판매·개인/공용 보관·손전등/battery ON/OFF·총기 package/spare magazine/ammo·탄창 분리/loose 회수/채움/장전·발사·재장전을 연결한다. Package의 standard magazine20발과 실제 발사 후 잔탄 감소를 persistent snapshot으로 assert한다. Native inside 후손은 `api.items_owned_by`로 조회한다.

기존 Full의 `Closeout.progression()`을 재사용한다. 체질·힘 배분과 Rank 훈련은 올바른 NPC에서 실제 획득 예산만 사용한다. 수송차 cache·정비기록·발전기 submit·실제 적 처치로 level을 올리고 능선 보스 처치/윤대장 보고 → 전초 Credential/access → T2 구매 → 두 표식·신호 전지·밀림 보스 처치/최종 보고를 실행한다. 두 Credential과 두 unique 생성은 실제 transaction 결과로 확인한다. Ledger는 끝까지0이다.

## Persistence

Full의 동일한 shutdown/startup assertion을 사용한다. Live before에서 실제 ON light와 active weapon이 존재해야 한다. 정상 `evennia stop` 뒤 stopped에서는 light OFF·started_at None·project_power 관찰 시간 범위의 잔량·active_light None만 허용하고 일반 ItemEntity/tree/state와 active weapon은 불변이다. Startup/relogin after는 stopped의 item snapshot과 엄격하게 같아야 한다. Profile/quest/discovery/credits/party·개인/공용 storage·시설·승강기와 loot callback/respawn 재예약을 함께 확인한다.

## 실제 결과

최종 `full-hvjdlzmj` 실행은 **511.030초 PASS**다. Schema-only runtime 없음/ledger0/Explorer0 → first boot runtime1 → 실제 등록2계정 → starter native → 실제 두 임무/보스/보고/Credential → 정상 restart/relogin → final runtime1/ledger0을 확인했다. Package standard magazine20발은 실제 두 발 발사 후18발이 됐고 재장전은 더 많은 잔탄의 spare를 선택했다.

Restart 직전 실제 ON 광원의 잔량1799.660은 정상 shutdown 뒤1426.242로 정산됐다. OFF·started_at=None·active_light=None, 일반 item UUID/sequence/location/tree/state와 active weapon 불변, after strict preservation이 성공했다. 저장된 개인/공용 붕대와 quest/credits/access도 유지됐다.

비밀 없는 evidence는 `work/phase7c/fresh-evidence/full-hvjdlzmj/`의 schema/first-boot/registered-starters/full-package/shot-consumption/gameplay-completed/final/run snapshot과 로그다. 성공 DB는 cleanup했으며 deterministic coordinator로 재생성할 수 있다. 기존 개발 DB SHA256 `B1318296F505B9B7522FCBDEDFF7642A06CF055E9DE72802198C70E6B8A7F700`, size733184, mtime_ns1790080153765082800은 전후 동일하다.

앞선 여섯 실패와 adapter/명령/fixture 기대 보정은 [playtest](playtest.md)의 Phase7C 절에 보존한다. 이 결과는 fresh 운영 경로의 검증이며 실제 장기 플레이 DB 채택은 아니다. PostgreSQL·multi-server·실제 모바일 기기 matrix·legacy cleanup은 수행하지 않는다.
