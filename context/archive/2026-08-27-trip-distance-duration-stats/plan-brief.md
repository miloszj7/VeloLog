# Trip Distance and Duration Stats — Plan Brief

> Full plan: `context/changes/trip-distance-duration-stats/plan.md`
> Research: `context/changes/trip-distance-duration-stats/research.md`

## What & Why

Show basic ride statistics — distance, elapsed duration, moving time, elevation gain and
loss — on the trip detail view, computed from the uploaded GPX file. This is roadmap
**S-05** / PRD **FR-010**, the PRD's Secondary Success Criterion: a rider looking at a
logged tour currently sees the route drawn on a map but no numbers about it.

## Starting Point

`GpxTrack` stores the parsed route as `[[lat, lon], ...]` plus four bounds. Elevation and
per-point timestamps are discarded inside the list comprehension at `gpx/parsing.py:154`
and never reach the database, so **duration is not computable from stored data at all** —
only 2D distance is. Nothing in the codebase computes any statistic today. The single
`gpxpy.parse()` call at `gpx/parsing.py:143` is the only moment the full data exists.

## Desired End State

A rider opening a trip with an uploaded GPX file sees a **Stats** section listing distance
in kilometres, elapsed duration, moving time, and metres climbed and descended. Where the
file itself did not carry the underlying data, that stat reads as explicitly not recorded
rather than as a zero or a blank. A trip with no track shows no Stats section, exactly as
it shows no map.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Which stats | Distance + elapsed duration + moving time + elevation gain/loss | One migration covers what riders on multi-day mountain tours actually ask for; the parse cost is identical. | Plan |
| Derivation | Compute once at upload, store in columns | Continues the rule stated verbatim at `gpx/models.py:25` so the render path can never fail on a parse. | Plan |
| Existing rows | Best-effort data migration | Existing trips gain stats on the next deploy with no manual step, since `migrate` runs with the media volume mounted. | Plan |
| Missing data | Explicit note per stat | Every `{% else %}` in `trip_detail.html` already renders a deliberate sentence, and the PRD's one NFR rejects silent failure. | Plan |
| Distance basis | 2D (`length_2d`) | Conventional, matches what other tools report, and consistent with the flat polyline the map draws; the 3D gap measured 0.06%. | Plan |
| Column shape | Five scalar `FloatField`s, not one `JSONField` | `GpxTrack` already stores its four bounds as scalar floats — established precedent for derived numbers on this model. | Plan |
| Re-parse at render | Rejected | `GpxDownloadView` already proves a row's file can go missing, and the PRD NFR forbids a blank page. | Research |

## Scope

**In scope:** five nullable columns on `GpxTrack`; statistics captured in `parse_gpx`;
upload-path wiring in `clean_file`; a schema migration and a best-effort backfill
migration; a `gpx/statistics.py` display builder; both render paths; the template block;
tests; an `AGENTS.md` sync.

**Out of scope:** elevation profile chart (GPL-3.0 library, parked in S-03); average and
max speed (`max_speed` read `0.0` on real timed input); stats on the trip list page; any
recomputation of `points` or bounds; a backfill management command; E-11.

## Architecture / Approach

```
upload ──► parse_gpx (gpxpy object)  ──► ParsedTrack (+5 stats)
                                            │
                                    clean_file copies onto instance
                                            │
                                     GpxTrack (+5 nullable columns)
                                            │
                          build_trip_stats(track) ─► TripStats (display strings)
                                            │
                    ┌───────────────────────┴───────────────────────┐
            TripDetailView                                  GpxUploadView
                    └──────────── trips/trip_detail.html ────────────┘
```

Statistics mirror `build_map_config` exactly: a pure `GpxTrack | None → … | None`
function in `gpx/`, reading stored columns and never re-parsing. Both views render the
same template and must set the key independently — a two-place change their own docstrings
warn about, pinned here by a parity test rather than a comment.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Capture and store | Stats stored for every new upload | Two gpxpy calls return `0` where a caller expects `None` — storing that zero is a silent data defect |
| 2. Backfill | Existing tracks gain stats on next deploy | A migration importing app code can stop replaying later; mitigated by a broad per-row `except` |
| 3. Render | The feature becomes user-visible | A context key set in one render path and missed in the other |
| 4. Sync `AGENTS.md` | Accurate `gpx/` ownership description | None |

**Prerequisites:** S-03 (`upload-gpx-and-view-map`) — done. `gpxpy>=1.6.2` already
installed; no new dependency, URL or view.
**Estimated effort:** ~2 sessions across 4 phases; phase 4 is a few lines.

## Open Risks & Assumptions

- **Moving time is threshold-sensitive.** On a 3-point timed track the probe returned
  `1800.0` moving against `7200.0` elapsed — gpxpy classified half the legs as stopped.
  Elapsed is the headline figure; moving time sits beside it and may read low on sparse
  exports.
- **Backfill depends on `MEDIA_ROOT` being right at migrate time** — the trap both
  `AGENTS.md` and `DEPLOY.md` warn about. If it is wrong, the backfill fills nothing and
  logs each skip; the recovery path is re-uploading the file, since a migration cannot be
  re-run once applied.
- **`gpx/statistics.py`'s backfill helper is pinned by migration `0003`** and cannot be
  deleted while that migration exists.
- Assumes v1's one-track-per-trip reality; FR-011 (multi-stage) is parked, so per-track
  aggregation across several files is not designed for.

## Success Criteria (Summary)

- A rider sees distance, duration and elevation for a trip whose GPX file carries that data.
- A file missing timestamps or elevation says so per stat, rather than showing zero or blank.
- A trip with no GPX file shows no Stats section, and a rejected upload does not wipe the
  stats of the route already attached.
