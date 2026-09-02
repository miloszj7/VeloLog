# Multi-stage GPX upload — Plan Brief

> Full plan: `context/changes/multi-stage-gpx-upload/plan.md`
> Research: `context/changes/multi-stage-gpx-upload/research.md`

## What & Why

A rider can upload a second (and further) GPX file to an existing trip as an additional
**stage**, instead of replacing the one already there. All stages render as one route,
ordered by GPS instants, each in its own colour, with markers at the trip's start, its end,
and each stage break. This is the milestone's north star (roadmap S-01) and closes the PRD's
data-fidelity gap: the model represents one day and one file, while the product's actual
subject is the multi-day tour.

## Starting Point

The schema was built for this — `GpxTrack.trip` is a plain FK with `related_name="tracks"`
and no uniqueness constraint. What is v1-shaped is the write path and the read path.
`GpxUploadView.form_valid` reads every existing track and deletes it after inserting the new
one (`gpx/views.py:116,121`); `build_map_config` takes one track and returns a flat point
list; `map.js` draws one polyline and two hardcoded markers; both render sites call
`.tracks.first()`, which under descending `Meta.ordering` is the *newest* track. And the
parse discards the one thing ordering needs: `gpx/parsing.py:117` reads the file's absolute
instants as a presence probe and throws them away one line later.

## Desired End State

Opening a trip with two stages shows both merged on the interactive map as differently
coloured segments in ride order, with a marker at the start, the end, and the boundary
between them. Below it, a **Stages** list gives each stage its colour swatch, filename, own
statistics and own download link. Both files stay in storage and stay downloadable. A
single-stage v1 trip shows one segment and one row — the same information it shows today.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Where the risk actually is | Signals need no edit; the leftover `DELETE` is the hazard | `pre_save` returns on every insert (`pk is None`) and was never trip-aware; `post_delete` is correct, which is exactly why a leftover delete becomes permanent file loss | Research |
| Ordering data source | New nullable `started_at`/`ended_at` columns captured at parse | The points blob carries no temporal signal, and re-parsing at render is rejected twice on record | Research |
| Ordering expression | `F("started_at").asc(nulls_last=True), "uploaded_at", "id"` | One expression covers all-timed, none-timed and mixed; `COALESCE` into one key would compare a ride instant against an upload instant | Research |
| Naive timestamps | Treated as "no usable timestamp" | Under `USE_TZ=True` a naive value is silently read as UTC — a wrong instant is worse than none | Plan |
| Per-stage colour vs. design system | Bounded map-only categorical palette, added to `design-system.md` | The PRD clause is the recorded *resolution* of a correctness counter-argument, not decoration; also ends the `#ff7800`/`#f97316` drift | Plan |
| Marker distinction | Three project-authored SVG pins (Leaflet's 25×41 geometry) | No third-party licence or integrity gate, hues stay in step with the palette, existing anchor values stay correct | Plan |
| Statistics under N stages | One stats block bound to each stage | No aggregate is invented, so the NULL-skipping fabrication trap never arises; S-03 stays additive and cuttable | Research |
| Payload size across N stages | Measure with a real export; decide on evidence | `MAX_GPX_POINTS` is already flagged "provisional, not calibrated against a real tour"; building thinning on a guess is scope in the riskiest slice | Plan |
| Backfill for existing rows | Full `0002`→`0003` precedent (schema migration, data migration, command) | US-02's own scenario starts from a trip that *already* has a stage — without instants on it, chronology is never established | Plan |
| Trip span | Derived from stage instants, gated on one predicate | `Min`/`Max` skip NULLs, so a span over a partially timed trip is a lower bound presented as the span | Research |
| E-10 (`Trip.date` split) | Closed as unnecessary; only the help text changes | The `(start, end)` pair is derivable, so storing it is denormalisation whose only novel behaviour is drift | Roadmap (`4c48d9e`) |

## Scope

**In scope:** stage instants at parse; ADD upload semantics; chronological ordering and the
chronology predicate; multi-stage map payload and client rendering; per-stage palette; stage
list with per-stage statistics and download links; backfill for pre-existing rows; three
marker pins; derived trip span and date help-text wording; a mutation shape proving the
file-loss guard bites.

**Out of scope:** stage removal (so no new `OBJECT_SCOPED_ROUTES` row); whole-trip statistics
aggregation (S-03); manual stage reordering or any `order` column; rider-supplied timestamps
(parked); accommodation waypoints; coordinate thinning; any `Trip` migration; re-parsing at
render.

## Architecture / Approach

A new `gpx/stages.py` owns "what are this trip's stages, in what order, and is that order
evidence": `ordered_stage_tracks`, `chronology_is_established`, `build_stages` (a frozen
`Stage` carrying track, number, colour, stats and file-availability), and `trip_span`. Both
render paths — `TripDetailView` and `GpxUploadView`'s error re-render, whose docstrings
already warn they must not drift — build the same `stages` tuple and hand it to
`build_map_config`, which returns segments, aggregate bounds and a marker array keyed by
kind. `map.js` loops both. `build_trip_stats` and `track_file_is_available` keep their
single-track signatures and are called once per stage, so no aggregate is invented anywhere.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Stage instants at parse | Both instants captured and stored; nullable columns; a second timed fixture | A naive timestamp stored as a wrong instant instead of as absent |
| 2. ADD semantics | Stages accumulate; ordering expression; mutation shape | The dangerous one — a leftover delete destroys prior stages' files |
| 3. Multi-stage rendering | Segments + marker array payload; `map.js` loops; palette amendment | Payload shape change breaks the `#map` byte-exact pin or the manifest-resolved icons |
| 4. Stage list + per-stage stats | Stages section: swatch, filename, figures, download link | Largest template diff; the stats correctness fix that is *not* cuttable |
| 5. Marker pins | Three SVG pins replacing the shared Leaflet one | Wrong anchor puts the pin tip off its coordinate |
| 6. Backfill *(cuttable)* | Instants filled on pre-existing rows | A migration cannot be re-applied — a bad `MEDIA_ROOT` fills nothing silently |
| 7. Derived span + wording *(cuttable)* | Tour span on the detail page; corrected help text | Showing a span over partially timed stages understates the tour |

