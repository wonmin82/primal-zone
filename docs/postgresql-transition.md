# PostgreSQL 전환 필요성·목적·향후 계획

## 현재 지원 구성

현재 개발·V1 운영 기준은 **SQLite + single Evennia server**다. `game/server/conf/settings.py`에는 `PRIMAL_DB_NAME`을 설정하면 PostgreSQL backend를 선택하는 경로가 있지만, PostgreSQL 운영·접속·concurrency 검증은 하지 않았다. `pyproject.toml`/`uv.lock`에는 psycopg가 없으며 환경변수 경로 존재만으로 지원 완료를 의미하지 않는다.

PostgreSQL 전환은 [Phase 7](phase7-final-integration-audit.md) 완료 조건이 아니다. 이번 문서는 계획이며 설치·의존성 변경·DB 이관·row-lock 테스트를 실행하지 않는다.

## 필요성과 목적

SQLite는 여러 reader를 지원하지만 한 DB 파일에는 한 시점에 writer 하나만 허용한다. 현재 규모에서 단일 서버의 `world_change` 잠금·transaction과 SQLite로 시작할 수 있다. 실제 write contention과 동시 사용자 부하를 관찰해 전환 시점을 판단한다. [SQLite 사용 지침](https://www.sqlite.org/whentouse.html)을 참고한다.

PostgreSQL에서는 `select_for_update()`가 transaction 동안 선택 row를 잠근다. Django의 SQLite backend에서는 이 호출에 row-level locking 효과가 없다. ItemEntity owner→UUID 순서, LootClaim 권리 재검증, CurrencyLoot/Share 다중 recipient payout, shared storage와 equipment slot 경쟁의 DB 잠금 계약을 실제로 검증할 수 있다는 점이 전환의 핵심 목적이다. [Django select_for_update](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)를 참고한다.

Writer serialization 한계를 완화하고 장기 운영의 백업·복구 선택지를 확장할 수 있다. 향후 multi-process/multi-server를 검토할 기반이 되지만 DB 변경만으로 scheduler·cache·world state의 다중 서버 안전성이 보장되지는 않는다. PostgreSQL은 SQL dump, 파일 수준 백업, 지속 아카이빙 등 복구 방식이 있으므로 운영 요구에 맞는 절차를 별도로 설계한다. [PostgreSQL backup/restore](https://www.postgresql.org/docs/current/backup.html)를 참고한다.

## 지금 전환하지 않는 이유와 전환 조건

Item System V1 마감과 DB engine 전환을 분리한다. 현재 이관할 실제 production/play DB는 없고 fresh native SQLite가 운영 시작 경로다. PostgreSQL 전용 integration/concurrency suite와 psycopg 3 의존성, backup/restore·장애 대응 절차를 먼저 준비해야 한다.

전환 검토 조건은 관찰된 SQLite write contention, 동시 사용자 증가, multi-process/server 필요, 복구 요구 증가다. PostgreSQL suite와 전체 DB engine 이관 rehearsal을 완료한 뒤 operational cutover를 결정한다. 수치상 동시 사용자 임계값을 근거 없이 정하지 않는다.

## 향후 구현·검증 항목

- psycopg 3 의존성 추가와 `uv.lock` 갱신, 지원 PostgreSQL 버전 선정·설치.
- 최소 권한 role/database 생성과 접속 설정: `PRIMAL_DB_NAME`, `PRIMAL_DB_USER`, `PRIMAL_DB_PASSWORD`, `PRIMAL_DB_HOST`, `PRIMAL_DB_PORT`. 비밀값은 소스·로그에 저장하지 않는다.
- Django schema bootstrap과 SQLite → PostgreSQL **전체 Evennia DB** data migration 설계. 기존 `migrate-items`는 아이템 표현 변환이며 DB engine 이관 도구를 대신하지 않는다.
- ObjectDB/Attribute/계정·Script와 ItemEntity/LootClaim/CurrencyLoot/Share/ledger/runtime marker의 FK·sequence·수량·고유 키·참조 보존 검증.
- PostgreSQL integration suite와 실제 `SELECT FOR UPDATE` contention, deterministic lock order/deadlock·retry 검증.
- LootClaim pickup/expiry/decay, CurrencyLoot 다중 지급, ItemEntity split/merge, shared storage 마지막 수량, equipment slot race, unique_per_owner 동시 생성 검증.
- `pg_dump`/`pg_restore`, 필요한 backup/recovery 전략, restore rehearsal과 복원 후 integrity/smoke.
- 서버 정지·backup·이관·verify·rollback 판단·operational cutover 절차와 운영 모니터링.
- multi-server는 별도 design/validation을 수행한다. PostgreSQL 성공을 multi-server 성공으로 간주하지 않는다.

위 항목은 future infrastructure backlog다. 현재 V1 SQLite 단일 서버의 Phase 7 종료 판정과 분리한다.
