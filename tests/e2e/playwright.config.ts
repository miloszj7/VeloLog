import { defineConfig, devices } from '@playwright/test';

// This project's own Playwright config — isolated from the root package.json
// (Railway IaC only, see .railway/railway.ts). `webServer` boots the Django dev
// server itself, so `npx playwright test` from this directory is self-contained
// as long as `uv` is on PATH and a real E2E user + DB already exist (see
// auth.setup.ts).

// Loads tests/e2e/.env — not the repo-root .env, which is Django's own and is
// never read by this Node process. Optional: CI sets E2E_USERNAME/E2E_PASSWORD
// directly instead of shipping a .env file.
try {
  process.loadEnvFile('.env');
} catch {
  // No .env present — fall through to whatever the shell/CI already exported.
}

export default defineConfig({
  testDir: '.',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',

  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'on-first-retry',
  },

  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'e2e',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
      testMatch: /.*\.spec\.ts/,
    },
  ],

  webServer: {
    command: 'uv run python manage.py runserver 8000',
    cwd: '../..',
    url: 'http://127.0.0.1:8000/healthz/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
