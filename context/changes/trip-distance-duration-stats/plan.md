# Trip Distance and Duration Stats Implementation Plan

## Overview

Show basic ride statistics — distance, recorded time and elevation gain/loss — on the
trip detail view, computed from the uploaded GPX file. Implements roadmap **S-05** / PRD
**FR-010** (Secondary Success Criterion).

The stats are captured during the single `gpxpy` parse that already runs at upload,
stored in four nullable columns on `GpxTrack`, and rendered by a pure builder that
mirrors `build_map_config`. Existing tracks are backfilled best-effort by a data
migration.

**"Recorded time", not "elapsed time"** — the label is a deliberate semantic. gpxpy's
`get_duration()` sums each *segment's* first-to-last span and excludes the gaps between
segments, so a tour export that paused and resumed recording reports riding time, not
wall-clock time from first point to last. For a multi-day tour — this product's whole
subject — those gaps include every overnight, so calling the number "elapsed" would be
wrong by days. The sum is the more useful figure; it just needs the honest name.

## Current State Analysis

**Nothing computes distance, duration or elevation anywhere in the codebase.** A
repo-wide grep for `distance|duration|haversine|elevation|statistics|length_2d` returns
only an unrelated session-cookie comment in `velo_log/settings.py`.

What exists today:

- `GpxTrack` (`gpx/models.py:20-42`) stores `trip`, `file`, `points`, four bound floats,
  `original_filename`, `uploaded_at`. No statistics columns.
- `points` is `[[lat, lon], ...]` rounded to `COORDINATE_DECIMAL_PLACES` (5). Elevation
  and per-point timestamps are **discarded** inside the list comprehension at
  `gpx/parsing.py:154-162` — they never reach the database.
- `gpx/parsing.py:143` (`gpx = gpxpy.parse(text)`) is the **only** point in the entire
  request lifecycle where the full gpxpy object, with elevation and time intact, exists.
- `GpxUploadForm.clean_file` (`gpx/forms.py:84-89`) copies each derived column from
  `ParsedTrack` onto `self.instance`. This is the established path for a derived column:
  the fields have no form field, so Django's `construct_instance` never sets them.
- `build_map_config` (`gpx/map_config.py:22`) is the reference pure-function shape:
  `GpxTrack | None → dict | None`, returns `None` on nothing-to-show, reads stored
  columns and never re-parses.
- **Two views render `trips/trip_detail.html`** and each independently builds the
  context: `TripDetailView.get_context_data` (`trips/views.py:83-97`) and
  `GpxUploadView.get_context_data` (`gpx/views.py:66-78`). Both docstrings warn that a
  key set in one and missed in the other renders the failure branch over healthy data.
- `gpx/migrations/` holds only `0001_initial.py`; the model and the migration agree.

Key constraints discovered:

- `GpxTrackAdmin` (`gpx/admin.py`) uses `exclude = ("points",)`, so **every other field
  appears on the admin change form**. A new column that is `null=True` but not
  `blank=True` renders as *required* there and breaks the admin repair path.
- `tests/conftest.py`'s `make_gpx_track` / `make_stored_track` build tracks from `points`
  plus bounds only. Nullable columns leave both untouched; non-null columns would break
  every track-based test in the suite.
- `tests/gpx/fixtures/valid-track.gpx` carries `<ele>` but **no `<time>`**;
  `second-track.gpx` carries neither. There is no fixture with both, so the
  fully-populated path currently has nothing to test against.

### Key Discoveries:

- **`get_uphill_downhill()` returns `0`, not `None`, on a file with no elevation.**
  Verified against the installed `gpxpy` — a bare track returned
  `UphillDownhill(uphill=0, downhill=0)` while `get_elevation_extremes()` returned
  `MinimumMaximum(minimum=None, maximum=None)`. Storing that `0` would render
  "0 m climbed" for an Alpine tour whose exporter omitted `<ele>`. The elevation-extremes
  call is the only reliable presence probe.
- **`get_moving_data().moving_time` returns `0.0`, not `None`, on a file with no
  timestamps** — the same trap. `get_duration()` looks like the presence probe for time
  but is not a safe one: `GPXTrackSegment.get_duration` returns `0.0` for any segment
  with fewer than two points *before* it reaches the timestamp check that produces
  `None`, and the track- and file-level calls sum those zeros. Since `parse_gpx` accepts
  a one-point file, `get_duration()` would report `0.0` — not `None` — for an untimed
  single-point track. `get_time_bounds().start_time is None` is the reliable probe: it
  is `None` exactly when no point carried a `<time>`, mirroring the elevation gate.
- **`length_3d()` degrades silently to the 2D value** when elevation is absent (both
  returned `1322.77` on the bare track), so distance never has a null case.
