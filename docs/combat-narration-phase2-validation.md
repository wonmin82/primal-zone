# 전투·회복 Narration Phase 2 검증

[Design Freeze](combat-equipment-narration-design-v1.md)의 출력 계약을 기준으로 한다. PR-A의 선택 라벨 조사 정책은 [장비 조사 Addendum](https://github.com/wonmin82/primal-zone/issues/95#issuecomment-7035053750)에 따른다.

공유 전투·대련은 확정된 HP 감소량을 순수 전투 표현에 전달한다. 표현은 공격 시점의 장비 스냅샷과 Actor 정적 선언을 읽는다. 보스 주기 규칙은 Combat Profile, 특수 공격과 예고 문구는 Actor Narration에 둔다. 명시적 회복의 공통 표현은 기존 `presentation.py`에서 구성한다.

## 출력 계약 대응

공격·회복 원문은 확정 수치를 사용한다. 문자열만 생성하는 기존 안내·오류의 역할은 기본 텍스트이며, 새 역할을 부여하지 않는다. PASS는 표에 적은 대표 출력 계약과 해당 회귀 범위의 결과다.

| OC | 행동 | 기대 원문·조건 | 실행 경로 | 역할·강조 범위 | 자동 검사 및 범위 |
|---|---|---|---|---|---|
| OC-01 | 근접 일반 | 개척창으로 갈퀴사냥룡을 찔렀다. 5 피해를 입혔다. | shared_combat → combat_narration | 이름(item·hostile), 공격 동사, 피해 및 기본 텍스트 | `test_attack_narration` · PASS (스냅샷) |
| OC-02 | 총기 일반 | 경비카빈으로 고장난경비기를 쏘았다. 8 피해를 입혔다. | shared_combat → combat_narration | 이름(item·hostile), 공격 동사, 피해 및 기본 텍스트 | `test_attack_narration` · PASS (스냅샷) |
| OC-03 | 맨손 | 맨손으로 어린청소룡을 때렸다. 3 피해를 입혔다. | shared_combat → combat_narration | hostile·combat_verb_outgoing·damage_dealt·text | `test_attack_narration` · PASS (스냅샷) |
| OC-04 | 강타 | 정글장도로 갈퀴사냥룡에게 강타를 가했다. 12 피해를 입혔다. | shared_combat → combat_narration | 이름(item·hostile), 공격 동사, 피해 및 기본 텍스트 | `test_combat_narration` · PASS (스냅샷) |
| OC-05 | 사격 기술 | 경비카빈으로 고장난경비기를 집중 사격했다. 18 피해를 입혔다. | shared_combat → combat_narration | 이름(item·hostile), 공격 동사, 피해 및 기본 텍스트 | `test_combat_narration` · PASS (스냅샷) |
| OC-06 | 견제 | 갈퀴사냥룡을 견제했다. 7 피해를 입혔다. 다음 2회 공격력이 10% 감소한다. | shared_combat → combat_narration | hostile·combat_verb_outgoing·damage_dealt·status_debuff·text | `test_combat_narration` · PASS (스냅샷) |
| OC-07 | 간파 | 갈퀴사냥룡의 빈틈을 간파했다. 다음 공격의 방어 관통이 20%, 피해가 15% 증가한다. | shared_combat → combat_narration | hostile·text·status_buff | `test_combat_narration` · PASS (스냅샷) |
| OC-08 | 간파 후 | 간파한 빈틈을 노려 정글장도로 갈퀴사냥룡을 크게 베었다! 18 피해를 입혔다. | shared_combat → combat_narration | 이름(item·hostile), 공격 동사, 피해 및 기본 텍스트 | `test_combat_narration` · PASS (스냅샷) |
| OC-09 | 적 일반 | 갈퀴사냥룡이 날카로운 발톱으로 당신을 할퀴었다. 6 피해를 입었다. | shared_combat → combat_narration | hostile·combat_verb_incoming·damage_taken·text | `test_attack_narration, test_combat` · PASS (스냅샷) |
| OC-10 | 적 특수 | 밀림의포식자가 몸을 날려 당신을 거세게 덮쳤다! 42 피해를 입었다. | shared_combat → combat_narration | hostile·combat_verb_incoming·damage_taken·text | `test_combat_narration, test_combat` · PASS (스냅샷) |
| OC-11 | 특수 예고 | 밀림의포식자가 숨을 고르며 도약할 자세를 취한다. | shared_combat → combat_narration | warning·hostile·text | `test_combat_narration, test_combat` · PASS (스냅샷) |
| OC-12 | 적 사망 | 갈퀴사냥룡이 더는 버티지 못하고 바닥에 쓰러졌다. | shared_combat | hostile·text | `test_combat` · PASS (직접 출력 검증) |
| OC-13 | 자기 치료 | 상처를 치료했다. 체력이 12 회복되고 정신력 5를 소모했다. | skill_services·shared_combat → presentation | hp_recovered 숫자 | `test_growth` · PASS (스냅샷) |
| OC-14 | 동료 치료 실행 | 철수를 치료했다. 철수의 체력이 12 회복되고 정신력 5를 소모했다. | skill_services·shared_combat → presentation | player 이름 및 hp_recovered 숫자 | `test_growth` · PASS (스냅샷) |
| OC-15 | 동료 치료 수신 | 철수의 치료로 체력이 12 회복됐다. | skill_services·shared_combat → presentation | player 이름 및 hp_recovered 숫자 | `test_growth` · PASS (스냅샷) |
| OC-16 | 호흡 | 호흡을 가다듬었다. 정신력이 8 회복됐다. | skill_services·shared_combat → presentation | mental_recovered 숫자 | `test_growth` · PASS (스냅샷) |
| OC-17 | 붕대 | 붕대 하나를 사용했다. 라벨이 있는 경우 ‘붕대 2를 사용했다.’ 뒤 실제 회복량을 표시한다. | skill_services·shared_combat → presentation | item·text 및 hp_recovered 숫자 | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-18 | 음식 | 탐사식량을 먹었다. 체력이 8 회복됐다. | item_equipment_services → presentation | item·text 및 hp_recovered 숫자 | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-19 | 음료 | 식수를 마셨다. 체력이 5 회복됐다. | item_equipment_services → presentation | item·text 및 hp_recovered 숫자 | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-20 | 패배 응급 처치 | 응급 처치로 체력이 10으로 회복됐다. 추가 회복이 필요하다. (10은 최종 HP 예시) | shared_combat → presentation | hp_recovered 숫자 | `test_combat` · PASS (스냅샷) |
| OC-21 | 회복 예약 | 다음 차례에는 공격 대신 치료한다. (성공색 금지) | skill_services | 기본 text | `test_growth` · PASS (직접 출력 검증) |
| OC-22 | 회복 실패 | 이미 체력이 가득합니다. | skill_services → Gateway | 실패 기본 텍스트 | `test_growth` · PASS (기존 출력 회귀) |
| OC-23 | 대련 시작 | 대련을 시작합니다. 최대 10분이며, 자동 공격과 별도로 60초마다 전투 행동을 입력해야 합니다. | duel | 기본 텍스트 | `test_exclusive_duel` · PASS (기존 출력 회귀) |
| OC-24 | 대련 상대 공격 | 개척창으로 능선의우두머리를 찔렀다. 상대의 대련 체력에 12 피해를 입혔다. | duel → shared_combat | 이름(item·hostile), 공격 동사, 피해 및 기본 텍스트 | `test_combat_narration, test_exclusive_duel` · PASS (스냅샷) |
| OC-25 | 대련 피격 | 능선의우두머리가 당신을 들이받았다. 대련 체력이 9 감소했다. | duel → shared_combat | hostile·combat_verb_incoming·damage_taken·text | `test_combat_narration, test_exclusive_duel` · PASS (스냅샷) |
| OC-26 | 대련 기술 | 기술 고유 의미+대련 체력 결과 | duel → shared_combat | 이름(item·hostile), 공격 동사, 피해 및 기본 텍스트 | `test_combat_narration, test_exclusive_duel` · PASS (직접 출력 검증) |
| OC-27 | 대련 승리·패배·기권 | 대련이 끝났습니다. 승리. / 패배. / 기권. | duel | 기본 텍스트 | `test_exclusive_duel` · PASS (기존 출력 회귀) |
| OC-28 | 대련 시간 초과·연결 유예 | 대련이 끝났습니다. 시간 초과. / 연결 유예 만료. | duel | 기본 텍스트 | `test_exclusive_duel` · PASS (기존 출력 회귀) |
| OC-29 | 무기 무장 | 정찰권총으로 무장했다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-30 | 무장 해제 | 정찰권총을 해제했다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-31 | 주무기 지정 | 정찰권총을 주무기로 지정했다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-32 | 방패 장착 | 접이식방패를 들었다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-33 | 방패 해제 | 접이식방패를 내려놓았다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-34 | 머리 착용 | 보안고글을 썼다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-35 | 몸 방어구 | 경량방호복을 입었다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-36 | 장갑 | 충격흡수장갑을 꼈다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-37 | 신발 | 미끄럼방지탐사화를 신었다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-38 | 반지 | 집중링을 꼈다. | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-39 | 기타 해제 | 실제 슬롯별 공식 해제 동사 | item_equipment_services | item·text·success | `test_item_equipment_actions` · PASS (스냅샷) |
| OC-40 | 장비 실패 | 기존 검증 오류 | item_equipment_services | 기존 text·warning·error | `test_item_equipment_actions` · PASS (직접 출력 검증) |
| OC-41 | 탄약 부족 | 기존 탄약 부족·재장전 안내 | firearm_service → combat_narration | error·text | `test_firearms, test_combat_narration` · PASS (직접 출력 검증) |
| OC-42 | 정신력 부족 | 기존 필요한 정신력 안내 | rules → combat_narration | error·text | `test_growth, test_combat_narration` · PASS (직접 출력 검증) |
| OC-43 | 재사용 대기 | 기존 남은 시간 안내 | rules → combat_narration | error·text | `test_growth, test_combat_narration` · PASS (직접 출력 검증) |
| OC-44 | 대상·권한 오류 | 이곳에는 공격할 수 있는 상대가 없습니다. | Action Gateway·shared_combat | 기존 사용자 오류 텍스트 | `test_combat, test_exclusive_duel` · PASS (기존 출력 회귀) |
| OC-45 | 교전 시작 | 갈퀴사냥룡과 교전을 시작했다. | shared_combat | hostile 이름·text | `test_combat` · PASS (직접 출력 검증) |
| OC-46 | 교전 종료 | 교전을 끝냈습니다. 적은 일정 시간 아무도 싸우지 않으면 회복합니다. | global_actions.flee → shared_combat | 기본 텍스트 | `test_combat` · PASS (기존 출력 회귀) |
| OC-47 | 처치 보상 | 이번 사냥으로 경험치 N을 얻었다. 보급칩은 시체에서 회수할 수 있다. | shared_combat → presentation.reward | text·reward | `test_combat` · PASS (기존 출력 회귀) |
| OC-48 | 패배·구조 | 기존 의무실·칩 손실·응급 처치 계약 | shared_combat → presentation | text 및 hp_recovered 숫자 | `test_combat, test_medical` · PASS (스냅샷) |

견제 적용 메시지는 OC-06의 완성 문장대로 주격 조사를 붙인다. 의미 강조 범위는 ‘공격력이 N% 감소’이다.

## 검증 경계

| Gate | 근거 |
|---|---|
| G1 | Actor 특수 표현 이전 및 누락·레거시 필드 검증, Actor·무기·맨손 선언 검사 |
| G2 | 공식 렌더러 원문·역할 스냅샷과 보존된 기본 텍스트 출력 회귀 |
| G3 | Phase 1 고정 RNG 기준선, 공유 전투·대련·회복·보상 회귀 및 독립 감사. 모든 시나리오의 구·신 별도 실행 대조는 UNVERIFIED |
| G4 | 위 OC-01~48 대응, 피해 경계 및 보스 Scaling 통합 회귀 |
| G5 | Text·JS·CSS 역할과 RGB, ANSI Reset, Telnet·SSH 무색 옵션 및 원문 보존 검사 |
| G6 | 실제 Chromium E2E-04·06·15에서 색상·굵기와 데스크톱·390px 공격 로그 폭을 검사. 수동 시각 평가와 실제 터미널 가독성은 UNVERIFIED |
| G7 | 격리 Quick Smoke·필수 CI, 표현 예외 Rollback, 전송 실패, 중복 Tick·대련 종료·재시작 테스트의 실행 결과는 PR 검증 기록 참조 |

전투 피해 계산, 임시 대련 HP 저장 및 구조 이후 HP 갱신을 기존 위치에서 유지한다. 표시용 적용 피해는 공격 전후의 확정 결과에서 얻는다. 예약과 실행 메시지는 기존 이벤트 순서로 전송하며 새 로그 수신자는 추가하지 않는다.

### 공격 후보 추가 시 검수

- 정적 검증에서는 후보 선언 구조와 타입, 빈 문자열과 문장부호, 확인된 도구격 중복과 목적어 충돌, 알려진 자동사·피동 패턴을 검사한다. `무거운 팔로`는 조사가 붙은 수단이라 거절하며, `고압 회로`와 `휴대 화로`의 `로`는 명사의 일부로 허용한다.
- Actor·무기·맨손에 공격 후보를 추가할 때는 후보마다 실제 전투 렌더러의 기본·강조·Severe 문장과 의미 세그먼트를 [Golden Snapshot](../game/world/test_attack_narration.py)에 함께 추가한다. 수단과 동사의 의미가 맞는지, 조사가 자연스럽고 목적어가 겹치지 않는지, Severe의 느낌표와 동사·피해 역할 범위가 정확한지 완성 문장에서 검수한다. 알려진 패턴을 벗어난 표현의 문법과 자연스러움은 정적 검사만으로 판정할 수 없다.

### PR #100 리뷰 후 회귀 검증

- P2·G5는 피해량과 회복량 네 역할에만 굵기 합성을 허용한다. Text 역할 계약과 실제 전투·회복·대련 로그의 Playwright 단언에 합성 정책을 추가했다.
- G6의 글꼴 표본은 Chromium에서 동봉한 NeoDunggeunmo Code Regular를 로드했다. 1366px와 390px에서 한글·영문·숫자가 섞인 동일 문자열을 14px 및 24px로 비교했다. 네 역할 모두 같은 요소에서 합성만 전환했을 때 화면 픽셀이 달라졌고, 캡처를 직접 확인해 일반 굵기와 강조 굵기를 구별할 수 있었다. 실제 로그의 좁은 화면 자동 검증과 별도로 수행했다. 실제 터미널 가독성은 UNVERIFIED다.
- P3·G3은 정수값 float 0.0·1.0을 복구해 후보 순환, 예약 Tick 중복 방지, 기권과 쿨다운을 검증했다. 비정수·음수·유한하지 않은 값과 잘못된 타입은 기존 invalid-state 경로에서 종료했고, 피해·자원·아이템·RNG 소비가 없음을 검증했다. 기존 main이 허용하던 비정수 회차의 거절은 의도한 변경이다. 전체 시나리오의 구·신 별도 실행 대조는 UNVERIFIED다.
- G3의 대련 교차 실행은 main `43a899c`와 P3 수정본의 격리 복사본에서 동일 프로브와 `Random(1)`을 사용했다. 회차 0·0.0의 일반 사격과 1·1.0의 사격 기술에서 양쪽 임시·실제 HP, 정신력, 탄약, 회차, 예약·중복 Tick, RNG 상태, 기권·쿨다운과 XP가 일치했다. 1.5에서 main은 사격 자원을 썼고 수정본은 재시작 복구 중 소비 없이 중단했다.
