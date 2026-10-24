const { test, expect, sessions, finishActors } = require('./fixtures.cjs');

test('TEST-50A-01 실제 Chromium HTTP·WebSocket·인증·초기 상태', async ({ actors, browser }, testInfo) => {
  const a = await actors.create(0);
  const icon = a.page.locator('link[rel="icon"]');
  await expect(icon).toHaveAttribute('href', '/static/website/images/favicon.ico');
  await expect(icon).toHaveAttribute('type', 'image/x-icon');
  // Headless Chromium의 자동 favicon 요청에 의존하지 않고 최종 DOM 참조를 실제 브라우저로 로드한다.
  const iconUrl = await icon.evaluate(link => {
    const url = new URL(link.href);
    // 새 Context에서 자동 favicon 요청과 다른 URL로 실제 서버 응답을 검증한다.
    url.searchParams.set('favicon-check', '1');
    return url.href;
  });
  const [response, size] = await Promise.all([
    a.page.waitForResponse(response => response.url() === iconUrl),
    a.page.evaluate(async url => {
      const image = new Image();
      image.src = url;
      await image.decode();
      return [image.naturalWidth, image.naturalHeight];
    }, iconUrl),
  ]);
  expect(new URL(response.url()).origin).toBe(new URL(a.page.url()).origin);
  expect(response.status()).toBe(200);
  const bytes = await response.body();
  expect(bytes.readUInt16LE(0)).toBe(0); // ICONDIR reserved
  expect(bytes.readUInt16LE(2)).toBe(1); // 실제 ICO
  expect(bytes.readUInt16LE(4)).toBe(2);
  expect([0, 1].map(index => [bytes[6 + index * 16], bytes[7 + index * 16]])).toEqual([[16, 16], [32, 32]]);
  expect([[16, 16], [32, 32]]).toContainEqual(size);
  expect(a.state.zone).toBe('staging_room');
  await expect(a.page.locator('#room-name')).toHaveText(a.state.room);
  expect(a.state.hp).toBeGreaterThan(0);
  expect(a.errors).toEqual([]);
  await testInfo.attach('chromium-version', { body: browser.version(), contentType: 'text/plain' });
});

test('TEST-50A-02 점수 Enter 전송·실제 출력·최신 Prompt·중복 없음', async ({ actors }) => {
  const a = await actors.create(0);
  const before = a.revision;
  await a.command('점수');
  await expect.poll(() => a.revision).toBeGreaterThan(before);
  await expect(a.page.locator('#log .sheet').last()).toContainText('점수');
  expect(a.sentCount).toBe(1);
  expect(a.errors).toEqual([]);
});

test('TEST-50A-03 서로 다른 Account·독립 Context·실제 Puppet', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  expect(a.page.context()).not.toBe(b.page.context());
  expect(a.state.name).not.toBe(b.state.name);
  expect(a.sockets).toHaveLength(1); expect(b.sockets).toHaveLength(1);
  await expect.poll(() => sessions()[a.name].length).toBe(1);
  await expect.poll(() => sessions()[b.name].length).toBe(1);
  await a.command('점수');
  await expect(b.page.locator('#player-name')).toHaveText(b.name);
  expect(a.errors.concat(b.errors)).toEqual([]);
  const bIds = sessions()[b.name];
  await actors.close(a);
  expect([...a.ownedSessionIds].every(id => !sessions()[a.name].includes(id))).toBe(true);
  expect(sessions()[b.name]).toEqual(bIds);
  await b.command('점수');
});

test('TEST-50A-04 같은 방 공개 메시지·동일 원문·HTML 안전성', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  expect(a.state.zone).toBe(b.state.zone);
  const text = '50A-' + Date.now() + ' <b>공개 검증</b> & 안전';
  await a.command(text + ' 말');
  for (const player of [a, b]) {
    const chat = player.page.locator('#log .chat').filter({ hasText: text });
    await expect(chat).toHaveCount(1);
    await expect(chat).toHaveText(a.name + ': ' + text);
    await expect(chat.locator('b')).toHaveCount(0);
    await expect(player.page.locator('#player-name')).toHaveText(player.name);
    expect(player.errors).toEqual([]);
  }
  expect(JSON.stringify(a.diagnostic()).includes(text)).toBe(false);
  expect(a.lastAction.category).toBe('chat');
});

test('TEST-50A-05 실제 종료·재연결·재인증·세션 중복 없음', async ({ actors }) => {
  const a = await actors.create(0);
  const previous = sessions()[a.name][0];
  await a.page.getByRole('button', { name: '접속 종료', exact: true }).click();
  await expect(a.page.locator('#connection-label')).toHaveText('연결 끊김');
  await expect.poll(() => sessions()[a.name].length).toBe(0);
  expect(a.sockets[0].closed).toBe(true);
  a.authenticated = false;
  await a.page.getByRole('button', { name: '재연결', exact: true }).click();
  await a.login(false);
  await expect.poll(() => sessions()[a.name].length).toBe(1);
  expect(sessions()[a.name][0]).not.toBe(previous);
  expect(a.sockets).toHaveLength(2);
  expect(a.state.zone).toBe('staging_room');
  await a.command('점수');
  expect(a.errors).toEqual([]);
});

