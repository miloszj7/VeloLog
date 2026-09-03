---
date: 2026-09-02T19:25:07+02:00
researcher: Miłosz Jarzynka
git_commit: b13a3c8615542a332c78c247baf6a70c259d2265
branch: master
repository: miloszj7/VeloLog
topic: "Multi-stage GPX upload: replace→add semantics, chronological merge, per-stage rendering, and the E-10 Trip.date question"
tags: [research, codebase, gpx, upload, signals, file-lifecycle, map-config, leaflet, trip-date, e-10, migrations]
status: complete
last_updated: 2026-09-02
last_updated_by: Miłosz Jarzynka
last_updated_note: "Added three follow-ups: S-03 melding; stage/trip temporal modeling (instants vs dates, resolves open question 6); absent-timestamp ordering and timespan fallbacks (resolves open question 2)"
---

# Research: Multi-stage GPX upload (S-01) and the E-10 `Trip.date` question

**Date**: 2026-09-02T19:25:07+02:00
**Researcher**: Miłosz Jarzynka
**Git Commit**: `b13a3c8615542a332c78c247baf6a70c259d2265`
**Branch**: `master` (pushed, 0 commits ahead of `origin/master`)
**Repository**: [miloszj7/VeloLog](https://github.com/miloszj7/VeloLog)

> **On references.** All citations are local `path:line` (clickable in-terminal). `HEAD` is
> pushed, so any reference resolves as a permalink by prefixing
> `https://github.com/miloszj7/VeloLog/blob/b13a3c8615542a332c78c247baf6a70c259d2265/`.
> Local refs are kept in the body deliberately rather than expanded inline — the document
> is read while editing these same files.

## Research Question

From `context/changes/multi-stage-gpx-upload/change.md` (roadmap slice S-01, the M-02 north
star): what does the codebase actually require to let a user upload a second (and further)
GPX file to an existing trip, merge all stages chronologically by GPS timestamp, render each
as a visually distinct segment with start/end/stage-break markers, and keep single-GPX v1
trips rendering unchanged?

Scope confirmed with the user before dispatch:

- **Focus**: the upload path and its file-lifecycle signals (the named risk, researched
  regardless); design options for chronological stage ordering; the rendering / map-config
  pipeline.
- **E-10 depth**: research the label/terminology change in full, *and* gather the evidence
  needed to decide whether the `Trip.date` start/end field split belongs in this change —
  the decision itself is `/10x-plan`'s, not this document's.
- **Deliberately not deep-researched** (user's call): the test-surface inventory, and the
  stats panel's behavior under multiple stages. Both still appear below as named open
  questions, because each turned out to be forced by this change rather than deferrable.

## Summary

Five findings, in descending order of consequence.

1. **The change's stated risk is aimed at the wrong file.** `change.md:14` and
   `roadmap.md:74` both say the danger is that "a `pre_save` signal reclaims the superseded
   file on that assumption," so the upload path and `gpx/signals.py` must be changed
   together. The code says otherwise: **neither receiver in `gpx/signals.py` is
   trip-aware, and the `pre_save` receiver returns early on every single upload** — it
   guards on `instance.pk is None`, and every upload is an INSERT
   (`gpx/signals.py:160-164`). REPLACE semantics live entirely in two lines of
   `gpx/views.py` (`:116` and `:121`). The real hazard is the inverse of the one written
   down: `post_delete` is *correct*, and will faithfully delete the storage file of every
   row that delete statement removes. Leave the delete in place under ADD semantics and
   the first second-stage upload destroys every prior stage's row **and** its file. The
   signals need no edit — they need re-verification and a mutation shape.

2. **"Ordered chronologically by GPS timestamp" has no data source today.** The single
   `gpxpy` parse keeps only rounded lat/lon; `point.time` is discarded inside the list
   comprehension (`gpx/parsing.py:269-277`). `duration_seconds` is a *relative* span from
   `gpx.get_duration()`, not a timestamp pair (`gpx/parsing.py:116-118`). The stored
   `points` blob is `[[lat, lon], ...]` and contains no temporal signal at all, so ordering
   cannot be derived from it at read time. Chronological ordering therefore requires a **new
   column captured at parse time**, and for pre-existing rows the **only** backfill source is
   re-parsing the stored `.gpx` file. The repo already has the exact three-part precedent for
   that (`0002` add nullable columns → `0003` RunPython under an import guard →
   `manage.py backfill_gpx_stats` as the manual recovery path).

3. **The map payload contract must change shape, and the design system forbids the
   styling the PRD requires.** `build_map_config` returns a *flat* coordinate list plus one
   bounds pair (`gpx/map_config.py`), and `map.js` draws exactly one `L.polyline` and
   exactly two hardcoded `L.marker` calls. Segments and stage breaks need a nested payload
   and marker-array-driven JS. Separately — and this is a genuine cross-artifact
   contradiction, not an implementation detail — `context/foundation/design-system.md`
   defines six tokens and states **"Do not introduce additional colors"** (capping orange at
   ~10% of the interface), while `prd.md:70` requires **"a different line color per stage."**
   No categorical palette exists anywhere in the repo. This needs a product decision.

4. **E-10's blocker is written against a superseded document.** The roadmap says the
   `Trip.date` split "needs a PRD amendment first: FR-003, FR-007 and the Primary Success
   Criterion all say 'a date', singular" (`roadmap.md:238`). FR-003 and FR-007 exist **only**
   in the archived v3 PRD (`context/foundation/archive/prd-2026-05-29-v3.md:66,74`); the
   live PRD v4 carries no FR numbering, and its Primary Success Criterion (`prd.md:46`) is
   about multi-stage map rendering and never mentions a date. Two of the three cited
   artifacts are archived and the third has been rewritten — so there is no live sentence
   left to amend. More decisive for scope: the split has **no functional consumer in S-01**
   even now, because stage chronology comes from GPS timestamps in the tracks (finding 2),
   exactly as `frame.md:56-58` predicted when it deferred this.

5. **There is no "Date of trip" label to revise.** The user's narrower instruction targets
   wording that does not exist under that name. The visible label is Django's auto-derived
   **"Date"**, left un-overridden on purpose (`trips/forms.py:31-32` explains why). What
   actually becomes wrong for a multi-day tour is the **help text**: *"The day the ride
   happened — VeloLog is a diary, not a planner."* (`trips/forms.py:35`), which is
   substring-asserted by a test (`tests/trips/test_trip_creation.py:172-187`). The
   terminology fix is genuinely small and self-contained; the field split is not.

## Detailed Findings

### 1. The upload path: where REPLACE semantics actually lives

`GpxUploadView.form_valid` (`gpx/views.py:89-122`) is a `CreateView` flow — a **new**
`GpxTrack` is built by the `ModelForm` and never mutated (`gpx/views.py:105` sets only
`form.instance.trip`). Inside `transaction.atomic()`:

```python
with transaction.atomic():
    # Read inside the transaction, and before the insert below so the new row is
    # not in it. Both halves matter: read outside, and two concurrent uploads to
    # one trip each see the same predecessor...
    superseded = list(self.trip.tracks.select_for_update())   # gpx/views.py:116
    response = super().form_valid(form)                        # gpx/views.py:120
    self.trip.tracks.filter(pk__in=[track.pk for track in superseded]).delete()  # :121
```

- `:116` reads **every** existing track on the trip, not "the one being replaced."
- `:120` is where `ModelForm.save()` → `FileField.pre_save` performs the implicit
  `storage.save()` and the row INSERT.
- `:121` deletes by the explicit pk set captured at `:116` — deliberately *not*
  `exclude(pk=new.pk)`. That ordering was hardened by a prior review finding against a TOCTOU
  race where two concurrent uploads to one trip each see the same predecessor
  (`context/archive/2026-08-23-upload-gpx-and-view-map/reviews/impl-review-phase-4.md:98-114`).

The method's own comment (`gpx/views.py:90-101`) records that file removal was deliberately
handed to the `post_delete` receiver: *"Removing the superseded files is no longer this
method's business… That is strictly stronger than scheduling the cleanup here was."*

**Replace-on-upload was a deliberate v1 decision, not an accident.** It is recorded as
decision D1's assumption in `context/archive/2026-08-23-upload-gpx-and-view-map/change.md:35-42`
(*"uploading again **replaces** the trip's existing track"*), restated in that plan
(`plan.md:61`), and was raised at review and explicitly upheld rather than treated as a bug
(`reviews/impl-review-phase-3.md:173-178`: *"the plan already commits to replace-on-upload…
so the invariant belongs at the boundary that creates tracks"*).

### 2. `gpx/signals.py`: correct as written, and not the risk

Both receivers are **row- and pk-scoped, never trip-scoped**.

`discard_file_of_deleted_track` (`post_delete`, `gpx/signals.py:80-113`):

- Sole guard: `if not storage_key: return` (`:107`) — skips only an empty file field.
- Closes over **scalars** (`instance.pk`, `instance.file.name`, `instance.file.storage`),
  not the instance — documented at `gpx/signals.py:37-48`, because registering the receiver
  defeats the collector's field-deferral optimization and a cascade now selects whole rows
  including the multi-megabyte `points` blob; an instance closure would hold every one of
  those resident past commit.
- Schedules via `transaction.on_commit`.
- Under ADD semantics its predicate is **unchanged and still correct**. It fires per row
  actually deleted, regardless of sibling count.

`discard_superseded_file_of_saved_track` (`pre_save`, `gpx/signals.py:116-182`), guards in
order: `raw` fixture load → **`instance.pk is None`** (`:160-164`) → `update_fields` without
`"file"` → empty old key → old key equals new key. Its own docstring states the second guard's
purpose: *"The insert path — every upload. Returning here is what keeps this receiver off
`GpxUploadView.form_valid`, whose superseded rows are *deleted* and so already covered by
`discard_file_of_deleted_track`."*

**Direct answer to the question the change poses.** A new `GpxTrack` inserted for a trip that
already has one *does* fire `pre_save`, but `pk` is still `None` at that moment, so the
receiver returns before it ever reads a predecessor. It compares only an instance's *own*
prior value by pk. It cannot see, and has never been able to see, sibling rows on the same
trip. Its only live consumer is the admin change form, where a row survives an in-place file
replacement and no delete signal fires (`gpx/signals.py:1-13` and the receiver docstring).

So the sentence in `change.md:14` — that changing replace to add "touches that upload path and
its file-lifecycle signal together" — does not hold. The signal is already correct for ADD.
What is true, and more dangerous, is that `post_delete` is *so* correct that it converts a
leftover delete statement into permanent file loss.

Registration is `GpxConfig.ready()` importing the module for its decorator side effects
(`gpx/apps.py:8-19`) — semantics-independent.

### 3. The schema is already ADD-ready; nothing in it forbids two tracks

`GpxTrack` (`gpx/models.py:20-63`), docstring first:

> *"The FK is deliberately many-tracks-per-trip so FR-011 needs no migration rewrite, even
> though v1 behaviour keeps exactly one track per trip. Points and bounds are derived once at
> upload, so rendering the detail page can never fail on a parse."*

- `trip = ForeignKey(Trip, on_delete=CASCADE, related_name="tracks")` (`:28`) — plain FK,
  no `unique=True`. `related_name` is plural on purpose (`.../upload-gpx-and-view-map/plan.md:409-411`).
- `file = FileField(upload_to=gpx_upload_path, max_length=255)` (`:29`);
  `gpx_upload_path` (`:8-17`) mints `gpx/{owner_id}/{trip_id}/{secrets.token_hex(16)}.gpx` —
  collision-free and filename-agnostic, so N stages per trip need no key-scheme change.
- `points = JSONField()` (`:30`) — NOT NULL, no default (which is why
  `GpxTrackAdmin.exclude = ("points",)` matters, `gpx/admin.py:24-25`).
- Four required bounds `FloatField`s; `original_filename`; `uploaded_at = DateTimeField(auto_now_add=True)`.
- Four nullable statistics columns (`:46-57`).
- `Meta.ordering = ["-uploaded_at", "-id"]` (`:59-60`) — and **nothing else**. Confirmed by
  grep against `gpx/migrations/0001_initial.py`: no `unique_together`, no `UniqueConstraint`.

Two model-level notes for a multi-stage world: `Meta.ordering` is **descending**, so a
chronological stage list needs an explicit ascending `order_by` at the query site rather than a
`Meta` change (flipping `Meta` would silently invert `.tracks.first()` everywhere it is still
used); and `__str__` returns bare `original_filename` (`:62-63`), so two stages of a trip can
render identically in admin widgets.

`GpxUploadForm` (`gpx/forms.py`) has `fields = ("file",)` and a `clean_file()` that parses and
populates the unsaved instance. It has **zero** awareness of the trip's other tracks — nothing
to change there for ADD.

### 4. Chronological ordering: what exists, what does not, and the three candidate designs

**What the parse captures.** The single parse is `gpx/parsing.py:258` (`gpxpy.parse(text)`).
Points are built at `:269-277`:

```python
points = [
    (
        round(point.latitude, COORDINATE_DECIMAL_PLACES),
        round(point.longitude, COORDINATE_DECIMAL_PLACES),
    )
    for track in gpx.tracks
    for segment in track.segments
    for point in segment.points
]
```

`point.time` appears nowhere in that comprehension. `point.elevation` is likewise reduced to
two scalars. `gpx/parsing.py:143` is documented as *"the only point in the entire request
lifecycle where the full gpxpy object, with elevation and time intact, exists."* This exclusion
was deliberate and is recorded:
`context/archive/2026-08-27-trip-distance-duration-stats/plan.md:31-33` — *"Elevation and
per-point timestamps are **discarded** inside the list comprehension… they never reach the
database."*

**Duration is not a timestamp pair** (`gpx/parsing.py:116-118`):

```python
duration_seconds: float | None = None
if gpx.get_time_bounds().start_time is not None:
    duration_seconds = gpx.get_duration()
```

`get_time_bounds().start_time` / `.end_time` — the absolute wall-clock values a chronological
sort needs — are live on the in-memory object **at this exact line**, read only as a presence
probe, and then dropped. `get_duration()` returns a relative span (sum of each segment's own
first-to-last), per `ParsedTrack.duration_seconds`' docstring (`gpx/parsing.py:144-158`).

**The points blob cannot supply order.** `ParsedTrack.json_points` (`gpx/parsing.py:169-176`)
persists `[[lat, lon], ...]` only. Capped at `MAX_GPX_POINTS = 100_000`
(`gpx/constants.py:22`).

**Candidate designs, with the evidence for each:**

| Design | Verdict from evidence |
| --- | --- |
| (a) Store absolute start (and end) datetimes on `GpxTrack` at parse time | The only design with a data source. Values are already in hand at `gpx/parsing.py:117` and thrown away; capturing them is additive to `ParsedTrack` and `clean_file`. Requires a new nullable column + a backfill for existing rows, following the exact `0002`→`0003`→management-command precedent. |
| (b) Derive order at read time from the stored blob | **Impossible.** The blob holds no timestamps (above). The only read-time alternative is re-parsing `track.file` on render, which this project has rejected twice on explicit grounds — see below. |
| (c) An explicit user-controlled order field | Ruled out by product, not by code: "no manual stage reordering" is a named Non-Goal (`prd.md:106`, `roadmap.md:118`) and order "is always derived from GPS timestamp." |

Re-parsing at render is rejected in two places with the same reasoning —
`.../trip-distance-duration-stats/plan.md:128,155-156`: *"No re-parsing at render time.
Rejected deliberately… `GpxDownloadView` already proves a row's file can go missing, and the
PRD's only NFR forbids a blank page"* — and restated in the model docstring (*"can never fail
on a parse"*). A multi-stage design that orders by re-parsing would revive exactly this.

**Backfill for existing rows.** Sources, in order of viability: the stored `.gpx` file
(viable, via the established re-open-and-re-parse pattern); the points blob (not viable, no
timestamps); nothing (rows stay null, exactly as the stats columns do today). The precedent
command is `gpx/management/commands/backfill_gpx_stats.py` — `--all` vs null-only filter,
`.only("id", "file", *STATS_FIELDS)` to keep `points` off the query, per-row
`try/except Exception` with a `filled`/`skipped` tally rather than aborting.
`backfill_track_statistics` (`gpx/statistics.py:62-106`) already documents five failure modes
that leave a row null.

**A real design gap this exposes:** a GPX file with no `<time>` elements yields a NULL start
time — legitimately, and `duration_seconds` proves it happens (that is what its presence probe
exists for). So the ordering key is nullable, and **this repo has no precedent for ordering by
a nullable field**: both `Meta.ordering` tuples pair a non-null business field with `-id` as
tiebreaker (`trips/models.py:19`, `gpx/models.py:59-60`). What order a timestamp-less stage
takes is an open product question; `uploaded_at` (already present, `auto_now_add`) is the
obvious fallback key, but that is a decision, not a default.

**Migration inventory** (relevant precedent):

- `gpx/migrations/0001_initial.py` — creates `GpxTrack`.
- `gpx/migrations/0002_gpxtrack_stats.py` — `AddField` ×4, all nullable. Schema only.
- `gpx/migrations/0003_backfill_gpxtrack_stats.py` — data-only `RunPython`, separate from
  `0002` *"per the additive-first migration rule: the schema change and the data write are
  independently reversible"* (`:3-4`). Imports `backfill_track_statistics` **inside** the
  function body (`:34`) under a broad `except Exception` so a rename degrades to one logged
  skip; selects `distance_meters__isnull=True`, `.only(...)` to skip `points`, and wraps each
  row in a savepoint because `Model.save_base` otherwise poisons the outer transaction
  (`:57-65`).
- `trips/migrations/0001_initial.py` — the only `trips` migration; creates `date` (`:27`) and
  `ordering = ["-date", "-id"]` (`:39`).

### 5. The rendering pipeline, end to end

**Server** — `gpx/map_config.py:1-55`:

```python
def build_map_config(track: GpxTrack | None) -> dict[str, Any] | None:
    if track is None or not track.points:
        return None
    return {
        "points": track.points,
        "bounds": [
            [track.min_latitude, track.min_longitude],
            [track.max_latitude, track.max_longitude],
        ],
        "icons": {
            "iconUrl": static(MARKER_ICON),
            "iconRetinaUrl": static(MARKER_ICON_RETINA),
            "shadowUrl": static(MARKER_SHADOW),
        },
    }
```

`icons` are resolved server-side deliberately: Leaflet's default icon builds
`marker-icon-2x.png` / `marker-shadow.png` URLs at runtime, which the hashed staticfiles
manifest never rewrites — *"silent 404s in production that pass every gate locally"*
(`.../upload-gpx-and-view-map/plan.md:933-936`). Bounds come from the four stored scalar
columns, not from `polyline.getBounds()`, to keep the degenerate-bounds decision server-side
(`plan.md:929-931`). Whole-trip bounds across N stages are therefore a cheap aggregate of
columns that already exist and are non-null (min of mins, max of maxes).

**Template** — `trips/templates/trips/trip_detail.html`: the config crosses into JS via
`{{ map_config|json_script:"map-config" }}` (not `|safe` — coordinates are user data), with
Leaflet and `map.js` loaded only inside `{% if map_config %}`. A `.map-fallback` `<p>` sits
inside `#map` and is left standing if JS fails.

**Client** — `gpx/static/gpx/map.js`: one `L.map` with the interactivity flags the S-02 change
flipped; **one** `L.polyline(config.points, {color: "#ff7800", weight: 5, opacity: 0.85})`;
**exactly two** hardcoded `L.marker` calls (`config.points[0]` titled "Start",
`config.points[length - 1]` titled "Finish") sharing one `L.icon`;
`map.fitBounds(config.bounds, {padding: [20, 20]})`; and a single all-or-nothing `try/catch`
that leaves the fallback paragraph in place and console-logs.

**Extension points, concretely.** `config.points` is flat → segments need a nested structure
(per-stage arrays, or a flat array plus break indices). Marker creation is two literal calls,
not a loop → stage-break markers need marker-array-driven logic. `build_map_config` takes a
single `track`, and its two callers — `trips/views.py:96` and `gpx/views.py:78`, both
`.tracks.first()` — each pick only the newest track (`Meta.ordering` is `-uploaded_at`). Both
call sites' docstrings warn that the two pages must never drift, so they change together.

**Constraints on how the render may change:**

- `tests/trips/test_trip_detail_map.py` pins the `#map` container's markup **byte-for-byte via
  regex**, so new map UI must be injected by `map.js` at runtime as a Leaflet control, never
  by editing the template — carried explicitly from the S-02 change
  (`.../interactive-trip-map/plan.md:52-65`).
- `context/foundation/test-plan.md:323` scopes map testing to *"the map configuration the
  server hands the page; do not diff the rendered canvas."* So the assertions land on the
  payload shape (segments and markers as data), not on Leaflet's drawing. The S-02 change
  relied on the same boundary to justify adding no JS tests
  (`.../interactive-trip-map/plan.md:22-25`) — no JS test harness exists in the repo.
- New static assets must be added to the `STATIC_REFERENCES` tuple in
  `tests/test_static_references.py` (checked against `finders.find()`), whose second gate
  renders a page through the production manifest backend and skips itself when no manifest has
  been collected.
- Vendored bytes are integrity-gated: `gpx/static/gpx/vendor/` and `static/vendor/bootstrap/`
  each carry `SHA256SUMS`, verified by the `gates` job *before* `uv sync`. Per-stage styling
  must live in project-owned files.

### 6. The design-system / PRD color conflict

`context/foundation/design-system.md` defines six tokens — primary green `#2f5d50`, secondary
gray, accent orange `#f97316`, plus bg / surface / border / text — and states **"Do not
introduce additional colors,"** with orange *"not to exceed roughly 10% of the visible
interface."* Its route-styling spec (`:449-457`) prescribes `color: #f97316; weight: 5;
outline: 2px solid white`.

`prd.md:70` requires the opposite: *"each stage rendered as a visually distinct segment (e.g. a
different line color per stage)."* And that clause is not incidental — it is the *resolution*
of a recorded counter-argument (`prd.md:71`): a single undifferentiated line would imply
continuous riding across a rest day, so distinct segments are the fix for a correctness
problem, not decoration.

No categorical or accessibility-checked multi-hue palette exists anywhere in the repo (no CSS
custom properties, no constants module, no Bootstrap theme vars carrying one). A 3–5 stage tour
has no colors to draw from under the current rule.

Also noted, pre-existing: the shipped `map.js` uses `#ff7800` while the design system specifies
`#f97316` — drift that predates this change, and that a per-stage palette decision would be the
natural moment to reconcile.

### 7. E-10: the `Trip.date` question

**The blocker as written no longer resolves.** `roadmap.md:238` conditions the split on a PRD
amendment because *"FR-003, FR-007 and the Primary Success Criterion all say 'a date',
singular."* Against the live tree:

- **FR-003** — only in `context/foundation/archive/prd-2026-05-29-v3.md:66`: *"User can create
  a trip with a name, date, and description. Priority: must-have."*
- **FR-007** — only in the same archived file, `:74`: *"User can edit a trip's details (name,
  date, description)."*
- **Primary Success Criterion** — the archived v3 one (`:35-36`) did say *"create a trip (name,
  date, description)."* The **live** one (`prd.md:46`) has been fully rewritten and concerns
  multi-stage rendering on an interactive map; it contains no reference to a trip date.
- The live PRD v4 carries **no FR numbering at all** — it is a brownfield delta PRD organized
  by `## Scope of Change` bullets.

So there is no live sentence to amend, and the archive must not be edited
(`AGENTS.md` Hard Rules; `lessons.md` #7). The blocker is stale in its literal form. What
*does* still bind from the live PRD is narrower and different: Guardrails require that
*"existing single-GPX, single-date trips keep working through the data-model change with no
manual migration step from the user"* (`prd.md:53`), and `## Scope of Change` contains **no
date-field bullet** — so a split would be new scope inside a 1-week hard deadline, which is a
budget argument rather than a documentation one.

**The split still has no consumer.** `frame.md:56-58` (from `edit-and-delete-trip`) found this
already: *"`prd.md:99` assigns multi-day stage chronology to **GPS timestamps**, not
`Trip.date`. The feature that most needs multi-day temporal semantics explicitly routes around
this field."* Finding 4 above confirms it from the other end — ordering will come from a new
`GpxTrack` timestamp column. E-10 was parked awaiting FR-011 as its trigger
(`roadmap.md:238`); FR-011 has now arrived and turns out not to read the field.

The owner's original words, for the record (`frame.md:17-19`, 2026-08-26): *"i havent think
about it. for one day trip it is simple, for mulit day, better will be two date fields - start
and end."* Disposition at the time (`.../edit-and-delete-trip/change.md:23`): *"Raised but
deliberately **not** actioned."*

**Consumer inventory, if the split were taken.** Application code — `trips/models.py:10`
(field), `:19` (`Meta.ordering`); `trips/forms.py:21` (fields), `:23` (widget), `:35` (help
text), `:38-54` (`clean_date`, including the `changed_data` escape hatch and the future-date
rule); `trips/constants.py:13` (`FUTURE_TRIP_DATE_TOLERANCE`); `trips/admin.py:17`
(`list_display`); `trips/migrations/0001_initial.py:27,39`. Templates —
`trip_detail.html:19`, `trip_list.html:15`, `trip_confirm_delete.html:9` (all bare
`{{ trip.date }}`, no label word); `trip_form.html` renders the field generically, so label and
help text come from `Meta`. Tests — a large surface across 11+ files, including ordering
assertions that directly test `Meta.ordering`
(`tests/trips/test_trip_model.py:22-28,32-38`), the tolerance tests
(`tests/trips/test_trip_creation.py:129-169`), the help-text render test (`:172-187`), the
detail page's `date_format(trip.date)` assertion (`tests/trips/test_trip_detail.py:14-30`), the
`changed_data` escape tests (`tests/trips/test_trip_edit.py:266-311`), and
`tests/test_ownership_matrix.py:47,148-150`, which pins `TARGET_TRIP_DATE` and asserts `date`
round-trips through the matrix harness. The earlier frame doc's estimate of *"~31 test sites
across 9 files"* is consistent with what the inventory found.

**The terminology fix, precisely.** There is no string "Date of trip" in the repo. The label is
Django's auto-derived **"Date"**, and `trips/forms.py:31-32` records that this was deliberate:
*"`labels` is deliberately not used. The auto-derived label is already 'Date'; what was missing
is the sentence saying which date."* That sentence is the help text at `:35` — *"The day the
ride happened — VeloLog is a diary, not a planner."* — and it is what a multi-day tour makes
wrong, since a tour does not happen on *a* day. Changing it touches `trips/forms.py:35` and the
substring assertion at `tests/trips/test_trip_creation.py:172-187` (which asserts *"The day the
ride happened"*, plus the `id="id_date_helptext"` / `aria-describedby` wiring). Note the same
comment block warns that `help_texts` is plural and a singular typo is silently ignored — which
is exactly why that test asserts the rendered page rather than the dict.

One semantic knock-on worth naming: `clean_date` compares against
`timezone.localdate() + FUTURE_TRIP_DATE_TOLERANCE` (`trips/forms.py:50`, one-day slack
documented as a UTC-vs-local correction in `trips/constants.py:1-13`). If the single date is
re-worded to mean a tour's *start*, the future-date rule keeps working unchanged; if it were
re-worded to mean the *end*, the rule's meaning shifts. Whichever wording is chosen should be
the one the rule already implements.

## Code References

- `gpx/views.py:89-122` — `form_valid`; `:116` reads all tracks, `:121` deletes them. The
  REPLACE mechanism.
- `gpx/views.py:57-66` — owner-scoped `get_trip()`; `:47-55` resolves the trip *before* the
  upload is inspected.
- `gpx/views.py:78`, `trips/views.py:96` — the two `.tracks.first()` render sites that must
  change together.
- `gpx/signals.py:80-113` — `post_delete` receiver; correct under ADD, and the reason a
  leftover delete becomes file loss.
- `gpx/signals.py:116-182`, guard at `:160-164` — `pre_save` receiver; returns on every
  insert, never trip-aware.
- `gpx/models.py:20-63` — `GpxTrack`; FK rationale in the docstring, `Meta.ordering` descending
  at `:59-60`, no uniqueness constraint anywhere.
- `gpx/parsing.py:258` — the single `gpxpy.parse`; `:269-277` discards `point.time`;
  `:116-118` reads and drops `get_time_bounds()`.
- `gpx/parsing.py:169-176` — `json_points`, the persisted `[[lat, lon], ...]` shape.
- `gpx/map_config.py:1-55` — the flat map payload.
- `gpx/static/gpx/map.js` — one polyline, two hardcoded markers, server-supplied bounds.
- `gpx/statistics.py:62-106` — `backfill_track_statistics`, the re-parse-from-storage pattern;
  `:206-245` — `build_trip_stats(track)`, single-track.
- `gpx/migrations/0003_backfill_gpxtrack_stats.py:34,54-65` — import-under-guard, `.only()`,
  per-row savepoint.
- `gpx/management/commands/backfill_gpx_stats.py` — the manual recovery precedent.
- `gpx/constants.py:16-22` — `MAX_GPX_POINTS = 100_000`, and the note that `points` is
  re-read and inlined into the detail page on every view.
- `trips/forms.py:31-35` — why there is no `labels` override, and the help text to revise.
- `context/foundation/design-system.md:449-457` — route styling spec and the six-token rule.
- `context/foundation/archive/prd-2026-05-29-v3.md:66,74,35-36` — FR-003, FR-007, and the
  archived Primary Success Criterion.
- `tests/test_ownership_matrix.py:258-265` — the `gpx:upload` inventory row and its probe;
  `:158-174` — `_assert_no_track_was_attached`, single-track-shaped.
- `tests/mutations.py:11-13` — patch the name where it is used, not where it is defined.
- `tests/test_assertion_strength.py:53-64` — `WAIVER_INVENTORY` shape.

## Architecture Insights

- **The schema was built for this change; only the write path and the read path encode v1.**
  Decision D1 spent its budget up front on an FK so that FR-011 *"needs no migration rewrite."*
  That prediction held for the geometry side and failed for the temporal side: nobody
  anticipated that ordering stages would need a timestamp the parser throws away. The lesson
  generalizes — a forward-looking *relationship* was preserved while a forward-looking *field*
  was discarded on the same code path, in the same change.
- **Derive-once-at-upload is a load-bearing invariant, not a performance choice.** "Rendering
  can never fail on a parse" is asserted in the model docstring, defended twice against
  re-parsing at render, and traced to the PRD's only NFR. Any multi-stage design should add
  columns at parse time rather than move work to render.
- **Scalar columns are the established shape for derived numbers**, chosen twice over JSON
  (bounds first, then stats): *"scalar columns are the established precedent for derived
  numbers on this model"* (`.../trip-distance-duration-stats/plan.md:158-160`). A start/end
  timestamp pair follows that precedent; stuffing them into the `points` blob would break it.
- **File-lifecycle safety is centralized in signals precisely so call sites cannot get it
  wrong** — and the flip side is that call sites now carry the full weight of *whether* to
  delete. The signals cannot second-guess an unwarranted delete, which is exactly why the ADD
  change is dangerous despite the signals being correct.
- **The test harness is self-policing in three places** (ownership inventory asserted against
  the URLconf, assertion-strength waivers checked both directions, bite-proof shapes naming
  guard tests), so a new route or a weakened test fails the suite rather than shipping unproven.

## Historical Context (from prior changes)

- `context/archive/2026-08-23-upload-gpx-and-view-map/change.md:35-42` — decision D1: FK for
  many-tracks-per-trip; replace-on-upload flagged as *"Assumption to confirm at plan review."*
- `.../upload-gpx-and-view-map/reviews/impl-review-phase-3.md:173-178` — replace semantics
  raised at review and upheld, with the reasoning that the invariant belongs at the
  track-creating boundary.
- `.../upload-gpx-and-view-map/reviews/impl-review-phase-4.md:98-114` — the concurrency finding
  that produced the read-inside-transaction-then-delete-by-explicit-pk ordering.
- `.../upload-gpx-and-view-map/plan.md:406-419,834-836,924-936` — derive-once rationale, scalar
  bounds, Leaflet 1.9.4 pinning (2.0 still alpha with an unknown release date), explicit icon
  URLs against the hashed manifest.
- `context/archive/2026-08-27-trip-distance-duration-stats/plan.md:31-33,112-128,155-160` —
  per-point timestamps and elevation discarded; no re-parsing at render; four scalar columns
  over JSON; elevation chart (GPL-3.0) and moving-time stats both parked.
- `context/archive/2026-08-28-gpx-upload-orphan-file/` — the two-receiver design and
  `reconcile_media` as backstop. Notably, a grep for `FR-011|multi-stage|multiple tracks`
  matches **neither** this folder nor `2026-08-30-testing-file-lifecycle-storage-consistency`:
  the file-lifecycle work was built on the single-track assumption without ever revisiting it.
- `context/archive/2026-09-02-interactive-trip-map/plan.md:5-8,22-25,52-65` — *"Applies to
  every trip, single-stage or multi-stage"*; deliberately did not touch `gpx/map_config.py`;
  the byte-for-byte `#map` markup pin and the runtime-injection rule. No backlog row was opened
  by that change for stage-break markers.
- `context/archive/2026-08-26-edit-and-delete-trip/frame.md:17-19,56-58,117-125` — the owner's
  two-date-fields quote, the finding that stage chronology routes around `Trip.date`, and the
  deferral naming FR-011 as trigger.
- `context/foundation/test-plan.md:45-51,127,323` — Risk #1 (replace/delete leaves or removes a
  file), #3 (row survives, track unreachable), #5 (malformed upload), #6 (detail page breaks
  instead of degrading); the ownership-matrix gate "has teeth because the module asserts its
  own inventory against the URLconf"; and the map-testing boundary.

## Related Research

- `context/archive/2026-08-23-upload-gpx-and-view-map/research.md` — original GPX/Leaflet
  exploration, including the rejection of `leaflet-gpx` (client-side parsing redundant once
  `gpxpy` parses server-side) and of serving raw GPX from `MEDIA_URL`.
- `context/archive/2026-09-02-interactive-trip-map/research.md` — Leaflet 1.9.4 interactivity
  options and the vendoring rationale.
- `context/archive/2026-08-26-edit-and-delete-trip/research.md:198` — FR-003's text quoted
  against the then-live PRD.

## Open Questions

1. **Per-stage colors vs. the design system.** `prd.md:70` requires distinct per-stage line
   colors; `design-system.md` says do not introduce additional colors and caps orange at ~10%.
   No categorical palette exists. Someone must decide: amend the design system with a
   bounded categorical palette, or distinguish stages without hue (alternating two existing
   tokens, or varying weight / opacity / dash pattern). Owner: user. **Blocks** the rendering
   phase of planning. Worth deciding alongside the `#ff7800` vs `#f97316` drift.
2. **Ordering key for a stage with no GPS timestamps.** A GPX with no `<time>` elements yields
   a NULL start time, and the repo has no precedent for ordering by a nullable column. Is the
   fallback `uploaded_at`, is such a file rejected at upload, or does it sort last? Owner: user.
   Block: no, but it must be answered before the ordering code is written.
3. **What the stats panel shows once a trip has N stages.** `prd.md:107` makes multi-stage
   statistics a Non-Goal, but "not extended" does not resolve what renders:
   `build_trip_stats(track)` takes one track and `trips/views.py:96` currently hands it the
   *newest*. Left as-is, a 3-stage tour would silently display stage 3's distance as the
   trip's. Showing the newest stage's numbers unlabeled is a correctness problem of the same
   family the PRD already fixed for the undifferentiated polyline. Owner: user. Block: no —
   but it is forced by this change, not deferrable.
4. **Detail-page payload size across N stages.** `points` is capped at 100,000 points per
   track and `gpx/constants.py:16-21` notes it is *"re-read and inlined into the trip detail
   page on every view."* N stages multiply that inline JSON N-fold, against an NFR that the
   page must reach an interactive state *"within a time that does not feel broken on typical
   home broadband"* (`prd.md:101`). No measurement exists. Owner: user. Block: no — but if a
   cap or a coordinate-thinning step is needed, it is cheaper to decide in planning than after.
5. **Download links for N stages.** `gpx:download` is keyed on a *track* pk and is already
   per-track, so the route needs no change — but the detail template surfaces one file today.
   Multi-stage needs N links, which is new UI subject to the byte-for-byte `#map` pin only
   insofar as it sits outside that container. Owner: user. Block: no.
6. **Does E-10 get closed, re-triggered, or re-worded?** Its literal blocker is stale
   (finding 4) and its functional trigger turned out not to consume the field (finding 7). The
   roadmap row should end this change saying something accurate — whether that is "wording
   fixed, split still parked with a corrected trigger" or "closed." Note `lessons.md` #5:
   update `AGENTS.md` and roadmap status in the same slice that invalidates them. Owner: user.
   Block: no.
7. **Stage removal stays out of scope — and the ownership matrix stays untouched only while
   that holds.** Carried from `change.md:18` and `roadmap.md:73`, and confirmed against the
   live inventory: no new `<int:pk>` route means no new `OBJECT_SCOPED_ROUTES` row. If a
   per-stage delete route is added, it needs a row plus a probe or
   `tests/test_ownership_matrix.py:321-337` turns the suite red. Separately,
   `_assert_no_track_was_attached` (`:158-174`) computes
   `expected = [] if target.track is None else [target.track.pk]` — single-track-shaped, and
   worth reviewing if fixtures start seeding multiple stages.
8. **US-02 still has no acceptance-criteria checklist.** Carried unresolved from `prd.md:112`
   and `roadmap.md:113`. Findings 1–3 give it concrete content now (what must not be deleted,
   what order means when timestamps are absent, what "visually distinct" resolves to), so this
   is the moment it is cheapest to write. Owner: user. Block: no.

## Follow-up Research 2026-09-02T20:10+02:00

**Question:** open question 3 concerns the stats panel under N stages, which is roadmap slice
S-03 (`roadmap.md:44,89-99`). Should S-03 be melded into S-01?

**Assessment: no — with one thin piece moved into S-01 that is not S-03 work.**

The question conflates two things:

- **(a) What the panel renders once a trip has N stages.** A correctness obligation of S-01.
  `trips/views.py:96` calls `.tracks.first()`, `Meta.ordering` is `["-uploaded_at", "-id"]`, so
  `build_trip_stats` receives the *newest* track. Ship ADD semantics untouched and a 3-stage
  tour prints stage 3's distance under a heading that reads as the trip's — a wrong number, the
  same family as the undifferentiated polyline already fixed at `prd.md:71`. Not deferrable.
- **(b) Whole-trip aggregation plus a per-stage breakdown.** Genuinely S-03, parked by
  `prd.md:107`.

**Why aggregation is not a cheap add-on to S-01.** `duration_seconds` is NULL when a file
carries no `<time>`, and elevation gain/loss are NULL when it carries no `<ele>`;
`gpx/statistics.py:206-245` checks `all(value is None ...)` rather than falsiness precisely
because `0.0` is a legitimate stored value. SQL `Sum()` skips NULLs, so three stages where one
lacks elevation data would report a trip elevation gain that silently omits a stage — a
fabricated number, the exact trap two separate presence probes exist to prevent
(`gpx/parsing.py:117`; `_has_elevation_data`). Honest aggregation therefore requires a
partial-data presentation rule, which is S-03 design work. S-03 also improves by waiting: S-01
introduces the absolute start-timestamp column that makes elapsed tour duration expressible at
all, so merging means designing the duration story without the field that fixes it.

**Structural arguments.** `roadmap.md:94` makes S-01 a prerequisite of S-03 — merging collapses
a real dependency into one slice. `roadmap.md:98` designates S-03 the first item to drop if
S-01 or S-02 run long; merging it into the riskiest slice before a hard 2026-09-10 deadline
removes that drop-valve, since it could then only be cut by cutting into the north star.

**Recommended disposition for S-01.** Bind the existing panel to the stage it describes: render
stats **per stage**, inside the stage list S-01 must build anyway for the N download links
(open question 5). Three properties make this minimal:

- `build_trip_stats` needs no signature change — it is called once per track. (Contrast
  `build_map_config`, which genuinely must change payload shape.)
- No aggregate is invented, so the mixed-nullity trap never arises.
- A single-stage trip renders one stats block exactly as today, satisfying `prd.md:53`, and it
  matches the PRD's own wording that "v1's stats display continues to reflect only what it
  already covers" (`prd.md:107`).

S-03 then becomes purely additive — a whole-trip summary above the per-stage rows, plus the
partial-data rule — and stays cuttable.

**Fallback under time pressure:** suppress the panel when `tracks.count() > 1`. Honest, but it
hands a multi-stage user less than v1 gave them, so it is a deadline concession rather than a
design.

**Knock-on:** either option touches `tests/trips/test_trip_detail_stats.py`. Per `lessons.md`
#5, S-03's roadmap row should be re-worded in the same slice that lands per-stage display,
since that would no longer be S-03's to deliver.

## Follow-up Research 2026-09-02T20:35+02:00 — temporal modeling (stages and trip)

**Question:** if a trip carries `(start, end)` to enable multi-day tours, and a stage is
assumed to be one day, what happens to a ride finishing after midnight, or a pure night ride?

**Answer: the assumption "a stage has one date" is the part that fails, and it fails on the
common case, not the edge case.** A stage is an interval between two instants; a date is a
lossy projection of an instant onto a calendar that requires a timezone to compute.

**Environment (verified).** `velo_log/settings.py:131` — `TIME_ZONE = "UTC"`; `:135` —
`USE_TZ = True`. GPX fixtures are `Z`-suffixed UTC (`tests/gpx/fixtures/timed-track.gpx:6`),
per the GPX 1.1 spec. The fixture coordinates (50.06, 19.94) are Kraków — UTC+2 in June.

**Why a per-stage date is undecidable.** For a Kraków rider:

| Ride (local) | UTC | Local date | UTC date |
| --- | --- | --- | --- |
| 1 Jun 23:30 → 2 Jun 01:30 | 1 Jun 21:30Z → 1 Jun 23:30Z | straddles 1→2 | entirely 1 Jun |
| 2 Jun 00:30 → 2 Jun 02:30 | 1 Jun 22:30Z → 2 Jun 00:30Z | entirely 2 Jun | straddles 1→2 |

Each convention converts a straddling ride into a single-date one and vice versa, so the two
answers disagree and neither is wrong. This project already paid for this mismatch once:
`FUTURE_TRIP_DATE_TOLERANCE = timedelta(days=1)` (`trips/constants.py:13`) exists precisely
because `timezone.localdate()` yields the UTC date while the `type="date"` widget submits the
rider's local one (`roadmap.md:222`). A date per stage multiplies that one-field fudge by the
stage count.

**Stage level — store instants, not dates.** `started_at` / `ended_at` as aware
`DateTimeField`s. Ordering becomes a total order on instants with no midnight case to handle,
and "which day was this?" becomes a presentation question answerable truthfully as a range
("1 Jun 22:30 → 2 Jun 03:30"). This costs nothing extra: finding 4 already established that
S-01 must add a start-timestamp column regardless, because chronological ordering has no data
source today. Projecting those instants down to dates would discard information the change is
about to start capturing.

**Trip level — derive the span, keep one stored field.** Trip span is `min(started_at)` …
`max(ended_at)` over stages: derived, it cannot disagree with the tracks; stored, it is a second
source of truth whose only novel behavior is drift (user types 3–7 June, stages span 3–8 June).
It cannot be *purely* derived, though — trips are created before any stage exists
(`trips:create` → `gpx:upload`), `Trip.date` is non-null (`trips/models.py:10`), and
`Meta.ordering = ["-date", "-id"]` (`:19`) needs a non-null key, with no precedent in this repo
for ordering by a nullable column (finding 4). Recommended shape: **keep the single
user-entered field, re-worded as the day the tour started, and derive the displayed span from
stage instants once stages exist.** This needs no `Trip` migration, keeps `clean_date`'s
future-date rule semantically unchanged, and preserves the ordering key.

**Consequence for E-10 (resolves open question 6).** Two independent findings stack here, and
both must be recorded together or the row will be misread.

1. **The PRD-amendment blocker is removed** — user-confirmed 2026-09-02. The amendment
   happened as a *regeneration*: PRD v4 superseded v3 wholesale (v3 now at
   `context/foundation/archive/prd-2026-05-29-v3.md`), so FR-003, FR-007 and the singular-date
   Primary Success Criterion no longer exist in any governing document. Nothing procedural
   stands in the way of the split. The one live sentence in v4 touching dates is the Guardrail
   at `prd.md:53` ("existing single-GPX, **single-date** trips keep working… with no manual
   migration step") — not a blocker, since it presupposes a data-model change and constrains
   only backward-compatibility.
2. **The split is unnecessary regardless** — the `(start, end)` pair is *derivable* as
   `min(started_at)` … `max(ended_at)` over stages, so storing it would be denormalization
   whose only novel behavior is drift. The derived-span approach satisfies `prd.md:53`
   trivially, because `Trip.date` does not change shape at all.

Taken together, clearing the blocker makes E-10 **closable, not due**. Recording only (1)
would leave the row reading "blocker cleared" and invite the next reader to perform the split.
This also supersedes finding 7's weaker argument (that the trigger FR-011 turned out not to
consume the field) — that remains true, but derivability is the decisive reason.

**Two implementation notes:**

- **Do not constrain a stage to one day.** A 24-hour ultra or a brevet is one continuous file
  spanning more than a day; the constraint would reject legitimate data and buys nothing, since
  the merge orders by instants.
- **Normalize the timezone at parse.** GPX 1.1 requires UTC and the fixtures comply, but real
  exporters sometimes emit local offsets or omit zone info. Under `USE_TZ=True` a naive
  datetime saved to a `DateTimeField` raises a `RuntimeWarning` and is interpreted against the
  default zone — so normalize to UTC, or treat a naive/absent value as "no usable timestamp"
  and route it to open question 2's fallback, rather than storing a silently wrong instant.
- **Overlapping stages** (the same ride uploaded twice, or a GPS glitch) still order fine by
  start instant, but a "stage break" marker between two overlapping stages has no real-world
  referent. Minor, and worth one line in the plan's acceptance criteria.

## Follow-up Research 2026-09-02T21:05+02:00 — resolves open question 2 (absent timestamps)

**Question:** what orders two stages of one trip when *neither* GPX file carries timestamps —
and, in parallel, what becomes of the derived trip timespan when nothing is derivable? Could
future user edits fill the gap?

### The fixtures reframe this from a corner case to the default path

`grep -L "<time>"` over `tests/gpx/fixtures/*.gpx` shows the repo's two canonical **valid**
fixtures — `valid-track.gpx` and `second-track.gpx` — carry **no `<time>` elements**. Only
`timed-track.gpx` and `two-segment-track.gpx` do. `second-track.gpx` is the fixture named for
the second-upload scenario, so "both stages untimed" is the shape the existing suite exercises
by default, not an exotic input.

**Test consequence, and it is load-bearing:** unless a *second timed fixture* is added (a
`timed-track.gpx` sibling whose timestamps fall later), the chronological ordering feature will
never be exercised by any test — only its fallback will. Green suite, unproven behavior; the
shape of `lessons.md` #1 and #3. The plan should treat "add a second timed fixture" as a
prerequisite of the ordering phase, not an afterthought.

### One expression covers all three cases

Verified against the Django 6.0 docs
([expressions ref](https://docs.djangoproject.com/en/6.0/ref/models/expressions)):
`F("field").asc(nulls_last=True)` is valid inside `order_by()`.

```python
tracks.order_by(F("started_at").asc(nulls_last=True), "uploaded_at", "id")
```

| Case | Result |
| --- | --- |
| All stages timed | Pure chronological order. |
| **No stages timed** | Every key is NULL, so the tiebreakers decide: `uploaded_at`, then `id` — both non-null columns that already exist, matching the repo's established `-id`-tiebreaker convention (`gpx/models.py:59-60`, `trips/models.py:19`). |
| Mixed | Timed stages in order first, untimed appended in upload order. No two-tier branching in code. |

**The trap to avoid:** do **not** `COALESCE(started_at, uploaded_at)` into one sort key. It
yields a total order but compares a *ride* instant against an *upload* instant — different
clocks. A stage ridden 5 June (timed) beside an untimed stage uploaded 1 June sorts the untimed
one first regardless of when it was actually ridden. Deterministic, and meaningless.

### Separate the order displayed from the claim made about it

The sort always produces *an* order; what varies is whether that order is *evidence*. Derive one
per-trip predicate — `all(stage.started_at is not None)` — and let it gate every claim that
depends on established chronology:

1. **Wording** — if false, the page must not say "chronological." Upload order presented as
   ride order is a fabricated fact.
2. **Stage-break markers** — a "stage break" asserts *the rider stopped here and resumed
   there*. Between upload-ordered stages that has no basis, and the marker would land on an
   arbitrary pair of endpoints. Suppress it; keep the per-stage segments and their own
   endpoints, which stay truthful because they are separate files.
3. **The derived trip timespan** — see below.

This is the discipline the codebase already applies to statistics: `build_trip_stats` returns
`None` rather than zeros (`gpx/statistics.py:206-245`), and two separate presence probes exist
so `0` never masquerades as "not recorded". Degrade the *claim*, not the render.

### The derived timespan degrades the same way — and lands on v1's behavior for free

Follow-up 2 recommended deriving the trip span as `min(started_at)` … `max(ended_at)` rather
than storing it. With no timestamps there is nothing to derive, and the fallback is already
correct: display the stored `Trip.date` alone (the user's stated start day), which is exactly
what v1 renders today (`trip_detail.html:19`). So the untimed case needs no new UI — it is the
current UI.

The **mixed** case carries the real trap, and it is the same NULL-skipping fabrication as
elevation summing in follow-up 1: SQL `Min`/`Max` ignore NULLs, so a span computed over the
timed subset is a *lower bound* on the true span, not the span. Reporting it as the span
understates the tour silently. Hence the rule: **derive the span only when the chronology
predicate above is true**; otherwise show the stored start date and no span. One predicate,
three consumers — it is a single concept ("is this trip's chronology established?"), not three
independent flags.

### On future user edits — a real capability, but it belongs on the stage, not the trip

Letting a rider supply missing temporal data is a legitimate future feature, and it is **not**
the same thing as the manual-reordering Non-Goal (`prd.md:106`), though it brushes against its
spirit. The distinction determines the design:

- **Supplying a missing instant** is data entry. Ordering stays a pure function of instants,
  so the Non-Goal ("stage order is always derived from GPS timestamp") softens only to
  "derived from timestamps, whether recorded or supplied." Small conceptual change.
- **Storing a manual order** (an `order` / `position` column) creates a second source of truth
  that can disagree with the timestamps, and needs a reconciliation rule on every later upload
  — when a new stage's instant falls mid-sequence, is it inserted or appended? This is the same
  derive-don't-store argument that retired E-10's field split, applied one level down.

**Recommendation:** if user edits ever ship, they edit a **stage's** `started_at`/`ended_at`,
never the trip's span directly — editing the trip span reintroduces E-10's two-sources-of-truth
drift, while editing stage instants feeds the derivation that everything else already reads.

**Forward-compatibility is free in this slice.** Making `started_at`/`ended_at` nullable — which
absent timestamps force anyway — is the whole schema requirement. A future edit capability then
needs only a form, no migration. So this slice should *not* build the edit UI, and should also
not add an order column that a future edit capability would have to unpick.

Suggested backlog shape (roadmap edit not yet approved by the user): a `## Parked` or
Engineering Backlog row for "rider supplies missing stage timestamps", triggered when an untimed
multi-stage trip is actually encountered in real use — which the empirical question below
decides.

### Open empirical question

How often do the owner's real files lack timestamps? Bike computers (Garmin, Wahoo) record time
as a matter of course; untimed GPX typically comes from *route-planning* exports — out-of-character
input for a tool whose own help text says "a diary, not a planner" (`trips/forms.py:35`). If real
tracks are reliably timed, the degrade above is sufficient and the edit capability stays parked
indefinitely. If untimed files are common, the reordering Non-Goal needs revisiting sooner than
a later milestone. Owner: user. Block: no.
