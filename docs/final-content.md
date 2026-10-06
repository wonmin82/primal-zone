# V1 최종 콘텐츠·경제·획득

정적 SSOT는 world/content/final_items.py, items.py, shops.py, loot_v1.py와 지역 ENEMIES다. 이 표는 해당 정의에서 작성했다. 고정 수치는 Phase 6 실행 프롬프트를 반영했고 sanity 차이 때문에 임의 tuning하지 않았다. 모든 weapon modifier는 active_weapon scope이며 나머지는 equipped scope다. 동일 ring 두 개 정책을 유지한다.

## 장비·stable ID·modifier·가격·획득

| 이름 / stable ID | 슬롯·손 | 수치 | 구매(또는 내부 body 값) | 매입 | 획득 |
| --- | --- | --- | ---: | ---: | --- |
| 탐사용 벌목도 / `explorer_machete` | hands/weapon/1H | weapon.attack +2 | 10 | 5 | 신규 시작 |
| 탐사대 작업복 / `expedition_workwear` | body | stat.defense +1 | 10 | 5 | 신규 시작 |
| 절단마체테 / `cutting_machete` | hands/weapon/1H | weapon.attack +4; skill.heavy.damage ×1.02 | 55 | 27 | 기본 병기점 |
| 개척창 / `pioneer_spear` | hands/weapon/2H | weapon.attack +6; skill.heavy.damage ×1.03 | 70 | 35 | 기본 병기점 |
| 정찰권총 / `scout_pistol` | hands/weapon/1H | weapon.attack +5 | 60 / package 108 | 30 | 기본 병기점 |
| 경비카빈 / `guard_carbine` | hands/weapon/2H | weapon.attack +8; skill.shooting.damage ×1.02 | 95 / package 200 | 47 | 기본 병기점, 고장난경비기 드롭 |
| 접이식방패 / `folding_shield` | hands/shield/1H | stat.defense +2 | 45 | 22 | 기본 병기점 |
| 휴대분석기 / `portable_analyzer` | hands/offhand/1H | skill.insight.penetration +0.02 | 35 | 17 | 기본 병기점, 고장난경비기 드롭 |
| 보안고글 / `security_goggles` | head | stat.max_mental +4; skill.insight.damage ×1.01 | 30 | 15 | 기본 장비점, 어린청소룡 드롭 |
| 탐사인식표 / `expedition_tag` | neck | stat.max_hp +6 | 25 | 12 | 수송차 1회 발견 |
| 경량방호복 / `light_protective_suit` | body | stat.defense +2 | 45 | 22 | 기본 장비점 |
| 강화방호조끼 / `reinforced_vest` | body | stat.defense +3; stat.max_hp +6 | 70 | 35 | 기본 장비점 |
| 충격흡수장갑 / `shock_absorbing_gloves` | gloves | skill.heavy.damage ×1.02 | 30 | 15 | 기본 장비점, 갈퀴사냥룡 드롭 |
| 응급벨트 / `emergency_belt` | waist | skill.heal.amount +3 | 35 | 17 | 기본 장비점 |
| 보강탐사바지 / `reinforced_explorer_pants` | legs | stat.max_hp +8 | 35 | 17 | 기본 장비점 |
| 미끄럼방지탐사화 / `non_slip_boots` | feet | stat.defense +1 | 30 | 15 | 기본 장비점, 어린청소룡 드롭 |
| 집중링 / `focus_ring` | ring | stat.max_mental +4 | 30 | 15 | 기본 장비점 |
| 방호링 / `protection_ring` | ring | stat.defense +1 | 35 | 17 | 기본 장비점, 갈퀴사냥룡 드롭 |
| 생존모듈 / `survival_module` | accessory | recovery.hp_per_minute +1 | 45 | 22 | 기본 장비점 |
| 정글장도 / `jungle_longblade` | hands/weapon/1H | weapon.attack +7; skill.heavy.damage ×1.03 | 110 | 55 | 전초 병기고, 날쌘발톱룡 드롭 |
| 파쇄창 / `shattering_spear` | hands/weapon/2H | weapon.attack +9; skill.heavy.damage ×1.04; skill.suppress.reduction +0.01 | 145 | 72 | 전초 병기고 |
| 전술권총 / `tactical_pistol` | hands/weapon/1H | weapon.attack +7; skill.shooting.penetration +0.01 | 95 / package 143 | 47 | 전초 병기고, 그늘추적룡 드롭 |
| 탐사카빈 / `exploration_carbine` | hands/weapon/2H | weapon.attack +10; skill.shooting.damage ×1.03 | 140 / package 245 | 70 | 전초 병기고 |
| 중량소총 / `heavy_rifle` | hands/weapon/2H | weapon.attack +12; skill.shooting.penetration +0.03 | 175 / package 257 | 87 | 전초 병기고 |
| 합성방패 / `composite_shield` | hands/shield/1H | stat.defense +4; stat.max_hp +8 | 105 | 52 | 전초 병기고, 철갑등짐승 드롭 |
| 전술분석단말 / `tactical_analyzer` | hands/offhand/1H | skill.insight.penetration +0.03; skill.insight.damage ×1.02 | 80 | 40 | 전초 병기고, 그늘추적룡 드롭 |
| 응급주입기 / `emergency_injector` | hands/offhand/1H | skill.heal.amount +5 | 80 | 40 | 전초 병기고 |
| 추적고글 / `tracking_goggles` | head | stat.max_mental +6; skill.insight.penetration +0.03 | 75 | 37 | 전초 장비고 |
| 호흡보조마스크 / `breathing_mask` | head | stat.max_mental +12; skill.breathing.amount +3 | 95 | 47 | 전초 장비고 |
| 생체감시장치 / `biomonitor` | neck | stat.max_hp +10 | 65 | 32 | 전초 장비고 |
| 신경안정칼라 / `neural_stabilizing_collar` | neck | stat.max_mental +8; recovery.mental_per_minute +1 | 90 | 45 | 전초 장비고 |
| 전술방호복 / `tactical_protective_suit` | body | stat.defense +4; stat.max_hp +10 | 120 | 60 | 전초 장비고 |
| 중장방호복 / `heavy_protective_suit` | body | stat.defense +5; stat.max_hp +20 | 165 | 82 | 전초 장비고 |
| 타격보조장갑 / `strike_assist_gloves` | gloves | skill.heavy.damage ×1.04 | 65 | 32 | 전초 장비고, 날쌘발톱룡 드롭 |
| 사격안정장갑 / `shooting_stability_gloves` | gloves | skill.shooting.penetration +0.02 | 60 | 30 | 전초 장비고, 그늘추적룡 드롭 |
| 의무전술벨트 / `medical_tactical_belt` | waist | skill.heal.amount +5; recovery.hp_per_minute +1 | 95 | 47 | 전초 장비고 |
| 제압전술벨트 / `suppression_tactical_belt` | waist | skill.suppress.reduction +0.01 | 60 | 30 | 전초 장비고, 그늘추적룡 드롭 |
| 습지방호바지 / `marsh_protective_pants` | legs | stat.max_hp +12; stat.defense +1 | 85 | 42 | 전초 장비고, 철갑등짐승 드롭 |
| 안정화전투화 / `stabilizing_boots` | feet | stat.defense +1; skill.suppress.reduction +0.01 | 70 | 35 | 전초 장비고, 날쌘발톱룡 드롭 |
| 생체안정링 / `bio_stability_ring` | ring | stat.max_hp +6 | 50 | 25 | 전초 장비고 |
| 정신집중링 / `mental_focus_ring` | ring | stat.max_mental +6 | 55 | 27 | 전초 장비고 |
| 제압보조링 / `suppression_ring` | ring | skill.suppress.reduction +0.01 | 50 | 25 | 전초 장비고 |
| 의술보조링 / `medical_ring` | ring | skill.heal.amount +2 | 50 | 25 | 전초 장비고 |
| 재생모듈 / `regeneration_module` | accessory | recovery.hp_per_minute +1 | 75 | 37 | 철갑등짐승 드롭 |
| 정신안정모듈 / `mental_stability_module` | accessory | recovery.mental_per_minute +1 | 75 | 37 | 늪지 1회 발견 |
| 전술연산모듈 / `tactical_computing_module` | accessory | skill.insight.damage ×1.02; skill.suppress.reduction +0.01 | 80 | 40 | 그늘추적룡 드롭 |
| 능선포식자표식 / `ridge_predator_mark` | neck | stat.attack +1; skill.heavy.damage ×1.02 | — | — | 통신탑 첫 최종 보고 |
| 포식자비늘장식 / `predator_scale_charm` | accessory | stat.defense +1; stat.max_hp +12; stat.max_mental +8 | — | — | 밀림 첫 최종 보고 |

