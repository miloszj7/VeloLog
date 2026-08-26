# Python GPX processing libraries — S-03 (`upload-gpx-and-view-map`)

- **Date:** 2026-08-24
- **Method:** External research (exa.ai web search) — per `AGENTS.md` research discipline (external research answers "what should we do?").
- **Question:** Which Python library should parse/process uploaded GPX files server-side, for extracting track points (lat/lon/elevation) to feed map rendering (S-03) and later distance/duration stats (S-05)?

## Libraries considered

| Library | Summary | Fit for VeloLog |
|---|---|---|
| **`gpxpy`** ✅ recommended | The long-standing standard Python GPX parser (`tkrajina/gpxpy`). Parses GPX 1.0/1.1 into a clean object model (`gpx.tracks[].segments[].points[]` with `.latitude`, `.longitude`, `.elevation`, `.time`). Built-in utility methods for distance, moving/stationary time, max speed (with GPS-error heuristics), elevation gain/loss. Uses `lxml` if installed (2-3x faster than falling back to `minidom`). Can also serialize back to GPX XML. | Best fit: mature, widely used, actively maintained, well-documented, and its object model directly supplies what S-03 (points → map) and S-05 (distance/duration stats) both need — no need to add a second library later for stats. |
| `gpx` (`sgraaf/gpx`) | Newer, zero-dependency pure-Python package. Reading/writing/converting GPX, KML; schema validation against GPX 1.1; has a CLI. Actively documented (Read the Docs). | Viable alternative, but newer/less battle-tested than `gpxpy` and no meaningful advantage for VeloLog's simple "read points, compute stats" use case. Zero-dependency is a nice-to-have, not a requirement here. |
| `fastgpx` | Experimental, performance-focused GPX parser; benchmarks show large speedups over `gpxpy` (avoids `lxml` overhead) for bulk/critical-path parsing. Explicitly *not* a `gpxpy` replacement — narrow API surface, only for hot-path extraction. | Rejected — VeloLog uploads one GPX file per trip via a web request; there's no batch/performance-critical path that justifies an experimental, narrow-API library over the standard one. |
| `ezgpx` | Easy-to-use wrapper with simplification (Ramer-Douglas-Peucker), metadata stripping, GPX/KML/KMZ/FIT conversion. | Rejected for v1 — track simplification and multi-format conversion are not in scope (PRD v1 is single-file GPX only, FR-011 multi-stage/other formats parked); adds surface area VeloLog doesn't need yet. |
| `fitcxgp` | Rust-backed, ABI3 wheel; GPX/TCX/FIT read/write, claims up to 31x faster GPX parsing than `gpxpy`. Very new. | Rejected — introduces a compiled Rust extension dependency for a performance need VeloLog doesn't have (single small file per upload, not a bulk pipeline), and is far less proven than `gpxpy`. |
| `gpxo` | Wraps `gpxpy` output into a `pandas` DataFrame, adds `smooth()`, `plot()` (matplotlib), `folium_map()`. | Rejected — pulls in `pandas`/`numpy`/`matplotlib`/`folium` for a Django backend that only needs raw point lists to hand to the client-side Leaflet map (see `leaflet-context7-docs.md`); those plotting/mapping helpers duplicate what the frontend already does. |

## Recommendation

**`gpxpy`**, added via `uv add gpxpy` (per `AGENTS.md` hard rule — never raw `pip install`).

Rationale:
- Directly satisfies S-03: parse the uploaded file, extract `[(lat, lon), ...]` (and elevation if present) to serialize into the template/JSON consumed by the Leaflet `Polyline`/`Marker` rendering path documented in `leaflet-context7-docs.md`.
- Directly satisfies the S-05 slice (distance/duration stats) later, without adding a second dependency — `gpxpy`'s built-in `length_2d()`/`length_3d()`, `get_duration()`, and moving-time heuristics cover FR-010 without hand-rolled great-circle math.
- Mature, actively maintained, widely used — matches the project's stated preference for well-documented, agent-friendly, popular libraries (see `tech-stack.md` quality gates referenced by `10x-tech-stack-selector`).
- No compiled/Rust extension, no heavy transitive deps (`pandas`, `matplotlib`) — keeps the dependency footprint aligned with a lightweight Django app on `uv`.

### Note on `lxml`

`gpxpy` docs state it prefers `lxml` over `minidom` for 2-3x faster parsing when available. Given GPX files here are small, single-track, user-uploaded files (not a bulk-processing pipeline), the stdlib `minidom` fallback is very likely fine for v1 — evaluate at `/10x-plan` time whether adding `lxml` as an explicit dependency is worth it, or leave it to `gpxpy`'s optional/fallback behavior.

## Follow-up for `/10x-plan`

- Confirm at plan time how `gpxpy`'s parsed points map onto the Leaflet rendering path from `leaflet-context7-docs.md` (server serializes `gpx.tracks[].segments[].points[]` into a JSON array of `[lat, lon]` for the template, no GPX-specific JS plugin needed).
- Confirm GPX-parse-error handling (malformed upload) surfaces as the PRD's required deliberate empty/error state, not a silent 500 — this is `gpxpy`'s job to raise (`gpxpy.gpx.GPXException` and friends), and the view's job to catch.
