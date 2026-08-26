# gpxpy — Context7 docs (S-03 `upload-gpx-and-view-map`, feeds S-05 `trip-distance-duration-stats`)

- **Date:** 2026-08-24
- **Method:** External research (Context7 MCP) — live library documentation, per `AGENTS.md` research discipline.
- **Question:** Fetch current `gpxpy` API docs for what the roadmap needs — S-03's parsed track points (for map rendering) and S-05's distance/duration stats.
- **Companion doc:** [`python-gpx-libraries.md`](./python-gpx-libraries.md) (exa.ai web search) selected `gpxpy` as the recommended parsing library; this doc captures the verified API surface from Context7.

## Library resolution

| Query | Result |
|---|---|
| "gpxpy" | `/tkrajina/gpxpy` — 379 snippets, High reputation, benchmark 74.5. Single, unambiguous match. |

## Data model

```text
GPX (root)
├── tracks: List[GPXTrack]
│   └── segments: List[GPXTrackSegment]
│       └── points: List[GPXTrackPoint]
├── routes: List[GPXRoute]
│   └── points: List[GPXRoutePoint]
└── waypoints: List[GPXWaypoint]
```

## Parsing (feeds S-03 — map rendering)

```python
import gpxpy
import gpxpy.gpx

with open('my_track.gpx') as f:
    gpx = gpxpy.parse(f)

for track in gpx.tracks:
    for segment in track.segments:
        for point in segment.points:
            print(f'Point at ({point.latitude},{point.longitude}) -> {point.elevation}')
```

- `gpx.tracks[].segments[].points[]` gives `.latitude`, `.longitude`, `.elevation` per point — this is exactly the `[lat, lon]` list the Leaflet `Polyline`/`Marker`/`fitBounds` rendering path (see `leaflet-context7-docs.md`) needs; elevation is available in the same pass for a later elevation-profile feature (parked addendum in `map-library-research.md`).
- `gpx.waypoints` and `gpx.routes` also parse if present, but S-03's scope is track points only.
- Also usable: `gpx.get_bounds()` → `GPXBounds` (min/max lat/lon) and `gpx.get_center()` → `Location` — could replace a client-side `fitBounds` computation, or double-check it server-side before rendering.

## Error handling (feeds S-03's required deliberate empty/error state)

```python
import gpxpy

try:
    with open(gpx_file) as f:
        gpx = gpxpy.parse(f)
except gpxpy.gpx.GPXXMLSyntaxException as e:
    print(f"XML parsing error: {e}")
    # malformed XML — not valid GPX at all
except gpxpy.gpx.GPXException as e:
    print(f"GPX data error: {e}")
    # valid XML, invalid/unsupported GPX structure
```

`GPXXMLSyntaxException` and `GPXException` are the two exception types to catch at the upload-handling view — this is what turns a bad upload into the PRD-required deliberate error state instead of a silent 500 (per roadmap S-03 risk note).

## Distance/duration/elevation stats (feeds S-05 — not needed for S-03 itself, but confirms no second library is required later)

```python
gpx = gpxpy.parse(gpx_file)

# Distance
dist_2d = gpx.length_2d()   # meters, ignores elevation
dist_3d = gpx.length_3d()   # meters, includes elevation

# Time
bounds = gpx.get_time_bounds()   # TimeBounds(start_time, end_time)
duration = gpx.get_duration()    # seconds

# Elevation
uphill, downhill = gpx.get_uphill_downhill()          # meters
min_elev, max_elev = gpx.get_elevation_extremes()     # MinimumMaximum(minimum, maximum)

# Movement (moving vs. stationary time, filtering GPS noise)
data = gpx.get_moving_data()   # MovingData
print(f"Moving: {data.moving_time}s, Speed: {data.max_speed * 3.6:.1f} km/h")
```

Same methods exist per-track (`track.length_3d()`, `track.get_duration()`, `track.get_uphill_downhill()`, `track.get_moving_data()`), useful if a trip's GPX file contains multiple tracks (not expected in v1 — FR-011 multi-stage is parked, so a v1 trip has one track).

## Follow-up for `/10x-plan`

- S-03 only needs the parsing snippet + exception handling above — `length_2d`/`get_duration`/etc. are S-05's concern, confirmed here to need no additional dependency.
- Decide server-side whether to compute `get_bounds()` and pass it to the template alongside the point list, or leave bounds-fitting entirely to the client-side Leaflet `fitBounds(new LatLngBounds(latlngs))` pattern already documented in `leaflet-context7-docs.md` — either is supported, this is a plan-time call, not a research gap.
- Catch both `GPXXMLSyntaxException` and `GPXException` (not just the base one) in the upload view, per the two distinct failure modes shown above.
