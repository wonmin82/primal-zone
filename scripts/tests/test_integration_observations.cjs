const { test } = require('node:test');
const assert = require('node:assert/strict');
const { extensionWindow, preDeadline, monitorBeforeDeadline, exitIntegrity, preservedExits } = require('../browser/review-contracts.cjs');

test('P1-01 실제 통과 요청~응답 창의 60초 예약과 30초 예약 거절', () => {
  extensionWindow(160.2, 100, 100.4);
  assert.throws(() => extensionWindow(130, 100, 100.4), /not-sixty/);
  assert.throws(() => extensionWindow(200, 100, 100.4), /not-sixty/);
});
test('P1-01 만료 전 OPEN과 조기 CLOSED/LOCKED/예약 변경 구분', () => {
  const window = { start: 30, end: 30.1 };
  preDeadline({ state: 'OPEN', auto_close_at: 60 }, window, 60, 'door');
  for (const state of ['CLOSED', 'LOCKED']) assert.throws(() => preDeadline({ state, auto_close_at: null }, window, 60, 'door'), /early-expiry/);
  assert.throws(() => preDeadline({ state: 'OPEN', auto_close_at: 30 }, window, 60, 'door'), /early-expiry/);
});
function monitored(kind, duration, earlyAt, { state = 'CLOSED', delay = () => 0, wait = ms => ms / 1000,
  unavailableAt = Infinity, observations = [], initial = 0 } = {}) {
  let seconds = initial;
  return monitorBeforeDeadline(() => {
    if (seconds >= unavailableAt) throw new Error('private-server-detail');
    const start = seconds;
    seconds += delay(seconds);
    observations.push({ start, end: seconds });
    const early = seconds >= earlyAt;
    return kind === 'door' ? { state: early ? state : 'OPEN', auto_close_at: early ? duration - 1 : duration }
      : { leader: early ? 2 : 1, leader_offline_since: 0 };
  }, { kind, since: 0, deadline: duration, expected: { leader: 1, leader_offline_since: 0 }, wall: () => seconds,
    mono: () => seconds * 1000, pause: async ms => { seconds += wait(ms, seconds); } });
}
test('P203-01 정상 Door 60초 중간/4초 전/최종 완료 창 (기존 P1-01)', async () => {
  const observations = [];
  assert.deepEqual(await monitored('door', 60, 60, { observations }), { middleSeen: true, nearSeen: true, finalSeen: true });
  assert(observations.some(o => o.end >= 30 && o.end < 56));
  assert(observations.some(o => o.start === 56));
  assert(observations.at(-1).end >= 59 && observations.at(-1).end <= 59.5);
  for (let n = 1; n < observations.length; n++) {
    assert(observations[n].start - observations[n - 1].end <= (observations[n - 1].end >= 56 ? 0.5 : 5));
  }
});
test('P203-02 30초 조기 닫힘을 만료 뒤 CLOSED 성공으로 오인하지 않음 (기존 P1-01)', async () => {
  await assert.rejects(monitored('door', 60, 30), /early-expiry/);
});
test('P203-06 정상 리더 600초 중간/4초 전/최종 완료 창 (기존 P1-01)', async () => {
  const observations = [];
  assert.deepEqual(await monitored('party', 600, 600, { observations }), { middleSeen: true, nearSeen: true, finalSeen: true });
  assert(observations.some(o => o.end >= 300 && o.end < 596));
  assert(observations.some(o => o.start === 596));
  assert(observations.at(-1).end >= 599 && observations.at(-1).end <= 599.5);
});
test('P203-07 300초 조기 승계를 600초 뒤 정상 결과로 오인하지 않음 (기존 P1-01)', async () => {
  await assert.rejects(monitored('party', 600, 300), /early-succession/);
});

test('P203-03 56초 OPEN 뒤 58초 조기 CLOSED 검출', async () => {
  await assert.rejects(monitored('door', 60, 58), /early-expiry/);
});

test('P203-08 596초 원래 리더 뒤 598초 조기 승계 검출', async () => {
  await assert.rejects(monitored('party', 600, 598), /early-succession/);
});

test('P203-04 56초 OPEN 뒤 58초 조기 LOCKED 검출', async () => {
  await assert.rejects(monitored('door', 60, 58, { state: 'LOCKED' }), /early-expiry/);
});

test('P203-05 OPEN 유지하더라도 58초 예약 변경 검출', async () => {
  await assert.rejects(monitored('door', 60, 58, { state: 'OPEN' }), /early-expiry/);
});

test('P203-09 스케줄링 지연으로 최종 창을 놓치면 실패', async () => {
  await assert.rejects(monitored('door', 60, 60, { wait: (ms, now) => now >= 58.5 ? 1.1 : ms / 1000 }), /final-checkpoint-missed/);
});

test('P203-10 최종 Probe 시작이 유효해도 완료가 만료를 넘어가면 실패', async () => {
  await assert.rejects(monitored('door', 60, Infinity, { delay: now => now >= 58.5 ? 1.6 : 0 }), /pre-observation-missed/);
  await assert.rejects(monitored('party', 600, Infinity, { delay: now => now >= 598.5 ? 1.6 : 0 }), /pre-observation-missed/);
});

