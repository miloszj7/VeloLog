---
project: VeloLog
version: 1
context_type: brownfield
created: 2026-09-02
updated: 2026-09-02
product_type: web-app
target_scale:
  users: small
timeline_budget:
  delivery_weeks: 1
  after_hours_only: true
  hard_deadline: "2026-09-10"
checkpoint:
  current_phase: 8
  phases_completed: [1, 2, 3, 4, 5, 6, 7]
  frs_drafted: 7
  quality_check_status: accepted
---

## Current System

VeloLog v1 is a deployed Django 6 web app (Railway) with a working end-to-end flow: register/login, create a trip (name, single date, description), upload exactly one GPX track file, view it on a static (non-interactive) map with distance/recorded-time/elevation stats, edit/delete the trip. Ownership scoping is enforced project-wide (404-not-403 contract, tested via an ownership matrix). Storage lifecycle for uploaded files is fully handled (signals + `reconcile_media` backstop). All 5 v1 roadmap slices (S-01–S-05) are done and archived.

## Vision & Problem Statement (v1.5 delta)

**What's changing**: Two gaps remain between v1 and the original core insight ("a trip is a first-class multi-stage entity, not a single activity"):

1. **Data-fidelity gap**: `Trip` still models a single day / single GPX file. A real multi-day tour — the product's actual subject — cannot be represented. This is the long-parked FR-011/FR-014/E-10 cluster.
2. **Presentation gap**: The map is static and the points on it are unstyled. FR-015 (interactive map) was explicitly deferred as "the first feature after the core flow is validated" — that validation is now done (v1 shipped and used).

**Why now**: One week of remaining after-hours time before the 2026-09-10 deadline. Both gaps are already named and reasoned-about in `roadmap.md`'s Parked section — this session's job is to scope how much of that cluster actually fits in a week, not to invent new scope.

**Must preserve**: Existing single-GPX, single-date trips must continue to render, edit, and delete correctly after any data-model change. Ownership scoping and the "data never lost" guardrail extend unchanged to any new upload paths.

## User & Persona

**Primary persona**: Unchanged from v1 — a solo touring cyclist (the product owner) who logs their own multi-day tours. No new persona introduced in v1.5.

## Access Control

No changes planned — current model preserved. Flat single-user role, email+password auth, strict per-owner scoping (404-not-403 contract) on every object-scoped route. New object types introduced in v1.5 (additional stage files, accommodation waypoints) are child records of `Trip` and inherit its ownership scope — no new access concept is required, but any new `<int:pk>` route added under `trips`/`gpx` must still be added to `OBJECT_SCOPED_ROUTES` in `tests/test_ownership_matrix.py` per the project's hard rule.

## Success Criteria

### Primary
A user opens an existing trip, uploads a second (and further) GPX file as an additional stage, and the trip detail view renders all stages as visually distinct, chronologically-ordered segments on an interactive (pan/zoom) OpenStreetMap, with distinct markers for the trip's start, end, and each inter-stage boundary ("stage break"). A single-GPX v1 trip continues to render correctly, unchanged, on the same interactive map.

### Secondary
None promoted for this slice — whole-trip/per-stage stats and standalone accommodation waypoints are explicitly fast-follow (see Non-Goals).

### Guardrails
- **Data never lost**: every uploaded stage file is durably stored and retrievable, same guarantee as v1.
- **v1 trips unaffected**: existing single-GPX, single-date trips keep working through the data-model change with no manual migration step from the user.
- **User data isolation**: unchanged from v1 — no cross-user access to trips or stage files under any circumstance.

`timeline_budget.delivery_weeks: 1` — scoped down to fit; no separate timeline acknowledgment needed.

## Functional Requirements

### Multi-stage trips
- FR-016: User can upload a second (and further) GPX file to an existing trip as an additional stage. Priority: must-have. Change: new
  > Socrates: No counter-argument; it stands as written — this is the core data-fidelity fix the whole increment is about.
- FR-017: User sees all of a trip's stages merged into one route, ordered chronologically by GPS timestamp, with each stage rendered as a visually distinct segment (e.g. a different line color per stage). Priority: must-have. Change: modified (supersedes v1's single-file render; realizes PRD Business Logic's stated v2 merge rule)
  > Socrates: Counter-argument considered: "chronological merge is wrong if stages have a time gap (rest day, or simply a new day) — a continuous unbroken line implies continuous riding." Resolution: revised — stages render as visually distinct segments (per-stage color) rather than one undifferentiated line, so a gap in time doesn't read as a gap that should exist in the geometry.
