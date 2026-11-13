import { defineConfig } from '@playwright/test';
import fast from './playwright.config';

export default defineConfig(fast, {
  testMatch: '**/full/**/*.spec.ts',
  testIgnore: [],
  workers: 1,
  use: { ...fast.use, baseURL: 'http://127.0.0.1:15175' },
  webServer: [
    { command: 'mise exec -- node scripts/e2e-api.mjs', url: 'http://127.0.0.1:18001/api/health', timeout: 30_000 },
    { command: 'npm run dev -- --host 127.0.0.1 --port 15175 --strictPort', url: 'http://127.0.0.1:15175', env: { API_PROXY_TARGET: 'http://127.0.0.1:18001' }, timeout: 30_000 },
  ],
});
