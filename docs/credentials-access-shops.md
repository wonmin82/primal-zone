# 출입증·접근·상점·소각

Phase 6 현재 상태: cutover 후 일반 gameplay는 native ItemEntity만 사용한다. 아래 legacy adapter/Phase 6 예정 설명은 Phase 1~5의 설계·검증 기록이며 maintenance migration과 historical audit fixture의 호환 경계로 남는다. 최신 저장·운영 정책은 [item-migration](item-migration.md), 최종 콘텐츠·가격은 [final-content](final-content.md)를 따른다.

## 출입증과 임무

`outpost_supply_pass`(전초 보급구역 출입증)과 `special_supply_pass`(특수 보급구역 출입증)은 backend와 무관하게 실제 ItemEntity만 authoritative하다. profile inventory에는 저장하지 않는다. non-stack/quantity1/max_stack1/unique_per_owner이며 `unique_scope_key` DB uniqueness를 그대로 사용한다. 알려진 operation 중 burn만 허용하고 unknown은 fail-closed다.

`credential_service.credential_items()`/`has_credential()`은 owner의 전체 tree scope를 읽는다. 숨겨진 personal_storage/inside 위치도 중복 발급을 숨기지 못한다. `grant_credential()`은 owner → 모든 owned UUID lock 후 기존 row를 반환하거나 하나만 만든다. `reissue_credential()`은 claimed entitlement를 확인한다. 정상 소지품 표시는 inventory 출입증만 표시한다. 정상 runtime의 일반 소지품과 출입증은 모두 native Entity snapshot을 사용한다. Phase 5 당시 legacy의 additive 표시는 출입증에 한정했다.

`issuer_talk()`은 기존 pure `rules.commander_talk()`/`jungle_talk()`, XP·credits·붕대·claimed, 출입증 생성, profile 저장을 하나의 world_change에 묶는다. native의 새 붕대 보상은 Entity에만 저장하고 archive inventory를 변경하지 않는다. 첫 final report는 출입증과 Boss unique를 실제 신규 지급한 경우에만 함께 안내한다. 통신탑은 윤대장에게 outpost pass, 깊은 밀림은 선발대 길잡이에게 special pass를 받는다. claimed + 출입증 없음이면 해당 원래 issuer가 출입증만 무료 재발급한다. XP/credits/기존 물품/quest는 반복 지급하지 않는다. startup 자동 발급이나 entitlement cache는 없다.

## 공간 접근과 이동 경로

`world.access.can_enter(character, destination)`은 read-only다. 단일 판정 helper `entry_message()`가 available → 실제 출입증 → 기존 requires quest/flag 순으로 검사한다. availability=false인 시설은 출입증이 있어도 닫혀 있으며 특수 출입증 보유자에게 `출입 권한은 확인되지만 시설은 아직 폐쇄되어 있다.`를 표시한다. quest claimed 자체나 파티원/리더의 출입증은 접근권이 아니다. 제한은 목적지 진입에만 적용해 제한실에서 일반 복도로 나가는 것은 허용한다.

| 실제 경로 | 공통 접근 연결 | 범위 |
| --- | --- | --- |
| 방향 Exit.at_traverse | blocked_exits → can_enter → traverse | Web 방향 버튼도 동일 서버 명령 |
| Explorer.at_pre_move / move_to | can_enter, 기존 combat/회복/visited 경계 | 직접 gameplay destination 이동도 검사 |
| elevator.board/disembark | player.move_to → at_pre_move | 승강기·현재 선택한 층 이동 |
| 귀환 | move_to(support_roof) → at_pre_move | 기존 public 옥상 의미 유지 |
| defeat | Enemy.receive_attack의 move_to(infirmary, move_type=defeat) | 기존 public 강제 복귀 의미 유지 |
| 도망 | 교전 해제, 공간 이동 없음 | 별도 destination/access 경로 없음 |
| party | 각 Explorer의 이동 | collective party movement 기능 없음, 개인별 검사 |
| 로그인/재로그인 | 시스템 location=staging_room | public 배치, 사용자 접근 판정 추가 없음 |
| bootstrap/admin/cache rollback | 내부 공간 배치/복구 | 사용자 credential 검사 강제 없음 |

기존 ridge 등 `requires`의 message/observe_message와 Exit 관찰 조건은 유지한다. 실제 gameplay 자동 teleport는 귀환 외에 별도로 없다. 일반 move_to의 move_hooks=False를 사용하는 관리자/시스템 relocation은 사용자 명령 경로가 아니다.

## 본부 공간과 bootstrap

