<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Whole-Trip Aggregate Statistics Implementation Plan

- **Plan**: context/changes/multi-stage-trip-stats/plan.md
- **Mode**: Deep
- **Date**: 2026-09-04
- **Verdict**: SOUND (after fixes; REVISE at initial review)
- **Findings**: 0 critical, 2 warnings, 1 observation — all fixed

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | WARNING (fixed) |
| Blind Spots | WARNING (fixed) |
| Plan Completeness | WARNING (fixed) |

## Grounding

8/8 paths ✓, all cited line ranges verified against source (`gpx/statistics.py`,
`gpx/stages.py`, `trips/views.py`, `gpx/views.py`, `trips/templates/trips/trip_detail.html`,
`tests/trips/test_trip_detail_stats.py`) ✓, brief↔plan ✓.

## Findings

### F1 — Proposed helper contradicts the codebase's own anti-getattr rationale

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architectural Fitness
- **Location**: Phase 1, Item 1 (`_summed_or_none(tracks, field_name, formatter)`)
- **Detail**: `gpx/statistics.py:build_trip_stats` deliberately spells out its four field
  reads instead of looping over `STATS_FIELDS` with `getattr`, with an explicit comment
  explaining why (typo-safety under `mypy --strict`). The plan's proposed helper signature
  took a string field name — the exact shape the existing code rejected for that reason.
- **Fix**: Give the helper an explicit getter callable per field (e.g.
  `_summed_or_none(tracks, lambda t: t.distance_meters, format_distance)`) instead of a
  string field name, keeping every field access statically typed under `mypy --strict`.
- **Decision**: FIXED (Fix in plan — Phase 1, Item 1 contract rewritten)

### F2 — Collapsing per-stage details removes a no-JS-required view of stats

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 3, Item 1 (Bootstrap collapse markup)
- **Detail**: The Stages section is today plain, always-visible markup with no JS
  dependency. The plan hid it behind a Bootstrap-JS-only collapse toggle (`<button>`) with
  no no-JS fallback — unlike the existing map block, which already degrades to a text
  message if its own JS/assets fail.
- **Fix B applied**: Trigger changed to `<a href="#stage-details" ... data-bs-toggle="collapse">`
  plus a `#stage-details:target { display: block !important; }` CSS rule, so a same-page
  navigation reveals the section even without Bootstrap's JS. Added manual verification
  step 3.15 and noted the mitigation in the plan-brief's Open Risks.
- **Decision**: FIXED (Fix B — anchor-link fallback)

### F3 — GpxUploadView's parity docstring warning isn't updated to name the new key

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2, Item 2 (`gpx/views.py`)
- **Detail**: Phase 2 Item 1 instructed updating `TripDetailView`'s docstring parity
  warning; Item 2 did not give the equivalent instruction for `GpxUploadView`, leaving the
  two docstrings asymmetric after the phase.
- **Fix**: Added the same docstring-update instruction to Phase 2 Item 2.
- **Decision**: FIXED (Fix in plan)
