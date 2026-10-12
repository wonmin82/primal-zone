const { test: base, expect, sessions } = require('./fixtures.cjs');
const { snapshot, command, travel, itemCount, party, restart, control } = require('./integration-helpers.cjs');
const { pollUntil } = require('./safety.cjs');
// 신규 인증은 정책상 출정 대기실로 이동한다. fixture 방에 teleport하지 않고
// 실제 Exit 명령으로 각 시나리오의 장소에 도착한다.
const starts = { 'E2E-02': 'dock', 'E2E-03': 'weapon_shop', 'E2E-04': 'infirmary',
  'E2E-05': 'dock', 'E2E-06': 'grass', 'E2E-07': 'dock', 'E2E-08': 'hq_lounge',
  'E2E-09': 'hq_concourse', 'E2E-10': 'hq_concourse', 'E2E-11': 'dock', 'E2E-12': 'hq_lounge',
  'E2E-13': 'dock', 'TIMING-DOOR': 'hq_lounge', 'TIMING-PARTY': 'dock' };
const test = base.extend({ actors: async ({ actors }, use) => {
  await use({ ...actors, create: async (index, viewport) => {
    const player = await actors.create(index, viewport);
    const target = starts[process.env.PRIMAL_BROWSER_SCENARIO];
    if (target) await travel(player, target);
    return player;
  } });
} });

test('TEST-E2E-01 명령·Alias·Help·개인 변수 줄임말', async ({ actors }) => {
  const a = await actors.create(0);
  await command(a, '상', '체력');
  for (const suffix of ['도움', '도움말']) await command(a, '준말 ' + suffix, '1,000');
  await command(a, '정찰 $1 봐 줄임말', '추가');
  await command(a, '남 정찰', '본부 중앙 로비');
  await command(a, '조회 점수, 장비 해 줄임말', '추가');
  await command(a, '조회', '장비');
  expect(snapshot().players[a.name].profile.command_shortcuts['조회']).toBe('점수, 장비 해');
  const profile = snapshot().players[a.name].profile;
  await travel(a, 'training_room');
  for (const npc of ['전투교관', '근력교관']) await command(a, npc + '에게 훈련 말', '서비스 명령');
  await command(a, '강타 배워', '남은 기술 훈련');
  await travel(a, 'training_office');
  await command(a, '훈련관리관에게 훈련 말', '서비스 명령');
  const after = snapshot().players[a.name].profile;
  for (const field of ['xp', 'credits', 'skills']) expect(after[field]).toEqual(profile[field]);
  expect(a.errors).toEqual([]);
});

test('TEST-E2E-02 실제 NPC 임무·수리·보고·출입증 재발급', async ({ actors }) => {
  const a = await actors.create(0);
  await command(a, '윤대장에게 임무 말');
  const prompts = a.prompts;
  const accept = a.page.getByRole('button', { name: /NPC 행동 실행:.*수락/ }).last();
  await accept.focus(); await accept.press('Enter');
  await expect.poll(() => a.prompts).toBeGreaterThan(prompts);
  expect(snapshot().players[a.name].profile.quests.radio_tower.started).toBe(true);
  await travel(a, 'office');
  await command(a, '정비기록 조사');
  await travel(a, 'generator');
  await command(a, '발전기 수리');
  expect(snapshot().players[a.name].profile.quests.radio_tower.generator_fixed).toBe(true);
  await travel(a, 'dock');
  const before = snapshot().players[a.name].profile;
  await command(a, '윤대장에게 진행 말');
  const reportPrompts = a.prompts;
  await a.page.getByRole('button', { name: /NPC 행동 실행:.*보고/ }).last().click();
  await expect.poll(() => a.prompts).toBeGreaterThan(reportPrompts);
  const after = snapshot().players[a.name].profile;
  expect(after.quests.radio_tower.claimed).toBe(true);
  expect(after.credits - before.credits).toBe(100);
  expect(after.xp - before.xp).toBe(100);
  await command(a, '윤대장에게 보고 말');
  expect(snapshot().players[a.name].profile.credits).toBe(after.credits);
  await command(a, '윤대장에게 출입증 말');
  const b = await actors.create(1), lost = snapshot();
  await command(b, '윤대장에게 재발급 말');
  const reissued = snapshot();
  expect(itemCount(reissued, b.name, 'outpost_supply_pass')).toBe(1);
  expect(reissued.players[b.name].profile.credits).toBe(lost.players[b.name].profile.credits);
  await command(b, '윤대장에게 재발급 말');
  expect(snapshot().items).toEqual(reissued.items);
  await travel(b, 'jungle_edge');
  await command(b, '선발대 길잡이에게 임무 말');
  await command(b, '선발대 길잡이에게 수락 말');
  expect(snapshot().players[b.name].profile.quests.deep_jungle.started).toBe(true);
  expect(a.errors).toEqual([]);
});

