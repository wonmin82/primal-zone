const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const { test: base, expect } = require('@playwright/test');
// Harness의 비공개 임시 파일만 읽는다. 보고서/Artifact/Trace로 복사하지 않는다.
const credentials = JSON.parse(fs.readFileSync(process.env.PRIMAL_BROWSER_CREDENTIALS, 'utf8'));

class Player {
  constructor(page, name, password) {
    this.page = page; this.name = name; this.password = password;
    this.state = null; this.revision = 0; this.logs = []; this.sent = [];
    this.sockets = []; this.errors = []; this.warnings = []; this.lastCommand = null;
    page.on('pageerror', error => this.errors.push(error.message));
    page.on('console', message => {
      if (message.type() !== 'error') return;
      const location = message.location().url;
      // 게임 실행과 무관한 기본 favicon 부재는 원 증거를 남기는 비차단 HTTP 경고다.
      if (location.endsWith('/favicon.ico') && message.text().includes('404')) this.warnings.push({ message: message.text(), url: location });
      else this.errors.push({ message: message.text(), url: location });
    });
    page.on('websocket', socket => {
      const observation = { url: socket.url(), closed: false, received: [] };
      this.sockets.push(observation);
      socket.on('close', () => { observation.closed = true; });
      socket.on('framereceived', ({ payload }) => {
        const [kind, args] = JSON.parse(String(payload));
        observation.received.push(kind);
        if (kind === 'pz_state') { this.state = args[0]; this.revision++; }
        if (kind === 'pz_log') this.logs.push(args[0]);
        if (kind === 'pz_auth') this.authenticated = args[0].ok;
      });
      socket.on('framesent', ({ payload }) => {
        const [kind, args] = JSON.parse(String(payload));
        if (kind === 'text') this.sent.push(args[0]); // 인증 프레임은 수집하지 않는다.
      });
    });
  }
  async login(navigate = true) {
    if (navigate) {
      const response = await this.page.goto('/webclient/');
      expect(response.status()).toBe(200);
    }
    await expect(this.page.locator('#connection-label')).toHaveText('연결됨');
    // Portal→Server 등록 완료 안내를 실제 프레임으로 확인한다.
    await expect.poll(() => this.sockets.at(-1)?.received.includes('text')).toBe(true);
    await this.page.locator('#username').fill(this.name);
    await this.page.locator('#password').fill(this.password);
    await this.page.getByRole('button', { name: '접속하기', exact: true }).click();
    await expect.poll(() => this.authenticated).toBe(true);
    await expect(this.page.locator('#player-name')).toHaveText(this.name);
    await expect(this.page.locator('#command')).toBeEnabled();
    await expect(this.page.locator('#auth-dialog')).not.toBeVisible();
    await expect.poll(() => this.state?.name).toBe(this.name);
    expect(new URL(this.sockets.at(-1).url).href).toBe(new URL(process.env.PRIMAL_BROWSER_WS).href);
    return this;
  }
  async command(command) {
    this.lastCommand = command;
    const prompts = this.logs.filter(log => log.kind === 'prompt').length;
    const sent = this.sent.length;
    await this.page.locator('#command').fill(command);
    await this.page.locator('#command').press('Enter');
    await expect.poll(() => this.sent.length).toBe(sent + 1);
    expect(this.sent.at(-1)).toBe(command);
    await expect.poll(() => this.logs.filter(log => log.kind === 'prompt').length).toBeGreaterThan(prompts);
    await expect(this.page.locator('#log .prompt').last()).toHaveAttribute('data-awaiting-input', 'true');
  }
  diagnostic() {
    return { player: this.name, url: this.page.url(), lastCommand: this.lastCommand,
      state: this.state && { name: this.state.name, zone: this.state.zone, hp: this.state.hp },
      revision: this.revision, sockets: this.sockets, errors: this.errors, warnings: this.warnings };
  }
}

const test = base.extend({
  actors: async ({ browser }, use, testInfo) => {
    const players = [];
    const create = async (index, viewport) => {
      const context = await browser.newContext({ viewport: viewport || { width: 1366, height: 768 } });
      const player = new Player(await context.newPage(), ...credentials[index]);
      players.push(player);
      return player.login();
    };
    try { await use({ create, credentials: credentials.map(([name]) => name) }); }
    finally {
      await testInfo.attach('observations', { body: JSON.stringify(players.map(p => p.diagnostic()), null, 2), contentType: 'application/json' });
      for (const player of players) {
        if (testInfo.status !== testInfo.expectedStatus && player.state && !player.page.isClosed()) {
          try {
            await player.page.screenshot({ path: testInfo.outputPath('failure-'+player.name+'.png'), fullPage: true, timeout: 3000 });
          } catch (error) {
            await testInfo.attach('screenshot-unavailable', { body: error.message, contentType: 'text/plain' });
          }
        }
        await player.page.context().close();
      }
    }
  },
});

function sessions() {
  return JSON.parse(execFileSync(process.env.PRIMAL_BROWSER_PYTHON,
    ['scripts/browser_probe.py'], { encoding: 'utf8', env: process.env }));
}
module.exports = { test, expect, sessions };