- **`get_duration()` sums per-segment spans, not first-point-to-last-point.**
  `GPX.get_duration` → `GPXTrack.get_duration` → `GPXTrackSegment.get_duration`
  (`gpx.py:2341` → `1754` → `1119`): each segment contributes `last.time - first.time`
  and the gaps *between* segments are never counted. A single-segment export therefore
  reports wall-clock elapsed, while a paused-and-resumed multi-day export reports only
  the recorded spans. This is why the stat is labelled **recorded time** throughout, and
  why a two-segment fixture pins the behaviour rather than leaving it inherited.
- **`get_moving_data()` is not shipped at all.** Its `max_speed` read `0.0` on real timed
  probe input and its `moving_time` read `1800.0` against `7200.0` elapsed — half the
  legs classified as stopped on a 3-point track. The two outputs are not equally
  trustworthy (`max_speed` is distorted by percentile clipping on short tracks, while
  threshold classification behaves sensibly on real 1 Hz data), but neither was probed
  against a real ride, and shipping a stat this slice cannot vouch for is not worth a
  column. See "What We're NOT Doing".
- `gpxpy>=1.6.2` is already a dependency (`pyproject.toml`, added by S-03). No new
  package, no new URL, no new view.
- The API surface was pre-fetched for this slice in
  `context/archive/2026-08-23-upload-gpx-and-view-map/research/gpxpy-context7-docs.md`
  ("feeds S-05") — use it rather than re-querying Context7.

## Desired End State

A rider opening a trip whose GPX file has been uploaded sees a **Stats** section on the
detail page showing distance in kilometres, recorded time, and elevation gained and lost.
Where the file itself did not carry the underlying data, that stat reads as explicitly not
recorded rather than as a zero or a blank. A trip with no track shows no Stats section at
all, exactly as it shows no map.

Verify by uploading `tests/gpx/fixtures/valid-track.gpx` (elevation, no timestamps) and
a timed file, and confirming the first renders distance and elevation with recorded time
marked unavailable, and the second renders all four.

## What We're NOT Doing

- **No elevation profile chart.** `@raruto/leaflet-elevation` is GPL-3.0 and was parked
  in S-03's plan; that stays parked.
- **No speed or moving-time stats — nothing from `get_moving_data()`.** `max_speed` read
  `0.0` on the probe's timed input, and `moving_time` classified half a 3-point track's
  legs as stopped. The two are not equally suspect, but both come out of the same
  threshold-and-percentile machinery that this slice has only probed against synthetic
  fixtures, and neither has been checked against a real ride. Shipping one while
  excluding the other on reliability grounds would be an argument this slice cannot
  make, so both are deferred together. Parked as a feature item on the roadmap, to be
  taken up with real timed exports in hand rather than as a rider on a nice-to-have
  slice. Dropping it also removes a column, a migration field, a formatter, a template
  row and three tests.
- **No per-stat display on the trip *list* page.** FR-010 and S-05 both name the detail
  view only.
- **No recomputation of `points` or bounds.** The backfill writes the four new columns
  and nothing else, so it can never disturb data the map already draws correctly.
- **No re-parsing at render time.** Rejected deliberately — see Implementation Approach.
- **No scheduled or automatic re-backfill.** The data migration fills existing rows at
  deploy and a management command exists to re-run the same helper on demand
  (Phase 2 §3); nothing watches for rows that stayed null and retries them.
- **E-11 (orphaned file on a rolled-back upload transaction) stays open.** This change
  does not touch `GpxUploadView.form_valid`'s transaction. See `change.md`.
- **No new `MAX_GPX_POINTS` calibration.** Statistics iterate the same parsed object the
  existing point extraction already walks; the cap is unchanged.
- **No handling of *partially* populated files.** Both presence gates are all-or-nothing
  by design: `get_elevation_extremes().minimum is None` and
  `get_time_bounds().start_time is None` each answer "did *any* point carry this?", not
  "did every point?". gpxpy's `get_uphill_downhill` docstring is explicit that "if
  elevation for some points is not found those are simply ignored", so a file where only
  some points carry `<ele>` clears the gate and reports gain computed over that subset —
  and the same holds for a partially timed file. This is accepted, not overlooked: the
  gates exist to stop a *wholly* absent input rendering as a confident `0`, which is the
  defect with a real failure mode. A subset-derived figure is an understated real number,
  not a fabricated one, and detecting the shape would mean walking every point to compare
  counts — cost that buys a caveat no rider would act on.

## Implementation Approach

