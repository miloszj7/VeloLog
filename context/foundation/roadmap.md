---
project: VeloLog
version: 1
status: draft
created: 2026-08-22
updated: 2026-08-26
prd_version: 3
main_goal: speed
top_blocker: time
---

# Roadmap: VeloLog

> Derived from `context/foundation/prd.md` (v2) + auto-researched codebase baseline.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Vision recap

GPX tracks from multi-day cycling tours are scattered across devices and third-party apps, and no existing platform (Strava, Komoot, Wikiloc) treats a "trip" as a first-class entity spanning multiple stages. VeloLog is a personal, trip-centric diary: a solo touring cyclist creates a trip, uploads track files, and gets a single view of the journey with a rendered map and basic stats.

## North star

**S-03: User can upload a GPX track file and see the route drawn on a non-interactive map** — this is the smallest end-to-end slice that proves the core product hypothesis (the "north star": the minimal capability whose successful delivery validates that the trip-centric idea works in practice, placed as early as its prerequisites allow because everything else only matters once this works). It maps directly to the PRD's Primary Success Criterion: *"register → log in → create a trip → upload one GPX file → see the route drawn on a non-interactive map."* (PRD v3 reworded this from "a static map image"; the outcome is unchanged — see the PRD Changelog.)

## At a glance

| ID   | Change ID                    | Outcome (user can …)                                                        | Prerequisites | PRD refs             | Status   |
| ---- | ----------------------------- | ----------------------------------------------------------------------------- | -------------- | --------------------- | -------- |
| S-01 | `user-registration-login`     | Register with email/password, and log in/out                                 | —              | FR-001, FR-002, US-01 | done |
| S-02 | `create-and-list-trips`       | Create a trip (name, date, description) and see it in their trip list        | S-01           | FR-003, FR-006, US-01 | done |
| S-03 | `upload-gpx-and-view-map`     | Upload a GPX file to a trip and see the route on a non-interactive map (or empty state)| S-02           | FR-004, FR-005, US-01 | in-progress |
| S-04 | `edit-and-delete-trip`        | Edit a trip's details or delete a trip                                       | S-02           | FR-007, FR-008        | proposed |
| S-05 | `trip-distance-duration-stats`| See basic trip stats (distance, duration) on the trip detail view            | S-03           | FR-010                | proposed |

## Baseline

What's already in place in the codebase as of `2026-08-22` (auto-researched + user-confirmed).
Slices below assume these are present and build directly on top of them.

- **Frontend:** absent — no templates directory, no static UI beyond Django defaults; no map or trip UI exists yet.
- **Backend / API:** partial — Django project scaffold exists (`velo_log/settings.py`, `velo_log/urls.py`) with only `admin/` and a `/healthz/` endpoint wired; no app package or trip/auth views exist yet.
- **Data:** partial — SQLite is configured and reachable on a persistent Railway Volume (`DEPLOY.md`, `/data/db.sqlite3`), exercised by `/healthz/`; no domain models (User-facing Trip/track-file models) exist yet.
- **Auth:** partial — `django.contrib.auth` is installed (framework capability present), but no registration/login views, URLs, or templates are wired.
- **Deploy / infra:** present — Railway deploy fully wired: `.github/workflows/deploy.yml` auto-deploys `master` via the Railway CLI, `railway.json` runs `collectstatic` + `migrate` + `gunicorn`, `whitenoise` serves static files, and the SQLite file lives on a mounted persistent Volume with a documented backup/restore runbook (`DEPLOY.md`).
- **Observability:** partial — a `/healthz/` endpoint round-trips a real DB write/read, but there is no structured logging configuration or error tracking.

## Foundations

No foundations are needed. The codebase baseline is a clean Django scaffold with deploy/persistence already solved (see `## Baseline`); every remaining gap (auth views, trip data model, upload/map rendering) is user-visible work that belongs inside the vertical slice that needs it, not a cross-cutting enabler ahead of it.

## Slices

### S-01: User can register, log in, and log out

- **Outcome:** User can register with an email and password, then log in and log out.
- **Change ID:** `user-registration-login`
- **PRD refs:** FR-001, FR-002, US-01 (the authentication portion of the primary flow)
- **Prerequisites:** —
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Every other slice requires an authenticated user; sequencing this first avoids rework on slices built against an unauthenticated stub.
- **Status:** done

### S-02: User can create a trip and see it in their trip list

- **Outcome:** User can create a trip with a name, date, and description, and see it appear in a list of their own trips.
- **Change ID:** `create-and-list-trips`
- **PRD refs:** FR-003, FR-006, US-01
- **Prerequisites:** S-01
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** —
- **Risk:** A trip with no uploaded file must be a valid empty draft (per PRD Business Logic) — the list and creation flow need to tolerate that state cleanly before S-03 builds the upload/map path on top of it.
- **Status:** done

### S-03: User can upload a GPX file and see the route on a non-interactive map

