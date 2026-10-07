# Phase 7C 밸런스 분석

## Current Baseline

기준 main: `393a8589adc33b3098028f9a33aab793a5fec38d`. 최초 수치 동결 측정 후 후보를 비교했다. `scripts/phase7c_balance.py`는 실제 정의와 `rules.player_attack/enemy_attack`, Defense V1, 성장 예산, 장비 modifier, recovery, Boss HP와 reward allocation을 재사용한다. DB에 접근하지 않는다.

재현 명령(저장소 루트):

```powershell
.\.venv\Scripts\python.exe scripts/phase7c_balance.py --candidate pre-tuning-ammo --output work/phase7c/balance-baseline.json
.\.venv\Scripts\python.exe scripts/phase7c_balance.py --candidate carbine-attack-plus-two --output work/phase7c/candidate-damage.json
.\.venv\Scripts\python.exe scripts/phase7c_balance.py --candidate sentinel-currency-plus-twelve --output work/phase7c/candidate-currency.json
.\.venv\Scripts\python.exe scripts/phase7c_balance.py --output work/phase7c/balance-final.json
```

각 조합은 seed 0~63을 사용한다. 짝수/홀수 seed에 player-first/enemy-first tick 순서를 적용하고 실제 2.5초 전투 기회·cooldown·자연회복을 계산한다. HP45% 아래에서 최대 붕대8개를 사용한다. 지원자는 HP70% 아래인 생존자 치료와 부족한 정신력의 호흡을 선택한다. 성공한 재장전은 전투 기회 하나를 소비하며 탄약은 표준 탄창 단위로 보충하고 발사한 round에 실제 구매 단가를 적용한다.

**범위:** scheduler/network 지연·이동·재장전 입력 시간·장비 획득 RNG·패배 칩 패널티는 simulation 밖이다. 실시간 흐름은 Quick/Full/fresh E2E로 별도 검증한다. 승률은 이 정책과 64개 seed의 관찰치이며 실제 모든 build의 승률을 보장하지 않는다. net은 성공 시 반복 gross EV에서 탄약·붕대 구매비를 뺀 값이며 시간 비용은 별도다. Boss unique·첫 임무 보고는 반복 farm EV에 포함하지 않는다.

## Representative Builds

Minimal은 Lv1 무배분·기본 Rank1이다. T1은 Lv4, T2는 Lv7이며 실제 특성/훈련 예산 내에서만 배분한다. 각 build의 stable ID·특성·Rank·stats·회복률은 evidence JSON에 저장된다. 총기와 melee는 같은 body/gloves/boots/neck 기준이며 권총은 1H 방패 조합도 비교한다. Field-only/발견품은 구매 총액에서 제외한다.

| Build | Lv | 장비 구매 합계 | HP / SP | ATK / DEF | HP·SP idle/분 |
| --- | ---: | ---: | --- | --- | --- |
| `minimal` | 1 | 0 | 60 / 40 | 9 / 1 | 3.00 / 6.00 |
| `t1_balanced` | 4 | 185 | 126 / 55 | 19 / 5 | 4.10 / 6.75 |
| `t1_2h` | 4 | 200 | 126 / 55 | 21 / 5 | 4.10 / 6.75 |
| `t1_shield` | 4 | 230 | 126 / 55 | 19 / 7 | 4.10 / 6.75 |
| `t1_firearm` | 4 | 330 | 126 / 55 | 23 / 5 | 4.10 / 6.75 |
| `t1_pistol` | 4 | 283 | 126 / 55 | 20 / 7 | 4.10 / 6.75 |
| `t1_support` | 4 | 240 | 126 / 71 | 17 / 4 | 5.10 / 7.55 |
| `t2_balanced` | 7 | 365 | 184 / 70 | 28 / 8 | 5.07 / 7.50 |
| `t2_2h` | 7 | 400 | 184 / 70 | 30 / 8 | 5.07 / 7.50 |
| `t2_shield` | 7 | 470 | 192 / 70 | 28 / 12 | 5.20 / 7.50 |
| `t2_firearm` | 7 | 500 | 184 / 70 | 31 / 8 | 5.07 / 7.50 |
| `t2_pistol` | 7 | 503 | 192 / 70 | 28 / 12 | 5.20 / 7.50 |
| `t2_support` | 7 | 405 | 168 / 102 | 26 / 7 | 5.80 / 10.10 |

T1 일반 조합: 절단마체테/개척창/접이식방패/경비카빈/정찰권총 + 강화방호조끼·충격흡수장갑·미끄럼방지탐사화·탐사인식표. T2는 대응하는 정글장도/파쇄창/합성방패/탐사카빈/전술권총 + 전술방호복·타격보조장갑·안정화전투화·탐사인식표를 사용한다. 지원 조합은 휴대분석기/응급주입기·응급/의무전술벨트·생존/정신안정모듈을 쓴다.