**Parse once, never fail at render.** `gpx/models.py:25` states the rule in the
codebase's own words: "Points and bounds are derived once at upload, so rendering the
detail page can never fail on a parse." Statistics follow the same path — computed inside
`parse_gpx` where the full gpxpy object already exists, carried on `ParsedTrack`, copied
onto the instance by `clean_file`, and read back from plain columns at render time. The
alternative (re-parsing `track.file` on each page view) was rejected: `GpxDownloadView`
already proves a row's file can go missing, and the PRD's only NFR forbids a blank page.

Four nullable columns rather than one `JSONField`, because `GpxTrack` already stores its
four bounds as scalar `FloatField`s rather than JSON — scalar columns are the established
precedent for derived numbers on this model.

The schema change and the backfill are separate phases and separate migrations, following
the additive-first migration rule: add nullable columns, then fill them. Either can be
reverted without the other.

## Critical Implementation Details

**Timing & lifecycle.** Compute the statistics *after* the empty-track and
`MAX_GPX_POINTS` rejections in `parse_gpx`, not before. A file that is about to be
refused should not pay for a full-track distance walk, and the ordering keeps the
existing rejection messages first in the function.

**State sequencing — the zero-versus-null traps.** Two gpxpy calls return `0` where a
caller would expect `None`, and storing that zero is a silent data defect:

- `get_uphill_downhill()` → `(0, 0)` when no point carries `<ele>`. Gate both values on
  `get_elevation_extremes()`: if its `minimum` is `None`, store `None` for gain and loss.
- `get_duration()` → `0.0`, not `None`, for any segment of fewer than two points. Gate
  recorded time on `get_time_bounds()`: if its `start_time` is `None`, store `None`. Do
  **not** gate on `get_duration() is None` — an untimed one-point file (which `parse_gpx`
  accepts) would store the exact zero this gate exists to prevent. `get_duration()`
  supplies the *value*; `get_time_bounds()` decides whether there is one, which makes
  both gates structural and symmetric.

