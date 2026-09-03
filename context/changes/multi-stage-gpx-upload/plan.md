# Multi-stage GPX upload Implementation Plan

## Overview

Let a rider upload a second (and further) GPX file to an existing trip as an additional
**stage**, rather than replacing the one already there. On the trip detail page all stages
render as one route: chronologically ordered by GPS instants, each stage drawn in its own
colour, with distinct markers for the trip's start, its end, and each inter-stage boundary
("stage break"). Each stage carries its own filename, statistics and download link. A
single-stage v1 trip renders exactly as it does today.

This is roadmap slice S-01, the M-02 north star, and the riskiest change in the milestone:
the file-lifecycle receivers are correct as written, which is precisely why a leftover
`DELETE` in the upload path would convert into permanent loss of every earlier stage's file.

## Current State Analysis

**Replace semantics lives in two lines, not in a signal.** `GpxUploadView.form_valid`
(`gpx/views.py:107-122`) opens a transaction, reads *every* existing track on the trip
(`:116`), lets `CreateView` insert the new one (`:120`), then deletes the pk set it captured
(`:121`). The `pre_save` receiver named as the risk in `change.md:14` and `roadmap.md:74`
returns on `instance.pk is None` (`gpx/signals.py:160-164`) — every upload is an INSERT, so
it has never once fired on this path and is not trip-aware at all. The `post_delete`
receiver (`gpx/signals.py:80-113`) is row-scoped and correct, and stays correct under ADD.
**The hazard is the inverse of the one written down**: the signals need no edit, but leaving
`:121` in place under ADD makes the first second-stage upload destroy every prior stage's
row and its file.

**The schema is already ADD-ready.** `GpxTrack.trip` is a plain FK with `related_name="tracks"`
and no uniqueness constraint anywhere (`gpx/models.py:28`; confirmed against
`gpx/migrations/0001_initial.py`). `gpx_upload_path` mints a random 16-byte key per file
(`gpx/models.py:8-17`), so N stages per trip need no key-scheme change.

