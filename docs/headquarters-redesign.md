# 본부 빌딩 개편

## 현재 배치

본부는 지상 5층과 옥상, 공용 승강기 하나로 구성한다. 활성 Room은 46개다. 부두는 외부 지역이므로 이 수에 포함하지 않는다. 지하층·커피숍·새 NPC·새 서비스는 추가하지 않는다. 상세 첨부 명세가 없는 상태에서 요청의 핵심 배치를 구현했으며, 5층은 기존 장비/병기 시설의 서쪽/동쪽 관계와 출입 정책을 유지한다.

| 층 | 중앙 ID | 구성 | Room 수 |
| --- | --- | --- | ---: |
| 1층 | `hq_concourse` | 중앙 로비·출정 대기실·관리실·휴게실 | 4 |
| 2층 | `support_2f_c` | 복도 3개·보관실·보급품 상점·자원 정산소 | 6 |
| 3층 | `support_3f_c` | 복도 3개·의료 대기실·의무실·회복실 | 6 |
| 4층 | `support_4f_c` | 복도 3개·교육시설 6개 | 9 |
| 5층 | `support_5f_c` | 복도 5개·장비/병기 시설 6개 | 11 |
| 옥상 | `support_roof` | 중앙·8방향 구역 | 9 |
| 공용 | `support_elevator` | 기존 단일 승강기 | 1 |

1층 로비의 북쪽은 `staging_room`, 서쪽은 `dock`, 동쪽은 `hq_admin_office`, 남쪽은 `hq_lounge`다. 아래 복도는 서쪽에서 동쪽으로 이어지고, 시설은 표의 방향에서 진입한다. 모든 일반 출구는 정의된 역방향으로 복귀한다.

| 층 | 복도 | 북쪽 | 남쪽 |
| --- | --- | --- | --- |
| 2층 | `support_2f_w1` | `storage_room` | 폐쇄 |
| 2층 | `support_2f_c` | `supply_shop` | 폐쇄 |
| 2층 | `support_2f_e1` | `salvage_office` | 폐쇄 |
| 3층 | `support_3f_w1` | `medical_waiting` | 폐쇄 |
| 3층 | `support_3f_c` | `infirmary` | 폐쇄 |
| 3층 | `support_3f_e1` | `recovery_room` | 폐쇄 |
| 4층 | `support_4f_w1` | `training_room` | `survival_training_room` |
| 4층 | `support_4f_c` | `training_office` | `tactics_room` |
| 4층 | `support_4f_e1` | `shooting_range` | `medical_training_room` |
| 5층 | `support_5f_w2` | `outpost_equipment` | `reserved_equipment` |
| 5층 | `support_5f_w1` | `armor_shop` | 폐쇄 |
| 5층 | `support_5f_c` | 폐쇄 | 폐쇄 |
| 5층 | `support_5f_e1` | `weapon_shop` | 폐쇄 |
| 5층 | `support_5f_e2` | `outpost_weapon` | `reserved_weapon` |

기본 장비점/병기점의 catalog·가격은 [최종 콘텐츠](final-content.md)를 따른다. 전초 두 시설은 기존 `outpost_supply_pass`가 필요하다. 예약 두 시설은 기존 `special_supply_pass` 계약과 `available=False`를 유지하므로 출입증을 가졌어도 아직 열리지 않는다. [접근·상점 정책](credentials-access-shops.md)은 바꾸지 않는다.

## NPC와 서비스

본부와 부두의 기존 NPC 21명을 재배치한다. 신규 NPC는 없다. 부두의 윤대장, 2층 보급관·정산관, 3층 의무관, 5층 기존 상인 4명은 stable ID·고유 대사·기능을 유지한다. 보관 객체와 침대도 기존 객체를 재사용한다.

| 4층 교육시설 | NPC ID |
| --- | --- |
| `training_room` | `trainer_attack`, `trainer_heavy`, `trainer_strength` |
| `survival_training_room` | `trainer_defense`, `trainer_constitution`, `trainer_breathing` |
| `training_office` | `instructor` |
| `tactics_room` | `trainer_suppress`, `trainer_wisdom` |
| `shooting_range` | `trainer_shooting`, `trainer_insight`, `trainer_agility` |
| `medical_training_room` | `trainer_heal` |