**Migration.** `manage.py check` passes with a model/schema mismatch and Railway runs
`migrate` unattended at boot, so a forgotten migration ships green and surfaces as a
production `no such column` (lessons.md #9). Generate both migrations with
`makemigrations`, commit them, and confirm with `makemigrations --check --dry-run` — the
guard CI already runs.

**Backfill robustness.** The data migration imports application code, which couples a
historical migration to code that will keep changing. Two distinct failures, and they
need two distinct defences:

- **A row fails** — its file is missing from storage, or its bytes no longer parse. A
  broad `except Exception` around each row's work logs it and leaves that row's columns
  `None`. `migrate` still succeeds.
- **The import fails** — `gpx/statistics.py` is later renamed, moved, or its helper's
  signature changes. A module-level `from gpx.statistics import …` is evaluated when
  Django *builds the migration graph*, before a single row is touched, so the per-row
  guard never runs and `migrate`, `makemigrations --check` and `manage.py check` all
  break at once. Put the import **inside** the `RunPython` function body, under the same
  guard, with a comment saying why it is not at module level; then a broken import
  degrades to a logged skip and a replay on a fresh database still succeeds.

The docstring pin in `gpx/statistics.py` (Phase 2 §1) is what defends against the module
being *deleted* outright — the guard makes that survivable, not invisible.

The migration must write with `save(update_fields=[...])` naming only the four stats
columns.

**Test-visibility of the backfill.** Migrations run against an empty in-memory database
in this suite, so the data migration is a no-op under `pytest` and proves nothing. Its
logic must be tested by calling the extracted helper directly.

---

## Phase 1: Capture stats at parse time and store them

### Overview

Widen the parse boundary to capture the four statistics, add the columns to hold them,
and wire the upload path so every new upload stores them. No user-visible change yet.

### Changes Required:

#### 1. Named constants

**File**: `gpx/constants.py`

**Intent**: Name the unit conversions the formatting and computation will use, per the
project's no-magic-values rule.

**Contract**: Add `METERS_PER_KILOMETER`, `SECONDS_PER_HOUR`, `SECONDS_PER_MINUTE`. Each
carries a one-line comment in the file's existing register.

#### 2. Statistics on the parse boundary

**File**: `gpx/parsing.py`

**Intent**: Capture distance, recorded time and elevation gain/loss from the `gpx` object
that already exists at line 143, and carry them on `ParsedTrack` alongside the points and
bounds. This is the only place the data is available.

**Contract**: `ParsedTrack` gains four fields — `distance_meters: float`,
`duration_seconds: float | None`, `elevation_gain_meters: float | None`,
`elevation_loss_meters: float | None`. Distance is non-optional: `length_2d()` always
returns a float and the empty-track rejection above it guarantees at least one point. The
other three are `None` when the file did not carry the input, per the two gating rules in
Critical Implementation Details. Computation is placed after the `MAX_GPX_POINTS` check.

`duration_seconds` carries a field docstring stating the semantic explicitly: it is the
sum of each segment's first-to-last span, so gaps between segments — including overnight
gaps on a multi-day tour — are excluded. It is recorded time, not wall-clock elapsed
time. Without that note the next reader will assume the two are the same, which they are
only for a single-segment file.

Extract the gating into a small module-level helper so the two traps are asserted once
and directly, rather than only through `parse_gpx`'s return value.

#### 3. Storage columns

**File**: `gpx/models.py`

**Intent**: Persist the four statistics on `GpxTrack`.

**Contract**: Four new fields, all `models.FloatField(null=True, blank=True)`:
`distance_meters`, `duration_seconds`, `elevation_gain_meters`, `elevation_loss_meters`.

`blank=True` is load-bearing, not decoration: `GpxTrackAdmin` excludes only `points`, so
without it these four render as required fields on the admin change form and break the
documented admin repair path. `null=True` is required regardless — rows already in the
deployed database predate the columns, and Phase 2's backfill is best-effort.

`FloatField` for the second-valued column because gpxpy returns floats (`7200.0`);
storing it as an integer would invent a rounding decision at the storage layer rather
than at the display layer where it belongs. `duration_seconds` carries the same
recorded-time-not-elapsed note as its `ParsedTrack` counterpart in its `help_text`, so
the semantic is visible in the admin form as well as in the code.

#### 4. Schema migration

**File**: `gpx/migrations/0002_gpxtrack_stats.py` (generated)

**Intent**: Add the four nullable columns.

**Contract**: `AddField` × 4, no data operations. Generated with
`uv run python manage.py makemigrations gpx`, then committed.

#### 5. Upload path wiring

**File**: `gpx/forms.py`

**Intent**: Copy the four new `ParsedTrack` values onto the instance, following the
existing block at lines 84-89.

**Contract**: Four assignments appended to the existing `self.instance.…` sequence in
`clean_file`. No change to the validation order or the rewind in `finally`.

#### 6. New test fixtures

**File**: `tests/gpx/fixtures/timed-track.gpx` (new),
`tests/gpx/fixtures/single-point-track.gpx` (new),
`tests/gpx/fixtures/two-segment-track.gpx` (new)

**Intent**: No existing fixture carries both `<ele>` and `<time>`, so the
fully-populated path has nothing to test against. `valid-track.gpx` (elevation, no time)
and `second-track.gpx` (neither) already cover the two degraded shapes — but both have
two or more points in a single segment, so between them they exercise neither the
sub-two-point branch of `get_duration()` that returns `0.0` instead of `None`, nor the
per-segment summing that makes recorded time differ from wall-clock elapsed. Both are
behaviours this plan now depends on, so both get a fixture rather than being inherited
untested.

**Contract**:

- `timed-track.gpx` — a well-formed GPX 1.1 track of three points in the style of
  `valid-track.gpx`, each with `<ele>` and an ISO-8601 `<time>`, spanning a known
  duration so assertions can be exact.
- `single-point-track.gpx` — a well-formed GPX 1.1 track of exactly one point with
  neither `<ele>` nor `<time>`: the shape `parse_gpx` accepts at `gpx/parsing.py:166`,
  and the shape that makes `get_duration()` an unsafe presence probe.
- `two-segment-track.gpx` — two timed `<trkseg>` blocks inside one `<trk>`, separated by
  a gap substantially larger than either segment's own span (an hour each, six hours
  apart, so the two candidate numbers cannot be confused). Its assertion is that
  `duration_seconds` equals the **sum of the segment spans** and not the
  first-point-to-last-point difference — the recorded-time semantic, pinned.

#### 7. Track factory

**File**: `tests/conftest.py`

**Intent**: Let stats-aware tests build a track with known statistics without changing
what every existing caller gets.

**Contract**: `make_gpx_track` accepts four optional keyword arguments defaulting to
`None`. Existing call sites are unchanged and continue to produce a stats-less track —
which is also the legacy-row shape Phase 3 must render.

#### 8. Parsing and upload tests

**File**: `tests/gpx/test_gpx_parsing.py`, `tests/gpx/test_gpx_upload.py`

**Intent**: Pin the three data shapes and the persistence of the new columns.

**Contract**: Against `timed-track.gpx`, all four values are populated and distance and
duration match the fixture's known geometry and timestamps. Against `valid-track.gpx`,
elevation gain and loss are populated while duration is `None`. Against
`second-track.gpx`, all three optional values are `None`. Against
`single-point-track.gpx`, duration is likewise `None` — this is the case a
`get_duration() is None` gate gets wrong, so the test must fail if the probe is ever
changed back. Against `two-segment-track.gpx`, `duration_seconds` equals the sum of the
two segment spans, not the span from the first point to the last. All `None` assertions
are written as `is None`, **not** as falsy, since `0` is precisely the wrong value this
pins against. On the upload path, a POST of `timed-track.gpx` persists the four columns
on the created row.

