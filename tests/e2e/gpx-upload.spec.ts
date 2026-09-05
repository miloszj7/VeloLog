// tests/e2e/gpx-upload.spec.ts
//
// Risk (context/foundation/test-plan.md #1 + #6): a GPX upload is a real multipart
// file round trip (browser <input type="file"> -> GpxUploadForm.clean_file -> gpxpy
// parse -> DB columns), and the trip detail page must render the parsed stage and its
// computed statistics back from those stored columns — not from anything client-side.
// A Django test-client SimpleUploadedFile exercises the parse/store path but never the
// real browser file-picker widget or the real multipart encoding; this is the one layer
// that does.
//
// Modeled on seed.spec.ts: role-based locators, one self-contained test, wait for
// state, unique trip name, cleanup via the UI.

import path from 'node:path';
import { test, expect } from '@playwright/test';

test.use({ storageState: 'playwright/.auth/user.json' });

test('an uploaded GPX stage renders its computed stats and persists after reload', async ({
  page,
}) => {
  const tripName = `GPX upload trip ${Date.now()}`;
  const fixture = path.resolve(__dirname, '../gpx/fixtures/timed-track.gpx');

  await page.goto('/trips/new/');
  await page.getByLabel('Name:').fill(tripName);
  await page.getByLabel('Date:').fill('2026-06-01');
  await page.getByLabel('Description:').fill('Created by the GPX upload E2E test.');
  await page.getByRole('button', { name: 'Save trip' }).click();

  await expect(page).toHaveURL('/trips/');
  await page.getByRole('link', { name: tripName }).click();
  await expect(page.getByRole('heading', { name: tripName })).toBeVisible();

  await page.getByLabel('GPX file:').setInputFiles(fixture);
  await page.getByRole('button', { name: 'Add GPX file' }).click();

  await expect(page.getByRole('alert')).toContainText('Stage added.');

  // Per-stage detail is collapsed by default (trip_detail.html) — the stage
  // heading and its own stats only exist in the accessibility tree once expanded.
  await page.getByRole('button', { name: 'Show per-stage details' }).click();
  await expect(page.getByRole('heading', { name: 'Stage 1', exact: false })).toBeVisible();

  // The parsed file carries three timestamped points 08:00 -> 09:00 UTC, a fixed
  // 3600s span — deterministic regardless of the distance/elevation formula's exact
  // rounding, so it is the sturdiest real (not placeholder) stat to pin here. With a
  // single-stage trip the whole-trip totals show the identical figure, so two
  // matches (totals + per-stage) is the correct count, not one.
  await expect(page.getByText('1 h 00 min')).toHaveCount(2);
  await expect(page.getByText('Not recorded', { exact: false })).toHaveCount(0);

  await page.reload();
  await page.getByRole('button', { name: 'Show per-stage details' }).click();
  await expect(page.getByRole('heading', { name: 'Stage 1', exact: false })).toBeVisible();
  await expect(page.getByText('1 h 00 min')).toHaveCount(2);

  // Cleanup — delete the trip via the UI so this run leaves nothing behind.
  await page.getByRole('link', { name: 'Delete trip' }).click();
  await page.getByRole('button', { name: 'Delete trip' }).click();

  await expect(page).toHaveURL('/trips/');
  await expect(page.getByRole('link', { name: tripName })).toHaveCount(0);
});
