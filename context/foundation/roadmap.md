---
project: VeloLog
version: 2
status: draft
created: 2026-08-22
updated: 2026-09-04
prd_version: 4
main_goal: speed
top_blocker: time
milestone_id: multi-stage-trips-interactive-map
milestone_seq: 2
milestone_status: open
---

# Roadmap: VeloLog

> Derived from `context/foundation/prd.md` (v4) + auto-researched codebase baseline.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Milestone

**M-02: Multi-stage trips and interactive map** — Status: open

- **Intent:** Close the two gaps left over from the MVP: a trip can now represent a real multi-day tour as chronologically-ordered stages, and the route renders on a pan/zoom interactive map — while every existing v1 single-stage trip keeps working unchanged.
- **Source materials:** `context/foundation/prd.md` (v4)
- **Done when:** S-01 and S-02 are `done`. S-03 (multi-stage statistics) is an explicit stretch slice — the user asked for it as "optional, worth doing if there is time"; picking it up is not required to close this milestone.
- **Scope anchors:** US-02; PRD `## Scope of Change` must-have bullets (multi-stage upload, chronological merge with distinct segments, interactive map, stage/start/end markers, preserved v1 behavior).

## Vision recap

GPX tracks from multi-day cycling tours are scattered across devices and third-party apps, and no existing platform (Strava, Komoot, Wikiloc) treats a "trip" as a first-class entity spanning multiple stages. VeloLog is a personal, trip-centric diary. The MVP (M-01) proved the core loop for a single-day, single-file trip; this milestone closes the two gaps the PRD names as still open: the data model only represents one day and one file, and the map is a static, unstyled image.

## North star

**S-01: User can upload a second GPX file to an existing trip as an additional stage, and see all stages merged chronologically as distinct segments with start/end/stage-break markers** — the smallest end-to-end flow that proves the core product hypothesis: that a trip is genuinely a multi-stage entity, not a single activity (the "north star" — placed first because everything else in this milestone only matters once this works). This is the PRD's Problem Statement gap #1 (data-fidelity), and the riskier of this milestone's two must-haves — a hard 1-week, after-hours-only deadline (2026-09-10) means proving the harder, higher-value change first leaves the core capability shipped even if the rest slips.

## At a glance

| ID   | Change ID                        | Outcome (user can …)                                                                                       | Prerequisites | PRD refs                                    | Status   |
| ---- | --------------------------------- | ------------------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------- | -------- |
| S-01 | `multi-stage-gpx-upload`          | Upload a second (and further) GPX file to a trip and see all stages merged chronologically as distinct colored segments, with start/end/stage-break markers | —              | US-02; Scope of Change (multi-stage upload, chronological merge, stage-break markers) | done |
| S-02 | `interactive-trip-map`            | Pan and zoom the trip map instead of viewing a static image                                                    | —              | US-02; Scope of Change (interactive map)        | done |
| S-03 | `multi-stage-trip-stats`          | (stretch) See whole-trip aggregate statistics (distance, duration, elevation) on the trip detail view, with a partial-data presentation rule when not every stage is timed | S-01           | PRD Fast-follow (whole-trip statistics, nice-to-have) | planning |

## Baseline

What's already in place in the codebase as of `2026-09-02` (auto-researched + user-confirmed). Unchanged from M-01 unless noted.

- **Frontend:** present — trip/GPX templates and static assets exist and are in production use (`trips/templates/`, `gpx/static/gpx/`).
- **Backend / API:** present — `trips` and `gpx` apps are fully wired (views, URLs, forms) and in production use.
- **Data:** present, and already anticipates this change — `GpxTrack.trip` is a `ForeignKey` (many tracks per trip), deliberately modeled that way in v1 "so FR-011 needs no migration rewrite" (`gpx/models.py` docstring). What's still v1-shaped: `GpxUploadView.post` resolves the trip's track via `.tracks.first()` and the upload flow *replaces* the existing track (a `pre_save` signal reclaims the superseded file) rather than adding a stage — that replace-semantics is exactly what S-01 changes.
- **Auth:** present — registration/login/logout fully wired, ownership scoping enforced project-wide (404-not-403 contract, `tests/test_ownership_matrix.py`).
- **Deploy / infra:** present — unchanged from M-01 (Railway, persistent Volume, CI gates).
- **Observability:** present — structured logging landed in M-01 (E-06).
- **Map rendering:** present, and confirms the PRD's own hypothesis — `gpx/static/gpx/map.js` already renders via Leaflet 1.9.4 with `dragging`, `scrollWheelZoom`, `touchZoom`, `doubleClickZoom`, `keyboard`, `boxZoom`, and `zoomControl` all explicitly set to `false`. Flipping to interactive (S-02) is a config change to already-vendored, already-working code, not a new library integration. Start/finish markers are also already drawn today (`L.marker(...)`), so per-stage/stage-break marker styling (S-01) has an existing pattern to extend rather than a new capability to build from scratch.

