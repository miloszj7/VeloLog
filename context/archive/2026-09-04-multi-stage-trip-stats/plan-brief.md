# Whole-Trip Aggregate Statistics — Plan Brief

> Full plan: `context/changes/multi-stage-trip-stats/plan.md`

## What & Why

Add whole-trip aggregate statistics (distance, recorded time, elevation gained/lost,
summed across every stage) to the trip detail view, shown above a now-collapsible
per-stage "Stages" section. This is roadmap slice S-03 — a stretch goal, narrowed to
aggregation only since per-stage figures already ship via S-01.

## Starting Point

`gpx/statistics.py:build_trip_stats(track)` already formats one track's four stats; it's
called once per stage. No aggregation across stages exists anywhere in the codebase. The
existing `trip_span` function (`gpx/stages.py`) is the closest precedent — an all-or-
nothing derived value across a trip's stages, computed fresh on every render, stored
nowhere. Two view render paths (`TripDetailView`, `GpxUploadView`'s re-render) already
share an identical context-building contract that any new key must join.

## Desired End State

Opening a trip's detail page shows a "Trip totals" block with the summed distance,
recorded time, and elevation figures — each rendered independently, so one stage missing
a figure blanks only that figure, never the whole block. Below it, per-stage detail is
folded away by default behind a "Show per-stage details" toggle.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Partial-data rule | All-or-nothing per figure | Matches the existing `trip_span` precedent; never lets a missing stage's contribution vanish into an unlabeled partial sum | Plan |
| Granularity | Each of the 4 stats gates independently | Matches the existing per-stage stat block, where each already gates independently | Plan |
| Duration total | Sum of per-stage recorded time, labeled distinctly from the header's calendar span | Reuses existing `duration_seconds` semantics (excludes inter-stage gaps) with no new computation rule | Plan |
| Single-stage trips | Aggregate block always renders | No stage-count branching; values simply equal the one stage's own figures | Plan |
| Zero-stage trips | Aggregate block suppressed | Mirrors the existing Stages section's own empty-state gate | Plan |
| Collapse toggle | Text button swapping label via CSS keyed off Bootstrap's `.collapsed` class | Standard Bootstrap 5 pattern, zero new JavaScript | Plan |
| Collapse persistence | Always starts collapsed, no `localStorage` | Matches the stated instruction literally; zero storage code for a stretch/optional feature under a tight deadline | Plan |

## Scope

**In scope:** whole-trip sums for the four existing stat columns; independent per-figure
missing-data handling; a collapsible Stages section with a text-swapping toggle; parity
between both view render paths; unit + page-rendering tests.

**Out of scope:** new stat types (speed, moving time — parked separately); partial/labeled
sums; persisted collapse state; accommodation waypoints; manual stage reordering; any
schema/migration change.

## Architecture / Approach

A new pure function `build_whole_trip_stats(tracks)` in `gpx/statistics.py`, sitting
beside `build_trip_stats` and reusing its `TripStats` dataclass and formatters. Both views
compute it from the same in-memory track list `build_stages` already produces (zero new
queries) and expose it as a new `whole_trip_stats` context key. The template renders it in
a new "Trip totals" section and wraps the existing "Stages" block in a Bootstrap collapse.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Whole-trip aggregation logic | `build_whole_trip_stats` + unit tests | Getting the zero-vs-null distinction wrong (a real `0.0` must count as present) |
| 2. View context wiring | `whole_trip_stats` in both render paths | The two views drifting out of parity, as the existing docstrings already warn about |
| 3. Template, collapse UI, and page tests | Trip totals block + collapsible Stages + tests | First use of Bootstrap collapse in this codebase — no established pattern to copy |

**Prerequisites:** S-01 (`multi-stage-gpx-upload`) done — stages must exist to aggregate.
**Estimated effort:** ~1 session across 3 phases; explicitly the first item to drop if
time runs short before the 2026-09-10 deadline.

## Open Risks & Assumptions

- This is marked stretch/optional on the roadmap — if S-01/S-02 run long, this plan may
  never be implemented this milestone.
- Bootstrap's `.collapsed` class behavior on the toggle trigger is standard Bootstrap 5
  behavior but unverified in this specific codebase until Phase 3's manual testing.
- Mitigated: the toggle is an `<a href="#stage-details">` (not a `<button>`), with a
  `#stage-details:target` CSS rule as a no-JS fallback, so per-stage details stay reachable
  even if Bootstrap's JS bundle fails to load — verified manually in Phase 3 (step 3.15).

## Success Criteria (Summary)

- A rider opens any trip's detail page and sees whole-trip totals above a collapsed
  Stages section they can expand.
- A stage missing one figure never hides the other three whole-trip totals, and never
  silently reports a lower-than-real sum.
- A rejected upload's re-rendered page still shows the same whole-trip totals as before.