stable 기본 room ID는 supply_shop/armor_shop/weapon_shop을 유지한다. 표시명은 1F 보급품 상점/3F 서쪽 기본 장비점/3F 동쪽 기본 병기점이다.

| 복도 | 북 | 남 |
| --- | --- | --- |
| support_3f_w2 | outpost_equipment, 전초 장비고 | reserved_equipment, 다음 단계 장비고 |
| support_3f_e2 | outpost_weapon, 전초 병기고 | reserved_weapon, 다음 단계 병기고 |

북쪽 두 방은 outpost pass + available=true, 남쪽 두 방은 special pass + available=false다. 예약 시설도 실제 관리 Exit/destination을 가진다. 실제 상인은 북쪽 두 방에만 배치한다. 자원 정산소에는 폐기물 소각기(alias 소각기)를 배치한다. 기존 build_world의 managed tag를 재사용하며 반복 실행은 방·출구·상인·소각기를 중복 생성하지 않는다. 플레이 월드의 build_world를 이번 개발에서 실행하지 않고 격리 테스트에서 확인한다.

## Shop V2와 source/sink

`SHOP_CATALOGS`는 모든 shop에 `purchase_catalog`와 `accepts`를 둔다. 구매는 명시적 ID 목록, 매입은 item_type category다. 기본 병기점은 weapon/magazine/ammo, 기본 장비점은 armor/equipment, 보급품 상점은 tool/consumable을 매입한다. field-found advanced gear도 category와 operation/가격이 맞으면 기본점에서 판매·가치 확인이 가능하다. 상품별 quest/credential 검사는 없다. progression은 공간 접근에서 결정한다.

현재 supply는 소모품/손전등/건전지, 기본 병기점은 T1 무기·방패·offhand·탄창·탄약, 기본 장비점은 T1 착용 장비, 전초 병기고/장비고는 T2와 확장 탄약을 취급한다. 전체 catalog/최종 가격은 [final-content](final-content.md)를 따른다.

`shop_service`가 보임·same-room·safe·noncombat을 검증한다. Native credits와 ItemEntity create/destroy는 같은 world_change에서 처리한다. Firearm은 full_standard package로 구매하며 Shopkeeper는 재고 owner가 아닌 source/sink다. 실패하면 tree·credits·sequence·active refs를 rollback한다. 탄약은 unit value×purchase_quantity, magazine은 empty resale+rounds×ammo resale을 사용한다. Loaded firearm은 탄창 분리 전 sell/burn을 거절한다.

`shop_snapshot()`의 구매 후보는 catalog만, 판매 후보는 소지 snapshot/accepts/policy/가격을 사용한다. Shopkeeper.web_actions는 동일 실제 서버 명령을 만든다. UUID나 global sequence를 노출하지 않고 동일 native non-stack instance를 sequence 기반 local selector로 구분한다. 현재 모두 판매는 스택에만 허용하며 장착 item은 inventory 판매 후보가 아니다. Legacy count 예약은 historical adapter용이다.

## 수량과 소각

`stack_quantity.parse_stack_quantity()`는 기본1, N개, 모두(None)를 분리한다. 숫자만 붙은 selector 번호와 9mm/5.56mm 이름의 숫자는 수량으로 해석하지 않는다. 정산의 parse_salvage도 이 helper를 사용하되 기존 회수부품 전용 선택/문법은 유지한다.

`incinerator_service.incinerate()`는 실제 같은 방에서 보이는 Incinerator를 요구한다. 일반 물품과 출입증은 Entity에서만 제거한다. Legacy profile 제거는 historical fixture 경계다. `api.destroy_quantity(operation="sell"|"burn")`은 owner/reference hook → 정렬 UUID lock → policy/수량 검사 → save/delete → reference reconcile을 따른다. 부분 폐기에서는 source UUID/sequence/state를 유지하고 임시 Entity/sequence를 만들지 않는다. 기존 split/merge/claimed loot 계약은 변경하지 않는다.

잔탄 탄창 소각은 row와 rounds를 함께 없애며 loose ammo/credits를 반환하지 않는다. loaded firearm은 소각할 수 없다. 출입증은 첫 `<selector> 소각`에서 폐기 mutation 없이 `<selector> 소각 확정`을 안내하며 두 단어 명령 alias를 공통 후치 parser로 인식한다. Burn은 정확한 alias일 때만 `incinerate(..., confirmed=True)`를 전달하고 서비스는 item 문자열 끝의 확정을 승인으로 해석하지 않는다. `<selector> 확정 소각` 등 잘못된 순서는 삭제하지 않는다. 정확한 명령 자체가 확인이며 pending Attribute/timer/token/session state를 만들지 않는다. 첫 명령의 일반 command recovery reconciliation은 기존대로다. 소각 후 quest/XP/credits는 유지하고 다음 DB 기반 접근 검사가 즉시 거절한다. 원래 issuer에게 `재발급 말`로 명시적으로 요청하면 출입증만 재발급한다. `임무`·`진행`·`출입증` 질문은 읽기 전용이며 [NPC 대화 서비스](npc-dialogue.md)가 수락·보고·재발급의 최종 조건을 검사한다.