test('TEST-E2E-03 상점 구매·정보 읽기·장착·해제·판매', async ({ actors }) => {
  const a = await actors.create(0), initial = snapshot();
  await command(a, '절단마체테 사');
  const bought = snapshot();
  expect(itemCount(bought, a.name, 'cutting_machete')).toBe(itemCount(initial, a.name, 'cutting_machete') + 1);
  expect(bought.players[a.name].profile.credits).toBe(initial.players[a.name].profile.credits - 55);
  await command(a, '절단마체테 정보', '기준 구매가');
  expect(snapshot().items).toEqual(bought.items);
  await command(a, '절단마체테 무장');
  expect(snapshot().items.some(i => i.owner_object_id === initial.players[a.name].id && i.location_kind === 'equipment' && i.slot === 'hands')).toBe(true);
  await command(a, '절단마체테 해제');
  await command(a, '절단마체테 팔아');
  const sold = snapshot();
  expect(itemCount(sold, a.name, 'cutting_machete')).toBe(itemCount(initial, a.name, 'cutting_machete'));
  expect(sold.players[a.name].profile.credits).toBe(initial.players[a.name].profile.credits - 28);
  await travel(a, 'salvage_office');
  await command(a, '정산관에게 정산 말', '10칩');
  await command(a, '정산관에게 회수부품 1개 교환');
  const exchanged = snapshot();
  expect(exchanged.players[a.name].profile.credits).toBe(sold.players[a.name].profile.credits + 10);
  expect(itemCount(exchanged, a.name, 'scrap')).toBe(itemCount(sold, a.name, 'scrap') - 1);
});

test('TEST-E2E-04 유료 회복·회복실 Door·무료 침대', async ({ actors }) => {
  const a = await actors.create(0);
  const before = snapshot().players[a.name].profile;
  await command(a, '20 회복');
  const after = snapshot().players[a.name].profile;
  const hp = after.hp - before.hp;
  expect(hp).toBeGreaterThan(0);
  expect(before.credits - after.credits).toBe(Math.max(1, Math.ceil((2 * hp + 1) / 10)));
  await travel(a, 'support_3f_e1');
  await command(a, '회복실 문 닫아');
  await command(a, '북');
  expect(snapshot().players[a.name].zone).toBe('support_3f_e1');
  await command(a, '회복실 문 열어');
  await a.command('북', { prepare: async () => {},
    submit: () => a.page.locator('#exits [data-command="북"]').click() });
  await expect.poll(() => a.state.zone).toBe('recovery_room');
  const credits = snapshot().players[a.name].profile.credits;
  await command(a, '침대 휴식');
  await expect.poll(() => a.state.mental).toBe(a.state.max_mental);
  expect(snapshot().players[a.name].profile.credits).toBe(credits);
});

test('TEST-E2E-05 개인·차단·일행 가입·제삼자 비공개', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1), c = await actors.create(2);
  const text = '합성비공개검증';
  await command(a, b.name + ' ' + text + ' 대화');
  await expect(b.page.locator('#log')).toContainText(text);
  expect(await c.page.locator('#log').textContent()).not.toContain(text);
  await command(b, a.name + ' 대화거부');
  await command(a, b.name + ' 차단본문 대화', '차단');
  expect(await b.page.locator('#log').textContent()).not.toContain('차단본문');
  await party(a, b);
  await travel(b, 'hq_concourse');
  await command(a, '합성원격일행 일행대화');
  await expect(b.page.locator('#log')).toContainText('합성원격일행');
  expect(await c.page.locator('#log').textContent()).not.toContain('합성원격일행');
});

test('TEST-E2E-06 일행 실제 전투·XP·Native 전리품·중복 방지', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  await party(a, b);
  const before = snapshot();
  await command(a, b.name + ' 일행방어');
  await command(a, '어린청소룡 일행공격');
  await expect.poll(() => a.state.combat_target, { timeout: 60000 }).toBeNull();
  await expect.poll(() => b.state.combat_target, { timeout: 60000 }).toBeNull();
  const dead = snapshot();
  for (const p of [a, b]) expect(dead.players[p.name].profile.xp).toBeGreaterThan(before.players[p.name].profile.xp);
  await command(a, '시체에서 모두 가져');
  await command(b, '시체에서 모두 가져');
  const after = snapshot();
  await command(a, '시체에서 모두 가져');
  expect(snapshot().players[a.name].profile.credits).toBe(after.players[a.name].profile.credits);
  expect(snapshot().items).toEqual(after.items);
  expect(a.errors.concat(b.errors)).toEqual([]);
});

