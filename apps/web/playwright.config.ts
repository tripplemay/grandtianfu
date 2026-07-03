import { defineConfig } from '@playwright/test';

// P0 冒烟安全网 (升级计划): 真 API(沙箱数据) + next dev, 全链路页面级冒烟。
// 端口避开本地开发 (web 3100 / api 8010)。
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:3100',
    trace: 'on-first-retry',
  },
  webServer: [
    {
      command: 'bash e2e/start-api.sh',
      url: 'http://127.0.0.1:8010/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: 'yarn dev -p 3100',
      url: 'http://127.0.0.1:3100/studio/projects',
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: { API_ORIGIN: 'http://127.0.0.1:8010' },
    },
  ],
});
