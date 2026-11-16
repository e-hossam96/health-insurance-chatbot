import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-stack',
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.STACK_URL ?? 'http://localhost',
    headless: true,
    timezoneId: 'America/New_York',
  },
});
