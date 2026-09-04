# Whole-Trip Aggregate Statistics Implementation Plan

## Overview

Add a whole-trip aggregate statistics block (distance, recorded time, elevation gained,
elevation lost — each summed across every stage) to the trip detail view, presented above
the existing per-stage "Stages" section. The Stages section becomes a collapsible block,
collapsed by default. This is roadmap slice S-03 (`multi-stage-trip-stats`), explicitly a
stretch goal narrowed by the PRD to aggregation-only (per-stage figures already ship via
S-01).

## Current State Analysis

- `gpx/statistics.py:build_trip_stats(track)` (lines 257-296) is the only stats builder
  today — single-track, returns `None` if the track is `None` or if all four stat columns
  (`distance_meters`, `duration_seconds`, `elevation_gain_meters`, `elevation_loss_meters`)
  are null. It is called once per stage by `gpx/stages.py:build_stages` (lines 114-131).
- `TripStats` (`gpx/statistics.py:241-254`) is a frozen dataclass with four `str | None`
  fields, already formatted by `format_distance`/`format_duration`/`format_elevation`
  (`gpx/statistics.py:175-238`), which are `None`-in/`None`-out and never collapse a real
  `0.0` into a missing-data sentence.
- `gpx/stages.py:trip_span(tracks)` (lines 60-93) is the existing precedent for an
  all-or-nothing aggregate derived across stages: it returns `None` unless every stage
  qualifies, rather than silently degrading to a partial answer.
- Two view render paths build the same template context and must stay in parity:
  `TripDetailView.get_context_data` (`trips/views.py:84-104`) and `GpxUploadView`'s
  re-render path (`gpx/views.py:73-90`) — both already assemble `stages`, `map_config`,
  `chronology_established`, and `trip_span` identically; a new context key must be added
  to both or one path silently regresses.
- `trips/templates/trips/trip_detail.html:113-201` is the existing per-stage "Stages"
  section — one `dl.row` block per stage (146-174), each of the four stats gated
  independently on `is not None`. No collapse/accordion markup exists anywhere in this
  codebase yet; Bootstrap's JS bundle (which includes the Collapse component) is already
  loaded unconditionally (`templates/base.html:51`) but unused.
- `tests/trips/test_trip_detail_stats.py` pins `DETAIL_PAGE_QUERIES = 4` (line 40) — the
  page's whole query budget. The new aggregate is computed in Python from the same track
  list `build_stages` already materializes, so it must add zero queries.

## Desired End State

The trip detail page shows a "Trip totals" block (whole-trip sums) directly after the
per-stage "Stages" heading's current position is replaced by: totals first, then a
collapsed-by-default "Stages" section a rider expands to see per-stage figures. Each of
the four totals renders independently — a stage missing a figure blanks only that one
total with a "not recorded"-style note, never the other three, and never a silent zero.
Verify by: visiting a multi-stage trip's detail page, confirming the totals block renders
above a collapsed Stages section, expanding it, and confirming the four totals equal the
sum of the visible per-stage figures.

### Key Discoveries:

- `build_trip_stats`'s all-null gate (`gpx/statistics.py:289-290`) doesn't fit the
  aggregate case: an aggregate should show whichever of the four figures every stage
  actually has, not go dark the moment any single stage lacks any single figure — the
  confirmed design decision is independent per-figure gating, not one shared gate.
- `trip_span`'s "derived every render, stored nowhere" discipline (`gpx/stages.py:9-13`)
  and its `Sequence[GpxTrack]` input shape are the pattern to follow for the new
  aggregation function.
- Bootstrap's `data-bs-toggle="collapse"` trigger element automatically gains/loses a
  `.collapsed` CSS class as the target opens/closes — a text-swapping toggle button needs
  no new JavaScript, only two `<span>`s and a CSS rule keyed off that class.

## What We're NOT Doing

- No new database columns or migrations — all four source columns already exist on
  `GpxTrack`.
- No "moving time"/"average speed"/"max speed" aggregation — parked separately on the
  roadmap (unreliable `gpxpy.get_moving_data()` on synthetic input).
- No partial-sum-with-label option — a figure is either shown in full (every stage has
  it) or replaced by a "not recorded" note; there is no partial/approximate total.
- No persistence of the Stages section's expanded/collapsed state across page loads
  (no `localStorage`) — every load starts collapsed.