multiply modifier의 1.02는 +2%, penetration/reduction의 add 0.01은 +1%p다. field-only의 내부 가격은 구매 가능성을 뜻하지 않는다. Boss unique는 가격이 없으며 소유자별 DB unique, equip/unequip/store만 허용한다.

## 소비품·탄약·탄창

| 이름 / stable ID | unit 구매 | 구매 수량 | 구매 합계 | 개별/빈 매입 |
| --- | ---: | ---: | ---: | ---: |
| 정제수 / `water` | 3 | 1 | 3 | 1 |
| 야전식량 / `field_ration` | 5 | 1 | 5 | 2 |
| 붕대 / `bandage` | 10 | 1 | 10 | 5 |
| 건전지 / `battery` | 8 | 1 | 8 | 4 |
| 탐사용손전등 / `flashlight` | 35 | 1 | 35 | 17 |
| 9mm 소형탄창 / `mag_9_small` | 16 | 1 | 16 | 8 |
| 9mm 표준탄창 / `mag_9_standard` | 24 | 1 | 24 | 12 |
| 9mm 확장탄창 / `mag_9_extended` | 40 | 1 | 40 | 20 |
| 5.56mm 단축탄창 / `mag_556_short` | 30 | 1 | 30 | 15 |
| 5.56mm 표준탄창 / `mag_556_standard` | 45 | 1 | 45 | 22 |
| 5.56mm 확장탄창 / `mag_556_extended` | 65 | 1 | 65 | 32 |
| 7.62mm 표준탄창 / `mag_762_standard` | 50 | 1 | 50 | 25 |
| 7.62mm 확장탄창 / `mag_762_extended` | 70 | 1 | 70 | 35 |
| 9mm 권총탄 / `ammo_9` | 2 | 12 | 24 | 1 |
| 5.56mm 카빈탄 / `ammo_556` | 3 | 20 | 60 | 1 |
| 7.62mm 소총탄 / `ammo_762` | 4 | 8 | 32 | 2 |