test('TEST-50A-06 Desktop/Narrow 구조·입력·버튼 이름·스크린샷 증거', async ({ actors }, testInfo) => {
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    const a = await actors.create(0, viewport);
    await expect(a.page.locator('#command')).toBeVisible();
    await a.page.locator('#command').scrollIntoViewIfNeeded();
    expect(await a.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(a.page.getByRole('button', { name: '실행 ↵', exact: true })).toBeVisible();
    await expect(a.page.getByRole('button', { name: '강타', exact: true })).toBeVisible();
    if (viewport.width === 1280) await expect(a.page.getByRole('button', { name: '주변 살펴보기 ↗', exact: true })).toBeVisible();
    for (const button of await a.page.getByRole('button').all()) await expect(button).toHaveAccessibleName(/\S/);
    await a.command('점수');
    await expect(a.page.locator('#log .sheet').last()).toContainText('점수');
    expect(a.errors).toEqual([]);
    const path = testInfo.outputPath(`safe-viewport-${viewport.width}.png`);
    // 레이아웃만 증거로 남긴다. 로그/입력/인증 UI는 원문을 수집하지 않는다.
    await a.page.screenshot({ path, fullPage: true, mask: [a.page.locator('#log'), a.page.locator('#command'), a.page.locator('#auth-dialog')] });
    await testInfo.attach(`safe-viewport-${viewport.width}`, { path, contentType: 'image/png' });
    await actors.close(a);
    expect(a.detached).toBe(true);
    expect(sessions()[a.name]).toEqual([]);
  }
});

test('TEST-P2-02-A 개인 메시지는 실제 전달하되 진단에 원문 비수집', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  const privateText = 'PRIVATE-FIXTURE-' + Date.now();
  const command = b.name + ' ' + privateText + ' 대화';
  await a.command(command);
  await expect.poll(async () => (await b.page.locator('#log').textContent()).includes(privateText)).toBe(true);
  expect(a.lastAction).toEqual({ kind: 'command', category: 'chat', length: command.length });
  expect(JSON.stringify(a.diagnostic()).includes(privateText)).toBe(false);
  expect(a.pendingCommand).toBeNull();
});

test('TEST-P2-02-D 실제 Assertion 실패·첨부 실패에도 안전한 증거와 Context 정리', async ({ actors }, testInfo) => {
  const a = await actors.create(0), b = await actors.create(1);
  const text = 'FAILURE-PRIVATE-FIXTURE-' + Date.now();
  await a.command(b.name + ' ' + text + ' 대화');
  if (process.env.PRIMAL_BROWSER_FAILURE_PROBE === '1') {
    // 잡지 않은 실제 Assertion 실패와 정상 Fixture teardown의 증거 경계를 검증한다.
    expect(await a.page.locator('#command').isEnabled()).toBe(false);
  }
  let assertion;
  try { expect(await a.page.locator('#command').isEnabled()).toBe(false); }
  catch (error) { assertion = error; }
  expect(!!assertion).toBe(true);
  // 실패 보고서가 오류 원문을 수집하지 않는지는 reporter 계약 테스트도 검사한다.
  await finishActors([a, b], testInfo);
  expect(a.detached && b.detached).toBe(true);
  expect(JSON.stringify(a.diagnostic()).includes(text)).toBe(false);
  const c = await actors.create(0);
  let cleanup;
  try { await finishActors([c], { attach: async () => { throw new Error('controlled-attach-failure'); } }); }
  catch (error) { cleanup = error; }
  expect(cleanup instanceof AggregateError).toBe(true);
  expect(c.detached).toBe(true);
  expect(sessions()[c.name]).toEqual([]);
});

test('TEST-P2-03-D Probe 실패·Timeout은 실패로 구분하고 실제 Context는 정리', async ({ actors }) => {
  for (const mode of ['probe', 'timeout']) {
    const a = await actors.create(0);
    const owned = [...a.ownedSessionIds];
    let cleanup;
    try { await a.close({ timeout: 0, probe: () => {
      if (mode === 'probe') throw new Error('controlled-probe-failure');
      return { [a.name]: owned };
    } }); } catch (error) { cleanup = error; }
    expect(cleanup instanceof AggregateError).toBe(true);
    expect(cleanup.errors.some(error => error.message === 'puppet-detach: ' + (mode === 'probe' ? 'probe-failed' : 'timeout'))).toBe(true);
    expect(a.page.isClosed()).toBe(true);
    await actors.close(a); // 실제 읽기 전용 Probe로 종료를 재확인한다.
    expect(a.detached).toBe(true);
  }
});