- No accommodation-waypoint entity, no manual stage reordering, no other roadmap-parked
  scope.

## Implementation Approach

Add one new pure function, `build_whole_trip_stats(tracks)`, next to `build_trip_stats` in
`gpx/statistics.py`, reusing the existing `TripStats` shape and formatters so the template
renders both blocks with the same stat markup. Wire its result into both view render paths
under a new `whole_trip_stats` context key, then add the "Trip totals" section and wrap
the existing "Stages" section in a Bootstrap collapse in the template.

## Phase 1: Whole-trip aggregation logic

### Overview

Add the pure aggregation function and its unit tests. No views or templates touched yet.

### Changes Required:

#### 1. Whole-trip stats builder

**File**: `gpx/statistics.py`

**Intent**: Add `build_whole_trip_stats(tracks: Sequence[GpxTrack]) -> TripStats | None`
that sums each of the four stat columns independently across `tracks`, returning `None`
only when `tracks` is empty. For each of the four fields: if every track in `tracks` has a
non-null value for that field, sum them and format with the matching `format_*` function;
otherwise that field is `None` in the result (same "not recorded" meaning `TripStats`
already carries). Add `from collections.abc import Sequence` to the module's imports
(mirrors `gpx/stages.py`'s existing use of the same input shape for `trip_span`).

**Contract**: Signature `build_whole_trip_stats(tracks: Sequence[GpxTrack]) -> TripStats | None`.
Reuses `TripStats`, `format_distance`, `format_duration`, `format_elevation` unchanged. A
small private helper (e.g. `_summed_or_none(tracks, field_name, formatter)`) avoids
repeating the four near-identical field computations; it must check `is None`, never
falsy, exactly like `build_trip_stats`'s existing all-null guard — a track legitimately
stored at `distance_meters = 0.0` must count as present, not as missing.

### Success Criteria:

#### Automated Verification:

- [ ] Unit tests pass: `uv run pytest tests/gpx/test_gpx_statistics.py -v`
- [ ] Full suite still green: `uv run pytest --cov`
- [ ] Type checking passes: `uv run mypy`
- [ ] Linting passes: `uv run ruff check .`
- [ ] Formatting passes: `uv run black --check .`
- [ ] Import order passes: `uv run isort --check-only .`

#### Manual Verification:

- None for this phase — no user-visible surface yet.

---

## Phase 2: View context wiring

### Overview

Expose `build_whole_trip_stats`'s result to the template from both render paths, keeping
the existing parity contract between `TripDetailView` and `GpxUploadView`.

### Changes Required:

#### 1. Trip detail view

**File**: `trips/views.py`

**Intent**: In `TripDetailView.get_context_data` (lines 84-104), compute
`whole_trip_stats = build_whole_trip_stats(tracks)` using the same `tracks` list already
built at line 98, and add it to `context`. Update the method's docstring's parity warning
(lines 84-95) to name the new key alongside `map_config`/`chronology_established`/
`trip_span`.

**Contract**: New context key `whole_trip_stats: TripStats | None`. Import
`build_whole_trip_stats` from `gpx.statistics` alongside the existing `gpx.stages` import.

#### 2. GPX upload re-render path

**File**: `gpx/views.py`

**Intent**: In `GpxUploadView.get_context_data` (lines 73-90), add the identical
`whole_trip_stats` key using the same `tracks` list already built at line 84, so a
rejected upload's re-render carries the same whole-trip totals as a normal page load
rather than silently dropping them (the exact failure mode the method's own docstring,
lines 74-81, already warns about for the other three keys).

**Contract**: Same context key and same import as Phase 2 item 1.

### Success Criteria:

#### Automated Verification:

- [ ] Full suite still green: `uv run pytest --cov`
- [ ] Type checking passes: `uv run mypy`
- [ ] Linting passes: `uv run ruff check .`
- [ ] Formatting passes: `uv run black --check .`

#### Manual Verification:

- None for this phase — the template does not read the new key yet, so no visible change.

---

## Phase 3: Template, collapse UI, and page tests

### Overview

Render the new "Trip totals" block, wrap the existing "Stages" section in a Bootstrap
collapse (default collapsed), add the text-swapping toggle, and add page-rendering tests
covering both the new block and the collapse behavior.

### Changes Required:

#### 1. Trip totals section + collapsible Stages

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: Inside the existing `{% if stages %}` branch (line 62), after the "Route" /map
block and before the current "Stages" heading (line 113), add a new `<div>` section headed
"Trip totals" that renders `whole_trip_stats`'s four fields using the same `is not None`
gating and "Not recorded — ..." sentence style as the per-stage block (lines 157-173), but
worded to name the trip rather than a single file (e.g. "Not recorded — not every stage
has this figure."). Then wrap the existing "Stages" `<div class="mb-4">...</div>` block
(lines 113-201) in a Bootstrap collapse: the outer div's id becomes the collapse target
(e.g. `id="stage-details"`, classes `collapse` and no `show`), and a toggle `<button>`
(`type="button"`, `data-bs-toggle="collapse"`, `data-bs-target="#stage-details"`,
`aria-expanded="false"`, `aria-controls="stage-details"`, starting with class `collapsed`)
sits above it carrying two `<span>`s — "Show per-stage details" and "Hide per-stage
details" — toggled by CSS keyed off Bootstrap's own `.collapsed` class on the button, no
new JavaScript.

**Contract**:
```css
/* static/css/style.css */
button.collapsed .when-expanded { display: none; }
button:not(.collapsed) .when-collapsed { display: none; }
```
Template markup for the toggle:
```html
<button type="button" class="btn btn-outline-secondary btn-sm mb-2 collapsed"
        data-bs-toggle="collapse" data-bs-target="#stage-details"
        aria-expanded="false" aria-controls="stage-details">
    <span class="when-collapsed">Show per-stage details</span>
    <span class="when-expanded">Hide per-stage details</span>
</button>
<div class="collapse" id="stage-details">
  ... existing Stages heading + per-stage loop, unchanged ...
</div>
```

#### 2. Collapse toggle CSS

**File**: `static/css/style.css`

**Intent**: Add the two-rule CSS block above, keyed off Bootstrap's automatic
`.collapsed` class management on the toggle trigger — no other markup in this file is
affected.

**Contract**: Two new CSS rules, additive only.

#### 3. Page-rendering tests

**File**: `tests/trips/test_trip_detail_stats.py`

**Intent**: Add tests covering: (a) a multi-stage trip's "Trip totals" block renders above
the "Stages" heading with the correct summed distance/duration/elevation figures given
several `make_gpx_track` stages with full stats; (b) a stage missing one figure (e.g. no
`elevation_gain_meters`) blanks only that one whole-trip total, leaving the other three
totals showing real sums (independent-per-figure rule); (c) the "Stages" section's outer
div carries `collapse` but not `show` by default, and the toggle button starts with class
`collapsed` and `aria-expanded="false"`; (d) a single-stage trip still renders the "Trip
totals" block, with figures equal to that one stage's own; (e) a trip with zero stages
renders neither the totals block nor the Stages section, consistent with today's `{% if
stages %}` empty-state; (f) `GpxUploadView`'s rejected-upload re-render path (POST an
invalid file) renders the same whole-trip totals as a normal GET, proving context parity
between the two views. Update `DETAIL_PAGE_QUERIES` only if a real query count changes —
expected to stay at 4, since aggregation reads the same in-memory track list `build_stages`
already produced.

**Contract**: New `pytest.mark.django_db` test functions in the existing file, following
its established fixture style (`trip`, `make_gpx_track`, `auth_client`).

### Success Criteria:

#### Automated Verification:

- [ ] New and existing tests pass: `uv run pytest tests/trips/test_trip_detail_stats.py -v`
- [ ] Full suite still green: `uv run pytest --cov`
- [ ] Bite-proof harness still green: `uv run pytest -m bite_proof -v`
- [ ] Type checking passes: `uv run mypy`
- [ ] Linting passes: `uv run ruff check .`
- [ ] Formatting passes: `uv run black --check .`
- [ ] Import order passes: `uv run isort --check-only .`
- [ ] `manage.py check` passes: `uv run python manage.py check`
- [ ] No missing migration: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- Open a multi-stage trip's detail page: "Trip totals" renders above a collapsed "Stages"
  section; the toggle button reads "Show per-stage details".
- Click the toggle: the Stages section expands, the button now reads "Hide per-stage
  details", and the per-stage figures visibly sum to the totals shown above.
- Upload a rejected (invalid) GPX file to a trip that already has stages: the re-rendered
  page still shows the same whole-trip totals as before the failed upload.
- View a single-stage trip: the totals block still renders, matching that one stage's
  figures.
- View a trip with zero stages: neither the totals block nor the Stages section appear.

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human that the manual testing was
successful.

---

## Testing Strategy

### Unit Tests:

- `build_whole_trip_stats`: all four stats present across all stages → correct sums,
  formatted identically to `build_trip_stats`. One stage missing one field → that field
  `None`, others summed. Zero tracks → `None`. A track with a legitimate `0.0` value
  counts as present, not missing (mirrors `build_trip_stats`'s existing zero-vs-null test
  coverage in `tests/gpx/test_gpx_statistics.py`).

### Integration Tests:

- Full-page render across zero/one/multi-stage trips, both view render paths
  (`TripDetailView` GET, `GpxUploadView` rejected-upload re-render), verifying context
  parity and the collapse's default-collapsed markup.

### Manual Testing Steps:

1. Visit a multi-stage trip's detail page and confirm totals + collapsed Stages.
2. Toggle the Stages section open/closed and confirm the label swaps and figures line up.
3. Trigger a rejected upload and confirm totals survive the re-render.
4. Visit a single-stage and a zero-stage trip and confirm the block's presence/absence.

## Performance Considerations

`build_whole_trip_stats` runs in Python over the already-materialized `tracks` list
`build_stages` produces for each render — no new database query, so
`DETAIL_PAGE_QUERIES = 4` is expected to hold unchanged.

## Migration Notes

None — no schema change.

## References

- Roadmap slice: `context/foundation/roadmap.md` S-03 (`multi-stage-trip-stats`)
- PRD: `context/foundation/prd.md` — Fast-follow bullet, Non-Goals #3
- Precedent for all-or-nothing aggregation: `gpx/stages.py:60-93` (`trip_span`)
- Precedent for per-figure independent gating: `gpx/statistics.py:241-296` (`TripStats`,
  `build_trip_stats`)
- Original single-track stats slice: `context/archive/2026-08-27-trip-distance-duration-stats/plan.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Whole-trip aggregation logic

#### Automated

- [ ] 1.1 Unit tests pass: `uv run pytest tests/gpx/test_gpx_statistics.py -v`
- [ ] 1.2 Full suite still green: `uv run pytest --cov`
- [ ] 1.3 Type checking passes: `uv run mypy`
- [ ] 1.4 Linting passes: `uv run ruff check .`
- [ ] 1.5 Formatting passes: `uv run black --check .`
- [ ] 1.6 Import order passes: `uv run isort --check-only .`

### Phase 2: View context wiring

#### Automated

- [ ] 2.1 Full suite still green: `uv run pytest --cov`
- [ ] 2.2 Type checking passes: `uv run mypy`
- [ ] 2.3 Linting passes: `uv run ruff check .`
- [ ] 2.4 Formatting passes: `uv run black --check .`

### Phase 3: Template, collapse UI, and page tests

#### Automated

- [ ] 3.1 New and existing tests pass: `uv run pytest tests/trips/test_trip_detail_stats.py -v`
- [ ] 3.2 Full suite still green: `uv run pytest --cov`
- [ ] 3.3 Bite-proof harness still green: `uv run pytest -m bite_proof -v`
- [ ] 3.4 Type checking passes: `uv run mypy`
- [ ] 3.5 Linting passes: `uv run ruff check .`
- [ ] 3.6 Formatting passes: `uv run black --check .`
- [ ] 3.7 Import order passes: `uv run isort --check-only .`
- [ ] 3.8 `manage.py check` passes: `uv run python manage.py check`
- [ ] 3.9 No missing migration: `uv run python manage.py makemigrations --check --dry-run`

#### Manual

- [ ] 3.10 Multi-stage trip: Trip totals above collapsed Stages, toggle reads "Show per-stage details"
- [ ] 3.11 Toggle expands Stages, label swaps, figures sum to totals
- [ ] 3.12 Rejected upload re-render still shows whole-trip totals
- [ ] 3.13 Single-stage trip still renders the totals block
- [ ] 3.14 Zero-stage trip renders neither block
