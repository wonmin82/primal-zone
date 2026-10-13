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
