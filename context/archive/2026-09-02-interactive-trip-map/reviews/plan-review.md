<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Interactive Trip Map Implementation Plan

- **Plan**: `context/changes/interactive-trip-map/plan.md`
- **Mode**: Deep
- **Date**: 2026-09-02
- **Verdict**: REVISE (all findings fixed during triage — see Decisions below)
- **Findings**: 0 critical, 3 warnings, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

6/6 paths ✓ (`gpx/static/gpx/map.js`, `tests/trips/test_trip_detail_map.py`,
`tests/test_static_references.py`, `gpx/static/gpx/vendor/leaflet/leaflet.css`,
`static/css/style.css`, `context/foundation/test-plan.md`), 3/3 symbols ✓
(`map.once`, `L.Control.extend`, Leaflet's auto-`tabIndex` on keyboard-enabled maps —
all confirmed present in the vendored `leaflet.js`), brief↔plan ✓

## Findings

### F1 — Scroll-zoom hint may never dismiss via control/drag/keyboard use

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment / Blind Spots
- **Location**: Phase 1, Change 2 (Click-to-enable scroll zoom)
- **Detail**: The plan bound enabling scroll-wheel zoom to a single
  `map.once("click", ...)` listener. Leaflet's built-in controls (including the zoom
  control this plan re-enables) call `L.DomEvent.disableClickPropagation` on their own
  DOM container, so a zoom-control click never reaches the map as a `"click"` event
  (confirmed present in the vendored `leaflet.js`). Leaflet also suppresses the
  synthetic `"click"` fired after a drag gesture. A user who only pans, or only uses the
  zoom control/keyboard, would never trigger the handler — scroll-wheel zoom would never
  enable and the hint would never disappear, undercutting the plan's own Desired End
  State promise.
- **Fix**: Broaden the trigger to `map.once("dragstart zoomstart click", ...)` so
  panning, zoom-control use, or a literal click all enable scroll zoom and dismiss the
  hint.
- **Decision**: FIXED (applied to plan.md, Phase 1 Change 2 Contract)

### F2 — Static-reference test check can pass by skipping, not verifying

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness / Blind Spots
- **Location**: Phase 1, Automated Verification
- **Detail**: `tests/test_static_references.py` skips itself (not fails) locally when
  no staticfiles manifest exists, per its own docstring — it only runs for real in CI,
  where `collectstatic` precedes it. The plan listed running this test without first
  running `collectstatic`, so a local "pass" could mean "skipped," not "verified."
- **Fix**: Add `uv run python manage.py collectstatic --noinput` immediately before
  running `tests/test_static_references.py` in Automated Verification, matching the
  order `.github/workflows/deploy.yml`'s `gates` job already enforces.
- **Decision**: FIXED (applied to plan.md Phase 1 Automated Verification and Progress 1.2)

### F3 — Top-of-file header comment left stale, not listed for update

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1, Change 1 (Map initialization options) — Contract
- **Detail**: `gpx/static/gpx/map.js:1` opens with "Draws an uploaded GPX route as a
  map that behaves like a static image." The plan's Contract only called out updating
  the FR-015 block comment near the options (lines 55-57), missing this top-of-file
  docstring, which becomes false the moment interactivity ships.
- **Fix**: Add the file's top-of-file header comment (line 1) to the list of comments
  Change 1 must revise, alongside the FR-015 block comment.
- **Decision**: FIXED (applied to plan.md Phase 1 Change 1 Contract)