test('TEST-E2E-07 실제 해체 뒤 Native/Legacy 개인 권리·지급', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1), c = await actors.create(2);
  const before = snapshot();
  await command(a, '일행해체');
  await command(a, '확인 일행해체');
  expect(Object.keys(snapshot().parties)).toHaveLength(0);
  await command(c, '모든 시체에서 모두 가져');
  expect(snapshot().items).toEqual(before.items);
  await command(a, '모든 시체에서 모두 가져');
  await command(b, '모든 시체에서 모두 가져');
  const after = snapshot();
  expect(itemCount(after, a.name, 'bandage')).toBe(itemCount(before, a.name, 'bandage') + 2);
  expect(after.players[b.name].profile.inventory.water || 0).toBe((before.players[b.name].profile.inventory.water || 0) + 1);
  expect(after.claims).toHaveLength(0);
  expect(b.errors).toEqual([]);
});

async function adminDoor(a, b) {
  await command(a, '관리실 열쇠함 조사');
  await travel(a, 'hq_concourse');
  await command(a, '관리실 문 풀어');
  await command(a, '관리실 문 열어');
  await travel(b, 'hq_admin_office');
}
test('TEST-E2E-08 두 방향 조작·통과·상태·오래된 요청 거절', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  await adminDoor(a, b);
  const endpoints = snapshot().doors.find(d => d.door_id === 'hq_admin_door');
  await Promise.all([command(a, '동 문 닫아'), command(b, '서 문 닫아')]);
  await expect.poll(() => snapshot().doors.find(d => d.door_id === 'hq_admin_door').state).toBe('CLOSED');
  await expect.poll(() => a.state.exit_details.find(e => e.name === '동')?.can_move).toBe(false);
  await command(a, '동');
  expect(snapshot().players[a.name].zone).toBe('hq_concourse');
  await command(b, '서 문 열어');
  await command(a, '동');
  await expect.poll(() => a.state.zone).toBe('hq_admin_office');
  const final = snapshot().doors.find(d => d.door_id === 'hq_admin_door');
  expect(final.exit_a_id).toBe(endpoints.exit_a_id); expect(final.exit_b_id).toBe(endpoints.exit_b_id);
  expect(final.auto_close_at).toBeGreaterThan(endpoints.auto_close_at);
});

test('TEST-E2E-09 이동하는 개인 묶음·현재 CmdSet·잠긴 Exit', async ({ actors }) => {
  const a = await actors.create(0);
  await command(a, '이동검증 남, 북, 동, 점수 해 줄임말');
  await command(a, '이동검증', '체력');
  expect(snapshot().players[a.name].zone).toBe('hq_concourse');
  expect(snapshot().doors.find(d => d.door_id === 'hq_admin_door').state).toBe('LOCKED');
});

test('TEST-E2E-10 실제 교전에서 Door·NPC·회복 거부', async ({ actors }) => {
  const a = await actors.create(0);
  await command(a, '검증사냥룡 때려');
  await expect.poll(() => a.state.combat_target).toBeTruthy();
  const db = snapshot(), credits = db.players[a.name].profile.credits;
  expect(db.players[a.name].profile.combat_target).toBeTruthy();
  await command(a, '관리실 문 열어', '전투');
  await command(a, '검증대장에게 수락 말', '비전투');
  await command(a, '20 회복', '전투');
  const after = snapshot();
  expect(after.players[a.name].profile.credits).toBe(credits);
  expect(after.players[a.name].profile.quests).toEqual(db.players[a.name].profile.quests);
  expect(after.players[a.name].profile.combat_target).toBeTruthy();
  expect(after.doors.find(d => d.door_id === 'hq_admin_door')).toEqual(db.doors.find(d => d.door_id === 'hq_admin_door'));
  await command(a, '도망');
});

test('TEST-E2E-11 마지막 Puppet 해제·즉시 승계·재접속', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  const id = await party(a, b);
  await command(a, b.name + ' 일행방어');
  await actors.close(a);
  expect(sessions()[a.name]).toEqual([]);
  const offline = snapshot().parties[id];
  await control('party-before');
  expect(snapshot().parties[id].leader).toBe(offline.leader);
  await control('party-at');
  const state = snapshot().parties[id];
  expect(state.leader).toBe(snapshot().players[b.name].id);
  const reconnected = await actors.create(0);
  await command(reconnected, '일행');
  expect(snapshot().parties[id].leader).toBe(state.leader);
  expect(snapshot().parties[id].tactics).toEqual(state.tactics);
  await command(b, reconnected.name + ' 일행리더');
  await actors.close(reconnected);
  await command(b, '일행승계');
  expect(snapshot().parties[id].leader).toBe(state.leader);
});

