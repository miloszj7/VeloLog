// tests/e2e/gpx-rejection.spec.ts
//
// Risk (context/foundation/test-plan.md #5): a malformed or hostile upload must return
// a clean rejection, never a server error — and the debris question (row/file left
// behind) is separately covered by tests/gpx/test_gpx_upload.py's storage-emptiness
// assertions, which a browser cannot observe. What only a real browser proves is that
// an actual <input type="file"> submission of a hostile payload — here, an XXE-style
// DOCTYPE with an external-entity declaration, real bytes real-multipart-encoded, not
// Django test client's SimpleUploadedFile — reaches the same clean GpxUploadForm
// rejection path and the app keeps rendering, rather than a crash page or a leak.
//
// Modeled on gpx-upload.spec.ts: role-based locators, one self-contained test, wait
// for state, unique trip name, cleanup via the UI.

import path from 'node:path';
import { test, expect } from '@playwright/test';

test.use({ storageState: 'playwright/.auth/user.json' });

test('a hostile XXE-style GPX upload is cleanly rejected, not a server error', async ({
  page,
}) => {
  const tripName = `GPX rejection trip ${Date.now()}`;
  const fixture = path.resolve(__dirname, '../gpx/fixtures/xxe.gpx');

  await page.goto('/trips/new/');
  await page.getByLabel('Name:').fill(tripName);
  await page.getByLabel('Date:').fill('2026-06-01');
  await page.getByLabel('Description:').fill('Created by the GPX rejection E2E test.');
  await page.getByRole('button', { name: 'Save trip' }).click();

  await expect(page).toHaveURL('/trips/');
  await page.getByRole('link', { name: tripName }).click();
  await expect(page.getByRole('heading', { name: tripName })).toBeVisible();

  await page.getByLabel('GPX file:').setInputFiles(fixture);
  await page.getByRole('button', { name: 'Add GPX file' }).click();

  // GpxUploadView.form_invalid re-renders trip_detail.html at 200, at the upload
  // POST's own URL — never a redirect back to the trip page, never a 500/debug page.
  // gpx/forms.py's clean_file rejects a DOCTYPE-carrying file inside the
  // GpxSyntaxError branch with this exact message.
  await expect(page).toHaveURL(/\/gpx\/trips\/\d+\/upload\/$/);
  await expect(page.getByText('That file could not be read as XML.')).toBeVisible();

  // Nothing was added: the page still shows the no-route empty state and the
  // trip-totals section, gated on `stages`, never rendered.
  await expect(
    page.getByText('No route yet', { exact: false })
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Trip totals' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Stage 1', exact: false })).toHaveCount(0);

  // Cleanup — delete the trip via the UI so this run leaves nothing behind.
  await page.getByRole('link', { name: 'Delete trip' }).click();
  await page.getByRole('button', { name: 'Delete trip' }).click();

  await expect(page).toHaveURL('/trips/');
  await expect(page.getByRole('link', { name: tripName })).toHaveCount(0);
});