## Foundations

No foundations are needed. The data model already supports multiple stages per trip (see `## Baseline` → Data), and the map library is already vendored and rendering (see `## Baseline` → Map rendering). The remaining gaps — upload-accumulation behavior, chronological merge/segment rendering, and the interactivity flip — are all user-visible work that belongs inside the vertical slice that needs it.

## Slices

### S-01: User can upload a second GPX file to a trip as an additional stage

- **Outcome:** User can upload a second (and further) GPX file to an existing trip and, on the trip detail view, see all stages merged into one route, ordered chronologically by GPS timestamp, each stage rendered as a visually distinct segment (e.g. a different line color), with distinct markers for the trip's start, end, and each inter-stage boundary ("stage break"). A single-GPX v1 trip continues to render unchanged.
- **Change ID:** `multi-stage-gpx-upload`
- **PRD refs:** US-02 (primary); Scope of Change — "user can upload a second (and further) GPX file" (must-have), "stages merged chronologically, distinct segments" (must-have), "distinct start/end/stage-break markers" (must-have), "existing single-GPX v1 trips continue to render, edit, and delete correctly" (preserved)
- **Prerequisites:** —
- **Parallel with:** S-02 (independent — the merge/rendering logic and the interactivity flip touch different code paths and neither blocks the other)
- **Blockers:** —
- **Unknowns:**
  - The Constraints section flags that a future route removing a single stage would need its own entry in the ownership-scoping test inventory (`tests/test_ownership_matrix.py`) — not required by this milestone's scope (no stage-removal capability is being built), but worth naming so `/10x-plan` doesn't skip it if scope grows. Owner: user. Block: no.
- **Risk:** `GpxUploadView.post` today resolves `.tracks.first()` and its upload flow *replaces* the trip's existing track — a `pre_save` signal reclaims the superseded file on that assumption. Changing "replace" to "add" touches that upload path and its file-lifecycle signal together; getting this wrong risks the "data never lost" guardrail (an accidentally-deleted earlier stage) rather than just a rendering bug. This is exactly why it's sequenced as the north star: it's the riskiest change in the milestone, and proving it first means a slip still leaves the core capability shipped.
- **Status:** done

### S-02: User views the trip route on an interactive map

- **Outcome:** User can pan and zoom the trip's map instead of viewing a static, non-interactive image. Applies to every trip, single-stage or multi-stage.
- **Change ID:** `interactive-trip-map`
- **PRD refs:** US-02 (the map-interactivity clause); Scope of Change — "user views the trip route on an interactive (pan/zoom) map instead of a static image" (must-have)
- **Prerequisites:** —
- **Parallel with:** S-01
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Low — per `## Baseline`, this is a config flip on already-vendored, already-rendering Leaflet code (flip `dragging`/`scrollWheelZoom`/`touchZoom`/`doubleClickZoom`/`keyboard`/`boxZoom`/`zoomControl` and re-enable the zoom control), not a new integration. Sequenced after S-01 in the milestone's priority (per the user's sequencing call) precisely because it's the safe, low-risk item — if time runs out, this is what's still acceptable to finish last or cut.
- **Status:** done

### S-03: User can view whole-trip aggregate statistics (stretch)

