---
date: 2026-09-05T00:00:00+02:00
researcher: Claude (10x-research)
git_commit: 1a2b5ffbc29740c6cd0b4d0531de6820d6821c95
branch: test/e2e-seed-playwright
repository: VeloLog
topic: "Refresh test-plan.md for now-available Playwright e2e layer"
tags: [research, codebase, test-plan, e2e, playwright, gpx-upload, risk-1, risk-6]
status: complete
last_updated: 2026-09-05
last_updated_by: Claude (10x-research)
---

# Research: Refresh test-plan.md for now-available Playwright e2e layer

**Date**: 2026-09-05T00:00:00+02:00
**Researcher**: Claude (10x-research)
**Git Commit**: 1a2b5ffbc29740c6cd0b4d0531de6820d6821c95
**Branch**: test/e2e-seed-playwright
**Repository**: VeloLog

## Research Question

`context/foundation/test-plan.md` was written (2026-08-29) when "Playwright MCP —
not available in current session" and no rollout phase proposed e2e. Commit
`1a2b5ff` (2026-09-05) landed a working, isolated Playwright layer under
`tests/e2e/`. What does the current e2e infra actually look like, and what needs
to change in test-plan.md §2, §4, §5 to reflect it — without promoting e2e to a
required gate or contradicting the plan's own cost×signal principle?

## Summary

The e2e layer is real, working, and narrowly scoped: one isolated npm project
(`tests/e2e/`, its own `package.json`/`package-lock.json`, separate from the
root Railway-IaC `package.json`), Playwright `^1.55.1`, a `storageState`-based
`auth.setup.ts` that logs in once through the real UI, and a `webServer` block
that boots `uv run python manage.py runserver 8000` against `/healthz/` before
tests run. Two spec files exist: `seed.spec.ts` (committed, trip-creation
persistence-after-reload) and `gpx-upload.spec.ts` (**currently untracked** —
still a working-tree draft, not yet committed) that exercises exactly the gap
change.md names: a real `<input type="file">` round trip through
`GpxUploadForm.clean_file` into rendered stage/stats DOM, surviving a hard
reload.

The e2e layer is not wired into CI anywhere — `.github/workflows/deploy.yml`
has zero references to `e2e`/`playwright`, confirming it stays a local/manual
layer, consistent with the change's "not a required CI gate" instruction.
`context/foundation/engineering-backlog.md` documents the root-level
`package.json` as IaC-only and explicitly scoped away from testing, so the two
Node footprints (root IaC, `tests/e2e/`) are already an established, intentional
split — nothing to reconcile.

## Detailed Findings

### e2e infra shape (commit 1a2b5ff)

- `tests/e2e/package.json` — name `velolog-e2e`, `"private": true`,
  `devDependencies: { "@playwright/test": "^1.55.1" }`, single `test` script
  (`playwright test`). Explicitly documented in its own `description` field as
  isolated from the root `package.json` (Railway IaC only).