탄창 매입은 빈 매입가 + 잔탄 × 해당 탄약의 per-round 매입가다. 총기는 full 표준 탄창을 포함하는 package만 구매하며 body만 구매하는 명령은 제공하지 않는다. 판매·소각 전에 탄창을 분리해야 한다.

## Firearm package 비증식 검사

| 총기 | package | body 매입 | 표준 빈 탄창 매입 | 포함 ammo 매입 | 포함 ammo 직접 구매 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 정찰권총 | 108 | 30 | 12 | 12 | 24 |
| 경비카빈 | 200 | 47 | 22 | 20 | 60 |
| 전술권총 | 143 | 47 | 12 | 12 | 24 |
| 탐사카빈 | 245 | 70 | 22 | 20 | 60 |
| 중량소총 | 257 | 87 | 25 | 16 | 32 |

전 총기에 package > body resale + empty-mag resale + ammo resale와 package − body resale − empty-mag resale ≥ ammo direct purchase를 검증한다.

## Shop catalogs

- **보급품점**: 탐사용손전등, 건전지, 붕대, 야전식량, 정제수
- **기본 병기점**: 절단마체테, 개척창, 정찰권총, 경비카빈, 접이식방패, 휴대분석기, 9mm 소형탄창, 9mm 표준탄창, 5.56mm 단축탄창, 5.56mm 표준탄창, 9mm 권총탄, 5.56mm 카빈탄
- **기본 장비점**: 보안고글, 경량방호복, 강화방호조끼, 충격흡수장갑, 응급벨트, 보강탐사바지, 미끄럼방지탐사화, 집중링, 방호링, 생존모듈
- **전초 병기고**: 정글장도, 파쇄창, 전술권총, 탐사카빈, 중량소총, 합성방패, 전술분석단말, 응급주입기, 9mm 소형탄창, 9mm 표준탄창, 9mm 확장탄창, 5.56mm 단축탄창, 5.56mm 표준탄창, 5.56mm 확장탄창, 7.62mm 표준탄창, 7.62mm 확장탄창, 9mm 권총탄, 5.56mm 카빈탄, 7.62mm 소총탄
- **전초 장비고**: 추적고글, 호흡보조마스크, 생체감시장치, 신경안정칼라, 전술방호복, 중장방호복, 타격보조장갑, 사격안정장갑, 의무전술벨트, 제압전술벨트, 습지방호바지, 안정화전투화, 생체안정링, 정신집중링, 제압보조링, 의술보조링