test('TEST-66A-01 실제 재분배 버튼의 안정 Provider·scope·단일 효과', async ({ actors }) => {
  const a = await actors.create(0);
  for (const command of ['남', '승강기', '4층', '북']) await a.command(command);
  expect(a.state.zone).toBe('training_office');
  const refs = a.state.training_controls.reset;
  for (const scope of ['attributes', 'skills', 'all']) {
    const button = a.page.locator('#reset-' + scope);
    await expect(button).toBeEnabled();
    const payload = JSON.parse(await button.getAttribute('data-action-invocation'));
    expect(payload.action_id).toBe('training.reset.' + scope);
    expect(payload.arguments.value).toBe(scope);
    expect(payload.roles.provider).toEqual(refs.find(row => row.action.arguments.value === scope).action.roles.provider);
    expect(payload.roles.provider[0].kind).toBe('object');
  }
  const skills = a.state.growth.skills.map(skill => [skill.id, skill.rank]);
  const prompts = a.prompts;
  await a.page.locator('#reset-attributes').click();
  await expect.poll(() => a.prompts).toBeGreaterThan(prompts);
  expect(a.state.growth.attributes.every(attribute => attribute.allocated === 0)).toBe(true);
  expect(a.state.growth.skills.map(skill => [skill.id, skill.rank])).toEqual(skills);
  expect(a.errors).toEqual([]);
});

test('TEST-66B-01 아이템 행의 안정 UUID Action과 장비 해제·재장착', async ({ actors }) => {
  const a = await actors.create(0);
  const weapon = a.state.inventory.find(item => item.weapon && item.location !== "inside");
  expect(weapon?.identity).toBeTruthy();
  const control = operation => a.page.locator('#inventory [data-action-invocation]').evaluateAll((buttons, { identity, operation }) => buttons.map(button => ({
    payload: JSON.parse(button.dataset.actionInvocation),
  })).find(row => row.payload.roles.provider[0].identity === identity &&
    row.payload.action_id.endsWith('.' + operation))?.payload, {identity: weapon.identity, operation});
  const info = await control('information');
  expect(info.roles.subject[0].identity).toBe(weapon.identity);
  async function click(operation) {
    const payload = await control(operation);
    expect(payload.roles.provider[0].identity).toBe(weapon.identity);
    const before = a.prompts;
    const buttons = a.page.locator('#inventory [data-action-invocation]');
    const index = await buttons.evaluateAll((buttons, action) => buttons.findIndex(button =>
      JSON.stringify(JSON.parse(button.dataset.actionInvocation)) === JSON.stringify(action)), payload);
    expect(index).toBeGreaterThanOrEqual(0);
    await buttons.nth(index).click();
    await expect.poll(() => a.prompts).toBeGreaterThan(before);
  }
  if (!weapon.equipped) await click('wield');
  await click('information');
  expect(a.state.inventory.find(item => item.identity === weapon.identity).equipped).toBe(true);
  await click('unwield');
  expect(a.state.inventory.find(item => item.identity === weapon.identity).equipped).toBe(false);
  await a.page.evaluate(() => {
    const send = WebSocket.prototype.send;
    window.itemScopeReplay = { send };
    WebSocket.prototype.send = function(frame) {
      const value = JSON.parse(frame);
      if (value[0] === 'pz_action' && value[1][0].action_id.endsWith('.wield')) {
        window.itemScopeReplay.socket = this;
        window.itemScopeReplay.frame = frame;
        WebSocket.prototype.send = send;
      }
      return send.call(this, frame);
    };
  });
  await click('wield');
  expect(a.state.inventory.find(item => item.identity === weapon.identity).equipped).toBe(true);
  await click('unwield');
  await a.command(`${weapon.name} 버려`);
  expect(a.state.inventory.some(item => item.identity === weapon.identity)).toBe(false);
  expect(a.state.ground_loot.flatMap(source => source.loot).some(entry =>
    entry.action?.roles.subject[0].identity === weapon.identity)).toBe(true);
  const inventory = a.state.inventory.map(({ identity, count, equipped }) => ({ identity, count, equipped }));
  const credits = a.state.credits;
  await a.page.evaluate(() => {
    const replay = window.itemScopeReplay;
    const value = JSON.parse(replay.frame);
    value[1][0].request_id = 'phase3-stale-root-item';
    replay.send.call(replay.socket, JSON.stringify(value));
  });
  await a.command('봐');
  expect(a.state.inventory.map(({ identity, count, equipped }) => ({ identity, count, equipped }))).toEqual(inventory);
  expect(a.state.credits).toBe(credits);
  expect(a.state.ground_loot.flatMap(source => source.loot).some(entry =>
    entry.action?.roles.subject[0].identity === weapon.identity)).toBe(true);
  expect(a.errors).toEqual([]);
});


