import { defineConfig } from '@playwright/test';

// not 3000: reuseExistingServer would silently test the stack's Grafana instead of the dev server
const port = Number(process.env.E2E_PORT ?? 5199);

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: `http://localhost:${port}`,
    headless: true,
    timezoneId: 'America/New_York',
  },
  webServer: {
    command: `npm run dev -- --port ${port} --strictPort`,
    port,
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