- FR-020: Existing single-GPX v1 trips continue to render, edit, and delete correctly, unchanged. Priority: must-have. Change: preserved
  > Socrates: No counter-argument; it stands as written.

### Interactive map & markers
- FR-018: User views the trip route on an interactive (pan/zoom) OpenStreetMap instead of a static image. Priority: must-have. Change: modified (supersedes FR-005; promotes FR-015 from nice-to-have)
  > Socrates: No counter-argument; it stands as written — the static map was always a v1 placeholder per the original PRD's FR-005 Socrates note.
- FR-019: User sees distinct markers for trip start, trip end, and each inter-stage boundary, labeled generically as a "stage break" rather than "accommodation". Priority: must-have. Change: new
  > Socrates: Counter-argument considered: "labeling a stage boundary as 'accommodation' asserts a fact the data doesn't support — it could be a lunch stop, a GPS pause, or any reason a rider split a stage into two files, not necessarily an overnight stay." Resolution: revised — marker labeled generically as "stage break". True accommodation semantics (a confirmed overnight stop with its own description/photo) is FR-021's job, deferred to fast-follow.

### Fast-follow (parked for this session — pick up only if the week's core slice finishes early)
- FR-021: User can add an accommodation waypoint (description, photo) between stages, as its own record rather than an inferred map marker. Priority: nice-to-have. Change: new
- FR-022: User can view whole-trip and per-stage statistics (distance, duration, elevation) on the trip detail view. Priority: nice-to-have. Change: new

## User Stories

### US-02: Multi-day trip logged as one interactive journey
Given a user has an existing trip with one GPX stage already uploaded,
When they upload a second GPX file to the same trip and open the trip detail view,
Then they see both stages as visually distinct, chronologically-ordered segments on an interactive map, with markers at the trip's start, end, and the "stage break" between the two stages.

## Business Logic

**Domain rule (modified)**: v1's rule — a trip is complete with exactly one uploaded track file; the system does not merge multiple files — is modified. A trip may now have multiple stages (track files); the system merges them into one route ordered chronologically by GPS timestamp, renders each stage as a visually distinct segment, and marks each inter-stage boundary as a "stage break". The system still does not infer trip boundaries or which files belong together — grouping stages under a trip remains an explicit user action (uploading to that trip), consistent with v1's Business Logic.

## Non-Functional Requirements

Unchanged from v1: the trip map renders and the page reaches an interactive state within a time that does not feel broken on typical home broadband, with no persistent spinners or silent load failures. This NFR extends to the merged multi-stage render without a new target.

## Constraints & Preserved Behavior

- **No data migration required from the user**: existing v1 trips (one file, one date) must continue to work with no manual action required — any schema change (e.g. splitting the single-file relationship into a stage collection) must be backward-compatible or auto-backfilled.
- **Ownership matrix stays in sync**: any new pk-scoped route this slice introduces (e.g. removing a single stage from a trip) must be added to `OBJECT_SCOPED_ROUTES` in `tests/test_ownership_matrix.py`, per the project's hard rule.

## Forward: tech-stack

- Leaflet is already a vendored dependency in this project (`gpx/static/gpx/vendor/SHA256SUMS`, checked in CI) — the current static map likely already renders via Leaflet with interaction disabled. Worth checking during planning whether "interactive map" is a config/feature change rather than a new library integration; this could substantially reduce FR-018's actual cost.

## Non-Goals

- **No accommodation waypoint entity in this slice**: FR-021 (a standalone record with description/photo, placed between stages) is fast-follow, not built this week. Only the generic "stage break" marker (FR-019) ships.
- **No manual stage reordering**: stage order is always derived from GPS timestamp; there is no drag-to-reorder UI or manual override in this slice.
- **No whole-trip/per-stage statistics in this slice**: FR-022 is fast-follow — existing single-file distance/duration/elevation stats are not extended to multi-stage aggregation this week (v1's stats display continues to reflect only what it already covers).
- **No product type or scale change**: still a responsive web app at small/solo scale; unchanged from v1.

## Quality Cross-Check

Completed on 2026-09-02. All elements present.

| Element | Status |
|---|---|
| Access Control | present (unchanged from v1) |
| Business Logic (one-sentence rule) | present (modified rule) |
| Project artifacts | present |
| Timeline-cost acknowledged | present (1-week scoped-down slice, within threshold) |
| Non-Goals | present (4 entries) |
| Preserved behavior | present (Constraints & Preserved Behavior section) |
