# Map library research — S-03 (`upload-gpx-and-view-map`)

- **Date:** 2026-08-24
- **Method:** External research (exa.ai web search) — see `AGENTS.md` research discipline (internal = codebase, external = library/ecosystem choices).
- **Question:** Which map library should render the GPX route for S-03's "static map" requirement, given it must also support the parked FR-015 (interactive map) and the parked idea of viewing/selecting from multiple GPX tracks on one map?

## Architectural fork

S-03's "static map image" outcome can be satisfied two ways:

1. **Server-side rendered image** — generate a PNG/SVG from the GPX track on the backend, no JS map library involved.
2. **Client-side JS map library, configured non-interactively** — render with a real map library but disable pan/zoom/drag controls so v1 behaves like a static image.

Recommendation: **(2)**. FR-015 (interactive map) and the parked multi-GPX viewing/selection idea are both explicitly future work on this same view (roadmap `## Parked`). Building a server-side renderer now means rebuilding the whole rendering path client-side later. A JS map library configured statically for v1 upgrades to interactive v2 by re-enabling controls — no rewrite.

## Client-side JS map libraries considered

| Library | Fit for S-03 (v1, static) | Fit for FR-015 / multi-GPX (v2) | Notes |
|---|---|---|---|
| **Leaflet + `leaflet-gpx`** ✅ recommended | Trivial: `L.GPX(url).addTo(map)`; disable `dragging`, `scrollWheelZoom`, `zoomControl` for a static look | `leaflet-gpx` natively accepts an array of GPX sources, each with its own `polyline_options` (color) — multi-track display and layer-toggle/selection is a thin wrapper around Leaflet's built-in layer control | ~40KB, no build step, raster tiles (OSM), no API key/cost. Actively maintained (BSD-2, 618★, last release 2025). Serves the GPX file directly from Django media/static — no server-side transform needed. |
| MapLibre GL JS | Possible but heavier | Strong — WebGL, smooth multi-layer styling | ~200KB, steeper learning curve, needs a vector-tile source or raster fallback; no existing vector-tile pipeline in this project. Overkill for a solo 2-week MVP. |
| OpenLayers | Possible | Strongest projection/editing support | Heaviest (~500KB), largest API surface — justified only by non-Mercator projections or editing tools, neither needed here. |

## Server-side static image alternative (rejected)

- `py-staticmaps` (Python, renders PNG/SVG from a GPX track via `gpxpy`) — genuinely produces a static image server-side, and would integrate cleanly with Django. Rejected because it's a dead end for FR-015: the interactive/multi-track work would have to be built again from scratch client-side, duplicating the "render the route" effort.

## Recommendation

**Leaflet + `leaflet-gpx`**, served as a static JS asset (via `whitenoise`/templates — no new backend dependency), rendered on an OSM raster tile layer with `dragging: false`, `scrollWheelZoom: false`, `zoomControl: false` (or similar) for v1's static feel.

- Satisfies S-03 exactly: upload GPX → render route, empty state if none uploaded.
- Compatible with the Django/SQLite/Railway stack (`tech-stack.md`) — pure static asset, no new server dependency, no API key/cost.
- Extends directly to FR-015 and the parked multi-GPX/selection idea: re-enable map controls and pass multiple `L.GPX` layers with a layer-selector UI — no rewrite of the rendering path.

## Addendum (2026-08-24): elevation profile chart, hover-synced with the map

New parked idea evaluated: a chart below the map (x-axis = trip distance, y-axis = terrain elevation), where hovering the chart shows a linked pointer on the map's GPX track (and, implicitly, the reverse — hovering the track highlighting the chart position).

This does not change the recommendation above — it's an argument *for* it. Both leading options are Leaflet plugins that only make sense once Leaflet is already the map library:

| Library | Fit | Notes |
|---|---|---|
| **`raruto/leaflet-elevation`** ✅ recommended | Purpose-built for exactly this: d3-based elevation profile with distance on x-axis, altitude on y-axis, and a `followMarker` option that syncs a map marker to chart hover position out of the box | Loads GPX/GeoJSON/TCX directly (`controlElevation.load(url)`) — reuses the same GPX file already served for `leaflet-gpx`. Actively maintained, MIT-style license, used in production by multiple public route-viewer sites. Also supports slope/speed chart variants and multi-track hover-to-toggle, which lines up with the parked multi-GPX idea too. |
| `GIScience/Leaflet.Heightgraph` | Also fits | d3-based height profile with explicit `mapMousemoveHandler`/`mapMouseoutHandler` for map↔chart sync; more manual wiring than `leaflet-elevation`'s built-in `followMarker`, and more geared toward highlighting route segments by attribute (e.g. surface type) than a plain elevation-vs-distance chart. |
| MapTiler SDK elevation profile control | Works, but ties the stack to MapTiler's hosted platform/API key | Rejected — no vector-tile/MapTiler dependency exists elsewhere in this stack; would introduce a new external service for a feature Leaflet already covers for free. |

**Recommendation:** `raruto/leaflet-elevation` alongside `leaflet-gpx` — same GPX file, same Leaflet map instance, no new backend dependency, and the hover-sync behavior this feature needs is a built-in option (`followMarker: true`) rather than something to hand-build.