출입증은 stack 수량 문법을 사용하지 않는다. 서비스가 raw selector를 기존 parse_selector/matching/select로 먼저 해석하며 stable ID·표시명·alias·정상 local index만 허용한다. `<출입증> 소각`은 안내, `<출입증> 소각 확정`은 삭제이며 `<출입증> 1개 소각 확정`, `<출입증> 2개 소각 확정`, `<출입증> 모두 소각 확정`은 전부 거절한다. confirmed 경로는 수량 parser로 fallback하지 않으며 서비스 직접 호출에도 같은 계약을 적용한다. 일반 물품만 parse_stack_quantity를 사용해 1/N개/모두와 숫자를 포함한 탄약 이름을 그대로 처리한다. 일반 물품의 소각 확정은 거절한다.

## 현재 검증·운영 경계

최종 가격·catalog·ammo/magazine production 거래 및 full-world migration이 구현되어 있다. 기존 DB는 explicit maintenance migration 후 runtime을 시작하고 fresh DB는 native로 직접 시작한다. Legacy blob은 보존할 수 있으나 일반 gameplay read/write/fallback/dual-write 대상이 아니다. [설치](installation.md), [migration](item-migration.md), [Phase 7 audit](phase7-final-integration-audit.md)을 따른다.

## Historical Phase 5 implementation boundary

아래 catalog와 가격·변환 미적용 설명은 Phase 5 당시의 범위다. 당시 검증 이력은 수정하지 않는다.

| shop | purchase_catalog |
| --- | --- |
| supply | flashlight, battery, bandage, field_ration, water |
| weapon | blade, spear, carbine |
| armor | leather_suit, armor |
| outpost_weapon | jungle_blade, heavy_carbine |
| outpost_equipment | tactical_vest, heavy_suit |

`shop_service`가 보임·same-room·safe·noncombat 검증과 backend 분기를 소유한다. legacy는 rules.buy/sell과 profile만 변경한다. native는 credits와 ItemEntity create/destroy를 같은 world_change에 묶는다. native firearm 구매는 기존 create_firearm(mode="full_standard")으로 표준 full 탄창을 삽입한다. Shopkeeper는 Entity 재고 owner가 아니며 구매는 source, 판매는 sink다. create/profile save/delete 실패 시 rows/tree/credits/sequence/active refs가 함께 rollback된다.

가격은 기존 value를 유지한다. 향후 구조화된 purchase_unit_value/resale_unit_value도 읽을 수 있지만 이번 Phase에서 최종 가격을 추가하지 않는다. 가격 metadata가 없는 production 탄창/탄약의 매매는 거절한다. `resale()`은 정의된 empty 매입가 + rounds × ammo 매입 단가를 기존 `firearms.magazine_resale()`로 계산한다. 실제 거래는 controlled fixture 가격으로 검증한다. 잔탄 판매 결과에는 잔탄 가치 포함을 표시한다. loaded firearm은 기존 structural policy로 판매를 거절하고 먼저 탄창을 분리해야 한다.


### Phase 6 경계와 검증 (당시 기록)

profile version10과 기존 inventory/equipment/storage/light_sources, Container items, legacy loot blob은 유지한다. ordinary runtime backend를 자동 전환하지 않고 출입증만 backend-independent Entity SSOT로 추가한다. dual-write/lazy conversion/full-world migration/schema migration은 없다. Phase 6은 최종 콘텐츠/가격 확장, 기존 claimed entitlement의 명시적 출입증 migration, 전체 legacy→Entity migration/integrity/cutover를 수행한다.

실제 실행 명령·성공/실패와 최신 CI는 [playtest](playtest.md)의 Phase 5 기록을 따른다. PostgreSQL 실제 경쟁·multi-server·OS IME·전체 browser/multiplayer matrix·full suite 로컬·smoke-full·full migration·balance simulation은 이번 단계에서 실행하지 않는다. schema를 바꾸지 않았으므로 신규 Django migration도 없다.