## Enemy Results

최종 수치. incoming은 방어 적용 후 누적 피해로 치료 이전의 총량이다. 방패 build를 보스 솔로 준비 기준으로 삼는다.

| Build / Enemy | 기회 | 초 | Incoming | SP 소모 | 붕대 | 승률 | net칩 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `minimal` / `scavenger` | 3 | 7.5 | 9.953 | 0 | 0 | 100.0% | 9.785 |
| `minimal` / `hunter` | 5.906 | 14.766 | 43.344 | 0 | 0 | 100.0% | 16.57 |
| `t1_balanced` / `scavenger` | 1 | 2.5 | 1.641 | 8 | 0 | 100.0% | 9.785 |
| `t1_balanced` / `hunter` | 2 | 5.0 | 10.047 | 8 | 0 | 100.0% | 16.57 |
| `t1_balanced` / `sentinel` | 4 | 10.0 | 27.969 | 16 | 0 | 100.0% | 26.905 |
| `t1_shield` / `alpha` | 16.047 | 40.117 | 247.875 | 38.625 | 7.984 | 100.0% | -29.844 |
| `t2_balanced` / `dartclaw` | 2 | 5.0 | 15 | 8 | 0 | 100.0% | 22.94 |
| `t2_balanced` / `shellback` | 4 | 10.0 | 27.969 | 16 | 0 | 100.0% | 34.59 |
| `t2_balanced` / `stalker` | 4 | 10.0 | 41.969 | 16 | 0 | 100.0% | 36.715 |
| `t2_shield` / `jungle_apex` | 14.391 | 35.977 | 199.016 | 39.875 | 4.906 | 100.0% | 8.938 |

## Economy / Firearm vs Melee

| Build / Enemy | Shots | 초 | Incoming | ammo cost | ammo/gross | net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `t1_balanced` / `sentinel` | 0 | 10.0 | 27.969 | 0 | 0.0% | 26.905 |
| `t1_2h` / `sentinel` | 0 | 8.203 | 22.125 | 0 | 0.0% | 26.905 |
| `t1_shield` / `sentinel` | 0 | 10.0 | 26.922 | 0 | 0.0% | 26.905 |
| `t1_firearm` / `sentinel` | 3.766 | 9.414 | 26.125 | 7.531 | 28.0% | 19.374 |
| `t1_pistol` / `sentinel` | 4 | 10.0 | 26.922 | 8 | 29.7% | 18.905 |
| `t2_firearm` / `shellback` | 5 | 12.5 | 36 | 10 | 28.9% | 24.59 |
| `t2_firearm` / `stalker` | 4 | 10.0 | 41.969 | 8 | 21.8% | 28.715 |
| `t2_pistol` / `stalker` | 5 | 12.5 | 48.094 | 10 | 27.2% | 26.715 |

2H는 일반 적 처치 기회에 이점이 있고 shield는 높은 누적 피해의 Boss에서 이점이 커진다. 카빈은 경비기에 melee 대비 시간·안전성 이점이 작으므로 높은 재보급 비용을 유지할 근거가 부족했다. 권총은 더 저렴한 진입가·1H 방패 병용이라는 역할을 유지한다. 사격의 실제 거리/조작 편의는 damage 공식에 추가 가산하지 않는다.

## Mental / Recovery

Minimal의 idle 완전 HP/SP 회복은 20분/6.67분이다. T1 일반 build는 HP30.73분/SP8.15분이고 지원 장비의 HP+1/분으로 HP24.71분이 된다. T2 지원자는 의무전술벨트 HP+1·정신안정모듈 SP+1을 적용해 HP28.97분/SP10.10분이다. 추가 최대 HP/SP는 저장량을 늘리지만 반드시 완전 회복 시간을 줄이지는 않는다.

경비기 T1 melee 강타는 SP16/전투, 사격은 SP12/전투, 지원자는 평균 SP5.625/전투다. SP55 기준 자연회복을 제외하면 각각 약3.4/4.6회다. SP 회복시간은 총 소모/rate의 보수적인 상한이며 실제 전투 중 SP 자연회복은 별도 적용된다. 지원 Lv7 포식자 솔로는 SP70, 30.078기회로 유한하며 무한 sustain을 전제로 하지 않는다. 본부 의무관/침대의 실제 무료 full 회복으로 일반 플레이의 비용을 줄일 수 있다. 이동시간과 회복 gear의 선택은 별도다.

## Loot EV

