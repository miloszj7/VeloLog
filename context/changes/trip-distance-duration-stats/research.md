---
date: 2026-08-27T19:45:29Z
researcher: Claude Sonnet 5
git_commit: 2f8cd3bf7ba49380ed7f60748c77d117ae83b759
branch: feat/trip-distance-duration-stats
repository: VeloLog
topic: "S-05 — trip distance/duration stats on the trip detail view"
tags: [research, codebase, gpx, trips, statistics, gpxpy]
status: complete
last_updated: 2026-08-27
last_updated_by: Claude Sonnet 5
---

# Research: S-05 — trip distance/duration stats on the trip detail view

**Date**: 2026-08-27T19:45:29Z
**Researcher**: Claude Sonnet 5
**Git Commit**: 2f8cd3bf7ba49380ed7f60748c77d117ae83b759
**Branch**: feat/trip-distance-duration-stats
**Repository**: VeloLog

## Research Question

What does it take to implement S-05 (`context/foundation/roadmap.md`): show basic trip
stats — distance and duration, calculated from the uploaded GPX file — on the trip
detail view (PRD FR-010, nice-to-have/Secondary Success Criterion)? Specifically: can
distance/duration be computed from data already stored, or does storage/parsing need to
change, and where does the display logic belong?

## Summary

**Distance is cheaply computable today (2D, from stored lat/lon); duration is not
computable from stored data at all — timestamps are discarded at parse time and never
persisted.** Elevation is likewise discarded, so 3D distance and elevation gain/loss are
also unavailable without a schema change.

Two design paths exist, both requiring a `GpxTrack` schema change:

1. **Re-parse the raw `.gpx` file** (`track.file`) at render time via `gpxpy.parse()`
   to recover timestamps/elevation for duration and 3D distance. Cheap per-request but
   reintroduces "does this fail if the file is missing/corrupted" risk that S-03's
   store-once philosophy explicitly avoided for the map.
2. **Extend `GpxTrack`** with new fields (e.g. `distance_meters`, `duration_seconds`)
   computed once at upload time from the full `gpxpy` parse (before points are stripped
   down to lat/lon-only), mirroring S-03's "parse once, never fail at render" precedent.
   Requires a migration and touches `gpx/parsing.py`'s `ParsedTrack`/`parse_gpx`.

No new URL, view, or dependency is needed either way — `gpxpy>=1.6.2` is already
installed (added in S-03) and this is a context/template addition on top of the
existing `TripDetailView` / `GpxUploadView` render paths.

## Detailed Findings

### GpxTrack model and parsing — what's stored today

- `GpxTrack` (`gpx/models.py:20-42`... see exact fields below) stores: `trip` FK,
  `file` (FileField), `points` (JSONField), `min_latitude`/`min_longitude`/
  `max_latitude`/`max_longitude` (bounds), `original_filename`, `uploaded_at`
  (upload timestamp — not ride time).
- `points` is a plain list of `[latitude, longitude]` pairs, rounded to 5 decimal
  places (`COORDINATE_DECIMAL_PLACES`, `gpx/constants.py`) — **no elevation, no
  per-point timestamp**. Confirmed both in the model and in `gpx/parsing.py`'s
  `ParsedTrack` dataclass, which only carries `points: tuple[tuple[float, float], ...]`
  plus the four bound floats.
- `gpx/parsing.py` parses with `gpxpy.parse(text)` and extracts only
  `point.latitude`/`point.longitude` per point (list comprehension over
  `gpx.tracks → segment.points`). `gpxpy`'s `GPXTrackPoint` also exposes
  `point.elevation` and `point.time`, but neither is read — both are silently
  discarded during parsing.
- Bounds are computed from `min()`/`max()` of the kept points, not from
  `gpx.get_bounds()`.
- The one migration (`gpx/migrations/0001_initial.py`) matches the model exactly —
  no schema drift to reconcile.
- **No existing distance/duration/statistics computation exists anywhere in the
  codebase** — confirmed by a repo-wide grep for `distance|duration|haversine|
  elevation|statistics|get_duration|length_2d|length_3d` (only unrelated hit: a
  session-cookie comment in `velo_log/settings.py`).

### gpxpy APIs available (already documented for this slice)

`context/archive/2026-08-23-upload-gpx-and-view-map/research/gpxpy-context7-docs.md`
is explicitly titled "feeds S-05" and already captures the exact API surface needed,
confirmed to require **no additional dependency** beyond the already-installed
`gpxpy>=1.6.2` (`pyproject.toml`):

```python
dist_2d = gpx.length_2d()        # meters, ignores elevation
dist_3d = gpx.length_3d()        # meters, includes elevation
bounds = gpx.get_time_bounds()   # TimeBounds(start_time, end_time)
duration = gpx.get_duration()    # seconds
uphill, downhill = gpx.get_uphill_downhill()
min_elev, max_elev = gpx.get_elevation_extremes()
data = gpx.get_moving_data()     # MovingData: moving_time, max_speed, ...
```