### Success Criteria:

#### Automated Verification:

- Migration exists and is complete: `uv run python manage.py makemigrations --check --dry-run`
- Django checks pass: `uv run python manage.py check`
- Parsing tests pass: `uv run pytest tests/gpx/test_gpx_parsing.py`
- Upload tests pass: `uv run pytest tests/gpx/test_gpx_upload.py`
- Full suite passes with no `.env`: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- Lint, format, import order and strict typing pass: `/python-quality-gates`

#### Manual Verification:

- Uploading a real timed GPX export stores plausible values (check via `manage.py shell` or the admin)
- The `GpxTrack` admin change form still saves without filling the new fields

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human that the manual testing was
successful before proceeding to the next phase.

---

## Phase 2: Backfill existing tracks

### Overview

Fill the new columns for rows uploaded before they existed, best-effort, leaving them
`None` for any row whose file cannot be read or parsed.

### Changes Required:

#### 1. Backfill helper

**File**: `gpx/statistics.py` (new)

**Intent**: Recompute a single track's statistics from its stored file and save only the
stats columns. Lives in application code rather than inside the migration so it can be
unit-tested directly — migrations are a no-op against this suite's empty database.

**Contract**: A function taking a `GpxTrack` (or the historical model instance the
migration passes) and returning whether it filled anything. It opens `track.file`, feeds
the bytes to the existing `parse_gpx_bytes`, and saves with
`update_fields=[<the four stats columns>]` — never touching `points` or the bounds.
Failure to open or parse is logged and returns `False` rather than raising.

The module docstring must name migration `0003` as a consumer, so a future reader knows
this function cannot be deleted while that migration exists.

#### 2. Data migration

**File**: `gpx/migrations/0003_backfill_gpxtrack_stats.py` (new)

**Intent**: Run the helper across every existing row on deploy.

**Contract**: A `RunPython` forward operation iterating rows that have `distance_meters`
null, with `migrations.RunPython.noop` as the reverse (the columns are dropped by 0002's
reverse anyway). The `from gpx.statistics import …` sits **inside** the forward
function, not at module level, so a later rename cannot break migration-graph loading —
see "Backfill robustness" above. Both that import and each row's work are wrapped so any
exception is logged and skipped: `migrate` must not fail because one file is unreadable
or because application code changed shape, and must stay replayable on a fresh database.

#### 3. Re-runnable backfill command

**File**: `gpx/management/commands/backfill_gpx_stats.py` (new)

**Intent**: Give the backfill a recovery path that is not "re-upload every file by
hand". Migration `0003` runs once, unattended, at boot — and its most likely failure is
a misconfigured `MEDIA_ROOT`, the one operational fault this repo has escalated to a
Hard Rule in `AGENTS.md`, documented in `DEPLOY.md`, and wired into `/healthz/`. If that
deploy is the deploy `0003` applies on, the migration fills nothing and can never be
re-run. The command makes that recoverable in one invocation.

**Contract**: A `BaseCommand` looping the same `gpx/statistics.py` helper the migration
calls, over `GpxTrack` rows with `distance_meters` null by default. A `--all` flag
reprocesses every row (for a track whose file was replaced or whose stats are stale).
Per-row failures are reported and skipped, never raised; the command prints a filled /
skipped tally and exits 0 even when some rows could not be read — a partially unreadable
media directory is a report, not a crash. No new logic: every line of computation lives
in the helper, so the command and the migration cannot drift.

#### 4. Backfill tests

**File**: `tests/gpx/test_gpx_statistics.py` (new)

**Intent**: Prove the helper both fills and fails safely, since the migration itself
proves nothing under pytest.

**Contract**: A track built by `make_stored_track` with the bytes of `timed-track.gpx`
gains all four values. A track whose stored file is absent from storage is left with all
four `None` and does not raise. A track built with `valid-track.gpx` bytes gains distance
and elevation while duration stays `None`. One test asserts `points` and
the four bounds are byte-for-byte unchanged after a backfill.

For the command (invoked via `call_command`): it fills a null-stats track, leaves an
already-filled track untouched unless `--all` is passed, and exits without raising when
one row's file is missing. This is what keeps the new file above `fail_under = 80`.

### Success Criteria:

#### Automated Verification:

- Migrations apply cleanly on an empty database: `uv run python manage.py migrate`
- No further migration is outstanding: `uv run python manage.py makemigrations --check --dry-run`
- Statistics tests pass: `uv run pytest tests/gpx/test_gpx_statistics.py`
- Full suite passes with no `.env`: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- Lint, format, import order and strict typing pass: `/python-quality-gates`

#### Manual Verification:

- Running `migrate` against a copy of the local development database fills stats on pre-existing tracks
- A track whose file has been deleted from `MEDIA_ROOT` leaves `migrate` succeeding, with a log line naming the row
- `uv run python manage.py backfill_gpx_stats` refills a track whose stats columns were nulled by hand, and reports its tally

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human that the manual testing was
successful before proceeding to the next phase.

---

## Phase 3: Render stats on the trip detail page

### Overview

Shape the stored values for display and render them on both paths that serve the trip
detail page. This is the phase that makes the feature user-visible.

### Changes Required:

#### 1. Display builder and formatters

**File**: `gpx/statistics.py`

**Intent**: Turn stored numbers into display-ready strings, so the template stays free of
arithmetic — matching how `build_map_config` hands the template a finished blob.

**Contract**: A frozen `TripStats` dataclass of four `str | None` fields, and
`build_trip_stats(track: GpxTrack | None) -> TripStats | None` mirroring
`build_map_config`'s signature exactly. It returns `None` when `track is None` **or when
all four stored values are null** — the legacy-row case, which the template must
distinguish from a file that simply lacked the data. A `None` field inside a returned
`TripStats` means the file did not carry that stat.

The all-null test is `all(value is None for value in …)` — explicitly **not** `not
any(...)` or any other falsy check. A track whose points are all identical stores
`distance_meters = 0.0`: legal, non-null, and falsy. Under a falsy check that perfectly
parsed track would collapse the entire Stats section into the re-upload sentence. This is
the same zero-versus-null trap the parse boundary guards against, one layer up.

Three module-level formatters, unit-testable in isolation: distance as kilometres to one
decimal place, seconds as hours and minutes (falling back to minutes only under an hour),
elevation as whole metres. All three take the stored value and return a string; each
returns `None` for a `None` input.

#### 2. Detail view context

**File**: `trips/views.py`

**Intent**: Expose the stats blob on the normal detail-page path.

**Contract**: `TripDetailView.get_context_data` sets `context["stats"] =
build_trip_stats(track)` beside the existing `map_config` line, and imports
`build_trip_stats` alongside `build_map_config`. Extend the docstring's list of keys the
two render paths must keep in sync.

#### 3. Upload view context

**File**: `gpx/views.py`

**Intent**: Expose the same key on the failed-upload re-render, or a rider whose upload
was rejected loses the stats for the route they already had.

**Contract**: The identical assignment in `GpxUploadView.get_context_data`. This is the
two-place change both view docstrings warn about; a test asserts the parity rather than a
comment.

#### 4. Template

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: Render the Stats section, with an explicit sentence wherever a stat is
unavailable.

**Contract**: A `<h2>Stats</h2>` block placed inside the existing `{% if track %}` branch
after the download paragraph, so it disappears in the no-track empty state without a
second condition. `{% if stats %}` renders the four labelled values — the time one
labelled **"Recorded time"**, not "Elapsed time", per the semantic in the Overview —
each falling back to
a short sentence naming the file as the reason when its field is `None`. The `{% else %}`
branch — a track whose stats were never computed — gets its own deliberate sentence
pointing at re-upload, worded differently from the per-stat notes so a bug report tells
the two apart. This follows the section's existing discipline: every `{% else %}` in this
template already renders a sentence rather than nothing.

#### 5. Display and render-path tests

**File**: `tests/gpx/test_gpx_statistics.py`, `tests/trips/test_trip_detail_stats.py` (new)

**Intent**: Cover the formatters directly and the two render paths end to end.

**Contract**: Formatter unit tests cover a sub-hour duration, a multi-hour duration, and
`None` for each of the three. A `build_trip_stats` test pins the falsy trap: a track with
`distance_meters = 0.0` and the other four `None` returns a populated `TripStats`, not
`None`. View tests, following the `auth_client` + `reverse` +
`response.context` pattern in `tests/trips/test_trip_detail.py`: a track with full stats
renders all four values; a track with no timestamps renders the recorded-time note and still
renders distance; a track with all-null stats renders the re-upload sentence; a trip with
no track renders no Stats heading at all. One test POSTs an invalid file to
`gpx:upload` and asserts the rejected re-render carries the same `stats` value as the GET
path — the parity the two docstrings ask for.

### Success Criteria:

#### Automated Verification:

