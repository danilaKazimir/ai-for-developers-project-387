import { defineConfig } from '@playwright/test';

if (!process.env.DEPLOYMENT_URL) throw new Error('DEPLOYMENT_URL is required');
export default defineConfig({
  testDir: './frontend/e2e/full',
  testMatch: 'bookings.spec.ts',
  workers: 1,
  use: { baseURL: process.env.DEPLOYMENT_URL, browserName: 'chromium' },
});