Same methods exist per-track (`track.length_3d()`, `track.get_duration()`, ...). All
of these require the **raw gpxpy point objects** (with elevation/time intact) — none
of them can be reconstructed from the currently-stored `points` field, which has
already dropped elevation and time by the time it reaches the database.

A plain 2D haversine sum over the stored `[lat, lon]` pairs *would* work for a
same-precision approximation of `length_2d()` without touching parsing/storage at
all — but duration is unavailable under any read of the current `points` field; it
requires either re-parsing the file or capturing timestamps at parse time.

### Where display logic belongs — reference pattern: `gpx/map_config.py`

`build_map_config(track)` (`gpx/map_config.py:22-54`) is the established pattern for
a "derive from stored track" pure function:
- Signature takes `GpxTrack | None`, returns `None` on the "nothing to compute" case
  (`track is None or not track.points`).
- Reads `track.points` and the four bound floats directly — no re-parsing.
- Lives in `gpx/` since it's a `gpx`-owned concern (not `trips/`).

A new `gpx/statistics.py` (or similarly named module) with a `build_trip_stats(track)`
function following this exact shape is the natural home, mirrored for both render
paths described next.

### Two render paths must both be updated

- `TripDetailView.get_context_data` (`trips/views.py`) — the normal detail-page path.
  Gets `track = self.object.tracks.first()`, builds `context["map_config"] =
  build_map_config(track)`. A new `context["stats"] = build_trip_stats(track)` (or
  similar) would sit right next to it.
- `GpxUploadView.get_context_data` (`gpx/views.py`) — re-renders the **same**
  template (`trips/trip_detail.html`) on a failed upload, and **independently
  re-derives** `track`/`map_config` the same way. The codebase's own comments call
  out explicitly that both paths must build the map blob identically to stay in
  sync — the same discipline applies to any new stats context key, or a failed
  upload will silently omit stats where a successful one shows them.

### Template — `trips/templates/trips/trip_detail.html`

- `<h2>Route</h2>` marks the natural insertion point for a `<h2>Stats</h2>` block
  (after the route/map section, before the upload form).
- The whole route/map section is gated `{% if track %}...{% else %}` (empty-state
  copy: "No route yet — this trip has no GPX file uploaded..."). A new stats block
  should live inside that same `{% if track %}` gate (or its own conditional keyed
  on the new context var) so it disappears in the empty state exactly like
  `Track: {{ track.original_filename }}` already does.
- `{% if map_config %}` vs `{% else %}` inside that block additionally handles the
  edge case of a track with no drawable points — noted as unreachable via normal
  upload today, but worth the same defensive treatment for stats if duration/
  distance could ever be `None`/zero on a degenerate track.

### Test conventions (`tests/trips/test_trip_detail.py`, `test_trip_detail_map.py`)

- Fixtures: `rider`/`other_rider` (Users), `auth_client` (logged-in client),
  `make_gpx_track: TrackFactory` (constructs a `GpxTrack` with fixed
  `GPX_POINTS = [[50.06, 19.94], [50.07, 19.95]]` / `GPX_BOUNDS`, no real file
  bytes — fine for stats since they'd derive from `points`, not by reopening the
  file). `make_stored_track` is the variant with real file bytes on disk, needed
  only if the chosen design re-parses the raw file.
- Pattern: `@pytest.mark.django_db`, GET via `auth_client.get(reverse("trips:detail",
  kwargs={"pk": trip.pk}))`, assert on `response.context["..."]` and/or substrings in
  `response.content.decode()`.
- `test_trip_detail_map.py` shows the `json_script`-embedded-data assertion pattern
  (regex-extracting a `<script id="map-config" type="application/json">` tag) — reuse
  this if stats are also JSON-embedded; otherwise the simpler `"12.3 km" in body`
  pattern used throughout `test_trip_detail.py` applies for plain-text rendering.
- Empty-state precedent to mirror: `test_trip_with_no_track_renders_the_empty_state_copy`
  and `test_a_trip_with_no_track_renders_no_map_container` — a new "no track → no
  stats block" test is the direct analogue.

### URL wiring

- `trips/urls.py` (list/create/detail/edit/delete) and `gpx/urls.py`
  (upload/download) have nothing stats-related and need no new entries — this is
  purely a context/template addition on the existing detail-view render paths.

## Code References

- `gpx/models.py` — `GpxTrack` model: `file`, `points` (JSONField, `[lat, lng]` pairs
  only), bounds, `original_filename`, `uploaded_at`
- `gpx/constants.py` — `COORDINATE_DECIMAL_PLACES` (5-decimal rounding for stored
  points)
- `gpx/parsing.py` — `ParsedTrack` dataclass and `parse_gpx()`; point extraction reads
  only `point.latitude`/`point.longitude`, discards `point.elevation`/`point.time`
- `gpx/map_config.py` — `build_map_config(track)`, the reference pure-function
  pattern for a new stats helper
