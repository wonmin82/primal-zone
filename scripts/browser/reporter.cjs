const fs = require('node:fs');
const path = require('node:path');
const { safeObservation } = require('./safety.cjs');

// Playwright의 오류/소스/호출 인자/stdout는 자유 입력을 포함할 수 있어 보고하지 않는다.
class SafeReporter {
  constructor() { this.tests = []; this.screenshots = []; this.errors = 0; }
  onError() { this.errors++; }
  onTestEnd(test, result) {
    const id = test.title.match(/^TEST-[A-Z0-9-]+/)?.[0] || 'unknown';
    const statuses = ['passed', 'failed', 'timedOut', 'skipped', 'interrupted'];
    const stages = ['browser-console-failed', 'context-close-failed', 'websocket-close: timeout', 'puppet-detach: timeout', 'puppet-detach: probe-failed', 'puppet-login: timeout', 'puppet-login: probe-failed', 'observations: attach-failed'];
    const entry = { id, status: statuses.includes(result.status) ? result.status : 'failed', seconds: result.duration / 1000, errors: result.errors.length,
      failureStages: [...new Set(result.errors.flatMap(error => {
        const found = stages.filter(stage => String(error.message).includes(stage));
        return found.length ? found : ['test-failure'];
      }))], evidenceCleanupFailed: false, observations: [] };
    for (const attachment of result.attachments) {
      // Playwright 자체 오류 context는 source/인자/DOM을 담을 수 있어 보존하지 않는다.
      if (attachment.name === 'error-context' && attachment.path) {
        const root = path.resolve(process.env.PRIMAL_BROWSER_RESULTS, 'screenshots');
        const relative = path.relative(root, attachment.path);
        if (!relative.startsWith('..') && !path.isAbsolute(relative) && path.basename(attachment.path) === 'error-context.md') {
          try { fs.unlinkSync(attachment.path); } catch { this.errors++; entry.errors++; entry.evidenceCleanupFailed = true; }
        } else { this.errors++; entry.errors++; entry.evidenceCleanupFailed = true; }
      }
      if (attachment.name === 'observations' && attachment.body) {
        try { entry.observations.push(...JSON.parse(attachment.body.toString()).map(safeObservation)); }
        catch { entry.errors++; }
      }
      if (attachment.name === 'chromium-version' && attachment.body && /^\d+(\.\d+){3}$/.test(attachment.body.toString())) entry.chromium = attachment.body.toString();
      if (id === 'TEST-50A-06' && /^safe-viewport-(1366|1280|390)$/.test(attachment.name) && attachment.path) {
        const root = path.resolve(process.env.PRIMAL_BROWSER_RESULTS, 'screenshots');
        const relative = path.relative(root, attachment.path);
        if (!relative.startsWith('..') && !path.isAbsolute(relative)) this.screenshots.push({ source: relative, name: attachment.name + '.png' });
      }
    }
    if (entry.evidenceCleanupFailed) { entry.status = 'failed'; entry.failureStages.push('evidence-cleanup-failed'); }
    this.tests.push(entry);
    process.stdout.write(`${id}: ${entry.status} (${entry.seconds.toFixed(3)}s)\n`);
    // 자유 입력/오류 본문 대신 실패한 테스트의 숫자 행만 로컬 진단에 남긴다.
    for (const error of result.errors) {
      const locations = String(error.stack || '').match(/integration(?:-helpers)?\.spec\.cjs:\d+:\d+/g) || [];
      for (const location of locations) process.stdout.write(`failure-location: ${location}\n`);
    }
    for (const chunk of result.stderr || []) {
      for (const line of String(chunk).split('\n')) {
        if (/^route-boundary: [a-z0-9_]+->[a-z0-9_]+; observed=[a-z0-9_]+$/.test(line)) process.stdout.write(line + '\n');
      }
    }
  }
  onEnd(result) {
    fs.writeFileSync(path.join(process.env.PRIMAL_BROWSER_RESULTS, 'results.json'), JSON.stringify({ status: this.errors ? 'failed' : (['passed', 'failed', 'timedout', 'interrupted'].includes(result.status) ? result.status : 'failed'), errors: this.errors, tests: this.tests, screenshots: this.screenshots }, null, 2));
  }
  printsToStdio() { return true; }
}
module.exports = SafeReporter;
