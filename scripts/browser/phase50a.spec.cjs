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

test('TEST-103-01 문자 지도 웹 로그와 좁은 화면', async ({ actors }) => {
  const a = await actors.create(0);
  for (const width of [1280, 375]) {
    await a.page.setViewportSize({ width, height: 840 });
    await a.command('지도');
    const map = a.page.locator('#log .log-entry.map').last();
    await expect(map).toContainText('@');
    await expect(map).toHaveCSS('white-space', 'pre');
    await expect(map).toHaveCSS('overflow-x', 'auto');
    await expect(map.locator('.semantic-player')).toContainText('@');
    await a.command('지도 목록');
    await expect(a.page.locator('#log .log-entry.sheet').last()).toContainText('방문한 장소만 표시됩니다.');
    await expect(a.page.locator('#log .log-entry.sheet').last()).toHaveCSS('white-space', 'pre-wrap');
  }
});

async function watchMinimap(player) {
  await player.page.evaluate(() => {
    const original = WebSocket.prototype.send;
    const observed = new WeakSet();
    const samples = new Map();
    let active;
    window.minimapEvidence = {requests: 0, bytes: 0, received: 0, leaks: 0, latest: null};
    window.minimapTimings = [];
    const output = document.getElementById('minimap-content'), replaceChildren = output.replaceChildren;
    function publish(sample) {
      if (sample.bytes && sample.finished !== undefined) {
        window.minimapTimings.push({
          bytes: sample.bytes,
          requestToDomMs: sample.finished - sample.started,
          domUpdateMs: sample.finished - sample.update,
        });
      }
    }
    output.replaceChildren = function(...children) {
      if (active && !children.length) active.update = performance.now();
      const result = replaceChildren.apply(this, children);
      if (active && children.length && active.update !== undefined) {
        active.finished = performance.now();
        publish(active);
        active = null;
      }
      return result;
    };
    WebSocket.prototype.send = function(frame) {
      const [kind, args] = JSON.parse(frame);
      if (kind === 'pz_map' && Number.isInteger(args[0]?.id)) {
        window.minimapEvidence.requests++;
        active = {started: performance.now()};
        samples.set(args[0].id, active);
        if (!observed.has(this)) {
          observed.add(this);
          this.addEventListener('message', ({data}) => {
            const [responseKind, values] = JSON.parse(data);
            if (responseKind !== 'pz_map') return;
            const result = values[0];
            const wire = JSON.stringify(result);
            window.minimapEvidence.bytes = new TextEncoder().encode(data).length;
            if (samples.has(result.id)) {
              const sample = samples.get(result.id);
              sample.bytes = window.minimapEvidence.bytes;
              publish(sample);
              samples.delete(result.id);
            }
            window.minimapEvidence.received++;
            const forbidden = /staging_room|hq_concourse|support_roof|jungle_edge|"position"|"route"|"edges"|"visited"|"destination_id"/;
            if (forbidden.test(wire)) window.minimapEvidence.leaks++;
            window.minimapEvidence.latest = result;
          }, {capture: true});
        }
      }
      return original.call(this, frame);
    };
  });
}

