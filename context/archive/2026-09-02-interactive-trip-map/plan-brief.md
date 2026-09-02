# Interactive Trip Map — Plan Brief

> Full plan: `context/changes/interactive-trip-map/plan.md`

## What & Why

VeloLog's trip-detail map currently behaves like a static image — every Leaflet
interaction handler is explicitly disabled. This closes the PRD's second must-have gap
for milestone M-02: the user can pan and zoom the route instead of viewing a fixed
picture of it. Applies to every trip, single-stage or multi-stage.

## Starting Point

`gpx/static/gpx/map.js` already vendors and renders Leaflet 1.9.4 (tile layer, polyline,
start/finish markers, `fitBounds`) — it just initializes the map with `dragging`,
`scrollWheelZoom`, `touchZoom`, `doubleClickZoom`, `keyboard`, `boxZoom`, `tapHold`, and
`zoomControl` all set to `false`, per a deliberate v1 decision recorded in the file's own
comments ("FR-015 ... parked for v2"). No test in the repo pins these flags, so flipping
them is safe from a regression standpoint.

## Desired End State

A user can drag to pan, pinch/double-click to zoom, use keyboard arrows once focused, and
click a `+`/`-` zoom control — on any trip detail page. Scroll-wheel zoom stays off until
the user clicks the map once (a hint says so), avoiding the common trap where scrolling
past an embedded map hijacks the page scroll into a map zoom.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Scroll-wheel zoom | Click-to-enable (Leaflet standard pattern) | Enabling it outright traps page-scroll over the map; a hint + one-click gate avoids that without giving up scroll zoom entirely | Plan |
| Which handlers enable | dragging, touchZoom, doubleClickZoom, keyboard | Covers pan + mobile/desktop zoom + accessibility; `boxZoom`/`tapHold` left off as low-value | Plan |
| Zoom control | Show, default top-left position | Zero extra config, matches the standard mental model of a map widget | Plan |
| Drag cursor | No CSS change | Leaflet's vendored CSS already applies `.leaflet-grab`/`grabbing` automatically once dragging is enabled — an explicit override would be dead-redundant code | Plan |
| Test coverage | Manual verification + existing Python suite as regression guard | No JS test harness exists in this repo, and `test-plan.md` deliberately scopes map testing to server-rendered config, not Leaflet's interactive behavior | Plan |

## Scope

**In scope:** `gpx/static/gpx/map.js` interaction flags, zoom control, and a JS-injected
click-to-enable scroll-zoom hint.

**Out of scope:** `boxZoom`, `tapHold`, any CSS changes, any template changes, any
server-side/data-model changes, any new JS test infrastructure.

## Architecture / Approach

Single-file client-side config change. `L.map("map", {...})` options flip from all-`false`
to interactive; a small `L.Control` subclass adds the scroll-zoom hint and a
`map.once("click", ...)` handler enables `scrollWheelZoom` on first interaction. No
server-side payload, template, or CSS changes are needed.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Flip map interactivity | Pan/zoom/keyboard interaction + click-to-enable scroll zoom | Low — config flip on already-vendored, already-rendering code; risk is limited to a manual-verification miss (no JS test harness to catch a regression automatically) |

**Prerequisites:** None.
**Estimated effort:** Single short session — one file, one phase.

## Open Risks & Assumptions

- No JS test harness exists, so a future accidental revert of these flags would only be
  caught manually, not by CI — accepted per the roadmap's own scoping of this slice as
  low-risk and per `test-plan.md`'s standing decision not to test Leaflet internals from
  Python.

## Success Criteria (Summary)

- User can drag, pinch/double-click, keyboard-navigate, and use the zoom control to
  interact with the trip map.
- Scroll-wheel zoom is gated behind a first click, with a visible hint, so page scroll is
  never hijacked.
- Existing Python test suite passes unchanged, proving the server-rendered contract
  `map.js` depends on wasn't disturbed.
