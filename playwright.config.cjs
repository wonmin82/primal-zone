const { defineConfig } = require('@playwright/test');
const path = require('node:path');
if (!process.env.PRIMAL_BROWSER_URL || !process.env.PRIMAL_BROWSER_RESULTS) {
  throw new Error('npm run test:browser의 격리 서버 실행기를 사용하세요.');
}
module.exports = defineConfig({
  testDir: './scripts/browser',
  testMatch: '*.spec.cjs',
  workers: 1,
  retries: 0,
  timeout: 45000,
  expect: { timeout: 15000 },
  outputDir: path.join(process.env.PRIMAL_BROWSER_RESULTS, 'screenshots'),
  reporter: [
    ['list'],
    ['json', { outputFile: path.join(process.env.PRIMAL_BROWSER_RESULTS, 'results.json') }],
  ],
  use: {
    browserName: 'chromium', channel: 'chromium',
    baseURL: process.env.PRIMAL_BROWSER_URL,
    viewport: { width: 1366, height: 768 },
    trace: 'off', video: 'off', screenshot: 'off',
  },
});