- **Outcome:** User can upload a GPX file to a trip and open the trip detail view to see the route drawn on a non-interactive map, with a clear empty state if no file is uploaded yet.
- **Change ID:** `upload-gpx-and-view-map`
- **PRD refs:** FR-004, FR-005, US-01 (this is the north star — see `## North star`)
- **Prerequisites:** S-02
- **Parallel with:** S-04
- **Blockers:** —
- **Unknowns:** —
- **Risk:** The "data never lost" guardrail means uploaded files must land on the already-provisioned persistent Railway Volume (see `## Baseline` → Deploy/infra), not ephemeral local disk — a `/10x-plan`-level implementation detail, not a roadmap-level blocker, since the Volume already exists and is documented in `DEPLOY.md`. Silent map-render failures are explicitly disallowed by the PRD's NFR; the empty/error state must be deliberate, not a byproduct.
- **Status:** in-progress

### S-04: User can edit and delete a trip

- **Outcome:** User can edit a trip's name, date, and description, or delete the trip entirely.
- **Change ID:** `edit-and-delete-trip`
- **PRD refs:** FR-007, FR-008
- **Prerequisites:** S-02
- **Parallel with:** S-03
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Low — edit/delete on an already-modeled Trip is table-stakes CRUD with no new domain concepts; safe to build alongside S-03 since neither depends on the other.
- **Status:** proposed

### S-05: User can view basic trip stats