| Enemy | gross resale/정산 EV칩 |
| --- | ---: |
| `scavenger` | 9.785 |
| `hunter` | 16.57 |
| `sentinel` | 26.905 |
| `alpha` | 50 |
| `dartclaw` | 22.94 |
| `shellback` | 34.59 |
| `stalker` | 36.715 |
| `jungle_apex` | 58 |

Consumable/resource와 special의 독립 roll, special 최대1개, enemy firearm의 partial magazine resale, scrap 실제 정산가를 사용한다. 희귀 장비의 실제 획득을 매 kill마다 현금으로 지급한다고 가정하지 않는다. Currency-only income은 gross보다 작다. Boss 고유 보상은 최초 progression 가치다.

## Progression

| 구매 목표 | 비용 | 청소룡 gross 기준 kill | 경비기 gross 기준 kill | 추적룡 gross 기준 kill |
| --- | ---: | ---: | ---: | ---: |
| `t1_essential` | 100 | 11 | 4 | 3 |
| `t1_balanced` | 185 | 19 | 7 | 6 |
| `t2_balanced` | 365 | 38 | 14 | 10 |
| `t1_firearm_entry` | 355 | 37 | 14 | 10 |

위 표는 시작20칩·임무 보상·판매 대기·소모품 비용을 제외한 gross affordability다. 필수 T1 무기+body100칩은 시작20칩을 빼면 청소룡 기대9회(순수 currency라면10회), Lv1 관찰 TTK7.5초 기준 전투67.5초다. 이동/HP 회복은 더 길고 성장에 따라 TTK는 줄어든다. 전체 장비를 동시에 사야 한다는 뜻은 아니다. T1 balanced185칩은 선택적 glove/boots를 포함하며 T1 firearm 입문355칩은 package+spare+20발+body다(이전375칩).

T2 balanced365칩은 추적룡 gross10회에 해당한다. T2 핵심 무기+body230칩은 gross7회이며 기존 T1 resale을 사용하면 더 줄어든다. 새 한 부위60~165칩은 밀림 일반 적 gross 약2~8회다. T2 full set을 해금 직후 모두 지급하지 않는다. 탐사인식표·field-only module·Boss unique는 shop 구매 비용에 섞지 않는다. 고정 discovery와 희귀 drop(재생모듈3%, 전술연산모듈3%)의 가치/희소성을 별도로 유지한다.

## Bosses

| Boss / build | 초 | incoming | 붕대 | SP | shots | 승률 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `alpha` / balanced | 41.328 | 275.141 | 8 | 32.5 | 0 | 78.1% |
| `alpha` / 2h | 37.734 | 250.203 | 8 | 32 | 0 | 100.0% |
| `alpha` / shield | 40.117 | 247.875 | 7.984 | 38.625 | 0 | 100.0% |
| `alpha` / firearm | 42.5 | 281.172 | 8 | 32.812 | 8.641 | 64.1% |
| `alpha` / pistol | 45.039 | 278.219 | 8 | 38.062 | 9.562 | 53.1% |
| `alpha` / support | 52.5 | 384.922 | 8 | 50 | 0 | 0.0% |
| `jungle_apex` / balanced | 43.75 | 287.891 | 7.984 | 36 | 0 | 100.0% |
| `jungle_apex` / 2h | 42.461 | 280.859 | 7.984 | 35.875 | 0 | 100.0% |
| `jungle_apex` / shield | 35.977 | 199.016 | 4.906 | 39.875 | 0 | 100.0% |
| `jungle_apex` / firearm | 47.5 | 308.594 | 8 | 39 | 11 | 100.0% |
| `jungle_apex` / pistol | 50.781 | 288.734 | 8 | 46.5 | 12.156 | 100.0% |
| `jungle_apex` / support | 75.195 | 516.266 | 8 | 70 | 0 | 100.0% |

| Boss / 인원 | 초 | 총 incoming | 붕대 | SP | ammo칩 | gross | XP / currency 지분 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `alpha` / 2 | 20.664 | 127.172 | 1.609 | 48 | 0 | 50 | [65, 65] / [25, 25] |
| `alpha` / 3 | 19.375 | 119.531 | 1.406 | 71.5 | 14.062 | 50 | [44, 43, 43] / [17, 17, 16] |
| `alpha` / 4 | 21.445 | 133.578 | 1.078 | 89.5 | 16 | 50 | [33, 33, 32, 32] / [13, 13, 12, 12] |
| `jungle_apex` / 2 | 23.75 | 146.719 | 1.422 | 52 | 0 | 58 | [78, 77] / [29, 29] |
| `jungle_apex` / 3 | 22.617 | 141.562 | 1.469 | 76.5 | 17.375 | 58 | [52, 52, 51] / [20, 19, 19] |
| `jungle_apex` / 4 | 24.922 | 155.281 | 0.562 | 107.5 | 18 | 58 | [39, 39, 39, 38] / [15, 15, 14, 14] |

