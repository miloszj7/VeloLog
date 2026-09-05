// tests/e2e/auth.setup.ts
//
// Logs in once through the real UI and saves the resulting Django session as
// storageState, so every other spec starts already authenticated — see
// e2e-quality-rules.md: "Use storageState for authentication — never log in
// through UI in individual tests." Wired as the "setup" project in
// playwright.config.ts, which the "e2e" project depends on.
//
// Needs a real user in whatever database the run is pointed at — this is a
// Django session, not a mock — so E2E_USERNAME / E2E_PASSWORD must be set.

import { test as setup, expect } from '@playwright/test';

const AUTH_FILE = 'playwright/.auth/user.json';

setup('authenticate', async ({ page }) => {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) {
    throw new Error('E2E_USERNAME and E2E_PASSWORD must be set to run E2E tests.');
  }

  await page.goto('/accounts/login/');
  await page.getByLabel('Username:').fill(username);
  await page.getByLabel('Password:').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();

  await expect(page.getByRole('heading', { name: 'Your trips' })).toBeVisible();
  await page.context().storageState({ path: AUTH_FILE });
});