**Prerequisites:** none — S-02 (interactive map) is already `done`, and no foundation work is
outstanding. Real timed GPX exports from the owner's device are needed for Phase 3's
measurement and Phase 5's manual verification.

**Estimated effort:** ~4-6 after-hours sessions. Phases 1-5 are the shippable core — the
marker pins are in it, not in the tail, because "distinct markers … without hovering" is a
PRD must-have (`prd.md:96-97,127`) that Phase 3's shared pin satisfies only on hover. Phases
6-7 are the nominated cuts, ordered most-valuable-first, against the 2026-09-10 deadline.

## Open Risks & Assumptions

- **Page weight across N stages is unmeasured.** `MAX_GPX_POINTS` is a per-track cap and N
  stages multiply it. Phase 3's manual step produces the first real number; a bad one opens a
  backlog row rather than being pre-solved.
- **The untimed path is the default one under test today.** Both canonical fixtures lack
  `<time>`, so without the new `timed-track-day-2.gpx` the ordering feature would ship
  unexercised — green suite, unproven behaviour.
- **Cutting Phase 5 degrades the demo path**, not an edge case: US-02 starts from a trip that
  already has a stage, and without backfill that stage has no instant.
- **Assumed:** real exports from the owner's device carry timestamps (bike computers record
  time as a matter of course). If they routinely do not, the parked "rider supplies missing
  stage timestamps" row becomes due sooner than the roadmap expects.
- Overlapping stages (the same ride uploaded twice) still sort fine by start instant, but a
  break marker between them has no real-world referent — acceptable, noted, not guarded.

## Success Criteria (Summary)

- A rider uploads a second GPX file to an existing trip and both stages render as distinct,
  chronologically ordered coloured segments with start, end and stage-break markers.
- Every uploaded stage file remains stored and downloadable — no upload ever removes another
  stage's file, and a mutation shape proves the test protecting that goes red when broken.
- An existing single-stage v1 trip renders, edits and deletes exactly as before, with no
  manual migration step asked of the user.