test('TEST-E2E-12 정상 Portal/Server 재시작·같은 DB·재인증', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  await party(a, b); await command(a, b.name + ' 일행방어');
  await command(a, '영속조회 점수 줄임말'); await command(a, '관리실 열쇠함 조사');
  await travel(a, 'hq_concourse');
  await command(a, '관리실 문 풀어'); await command(a, '관리실 문 열어');
  await actors.close(a); await actors.close(b);
  const before = snapshot();
  await restart();
  const stopped = snapshot();
  expect(stopped.items).toEqual(before.items);
  expect(stopped.doors).toHaveLength(before.doors.length);
  // 정상 재시작의 만료 sweep은 허용한다. PK/권한/비만료 예약의 리셋은 거절한다.
  for (const saved of before.doors) {
    const current = stopped.doors.find(d => d.door_id === saved.door_id);
    if (saved.state === 'OPEN' && current.state === 'CLOSED') {
      expect(saved.auto_close_at).toBeLessThanOrEqual(Date.now() / 1000);
      expect(current).toEqual({ ...saved, state: 'CLOSED', auto_close_at: null });
    } else {
      // 만료 직후에는 sweep이 최대 한 tick 늦을 수 있다. 저장 OPEN/원래 예약을
      // 보존해도 정상이며 논리적 차단은 Door 경계 테스트가 별도로 확인한다.
      expect(current).toEqual(saved);
    }
  }
  expect(stopped.installations).toEqual(before.installations);
  expect(stopped.claims).toEqual(before.claims); expect(stopped.currency).toEqual(before.currency); expect(stopped.shares).toEqual(before.shares);
  expect(stopped.legacy_loot).toEqual(before.legacy_loot);
  for (const name of [a.name, b.name]) {
    for (const field of ['command_shortcuts', 'quests', 'credits', 'xp']) expect(stopped.players[name].profile[field]).toEqual(before.players[name].profile[field]);
    expect(stopped.players[name].id).toBe(before.players[name].id);
    expect(stopped.players[name].zone).toBe(before.players[name].zone);
    expect(stopped.players[name].prelogout_zone).toBe(before.players[name].prelogout_zone);
  }
  for (const id of Object.keys(before.parties)) {
    for (const field of ['leader', 'members', 'tactics', 'leader_offline_since']) expect(stopped.parties[id][field]).toEqual(before.parties[id][field]);
  }
  const again = await actors.create(0), member = await actors.create(1);
  await command(again, '영속조회', '체력');
  expect(again.state.party.id).toBe(member.state.party.id);
  expect(snapshot().parties[again.state.party.id].tactics).toEqual(before.parties[again.state.party.id].tactics);
});

test('TEST-E2E-13 실제 Native/Legacy 지급 뒤 상위 Rollback·성공 알림 없음', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1), before = snapshot();
  await command(a, '모든 시체에서 모두 가져', '상위 변경 롤백');
  await command(b, '모든 시체에서 모두 가져', '상위 변경 롤백');
  const after = snapshot();
  expect(after.items).toEqual(before.items); expect(after.claims).toEqual(before.claims);
  expect(after.currency).toEqual(before.currency); expect(after.shares).toEqual(before.shares); expect(after.legacy_loot).toEqual(before.legacy_loot);
  expect(after.players[a.name].profile.inventory).toEqual(before.players[a.name].profile.inventory);
  expect(after.players[b.name].profile.inventory).toEqual(before.players[b.name].profile.inventory);
  expect(after.players[a.name].profile.credits).toBe(before.players[a.name].profile.credits);
  expect(after.players[b.name].profile.credits).toBe(before.players[b.name].profile.credits);
  expect(await a.page.locator('#log').textContent()).not.toMatch(/챙겼다|회수했다/);
  expect(await b.page.locator('#log').textContent()).not.toMatch(/챙겼다|회수했다/);
});

