// tests/e2e/seed.spec.ts
//
// The exemplar every generated E2E test in this project is modeled on — see
// .claude/skills/10x-e2e/references/seed-test-pattern.md. Four things to copy:
//   - role-based locators (getByRole / getByLabel), never CSS selectors or XPath
//   - one test = full setup -> action -> assertion -> cleanup, independently runnable
//   - wait for state (toBeVisible / toHaveURL), never page.waitForTimeout()
//   - a name that binds the test to the risk it protects, not "test 1"
//
// Risk: a saved trip is a real DB round-trip (TripForm -> TripCreateView -> DB),
// not client-side state — it must still be there after a hard reload of the page
// that actually renders it back from the database.
//
// Requires the "authenticate" setup project (auth.setup.ts) to have run first,
// so playwright/.auth/user.json exists — playwright.config.ts wires that
// dependency.

import { test, expect } from '@playwright/test';

test.use({ storageState: 'playwright/.auth/user.json' });

test('created trip persists after page reload', async ({ page }) => {
  const tripName = `Seed trip ${Date.now()}`;

  await page.goto('/trips/new/');
  await page.getByLabel('Name:').fill(tripName);
  await page.getByLabel('Date:').fill('2026-06-01');
  await page.getByLabel('Description:').fill('Created by the E2E seed test.');
  await page.getByRole('button', { name: 'Save trip' }).click();

  // TripCreateView.success_url is trips:list, not the trip's own detail page —
  // assert the real redirect target, not the one that would be convenient.
  await expect(page).toHaveURL('/trips/');
  await expect(page.getByRole('alert')).toContainText('Trip saved.');

  await page.getByRole('link', { name: tripName }).click();
  await expect(page.getByRole('heading', { name: tripName })).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading', { name: tripName })).toBeVisible();

  // Cleanup — delete via the UI so this run leaves no trip behind for the next one.
  await page.getByRole('link', { name: 'Delete trip' }).click();
  await page.getByRole('button', { name: 'Delete trip' }).click();

  await expect(page).toHaveURL('/trips/');
  await expect(page.getByRole('link', { name: tripName })).toHaveCount(0);
});
