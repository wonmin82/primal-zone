// 순수 관측 계약. 원본 Snapshot/입력은 공개 진단에 포함하지 않는다.
const assert = require('node:assert/strict');
function requireCondition(condition, stage) { if (!condition) throw new Error(stage); }
function extensionWindow(deadline, started, completed, seconds = 60) {
  requireCondition([deadline, started, completed].every(Number.isFinite) && completed >= started,
    'timing-extension-invalid');
  // 서버와 브라우저는 같은 격리 호스트의 wall clock이다. 완료 시각은 요청~응답 사이.
  requireCondition(deadline >= started + seconds - 0.1 && deadline <= completed + seconds + 0.1,
    'timing-extension-not-sixty-seconds');
}
function preDeadline(value, window, deadline, kind, expected) {
  requireCondition(window.end >= window.start && window.end < deadline, 'timing-pre-observation-missed');
  if (kind === 'door') requireCondition(value.state === 'OPEN' && value.auto_close_at === deadline,
    'timing-door-early-expiry');
  else requireCondition(value.leader === expected.leader && value.leader_offline_since === expected.leader_offline_since,
    'timing-party-early-succession');
}
async function monitorBeforeDeadline(read, { since, deadline, kind, expected, wall = () => Date.now() / 1000,
  mono = () => performance.now(), pause = ms => new Promise(resolve => setTimeout(resolve, ms)) }) {
  requireCondition(deadline > since && Number.isFinite(deadline), 'timing-deadline-invalid');
  const middle = since + (deadline - since) / 2, near = deadline - 4;
  let middleSeen = false;
  while (true) {
    const start = wall(), tick = mono(), value = await read(), end = wall();
    requireCondition(mono() - tick <= 2000, 'timing-probe-too-slow');
    preDeadline(value, { start, end }, deadline, kind, expected);
    if (start >= middle && start < near) middleSeen = true;
    if (start >= near) {
      requireCondition(middleSeen && end <= deadline - 0.5, 'timing-required-checkpoint-missed');
      return { middleSeen: true, nearSeen: true }; // 상태 원문은 반환/첨부하지 않는다.
    }
    await pause(Math.min(5000, Math.max(0, near - end) * 1000));
  }
}
function exitIntegrity(db) {
  const expected = Object.entries(db.routes).flatMap(([zone, paths]) => Object.keys(paths).map(d => zone + ':' + d)).sort();
  const managed = db.exits.flatMap(e => e.managed_ids);
  requireCondition(new Set(db.exits.map(e => e.pk)).size === db.exits.length, 'exit-pk-duplicate');
  requireCondition(new Set(managed).size === managed.length, 'exit-identity-duplicate');
  requireCondition(JSON.stringify(managed.sort()) === JSON.stringify(expected), 'exit-managed-count-or-identity');
  const endpoints = new Set();
  requireCondition(db.doors.length === db.installations.length, 'exit-installation-count');
  for (const door of db.doors) {
    const journals = db.installations.filter(j => j.door_id === door.door_id && j.door_pk === door.id);
    requireCondition(journals.length === 1 && journals[0].endpoints.length === 2, 'exit-installation-door-mismatch');
    for (const [index, side] of ['a', 'b'].entries()) {
      const proof = journals[0].endpoints[index], exit = db.exits.find(e => e.pk === door['exit_' + side + '_id']);
      requireCondition(exit && !endpoints.has(exit.pk), 'exit-endpoint-missing-or-duplicate');
      endpoints.add(exit.pk);
      requireCondition(exit.pk === proof.exit_pk && exit.location_pk === proof.room_pk && exit.destination_pk === proof.target_pk,
        'exit-installation-endpoint-mismatch');
      requireCondition(exit.typeclass === 'typeclasses.exits.Exit' && exit.key === door['direction_' + side], 'exit-endpoint-type-or-direction');
      requireCondition(exit.location_pk === db.rooms[door['room_' + side]] && exit.destination_pk === db.rooms[door['room_' + (side === 'a' ? 'b' : 'a')]], 'exit-endpoint-room-mismatch');
      requireCondition(exit.door_id === door.door_id && exit.installation_ids.length === 1 && exit.installation_ids[0] === door.door_id,
        'exit-door-reference-mismatch');
      requireCondition(exit.managed_ids.length === 1 && exit.managed_ids[0] === door['room_' + side] + ':' + exit.key, 'exit-endpoint-managed-identity');
    }
  }
  for (const exit of db.exits) {
    if (!endpoints.has(exit.pk)) requireCondition(exit.door_id == null && exit.installation_ids.length === 0, 'exit-general-adopted-by-door');
  }
}
function preservedExits(before, after) {
  exitIntegrity(before); exitIntegrity(after);
  try { assert.deepEqual(after.exits, before.exits); assert.deepEqual(after.rooms, before.rooms); }
  catch { throw new Error('exit-pk-location-destination-type-or-reference-changed'); }
}
module.exports = { extensionWindow, preDeadline, monitorBeforeDeadline, exitIntegrity, preservedExits };