- Statistics tests pass: `uv run pytest tests/gpx/test_gpx_statistics.py`
- Detail-page stats tests pass: `uv run pytest tests/trips/test_trip_detail_stats.py`
- Existing detail and map tests still pass: `uv run pytest tests/trips/`
- Static references still resolve: `uv run python manage.py collectstatic --noinput` then `uv run pytest tests/test_static_references.py`
- Full suite passes with no `.env`: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- Lint, format, import order and strict typing pass: `/python-quality-gates`

#### Manual Verification:

- A trip with a timed GPX file shows all four stats, correctly formatted, with the time one labelled "Recorded time"
- A trip with `valid-track.gpx` shows distance and elevation, with recorded time marked not recorded
- A trip with no GPX file shows no Stats section
- Submitting an invalid file on a trip that has a track re-renders the page with its stats intact
- The page is readable with the stylesheet blocked

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human that the manual testing was
successful before proceeding to the next phase.

---

## Phase 4: Sync AGENTS.md and roadmap

### Overview

`AGENTS.md` loads in every session, so a stale description of what the `gpx` app owns
actively misdirects the next agent. lessons.md #5 names both artefacts — "Update
`AGENTS.md` **and roadmap status** in the same slice that invalidates them" — and two
roadmap rows go stale the moment this ships.

### Changes Required:

#### 1. Repository guidelines

**File**: `AGENTS.md`

**Intent**: The `gpx/` bullet describes the app as upload, parse, store, download, map
config and file lifecycle. It now also computes and stores a track's statistics, and owns
a module whose backfill helper is pinned by a migration.

**Contract**: Extend the `gpx/` bullet in Project Structure to name statistics as an
owned concern, and note that `gpx/statistics.py`'s backfill helper cannot be deleted while
migration `0003` exists. Add `manage.py backfill_gpx_stats` to the Development Commands
table, since it is the documented recovery path in Migration Notes. No change to the Hard
Rules or Testing sections.

#### 2. Roadmap status

**File**: `context/foundation/roadmap.md`

**Intent**: Two rows describe S-05 as unstarted and blocked, and both are false once this
ships. lessons.md #5 requires them to move in the slice that invalidates them.

**Contract**: Two edits, following the wording S-03 and S-04 already use:

- Slice table (`roadmap.md:34`) — S-05's status column `planning` → `done`.
- Issue table (`roadmap.md:122`) — S-05's last column `Waiting on S-03` (stale since S-03
  closed) → `Planned and implemented (Phase 5, /10x-implement trip-distance-duration-stats)`,
  matching the S-02/S-03/S-04 format; the "shipped" column moves `no` → `yes`.

### Success Criteria:

#### Automated Verification:

