import { defineConfig } from '@playwright/test';

// Grafana also defaults to 3000; set E2E_PORT to run the mocked specs while the stack is up.
const port = Number(process.env.E2E_PORT ?? 3000);

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
