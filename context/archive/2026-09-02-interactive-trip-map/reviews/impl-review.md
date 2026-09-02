<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Interactive Trip Map Implementation Plan

- **Plan**: context/changes/interactive-trip-map/plan.md
- **Scope**: Phase 1 of 1 (full plan)
- **Date**: 2026-09-02
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 1 warning, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Hint-control code inside the try block can corrupt the fallback contract on failure

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is a narrowly scoped reorder
- **Dimension**: Safety & Quality
- **Location**: gpx/static/gpx/map.js:97-120
- **Detail**: The new `ScrollZoomHint` control and `map.once(...)` handler (lines 99-120)
  sit inside the existing `try` block, after `fitBounds` has already attached tiles,
  polyline, and markers to the DOM. The file's own header comment (lines 14-19)
  documents an explicit contract: the `.map-fallback` paragraph is removed "on the
  success path and nowhere else." If any statement in the new block throws (e.g. a
  future Leaflet version reshaping `map.scrollWheelZoom`, or `L.Control`/`L.DomUtil`
  behaving unexpectedly), execution jumps to `catch`, which logs and returns —
  skipping the fallback-removal block at lines 131-134. That leaves a *partially
  rendered live map* coexisting with the "could not be loaded" fallback message,
  contradicting the documented contract. Likelihood is low (these are stable 1.9.4
  APIs) but the regression is real and easy to close off.
- **Fix**: Move the fallback-removal block (lines 131-134) to immediately after
  `map.fitBounds(...)` (line 97), before the hint-control code. The map is already
  fully drawn and functional at that point, so gating fallback removal on "core map
  exists" rather than "everything including the decorative hint succeeded" restores
  the documented contract — a failure in the hint control would then only skip the
  hint itself (scroll-zoom stays permanently disabled, no visible fallback overlap).
- **Decision**: FIXED — fallback removal moved to right after `map.fitBounds(...)`,
  before the hint-control code.

### F2 — `.leaflet-control-scroll-zoom-hint` has no matching CSS rule

- **Severity**: ⚠️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; not a correctness issue
- **Dimension**: Pattern Consistency
- **Location**: gpx/static/gpx/map.js:111
- **Detail**: The hint control's custom class renders with Leaflet's stock
  `.leaflet-bar` chrome only; no repo CSS targets
  `.leaflet-control-scroll-zoom-hint` for padding/width tuned to the longer text
  string. The plan explicitly scoped out any `static/css/style.css` change, so this
  is intentional, not a gap — flagged only for visibility in case the rendered hint
  looks cramped in manual testing.
- **Decision**: SKIPPED