- **Outcome:** User can see whole-trip *aggregate* statistics (distance, duration, elevation) on the trip detail view, summed across every stage, with a rule for presenting the total when not every stage carries every figure. Per-stage display already shipped in S-01 (`multi-stage-gpx-upload`'s Phase 4 Stages section), so this narrows to the aggregation and its partial-data presentation only.
- **Change ID:** `multi-stage-trip-stats`
- **PRD refs:** PRD `### Fast-follow` — "user can view whole-trip and per-stage statistics (distance, duration, elevation) on the trip detail view" (nice-to-have, explicitly parked for this change but named "pick up only if the week's core scope finishes early"); per-stage display narrowed out per the Open Roadmap Questions #1 resolution below.
- **Prerequisites:** S-01 (needs stages to actually exist and be ordered before per-stage/whole-trip aggregation means anything)
- **Parallel with:** S-02
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Explicitly optional — the PRD frames this as fast-follow and the user confirmed it's a "worth doing if there is time" stretch goal, not required for the Primary Success Criterion. Under the 1-week/after-hours/hard-deadline constraint (`top_blocker: time`), this is the first item to drop if S-01 or S-02 run long.
- **Status:** planning

## Backlog Handoff

| Roadmap ID | Change ID                 | Suggested issue title                                              | Ready for `/10x-plan` | GitHub Issue | Notes |
| ---------- | -------------------------- | ---------------------------------------------------------------------- | ---------------------- | ------------ | ----- |
| S-01       | `multi-stage-gpx-upload`   | Multi-stage GPX upload: chronological merge, segments, stage markers   | yes                     | [#37](https://github.com/miloszj7/VeloLog/issues/37) | Run `/10x-plan multi-stage-gpx-upload` — north star |
| S-02       | `interactive-trip-map`     | Flip trip map to interactive (pan/zoom)                                 | yes                     | [#38](https://github.com/miloszj7/VeloLog/issues/38) | Run `/10x-plan interactive-trip-map` — can run in parallel with S-01 |
| S-03       | `multi-stage-trip-stats`   | Whole-trip and per-stage statistics (stretch goal)                      | no                      | [#39](https://github.com/miloszj7/VeloLog/issues/39) | Stretch — only plan after S-01 lands and time remains before 2026-09-10 |

Milestone `M-02` slices migrated to GitHub Issues on 2026-09-02, under the GitHub milestone "VeloLog v1.5" (due 2026-09-10) — see `context/foundation/github-issues-migration.md` for format and decisions.

## Open Roadmap Questions

1. ~~**US-02 has no separate Acceptance Criteria checklist beyond its Given/When/Then.**~~ — **Resolved 2026-09-02**, in `prd.md` → US-02 `#### Acceptance Criteria` (and its `## Open Questions` #1). Answered *after* `/10x-plan` rather than before it: S-01's plan worked out the concrete criteria while deciding what to build, so the checklist was backfilled from the plan's Phase 2/3/4 success criteria instead of being guessed at up front. One PRD amendment rode along — Non-Goal #3 narrowed to whole-trip aggregation only, which **narrows S-03**: per-stage display now lands in S-01, leaving S-03 as trip-total aggregation plus its partial-data presentation rule. S-01's plan already schedules that S-03 re-wording as Phase 4 work; this row records why it is coming.

## Parked

- **Accommodation waypoint entity (description, photo) between stages** — Why parked: PRD Non-Goals / Fast-follow — a standalone record is explicitly deferred; only the generic "stage break" marker (built in S-01) ships this milestone. Depends on the same multi-stage grouping S-01 introduces, so revisit only after S-01 lands.
- **Manual stage reordering** — Why parked: PRD Non-Goals — stage order is always derived from GPS timestamp; no drag-to-reorder UI or manual override in this milestone.
- **No external platform integration** — Why parked: PRD Non-Goals — avoids third-party API/OAuth complexity.
- **No route planning or track editing** — Why parked: PRD Non-Goals — VeloLog is a log/viewer, not a planner or editor.
- **No native mobile app** — Why parked: PRD Non-Goals — a responsive web app is sufficient.
- **No AI or geographic enrichment features** — Why parked: PRD Non-Goals — deferred to v2+.
- **FR-009 (trip visibility toggle, public/private)** — Why parked: carried from M-01; still nice-to-have, still out of scope for this milestone.
- **FR-012 (browse/filter trip list)** — Why parked: carried from M-01; small trip count still doesn't justify it.
- **FR-013 (trip metadata — start location, photos, companions)** — Why parked: carried from M-01; nice-to-have, not required by this milestone's Success Criterion.
- **Speed and moving-time stats (average speed, max speed, moving time)** — Why parked: carried from M-01 (dropped from S-05 during its plan review, 2026-08-27, F7 — `gpxpy.get_moving_data()` was unreliable on synthetic probe input). Pick up with real timed exports in hand; if S-03 (multi-stage stats) is picked up this milestone, this is a natural companion to reconsider at the same time, not before.
- **Rider supplies missing stage timestamps (and, through them, the trip's timespan)** — Why parked: raised 2026-09-02 while researching S-01. A GPX with no `<time>` elements yields no orderable instant, so such stages fall back to upload order and a trip holding one shows no derived timespan — only its stored start date, which is exactly v1's current display. That degrade is cheap and ships in S-01; a capability letting the rider fill the gap in is not, and its value is unmeasured. **Pick up only with real exports in hand** (owner investigating Garmin and phone-app output) — untimed GPX is typically a *planned-route* export rather than a ridden track, which is out-of-character input for a diary-not-planner, so this may never be due. Two design constraints are already settled if it is: the edit targets a **stage's** `started_at`/`ended_at`, never the trip's span directly (editing the trip span reintroduces the two-sources-of-truth drift that closed E-10), and **no `order`/`position` column** is added, so stage order stays a pure function of instants and the "no manual reordering" Non-Goal above softens only to "derived from timestamps, recorded or supplied". Forward-compatibility is free: the nullable timestamp columns S-01 adds are the whole schema requirement, so this needs only a form later, no migration. Full reasoning in `context/changes/multi-stage-gpx-upload/research.md` (follow-up 3).

## Engineering Backlog

Non-feature engineering debt, distinct from `## Parked` (which holds deliberately deferred
PRD scope). Each item's trigger names the condition that makes the fix due — nothing here
is picked up until its trigger fires. The table below is the index; full context for each
item is in `### Details`.

### At a glance — To Do

| ID   | Item                                                    | Trigger                                                        | Status      |
| ---- | -------------------------------------------------------- | ----------------------------------------------------------------- | ----------- |
| E-04 | `railway.json` must migrate to `.railway/railway.ts`       | By 2026-11-01, after the 2026-09-10 product deadline               | open        |
| E-07 | `$5` Railway spend alert un-reverified                     | After free trial expires (23 days from 2026-08-28)                 | **blocked** (on free trial) |

### At a glance — Done

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

### Details

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
- **Status:** open
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
- **Status:** done (2026-09-02) — **closed as unnecessary, not as delivered.** Two independent findings, both from `context/changes/multi-stage-gpx-upload/research.md`; either alone would be misleading. (1) *The PRD-amendment blocker is gone.* It cited FR-003, FR-007 and the Primary Success Criterion as all saying "a date", singular — but PRD v4 superseded v3 wholesale (v3 now at `context/foundation/archive/prd-2026-05-29-v3.md:66,74`), carries no FR numbering, and its Primary Success Criterion never mentions a date. The amendment happened as a regeneration, so nothing procedural stood in the way. (2) *The split is unnecessary regardless* — the `(start, end)` pair is derivable from stage timestamps (above), so storing it would be denormalization. Recording only (1) would leave this row reading "blocker cleared" and invite the next reader to perform the split, which is why both are here. The owner's original insight stands as correct — a multi-day tour does span dates — and is satisfied by derivation rather than by a second stored field. Absent-timestamp fallbacks and a possible future "rider supplies missing stage timestamps" capability are parked (`## Parked`), pending inspection of real Garmin/phone exports. **The derivation shipped in `multi-stage-gpx-upload` (Phase 7, 2026-09-03)**: `gpx.stages.trip_span` computes the displayed span from the stage instants and stores nothing, gated on the same `chronology_is_established` predicate as the page's chronology wording and its stage-break markers, so a trip with any untimed stage shows the stored `Trip.date` alone — the v1 render, unchanged. `Trip.date`'s help text now names it as the day the tour *started*, which was the one user-visible change this row predicted. No `Trip` migration, as reasoned above.
- **GitHub Issue:** —

#### E-11 — GPX upload orphans its file in storage on transaction rollback

- **Item:** A GPX upload whose transaction rolls back leaves its file in storage with no row pointing at it (`gpx/views.py:104-119`, write at `:117`). **The atomic block is not the cause** — `FileField.pre_save` welds `storage.save()` to the INSERT inside the same `Model.save()` field loop, so the orphan reproduces under plain autocommit with no transaction anywhere. The `post_delete` receiver cannot reach such a file either way: it fires on deletes, not on failed inserts. A second, *deterministic* strand was found while investigating this one — the admin change form replaces a file on a row that survives, so no delete signal ever fires.
- **Proposed fix:** **Original proposal refuted** — moving the write outside `atomic()` or adding a rollback hook fixes nothing (the write is not transactional to begin with, and process death drives the same rollback with no exception to hook). Built instead, in two layers: a `pre_save` receiver reclaiming a file superseded on a surviving row, which closes the deterministic admin strand at the write site; and `manage.py reconcile_media`, which set-differences `MEDIA_ROOT` against the referenced keys and reclaims under `--delete` — the backstop for the crash window, for `bulk_*`/`QuerySet.update`, and for restore skew, none of which prevention can reach.
- **Trigger:** The next time `gpx/views.py`'s upload transaction is touched — the block's ordering was hardened by three prior review findings, so it should be reopened deliberately rather than in passing.
- **Change ID:** `gpx-upload-orphan-file`
- **Status:** done (2026-08-28) — all ten of its acceptance criteria are met by the four phases; its `status:planning` label is stale on close. Its Context section carries the pre-framing cause and the drifted cite `gpx/views.py:100-113`, then refutes both under *The roadmap's original proposed fix does not work* — read the issue whole, not by its opening paragraph. Measured 2026-08-28 before any fix: production 4 rows ↔ 4 files exact, 1.38 MiB on a 500 MB volume; local 3 ↔ 3 plus four empty directories — so this closed from a starting position of zero real orphans. The rollback window itself is **covered by reclamation, not prevented**; that is the deliberate outcome, not a shortfall. Found during the `edit-and-delete-trip` implementation review (F10).
- **GitHub Issue:** [#23](https://github.com/miloszj7/VeloLog/issues/23)

## Done

- **S-01: User can register with an email and password, then log in and log out.** — Archived 2026-08-22 → `context/archive/2026-08-22-user-registration-login/`. Lesson: —.
- **S-02: User can create a trip with a name, date, and description, and see it appear in a list of their own trips.** — Archived 2026-08-23 → `context/archive/2026-08-23-create-and-list-trips/`. Lesson: —.
- **S-03: User can upload a GPX file to a trip and open the trip detail view to see the route drawn on a non-interactive map, with a clear empty state if no file is uploaded yet.** — Archived 2026-08-26 → `context/archive/2026-08-23-upload-gpx-and-view-map/`. Lesson: —.
- **S-04: User can edit a trip's name, date, and description, or delete the trip entirely.** — Archived 2026-08-27 → `context/archive/2026-08-26-edit-and-delete-trip/`. Lesson: —.
- **S-05: User can see basic trip stats (distance and duration), calculated from the uploaded GPX file, on the trip detail view.** — Archived 2026-08-28 → `context/archive/2026-08-27-trip-distance-duration-stats/`. Lesson: —.
- **S-02: User can pan and zoom the trip's map instead of viewing a static, non-interactive image. Applies to every trip, single-stage or multi-stage.** — Archived 2026-09-02 → `context/archive/2026-09-02-interactive-trip-map/`. Lesson: —.
- **S-01: User can upload a second (and further) GPX file to an existing trip and, on the trip detail view, see all stages merged into one route, ordered chronologically by GPS timestamp, each stage rendered as a visually distinct segment (e.g. a different line color), with distinct markers for the trip's start, end, and each inter-stage boundary ("stage break"). A single-GPX v1 trip continues to render unchanged.** — Archived 2026-09-03 → `context/archive/2026-09-02-multi-stage-gpx-upload/`. Lesson: —.

## Milestone History

- **M-01: Core trip log MVP** (`core-trip-log-mvp`) — closed 2026-09-02 (adopted retroactively; all slices had been done since 2026-08-28). Register/login, create/list/edit/delete a trip, upload one GPX file per trip and view its route on a non-interactive map with distance/duration stats.
