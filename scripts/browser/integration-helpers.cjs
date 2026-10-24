const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { expect } = require('@playwright/test');
const { pollUntil } = require('./safety.cjs');

function snapshot(timing = false) {
  const script = path.resolve(__dirname, '..', 'integration_probe.py');
  return JSON.parse(execFileSync(process.env.PRIMAL_BROWSER_PYTHON, timing ? [script, '--timing'] : [script], {
    cwd: path.join(process.env.PRIMAL_SMOKE_RUN_DIR, 'game'), env: process.env,
    encoding: 'utf8', timeout: 15000,
  }).trim().split('\n').at(-1));
}
async function command(player, text, fragment) {
  const before = await player.page.locator('#log').textContent();
  await player.command(text);
  if (fragment) await expect.poll(async () => (await player.page.locator('#log').textContent()).slice(before.length)).toContain(fragment);
}
async function travel(player, target) {
  const routes = snapshot().routes, queue = [[player.state.zone, []]], seen = new Set();
  while (queue.length) {
    const [zone, steps] = queue.shift();
    if (zone === target) {
      for (const [action, destination] of steps) {
        if (destination === 'recovery_room' || player.state.zone === 'recovery_room') await player.command('회복실 문 열어');
        await player.command(action);
        try { await expect.poll(() => player.state.zone).toBe(destination); }
        catch (error) {
          // 정의된 Room ID만 로컬 진단한다. 입력/화면/WS 원문은 수집하지 않는다.
          process.stderr.write(`route-boundary: ${zone}->${destination}; observed=${player.state.zone}\n`);
          throw error;
        }
      }
      expect(snapshot().players[player.name].zone).toBe(target);
      return;
    }
    if (seen.has(zone)) continue;
    seen.add(zone);
    for (const [action, destination] of Object.entries(routes[zone])) queue.push([destination, [...steps, [action, destination]]]);
  }
  throw new Error('route-not-found');
}
function itemCount(db, name, definition) {
  const id = db.players[name].id;
  return db.items.filter(row => row.owner_object_id === id && row.definition_id === definition && ['inventory', 'equipment'].includes(row.location_kind)).reduce((n, row) => n + row.quantity, 0);
}
async function party(a, b) {
  await command(a, b.name + ' 일행초청');
  await command(b, '일행합류');
  await expect.poll(() => a.state.party?.id).toBeTruthy();
  await expect.poll(() => b.state.party?.id).toBe(a.state.party.id);
  return a.state.party.id;
}
async function control(operation) {
  const root = process.env.PRIMAL_BROWSER_CONTROL;
  fs.rmSync(path.join(root, 'response.json'), { force: true });
  fs.writeFileSync(path.join(root, 'request.tmp'), JSON.stringify({ operation }));
  fs.renameSync(path.join(root, 'request.tmp'), path.join(root, 'request.json'));
  await pollUntil(() => fs.existsSync(path.join(root, 'response.json')), { timeout: 90000, stage: 'restart-ready' });
  const response = JSON.parse(fs.readFileSync(path.join(root, 'response.json')));
  expect(response.ready).toBe(true);
  if (operation !== 'restart') expect(response.boundary).toBe(operation);
  return response;
}
module.exports = { snapshot, timingSnapshot: () => snapshot(true), command, travel, itemCount, party, restart: () => control('restart'), control };