test('TEST-66C-01 바닥 전리품 안정 UUID·중복 및 오래된 요청 거절·텍스트 동등 지급', async ({ actors }) => {
  const a = await actors.create(0, { width: 1280, height: 900 });
  const count = () => a.state.inventory.filter(item => item.id === 'scrap').reduce((sum, item) => sum + item.count, 0);
  const initialIdentities = a.state.inventory.filter(item => item.id === 'scrap').map(item => item.identity).sort();
  const initial = count();
  expect(initial).toBeGreaterThan(1);
  await a.command('회수부품 버려');
  expect(count()).toBe(initial - 1);
  const entry = a.state.ground_loot.flatMap(source => source.loot).find(item => item.id === 'scrap');
  expect(entry.label).toBe('회수부품 1');
  expect(entry?.action.action_id).toBe('loot.take');
  const original = entry.action;
  expect(original.roles.source[0].identity).toBeTruthy();
  expect(original.roles.subject[0].identity).toMatch(/^[0-9a-f-]{36}$/i);
  expect(original.arguments.snapshot).toBeTruthy();
  const buttons = a.page.locator('#context-actions [data-action-invocation]');
  const index = await buttons.evaluateAll((buttons, original) => buttons.findIndex(button =>
    JSON.stringify(JSON.parse(button.dataset.actionInvocation)) === JSON.stringify(original)), original);
  expect(index).toBeGreaterThanOrEqual(0);
  // 실제 UI가 보낸 프레임을 같은 소유 브라우저 메모리에서만 보존한다.
  await a.page.evaluate(() => {
    const send = WebSocket.prototype.send;
    window.lootReplay = {send};
    WebSocket.prototype.send = function(frame) {
      const value = JSON.parse(frame);
      if (value[0] === 'pz_action' && value[1][0].action_id === 'loot.take') {
        window.lootReplay.socket = this;
        window.lootReplay.frame = frame;
        WebSocket.prototype.send = send;
      }
      return send.call(this, frame);
    };
  });
  await buttons.nth(index).click();
  await expect.poll(count).toBe(initial);
  // 회수된 분할 Entry는 기존 스택으로 병합된다. 이후 stale 요청은 소멸한
  // UUID를 보유한 실제 버튼 프레임이며 생존 스택에 다시 적용되면 안 된다.
  expect(a.state.inventory.filter(item => item.id === 'scrap').map(item => item.identity).sort()).toEqual(initialIdentities);
  expect(initialIdentities).not.toContain(original.roles.subject[0].identity);
  expect(a.state.ground_loot.flatMap(source => source.loot).filter(item => item.id === 'scrap')).toEqual([]);
  async function replay(sameRequest) {
    await a.page.evaluate(sameRequest => {
      const replay = window.lootReplay;
      const value = JSON.parse(replay.frame);
      if (!sameRequest) value[1][0].request_id += '-stale';
      replay.send.call(replay.socket, JSON.stringify(value));
    }, sameRequest);
    // 같은 WebSocket의 후속 공개 명령으로 처리를 직렬화한다. 중복 요청에는 ACK/Prompt가 없다.
    await a.command('봐');
  }
  await replay(true);
  expect(count()).toBe(initial);
  // 같은 실제 Typed 요청/서버 상태를 좁은 화면에서도 유지한다.
  await a.page.setViewportSize({ width: 390, height: 844 });
  await a.page.locator('#command').scrollIntoViewIfNeeded();
  expect(await a.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(a.page.locator('#command')).toBeEnabled();
  await a.command('회수부품 버려');
  const replacement = a.state.ground_loot.flatMap(source => source.loot).find(item => item.id === 'scrap');
  // 실물이 모두 사라진 동일 Ground 그룹이 번호 1을 다시 받더라도
  // 원래 UUID의 요청은 새 실물에 적용되지 않아야 한다.
  expect(replacement.label).toBe(entry.label);
  expect(replacement.action.roles.subject[0].identity).not.toBe(original.roles.subject[0].identity);
  expect(replacement.action.roles.subject[0].scope_id).toBe(original.roles.subject[0].scope_id);
  expect(replacement?.action.roles.source).not.toEqual(original.roles.source);
  await replay(false);
  expect(count()).toBe(initial - 1);
  expect(a.state.ground_loot.flatMap(source => source.loot).find(item => item.id === 'scrap').action.roles.source)
    .toEqual(replacement.action.roles.source);
  await a.command(replacement.take_command);
  expect(count()).toBe(initial);
  expect(a.errors).toEqual([]);
});
