import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './frontend/e2e',
  testIgnore: '**/full/**',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  workers: 2,
  reporter: 'list',
  use: {
    browserName: 'chromium',
    baseURL: 'http://127.0.0.1:15174',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 15174 --strictPort',
    url: 'http://127.0.0.1:15174',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