test('TEST-E2E-14 연속 입력·History·Backspace·HTML·Focus·두 화면', async ({ actors }) => {
  for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
    const a = await actors.create(0, viewport);
    await command(a, '점수'); await command(a, '봐');
    const input = a.page.locator('#command');
    await input.press('ArrowUp'); await expect(input).toHaveValue('봐');
    await input.press('ArrowDown'); await input.fill('점수x'); await input.press('Backspace');
    await expect(input).toHaveValue('점수');
    await a.context.grantPermissions(['clipboard-read', 'clipboard-write']);
    const priorClipboard = await a.page.evaluate(() => navigator.clipboard.readText());
    try {
      await a.command('점수', { prepare: async field => {
        await field.fill(''); await field.focus();
        await a.page.evaluate(() => navigator.clipboard.writeText('점수'));
        await field.press('Control+V'); await expect(field).toHaveValue('점수');
      } });
    } finally {
      await a.page.evaluate(async previous => {
        if (await navigator.clipboard.readText() === '점수') await navigator.clipboard.writeText(previous);
      }, priorClipboard); // 원문은 진단/Artifact에 수집하지 않는다.
    }
    await command(a, '<img src=x onerror=alert(1)> 말');
    await expect(a.page.locator('#log .chat img')).toHaveCount(0);
    await input.focus(); await expect(input).toBeFocused();
    await expect(input).toBeInViewport({ ratio: 1 });
    const submit = a.page.getByRole('button', { name: '실행 ↵', exact: true });
    await submit.scrollIntoViewIfNeeded(); await expect(submit).toBeInViewport({ ratio: 1 });
    expect(await submit.evaluate(element => {
      const r = element.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return element === hit || element.contains(hit);
    })).toBe(true);
    const promptSegments = a.page.locator('#log .prompt').last().locator('[class^="semantic-"]');
    expect(await promptSegments.count()).toBeGreaterThan(0);
    expect(await a.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const button of await a.page.getByRole('button').all()) await expect(button).toHaveAccessibleName(/\S/);
    await travel(a, a.state.zone === 'staging_room' ? 'hq_concourse' : 'staging_room');
    expect(a.errors).toEqual([]);
    await actors.close(a); expect(sessions()[a.name]).toEqual([]);
  }
});

test('TEST-TIMING-DOOR 실제 60초·통과 연장·자동 닫힘', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  await adminDoor(a, b);
  const opened = snapshot().doors.find(d => d.door_id === 'hq_admin_door');
  await command(b, '서');
  await command(b, '동');
  const passed = snapshot().doors.find(d => d.door_id === 'hq_admin_door');
  expect(passed.auto_close_at).toBeGreaterThan(opened.auto_close_at);
  await command(a, '관리실 문 열어');
  expect(snapshot().doors.find(d => d.door_id === 'hq_admin_door').auto_close_at).toBe(passed.auto_close_at);
  await pollUntil(() => Date.now() / 1000 >= passed.auto_close_at, { timeout: 65000, interval: 100 });
  await command(a, '동');
  expect(snapshot().players[a.name].zone).toBe('hq_concourse');
  await command(b, '서');
  expect(snapshot().players[b.name].zone).toBe('hq_admin_office');
  await pollUntil(() => snapshot().doors.find(d => d.door_id === 'hq_admin_door').state === 'CLOSED', { timeout: 10000, interval: 500 });
  expect(snapshot().doors.find(d => d.door_id === 'hq_admin_door').auto_close_at).toBeNull();
  await expect.poll(() => a.state.exit_details.find(e => e.name === '동')?.can_move).toBe(false);
  await expect.poll(() => b.state.exit_details.find(e => e.name === '서')?.can_move).toBe(false);
});

test('TEST-TIMING-PARTY 실제 600초 오프라인 자동 승계', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  const id = a.state.party.id;
  expect(b.state.party.id).toBe(id);
  await command(a, b.name + ' 일행방어'); await actors.close(a);
  const saved = snapshot(), original = saved.parties[id];
  expect(saved.claims.length).toBeGreaterThan(0);
  expect(original.leader_offline_since).toBeGreaterThan(0);
  await pollUntil(() => Date.now() / 1000 >= original.leader_offline_since + 600, { timeout: 605000, interval: 1000 });
  await pollUntil(() => snapshot().parties[id].leader === snapshot().players[b.name].id, { timeout: 15000, interval: 500 });
  const again = await actors.create(0);
  await command(again, '일행');
  expect(snapshot().parties[id].leader).toBe(snapshot().players[b.name].id);
  expect(snapshot().parties[id].tactics).toEqual(original.tactics);
  expect(snapshot().parties[id].members).toEqual(original.members);
  expect(snapshot().claims).toEqual(saved.claims);
  expect(snapshot().items).toEqual(saved.items);
});
