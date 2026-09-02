# Interactive Trip Map Implementation Plan

## Overview

Flip the trip-detail Leaflet map from a static "picture of the route" (every interaction
handler disabled, zoom control hidden) to a genuinely interactive pan/zoom map, closing
the PRD's second must-have gap for M-02 (S-02, `interactive-trip-map`). Applies to every
trip, single-stage or multi-stage.

## Current State Analysis

`gpx/static/gpx/map.js:53-66` initializes `L.map("map", {...})` with `dragging`,
`scrollWheelZoom`, `touchZoom`, `doubleClickZoom`, `keyboard`, `boxZoom`, `tapHold`, and
`zoomControl` all explicitly `false` — a deliberate v1 decision recorded in the file's own
comment as "FR-015 (an interactive map) is parked for v2." Leaflet 1.9.4 is already
vendored and rendering (tile layer, polyline, start/finish markers, `fitBounds`); no new
library integration is needed.

No test in `tests/` asserts any of these interaction flags — `tests/trips/test_trip_detail_map.py`
only asserts the `map-config` JSON payload shape (`points`/`bounds`/`icons`) and the
`#map` container/fallback markup byte-for-byte (its regexes pin that markup), never
Leaflet init options. `context/foundation/test-plan.md` explicitly scopes map testing to
"the map configuration the server hands the page," not rendered/interactive behavior —
so this change has no Python test to update and no JS test harness exists in the repo to
add one to.

## Desired End State

A user can drag to pan, pinch or double-click to zoom, use arrow keys once the map has
focus, and click the `+`/`-` zoom control — on every trip detail page, single-stage or
multi-stage. Scroll-wheel zoom is off by default and turns on only after the user clicks
the map once (avoiding the standard trap where scrolling the page with the cursor over an
embedded map hijacks the scroll into a zoom). Verified by: `pytest` staying green
(proving the server-rendered container/config contract is untouched) plus a manual pass
in a browser exercising every enabled interaction.

### Key Discoveries:

- `gpx/static/gpx/map.js:53-66` — the single place all eight interaction flags live; no
  other file references them.
- `tests/trips/test_trip_detail_map.py` pins the `#map` container's HTML byte-for-byte via
  regex — any new hint UI must be injected by `map.js` at runtime (a Leaflet control),
  never by editing `trips/templates/trips/trip_detail.html`, or the pinned-markup tests
  break for reasons unrelated to this change.
- `gpx/static/gpx/vendor/leaflet/leaflet.css:219,232-238` already ships `.leaflet-grab`
  (`cursor: grab`) and `.leaflet-dragging .leaflet-grab` (`cursor: grabbing`), which
  Leaflet applies to the map container automatically once `dragging: true`. No CSS
  addition is needed for the drag cursor — `static/css/style.css` stays untouched.
- `map.js` is app code, not a vendored asset, so it is outside
  `gpx/static/gpx/vendor/SHA256SUMS` and this change needs no integrity-manifest update.

## What We're NOT Doing

- Not enabling `boxZoom` or `tapHold` — not requested, and both are low-value chrome
  (shift-drag zoom-box, touch-hold context menu) on a simple route-viewing map.
- Not adding any CSS to `static/css/style.css` — Leaflet's own vendored CSS already
  supplies the grab/grabbing cursor once dragging is enabled.
- Not changing `trips/templates/trips/trip_detail.html` — the `#map` container and
  `map-config` script tag stay byte-identical; the scroll-zoom hint is a Leaflet control
  injected by `map.js`, not new server-rendered markup.
- Not adding a JS test harness — consistent with `test-plan.md`'s standing scope decision
  to test only what the server hands the template, not Leaflet's rendered/interactive
  behavior.
- Not touching `gpx/map_config.py` or any server-side config payload — no new data needs
  to reach the client; the interaction flags are static per-load Leaflet options.

## Implementation Approach