test('TEST-104-01 실제 미니맵 세션 격리·공개 정보·이동 외 상태 갱신', async ({ actors }) => {
  const a = await actors.create(0), b = await actors.create(1);
  const canvas = player => player.page.locator('#minimap-output .minimap-map');
  for (const player of [a, b]) {
    await expect(canvas(player)).toContainText('@');
    await watchMinimap(player);
  }
  const concurrentStart = performance.now();
  await Promise.all([a, b].map(async player => {
    await player.page.locator('#minimap-refresh').click();
    await expect.poll(() => player.page.evaluate(() => window.minimapEvidence.received)).toBe(1);
    await expect(canvas(player)).toContainText('?');
    await expect(canvas(player)).toContainText('@');
  }));
  const concurrentWallMs = performance.now() - concurrentStart;
  await a.command('지도');
  const log = a.page.locator('#log .log-entry.map').last();
  expect(await log.textContent()).toBe(await canvas(a).textContent());
  const aGrid = await canvas(a).textContent(), bGrid = await canvas(b).textContent();
  expect(aGrid).toBe(bGrid);

  const before = a.revision;
  await a.command('점수');
  await expect.poll(() => a.revision).toBeGreaterThan(before);
  expect(await a.page.evaluate(() => window.minimapEvidence.requests)).toBe(1);
  expect(await b.page.evaluate(() => window.minimapEvidence.requests)).toBe(1);

  const south = a.page.locator('#exits .direction-south');
  await expect(south).toBeEnabled();
  await south.click();
  await expect.poll(() => a.state.zone).toBe('hq_concourse');
  await expect(canvas(a)).toContainText('×');
  await a.command('서');
  await expect.poll(() => a.state.zone).toBe('dock');
  await expect(canvas(a)).toContainText('+');
  await a.command('동');
  await expect.poll(() => a.state.zone).toBe('hq_concourse');
  await b.command('남');
  await expect.poll(() => b.state.zone).toBe('hq_concourse');
  await expect(canvas(a)).toContainText('+');
  await expect(canvas(b)).not.toContainText('+');
  await expect(canvas(b)).toContainText('?');
  const sheets = a.page.locator('#minimap-sheet');
  const outpost = sheets.locator('option').filter({hasText: '전초구역'});
  await expect(outpost).toHaveCount(1);
  await sheets.selectOption(await outpost.getAttribute('value'));
  await expect(canvas(a)).toContainText('o');
  await expect(canvas(a)).not.toContainText('@');
  await expect(b.page.locator('#minimap-sheet option').filter({hasText: '전초구역'})).toHaveCount(0);
  const evidence = await a.page.evaluate(() => window.minimapEvidence);
  expect(evidence.leaks).toBe(0);
  expect(evidence.bytes).toBeGreaterThan(0);
  expect(evidence.latest.messages.some(message => message.kind === 'map')).toBe(true);
  expect(evidence.latest.centers).toContain('탐사대 부두');
  expect(await b.page.evaluate(() => window.minimapEvidence.leaks)).toBe(0);
  const timings = await a.page.evaluate(() => window.minimapTimings);
  expect(timings.length).toBeGreaterThan(0);
  // 격리 브라우저 결과 폴더의 로컬 근거에는 숫자만 저장한다.
  require('node:fs').writeFileSync(
    require('node:path').join(process.env.PRIMAL_BROWSER_RESULTS, 'minimap-104-metrics.json'),
    JSON.stringify({timings, concurrentWallMs}),
  );

  await a.page.getByRole('button', {name: '접속 종료', exact: true}).click();
  await expect(a.page.locator('#minimap-panel')).toBeHidden();
  await expect(canvas(a)).toHaveCount(0);
  await expect(a.page.locator('#minimap-sheet option')).toHaveCount(1);
  await a.page.getByRole('button', {name: '재연결', exact: true}).click();
  await a.login(false);
  await expect(canvas(a)).toContainText('@');
  await expect(a.page.locator('#minimap-sheet')).toHaveValue('');
  expect(a.errors.concat(b.errors)).toEqual([]);
});