accepts는 category 기반이고 purchase catalog와 독립이다. T2 무기/착용 장비/field-only accessory도 해당 기본점에서 판매할 수 있다.

## Enemy V1·드롭

| 적 | HP | ATK | DEF | XP | 칩 | 자원 roll / 성공 후 weight | special 절대 확률 | trophy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 어린청소룡 | 24 | 5 | 0 | 22 | 8 | 30%: 정제수 50%, 야전식량 35%, 붕대 15% | 보안고글 4%, 미끄럼방지탐사화 4%; 없음 92% | 없음 |
| 갈퀴사냥룡 | 45 | 9 | 2 | 38 | 14 | 30%: 붕대 50%, 야전식량 30%, 정제수 20% | 충격흡수장갑 6%, 방호링 4%; 없음 90% | 없음 |
| 고장난경비기 | 65 | 11 | 5 | 55 | 20 | 25%: 건전지 40%, 5.56mm 카빈탄 60% 2~5개 | 휴대분석기 8%, 경비카빈 7%; 없음 85% | 없음 |
| 능선의우두머리 | 170 | 17 | 6 | 130 | 50 | 없음 | 없음 | 우두머리송곳니 100% |
| 날쌘발톱룡 | 58 | 15 | 2 | 55 | 18 | 30%: 붕대 45%, 야전식량 35%, 정제수 20% | 정글장도 3%, 타격보조장갑 3.5%, 안정화전투화 3.5%; 없음 90% | 없음 |
| 철갑등짐승 | 105 | 12 | 10 | 70 | 24 | 35%: 회수부품 100% 1~2개 | 합성방패 4.5%, 습지방호바지 4.5%, 재생모듈 3%; 없음 88% | 없음 |
| 그늘추적룡 | 110 | 18 | 4 | 84 | 29 | 30%: 붕대 50%, 야전식량 30%, 정제수 20% | 전술권총 5%, 전술분석단말 3%, 사격안정장갑 2%, 제압전술벨트 2%, 전술연산모듈 3%; 없음 85% | 없음 |
| 밀림의포식자 | 270 | 20 | 8 | 155 | 58 | 없음 | 없음 | 포식자 비늘 100% |

자원/소비품과 special은 서로 독립 roll이고 각각 최대 1종/1개다. 고장난경비기의 경비카빈은 5.56mm 단축탄창 2~6발, 그늘추적룡의 전술권총은 9mm 표준탄창 2~5발이다. Enemy drop을 full_standard로 생성하지 않는다. Boss random equipment drop은 없고 unique는 최종 보고에서 준다. XP는 기존 즉시 보상이다.

## Boss scaling

기존 reward_groups의 eligible participant 수를 재사용한다. max HP는 floor(base HP × (1 + 0.75 × (n−1)))다. 1/2/3/4명은 1/1.75/2.50/3.25배이고 integer HP는 내린다. 공격력은 변하지 않는다. late eligible join 시 max HP 증가분만 current HP에 더하고 기존 damage를 보존한다. 같은 encounter에서는 참여자 이탈·timeout으로 downscale하지 않는다. respawn/완전 회복 후 다음 encounter는 1명 기준이다.

## Deterministic balance sanity

