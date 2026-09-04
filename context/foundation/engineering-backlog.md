---
project: VeloLog
updated: 2026-09-04
---

# Engineering Backlog: VeloLog

Non-feature engineering debt, distinct from `roadmap.md`'s `## Parked` (which holds
deliberately deferred PRD scope). Each item's trigger names the condition that makes
the fix due — nothing here is picked up until its trigger fires. The table below is
the index; full context for each item is in `### Details`.

Edit-in-place per `README.md`'s convention — this file lives alongside `roadmap.md`
as a foundation doc, split out so the roadmap holds only milestones and slices.

## At a glance — To Do

| ID   | Item                                                    | Trigger                                                        | Status      |
| ---- | -------------------------------------------------------- | ----------------------------------------------------------------- | ----------- |
| E-07 | `$5` Railway spend alert un-reverified                     | After free trial expires (23 days from 2026-08-28)                 | **blocked** (on free trial) |

## At a glance — Done

| ID   | Item                                                                | Status               | GitHub Issue |
| ---- | ---------------------------------------------------------------------- | --------------------- | ------------ |
| E-03 | Tracker statuses never sync back from GitHub/Linear                 | done (2026-08-31)      | — |
| E-01 | CI ran no tests/lint/type checks before merge                           | done                   | [#7](https://github.com/miloszj7/VeloLog/issues/7) |
| E-02 | `gates` was not a required branch-protection check                      | done (2026-08-28)      | [#19](https://github.com/miloszj7/VeloLog/issues/19) |
| E-05 | DB/media restore path had never been exercised                          | done (2026-08-26)      | — |
| E-06 | No structured logging or error tracking                                 | done (2026-08-26)      | [#12](https://github.com/miloszj7/VeloLog/issues/12) |
| E-08 | `TripForm` accepted a future-dated trip with no validation               | done (2026-08-27)      | — |
| E-09 | CI actions pinned to deprecated Node 20 runtime                         | done (2026-08-28)      | [#20](https://github.com/miloszj7/VeloLog/issues/20) |
| E-11 | GPX upload orphans its file in storage on transaction rollback          | done (2026-08-28)      | [#23](https://github.com/miloszj7/VeloLog/issues/23) |
| E-10 | `Trip.date` is a single field on a multi-day product                    | done (2026-09-02) — closed as unnecessary | — |
| E-04 | `railway.json` must migrate to `.railway/railway.ts`                    | done (2026-09-04)      | [#22](https://github.com/miloszj7/VeloLog/issues/22) |

## Details

#### E-01 — CI ran no tests/lint/type checks before merge

- **Item:** CI runs no tests, ruff, black, isort, or mypy — only `manage.py check` plus the migration guard S-02 added, and only on push to `master`.
- **Proposed fix:** Add a `pull_request` trigger and a job running `uv run pytest --cov` plus the lint/type gates, before the `railway up` step.
- **Trigger:** Before S-03 — the north star slice adds file upload and map rendering, where a silent regression is most costly.
- **Change ID:** `ci-quality-gates`
- **Status:** done
- **GitHub Issue:** [#7](https://github.com/miloszj7/VeloLog/issues/7)

#### E-02 — `gates` was not a required branch-protection check

- **Item:** `gates` is not a required check — a merge can still be forced past a red run.
- **Proposed fix:** Enable branch protection on `master` requiring the `gates` check.
- **Trigger:** Immediately after `ci-quality-gates` merges.
- **Status:** done (2026-08-28)
- **GitHub Issue:** [#19](https://github.com/miloszj7/VeloLog/issues/19) — set via the API rather than the UI, so the exact ruleset is reviewable: `gates` required, `strict` on (a branch must be current with `master` before merging — which the rebase-before-merge rule already demanded), and `enforce_admins` on, since the row's whole complaint is that a red run *can* be forced past and the sole admin is who would force it. `required_linear_history` is deliberately **off**: it rejects merge commits, and `--no-ff` is the mandated merge strategy. Direct pushes to `master` are now refused; merges land through the PR button, which is what the history already shows.

#### E-03 — Tracker statuses never sync back from GitHub/Linear

- **Item:** Tracker statuses never propagate — GitHub and Linear migrations are documented as one-way with no sync back.
- **Proposed fix:** Decide whether trackers are authoritative or decorative, and either close them out per slice or note in the roadmap that they are a point-in-time snapshot.
- **Trigger:** Before the next roadmap regeneration.
- **Status:** done (2026-08-31) — Linear mirror retired; GitHub Issues is now the single source of truth. Manual sync adopted (Option A): when a GitHub issue with the `roadmap` label is closed, update `roadmap.md`'s `Status` field by hand. Automation rejected as overkill for a 5-issue roadmap.
- **GitHub Issue:** —

#### E-04 — `railway.json` must migrate to `.railway/railway.ts`

- **Item:** `railway.json` must migrate to `.railway/railway.ts` before 2026-12-01.
- **Proposed fix:** Convert the start command to the TypeScript config format.
- **Trigger:** By 2026-11-01, after the 2026-09-10 product deadline.
- **Status:** done (2026-09-04) — `railway config migrate --apply` (the CLI's own converter, not hand-written) produced `.railway/railway.ts`, which `railway.json` is replaced by. Requires the `railway` npm package (the TypeScript IaC SDK, distinct from the `@railway/cli` binary) as a devDependency to evaluate the file locally — added via a new root `package.json`/`package-lock.json`, the project's first Node footprint, scoped in its description to IaC only. `node_modules/` is gitignored.
  - **Windows `execFileSync` bug, worked around.** `railway config plan`/`apply`/`pull` initially failed on this machine with a misleading "requires Railway CLI 5.42.1 or newer" error regardless of CLI version — root cause is upstream, tracked at [railwayapp/railway-ts-sdk#77](https://github.com/railwayapp/railway-ts-sdk/issues/77): the SDK's version probe shells out via `execFileSync(process.env._ || "railway", ["--version"])` with no `shell: true`, which can't resolve the npm `railway.cmd` shim on Windows, and separately `_` is a POSIX-only shell convention that Git Bash itself keeps re-clobbering to the currently-executing command's own path (its own `_` bookkeeping runs *after* any manual `export _=...` or `env _=... cmd` prefix, since each new command bash execs resets `_` again before handoff). The fix: invoke the real bundled binary directly by its absolute path (`.../npm/node_modules/@railway/cli/bin/railway.exe`) instead of through the `railway` shim — bash then sets `_` to that same resolved path as an inherent side effect of running it, which happens to be exactly the value the SDK needs, no manual `_` juggling required.
  - **Incident: `config migrate --apply` broke production, twice.** That command clears the service's legacy Config File pointer as a side effect, which also cleared its Custom Start Command — confirmed via the deploy log of the merge-triggered CI run (PR #48, run `33916184779`): `railway up` doesn't read `.railway/railway.ts` at all (contrary to legacy `railway.json`'s auto-read-per-deploy behavior), so with no start command configured it fell back to Railpack's auto-detected default (`python manage.py migrate && gunicorn ... velo_log.wsgi:application` — no `collectstatic`, no `uv run`), which 500'd. A first manual dashboard fix, made and confirmed *before* the merge, evidently never actually persisted (the same fallback command still ran after merge); a second manual fix plus a dashboard-triggered redeploy (deployment `55137c9f-e175-4e61-a1d1-3ee2ed73886b`, logged in `DEPLOY.md`) restored service. **`railway up` is not IaC-aware** — until someone deliberately runs `config apply`, the Railway dashboard's Custom Start Command is the sole source of truth for what actually deploys, independent of `.railway/railway.ts`'s contents.
  - **`.railway/railway.ts` rebuilt from live state, verified safe.** The file `migrate --apply` originally generated only declared `start` — a deliberate "last resort for a per-service repo" per its own comment — omitting environment variables, the GitHub source link, and the volume mount entirely. Running `railway config plan` for real (via the `.exe`-path workaround) against that original file showed **`0 to add, 3 to change, 7 to destroy`**: every env var (including `SECRET_KEY` and `MEDIA_ROOT`) deleted, the GitHub source unlinked, and the persistent volume detached — because IaC treats anything undeclared in the file as "should not exist." Nobody ran `apply` against that version, so production was never actually hit by this, but it was merged to `master` in that state. Replaced via `railway config pull --force`, which reimports the live project (env vars as `preserve()`, `source: github(...)`, `volumeMounts`, `networking`) and now round-trips: `railway config plan` reports "Your Railway configuration is already up to date" — zero pending changes.
  - **Follow-up still open:** `railway config apply` has still never been run against this project — the corrected file matches live state by construction (via `pull`), not because `apply` reconciled it. The dashboard-set start command remains the actual authority for deploys; `.railway/railway.ts` stays inert scaffolding until someone deliberately runs `apply` to put the live service under real IaC management. Re-run `railway config plan` after any manual dashboard change to keep the file from drifting.
- **GitHub Issue:** [#22](https://github.com/miloszj7/VeloLog/issues/22)

#### E-05 — DB/media restore path had never been exercised

- **Item:** The `/data/db.sqlite3` restore path has never been exercised.
- **Proposed fix:** Restore a backup into a scratch environment once, to prove the runbook.
- **Trigger:** Before the deploy following S-03, once real user data exists.
- **Status:** done (2026-08-26) — drilled against production rather than a scratch environment, production held only test data, the cheapest this would ever be. Found **three** runbook defects, all corrected in `DEPLOY.md` → *Restore drill*: the documented DB restore was refused outright without `--overwrite`, and the documented media restore reported success while nesting the backup and recovering nothing. The scratch-target path still does not exist and is now the open remainder — see the note at the end of that section.
- **GitHub Issue:** —

#### E-06 — No structured logging or error tracking

- **Item:** No structured logging or error tracking — `/healthz/` is the whole observability story.
- **Proposed fix:** Introduce `LOGGING` config; a trips view 500ing in production is diagnosed only via `railway logs`. The dict must include a `velo_log` logger and a formatter that emits the `media_root` extra — `/healthz/` reports failures through logging alone, and its misconfigured-path detail is passed via `extra`, which `logging.lastResort` drops. See the Logging note in `velo_log/settings.py`.
- **Trigger:** When the first production incident is diagnosed by guesswork.
- **Change ID:** `logging-config`
- **Status:** done (2026-08-26)
- **GitHub Issue:** [#12](https://github.com/miloszj7/VeloLog/issues/12) (closed)

#### E-07 — `$5` Railway spend alert un-reverified

- **Item:** The `$5` Railway spend alert is flagged un-reverified (`DEPLOY.md:43`).
- **Proposed fix:** Re-confirm the alert fires.
- **Trigger:** After free trial expires (23 days from 2026-08-28) and paid plan begins.
- **Status:** **blocked** (on free trial — cannot verify until paid plan is active)
- **GitHub Issue:** —

#### E-08 — `TripForm` accepted a future-dated trip with no validation

- **Item:** `TripForm` accepts a future-dated trip with no validation (found during S-02 Phase 3 manual verification).
- **Proposed fix:** Decide product intent (block future dates? allow and label as "planned"?) then add `clean_date()` if blocking is the answer.
- **Trigger:** When trip-date semantics are next revisited, e.g. alongside S-03/S-04.
- **Change ID:** `edit-and-delete-trip`
- **Status:** done (2026-08-27) — product intent was never actually open: E-08's "allow and label as 'planned'" branch is excluded by a named PRD Non-Goal (*"not a planner"*), and the owner confirmed usage is "always after riding" — so blocking was the only live option. See `context/changes/edit-and-delete-trip/frame.md`. The rule allows **one day** of slack, which is a timezone correction rather than a fudge: `TIME_ZONE = "UTC"` makes `timezone.localdate()` the UTC date while the `type="date"` widget submits the rider's local one, so a rider east of UTC filing a ride just after midnight is legitimately a day ahead. It is also skipped when the date is unchanged, so a trip already stored with a future date stays editable. The `date` field now carries help text saying it is the day the ride happened — the semantic gap the frame brief found underneath E-08.
- **GitHub Issue:** —

#### E-09 — CI actions pinned to deprecated Node 20 runtime

- **Item:** `.github/workflows/deploy.yml` pins `actions/checkout@v4` and `astral-sh/setup-uv@v3.2.4`, both of which target the deprecated Node 20 runtime — CI already logs a deprecation warning since GitHub forces them onto Node 24 anyway.
- **Proposed fix:** Bump `actions/checkout` to `v5+` and `astral-sh/setup-uv` to a Node-24-runtime major (`v10` confirmed Node 24; exact cutover unverified), re-pinning both to commit SHAs with trailing version comments per the existing convention.
- **Trigger:** Before GitHub removes the forced Node 24 fallback and these actions stop running altogether.
- **Change ID:** `ci-quality-gates` (found post-merge, F11)
- **Status:** done (2026-08-28) — taken to the newest majors rather than the minimum that clears Node 20: `actions/checkout` v7.0.1, `astral-sh/setup-uv` v10.0.1, with `using: node24` read out of each action's own manifest at the pinned tag rather than trusted from a changelog. `checkout` is now SHA-pinned with a trailing version comment, which it never was. One behavior change rode along: setup-uv v10 defaults `enable-cache` to `auto` where v3 defaulted to off, so `gates` now restores and saves a uv cache keyed on `uv.lock` and `pyproject.toml`.
- **GitHub Issue:** [#20](https://github.com/miloszj7/VeloLog/issues/20)

#### E-10 — `Trip.date` is a single field on a multi-day product

- **Item:** `Trip.date` is a single `DateField` on a product whose subject is the **multi-day** tour — the owner's own framing: *"for one day trip it is simple, for multi day, better will be two date fields - start and end"* (2026-08-26).
- **Proposed fix:** **Original proposal superseded** — splitting `Trip.date` into start and end dates (re-deriving `Meta.ordering`, both templates, the admin column and `TripForm.clean_date` from the pair) would store a pair that is *derivable*, creating a second source of truth whose only novel behavior is drift. Resolved instead by deriving the displayed span from the stages: `min(started_at)` … `max(ended_at)` over a trip's `GpxTrack` rows, with `Trip.date` retained unchanged as the day the tour started. No `Trip` migration; the wording of that field's help text is the only user-visible change, and it belongs to `multi-stage-gpx-upload`.
- **Trigger:** FR-011 (multi-stage grouping) — was the named trigger, on the reasoning that multi-day chronology lives there per `prd.md:99`. It fired (S-01, `multi-stage-gpx-upload`) and disclosed the opposite: FR-011 orders stages by **GPS timestamp**, so it never reads `Trip.date` at all. The field had no consumer waiting on it.
- **Status:** done (2026-09-02) — **closed as unnecessary, not as delivered.** Two independent findings, both from `context/changes/multi-stage-gpx-upload/research.md`; either alone would be misleading. (1) *The PRD-amendment blocker is gone.* It cited FR-003, FR-007 and the Primary Success Criterion as all saying "a date", singular — but PRD v4 superseded v3 wholesale (v3 now at `context/foundation/archive/prd-2026-05-29-v3.md:66,74`), carries no FR numbering, and its Primary Success Criterion never mentions a date. The amendment happened as a regeneration, so nothing procedural stood in the way. (2) *The split is unnecessary regardless* — the `(start, end)` pair is derivable from stage timestamps (above), so storing it would be denormalization. Recording only (1) would leave this row reading "blocker cleared" and invite the next reader to perform the split, which is why both are here. The owner's original insight stands as correct — a multi-day tour does span dates — and is satisfied by derivation rather than by a second stored field. Absent-timestamp fallbacks and a possible future "rider supplies missing stage timestamps" capability are parked (`roadmap.md` → `## Parked`), pending inspection of real Garmin/phone exports. **The derivation shipped in `multi-stage-gpx-upload` (Phase 7, 2026-09-03)**: `gpx.stages.trip_span` computes the displayed span from the stage instants and stores nothing, gated on the same `chronology_is_established` predicate as the page's chronology wording and its stage-break markers, so a trip with any untimed stage shows the stored `Trip.date` alone — the v1 render, unchanged. `Trip.date`'s help text now names it as the day the tour *started*, which was the one user-visible change this row predicted. No `Trip` migration, as reasoned above.
- **GitHub Issue:** —

#### E-11 — GPX upload orphans its file in storage on transaction rollback

- **Item:** A GPX upload whose transaction rolls back leaves its file in storage with no row pointing at it (`gpx/views.py:104-119`, write at `:117`). **The atomic block is not the cause** — `FileField.pre_save` welds `storage.save()` to the INSERT inside the same `Model.save()` field loop, so the orphan reproduces under plain autocommit with no transaction anywhere. The `post_delete` receiver cannot reach such a file either way: it fires on deletes, not on failed inserts. A second, *deterministic* strand was found while investigating this one — the admin change form replaces a file on a row that survives, so no delete signal ever fires.
- **Proposed fix:** **Original proposal refuted** — moving the write outside `atomic()` or adding a rollback hook fixes nothing (the write is not transactional to begin with, and process death drives the same rollback with no exception to hook). Built instead, in two layers: a `pre_save` receiver reclaiming a file superseded on a surviving row, which closes the deterministic admin strand at the write site; and `manage.py reconcile_media`, which set-differences `MEDIA_ROOT` against the referenced keys and reclaims under `--delete` — the backstop for the crash window, for `bulk_*`/`QuerySet.update`, and for restore skew, none of which prevention can reach.
- **Trigger:** The next time `gpx/views.py`'s upload transaction is touched — the block's ordering was hardened by three prior review findings, so it should be reopened deliberately rather than in passing.
- **Change ID:** `gpx-upload-orphan-file`
- **Status:** done (2026-08-28) — all ten of its acceptance criteria are met by the four phases; its `status:planning` label is stale on close. Its Context section carries the pre-framing cause and the drifted cite `gpx/views.py:100-113`, then refutes both under *The roadmap's original proposed fix does not work* — read the issue whole, not by its opening paragraph. Measured 2026-08-28 before any fix: production 4 rows ↔ 4 files exact, 1.38 MiB on a 500 MB volume; local 3 ↔ 3 plus four empty directories — so this closed from a starting position of zero real orphans. The rollback window itself is **covered by reclamation, not prevented**; that is the deliberate outcome, not a shortfall. Found during the `edit-and-delete-trip` implementation review (F10).
- **GitHub Issue:** [#23](https://github.com/miloszj7/VeloLog/issues/23)