- **Outcome:** User can see basic trip stats (distance and duration), calculated from the uploaded GPX file, on the trip detail view.
- **Change ID:** `trip-distance-duration-stats`
- **PRD refs:** FR-010 (the PRD's Secondary Success Criterion)
- **Prerequisites:** S-03
- **Parallel with:** S-04
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Not required for the primary proof — if the 2026-09-10 deadline gets tight, this is the first must-have-adjacent slice to reconsider deferring, since the PRD itself frames it as value-add rather than blocking.
- **Status:** proposed

## Backlog Handoff

| Roadmap ID | Change ID                      | Suggested issue title                                    | Ready for `/10x-plan` | GitHub Issue | Linear Issue | Notes |
| ---------- | -------------------------------- | ---------------------------------------------------------- | ---------------------- | ------------ | ------------ | ----- |
| S-01       | `user-registration-login`        | User registration and login/logout                         | yes                     | [#1](https://github.com/miloszj7/VeloLog/issues/1) | [10X-1](https://linear.app/miloszj/issue/10X-1/s-01-user-can-register-log-in-and-log-out) | Run `/10x-plan user-registration-login` |
| S-02       | `create-and-list-trips`          | Create and list trips                                       | yes                     | [#2](https://github.com/miloszj7/VeloLog/issues/2) | [10X-2](https://linear.app/miloszj/issue/10X-2/s-02-user-can-create-a-trip-and-see-it-in-their-trip-list) | Planned and implemented (Phase 5, `/10x-implement create-and-list-trips`) |
| S-03       | `upload-gpx-and-view-map`        | Upload GPX and view route as static map (north star)        | no                      | [#3](https://github.com/miloszj7/VeloLog/issues/3) | [10X-3](https://linear.app/miloszj/issue/10X-3/s-03-user-can-upload-a-gpx-file-and-see-the-route-as-a-static-map) | Waiting on S-02 |
| S-04       | `edit-and-delete-trip`           | Edit and delete a trip                                       | no                      | [#4](https://github.com/miloszj7/VeloLog/issues/4) | [10X-4](https://linear.app/miloszj/issue/10X-4/s-04-user-can-edit-and-delete-a-trip) | Waiting on S-02 |
| S-05       | `trip-distance-duration-stats`   | Trip distance/duration stats                                 | no                      | [#5](https://github.com/miloszj7/VeloLog/issues/5) | [10X-5](https://linear.app/miloszj/issue/10X-5/s-05-user-can-view-basic-trip-stats) | Waiting on S-03 |

Migrated to GitHub Issues on 2026-08-22 — see `context/foundation/github-issues-migration.md` for the format, labels, and migration decisions.
Mirrored to Linear on 2026-08-22 — see `context/foundation/linear-issues-migration.md` for the format, labels, and mirroring decisions.

## Open Roadmap Questions

_None — the PRD has 0 Open Questions, and no cross-cutting sequencing question emerged during roadmap framing._

## Parked

- **FR-009 (trip visibility toggle, public/private)** — Why parked: PRD marks nice-to-have and explicitly scopes v1 to "all trips are private"; toggle is a stated v2 feature.
- **FR-011 (multi-stage grouping — multiple GPX files per trip)** — Why parked: PRD Business Logic states this is a v2 feature requiring chronological merge logic not needed for the v1 single-file trip.
- **FR-012 (browse/filter trip list)** — Why parked: PRD explicitly scopes v1 to a minimal, unfiltered list given the small expected trip count.
- **FR-013 (trip metadata — start location, photos, companions)** — Why parked: nice-to-have, not required by the primary or secondary Success Criteria.
- **FR-014 (accommodation waypoints between stages)** — Why parked: nice-to-have, depends on multi-stage grouping (FR-011) which is itself parked.
- **FR-015 (interactive map)** — Why parked: PRD explicitly notes this is "the first feature after the core upload-and-view flow is validated" — a stated v2 priority, not v1.
- **No external platform integration** — Why parked: PRD Non-Goals — avoids third-party API/OAuth complexity in v1.
- **No route planning or track editing** — Why parked: PRD Non-Goals — VeloLog is a log/viewer, not a planner or editor.
- **No native mobile app** — Why parked: PRD Non-Goals — a responsive web app is sufficient for v1.
- **No AI or geographic enrichment features** — Why parked: PRD Non-Goals — deferred to v2+.

## Engineering Backlog

Non-feature engineering debt, distinct from `## Parked` (which holds deliberately deferred
PRD scope). Each row's trigger names the condition that makes the fix due — nothing here
is picked up until its trigger fires.

| ID   | Item | Proposed fix | Trigger | Change ID | Status | GitHub Issue |
|------|---|---|---|---|---|---|
| E-01 | CI runs no tests, ruff, black, isort, or mypy — only `manage.py check` plus the migration guard S-02 added, and only on push to `master` | Add a `pull_request` trigger and a job running `uv run pytest --cov` plus the lint/type gates, before the `railway up` step | Before S-03 — the north star slice adds file upload and map rendering, where a silent regression is most costly | `ci-quality-gates` | done | [#7](https://github.com/miloszj7/VeloLog/issues/7) |
| E-02 | `gates` is not a required check — a merge can still be forced past a red run | Enable branch protection on `master` requiring the `gates` check | Immediately after `ci-quality-gates` merges | — | open | — |
| E-03 | Tracker statuses never propagate — GitHub and Linear migrations are documented as one-way with no sync back | Decide whether trackers are authoritative or decorative, and either close them out per slice or note in the roadmap that they are a point-in-time snapshot | Before the next roadmap regeneration | — (partial: `ci-quality-gates` PR #8 added the `GitHub Issue` column read by this row, but the gap it describes — no sync *back* from GitHub — is untouched) | open | — |
| E-04 | `railway.json` must migrate to `.railway/railway.ts` before 2026-12-01 | Convert the start command to the TypeScript config format | By 2026-11-01, after the 2026-09-10 product deadline | — | open | — |
| E-05 | The `/data/db.sqlite3` restore path has never been exercised | Restore a backup into a scratch environment once, to prove the runbook | Before the deploy following S-03, once real user data exists | — | done (2026-08-26) | Drilled against production rather than a scratch environment — production held only test data, the cheapest this would ever be. Found **three** runbook defects, all corrected in `DEPLOY.md` → *Restore drill*: the documented DB restore was refused outright without `--overwrite`, and the documented media restore reported success while nesting the backup and recovering nothing. The scratch-target path still does not exist and is now the open remainder — see the note at the end of that section. |
| E-06 | No structured logging or error tracking — `/healthz/` is the whole observability story | Introduce `LOGGING` config; a trips view 500ing in production is diagnosed only via `railway logs`. The dict must include a `velo_log` logger and a formatter that emits the `media_root` extra — `/healthz/` reports failures through logging alone, and its misconfigured-path detail is passed via `extra`, which `logging.lastResort` drops. See the Logging note in `velo_log/settings.py` | When the first production incident is diagnosed by guesswork | — | open | — |
| E-07 | The `$5` Railway spend alert is flagged un-reverified (`DEPLOY.md:43`) | Re-confirm the alert fires | Next time the Railway dashboard is open | — | open | — |
| E-08 | `TripForm` accepts a future-dated trip with no validation (found during S-02 Phase 3 manual verification) | Decide product intent (block future dates? allow and label as "planned"?) then add `clean_date()` if blocking is the answer | When trip-date semantics are next revisited, e.g. alongside S-03/S-04 | — | open | — |
| E-09 | `.github/workflows/deploy.yml` pins `actions/checkout@v4` and `astral-sh/setup-uv@v3.2.4`, both of which target the deprecated Node 20 runtime — CI already logs a deprecation warning since GitHub forces them onto Node 24 anyway | Bump `actions/checkout` to `v5+` and `astral-sh/setup-uv` to a Node-24-runtime major (`v10` confirmed Node 24; exact cutover unverified), re-pinning both to commit SHAs with trailing version comments per the existing convention | Before GitHub removes the forced Node 24 fallback and these actions stop running altogether | `ci-quality-gates` (found post-merge, F11) | open | — |

## Done

- **S-01: User can register with an email and password, then log in and log out.** — Archived 2026-08-22 → `context/archive/2026-08-22-user-registration-login/`. Lesson: —.
- **S-02: User can create a trip with a name, date, and description, and see it appear in a list of their own trips.** — Archived 2026-08-23 → `context/archive/2026-08-23-create-and-list-trips/`. Lesson: —.
