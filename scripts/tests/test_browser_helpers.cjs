const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { actionMetadata, safePath, observeBrowserErrors, safeObservation, waitDetached, finishActors } = require('../browser/safety.cjs');
const SafeReporter = require('../browser/reporter.cjs');

test('TEST-P2-02-A 개인 메시지 입력은 분류와 길이만 보존', () => {
  const input = '검증나 PRIVATE-ONLY-SECRET 대화';
  const action = actionMetadata(input);
  assert.deepEqual(action, { kind: 'command', category: 'chat', length: input.length });
  assert.equal(JSON.stringify(action).includes('PRIVATE-ONLY-SECRET'), false);
});
test('TEST-P2-02-B 공개 발화와 인자형 명령도 원문 비수집', () => {
  for (const input of ['공개-SENTINEL 말', "'공개-SENTINEL", '암호-SENTINEL 물어', '비밀-SENTINEL 일행대화', '인자-SENTINEL 정보']) {
    assert.equal(JSON.stringify(actionMetadata(input)).includes('SENTINEL'), false);
    assert.equal(actionMetadata(input).length, input.length);
  }
});
test('TEST-P2-02-C URL·상태·Console·임의 프레임 원문 비수집', () => {
  const secret = 'PASSWORD-TOKEN-SENTINEL';
  const observation = safeObservation({ player: secret, path: safePath(`http://user:${secret}@localhost/webclient/?token=${secret}#${secret}`),
    state: { message: secret }, lastCommand: secret, errors: [secret], sockets: [{ url: secret, received: [secret], frames: 2 }], lastAction: { category: secret, length: 24, raw: secret } });
  assert.equal(observation.path, '/webclient/');
  assert.equal(JSON.stringify(observation).includes(secret), false);
});
test('TEST-P2-02-D 실패 reporter는 오류·stdout·임의 첨부와 스크린샷을 버림', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pz-safe-reporter-'));
  const previous = process.env.PRIMAL_BROWSER_RESULTS;
  process.env.PRIMAL_BROWSER_RESULTS = root;
  try {
    const secret = 'ASSERTION-PRIVATE-SENTINEL';
    const context = path.join(root, 'screenshots', 'owned', 'error-context.md');
    fs.mkdirSync(path.dirname(context), { recursive: true });
    fs.writeFileSync(context, secret);
    const reporter = new SafeReporter();
    reporter.onTestEnd({ title: 'TEST-P2-02-D ' + secret }, { status: 'failed', duration: 1, errors: [{ message: secret, stack: secret }], stdout: [secret], attachments: [
      { name: 'observations', body: Buffer.from(JSON.stringify([{ player: 'A', lastCommand: secret, errors: [secret] }])) },
      { name: 'unsafe-screenshot', path: path.join(root, secret + '.png') },
      { name: 'unknown', body: Buffer.from(secret) },
      { name: 'error-context', path: context },
    ] });
    reporter.onError({ message: secret });
    reporter.onEnd({ status: 'failed' });
    const result = fs.readFileSync(path.join(root, 'results.json'), 'utf8');
    assert.equal(result.includes(secret), false);
    assert.equal(JSON.parse(result).tests[0].status, 'failed');
    assert.deepEqual(JSON.parse(result).screenshots, []);
    assert.equal(fs.existsSync(context), false);
  } finally {
    if (previous === undefined) delete process.env.PRIMAL_BROWSER_RESULTS; else process.env.PRIMAL_BROWSER_RESULTS = previous;
    fs.rmSync(root, { recursive: true });
  }
});
test('TEST-P2-02-D 오류 context 삭제 실패는 reporter 성공으로 기록하지 않음', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pz-context-cleanup-'));
  const previous = process.env.PRIMAL_BROWSER_RESULTS, unlink = fs.unlinkSync;
  process.env.PRIMAL_BROWSER_RESULTS = root;
  try {
    const reporter = new SafeReporter();
    fs.unlinkSync = () => { throw new Error('controlled-delete-failure'); };
    reporter.onTestEnd({ title: 'TEST-P2-02-D' }, { status: 'passed', duration: 1, errors: [], attachments: [
      { name: 'error-context', path: path.join(root, 'screenshots', 'owned', 'error-context.md') },
    ] });
    reporter.onEnd({ status: 'passed' });
    const result = JSON.parse(fs.readFileSync(path.join(root, 'results.json'), 'utf8'));
    assert.equal(result.status, 'failed'); assert.equal(result.errors, 1);
  } finally {
    fs.unlinkSync = unlink;
    if (previous === undefined) delete process.env.PRIMAL_BROWSER_RESULTS; else process.env.PRIMAL_BROWSER_RESULTS = previous;
    fs.rmSync(root, { recursive: true });
  }
});
test('TEST-P2-03-C 자기 세션 해제를 기다리되 남아 있는 다른 세션을 보존', async () => {
  let calls = 0;
  await waitDetached(() => ({ A: ++calls === 1 ? ['owned', 'other'] : ['other'], B: ['b-live'] }), 'A', new Set(['owned']), { interval: 0 });
  assert.equal(calls, 2);
});
test('TEST-P2-03-D Probe 실패와 Timeout을 명확한 실패로 전달', async () => {
  await assert.rejects(waitDetached(() => { throw new Error('private-error'); }, 'A', new Set(['id'])), /puppet-detach: probe-failed/);
  await assert.rejects(waitDetached(() => ({ A: ['id'] }), 'A', new Set(['id']), { timeout: 0 }), /puppet-detach: timeout/);
});
test('TEST-P2-03-D 첨부와 일부 Context 정리가 실패해도 모든 Context 정리', async () => {
  const closed = [];
  const players = [0, 1].map(index => ({ diagnostic: () => ({ player: 'A' }), close: async () => {
    closed.push(index); if (index === 0) throw new Error('context-close-failed');
  } }));
  let failure;
  try { await finishActors(players, { attach: async () => { throw new Error('attachment'); } }); }
  catch (error) { failure = error; }
  assert.deepEqual(closed, [0, 1]);
  assert.equal(failure.errors.length, 2);
  assert.match(failure.errors[1].message, /attach-failed/);
});
test('TEST-P2-03-A 이미 닫힌 세션은 추가 대기 없이 완료', async () => {
  await waitDetached(() => ({ A: [] }), 'A', new Set(['old']));
});
test('favicon 404·다른 404·500·JS·전송 오류는 원문 비수집으로 실패', async () => {
  const secret = 'PRIVATE-RESOURCE-SENTINEL';
  for (const [event, details] of [
    ['response', { status: () => 404, url: () => '/favicon.ico?token=' + secret }],
    ['response', { status: () => 404, url: () => '/static/website/images/favicon.ico' }],
    ['response', { status: () => 404, url: () => '/other.js?token=' + secret }],
    ['response', { status: () => 500, url: () => '/other.js?token=' + secret }],
    ['console', { type: () => 'error', text: () => secret, location: () => ({ url: secret }) }],
    ['pageerror', new Error(secret)], ['requestfailed', { failure: () => secret }],
  ]) {
    const page = new EventEmitter(), errors = [];
    observeBrowserErrors(page, errors);
    // 감지 과정 자체가 원문 getter를 호출하지 않는 것도 검증한다.
    for (const key of ['url', 'text', 'location', 'failure']) if (key in details) details[key] = () => { throw new Error('원문 접근 금지'); };
    page.emit(event, details);
    assert.deepEqual(errors, ['browser-error']);
    let observation, closed = false;
    await assert.rejects(finishActors([{ errors, close: async () => { closed = true; }, diagnostic: () => ({ errors, warnings: [secret] }) }],
      { attach: async (_, attachment) => { observation = JSON.parse(attachment.body); } }), /actor-cleanup-failed/);
    assert.equal(closed, true);
    assert.equal(JSON.stringify(observation).includes(secret), false);
    assert.equal('warnings' in observation[0], false);
    assert.deepEqual(observation[0].errors, ['browser-error']);
  }
});
test('성공 리소스와 일반 Console 메시지는 오류로 기록하지 않음', () => {
  const page = new EventEmitter(), errors = [];
  observeBrowserErrors(page, errors);
  for (const status of [200, 204, 301, 304]) page.emit('response', { status: () => status });
  for (const type of ['log', 'info', 'warning']) page.emit('console', { type: () => type });
  assert.deepEqual(errors, []);
});
test('60초 keepalive는 실제 명령 횟수·원문 비교를 덮지 않는다', () => {
  const { isCommandFrame } = require('../browser/safety.cjs');
  assert.equal(isCommandFrame('text', ['idle']), false);
  assert.equal(isCommandFrame('pz_auth', [{ password: 'private-fixture' }]), false);
  assert.equal(isCommandFrame('text', ['서']), true);
  assert.equal(isCommandFrame('text', ['']), true);
  assert.equal(isCommandFrame('text', []), false);
});

test('차단 Console 오류는 원문 노출 없이 실패하며 모든 Context는 닫는다', async () => {
  const closed = [];
  const players = [0, 1].map(index => ({ errors: index ? [] : ['PRIVATE-CONSOLE-BODY'],
    close: async () => closed.push(index), diagnostic: () => ({ player: index ? 'B' : 'A' }) }));
  await assert.rejects(finishActors(players, { attach: async () => {} }), error =>
    error instanceof AggregateError && error.errors[0].message === 'browser-console-failed' && !String(error).includes('PRIVATE-CONSOLE-BODY'));
  assert.deepEqual(closed, [0, 1]);
});