- `gpx/migrations/0001_initial.py` — current `GpxTrack` schema, matches `models.py`
  exactly
- `trips/views.py` — `TripDetailView.get_context_data`, `get_queryset` (owner-scoped)
- `gpx/views.py` — `GpxUploadView.get_context_data` (the second render path that must
  stay in sync with `TripDetailView`)
- `trips/templates/trips/trip_detail.html` — `<h2>Route</h2>` insertion point,
  `{% if track %}` empty-state gate, `{% if map_config %}` inner gate
- `trips/urls.py`, `gpx/urls.py` — no stats-related routes exist or are needed
- `tests/trips/test_trip_detail.py`, `tests/trips/test_trip_detail_map.py` — test
  conventions, fixtures (`make_gpx_track`, `make_stored_track`), empty-state test
  precedent
- `pyproject.toml` — `gpxpy>=1.6.2` already a dependency, no new package needed

## Architecture Insights

- **"Parse once, never fail at render"** is the established philosophy from S-03
  (`context/archive/2026-08-23-upload-gpx-and-view-map/plan.md`): derive everything
  needed for display at upload time and store it, so the detail-page render path
  never depends on re-parsing a file that could be missing or malformed. A stats
  design that stores `distance_meters`/`duration_seconds` on `GpxTrack` (computed
  once at upload, before points are stripped to lat/lon) continues this philosophy;
  a design that re-parses `track.file` at render time breaks it and reintroduces the
  exact class of risk S-03 deliberately avoided for the map.
- **Two render paths, one context contract**: `TripDetailView` and `GpxUploadView`
  both render `trips/trip_detail.html` and must independently build identical
  context. Any new context key (stats included) is a two-place change, not one —
  this is already true for `map_config` and is explicitly called out in code
  comments in both views.
- **Pure-function-per-concern-app pattern**: map/stats-shaping logic lives in `gpx/`
  as small functions taking a `GpxTrack | None` and returning `None` on "nothing to
  show," not in `trips/` — `trips/views.py` only orchestrates by calling into `gpx`.

## Historical Context (from prior changes)

- `context/archive/2026-08-23-upload-gpx-and-view-map/plan.md` (line ~123, "What
  We're NOT Doing"): *"No trip stats — distance/duration is S-05. This plan persists
  the parsed track in a shape S-05 can build on, and adds no second dependency for
  it."* — S-03 deliberately deferred stats but claimed the stored shape would be
  sufficient; this research finds that claim is **only true for 2D distance**, not
  duration (timestamps were never part of the persisted shape).
- `context/archive/2026-08-23-upload-gpx-and-view-map/research/gpxpy-context7-docs.md`
  — pre-fetched gpxpy API reference explicitly scoped "feeds S-05"; use this directly
  rather than re-querying Context7 for gpxpy during planning.
- `context/changes/trip-distance-duration-stats/change.md` — this change's own notes
  already reasoned that E-11 (orphaned file on rolled-back upload transaction) is out
  of scope, since S-05 only reads `GpxTrack.points`/file, never touches
  `GpxUploadView.form_valid`'s transaction. This research confirms that reasoning
  holds even if the chosen design re-parses `track.file` — that read happens outside
  and after the upload transaction, on an already-committed row.
- No rejected ideas or prior haversine/elevation-chart discussion found beyond the
  already-parked `@raruto/leaflet-elevation` (GPL-3.0, parked in S-03's plan as
  out of scope).

## Related Research

- `context/archive/2026-08-23-upload-gpx-and-view-map/research.md`
- `context/archive/2026-08-23-upload-gpx-and-view-map/research/gpxpy-context7-docs.md`
- `context/archive/2026-08-23-upload-gpx-and-view-map/plan.md`

## Open Questions

1. **Schema-change design choice** (the central decision for `/10x-plan`): store
   `distance_meters`/`duration_seconds` (and optionally elevation gain) on `GpxTrack`
   at upload time, vs. re-parse `track.file` at render time. The former matches S-03's
   established philosophy and needs a migration; the latter needs no migration but
   reintroduces render-time file-read risk.
2. **2D vs 3D distance**: is elevation-aware distance (`length_3d`) worth capturing,
   or is a simpler 2D distance (`length_2d`, or a haversine over stored `points`)
   enough for a "basic stats" nice-to-have? Capturing elevation also unlocks the
   "duration" fix for free (if the full gpxpy parse is done once at upload) but
   further widens the `ParsedTrack`/`points` schema conversation.
3. **GPX files without `<time>` elements**: `gpx.get_duration()` returns `None` when
   points have no timestamps at all — the plan needs to decide how "duration
   unavailable" renders (e.g. show distance only, omit the duration line) rather
   than assume every uploaded file carries time data.
4. **Where exactly the two-field vs. one-JSON-field storage decision lands** — e.g.
   two new scalar columns (`distance_meters: FloatField`, `duration_seconds:
   IntegerField`, nullable) vs. a single `stats: JSONField` — is a planning-level
   choice, not yet made anywhere in the codebase.