A single, self-contained edit to `gpx/static/gpx/map.js`: flip the four requested
interaction flags to `true`, re-enable the zoom control at its Leaflet default position
(top-left), and replace the `scrollWheelZoom: false` intent with a click-to-enable
pattern using a small Leaflet control as the hint — the standard approach used by
Wikipedia/OSM embeds to avoid trapping page scroll. Nothing else in the codebase changes.

## Phase 1: Flip map interactivity

### Overview

Enable pan/zoom/keyboard interaction on the trip-detail map, with scroll-wheel zoom
gated behind a first click, and remove the now-stale "static image" framing from the
file's comments.

### Changes Required:

#### 1. Map initialization options

**File**: `gpx/static/gpx/map.js`

**Intent**: Turn the map from a non-interactive image into a pannable, zoomable widget.
Enable dragging (pan), touchZoom and doubleClickZoom (mobile/desktop zoom gestures), and
keyboard (arrow keys + `+`/`-` once focused). Leave `boxZoom` and `tapHold` disabled —
out of scope per user decision. Re-enable `zoomControl` at Leaflet's default `topleft`
position.

**Contract**: In the `L.map("map", {...})` options object (currently at lines 53-66),
change `dragging`, `touchZoom`, `doubleClickZoom`, `keyboard`, and `zoomControl` from
`false` to `true`. Leave `boxZoom: false` and `tapHold: false` unchanged. `scrollWheelZoom`
stays `false` at init time (handled by the click-to-enable control below, not a plain
flag flip). Update the block comment above the options (currently "FR-015 ... is parked
for v2 ... every interaction handler is off") to reflect that FR-015 is now live and
describe the click-to-enable exception for scroll zoom. Also update the file's
top-of-file header comment (line 1, currently "Draws an uploaded GPX route as a map that
behaves like a static image.") — it becomes stale the moment interactivity ships and is
the first thing a future reader trusts.

#### 2. Click-to-enable scroll zoom

**File**: `gpx/static/gpx/map.js`

**Intent**: Avoid the classic embedded-map trap where a user scrolling the page with
their cursor over the map gets stuck zooming the map instead of scrolling past it.
Scroll-wheel zoom starts disabled; a small on-map hint tells the user to click to enable
it; the first click enables it permanently for that page view and removes the hint.

**Contract**: After `map.fitBounds(...)`, register a Leaflet custom control (extending
`L.Control`) positioned `topright`, rendering a short text hint (e.g. "Click map to
enable scroll zoom"). Attach a one-time handler on the map bound to
`map.once("dragstart zoomstart click", ...)` — not `"click"` alone — that calls
`map.scrollWheelZoom.enable()` and removes the hint control from the map. Leaflet's
built-in controls (including the zoom control this plan re-enables) call
`L.DomEvent.disableClickPropagation` on their own DOM element, so a zoom-control click
never reaches the map as a `"click"` event; Leaflet also suppresses the synthetic
`"click"` fired after a drag gesture. Binding to `dragstart`/`zoomstart` as well ensures
panning or using the zoom control also enables scroll zoom and dismisses the hint, not
only a literal click on the map surface. This control must be created entirely in JS —
no new element in `trips/templates/trips/trip_detail.html` — so the template's pinned
`#map` markup stays byte-identical for `tests/trips/test_trip_detail_map.py`. Since the
hint markup is attacker-uncontrolled static text (not derived from `config`), it can be
set via `innerHTML`/`textContent` without reopening the file's existing "coordinates are
always data, never inline script" invariant — no user-controlled value enters this
string.

### Success Criteria:

#### Automated Verification:

- `uv run pytest tests/trips/test_trip_detail_map.py` passes unchanged — the `#map`
  container, `map-config` JSON payload, and static-file references stay untouched
- `uv run python manage.py collectstatic --noinput` then `uv run pytest
  tests/test_static_references.py` passes unchanged — `gpx/map.js` is still correctly
  referenced under the hashed staticfiles manifest. `test_static_references.py` skips
  itself (rather than failing) when no manifest has been collected, so `collectstatic`
  must run first or this step gives false confidence by skipping instead of checking,
  same order `.github/workflows/deploy.yml`'s `gates` job enforces
- Full suite stays green: `uv run pytest --cov`
- Lint/format/type gates stay green: `ruff`, `black`, `isort`, `mypy` (JS is unaffected by
  these Python tool gates; run them to confirm no incidental Python changes)

#### Manual Verification:

- On a trip detail page with an uploaded GPX track: drag the map and confirm it pans
- Pinch-zoom (or double-click) and confirm the map zooms
- Click the `+`/`-` zoom control and confirm it zooms
- Tab to the map and use arrow keys / `+`/`-` and confirm keyboard pan/zoom works
- Scroll the mouse wheel over the map before clicking it and confirm the page scrolls
  normally (zoom does NOT trigger) and the hint is visible
- Click the map once, then scroll the wheel over it and confirm the map now zooms and the
  hint is gone
- Confirm the drag cursor shows `grab` at rest and `grabbing` while dragging (from
  Leaflet's vendored CSS, no new styling needed)
- Confirm a trip with no uploaded GPX file still renders the `.map-fallback` message
  unchanged (this code path is untouched, but verify no regression)

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human that the manual testing was
successful. This is the plan's only phase.

---

## Testing Strategy

### Unit Tests:

- No new unit tests — per `test-plan.md`'s standing scope decision, Leaflet interaction
  behavior is not asserted from Python tests, and this repo has no JS test harness.

### Integration Tests:

- The existing `tests/trips/test_trip_detail_map.py` suite serves as the regression
  guard: it must keep passing unchanged, proving the server-rendered contract (container
  markup, config JSON, static references) that `map.js` depends on wasn't disturbed.

### Manual Testing Steps:

1. Open a trip detail page for a trip with an uploaded GPX track.
2. Drag the map — confirm it pans.
3. Scroll the mouse wheel over the map before clicking — confirm the page scrolls, the
   map does not zoom, and the hint control is visible.
4. Click the map once — confirm the hint disappears and scroll-wheel zoom now works.
5. Double-click and pinch (on a touch device or browser touch emulation) — confirm zoom.
6. Tab to the map and use arrow keys and `+`/`-` — confirm keyboard pan/zoom.
7. Click the `+`/`-` zoom control buttons — confirm they zoom.
8. Open a trip with no uploaded GPX file — confirm the fallback message still renders and
   nothing throws in the console.

## Performance Considerations

None — this is a client-side configuration change to an already-loaded Leaflet instance;
no additional network requests or payload size change.

## Migration Notes

None — no data model or server-side change.

## References

- Roadmap slice: `context/foundation/roadmap.md` → S-02 (`interactive-trip-map`)
- PRD refs: US-02 (map-interactivity clause); Scope of Change — "user views the trip
  route on an interactive (pan/zoom) map instead of a static image"
- Prior static-map decision: `gpx/static/gpx/map.js:55-57` (comment being reversed by
  this change)
- Test scope decision: `context/foundation/test-plan.md:323`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands.
> Do not rename step titles.

### Phase 1: Flip map interactivity

#### Automated

- [x] 1.1 `uv run pytest tests/trips/test_trip_detail_map.py` passes unchanged
- [x] 1.2 `uv run python manage.py collectstatic --noinput` then `uv run pytest
      tests/test_static_references.py` passes unchanged
- [x] 1.3 Full suite stays green: `uv run pytest --cov`
- [x] 1.4 Lint/format/type gates stay green: `ruff`, `black`, `isort`, `mypy`

#### Manual

- [x] 1.5 Drag pans the map
- [x] 1.6 Pinch/double-click zooms the map
- [x] 1.7 Zoom control (`+`/`-`) zooms the map
- [x] 1.8 Keyboard pan/zoom works once the map has focus
- [x] 1.9 Scroll-wheel zoom is disabled until first click, page scrolls normally over the
      map beforehand, hint is visible
- [x] 1.10 After first click, scroll-wheel zoom works and the hint is gone
- [x] 1.11 Drag cursor shows grab/grabbing correctly
- [x] 1.12 No-GPX trip still renders the fallback message unchanged
