const { test, expect, sessions } = require('./fixtures.cjs');

test('TEST-50A-01 실제 Chromium HTTP·WebSocket·인증·초기 상태', async ({ actors, browser }, testInfo) => {
  const a = await actors.create(0);
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
  expect(a.sent.filter(text => text === '점수')).toHaveLength(1);
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
  for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
    const a = await actors.create(0, viewport);
    await expect(a.page.locator('#command')).toBeVisible();
    await a.page.locator('#command').scrollIntoViewIfNeeded();
    expect(await a.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(a.page.getByRole('button', { name: '실행 ↵', exact: true })).toBeVisible();
    await expect(a.page.getByRole('button', { name: '강타', exact: true })).toBeVisible();
    if (viewport.width === 1366) await expect(a.page.getByRole('button', { name: '주변 살펴보기 ↗', exact: true })).toBeVisible();
    for (const button of await a.page.getByRole('button').all()) await expect(button).toHaveAccessibleName(/\S/);
    await a.command('점수');
    await expect(a.page.locator('#log .sheet').last()).toContainText('점수');
    expect(a.errors).toEqual([]);
    await a.page.screenshot({ path: testInfo.outputPath(`viewport-${viewport.width}.png`), fullPage: true });
    await a.page.context().close();
  }
});