**Chronological ordering has no data source.** `gpx/parsing.py:117` reads
`gpx.get_time_bounds().start_time` purely as a presence probe for `duration_seconds` and then
discards it; `point.time` never enters the points comprehension (`:269-277`); the stored
`points` blob is `[[lat, lon], ...]` and carries no temporal signal. `duration_seconds` is a
*relative* span (the sum of each segment's own first-to-last), not a timestamp pair. Ordering
therefore needs new columns captured at parse time — the blob cannot supply it, and
re-parsing at render is rejected twice on record (`.../trip-distance-duration-stats/plan.md:128,155-156`)
and contradicted by the model docstring's "rendering can never fail on a parse".

**The render path is single-track from end to end.** `build_map_config(track)` returns a
*flat* point list plus one bounds pair and one `icons` blob (`gpx/map_config.py:22-54`);
`map.js` draws exactly one `L.polyline` (`:76`) and exactly two hardcoded `L.marker` calls
(`:90-91`) sharing one `L.icon`. Both call sites — `trips/views.py:96` and `gpx/views.py:78`
— resolve `.tracks.first()`, which under `Meta.ordering = ["-uploaded_at", "-id"]`
(`gpx/models.py:59-60`) is the *newest* track. Both docstrings warn the two paths must never
drift, so they change together.

**The statistics panel is forced by this change, not deferrable.** `trips/views.py:99` hands
`build_trip_stats` that same newest track, so shipping ADD semantics untouched would print
stage 3's distance under a heading that reads as the trip's — a wrong number of the same
family as the undifferentiated polyline `prd.md:71` already fixed.

**The two canonical fixtures are untimed.** `valid-track.gpx` and `second-track.gpx` carry no
`<time>`; only `timed-track.gpx` and `two-segment-track.gpx` do. Without a *second* timed
fixture the ordering feature would never be exercised by any test — only its fallback would
— which is `lessons.md` #1 and #3 in their exact shape.

**Verified against the installed gpxpy 1.6.2** (probe run in this repo's venv):
`get_time_bounds()` returns `TimeBounds(start_time, end_time)`; a `Z`-suffixed file yields
aware datetimes carrying gpxpy's own `SimpleTZ('Z')`; an untimed file yields
`TimeBounds(None, None)`; a file with offset-less timestamps yields **naive** datetimes,
which under `USE_TZ=True` (`velo_log/settings.py:135`) would raise a `RuntimeWarning` and be
silently interpreted against UTC.

**E-10 is already closed** (`roadmap.md:155,240`, commit `4c48d9e`) as *unnecessary, not
delivered*: the trip's span is derivable from stage instants, so storing a start/end pair
would be denormalisation whose only novel behaviour is drift. What remains of it here is the
derived span and the `trips/forms.py:35` help-text wording.

## Desired End State

A rider opens a trip that already has one stage, uploads a second GPX file, and the page
shows both stages merged into one route on the interactive map: each stage in its own
colour, a marker at the trip's start, one at its end, and one at the boundary between the
two. Below the map a **Stages** list gives each stage, in chronological order, a colour
swatch matching its segment, its filename, its own distance / recorded time / elevation
figures, and its own download link. Both files remain in storage and both remain
downloadable. A trip with exactly one stage renders a one-row list and one segment — the
same information v1 showed.

**How to verify:** upload two timed GPX files to one trip in the *reverse* of their ride
order; the map draws two differently-coloured segments, the stage list orders them by ride
time rather than upload time, and both download links serve their original bytes.

### Key Discoveries:

- `gpx/signals.py:160-164` — the `pre_save` guard that makes the named risk a non-event, and
  `gpx/signals.py:80-113` — the `post_delete` receiver whose correctness is what makes a
  leftover delete catastrophic rather than merely wrong.
- `gpx/views.py:116,121` — the entire replace mechanism, hardened by a prior TOCTOU review
  finding (`.../upload-gpx-and-view-map/reviews/impl-review-phase-4.md:98-114`), so it is
  reopened deliberately.
- `gpx/parsing.py:116-118` — the absolute instants are live on the in-memory object at this
  exact line and thrown away one line later.
- `F("started_at").asc(nulls_last=True)` is valid inside `order_by()` on Django 6.0, and one
  expression covers all-timed, none-timed and mixed without branching.
- `gpx/constants.py:16-22` — `MAX_GPX_POINTS = 100_000` is documented as "provisional …
  not yet calibrated against a real multi-day tour export". This change is what produces
  that measurement.
- `tests/test_trip_detail_map.py:29` — `MAP_CONTAINER` pins the `#map` markup by regex, so
  new map UI must be injected by `map.js` at runtime, never by editing the template.
- `context/foundation/test-plan.md:323` — map testing is scoped to *the configuration the
  server hands the page*; do not diff the rendered canvas.

## What We're NOT Doing

- **No stage removal.** No per-stage delete route, so `OBJECT_SCOPED_ROUTES` in
  `tests/test_ownership_matrix.py` gains no row. If scope ever grows to include one, it
  needs a row plus a probe or `tests/test_ownership_matrix.py:321-337` turns the suite red.
- **No whole-trip statistics aggregation.** Stays S-03. Nothing here computes a trip total,
  so the NULL-skipping fabrication trap (`Sum()` silently omitting a stage with no `<ele>`)
  never arises.
- **No manual stage reordering, and no `order`/`position` column.** Named Non-Goal
  (`prd.md:106`); a stored order would be a second source of truth needing a reconciliation
  rule on every later upload.
- **No rider-supplied stage timestamps.** Parked (`roadmap.md:127`) pending real Garmin/phone
  exports. The nullable columns this change adds are the whole schema requirement, so it
  needs only a form later.
- **No accommodation waypoint entity** (`prd.md:105`), **no elevation chart**, **no
  coordinate thinning or per-trip render budget** (decided on evidence instead — see Phase 3
  manual verification).
- **No `Trip` migration.** `Trip.date` keeps its shape; the span is derived.
- **No re-parsing at render**, ever. Columns are filled at the parse boundary.

## Implementation Approach

Capture the instants first, in a phase that changes no behaviour, so the schema and the
parse are settled before the dangerous edit. Flip replace→add second, on its own, with a
mutation shape proving a guard test bites when the delete comes back. Then widen the read
path — server payload and client rendering together, since the payload shape is the test
boundary and the drawing is only verifiable by eye. Then the stage list, which is where the
per-stage statistics decision lands.

Then the custom pins, which are **not** cuttable: the "distinct markers" clause is a PRD
must-have (`prd.md:96-97,127`) that Phase 3's shared pin satisfies only on hover, so Phases
1-5 are the shippable core. Phase 3 deliberately emits marker *kinds* through a keyed
`icons` map so Phase 5 is a two-URL swap rather than a rewrite, which is what makes it cheap
enough to sit inside the core rather than in the tail.

Only the last two phases are nominated as cuttable, ordered most-valuable-first: backfill,
then the derived span. Each is self-contained and leaves the codebase shippable if the week
runs out.

## Critical Implementation Details

**Timezone normalisation at the parse boundary.** gpxpy hands back naive datetimes for a file
whose timestamps carry no offset. Storing one into a `DateTimeField` under `USE_TZ=True`
raises a `RuntimeWarning` and interprets it against UTC — a silently wrong instant, which is
worse than none. Treat a naive value as *no usable timestamp* (both columns null) and
normalise an aware one to `datetime.timezone.utc`, so gpxpy's own `SimpleTZ` never reaches
the database. Both columns move together: a file yielding one instant but not the other is
treated as having neither, so no consumer has to handle a half-timed stage.

**Ordering-key nullability has no precedent in this repo.** Both existing `Meta.ordering`
tuples pair a non-null business field with `-id`. Do not `COALESCE(started_at, uploaded_at)`
into a single sort key: it produces a total order but compares a *ride* instant against an
*upload* instant, so an untimed stage uploaded in January sorts ahead of a timed stage ridden
in June. Deterministic and meaningless. The three-term `order_by` handles every case without
branching.

**One predicate, three consumers.** `chronology_is_established` (every stage has a
`started_at`) gates all three claims that depend on established ride order: the page may not
use the word "chronological", stage-break markers must not be drawn (a break asserts *the
rider stopped here and resumed there*, which upload order cannot evidence), and the derived
trip span must not be shown (`Min`/`Max` skip NULLs, so a span over the timed subset is a
lower bound presented as the span). This is the discipline `build_trip_stats` already
follows by returning `None` rather than zeros — degrade the *claim*, not the render.

**Fixture ordering must contradict upload order.** A test that uploads the earlier-ridden
file first proves nothing that `uploaded_at` ordering would not also satisfy. The ordering
test must upload the *later* file first.

---

## Phase 1: Stage instants captured at parse

### Overview

Add `started_at` / `ended_at` to the parse result and to `GpxTrack`, filled on every new
upload. No behaviour changes: replace semantics, rendering and the detail page are all
untouched. This phase exists so the schema and the timezone rule are settled before the
dangerous edit lands.

### Changes Required:

#### 1. Parse boundary

**File**: `gpx/parsing.py`

**Intent**: Capture the absolute instants that `track_statistics` already reads and throws
away, normalising them so a naive or half-present pair degrades to "not recorded" rather
than to a silently wrong stored value.

**Contract**: `TrackStatistics` gains `started_at: datetime | None` and
`ended_at: datetime | None`; `ParsedTrack` gains the same two fields with docstrings stating
the both-or-neither rule and the naive-is-absent rule. The values come from the
`gpx.get_time_bounds()` call already made at `:117` — read both members rather than only
probing `start_time`. Normalisation:

```python
# gpxpy yields `SimpleTZ('Z')`-aware datetimes for Z-suffixed files and *naive* ones for
# offset-less timestamps. A naive value saved under USE_TZ=True warns and is read as UTC —
# a wrong instant, worse than none — so it is treated as absent, together with its partner.
if start is None or end is None or start.tzinfo is None or end.tzinfo is None:
    started_at = ended_at = None
else:
    started_at, ended_at = start.astimezone(UTC), end.astimezone(UTC)
```

`duration_seconds`' existing presence probe is unchanged — it answers a different question
(usable per-segment spans) and must not be re-derived from these two.

#### 2. Model columns

**File**: `gpx/models.py`

**Intent**: Store the pair as plain nullable columns, following the scalar-columns precedent
the four statistics set.

**Contract**: `started_at` and `ended_at` as `DateTimeField(null=True, blank=True)` with
help text naming them as the first and last recorded GPS instants. `blank=True` is
load-bearing for the same reason the statistics columns document: `GpxTrackAdmin` excludes
only `points`, so without it these render as required on the admin change form and break the
documented admin repair path. `Meta.ordering` stays `["-uploaded_at", "-id"]` — flipping it
would silently invert every remaining `.tracks.first()`; ordering is applied at the query
site instead.

#### 3. Schema migration

**File**: `gpx/migrations/0004_gpxtrack_stage_instants.py`

**Intent**: Additive-first, schema only — the data write is a separate migration in Phase 6,
so the two are independently reversible, exactly as `0002`/`0003` are.

**Contract**: `AddField` ×2, both nullable. Generated with `makemigrations gpx` and committed
by hand; `makemigrations --check --dry-run` is the gate (`lessons.md` #9).

#### 4. Upload form

**File**: `gpx/forms.py`

**Intent**: Copy the two new values onto the unsaved instance alongside the ten fields
`clean_file` already sets, so a fresh upload and a backfilled row cannot disagree.

**Contract**: Two assignments after `self.instance.elevation_loss_meters`.

#### 5. Fixtures

**File**: `tests/gpx/fixtures/timed-track-day-2.gpx` (new)

**Intent**: Without a *second* timed fixture the ordering feature ships unexercised — the
repo's two canonical valid fixtures carry no `<time>`, so every existing multi-upload test
would only ever exercise the fallback.

**Contract**: A well-formed GPX 1.1 track, distinct coordinates from `timed-track.gpx`, with
`<time>` values on **2026-06-02** — strictly later than `timed-track.gpx`'s 2026-06-01 — so a
test can upload it *first* and prove ride order beats upload order.

### Success Criteria:

#### Automated Verification:

- Migration guard clean: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies: `uv run python manage.py migrate`
- A timed upload stores both instants as UTC-aware values matching the file's first and last `<time>`
- An untimed upload (`valid-track.gpx`) stores null for both, and still stores its distance
- A file with naive (offset-less) timestamps stores null for both rather than a naive instant
- A multi-segment timed file (`two-segment-track.gpx`) spans first segment start to last segment end
- No `RuntimeWarning` about naive datetimes is emitted anywhere in the suite
- Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- Upload a real timed export from the owner's device; the admin change form shows both instants and both are editable

---

## Phase 2: ADD semantics and chronological ordering

### Overview

The dangerous phase. Stop deleting the trip's existing tracks on upload, introduce the
ordering expression and the chronology predicate, and prove with a mutation shape that a
guard test goes red if the delete ever comes back. Rendering still shows one stage — the
chronologically first one — so the phase is committable on its own.

### Changes Required:

#### 1. The upload path

**File**: `gpx/views.py`

**Intent**: A new stage accumulates rather than superseding. The transaction block, the
`select_for_update` read and the explicit-pk delete all go; what remains is the insert.

**Contract**: `form_valid` sets `form.instance.trip` and delegates to `super()`. The class
docstring, the `form_valid` docstring and `success_message` ("Route uploaded." → "Stage
added.") all change with it — the existing docstrings assert replace semantics as a
guarantee, so leaving them is `lessons.md` #11 in its exact shape. Keep a short note in the
docstring recording *why* the delete is gone and that `post_delete` remains the only path
that removes a file, so the next reader does not reinstate it as "cleanup".

**The rider-facing replace copy changes here too, not in Phase 4.** `trip_detail.html:159`
and `:174` read `{% if track %}` — two uses that sit *outside* the `:41` gate — and render
"Replace the route" / "Replace GPX file". Both become "Add a stage" / "Add GPX file"
unconditionally in this phase, because this is the phase where the semantics actually flip:
leaving them until Phase 4 would ship one commit whose button promises a replacement the
view no longer performs, which is `lessons.md` #11 aimed at the rider instead of the next
reader. Add `trips/templates/trips/trip_detail.html` to this phase's touched files for those
two strings only — the `:41` gate and everything under it stay untouched until Phase 4.

Note for the implementer: `transaction.atomic()` is no longer needed for a single insert,
but E-11's roadmap row (`roadmap.md:247`) names "the next time `gpx/views.py`'s upload
transaction is touched" as a deliberate-reopening trigger. State in the commit message that
the block was removed because the multi-statement write it guarded no longer exists, and
that the storage-write orphan window it never covered is still covered by `reconcile_media`.

#### 2. Stage ordering and the chronology predicate

**File**: `gpx/stages.py` (new)

**Intent**: One module owning "what are this trip's stages, in what order, and is that order
evidence" — so the two render paths cannot drift, and so the three consumers of the
chronology claim read one concept rather than three flags.

**Contract**:

```python
def ordered_stage_tracks(trip: Trip) -> QuerySet[GpxTrack]:
    # Not COALESCE into one key: that compares a ride instant against an upload instant.
    # Timed stages sort first in ride order; untimed ones follow in upload order.
    return trip.tracks.order_by(F("started_at").asc(nulls_last=True), "uploaded_at", "id")

def chronology_is_established(tracks: Sequence[GpxTrack]) -> bool: ...
```

`chronology_is_established` is `True` only when there is at least one stage and every one has
a non-null `started_at`. A single-stage timed trip is established; a single untimed stage is
not — and correctly so, since nothing about it is a chronology claim either way.

#### 3. Both render paths read the ordered first stage

**Files**: `trips/views.py`, `gpx/views.py`

**Intent**: Keep the page coherent in this intermediate state without pre-building Phase 3.

**Contract**: Both `.tracks.first()` calls become the first element of
`ordered_stage_tracks(trip)`. Context keys are unchanged in this phase.

#### 4. Mutation shape

**File**: `tests/mutations.py`

**Intent**: Risk #1's whole point is a file removed that is still in use. A test asserting
"the first stage survives a second upload" is worthless unless it is proven to go red when
the delete returns.

**Contract**: A `MutationShape` named `upload_replaces_instead_of_adding`, `risk="#1"`,
patching `gpx.views` / `GpxUploadView.form_valid` (a class attribute, so the dotted-attribute
form the `unscoped_trip_detail_queryset` shape already uses) with a replacement that
reinstates the read-then-delete. `replacement` is a zero-argument *factory* returning the
broken `form_valid`, with any Django-model import deferred inside it, per the registry's own
module docstring. `guard_node_id` names the Phase 2 test below, in
`tests/<path>.py::<test name>` posix form; `fragment` is a distinctive string from that
test's assertion message. `tests/test_suite_bites.py` asserts every risk area has a shape
and every guard node resolves, so the registration itself is checked rather than trusted.

**`fragment` must be *proven* to discriminate, not chosen to look distinctive.**
`test-plan.md` §6.8 is explicit that the obvious check is worthless here: "a clean unmutated
pass proves nothing, since a passing run prints no source at all and every fragment is
trivially absent from it", and "a shape whose guard stays green, or goes red for an
unrelated reason, is a broken shape — do not commit it un-verified." So do both halves
before committing:

1. **Positive.** `VELOLOG_MUTATION=upload_replaces_instead_of_adding` on the guard node with
   `-o addopts=`, and confirm it fails with `fragment` present in the `>` / `E ` lines — not
   a collection error, and not some other assertion in the same test.
2. **Negative.** Force the guard to fail for an *unrelated* reason with the mutation off
   (break some unrelated precondition), and confirm `fragment` is **absent** from those
   `>` / `E ` lines. This is the half that catches a fragment matching by way of source
   context or a neighbouring assertion, and it is the only half that proves the shape is
   pinned to the behaviour it names.

This matters more here than for any existing shape: risk #1 is permanent loss of a rider's
file, and an unverified fragment means the harness reports protection it does not have —
which is risk #4 (`test-plan.md` §2) wearing risk #1's clothes.

#### 5. Signal re-verification

**File**: `tests/gpx/test_gpx_signals.py`

**Intent**: The receivers need no edit, but "correct under ADD" is currently an argument, not
an assertion. Pin it.

**Contract**: A test proving `pre_save` returns without touching storage when a second track
is inserted for a trip that already has one, and a test proving `post_delete` removes exactly
the file of the row deleted and no sibling's. Both must wrap the request in
`django_capture_on_commit_callbacks(execute=True)` — without `execute=True` a
removal assertion passes while proving nothing.

#### 6. Existing upload tests

**File**: `tests/gpx/test_gpx_upload.py`

**Intent**: `test_a_second_upload_replaces_the_first_and_removes_its_file` (`:349`) asserts
the behaviour being deliberately removed. It becomes the guard test the mutation shape names.

**Contract**: Rewrite as `test_a_second_upload_adds_a_stage_and_keeps_the_first_file`:
both rows exist, both storage keys still exist, the pks differ, and the assertion message is
distinctive enough to serve as the mutation `fragment`.
`test_a_second_upload_leaves_another_trips_track_alone` (`:427`) keeps its name and its
point — cross-trip isolation still matters — but its expectations change from
one-track-replaced to two-tracks-accumulated.

**Addendum, recorded at implementation review (F7).** A *third* test was deleted during
implementation without a clause here authorising it:
`test_a_cleanup_failure_does_not_fail_an_upload_that_already_committed`. It monkeypatched
`FileSystemStorage.delete` to prove that a deferred delete failing after commit did not 500
an upload that had already succeeded — a guarantee about the delete this phase removes, so
with no delete scheduled on the upload path the test had no subject left. **No coverage was
lost**: the same guarantee for the path that *does* still schedule a delete is asserted by
`tests/gpx/test_gpx_signals.py::test_a_cleanup_failure_does_not_fail_a_replacement_that_already_committed`,
which this change leaves untouched. Recorded rather than reverted, because deleting a test
is exactly the kind of decision that should be visible in the plan instead of discovered by
reading a diff.

**Addendum, added at implementation review (F4).** One test this phase's criteria implied but
that was never written: `test_two_uploads_in_reverse_ride_order_come_back_in_ride_order`,
which uploads `timed-track-day-2.gpx` and *then* `timed-track.gpx` through the real form and
asserts `ordered_stage_tracks` returns day 1 first. Criterion 2.3 was otherwise met only
against hand-set columns, leaving `clean_file` → `started_at` → ordering unjoined and
`tests/gpx/fixtures/timed-track-day-2.gpx` — added by Phase 1 §5 precisely so ride order
could contradict upload order — referenced by nothing. Verified to bite: dropping the
`started_at` term from `ordered_stage_tracks` fails it with "stages came back in upload order
rather than ride order".

### Success Criteria:

#### Automated Verification:

- A second upload leaves the first row **and** its stored file intact, asserted after commit
- A second upload to trip A leaves trip B's tracks untouched
- Two timed stages uploaded in reverse ride order come back in ride order, not upload order
- Two untimed stages come back in upload order (`uploaded_at`, then `id`)
- A mixed pair returns the timed stage first and the untimed one appended
- `chronology_is_established` is true for all-timed, false for any-untimed, false for no stages
- The `pre_save` receiver removes nothing when a sibling stage is inserted
- Deleting one stage removes exactly its own file, leaving the sibling's in place
- The bite-proof harness passes with the new shape: `uv run pytest -m bite_proof -v`
- The new shape's `fragment` is proven to discriminate, per `test-plan.md` §6.8: present in the guard's failure output under the mutation, and **absent** when the guard is broken for an unrelated reason
- Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- Upload two files to one trip; both appear in the admin and both download links serve their own original bytes
- Delete the trip; `MEDIA_ROOT` retains neither file, and `manage.py reconcile_media` reports nothing orphaned

---

## Phase 3: Multi-stage rendering

### Overview

Widen the map payload from one flat point list to per-stage segments with a whole-trip
bounding box and an explicit marker array, and teach `map.js` to draw them. Amend the design
system with the bounded, map-only categorical palette, reconciling the `#ff7800` /
`#f97316` drift `map.js:76` has carried since v1.

### Changes Required:

#### 1. Stage palette

**Files**: `gpx/constants.py`, `context/foundation/design-system.md`

**Intent**: `prd.md:70` requires a different line colour per stage; `design-system.md:491`
forbids additional colours. Resolve it rather than work around it: a named palette scoped
explicitly to route rendering, which the design system already calls the primary visual
element.

**Contract**: `STAGE_COLORS: tuple[str, ...]` in `gpx/constants.py` — 4-6 hues, cycled by
stage index so stage 7 reuses stage 1's colour. First entry is `#f97316`, the design
system's accent, so a single-stage trip is drawn in the colour the system already specifies
(and the `#ff7800` drift ends here). Remaining hues must be distinguishable from each other
*and* legible over the OpenStreetMap basemap.

`design-system.md` gains a **Stage Route Palette** subsection under Route Styling naming the
hues and stating the exception's bounds — map polylines and their stage-list swatches only,
never interface chrome — and the "Do not introduce additional colors" rule gains a pointer to
it. The `weight: 5` / white outline spec is unchanged.

#### 2. Stage view models

**File**: `gpx/stages.py`

**Intent**: One ordered structure carrying everything both the map payload and the template
need per stage, so the two render paths and the two consumers cannot drift.

**Contract**: A frozen `Stage` dataclass — `track`, `number` (1-based position in ride
order), `color` (from `STAGE_COLORS`, cycled), `stats` (the existing
`build_trip_stats(track)` result), `file_available` (the existing
`track_file_is_available(track)` result) — and `build_stages(trip) -> tuple[Stage, ...]`
building them over `ordered_stage_tracks`. `build_trip_stats` and `track_file_is_available`
keep their single-track signatures; they are called once per stage.

#### 3. Map payload

**Files**: `gpx/map_config.py`, `gpx/statistics.py` (docstring only)

**Intent**: Segments and markers as data, so the assertions land on the payload rather than
on Leaflet's drawing (`test-plan.md:323`).

**Two module docstrings currently assert this signature and must move with it.**
`gpx/statistics.py:30-31` claims "`build_trip_stats` mirrors `gpx/map_config.py`'s
`build_map_config` exactly — same `GpxTrack | None` in, same 'or `None` when there is
nothing to show' out". Half of that stops being true here: `build_map_config` takes
`Sequence[Stage]` while `build_trip_stats` deliberately keeps its single-track signature
(§2). Correct it to name only the half that survives — the `None`-when-nothing-to-show
discipline, which is the part the template actually depends on — and drop the input-type
claim rather than deleting the paragraph, since the discipline is still the reason both
helpers live outside the views. Re-read `gpx/availability.py:1-8` at the same time: its
"exact drift `build_map_config` and `build_trip_stats` already exist to prevent" sentence is
about drift, not signatures, so it should survive unedited — confirm that rather than
assume it. `lessons.md` #11: a docstring is a claim the body must honour, and a stale one
misdirects the next reader instead of merely aging.

**Contract**: `build_map_config(stages: Sequence[Stage]) -> dict[str, Any] | None`, returning
`None` when there are no stages or when no stage has points. Shape:

```python
{
  "segments": [{"number": 1, "color": "#f97316", "points": [[lat, lon], ...]}, ...],
  "bounds": [[min_lat, min_lon], [max_lat, max_lon]],   # min of mins / max of maxes
  "markers": [{"kind": "start"|"finish"|"break", "point": [lat, lon], "title": "..."}],
  "icons": {"start": {...}, "finish": {...}, "break": {...}},
}
```

Bounds aggregate the four stored non-null scalar columns across stages — no
`polyline.getBounds()`, keeping the degenerate-bounds decision server-side. Markers: one
`start` at the first stage's first point, one `finish` at the last stage's last point, and
one `break` at the **end point of each stage but the last**. Break markers are emitted only
when `chronology_is_established` — an upload-ordered boundary has no real-world referent.
A stage carrying no points is skipped for segments and markers but must not crash the build.

`icons` becomes a mapping keyed by marker kind. In this phase all three values are the same
existing Leaflet pin blob, which is what makes Phase 5 a two-URL swap rather than a rewrite.

#### 4. Both views

**Files**: `trips/views.py`, `gpx/views.py`

**Intent**: One context contract across both render paths, which is what their docstrings
already demand.

**Contract**: Both set `context["stages"] = build_stages(trip)` and
`context["map_config"] = build_map_config(stages)`, plus
`context["chronology_established"]`. Both docstrings update to say so.

**`track`, `stats` and `track_file_available` are *not* retired here** — they survive this
phase as a deliberate interim shim, each resolved from `stages[0]` (equivalently, the first
element of `ordered_stage_tracks(trip)`, which Phase 2 already computes at both call sites)
and each carrying a comment naming Phase 4 §1 as its removal point. Retiring them in this
phase would break the page and this phase's own criteria, because the template does not
change until Phase 4:

- `trip_detail.html:41`'s `{% if track %}` gate wraps **both** the Route block (`:42-92`)
  and the Stats block (`:103-149`), and `{% if map_config %}` (`:44`) is *nested inside* it.
  With `track` falsy the whole page falls to the `{% else %}` empty state at `:150`, so
  `#map` and the `json_script` element are never rendered — which makes criterion 3.9
  ("`#map`'s markup is byte-identical to today") unsatisfiable and reddens
  `tests/trips/test_trip_detail_map.py:60`.
- Three test files read the keys and are not otherwise touched here:
  `tests/trips/test_trip_detail.py:109,134` and `tests/gpx/test_gpx_upload.py:343`.

The shim's only honest reading is "the chronologically first stage", not "the trip's
track" — which is exactly why it is temporary and why the comment is load-bearing rather
than decorative. Phase 4 §1 deletes all three in the same edit that stops reading them.

#### 5. Client rendering

**File**: `gpx/static/gpx/map.js`

**Intent**: Draw N segments and N+1 markers from data, instead of one polyline and two
literal `L.marker` calls.

**Contract**: Loop `config.segments` into one `L.polyline` each, `color` taken from the
segment (never hardcoded), `weight`/`opacity` unchanged. Build one `L.icon` per key in
`config.icons` and loop `config.markers`, selecting by `kind`. `fitBounds`, the scroll-zoom
hint control, the fallback-removal ordering and the single all-or-nothing `try/catch` are all
unchanged. Nothing may be added to the `#map` container from the template — the byte-exact
markup pin (`tests/trips/test_trip_detail_map.py:29`) stands.

#### 6. Map tests

**File**: `tests/trips/test_trip_detail_map.py`

**Intent**: The payload shape changed, so the assertions that pinned the flat shape must
re-pin the new one, not merely be relaxed.

**Contract**: `test_the_marker_icon_urls_come_from_the_staticfiles_storage` moves to the
keyed `icons` map and keeps its `STATIC_URL`-moving technique — that is what catches a
literal path written into `map_config.py`. The coordinate test asserts `segments`. New tests
cover segment count and per-stage colour, whole-trip bounds across stages, the marker array's
kinds and positions, and break-marker suppression when chronology is not established.

#### 7. Repoint the risk-#3 mutation shape

**File**: `tests/mutations.py`

**Intent**: `file_always_available` (`:130-146`) is the **only** shape covering risk #3, and
§2 moves the name it patches out from under it. Left alone, `pytest -m bite_proof` fails and
CI's `Suite credibility` step goes red — for a reason that has nothing to do with what
broke.

**Contract**: The shape names `module_path="trips.views"` / `attribute="track_file_is_available"`,
and its comment states why: "`trips/views.py` does `from gpx.availability import
track_file_is_available`, so the view's live reference is
`trips.views.track_file_is_available` — patching `gpx.availability.track_file_is_available`
would leave the view untouched." Once `build_stages` owns that call, `trips.views` no longer
reads the name and the patch target ceases to exist. Repoint `module_path` at the module
that now reads it — `gpx.stages` — and **rewrite the comment to match**, since it explains a
re-export trap whose location has moved; a stale comment here is worse than none
(`lessons.md` #11).

`fragment` needs no edit *in this phase*: Phase 3 §4's shim keeps
`context["track_file_available"]` alive, so the guard's assertion is unchanged. It moves in
Phase 4 §3, with the assertion it quotes. Verify the repointed shape per `test-plan.md` §6.8
before committing — a shape whose guard stays green is a broken shape.

### Success Criteria:

#### Automated Verification:

- A single-stage trip's payload carries one segment whose points equal the stored points
- A three-stage trip carries three segments in ride order, each with a distinct colour
- Whole-trip bounds equal the min/max across all stages, not any one stage's
- Markers are exactly one `start`, one `finish`, and one `break` per inter-stage boundary
- No `break` markers are emitted when any stage lacks `started_at`
- A stage with no points is skipped without raising, and the remaining stages still draw
- The payload is still delivered by `json_script` only — the "no inline script" test still passes
- Marker icon URLs still resolve through staticfiles storage when `STATIC_URL` moves
- `#map`'s markup is byte-identical to today, fallback paragraph included
- Static references resolve: `uv run python manage.py collectstatic --noinput` then `uv run pytest tests/test_static_references.py`
- The bite-proof harness still passes with the repointed risk-#3 shape: `uv run pytest -m bite_proof -v`
- Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- A three-stage trip draws three visibly distinct coloured segments in ride order, with markers at start, end and both breaks
- Each hue is legible against the OpenStreetMap basemap at both a zoomed-out tour extent and street-level zoom
- A single-stage v1 trip looks the same as before the change
- **Measurement step (feeds the payload decision):** upload a real multi-day tour export, then record the rendered page's transferred size and time-to-interactive on home broadband. Compare against `MAX_GPX_POINTS`' "provisional" note in `gpx/constants.py:16-22`. If the page is unacceptable, open an Engineering Backlog row with that number as the trigger — do not build thinning on a guess.

---

## Phase 4: Stage list and per-stage statistics

### Overview

Replace the single "Track: <filename>" line and its lone download button with a **Stages**
section: one row per stage in ride order, carrying the colour swatch that makes the map's
palette mean something, the filename, that stage's own statistics, and its own download link.
This is also where the forced statistics correctness fix lands — without it a multi-stage
trip would print the newest stage's distance as the trip's.

### Changes Required:

#### 1. Detail template, and retiring Phase 3's shim

**Files**: `trips/templates/trips/trip_detail.html`, `trips/views.py`, `gpx/views.py`

**Intent**: One structure ties colour, filename, figures and download together, so a rider
can answer "how long was the orange stage" without counting positions across three lists.

**Contract**: This is where Phase 3 §4's interim shim dies. The three legacy context keys —
`track`, `stats`, `track_file_available` — are deleted from **both** views in the same edit
that stops the template reading them, never earlier: the template's gate is what keeps them
alive, so removing either half alone breaks the page (see Phase 3 §4). Both view docstrings
drop the shim note.

The `{% if track %}` gate becomes `{% if stages %}`. The Route section keeps
`#map`, its fallback paragraph and the `json_script` element **byte-identical**. Below it, a
Stages section loops `stages`, each row rendering: an inline colour swatch (a small span
whose background is `stage.color`, the palette's only non-map use), `Stage {{ stage.number }}`,
`stage.track.original_filename`, the four `dt`/`dd` statistics pairs moved verbatim from
today's Stats block — including every `is not None` gate and every "Not recorded — …"
sentence, which must not be reworded — and either the download link or today's
file-unavailable text, per `stage.file_available`. The `stats`-is-`None` branch ("These stats
have not been worked out for this route.") is preserved per stage.

The list is labelled as chronological **only when `chronology_established`**; otherwise it
carries a short line saying the stages are shown in upload order because the files carry no
ride timestamps. The upload card's heading and button already read "Add a stage" / "Add GPX
file" unconditionally — Phase 2 changed those two strings when the semantics flipped, so
there is no replace branch left here to switch on.

A single-stage trip renders one row, so a v1 trip's information is unchanged even though its
layout is.

#### 2. Delete-confirmation copy

**Files**: `trips/templates/trips/trip_confirm_delete.html`, `tests/trips/test_trip_delete.py`

**Intent**: `:19-20` warns "Its GPX file will be deleted too." — singular, and after this
change one sentence stands in for five files. The template's own comment says why it exists
at all: "a name and a date can be retyped, an uploaded GPX file cannot." Under-counting what
is about to be destroyed is the one place that reasoning fails outright. This is the only gap
this change opens against the PRD guardrail that existing trips' delete flow is unchanged
(`prd.md:112-113`) — the *behaviour* is unchanged; the copy stops being true.

**Contract**: Pluralise against the stage count, keeping the `{% if trip.tracks.exists %}`
branch and the "one idiom, not two" template-branching decision its comment records. Update
`GPX_WARNING` in `tests/trips/test_trip_delete.py` in step — it pins the exact string, and
`test_confirmation_page_for_a_trackless_trip_omits_the_gpx_warning` (`:45-61`) is, by its own
docstring, "the only automated check on the `{% if trip.tracks.exists %}` branch", so it must
keep discriminating both ways. Add a case proving a multi-stage trip's warning names more
than one file.

#### 3. Stats and detail tests

**Files**: `tests/trips/test_trip_detail_stats.py`, `tests/trips/test_trip_detail.py`,
`tests/gpx/test_gpx_upload.py`, `tests/mutations.py`

**Intent**: These pin a single unlabelled stats block; the block is now per stage.

**Contract**: Existing single-track assertions keep their meaning against a one-stage trip.
New coverage: a three-stage trip renders three stats blocks whose figures differ per stage
and are not the newest stage's repeated; each stage's download link points at its own pk; a
stage whose file is missing renders the unavailable text while its siblings keep live links;
and the chronological/upload-order wording follows the predicate. Every new request-cycle
test must assert past its status code or `tests/test_assertion_strength.py` fails the suite.

The three assertions on the retired keys move to their per-stage equivalents in this phase,
together with the shim they read: `tests/trips/test_trip_detail.py:109,134` (both branches
of file availability — the pair its own docstring insists on keeping separate) and
`tests/gpx/test_gpx_upload.py:343`, whose point is that the *rejected-upload* re-render
supplies the same context as a normal visit and so must move in step with it.

`file_always_available`'s `fragment` moves with them. It currently quotes the assertion
verbatim — `'assert response.context["track_file_available"] is False'` — so retiring that
key strands it, and `tests/test_suite_bites.py` asserts the guard fails *for the named
reason*, not merely that it fails. Requote it from the rewritten per-stage assertion in
`tests/trips/test_trip_detail.py`, and re-verify per `test-plan.md` §6.8: force the guard to
fail for an unrelated reason and confirm the new fragment stays absent from the `>` / `E `
lines. (Phase 3 §7 already repointed this shape's `module_path`; this is the other half.)

#### 4. Roadmap and agent-doc sync

**Files**: `context/foundation/roadmap.md`, `AGENTS.md`

**Intent**: `lessons.md` #5 — update the docs in the same slice that invalidates them.

**Contract**: S-03's row and body are re-worded: per-stage display is delivered here, so
S-03 narrows to whole-trip aggregation plus its partial-data presentation rule, and stays
cuttable. `AGENTS.md`'s `gpx/` bullet drops the replace-on-upload description, names
`gpx/stages.py` and the two new columns, and states that `Meta.ordering` is descending while
stage order is applied at the query site.

### Success Criteria:

#### Automated Verification:

- A three-stage trip renders three stats blocks with each stage's own figures
- Each stage row links to its own `gpx:download` pk
- A stage with a missing file renders the unavailable text while siblings keep live links
- A stage whose statistics are all null renders the "not worked out" sentence, not four blanks
- A single-stage trip renders exactly one row and the same figures it renders today
- The list claims chronological order only when every stage has `started_at`
- The delete confirmation names more than one file for a multi-stage trip, one for a single-stage trip, and none for a trackless one
- `#map`'s markup and the `json_script` element are unchanged
- The assertion-strength audit passes with no new waivers: `uv run pytest tests/test_assertion_strength.py`
- The bite-proof harness still passes with the requoted risk-#3 fragment: `uv run pytest -m bite_proof -v`
- Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- Each swatch colour matches its segment on the map
- The page reads sensibly on a phone-width viewport for a 5-stage trip
- Uploading a stage to a trip that already has one returns to the detail page with "Stage added." and the new row in the right position

---

## Phase 5: Distinct stage markers

### Overview

Replace Phase 3's shared Leaflet pin with three project-authored SVG pins, so trip start,
trip end and stage break are distinguishable without hovering — which is what the Primary
Success Criterion's "distinct markers" clause asks for and a tooltip cannot deliver on a
phone.

**Not cuttable, and sequenced ahead of the backfill deliberately.** `prd.md:96-97` makes
"the three kinds are distinguishable at a glance, **without hovering**, on desktop and at
phone width" an acceptance criterion, and `prd.md:127` lists distinct start/end/stage-break
markers as **must-have**. Phase 3 satisfies the *marker* clause but not the *distinct*
clause — all three kinds share one pin and separate only on hover, which a phone has no
gesture for. Leaving this cuttable would let every earlier phase go green with the Primary
Success Criterion unmet. It is also the cheapest of the three tail phases: three text
assets, three constants, three `STATIC_REFERENCES` entries and no `map.js` change, because
Phase 3's keyed `icons` map already reduced it to a URL swap.

### Changes Required:

#### 1. Pin assets

**Files**: `gpx/static/gpx/markers/stage-start.svg`, `stage-finish.svg`, `stage-break.svg` (new)

**Intent**: Project-authored rather than vendored: no third-party licence to clear, no
`SHA256SUMS` entry or CI step (the integrity gate exists for bytes we did not author), and
the hues stay in step with `STAGE_COLORS` automatically. They are text, so a diff reviews
them.

**Contract**: Each SVG uses Leaflet's pin geometry — a 25×41 viewBox with the point at the
bottom centre — so the existing `iconSize: [25, 41]` / `iconAnchor: [12, 41]` /
`popupAnchor: [1, -34]` values stay correct and no anchor maths changes. Start and finish are
full pins in distinct fills; break is visually subordinate (smaller or hollow), matching the
semantic that a tour has one start and one end but many breaks. One SVG serves both pixel
densities, so `iconRetinaUrl` points at the same file; the vendored PNG shadow is retained
for all three.

#### 2. Payload and references

**Files**: `gpx/constants.py`, `gpx/map_config.py`, `tests/test_static_references.py`

**Intent**: Keep every URL server-resolved through the staticfiles manifest — the whole
reason `icons` is built server-side.

**Contract**: Three new path constants beside `MARKER_ICON`; the `icons` map's three keys
now resolve to their own `static()` URLs. The three paths join the `STATIC_REFERENCES` tuple,
which is checked against `finders.find()` and, under the production manifest backend, against
a rendered page. `map.js` needs no change — it already selects by `kind`.

### Success Criteria:

#### Automated Verification:

- The payload's three `icons` keys resolve to three *different* URLs, each following `STATIC_URL`
- All three SVGs resolve through `finders.find()` and survive `collectstatic --noinput`
- `uv run pytest tests/test_static_references.py` passes under the production manifest backend
- Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- Start, finish and break markers are distinguishable at a glance, without hovering, on desktop and on a phone-width viewport
- Each pin's tip sits exactly on its coordinate — no vertical offset from a wrong anchor
- All three render correctly under the hashed manifest after `collectstatic`

---

## Phase 6: Backfill stage instants for existing rows *(cuttable)*

### Overview

Fill `started_at` / `ended_at` on rows that predate the columns, by re-parsing the bytes still
in storage. Without this, US-02's own scenario — a trip that *already* has a stage, gaining a
second — can never establish chronology, because the pre-existing stage has no instant.

### Changes Required:

#### 1. Backfill helper

**File**: `gpx/statistics.py`

**Intent**: The re-parse-from-storage path already exists and is unit-tested; extend it
rather than adding a second one, so a backfilled row and a freshly uploaded one cannot
disagree about the same file.

**Contract**: `backfill_track_statistics` also writes the two instants, and `STATS_FIELDS`
grows to include them — the tuple is what keeps the helper's `update_fields` and both
callers' `.only(...)` narrowing from drifting apart. It is deliberately *not* what the
null-row filters are derived from: those are chosen per caller and for different reasons
(§2, §3), and a filter mechanically derived from this tuple is exactly the trap §3 rejects.
The broad `except Exception` with
its `logger.exception` and `False` return is unchanged; so is the `update_fields` discipline
that keeps `points` and the bounds untouched. The module docstring notes it is now pinned by
migration `0005` as well as `0003`.

#### 2. Data migration

**File**: `gpx/migrations/0005_backfill_gpxtrack_stage_instants.py`

**Intent**: Data-only and separate from `0004`, per the additive-first rule the `0002`/`0003`
pair established.

**Contract**: `RunPython` importing `backfill_track_statistics` **inside** the function body
under a broad `except Exception`, so a rename degrades to one logged skip rather than
breaking the unattended `migrate` that runs at container boot. Filter
`started_at__isnull=True`, resolve the model with `apps.get_model("gpx", "GpxTrack")`, bind
the queryset with `.using(schema_editor.connection.alias)`, narrow it with
`.only("id", "file", *STATS_FIELDS)` and walk it with `.iterator()` so the `points` blob
stays off the query and out of memory, and wrap each row in its own `transaction.atomic()`
savepoint. Reverse is `RunPython.noop`. All six elements are `0003`'s, not a subset of them
— read `gpx/migrations/0003_backfill_gpxtrack_stats.py` and mirror it rather than working
from this paragraph.

The savepoint is the one whose reason must be reproduced, not restated: without it a single
row's failure calls `mark_for_rollback_on_error` on the outer transaction, and `migrate`
prints `OK` having written nothing — the exact shape `0003:56-64` documents.

**`started_at__isnull=True` is a correct filter here and a wrong one for §3.** It is sound
for a migration, which runs exactly once: the worst case is that every untimed row is
re-parsed one time for nothing. It is *not* a convergence predicate, because the
both-or-neither rule (see Critical Implementation Details) makes null permanent for an
untimed file — unlike `distance_meters`, which `0003:44-46` chose precisely because it is
the only statistic never legitimately null. There is no instant column with that property,
so do not carry this filter into the command.

#### 3. Management command

**File**: `gpx/management/commands/backfill_gpx_stats.py`

**Intent**: The documented recovery path when a migration ran against a misconfigured
`MEDIA_ROOT` and filled nothing — a migration cannot be re-applied once recorded.

**Contract**: **The default filter does not change** — it stays `distance_meters__isnull=True`,
and `--all` remains the way to refill instants. Per-row failures stay a tally, not a crash.

Widening the default to "missing *either* statistics or instants" is the obvious move and is
wrong: `started_at` is legitimately null forever for an untimed file, so every such row would
be permanently pending, re-parsed on every invocation, and the tally would never reach zero.
That destroys the command's only signal for *nothing left to do* — on the one path documented
for recovering a `0005` that ran against a misconfigured `MEDIA_ROOT`. A recovery step that
reports work and converges on nothing is what E-05's restore drill actually found
(`roadmap.md` E-05: "three documented steps that reported success and recovered nothing"), so
it is a shape this repo has already been burned by, not a hypothetical.

`--all` covers the real recovery need at zero cost here: production measured 4 rows
(`roadmap.md` E-11), so "reprocess everything" and "reprocess the ones that need it" are the
same command in practice, and only one of them can tell the operator when it is done.

`AGENTS.md`'s Development Commands row updates to say instants are refilled too, and that
`--all` is the invocation that refills them on a row whose statistics are already present.

### Success Criteria:

#### Automated Verification:

- The helper fills both instants from a stored timed file and leaves them null for an untimed one
- The helper still writes nothing but `STATS_FIELDS` — `points` and the four bounds are unchanged after a run
- The helper returns `False` and logs, without raising, when the stored file is missing or no longer parses
- `manage.py backfill_gpx_stats` fills instants under `--all`, and its default run selects only rows missing statistics — an untimed row is *not* selected twice in a row, so the pending count converges
- Migration guard clean, and `migrate` runs forward and backward on a database seeded with a pre-`0004` row
- Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- Against a copy of production data, `backfill_gpx_stats --all` fills instants for existing rows and the tally matches the row count
- An existing v1 trip, after backfill, correctly orders a newly uploaded earlier-ridden stage ahead of it

---

## Phase 7: Derived trip span and date wording *(cuttable)*

### Overview

Close out what remains of E-10: show the tour's real span, derived from stage instants rather
than stored, and reword the `Trip.date` help text that a multi-day tour makes wrong. Gated on
the same chronology predicate everything else uses, so a partially-timed trip shows the stored
start date alone — which is exactly what v1 renders today, so the degraded case needs no new
UI.

### Changes Required:

#### 1. Span derivation

**File**: `gpx/stages.py`

**Intent**: Derive, never store — the reasoning that closed E-10 (`roadmap.md:240`).

**Contract**: `trip_span(stages) -> tuple[datetime, datetime] | None`, returning
`min(started_at) … max(ended_at)` **only** when `chronology_is_established`, and `None`
otherwise. The gate is the whole point: `Min`/`Max` skip NULLs, so a span over a partially
timed trip is a lower bound that would be presented as the span.

#### 2. Detail page

**Files**: `trips/views.py`, `gpx/views.py`, `trips/templates/trips/trip_detail.html`

**Intent**: Show the span when it is evidence; otherwise show what v1 shows.

**Contract**: Both views add `context["trip_span"]`. The template's
`<p class="text-muted mb-1">{{ trip.date }}</p>` renders the span when present and the bare
stored date otherwise. A same-day span renders as a single date rather than as a range
repeating itself.

#### 3. Help text

**Files**: `trips/forms.py`, `tests/trips/test_trip_creation.py`

**Intent**: "The day the ride happened" is wrong for a tour, which does not happen on *a* day.

**Contract**: The `help_texts["date"]` sentence is reworded to name the field as the day the
tour **started**, keeping the diary-not-planner clause. Start, deliberately — not end: the
future-date rule at `trips/forms.py:50` compares against `localdate() + FUTURE_TRIP_DATE_TOLERANCE`,
which is a *start* semantic, so this wording is the one the rule already implements and
`clean_date` needs no change. `labels` stays unused; the auto-derived "Date" is still right.
The substring assertion at `tests/trips/test_trip_creation.py:172-187` updates to the new
sentence, keeping its `id="id_date_helptext"` / `aria-describedby` wiring checks — it asserts
the *rendered page* precisely because a singular `help_text` typo is silently ignored.

#### 4. Roadmap sync

**File**: `context/foundation/roadmap.md`

**Intent**: E-10 is recorded as closed *by derivation*; this is the slice that performs it.

**Contract**: E-10's Status note gains one sentence confirming the derived span shipped in
`multi-stage-gpx-upload`, and S-01's status advances. Nothing about the "closed as
unnecessary" reasoning changes — the row was already correct.

### Success Criteria:

#### Automated Verification:

- A fully timed multi-stage trip shows a span spanning the first stage's start to the last stage's end
- A trip with any untimed stage shows the stored `Trip.date` alone and no span
- A trip with no stages shows the stored `Trip.date`, exactly as today
- A same-day span renders as one date, not as a range repeating itself
- The rendered create/edit form carries the new help-text sentence, with its `aria-describedby` wiring intact
- `clean_date` still rejects a future date and still skips the check when the date is unchanged
- Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- A real multi-day tour's detail page shows a span matching the rider's memory of the trip
- The create and edit forms read correctly with the new sentence

---

## Testing Strategy

### Unit Tests:

- **Parsing** (`tests/gpx/test_gpx_parsing.py`): instants from a timed file, both-null from an
  untimed one, both-null from naive timestamps, span across a multi-segment file. The naive
  case is the one that would otherwise ship a silently wrong instant.
- **Ordering and predicate** (new, `tests/gpx/test_stages.py`): all-timed, none-timed, mixed;
  the predicate's three answers; the span's gate. Ordering tests must upload the later-ridden
  file first — an order that agrees with upload order proves nothing.
- **Map payload** (`tests/trips/test_trip_detail_map.py`): segment count, per-stage colour,
  aggregate bounds, marker kinds and positions, break suppression, the pointless-stage branch.
- **Statistics** (`tests/gpx/test_gpx_statistics.py`): the widened backfill helper still writes
  only `STATS_FIELDS`, and still returns `False` rather than raising on the five documented
  failure modes.

### Integration Tests:

- A second upload adds a stage and keeps the first file — asserted **after commit** via
  `django_capture_on_commit_callbacks(execute=True)`; without `execute=True` the assertion
  passes while proving nothing.
- Cross-trip isolation: uploading to trip A never touches trip B's stages.
- Deleting a trip removes every stage's file; deleting one stage removes only its own.
- A rejected upload re-renders the page with every existing stage intact — the
  `GpxUploadView` path owes the template the same context `TripDetailView` supplies.
- Ownership: no new pk route, so `OBJECT_SCOPED_ROUTES` is unchanged. `_assert_no_track_was_attached`
  (`tests/test_ownership_matrix.py:158-174`) already compares the full pk list, so it holds
  under ADD — but re-read it if fixtures start seeding multiple stages.

### Bite-proof harness:

One new shape (`upload_replaces_instead_of_adding`, risk #1). Run explicitly —
`addopts` deselects `bite_proof` from every plain run:

```
uv run pytest -m bite_proof -v
```

### CI-equivalence (both invocations — `addopts` deselects `bite_proof`):

```
SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov
SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest -m bite_proof
```

### Manual Testing Steps:

1. Create a trip; upload `timed-track-day-2.gpx` (2026-06-02), then `timed-track.gpx`
   (2026-06-01). The stage list must show day 1 first — proving ride order beats upload order.
2. Confirm both download links serve their own original bytes.
3. Upload a third, untimed file; confirm the list falls back to upload-order wording and the
   break markers disappear.
4. Upload a real multi-day export and **record page weight and time-to-interactive** (Phase 3).
5. Delete the trip; confirm `manage.py reconcile_media` reports nothing orphaned.
6. Check the page at phone width for a 5-stage trip.

## Performance Considerations

`MAX_GPX_POINTS = 100_000` is a *per-track* cap (~2.4 MB of inlined JSON), and N stages
multiply it N-fold into one page, against the NFR that the page must reach an interactive
state without feeling broken. `gpx/constants.py:16-22` flagged the figure as
"provisional … not yet calibrated against a real multi-day tour export" — this change is what
produces that calibration.

**Measured 2026-09-03 (criterion 3.15), on a real three-day tour**: 3 stages, 123 km,
8,330 points, a 178 KiB inlined payload inside a 186 KiB page, 67 ms server render —
~21.9 bytes per point, matching the synthetic estimate. Real sampling runs ~2,800 points
per riding day, so one stage at the cap would be ~25 riding days in a single file. No
thinning is warranted and no Engineering Backlog row was opened; the figures and the
conditions that would invalidate them now live in `gpx/constants.py` beside the constant
itself, rather than only here. Deliberately measured rather than pre-solved: thinning is a real
algorithm with its own tests, and building it into the milestone's riskiest slice on an
unmeasured problem is the wrong trade. Phase 3's manual verification records the number; a
bad one opens an Engineering Backlog row with that number as its trigger.

Two cheap wins are already in hand: bounds are aggregated from stored scalar columns rather
than computed from points, and `build_trip_stats` reads plain columns — so neither the map
box nor the statistics cost anything per point.

**Added at implementation review (F10): the one per-stage cost this section originally
omitted.** `build_stages` calls `track_file_is_available` once per stage, and that helper
does touch storage — `track.file.storage.exists(track.file.name)` (`gpx/availability.py:27`)
— so an N-stage trip makes **N storage calls per render**, on the detail path and on the
rejected-upload re-render alike. Accepted deliberately: under `FileSystemStorage` on the
mounted volume each is an `os.path.exists`, and the accuracy it buys is per-stage rather
than per-trip, which is the whole point of the stage list showing one dead link beside live
siblings rather than condemning the lot.

The assumption to watch is the storage backend, not the stage count: **the day `MEDIA_ROOT`
moves to an object store, these become N network round-trips on every page view** and want
batching or caching before they want anything else. There is no DB N+1 here to confuse it
with — `build_stages` materialises `ordered_stage_tracks` once with `list(...)`, both views
call it once and pass the tuple to `build_map_config`, and every figure after that is read
off an already-loaded instance. `tests/trips/test_trip_detail_stats.py`'s
`DETAIL_PAGE_QUERIES` pins the query count, though only against a single-stage trip — see
the review's Notes.

## Migration Notes

Two migrations, deliberately separate so schema and data stay independently reversible:
`0004` adds both columns nullable (Phase 1), `0005` backfills from stored files (Phase 6).
Generate and commit both by hand and verify with `makemigrations --check --dry-run` —
`manage.py check` passes with a model/schema mismatch and the deploy pipeline runs `migrate`
unattended at container boot, so a forgotten migration ships green and surfaces as a
production `no such column` (`lessons.md` #9).

`0005` must not be relied on as the only fill path: a migration cannot be re-applied once
recorded, so if it runs against a misconfigured `MEDIA_ROOT` it fills nothing and
`manage.py backfill_gpx_stats` is the documented recovery. Read `DEPLOY.md`'s `MEDIA_ROOT`
section before deploying this.

If Phase 6 is cut, `0004` ships alone and existing rows keep null instants — legal, handled
by the ordering expression, and re-fillable later by the command.

**Amended at implementation review (F2).** That last clause was false as first written: the
command refills only what `STATS_FIELDS` names, and Phase 6 §1 is where the two instants
join that tuple — so with Phase 6 cut there was no fill path at all, and US-02's own
scenario (an existing trip gaining a second stage) could never establish chronology. Phase
6 §1's `STATS_FIELDS` widening was therefore pulled forward into phases 1-5, which makes the
sentence true: `manage.py backfill_gpx_stats --all` now refills instants. Phase 6 keeps
migration `0005` (the unattended fill at container boot) and its own success criteria; only
§1's tuple and helper landed early.

Pulling it forward exposed a latent trap worth recording, because it predates this change:
`0003` narrowed its historical queryset with `.only("id", "file", *STATS_FIELDS)`, importing
a **live** constant into a migration that runs at `0002`'s schema state. The moment that
tuple grew, `.only()` raised `FieldDoesNotExist` from `pending.iterator()` — outside the
per-row guard — failing `migrate` outright on every fresh database, which is a failed
container boot. `0003` now pins its own `STATS_COLUMNS_AT_0002`, and
`gpx.statistics._writable_stats_fields` builds `update_fields` from the row's own model so
the shared helper stays safe under either schema state. The rule: **a migration's field list
is history, not configuration** — never narrow or write a historical queryset with a name
imported from live application code.

## References

- Research: `context/changes/multi-stage-gpx-upload/research.md`
- Change identity: `context/changes/multi-stage-gpx-upload/change.md`
- Roadmap slice S-01 and E-10's closure: `context/foundation/roadmap.md:64-75,235-241`
- PRD scope and guardrails: `context/foundation/prd.md:46,53,66-77,103-108`
- Risk map and the map-testing boundary: `context/foundation/test-plan.md` §2, §6.8, `:323`
- Replace semantics upheld at review: `context/archive/2026-08-23-upload-gpx-and-view-map/reviews/impl-review-phase-3.md:173-178`
- The TOCTOU finding that shaped the block being removed: `.../impl-review-phase-4.md:98-114`
- Scalar-columns-over-JSON precedent: `context/archive/2026-08-27-trip-distance-duration-stats/plan.md:155-160`
- The `#map` byte-exact pin and runtime-injection rule: `context/archive/2026-09-02-interactive-trip-map/plan.md:52-65`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Stage instants captured at parse

#### Automated

- [x] 1.1 Migration guard clean: `makemigrations --check --dry-run` — d8f0d7a
- [x] 1.2 Migration applies: `manage.py migrate` — d8f0d7a
- [x] 1.3 A timed upload stores both instants as UTC-aware values matching the file's first and last `<time>` — d8f0d7a
- [x] 1.4 An untimed upload stores null for both, and still stores its distance — d8f0d7a
- [x] 1.5 A file with naive timestamps stores null for both rather than a naive instant — d8f0d7a
- [x] 1.6 A multi-segment timed file spans first segment start to last segment end — d8f0d7a
- [x] 1.7 No naive-datetime `RuntimeWarning` is emitted anywhere in the suite — d8f0d7a
- [x] 1.8 Quality gates pass — d8f0d7a

#### Manual

- [x] 1.9 A real timed export shows both instants on the admin change form, both editable — d8f0d7a

### Phase 2: ADD semantics and chronological ordering

#### Automated

- [x] 2.1 A second upload leaves the first row and its stored file intact, asserted after commit — 92940a0
- [x] 2.2 A second upload to trip A leaves trip B's tracks untouched — 92940a0
- [x] 2.3 Two timed stages uploaded in reverse ride order come back in ride order — 92940a0
- [x] 2.4 Two untimed stages come back in upload order — 92940a0
- [x] 2.5 A mixed pair returns the timed stage first, untimed appended — 92940a0
- [x] 2.6 `chronology_is_established` answers correctly for all-timed, any-untimed, and no stages — 92940a0
- [x] 2.7 The `pre_save` receiver removes nothing when a sibling stage is inserted — 92940a0
- [x] 2.8 Deleting one stage removes exactly its own file — 92940a0
- [x] 2.9 Bite-proof harness passes with the new shape: `pytest -m bite_proof` — 92940a0
- [x] 2.10 Quality gates pass — 92940a0
- [x] 2.13 The new shape's `fragment` discriminates: present under the mutation, absent when the guard fails for an unrelated reason — 92940a0

#### Manual

- [x] 2.11 Two files uploaded to one trip both appear in admin and both download links serve their own bytes — 92940a0
- [x] 2.12 Deleting the trip leaves neither file; `reconcile_media` reports nothing orphaned — 92940a0

### Phase 3: Multi-stage rendering

#### Automated

- [x] 3.1 A single-stage trip's payload carries one segment matching its stored points — ac6ff25
- [x] 3.2 A three-stage trip carries three segments in ride order with distinct colours — ac6ff25
- [x] 3.3 Whole-trip bounds equal the min/max across all stages — ac6ff25
- [x] 3.4 Markers are exactly one `start`, one `finish`, one `break` per boundary — ac6ff25
- [x] 3.5 No `break` markers when any stage lacks `started_at` — ac6ff25
- [x] 3.6 A stage with no points is skipped without raising — ac6ff25
- [x] 3.7 The payload is still delivered by `json_script` only — ac6ff25
- [x] 3.8 Marker icon URLs still follow a moved `STATIC_URL` — ac6ff25
- [x] 3.9 `#map`'s markup is byte-identical to today — ac6ff25
- [x] 3.10 `collectstatic --noinput` then `pytest tests/test_static_references.py` passes — ac6ff25
- [x] 3.11 Quality gates pass — ac6ff25
- [x] 3.16 Bite-proof harness passes with the repointed risk-#3 shape: `pytest -m bite_proof` — ac6ff25

#### Manual

- [x] 3.12 Three visibly distinct coloured segments in ride order, markers at start, end and both breaks — ac6ff25
- [x] 3.13 Every hue is legible over the OSM basemap at tour extent and street zoom — ac6ff25
- [x] 3.14 A single-stage v1 trip looks unchanged — ac6ff25
- [x] 3.15 Measurement: record a real multi-day tour's page weight and time-to-interactive; open a backlog row if unacceptable — **unchecked at implementation review (F3): the criterion's deliverable is a recorded number and none was written down.** `gpx/constants.py:16-22` still reads "not yet against a real multi-day tour export", `## Performance Considerations` below still says the calibration is forthcoming, and no backlog row was opened. This is the one criterion outstanding across Phases 1-5; it needs a real export uploaded and the page observed, then the two figures written into `gpx/constants.py`. **Done 2026-09-03**: a real three-day tour (3 stages, 123 km, 8,330 points) measures 178 KiB of payload in a 186 KiB page, 67 ms server render; the figures and the conditions that would invalidate them are in `gpx/constants.py`, and no backlog row was warranted

### Phase 4: Stage list and per-stage statistics

#### Automated

- [x] 4.1 A three-stage trip renders three stats blocks with each stage's own figures — f16973d
- [x] 4.2 Each stage row links to its own `gpx:download` pk — f16973d
- [x] 4.3 A stage with a missing file renders the unavailable text while siblings keep live links — f16973d
- [x] 4.4 A stage with all-null statistics renders the "not worked out" sentence — f16973d
- [x] 4.5 A single-stage trip renders one row with today's figures — f16973d
- [x] 4.6 The list claims chronological order only when the predicate is true — f16973d
- [x] 4.7 `#map`'s markup and the `json_script` element are unchanged — f16973d
- [x] 4.8 Assertion-strength audit passes with no new waivers — f16973d
- [x] 4.9 Quality gates pass — f16973d
- [x] 4.13 Bite-proof harness passes with the requoted risk-#3 fragment: `pytest -m bite_proof` — f16973d
- [x] 4.14 The delete confirmation counts files correctly for multi-stage, single-stage and trackless trips — f16973d

#### Manual

- [x] 4.10 Each swatch colour matches its map segment — f16973d
- [x] 4.11 The page reads sensibly at phone width for a 5-stage trip — f16973d
- [x] 4.12 Uploading to a trip with an existing stage returns "Stage added." and the row lands in the right position — f16973d

### Phase 5: Distinct stage markers

#### Automated

- [x] 5.1 The payload's three `icons` keys resolve to three different URLs, each following `STATIC_URL` — 6913a5e
- [x] 5.2 All three SVGs resolve through `finders.find()` and survive `collectstatic --noinput` — 6913a5e
- [x] 5.3 `pytest tests/test_static_references.py` passes under the production manifest backend — 6913a5e
- [x] 5.4 Quality gates pass — 6913a5e

#### Manual

- [x] 5.5 Start, finish and break markers are distinguishable without hovering, on desktop and phone — 6913a5e
- [x] 5.6 Each pin's tip sits exactly on its coordinate — 6913a5e
- [x] 5.7 All three render correctly under the hashed manifest after `collectstatic` — 6913a5e

### Phase 6: Backfill stage instants for existing rows

#### Automated

- [x] 6.1 The helper fills both instants from a stored timed file and leaves them null for an untimed one — 06368bb
- [x] 6.2 The helper still writes nothing but `STATS_FIELDS` — 06368bb
- [x] 6.3 The helper returns `False` and logs, without raising, on a missing or unparseable file — 06368bb
- [x] 6.4 `backfill_gpx_stats --all` fills instants; the default run converges (an untimed row is not selected twice) — 06368bb
- [x] 6.5 Migration guard clean; `migrate` runs forward and backward over a pre-`0004` row — 06368bb
- [x] 6.6 Quality gates pass — 06368bb

#### Manual

- [x] 6.7 Against a copy of production data, `--all` fills instants and the tally matches the row count — 06368bb
- [x] 6.8 An existing v1 trip correctly orders a newly uploaded earlier-ridden stage ahead of it — 06368bb

### Phase 7: Derived trip span and date wording

#### Automated

- [x] 7.1 A fully timed multi-stage trip shows a span from first stage start to last stage end
- [x] 7.2 A trip with any untimed stage shows the stored `Trip.date` alone
- [x] 7.3 A trip with no stages shows the stored `Trip.date`, as today
- [x] 7.4 A same-day span renders as one date, not a repeated range
- [x] 7.5 The rendered form carries the new help text with `aria-describedby` wiring intact
- [x] 7.6 `clean_date` still rejects a future date and still skips when the date is unchanged
- [x] 7.7 Quality gates pass

#### Manual

- [x] 7.8 A real multi-day tour's detail page shows a span matching the rider's memory
- [x] 7.9 The create and edit forms read correctly with the new sentence