기술·특성 교관 12명과 훈련관리관 1명이다. 담당 ID·학습 조건·재분배·비전투 제한은 [성장 계약](progression.md)을 유지한다. 새 의료 대기실·회복실은 공간만 제공하며 회복 보너스나 새 의료 기능을 추가하지 않는다. 기존 의무실의 회복·진료·침대, 로비와 옥상의 회복 값도 유지한다.

## 계단과 승강기

각 층 중앙에서 `계단 올라`·`계단 내려`로 인접 층만 이동한다. 1층에는 올라가기, 옥상에는 내려가기만 있다. 방 안의 본문과 Web 주변 행동이 같은 서버 명령을 표시한다. 계단실 Room·방향 Exit는 만들지 않으며 전투 중 이용할 수 없다.

승강기는 기존 `support_elevator`와 persistent `current_stop`을 보존한다. 정류장은 1~5층·옥상이다. 층 선택자는 자동 하차하고 다른 승객은 공용 승강기에 남는다. 수동 `내려`, 동시 요청의 transaction, 정상 층의 bootstrap/restart 보존은 기존 계약을 따른다. 계단 이동은 승강기의 공용 현재 층을 변경하지 않는다.

새 로그인·재로그인은 출정 대기실, 일반 `귀환`은 옥상, 패배 후 구조는 3층 의무실이다. 패배 손실·진료·침대·진행 보존 정책은 변경하지 않는다.

## 영속 데이터와 반복 bootstrap

새 Room 14개는 관리실·휴게실·의료 대기실·회복실·생존훈련실·의료훈련실과 4층 복도 3개·5층 복도 5개다. 폐지된 복도 9개는 다음 공간으로 contents를 옮긴다.

| 폐지 ID | 대체 공간 |
| --- | --- |
| `support_1f_w2`, `support_1f_w1`, `support_1f_c`, `support_1f_e1`, `support_1f_e2` | `hq_concourse` |
| `support_2f_w2` | `support_2f_w1` |
| `support_2f_e2` | `support_2f_e1` |
| `support_3f_w2` | `support_3f_w1` |
| `support_3f_e2` | `support_3f_e1` |

폐지 Room 객체 자체는 삭제하지 않는다. `primal_zone_room` 활성 tag를 제거하고 `primal_retired_room` tag·`retired_to`를 남겨 FK·home·prelogout 참조와 원래 방문 기록을 보존한다. 따라서 이전 월드 DB에는 활성 46개 외에 보존용 Room 9개가 남을 수 있다. 이를 현재 시설 수에 포함하지 않는다.

플레이어·DroppedLoot/Corpse·일반 객체는 객체 identity를 보존한 채 대체 공간으로 옮긴다. 전리품 owner 객체를 재생성하지 않아 ItemEntity UUID·sequence·quantity·tree·state와 권리/화폐 share를 유지한다. 폐지된 관리 출구는 `primal_zone_exit` tag 기준으로만 정리하며 사용자 생성 출구와 본부 밖의 무관한 stale 객체는 보존한다. 기존 Room·NPC·Exit는 stable tag로 재사용한다. `build_world()`는 transaction 안에서 처리하며 재실행으로 방·출구·NPC를 중복 생성하거나 아이템·개인 기록을 초기화하지 않는다.

일반 개발 DB에 이번 검증용 bootstrap을 실행하지 않는다. 실제 운영 적용은 코드 갱신 후 기존 월드 bootstrap 경로를 이용하며 ItemEntity migration·schema 변경은 필요하지 않다.

## 관리 출구 소유권과 충돌 처리

`primal_zone_exit`의 정확한 `Room ID:방향` identity 하나를 가진 관리 Exit만 재사용한다. 해당 객체는 올바른 출발 Room·방향 key·Exit typeclass를 가져야 한다. 관리 identity 중복·복수 관리 태그·잘못된 위치/방향은 거절한다. 정상 관리 Exit의 ID는 유지하고 정의가 소유하는 목적지·별칭은 최신 배치에 맞춰 갱신한다. 관리 태그가 없는 객체는 이름만 같아도 편입하지 않는다. 다른 시스템 태그도 소유권 증거가 아니다.

