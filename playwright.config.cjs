const { defineConfig } = require('@playwright/test');
const path = require('node:path');
if (!process.env.PRIMAL_BROWSER_URL || !process.env.PRIMAL_BROWSER_RESULTS) {
  throw new Error('npm run test:browser의 격리 서버 실행기를 사용하세요.');
}
module.exports = defineConfig({
  testDir: './scripts/browser',
  testMatch: process.env.PRIMAL_BROWSER_SCENARIO ? 'integration.spec.cjs' : 'phase50a.spec.cjs',
  workers: 1,
  retries: 0,
  // 로컬 음성 검사는 의도된 실패 하나만 실행한다. 기본/CI 수용 검사는 모두 유지한다.
  grep: process.env.PRIMAL_BROWSER_SCENARIO ? new RegExp('TEST-' + process.env.PRIMAL_BROWSER_SCENARIO + ' ') :
    (process.env.PRIMAL_BROWSER_FAILURE_PROBE === '1' ? /TEST-P2-02-D / : undefined),
  timeout: process.env.PRIMAL_BROWSER_SCENARIO?.startsWith('TIMING-') ? 750000 :
    (process.env.PRIMAL_BROWSER_SCENARIO ? 240000 : 45000),
  expect: { timeout: 15000 },
  outputDir: path.join(process.env.PRIMAL_BROWSER_RESULTS, 'screenshots'),
  reporter: [['./scripts/browser/reporter.cjs']],
  use: {
    browserName: 'chromium', channel: 'chromium',
    baseURL: process.env.PRIMAL_BROWSER_URL,
    viewport: { width: 1366, height: 768 },
    trace: 'off', video: 'off', screenshot: 'off',
  },
});