- `tests/e2e/playwright.config.ts` — `testDir: '.'`, `fullyParallel: true`,
  two projects: `setup` (matches `auth.setup.ts`) and `e2e` (matches
  `*.spec.ts`, `dependencies: ['setup']`, Desktop Chrome only). `webServer`
  runs `uv run python manage.py runserver 8000` with `cwd: '../..'` (repo
  root), health-checked at `/healthz/`, `reuseExistingServer: !process.env.CI`.
  Loads `tests/e2e/.env` via `process.loadEnvFile('.env')` (Node's own env
  loader, not Django's — the repo-root `.env` is never read by this process).
- `tests/e2e/auth.setup.ts` — logs in through the real UI
  (`/accounts/login/`, `getByLabel('Username:')`/`getByLabel('Password:')`,
  `getByRole('button', { name: 'Log in' })`), asserts the post-login "Your
  trips" heading, then persists `page.context().storageState()` to
  `playwright/.auth/user.json`. Requires `E2E_USERNAME`/`E2E_PASSWORD` env
  vars — throws immediately if unset. Needs a **real Django user already
  existing** in whatever DB the run targets; this is a session, not a mock.
- `tests/e2e/.env.example` — template for the two required env vars, states
  "Any account works — no admin/staff rights needed."
- `.gitignore` (added in the same commit) — ignores
  `/tests/e2e/test-results/`, `/tests/e2e/playwright-report/`,
  `/tests/e2e/playwright/.auth/` (run artifacts and the storageState file,
  not source).
- `tests/e2e/seed.spec.ts` (committed) — `created trip persists after page
  reload`. Uses `test.use({ storageState: 'playwright/.auth/user.json' })`.
  Creates a trip via the real `/trips/new/` form, asserts the redirect target
  is `trips:list` (not the trip's own detail page — a documented gotcha:
  `TripCreateView.success_url` points at the list), navigates to the trip,
  reloads, re-asserts the heading, then deletes via the UI for cleanup and
  asserts the link is gone (`toHaveCount(0)`). Verified red when persistence
  was deliberately broken (per the commit message).
- `tests/e2e/gpx-upload.spec.ts` — **untracked in git status**, i.e. a
  working-tree file not yet committed on this branch. Test name: `an
  uploaded GPX stage renders its computed stats and persists after reload`.
  Creates a trip, uploads `../gpx/fixtures/timed-track.gpx` via
  `getByLabel('GPX file:').setInputFiles(fixture)`, asserts the `Stage
  added.` alert and `Stage 1` heading, drills into per-stage details, and
  pins `1 h 00 min` as "the sturdiest real (not placeholder) stat" from a
  fixture with three timestamped points spanning exactly 3600s — a
  deliberate choice to avoid asserting a distance/elevation value whose
  exact rounding could drift. Reloads and re-asserts, then cleans up via
  the UI. Its own header comment explicitly frames the risk it closes: "A
  Django test-client `SimpleUploadedFile` exercises the parse/store path but
  never the real browser file-picker widget or the real multipart
  encoding; this is the one layer that does."

### What this e2e layer covers that integration tests structurally cannot

`GpxUploadForm.clean_file` (`gpx/forms.py:36-91`) is the validation/parse
entry point every GPX upload passes through — size check, extension check,
then `parse_gpx_bytes` via `gpxpy`, with specific `ValidationError` messages
per failure mode (`GpxEncodingError`, `GpxSyntaxError`,
`GpxTooManyPointsError`, `GpxContentError`), and a `finally` rewind so the
storage write persists all bytes. Every existing integration test reaches
this method through Django's test client, which builds the multipart
request programmatically (`SimpleUploadedFile`) — it never drives an actual
`<input type="file">` widget, never goes through a browser's real multipart
encoding, and never round-trips through a page reload to prove the
rendered stage/stats DOM survived. `gpx-upload.spec.ts` is the one test in
the repo that does all three, which matches change.md's framing precisely:
"the one thing neither the Django test client nor an integration test
reaches."

### CI wiring — confirmed absent

`grep -i 'e2e\|playwright'` against `.github/workflows/deploy.yml` returns
zero matches. The `gates` job (vendored-asset integrity → lint/format/isort
→ mypy → `manage.py check` → migration guard → `collectstatic` → `pytest
--cov` → `pytest -m bite_proof`) has no e2e step, and the Railway deploy job
only runs after `gates` passes. This confirms the e2e layer is currently a
local/manual-only layer — nothing in CI would need to change to keep it
that way, and test-plan.md's forthcoming "narrow slice only" framing for §5
matches the codebase as it stands, not just as intended.

### Root-level `package.json` vs `tests/e2e/package.json` — already reconciled

`context/foundation/engineering-backlog.md:69-73` documents the root
`package.json`/`package-lock.json` as added solely to evaluate
`.railway/railway.ts` (Railway's IaC SDK), explicitly scoped to IaC only.
`tests/e2e/package.json`'s own description field cross-references this same
split ("isolated from the root package.json, which is Railway IaC only").
Both files independently state the boundary — no naming collision or
scope-creep risk for the plan to flag.

### Historical/context grep for prior e2e discussion

Searched `context/**` for `e2e`/`playwright` (case-insensitive). Every hit
predating this branch is exactly the test-plan.md content already read
(§4's "Playwright MCP — not available" line, §5's "not planned" row) plus
its own drafting artifacts (`plan.md`, `plan-brief.md`, `impl-review.md`
under `2026-08-29-testing-data-isolation-contract` and
`2026-08-31-testing-gate-credibility`) — these only mention e2e in the
context of *deciding not to pursue it yet*, consistent with the "no e2e
phase was proposed" state test-plan.md itself records. No prior change
folder proposed or scoped an e2e layer; this is the first.

## Code References

- `tests/e2e/package.json` - isolated npm project, `@playwright/test ^1.55.1`
- `tests/e2e/playwright.config.ts:18-47` - config: `testDir`, two-project
  `setup`→`e2e` dependency, `webServer` boots `manage.py runserver` against
  `/healthz/`
- `tests/e2e/auth.setup.ts:16-30` - storageState auth setup, real UI login,
  requires `E2E_USERNAME`/`E2E_PASSWORD` and a real pre-existing user
- `tests/e2e/seed.spec.ts:22-48` - trip-creation persistence-after-reload
  seed test
- `tests/e2e/gpx-upload.spec.ts:19-59` - GPX upload → stage/stats render →
  reload persistence (untracked, not yet committed)
- `gpx/forms.py:36-91` - `GpxUploadForm.clean_file`, the parse/validation
  entry point the e2e test round-trips through a real file-input widget
- `.gitignore` (new in commit `1a2b5ff`) - ignores e2e run artifacts and
  storageState, not source
- `.github/workflows/deploy.yml` - no e2e/playwright reference; `gates` job
  ends at `pytest -m bite_proof`
- `context/foundation/engineering-backlog.md:69-73` - root `package.json`
  scoped to Railway IaC only, the existing precedent for a second,
  differently-scoped Node footprint

## Architecture Insights

- **Two independent Node footprints, two independent purposes, already
  self-documented.** Root `package.json` (IaC evaluation) and
  `tests/e2e/package.json` (browser tests) each state their own scope in
  their own `description` field — the plan's Stack section (§4) can record
  the e2e row without needing to reconcile or cross-reference the IaC one.
- **The e2e layer's only external dependencies are `uv` on `PATH` and a
  pre-existing real user + DB** — no fixture/factory seeds the E2E user;
  `auth.setup.ts` fails loudly (`throw new Error(...)`) if the env vars are
  unset, and login itself will fail if the account doesn't exist. This is a
  manual-setup cost the plan should probably note under Stack, since it's
  the reason this can't just be dropped into CI without also provisioning
  a seeded database.
- **`gpx-upload.spec.ts` is uncommitted.** Test-plan.md should describe the
  e2e *layer* and its pattern (webServer, storageState, isolated package),
  not hard-pin an uncommitted spec file as delivered — the committed anchor
  is `seed.spec.ts`; `gpx-upload.spec.ts` is the concrete evidence that the
  pattern extends to Risk #1/#6 but is not yet landed history the way
  `1a2b5ff` is.
- **No CI gate exists to demote** — §5's e2e row can move straight from "not
  planned" to "narrow slice only, not a required CI gate" without touching
  `deploy.yml`, because nothing there currently references it.

## Historical Context (from prior changes)

- No prior `context/changes/**` or `context/archive/**` folder proposed an
  e2e rollout phase. Every existing mention of e2e/Playwright in `context/`
  predates this branch and only records the *absence* of a Playwright MCP
  session and the resulting decision not to add an e2e phase
  (`test-plan.md` §4, §5 as originally written; echoed in the Phase-1 and
  Phase-5 planning docs under `context/archive/`).
- `context/foundation/engineering-backlog.md:69-73` — the Railway IaC
  `package.json` decision, useful precedent for framing the e2e npm
  project as a second, deliberately separate Node footprint rather than
  something needing consolidation.

## Related Research

- None — this is the first research artifact referencing the e2e layer.

## Open Questions

- Should test-plan.md's Stack row note that `gpx-upload.spec.ts` is
  currently uncommitted, or should this refresh land after (or alongside)
  that file's own commit? The plan text itself doesn't need to block on
  this, but whoever writes §2/§4 should decide whether to cite
  `gpx-upload.spec.ts` as "the additional protection layer" only once it's
  committed, to avoid the plan referencing a file that isn't yet part of
  history.
- Does the e2e layer need a documented manual runbook (README under
  `tests/e2e/`) for provisioning the required real user, or does
  `auth.setup.ts` + `.env.example`'s comments already count as sufficient
  documentation? Not blocking for this refresh, but worth a follow-up
  `10x-lesson` entry if a future contributor gets stuck on it.