대표 party는 shield→2H→firearm→support 순서로 구성한다. 위협 기준으로 피해가 집중되므로 균등 피해로 해석하지 않는다. HP 잔여량 배열은 JSON에 있고 보상 총량은 모든 구성에서 보존한다. 1.00/1.75/2.50/3.25 scaling을 유지한다. 솔로는 회복 준비 부담이 크며 party는 kill 시간을 줄이고 부담을 분산하지만 보상은 나누어 받는다.

능선 Lv4 방패·2H 준비 build는64/64 성공, balanced는50/64, firearm은41/64, 지원은0/64다. 지원자는 일반 사냥64/64이나 최소 권장 level의 보스 전담 솔로에는 공격 투자/무료 재훈련/추가 성장이 필요하다. 밀림 Lv7 모든 측정 build는64/64 성공이다. Boss 반복 farm net이 음수인 구성도 있지만 최초 보고의 추가 칩·XP·붕대·Credential·unique progression 보상과 혼동하지 않는다. 모든 archetype의 최소 level 보스 무소모품 승리를 목표로 추가 tuning하지 않는다.

## Known Issues / Candidate Changes / Chosen Changes

Observed: 이전 기본 공격 sanity는4발×3칩=12칩, gross26.905 대비44.6%였다. 합법적 Lv4 build와 사격/cooldown을 포함한 이번 baseline은3.766발×3칩=11.297칩,42.0%다. Target: 같은 전투 부담에서 대략15~30%의 재보급 비중.

| 후보 | 경비카빈 ammo/gross | 영향 / 판단 |
| --- | ---: | --- |
| 5.56mm 구매3→2칩 | 28.0% | 선택. 전투·resale EV·다른 currency를 그대로 유지 |
| 카빈 attack8→10 | 33.5% | 거절. T1/T2 attack 차이를 줄이고 목표 미달 |
| 경비기 currency20→32 | 29.0% | 거절. 모든 style 수익 증가, gross38.905로 밀림 추적룡보다 높아짐 |
| Ammo drop 증가 | 미선택 | 현재 loose ammo roll resale EV는0.525칩뿐. 목표 개선에는 큰 공급량 변화가 필요 |
| Boss/Defense/recovery/gear 수치 변경 | NO CHANGE | 솔로 준비·role trade-off 확인, 해당 문제와 직접 관련 없음 |

Chosen: 5.56mm **purchase unit만3→2칩**, 20발 bundle60→40칩. Resale1칩, magazine 가격, body 가격, package200/245칩은 유지한다. 가격 변경은 world/content/items.py의 authoritative metadata 한 곳이다.

## Post-Tuning Results / Rejected Alternatives

경비기 사격 TTK9.414초·incoming26.125·shots3.766은 전후 동일하다. Ammo11.297→7.531칩, net15.608→19.374칩, ratio42.0→28.0%. 기본4발 sanity도44.6→29.7%다. 9mm/7.62mm 구매·판매가와 melee 결과·drop EV는 변경하지 않는다. T2 카빈도 동일한 단가 개선을 받으며 권총은1H 방패 선택권과 낮은 초기 package 가격을 유지한다.

| Package | 구매 | 분해 resale 합계 | 구매−body/mag resale | 포함 ammo 직접 구매 |
| --- | ---: | ---: | ---: | ---: |
| `scout_pistol` | 108 | 54 | 66 | 24 |
| `guard_carbine` | 200 | 89 | 131 | 40 |
| `tactical_pistol` | 143 | 71 | 84 | 24 |
| `exploration_carbine` | 245 | 112 | 153 | 40 |
| `heavy_rifle` | 257 | 128 | 145 | 32 |

모든 package에서 구매>전체 분해 resale, 구매−body/mag resale≥포함 탄약 직접 구매를 유지한다. Carbine body+standard mag+ammo component 구매 합180/225칩보다 package는20칩 높아진다. V1 shop은 body-only 구매를 제공하지 않고 package 가격을 함께 낮추어 초기 진입/상대 가격을 흔드는 추가 변경은 선택하지 않았다.

실행 검증·실패 이력·최종 판단은 [playtest](playtest.md), [fresh 검증](phase7c-fresh-operational-validation.md), [Phase7 audit](phase7-final-integration-audit.md)를 따른다. PostgreSQL·multi-server·legacy 정리는 별도 후속 작업이다.