- Full suite passes with no `.env`: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`

#### Manual Verification:

- The `gpx/` bullet reads accurately against the shipped code
- Both S-05 roadmap rows read `done` / `Planned and implemented`, with no "Waiting on S-03" left

---

## Testing Strategy

### Unit Tests:

- The gpxpy data shapes at the parse boundary: elevation + time, elevation only, neither,
  a single untimed point, and two timed segments. Optional values asserted `is None`,
  never as falsy — `0` is the defect being pinned against.
- The two zero-versus-null gates, asserted directly against their helper rather than only
  through `parse_gpx`.
- The recorded-time semantic: a two-segment file's `duration_seconds` is the sum of the
  segment spans, not first-point-to-last-point.
- The three formatters: sub-hour duration, multi-hour duration, `None` input.
- `build_trip_stats` returning `None` for a `None` track and for an all-null track, and a
  populated `TripStats` otherwise — including for a track whose only non-null value is
  `distance_meters = 0.0`, which a falsy all-null check would wrongly discard.
- The backfill helper: fills a readable file, leaves nulls on a missing file, and never
  modifies `points` or bounds.

### Integration Tests:

- Upload a timed GPX through the real form and assert the four columns on the stored row.
- GET the detail page for each of the three data shapes and assert the rendered values and
  notes.
- POST an invalid file to `gpx:upload` on a trip that has a track, and assert the
  re-rendered page carries the same stats as the GET path.
- A trip with no track renders no Stats heading.

### Manual Testing Steps:

1. Upload a real multi-day tour export and confirm distance, recorded time and elevation
   are plausible against whatever recorded the ride. If that export is multi-segment,
   note whether recorded time reads as riding time rather than wall-clock — the semantic
   this plan commits to, checked once against a real file.
2. Upload `tests/gpx/fixtures/valid-track.gpx` and confirm recorded time reads as not
   recorded rather than as zero.
3. Open a trip whose track predates this change (or null its stats columns by hand) and
   confirm the re-upload sentence appears rather than four zeroes.
4. Submit a `.txt` file on a trip that has a track and confirm the error re-render keeps
   the stats.
5. Confirm the `GpxTrack` admin change form still saves with the new fields left empty.

## Performance Considerations

The statistics calls walk the parsed track once more at upload time, on a file already
capped at `MAX_GPX_POINTS` (100,000). This is upload-time cost paid once, never
render-time cost — the whole point of storing the results. The render path gains four
column reads on a row it already fetches, and no new query.

The backfill migration re-parses every stored file once, at deploy. At this project's
scale (a personal diary, single-digit trips) that is negligible; it would need revisiting
before a bulk import.

## Migration Notes

Two migrations, applied in order by Railway's unattended `migrate` at boot:

- `0002` adds four nullable columns — reversible, no data touched.
- `0003` backfills them best-effort — `RunPython` with a `noop` reverse, per-row failures
  logged and skipped.

Rollback: reversing `0003` is a no-op and reversing `0002` drops the columns. No data
outside the four new columns is ever written, so a revert cannot damage `points`, the
bounds, or the stored files.

If `MEDIA_ROOT` is misconfigured at migrate time (the trap `AGENTS.md` and `DEPLOY.md`
both warn about), the backfill fills nothing and logs each skip. The columns stay null and
the page shows the re-upload sentence — visible, not silent. A migration cannot be
re-applied once recorded, so the recovery path is
`uv run python manage.py backfill_gpx_stats` (Phase 2 §3) after `MEDIA_ROOT` is
corrected — the same helper, run on demand, with no re-upload required.

## References

- Related research: `context/changes/trip-distance-duration-stats/research.md`
- Change identity and E-11 scope note: `context/changes/trip-distance-duration-stats/change.md`
- gpxpy API surface, pre-fetched for this slice: `context/archive/2026-08-23-upload-gpx-and-view-map/research/gpxpy-context7-docs.md`
- Reference pure-function pattern: `gpx/map_config.py:22`
- Derived-column upload path: `gpx/forms.py:84-89`
- Two-render-path warning: `trips/views.py:83-97`, `gpx/views.py:66-78`
- Migration discipline: `context/foundation/lessons.md` #9; docs sync: #5

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Capture stats at parse time and store them

#### Automated

- [x] 1.1 Migration exists and is complete: `makemigrations --check --dry-run` — c5924fc
- [x] 1.2 Django checks pass: `manage.py check` — c5924fc
- [x] 1.3 Parsing tests pass — c5924fc
- [x] 1.4 Upload tests pass — c5924fc
- [x] 1.5 Full suite passes with no `.env` — c5924fc
- [x] 1.6 Lint, format, import order and strict typing pass — c5924fc

#### Manual

- [x] 1.7 Uploading a real timed GPX export stores plausible values — c5924fc
- [x] 1.8 The `GpxTrack` admin change form still saves without filling the new fields — c5924fc

### Phase 2: Backfill existing tracks

#### Automated

- [x] 2.1 Migrations apply cleanly on an empty database — 070ff11
- [x] 2.2 No further migration is outstanding — 070ff11
- [x] 2.3 Statistics tests pass — 070ff11
- [x] 2.4 Full suite passes with no `.env` — 070ff11
- [x] 2.5 Lint, format, import order and strict typing pass — 070ff11

#### Manual

- [x] 2.6 Running `migrate` against a copy of the local database fills stats on pre-existing tracks — 070ff11
- [x] 2.7 A track whose file was deleted leaves `migrate` succeeding, with a log line naming the row — 070ff11
- [x] 2.8 `manage.py backfill_gpx_stats` refills a hand-nulled track and reports its tally — 070ff11

### Phase 3: Render stats on the trip detail page

#### Automated

- [x] 3.1 Statistics tests pass
- [x] 3.2 Detail-page stats tests pass
- [x] 3.3 Existing detail and map tests still pass
- [x] 3.4 Static references still resolve
- [x] 3.5 Full suite passes with no `.env`
- [x] 3.6 Lint, format, import order and strict typing pass

#### Manual

- [x] 3.7 A trip with a timed GPX file shows all four stats, correctly formatted, labelled "Recorded time"
- [x] 3.8 A trip with `valid-track.gpx` shows distance and elevation, recorded time marked not recorded
- [x] 3.9 A trip with no GPX file shows no Stats section
- [x] 3.10 An invalid-file re-render keeps the stats intact
- [x] 3.11 The page is readable with the stylesheet blocked

### Phase 4: Sync AGENTS.md and roadmap

#### Automated

- [ ] 4.1 Full suite passes with no `.env`

#### Manual

- [ ] 4.2 The `gpx/` bullet reads accurately against the shipped code
- [ ] 4.3 Both S-05 roadmap rows read `done` / `Planned and implemented`, with no "Waiting on S-03" left
