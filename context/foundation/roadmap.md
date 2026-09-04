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
milestone_status: done
---

# Roadmap: VeloLog

> Derived from `context/foundation/prd.md` (v4) + auto-researched codebase baseline.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Milestone

**M-02: Multi-stage trips and interactive map** — Status: done

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
| S-03 | `multi-stage-trip-stats`          | (stretch) See whole-trip aggregate statistics (distance, duration, elevation) on the trip detail view, with a partial-data presentation rule when not every stage is timed | S-01           | PRD Fast-follow (whole-trip statistics, nice-to-have) | done |

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
- **Status:** done (2026-09-04) — `context/changes/multi-stage-trip-stats/reviews/impl-review.md`: APPROVED, all three phases match plan, no critical/warning findings beyond a documented post-close addendum (stage-count line).

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

Non-feature engineering debt (CI, infra, tooling hardening) is tracked separately in
`context/foundation/engineering-backlog.md` — distinct from `## Parked` above, which
holds deliberately deferred PRD scope.

## Done

Slice IDs (`S-xx`) restart at 1 within each milestone, so the same ID appears more
than once below — each entry is tagged with its milestone to disambiguate.

- **[M-01] S-01: User can register with an email and password, then log in and log out.** — Archived 2026-08-22 → `context/archive/2026-08-22-user-registration-login/`. Lesson: —.
- **[M-01] S-02: User can create a trip with a name, date, and description, and see it appear in a list of their own trips.** — Archived 2026-08-23 → `context/archive/2026-08-23-create-and-list-trips/`. Lesson: —.
- **[M-01] S-03: User can upload a GPX file to a trip and open the trip detail view to see the route drawn on a non-interactive map, with a clear empty state if no file is uploaded yet.** — Archived 2026-08-26 → `context/archive/2026-08-23-upload-gpx-and-view-map/`. Lesson: —.
- **[M-01] S-04: User can edit a trip's name, date, and description, or delete the trip entirely.** — Archived 2026-08-27 → `context/archive/2026-08-26-edit-and-delete-trip/`. Lesson: —.
- **[M-01] S-05: User can see basic trip stats (distance and duration), calculated from the uploaded GPX file, on the trip detail view.** — Archived 2026-08-28 → `context/archive/2026-08-27-trip-distance-duration-stats/`. Lesson: —.
- **[M-02] S-02: User can pan and zoom the trip's map instead of viewing a static, non-interactive image. Applies to every trip, single-stage or multi-stage.** — Archived 2026-09-02 → `context/archive/2026-09-02-interactive-trip-map/`. Lesson: —.
- **[M-02] S-01: User can upload a second (and further) GPX file to an existing trip and, on the trip detail view, see all stages merged into one route, ordered chronologically by GPS timestamp, each stage rendered as a visually distinct segment (e.g. a different line color), with distinct markers for the trip's start, end, and each inter-stage boundary ("stage break"). A single-GPX v1 trip continues to render unchanged.** — Archived 2026-09-03 → `context/archive/2026-09-02-multi-stage-gpx-upload/`. Lesson: —.
- **[M-02] S-03: User can see whole-trip *aggregate* statistics (distance, duration, elevation) on the trip detail view, summed across every stage, with a rule for presenting the total when not every stage carries every figure. Per-stage display already shipped in S-01 (`multi-stage-gpx-upload`'s Phase 4 Stages section), so this narrows to the aggregation and its partial-data presentation only.** — Archived 2026-09-04 → `context/archive/2026-09-04-multi-stage-trip-stats/`. Lesson: —.

## Milestone History

- **M-01: Core trip log MVP** (`core-trip-log-mvp`) — closed 2026-09-02 (adopted retroactively; all slices had been done since 2026-08-28). Register/login, create/list/edit/delete a trip, upload one GPX file per trip and view its route on a non-interactive map with distance/duration stats.
- **M-02: Multi-stage trips and interactive map** (`multi-stage-trips-interactive-map`) — closed 2026-09-04. A trip can now hold multiple chronologically-ordered stages merged into one route with distinct segments and stage-break markers, the map is pan/zoom interactive, and whole-trip aggregate statistics are shown on the trip detail view — every v1 single-stage trip keeps working unchanged.