- Lv4 평균 T1: 능선 Boss 기본 12 opportunities / 기술 활용 9. Lv7 T1/T2 혼합: 밀림 Boss 기본 13 / 기술 활용 10.
- 손 조합의 대표 Lv4 ATK/DEF: {'2H': {'attack': 21, 'defense': 4, 'max_hp': 112}, '1H+shield': {'attack': 19, 'defense': 6, 'max_hp': 112}, '1H+offhand': {'attack': 19, 'defense': 4, 'max_hp': 112}, '1H+1H': {'attack': 19, 'defense': 4, 'max_hp': 112}}. 2H는 공격, shield는 방어, offhand는 간파 modifier, dual weapon은 active 선택의 역할 차이를 유지한다. 이 작은 계산으로 전체 build dominance를 판정하지 않는다.
- penetration: raw30의 DEF0/2/10 및 0/10/30% penetration 피해: {'0': {'0': 30, '0.1': 30, '0.3': 30}, '2': {'0': 27, '0.1': 27, '0.3': 28}, '10': {'0': 20, '0.1': 20, '0.3': 22}}. 높은 DEF에서 차이가 커지는 계약을 확인한다.
- 경비카빈의 경비기 기본 공격 예시: 4발 ×3칩 = 12칩, 예상 전리품 가치 대비 44.6%. 목표15~30%보다 높다. 확정 attack/price/drop을 바꾸지 않고 Phase 7 ammo cost/build simulation 검토 항목으로 남긴다.
- 칩+매입/정산 기준 EV: {'scavenger': 9.785, 'hunter': 16.57, 'sentinel': 26.905, 'dartclaw': 22.94, 'shellback': 34.59, 'stalker': 36.715}. 회수부품은 정산율10, firearm drop은 body+빈 탄창+평균 잔탄 매입가를 합친다. T1/T2 upgrades의 전투 횟수 체감은 Phase 7에서 검증한다.

## 검증과 경계

world.test_final_content와 관련 pure regressions, tests.test_phase6_runtime/tests.test_item_migration 및 영향 범위 통합 테스트로 정의·경제·drop·지급·변환을 검증한다. 실제 실행 결과/CI는 [playtest](playtest.md)에 남긴다. 전체 local suite·smoke-full·전체 browser/multiplayer·OS IME·PostgreSQL/multi-server 경쟁·full balance simulation과 실제 플레이 DB 변환은 미실행이다. [migration 운영 절차](item-migration.md)를 별도로 따른다.

## 승인된 progression 보완

초기 Phase 6에서는 T1 drop에서 사라진 발전기 자원을 보충하기 위해 수송차에 일반 회수부품3개를 추가했다. 이 초기안은 아래 PR #34 리뷰 결정으로 정비용 회수부품으로 대체되었다. 기존 cache의 신규 장비 보상도 아래 migration entitlement로 소급하며 cache 자체를 다시 열지는 않는다.


## PR #34 리뷰 보완 — 진행 자원·귀속·발견 보상

초기 Phase 6의 일반 회수부품3개 보급안을 리뷰에서 정비용 회수부품(`generator_repair_part`)으로 대체했다. 일반 scrap의 field drop·정산 환율·처분 정책은 그대로이며 발전기는 정비용 부품3개만 submit한다. 수송차 보급상자는 붕대2개·탐사인식표와 정비용 부품 총3개를 확보하게 한다. Migration에서 이미 지급한 부품은 중복 지급하지 않는다.

정비용 회수부품은 stack/max_stack3, transferable=false, submit-only이며 shop 구매·매입·가치·drop·give·store·burn·consume 대상이 아니다. Alias는 정비부품/발전기부품이다. 획득처는 fixed discovery와 명시적인 미수리 migration entitlement다.

Boss unique의 store=true는 개인 보관에만 유효하다. Shared Container는 다른 owner이므로 owner-changing transfer의 transferable 검사를 통과해야 한다. 내부 tree의 귀속 물품도 검사한다. First final report 메시지는 실제 신규 지급한 unique 이름을 표시하며 반복 대화나 Credential 재발급에서 unique 지급을 다시 안내하지 않는다.

기존 supply/jungle cache 완료 캐릭터의 탐사인식표/정신안정모듈은 owner tree에 없을 때 Explorer migration source transaction에서 소급한다. 이미 보유한 UUID/sequence를 유지한다. Full/idle alive 적은 콘텐츠 max HP 변경 시 새 max 기준 full을 유지하고 damaged/combat 상태는 기존 HP를 clamp한다. Boss scaling 참가자 수와 확정 수치는 변경하지 않는다.

경비카빈 대표 전투 탄약 지출12칩은 경비기 expected gross 약26.9칩의44.6%로 목표15~30%를 초과한다. 이번 리뷰에서 가격·전투·drop 수치를 변경하지 않는다. Phase 7 full balance simulation에서 melee/firearm progression·shots-to-kill·refill cadence와 함께 재검토한다.