`build_world()`는 runtime 초기화와 Room/Exit/NPC/플레이어 변경보다 먼저 transaction 안에서 읽기 전용 충돌 검사를 수행한다. 필요한 방향의 정식 이름·영문 alias·기본 방향 단축어와 겹치는 미관리 Exit, 폐쇄 방향에 이동 가능한 미관리 Exit가 있으면 Room ID·방향·충돌 Exit ID·기존 목적지를 포함한 오류로 중단한다. 기존 Exit의 key/alias/tag/목적지를 변경하거나 삭제하지 않고 새 관리 Exit도 추가하지 않는다. 충돌을 성공한 bootstrap으로 간주하지 않는다.

폐지된 정식 관리 Exit 정리와 폐지 복도의 archive/contents 보존은 기존 계약을 유지한다. 폐지 Room의 사용자 출구는 보존한다. 이름만 일치하는 태그 누락 객체를 레거시 관리 출구로 자동 추정하는 경로는 없다.

운영자는 서버를 정지하고 백업한 뒤 오류에 표시된 Room/Exit ID·목적지·태그·별칭과 원래 소유권을 확인한다. 사용자 출구가 필요한 방향/폐쇄 방향을 점유했다면 소유자의 의도를 확인해 이름/별칭 또는 위치를 명시적으로 조정한다. 관리 identity가 중복되거나 누락됐다면 과거 설치/변경 기록으로 관리 객체를 확인한 경우에만 올바른 태그·위치를 복구한다. 단순 이름 일치로 태그를 붙이거나 데이터/사용자 출구를 삭제해 우회하지 않는다. 다시 `validate_managed_exits()`로 읽기 전용 검사를 통과한 뒤 정상 `build_world()`와 재실행 idempotency를 확인한다. 이번 검증은 격리 DB에서만 수행했다.

## 계단 알림과 도움말 경계

계단과 승강기의 출발·도착 presence 알림은 각각 해당 방에 있을 때 `can_perceive()`의 위치·view lock·시야 정책으로 관찰자를 확정한다. 가장 바깥 `world_change()` 성공 이후 `after_change()`로 한 번 전달하고 실패/rollback에서는 전달하지 않는다. 출발 시점의 관찰 결정을 보존하므로 이동 후 위치 검사로 출발 알림이 사라지지 않는다. 전달 시에는 여전히 해당 방에 접속해 있는 관찰자만 받는다. 일반 방향 이동은 기존 즉시 presence 경로를 유지한다.

`계단 도움말`의 metadata는 전역 도움말에만 포함하고 실제 실행 CmdSet에는 전역 추가하지 않는다. 일반 Room에서도 사용법과 1층/옥상 경계를 조회할 수 있지만 `계단 올라`/`계단 내려` 실행은 여섯 중앙 공간에서만 가능하다. 후치형 명령·개인 줄임말·채팅 parser는 바꾸지 않는다.

4층 설명은 대련/무기/중량, 방호/체력/호흡, 기록/상담/재훈련 안내, 작전 지도/지형/분석판, 사격/이동 표적/기동, 처치 모형/응급 실습의 고정 설비를 서술한다. NPC 행동은 presence로 분리하며 새 기능이나 회복 효과는 없다.

## 검증 안내

자동 검증은 활성 Room 수·역방향 출구·폐쇄 방향·NPC 21명과 교관 배치·모든 중앙 층 계단 왕복·승강기 공유/자동 하차·학습/재분배·의료·상점·출입 권한·방문/참조/전리품 보존·반복 bootstrap을 검사한다. 출구 충돌·계단 알림/도움말 보완은 [PR #40 리뷰 수정 검증](playtest.md#pr-40-본부-개편-리뷰-수정-2026-10-08)을 따른다. 최초 실제 브라우저와 격리 서버 검증의 실행 결과 및 실패→수정 이력은 [개편 당시 playtest 기록](playtest.md#본부-5층-개편-검증-2026-10-08)에 보존한다.

권장 수동 동선은 대기실 → 남(로비) → 계단 올라(2층) → 서·북(보관실), 3층 중앙 → 북(의무실), 4층 서쪽 → 북/남(전투/생존 훈련), 4층 중앙 → 북/남(관리/전술), 4층 동쪽 → 북/남(사격/의료 훈련), 5층 동쪽 → 북(기본 병기점)이다. 옥상 8방향과 승강기 여섯 정류장도 확인한다.

과거 본부 1~7단계와 Item System V1 실행 기록은 당시 구조·수치 그대로 보존한다. 현재 배치는 이 문서와 [architecture](architecture.md#현재-본부-room-구조)를 따른다.
