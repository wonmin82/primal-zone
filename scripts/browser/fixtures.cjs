const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const { test: base, expect } = require('@playwright/test');
const { actionMetadata, safePath, isFavicon404, safeObservation, pollUntil, waitDetached, finishActors } = require('./safety.cjs');
// 인증 파일/프레임 원문은 보고서·Artifact·Trace에 복사하지 않는다.
const credentials = JSON.parse(fs.readFileSync(process.env.PRIMAL_BROWSER_CREDENTIALS, 'utf8'));
function sessions() {
  return JSON.parse(execFileSync(process.env.PRIMAL_BROWSER_PYTHON,
    ['scripts/browser_probe.py'], { encoding: 'utf8', env: process.env, timeout: 10000 }));
}
class Player {
  constructor(context, index) {
    this.context = context; this.index = index;
    [this.name, this.password] = credentials[index];
    this.state = null; this.revision = 0; this.prompts = 0; this.sentCount = 0;
    this.sockets = []; this.errors = []; this.warnings = []; this.lastAction = null;
    this.ownedSessionIds = new Set(); this.detached = false;
  }
  async initialize() {
    this.page = await this.context.newPage();
    const page = this.page;
    page.on('pageerror', () => this.errors.push('browser-error'));
    page.on('console', message => {
      if (message.type() !== 'error') return;
      if (isFavicon404(message.location().url, message.text())) this.warnings.push('favicon-404');
      else this.errors.push('browser-error');
    });
    page.on('websocket', socket => {
      const observation = { closed: false, frames: 0, ready: false, expectedUrl: new URL(socket.url()).href === new URL(process.env.PRIMAL_BROWSER_WS).href };
      this.sockets.push(observation);
      socket.on('close', () => { observation.closed = true; });
      socket.on('framereceived', ({ payload }) => {
        const [kind, args] = JSON.parse(String(payload));
        observation.frames++;
        if (kind === 'text') observation.ready = true;
        if (kind === 'pz_state') { this.state = args[0]; this.revision++; }
        if (kind === 'pz_log' && args[0].kind === 'prompt') this.prompts++;
        if (kind === 'pz_auth') this.authenticated = args[0].ok;
      });
      socket.on('framesent', ({ payload }) => {
        const [kind, args] = JSON.parse(String(payload));
        if (kind === 'text') { this.sentCount++; this.exactSubmission = args[0] === this.pendingCommand; }
      });
    });
    return this;
  }
  async login(navigate = true) {
    const previous = new Set(sessions()[this.name]);
    if (navigate) expect((await this.page.goto('/webclient/')).status()).toBe(200);
    await expect(this.page.locator('#connection-label')).toHaveText('연결됨');
    await expect.poll(() => this.sockets.at(-1)?.ready).toBe(true);
    await this.page.locator('#username').fill(this.name);
    await this.page.locator('#password').fill(this.password);
    await this.page.getByRole('button', { name: '접속하기', exact: true }).click();
    await pollUntil(() => {
      const added = sessions()[this.name].filter(id => !previous.has(id));
      for (const id of added) this.ownedSessionIds.add(id);
      return added.length > 0;
    }, { stage: 'puppet-login' });
    await expect.poll(() => this.authenticated).toBe(true);
    await expect(this.page.locator('#player-name')).toHaveText(this.name);
    await expect(this.page.locator('#command')).toBeEnabled();
    await expect(this.page.locator('#auth-dialog')).not.toBeVisible();
    await expect.poll(() => this.state?.name).toBe(this.name);
    expect(this.sockets.at(-1).expectedUrl).toBe(true);
    return this;
  }
  async command(command) {
    this.lastAction = actionMetadata(command);
    const prompts = this.prompts, sent = this.sentCount;
    this.pendingCommand = command;
    try {
      await this.page.locator('#command').fill(command);
      await this.page.locator('#command').press('Enter');
      await expect.poll(() => this.sentCount).toBe(sent + 1);
      expect(this.exactSubmission).toBe(true);
      await expect.poll(() => this.prompts).toBeGreaterThan(prompts);
      await expect(this.page.locator('#log .prompt').last()).toHaveAttribute('data-awaiting-input', 'true');
    } finally { this.pendingCommand = null; }
  }
  diagnostic() {
    return safeObservation({ player: ['A', 'B', 'C'][this.index], path: safePath(this.page?.url() || ''), lastAction: this.lastAction,
      hasState: !!this.state, revision: this.revision, sockets: this.sockets, contextClosed: this.page?.isClosed() === true,
      ownedSessions: this.ownedSessionIds.size, detached: this.detached, errors: this.errors, warnings: this.warnings });
  }
  async close({ probe = sessions, timeout = 10000 } = {}) {
    if (this.detached) return;
    const failures = [];
    try { await this.context.close(); } catch { failures.push(new Error('context-close-failed')); }
    // Context 종료 뒤 Playwright가 WebSocket close 이벤트를 전달하지 않을 수 있다.
    // 브라우저 채널 종료와 아래 실제 서버 Puppet 해제를 각각 확인한다.
    try { await pollUntil(() => this.sockets.every(s => s.closed) || this.page?.isClosed(), { timeout, stage: 'websocket-close' }); }
    catch (error) { failures.push(error); }
    try { await waitDetached(probe, this.name, this.ownedSessionIds, { timeout }); }
    catch (error) { failures.push(error); }
    this.detached = failures.length === 0;
    if (failures.length) throw new AggregateError(failures, 'player-cleanup-failed');
  }
}
const test = base.extend({
  actors: async ({ browser }, use, testInfo) => {
    const players = [];
    const create = async (index, viewport) => {
      const context = await browser.newContext({ viewport: viewport || { width: 1366, height: 768 } });
      const player = new Player(context, index);
      players.push(player); // newPage/login 실패도 정리한다.
      await player.initialize();
      return player.login();
    };
    try { await use({ create, close: player => player.close(), credentials: credentials.map(([name]) => name) }); }
    finally { await finishActors(players, testInfo); }
  },
});
module.exports = { test, expect, sessions, finishActors };