test('TEST-104-02 본부 층·Connector·중심 이동과 반응형 지도 접근성', async ({ actors }) => {
  const a = await actors.create(0);
  const panel = a.page.locator('#minimap-panel');
  const canvas = a.page.locator('#minimap-output .minimap-map');
  const summary = a.page.locator('#minimap-description');
  const go = async (command, zone, connector = false) => {
    await a.command(command);
    await expect.poll(() => a.state.zone).toBe(zone);
    await expect(summary).toContainText(a.state.room);
    if (connector) await expect(canvas).toHaveCount(0);
    else await expect(canvas).toContainText('@');
  };
  await go('남', 'hq_concourse');
  await go('계단', 'hq_stairs_1f', true);
  await expect(a.page.locator('#minimap-output')).toContainText('나가기');
  await go('나가기', 'hq_concourse');
  await go('승강기', 'support_elevator', true);
  for (const [floor, zone] of [
    ['2층', 'support_2f_c'], ['3층', 'support_3f_c'], ['4층', 'support_4f_c'], ['5층', 'support_5f_c'],
  ]) {
    await go(floor, zone);
    if (floor === '3층') {
      await go('동', 'support_3f_e1');
      await a.command('회복실 문 닫아');
      await expect(canvas).toContainText('×');
      await a.command('회복실 문 열어');
      await expect(canvas).toContainText('?');
      await go('서', zone);
    }
    await go('승강기', 'support_elevator', true);
  }
  await go('옥상', 'support_roof');
  await go('북동', 'support_roof_ne');
  await expect(canvas).toContainText('╱');
  const center = a.page.getByLabel('중심 방문 장소 또는 별칭');
  await center.fill('본부 옥상');
  await center.press('Enter');
  await expect(a.page.locator('#minimap-output .minimap-message').first()).toContainText('본부 옥상');
  const viewport = a.page.locator('#minimap-output');
  await expect(viewport).toHaveAttribute('aria-describedby', 'minimap-description');
  await expect(summary).toContainText('공개 연결');
  const current = a.page.getByRole('button', {name: '현재 위치', exact: true});
  await current.focus();
  await expect(current).toBeFocused();
  await current.press('Enter');
  await expect(center).toHaveValue('');

  // 기존 로그와 미니맵의 줄바꿈 정책은 독립적이다.
  for (const width of [1366, 1024, 375]) {
    await a.page.setViewportSize({width, height: 840});
    await expect(canvas).toHaveCSS('white-space', 'pre');
    await expect(viewport).toHaveCSS('overflow-x', 'auto');
    expect(await a.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await expect(a.page.locator('#command')).toBeEnabled();
  }
  await a.page.addStyleTag({content: 'html { zoom: 1.25; } #minimap-output .minimap-map { font-family: monospace !important; }'});
  await expect(canvas).toHaveCSS('font-family', 'monospace');
  await expect(canvas).toContainText('╱');
  const toggle = panel.locator(':scope > summary');
  await toggle.focus();
  await toggle.press('Enter');
  await expect(canvas).toHaveCount(0);
  await toggle.press('Enter');
  await expect(canvas).toContainText('@');
  await a.command('지도 목록');
  await expect(a.page.locator('#log .sheet').last()).toHaveCSS('white-space', 'pre-wrap');
  await a.command('출구');
  await expect(a.page.locator('#log .sheet').last()).toContainText('출구');
  expect(a.errors).toEqual([]);
});

test('TEST-104-03 주변 행동과 지도 뷰포트의 위치·크기 및 키보드 초점', async ({ page }) => {
  // 게임 서버 HTML·정적 파일을 사용하며, 지연·긴 지도·권한 철회 시점만 격리 WebSocket으로 제어한다.
  let wire;
  let pageErrors = 0;
  page.on('pageerror', () => { pageErrors++; });
  const requests = [];
  await page.routeWebSocket(url => ['ws:', 'wss:'].includes(url.protocol), ws => {
    wire = ws;
    ws.onMessage(data => {
      const [kind, [request]] = JSON.parse(String(data));
      if (kind === 'pz_map') requests.push(request);
    });
  });
  await page.goto('/webclient/');
  await expect(page.locator('#connection-label')).toHaveText('연결됨');
  const send = (kind, payload) => wire.send(JSON.stringify([kind, [payload], {}]));
  const direction = name => ({name, exists:true, can_move:true, status:'이동 가능', destination_name:'공개 출구'});
  const state = (revision, more = false) => send('pz_state', {
    name:'검증 탐사자', currency:{}, growth:{attributes:[], skills:[]}, minimap_owner:'fixture', minimap_revision:revision,
    level:1, max_level:10, hp:60, max_hp:60, mental:40, max_mental:40, xp:0, xp_floor:0, xp_next:100,
    exit_details:(more ? ['북', '동', '계단', '승강기'] : ['북']).map(direction),
    enemies:more ? [{label:'적', hp:4, max_hp:4, can_attack:true}] : [],
    corpses:[], ground_loot:more ? [{loot:[{display_label:'전리품'}]}] : [], inventory:[],
    interactables:more ? Array.from({length:16}, (_, i) => ({
      role:'npc', label:'주변 인물 ' + i, actions:[{label:'봐', command:'주변 인물 봐'}],
    })) : [],
  });
  const receive = async (revision, count, messages, selected = true) => {
    await expect.poll(() => requests.length).toBe(count);
    send('pz_map', {
      id:requests[count - 1].id, owner:'fixture', revision, messages,
      sheet:selected ? '본부' : '', sheets:selected ? ['본부', '다른 층'] : [],
      centers:selected ? ['중앙 복도'] : [], summary:selected ? '현재 위치 중앙 복도' : '',
    });
  };
  const message = (kind, text) => ({kind, segments:[{role:'text', text}]});
  const small = [message('event', '본부'), message('map', '@─?')];
  const big = [message('event', '공개 지도 제목 '.repeat(35)),
    message('map', Array(24).fill('@'.repeat(60)).join('\n'))];
  const viewport = page.locator('#minimap-output'), canvas = viewport.locator('.minimap-map');
  const scroll = page.locator('.surroundings-scroll'), mapSheet = page.locator('#minimap-sheet');
  const center = page.locator('#minimap-center'), command = page.locator('#command');
  const geometry = () => page.evaluate(() => {
    const rect = s => document.querySelector(s).getBoundingClientRect();
    const surrounding = rect('.surroundings-panel'), grid = rect('#exits');
    const map = rect('#minimap-panel'), viewport = rect('#minimap-output'), party = rect('.party-panel');
    return {
      surroundingTop:surrounding.top, surroundingHeight:surrounding.height, gridHeight:grid.height,
      mapTop:map.top, viewportTop:viewport.top, viewportHeight:viewport.height, partyTop:party.top,
      actionHeight:rect('.surroundings-scroll').height, scrollY,
    };
  });
  let requestCount = 0;
  const results = [];
  for (const [width, zoom] of [[1600, 1], [1024, 1], [375, 1], [375, 1.25]]) {
    await page.setViewportSize({width, height:840});
    if (zoom !== 1) await page.addStyleTag({content:'html { zoom:1.25; } body,.minimap-map { font-family:monospace !important; }'});
    await page.evaluate(() => window.scrollTo(0, 0));
    const revision = `${width}/${zoom}`;
    state(revision);
    await receive(revision, ++requestCount, small);
    await expect(canvas).toHaveText('@─?');
    expect(await page.locator('.right-column > :first-child > :first-child').getAttribute('class')).toContain('surroundings-panel');
    const start = await geometry();
    expect(start.actionHeight).toBeGreaterThanOrEqual(180);
    expect(start.mapTop).toBeGreaterThan(start.surroundingTop);
    expect(start.partyTop).toBeGreaterThan(start.mapTop);
    const measured = {};
    const stable = async stage => {
      const current = await geometry();
      expect(current.scrollY).toBe(start.scrollY);
      for (const key of ['surroundingTop', 'surroundingHeight', 'gridHeight', 'mapTop', 'viewportTop', 'viewportHeight', 'actionHeight']) {
        expect(Math.abs(current[key] - start[key]), stage + ' ' + key).toBeLessThanOrEqual(1);
      }
      measured[stage] = current;
    };
    await expect(page.locator('#other-exits')).toBeHidden();
    state(revision, true);
    await expect(scroll.getByText('주변 인물 15')).toHaveCount(1);
    await expect(scroll.getByRole('button', {name:/^승강기/})).toBeEnabled();
    await expect(page.locator('#exits [data-command="승강기"]')).toHaveCount(0);
    await stable('주변 대상·특수 출구');
    await scroll.evaluate(el => { el.scrollTop = 90; });
    expect(await scroll.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    await stable('주변 행동 스크롤');
    await viewport.evaluate(el => el.focus({preventScroll:true}));
    const pending = revision + '-loading';
    state(pending);
    await expect(viewport.getByRole('status')).toHaveText('지도를 불러오는 중입니다.');
    await expect(canvas).toHaveCount(0);
    await expect(viewport).toBeFocused();
    await stable('로딩');
    await receive(pending, ++requestCount, big);
    await expect(canvas).toContainText('@@@@@@@@');
    expect(await viewport.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
    expect(await viewport.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(width !== 1024);
    await stable('큰 지도');
    await viewport.evaluate(el => { el.scrollTop = 40; });
    const offset = await viewport.evaluate(el => el.scrollTop);
    await page.locator('#minimap-refresh').evaluate(el => el.click());
    await receive(pending, ++requestCount, big);
    await expect(canvas).toContainText('@@@@@@@@');
    await expect(viewport).toBeFocused();
    expect(await viewport.evaluate(el => el.scrollTop)).toBe(offset);
    state(revision + '-connector');
    await receive(revision + '-connector', ++requestCount, [message('sheet', '승강기\n나가기')], false);
    await expect(viewport).toContainText('나가기');
    await expect(viewport).toBeFocused();
    await stable('Connector');
    await center.evaluate(el => { el.value = '작성 중'; el.focus({preventScroll:true}); });
    state(revision + '-revoked');
    await expect(center).toBeFocused();
    await expect(center).toHaveValue('작성 중');
    await expect(mapSheet.locator('option')).toHaveCount(1);
    await expect(page.locator('#minimap-centers option')).toHaveCount(0);
    await expect(page.locator('#minimap-description')).toBeEmpty();
    await expect(viewport).not.toContainText('나가기');
    await receive(revision + '-revoked', ++requestCount, [message('error', '조회할 수 없는 지도')], false);
    await expect(viewport.getByRole('status')).toHaveText('조회할 수 없는 지도');
    await stable('권한 철회·오류');
    await mapSheet.evaluate(el => el.focus({preventScroll:true}));
    state(revision + '-sheet-focus');
    await expect(mapSheet).toBeFocused();
    await receive(revision + '-sheet-focus', ++requestCount, small);
    await expect(canvas).toHaveText('@─?');
    await expect(mapSheet).toBeFocused();
    await expect(page.locator('#minimap-description')).toHaveAttribute('aria-live', 'polite');
    await command.evaluate(el => el.focus({preventScroll:true}));
    state(revision + '-restored');
    await receive(revision + '-restored', ++requestCount, small);
    await expect(canvas).toHaveText('@─?');
    await expect(command).toBeFocused();
    await stable('권한 복구');
    results.push({width, zoom, start, measured});
  }
  expect(pageErrors).toBe(0);
  require('node:fs').writeFileSync(require('node:path').join(process.env.PRIMAL_BROWSER_RESULTS, 'minimap-106-layout.json'),
    JSON.stringify(results, null, 2));
});

test('TEST-104-04 실제 지도 갱신 중 중심 제출 제한과 조회 복구', async ({ actors }) => {
  const a = await actors.create(0);
  const { page } = a;
  const center = page.locator('#minimap-center');
  const submit = page.locator('#minimap-center-submit');
  const refresh = page.locator('#minimap-refresh');
  const status = page.locator('#minimap-status');
  const canvas = page.locator('#minimap-output .minimap-map');
  const summary = page.locator('#minimap-description');
  const place = '본부 3층 중앙 복도';
  const go = async (command, zone) => {
    await a.command(command);
    await expect.poll(() => a.state.zone).toBe(zone);
    await expect(summary).toContainText(a.state.room);
  };

  // 실제 서버 요청은 전달하고 지도 응답만 클라이언트 수신 경계에서 지연한다.
  await page.evaluate(() => {
    const {send, addEventListener} = WebSocket.prototype;
    const held = [];
    const gate = window.mapCenterGate = {
      hold: false, requests: [], held: 0,
      release() {
        this.hold = false;
        for (const deliver of held.splice(0)) deliver();
        this.held = 0;
      },
    };
    WebSocket.prototype.send = function(data) {
      const [kind, args] = JSON.parse(data);
      if (kind === 'pz_map' && Number.isInteger(args[0]?.id)) {
        const {sheet, center} = args[0];
        gate.requests.push({...sheet && {sheet}, ...center && {center}});
      }
      return send.call(this, data);
    };
    WebSocket.prototype.addEventListener = function(kind, listener, options) {
      if (kind !== 'message') return addEventListener.call(this, kind, listener, options);
      return addEventListener.call(this, kind, event => {
        if (gate.hold && JSON.parse(event.data)[0] === 'pz_map') {
          held.push(() => listener.call(this, event));
          gate.held++;
        } else listener.call(this, event);
      }, options);
    };
  });
  await page.getByRole('button', {name:'접속 종료', exact:true}).click();
  await expect(page.locator('#connection-label')).toHaveText('연결 끊김');
  a.authenticated = false;
  await page.getByRole('button', {name:'재연결', exact:true}).click();
  await a.login(false);
  await expect(canvas).toContainText('@');
  for (const [command, zone] of [
    ['남', 'hq_concourse'], ['승강기', 'support_elevator'],
    ['3층', 'support_3f_c'], ['동', 'support_3f_e1'],
  ]) await go(command, zone);
  await expect(submit).toBeEnabled();
  await page.evaluate(() => { window.mapCenterGate.requests = []; });
  const hold = () => page.evaluate(() => { window.mapCenterGate.hold = true; });
  const release = () => page.evaluate(() => window.mapCenterGate.release());
  const requests = () => page.evaluate(() => window.mapCenterGate.requests);
  const waitHeld = () => expect.poll(() => page.evaluate(() => window.mapCenterGate.held)).toBe(1);
  const tops = () => page.evaluate(() => ['#minimap-panel', '#minimap-output'].map(selector =>
    document.querySelector(selector).getBoundingClientRect().top + window.scrollY));
  const expectStable = async reference => {
    for (const [index, top] of (await tops()).entries()) expect(Math.abs(top - reference[index])).toBeLessThanOrEqual(1);
  };

  await center.fill(place);
  const before = await tops();
  await hold();
  await a.command('회복실 문 닫아');
  await waitHeld();
  await expect(status).toHaveText('지도를 불러오는 중입니다.');
  await expect(submit).toBeDisabled();
  await expect(page.locator('#command')).toBeFocused();
  const pending = await requests();
  expect(pending).toEqual([{}]);
  await center.press('Enter');
  await expect(center).toBeFocused();
  expect(await requests()).toEqual(pending);
  await submit.click({force:true});
  expect(await requests()).toEqual(pending);
  await page.locator('#minimap-center-form').dispatchEvent('submit', {cancelable:true});
  expect(await requests()).toEqual(pending);
  await expect(center).toHaveValue(place);
  await expectStable(before);
  await release();
  await expect(submit).toBeEnabled();
  await expect(center).toHaveValue(place);
  await expectStable(before);
  expect(await requests()).toEqual(pending);

  await page.setViewportSize({width:375, height:840});
  await submit.click();
  await expect.poll(requests).toEqual([...pending, {sheet:'본부 3층', center:place}]);
  await expect(page.locator('#minimap-output .minimap-message').first()).toContainText(place);
  await expect(submit).toBeEnabled();

  await center.fill('존재하지 않는 중심 검증');
  await center.press('Enter');
  await expect(status).not.toBeEmpty();
  await expect(canvas).toHaveCount(0);
  await expect(submit).toBeDisabled();
  await expect.poll(async () => (await requests()).at(-1)).toEqual({sheet:'본부 3층', center:'존재하지 않는 중심 검증'});
  await page.locator('#minimap-current').click();
  await expect(submit).toBeEnabled();
  await expect.poll(async () => (await requests()).at(-1)).toEqual({});

  await page.clock.install();
  await hold();
  await refresh.click();
  await waitHeld();
  await page.clock.fastForward(10001);
  await expect(status).toContainText('지도 응답이 지연되었습니다');
  await expect(submit).toBeDisabled();
  await release();
  await expect(status).toContainText('지도 응답이 지연되었습니다');
  await expect(submit).toBeDisabled();
  await refresh.click();
  await expect(submit).toBeEnabled();

  await go('서', 'support_3f_c');
  await go('승강기', 'support_elevator');
  await expect(canvas).toHaveCount(0);
  await expect(submit).toBeEnabled();
  await center.fill(place);
  await center.press('Enter');
  await expect.poll(async () => (await requests()).at(-1)).toEqual({center:place});
  await expect(canvas).toContainText('o');
  expect(a.errors).toEqual([]);
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
    expect(payload.roles.provider[0].kind).toBe('actor');
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
  async function expectEquipmentMessage(verb) {
    const log = a.page.locator('#log');
    const entry = log.locator('.log-entry').filter({
      has: a.page.locator('.semantic-success', { hasText: verb }),
    }).last();
    await expect(entry.locator('.semantic-item')).toContainText(weapon.name);
    await expect(entry.locator('.semantic-success')).toHaveText(verb);
    const colors = await entry.locator('span').evaluateAll(spans => spans.map(span => getComputedStyle(span).color));
    expect(new Set(colors).size).toBe(3);
    expect(await log.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  }
  if (!weapon.equipped) await click('wield');
  await click('information');
  expect(a.state.inventory.find(item => item.identity === weapon.identity).equipped).toBe(true);
  await click('unwield');
  expect(a.state.inventory.find(item => item.identity === weapon.identity).equipped).toBe(false);
  await expectEquipmentMessage('해제했다');
  await a.page.setViewportSize({ width: 390, height: 844 });
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
  await expectEquipmentMessage('무장했다');
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