test('P203-11 정상 Probe 지연을 고려해 조회 완료를 최종 창 안에서 확인', async () => {
  for (const [kind, duration] of [['door', 60], ['party', 600]]) {
    const observations = [];
    await monitored(kind, duration, duration, { observations, delay: () => 0.2 });
    const last = observations.at(-1);
    assert(last.end >= duration - 1 && last.end <= duration - 0.5);
    assert(observations.filter(o => o.start >= duration - 4).length >= 4);
    for (let n = 1; n < observations.length; n++) {
      if (observations[n - 1].start >= duration - 4) assert(observations[n].start - observations[n - 1].start <= 0.500001);
    }
  }
  // 500ms보다 조회가 오래 걸리면 불필요한 대기를 더하지 않고, 최종 완료 창은 유지한다.
  const observations = [];
  await monitored('door', 60, 60, { observations, delay: () => 0.8 });
  assert(observations.at(-1).end >= 59 && observations.at(-1).end <= 59.5);
  assert(observations.at(-1).start < 59);
});

test('P203-12 서버 조회 실패는 민감 오류 원문 없이 명확하게 실패', async () => {
  await assert.rejects(monitored('door', 60, 60, { unavailableAt: 40 }), error => {
    assert.equal(error.message, 'timing-observation-unavailable');
    assert(!JSON.stringify(error).includes('private-server-detail'));
    return true;
  });
});

test('P2-03 중간 체크포인트 누락 및 최종 창 뒤 완료는 실패', async () => {
  await assert.rejects(monitored('door', 60, 60, { initial: 56 }), /required-checkpoint-missed/);
  await assert.rejects(monitored('door', 60, 60, { wait: (ms, now) => now === 25 ? 15 : ms / 1000 }), /required-checkpoint-missed/);
  await assert.rejects(monitored('door', 60, 60, { wait: (ms, now) => now === 55 ? 4 : ms / 1000 }), /required-checkpoint-missed/);
  await assert.rejects(monitored('door', 60, Infinity, { delay: now => now >= 58.5 ? 1.1 : 0 }), /final-checkpoint-missed/);
});
test('P1-01 만료 직전 관측 누락/지연은 PASS가 아님', async () => {
  assert.throws(() => preDeadline({ state: 'OPEN', auto_close_at: 60 }, { start: 59, end: 60 }, 60, 'door'), /observation-missed/);
  let seconds = 0;
  await assert.rejects(monitorBeforeDeadline(() => { seconds += 3; return { state: 'OPEN', auto_close_at: 60 }; },
    { since: 0, deadline: 60, kind: 'door', wall: () => seconds, mono: () => seconds * 1000 }), /probe-too-slow/);
});
function database() {
  return { rooms: { outside: 10, inside: 11, general: 12 }, routes: { outside: { 동: 'inside', 남: 'general' }, inside: { 서: 'outside' }, general: {} },
    doors: [{ id: 8, door_id: 'admin', room_a: 'outside', room_b: 'inside', direction_a: '동', direction_b: '서', exit_a_id: 20, exit_b_id: 21 }],
    installations: [{ door_id: 'admin', door_pk: 8, endpoints: [{ exit_pk: 20, room_pk: 10, target_pk: 11 }, { exit_pk: 21, room_pk: 11, target_pk: 10 }] }],
    exits: [
      { pk: 20, key: '동', location_pk: 10, destination_pk: 11, typeclass: 'typeclasses.exits.Exit', managed_ids: ['outside:동'], door_id: 'admin', installation_ids: ['admin'] },
      { pk: 21, key: '서', location_pk: 11, destination_pk: 10, typeclass: 'typeclasses.exits.Exit', managed_ids: ['inside:서'], door_id: 'admin', installation_ids: ['admin'] },
      { pk: 22, key: '남', location_pk: 10, destination_pk: 12, typeclass: 'typeclasses.exits.Exit', managed_ids: ['outside:남'], door_id: null, installation_ids: [] }] };
}
test('P1-02 실제 Exit·설치 증거·일반 출구가 같은 정상 Snapshot', () => {
  const before = database(); exitIntegrity(before); preservedExits(before, structuredClone(before));
});
for (const [field, value] of [['location_pk', 12], ['destination_pk', 12], ['pk', 99], ['typeclass', 'evennia.objects.objects.DefaultExit']]) {
  test('P1-02 실제 Exit ' + field + ' 손상 검출 (정적 routes 불변)', () => {
    const before = database(), after = structuredClone(before); after.exits[0][field] = value;
    assert.deepEqual(after.routes, before.routes);
    assert.throws(() => preservedExits(before, after), /exit-/);
  });
}
test('P1-02 설치 원본 PK/Room/Destination 증거 불일치 검출', () => {
  for (const field of ['exit_pk', 'room_pk', 'target_pk']) {
    const db = database(); db.installations[0].endpoints[0][field] = 99;
    assert.throws(() => exitIntegrity(db), /endpoint-mismatch/);
  }
});
test('P1-02 일반 Exit 재생성 및 Door 자동 편입 검출', () => {
  const before = database(), after = structuredClone(before); after.exits[2].pk = 99;
  assert.throws(() => preservedExits(before, after), /changed/);
  after.exits[2].door_id = 'admin'; assert.throws(() => exitIntegrity(after), /general-adopted/);
});
test('P1-02 관리 Exit 중복/소실 및 Door 참조 손상 검출', () => {
  const db = database(); db.exits.push(structuredClone(db.exits[0]));
  assert.throws(() => exitIntegrity(db), /duplicate/);
  db.exits.pop(); db.exits[0].door_id = null;
  assert.throws(() => exitIntegrity(db), /reference-mismatch/);
  db.exits.shift(); assert.throws(() => exitIntegrity(db), /count-or-identity/);
});
