// 입력/오류 원문은 수집하지 않는다. 게임 처리와 분리된 증거·정리 경계다.
function actionMetadata(input) {
  return { kind: 'command', category: /(?:^'|(?:말|대화|답|무|일행대화|물어)$)/u.test(input.trim()) ? 'chat' : 'command', length: input.length };
}
function safePath(url) {
  try { const pathname = new URL(url).pathname; return ['/webclient/', '/favicon.ico', '/'].includes(pathname) ? pathname : '/other'; }
  catch { return '/invalid'; }
}
function isFavicon404(location, message) {
  return location.endsWith('/favicon.ico') && message.includes('404');
}
function safeObservation(value) {
  const number = n => Number.isFinite(n) && n >= 0 ? n : 0;
  const action = value.lastAction;
  return {
    player: ['A', 'B', 'C'].includes(value.player) ? value.player : 'unknown',
    path: ['/webclient/', '/favicon.ico', '/', '/other', '/invalid'].includes(value.path) ? value.path : '/other',
    lastAction: action ? { kind: 'command', category: action.category === 'chat' ? 'chat' : 'command', length: number(action.length) } : null,
    hasState: value.hasState === true, contextClosed: value.contextClosed === true, revision: number(value.revision),
    sockets: (value.sockets || []).map(s => ({ closed: s.closed === true, frames: number(s.frames) })),
    ownedSessions: number(value.ownedSessions), detached: value.detached === true,
    errors: (value.errors || []).map(() => 'browser-error'), warnings: (value.warnings || []).map(() => 'favicon-404'),
  };
}
async function pollUntil(condition, { timeout = 10000, interval = 50, now = Date.now, pause = ms => new Promise(resolve => setTimeout(resolve, ms)), stage = 'cleanup' } = {}) {
  const deadline = now() + timeout;
  while (true) {
    let ready;
    try { ready = await condition(); } catch { throw new Error(stage + ': probe-failed'); }
    if (ready) return;
    if (now() >= deadline) throw new Error(stage + ': timeout');
    await pause(interval);
  }
}
async function waitDetached(probe, name, ownedIds, options) {
  await pollUntil(() => {
    const current = probe()[name];
    if (!Array.isArray(current)) throw new Error('invalid probe');
    return [...ownedIds].every(id => !current.includes(id));
  }, { ...options, stage: 'puppet-detach' });
}
async function finishActors(players, testInfo) {
  const failures = [];
  for (const player of players) {
    try { await player.close(); } catch (error) { failures.push(error); }
  }
  // 정리 완료 상태를 기록한다. 진단/첨부 실패로 Context 정리를 건너뛰지 않는다.
  try { await testInfo.attach('observations', { body: JSON.stringify(players.map(p => safeObservation(p.diagnostic()))), contentType: 'application/json' }); }
  catch { failures.push(new Error('observations: attach-failed')); }
  if (failures.length) throw new AggregateError(failures, 'actor-cleanup-failed');
}
module.exports = { actionMetadata, safePath, isFavicon404, safeObservation, pollUntil, waitDetached, finishActors };
