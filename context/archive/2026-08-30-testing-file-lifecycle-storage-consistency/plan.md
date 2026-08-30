# File Lifecycle and Storage/Row Consistency — Implementation Plan

## Overview

Test-plan Phase 2 covers Risk #1 (a delete or replace path leaves a file on the
volume forever, or removes one still in use) and Risk #3 (a trip's row survives
but its track becomes unreachable, and the page never says so). Research found
Risk #1 already close to fully proven by the existing suite — only two small,
well-defined gaps remain. Risk #3 has one real, unclaimed gap: the trip detail
page currently renders identically whether the track's file is present or has
vanished from storage, which is exactly the "nobody notices for months" shape
the risk names. Closing it requires a small product change, not only a test.

## Current State Analysis

- `gpx/signals.py`'s two receivers (`post_delete`, `pre_save`) are the only
  code that removes a `.gpx` file from storage, and `tests/gpx/test_gpx_signals.py`
  already exercises both across every path except a two-level cascade.
- `reconcile_media.py:218` spares a file when `modified > cutoff`; the exact
  equality case (a file aged to precisely the cutoff) has no test.
- `trips/views.py:84-100` (`TripDetailView.get_context_data`) builds `track`,
  `map_config`, and `stats` entirely from stored columns — none of the three
  ever touches storage. `trips/templates/trips/trip_detail.html:66-69`
  unconditionally renders a `Track:` line and a live-looking `Download` link.
  `gpx:download` already 404s on a storage miss (`gpx/views.py:140-153`,
  tested), but nothing on the detail page itself distinguishes a healthy track
  from one whose file is gone.

## Desired End State

- Deleting a `User` (cascading through their `Trip`s into their `GpxTrack`s)
  reclaims every track file, proven by a direct test starting from
  `User.objects...delete()`.
- `reconcile_media` treats a file aged to exactly the cutoff as an orphan
  (matching its documented strict `>` comparison), proven by a test that
  controls both `cutoff` and `modified` precisely.
- A trip whose track row survives but whose file is missing from storage
  renders a visible "track file unavailable" marker and disables the download
  link (plain text, no `href`), instead of looking healthy. `gpx:download`'s
  existing 404 behavior is unchanged.
- `test-plan.md` §6.3, §6.5, and §6.7 are filled in with this phase's patterns.

### Key Discoveries:

- `tests/gpx/conftest.py:31` (`trip` fixture) already depends on a `rider`
  fixture — a two-level cascade test can reach the owner via `trip.owner_id`
  or the `rider` fixture directly, no new fixture needed.
- `tests/gpx/test_reconcile_media.py:31-40` (`back_date`) moves a real file's
  mtime by writing to disk with `os.utime` — real-clock timing makes hitting
  an *exact* equality boundary unreliable via `back_date` alone; the existing
  file already monkeypatches `default_storage.get_modified_time` for a
  different edge case (`tests/gpx/test_reconcile_media.py:368-375`), which is
  the mechanism to reuse here to pin `modified` to the exact computed cutoff.
- `tests/trips/test_trip_detail.py` already establishes the response-body
  assertion pattern (`assert "..." in response.content.decode()`) this
  phase's new detail-page test should follow.

## What We're NOT Doing

- Not adding a dedicated test for the admin's default "delete selected
  tracks" bulk action — research found it structurally subsumed by existing
  `QuerySet.delete()`/cascade coverage, and admin CRUD is explicitly excluded
  scope per test-plan.md §7.
- Not adding caching, background reconciliation, or any deferred/async check
  for the new storage-presence check — a single `storage.exists()` call per
  detail-page render is accepted as-is at this project's scale.
- Not introducing a new exception type for "file missing from storage" —
  the existing `OSError` handling in `gpx:download` stays as-is; the detail
  page's new check is a presence probe, not an error-handling change.
- Not touching `gpx/statistics.py`, `gpx/map_config.py`, or the backfill
  command — all three are already correctly decoupled from file presence and
  already tested for their own storage-miss behavior.

## Implementation Approach

Three phases, in dependency order: close the two residual Risk #1 test gaps
first (pure test additions, no product code, fastest to land and rebase
against), then the Risk #3 product change plus its test (touches
`trips/views.py` and `trips/templates/trips/trip_detail.html`), then the
mandatory cookbook update that documents both patterns for future
contributors.

## Phase 1: Two-level cascade and reconcile_media boundary tests

### Overview

Close the two remaining Risk #1 gaps identified by research. Both are
additive test-only changes against code that does not change.

### Changes Required:

#### 1. Two-level `User → Trip → GpxTrack` cascade test

**File**: `tests/gpx/test_gpx_signals.py`

**Intent**: Prove deleting a `User` cascades through their `Trip` into their
`GpxTrack` and still reclaims the track's file — the one cascade depth the
existing suite (`test_a_trip_queryset_cascade_removes_the_track_files_it_never_loaded`)
does not reach.

**Contract**: New test function, same file, same fixtures and assertion shape
as its `Trip`-level sibling immediately above it: create a stored track via
`make_stored_track(trip)`, assert the file exists, delete via
`User.objects.filter(pk=trip.owner_id).delete()` inside
`django_capture_on_commit_callbacks(execute=True)`, then assert
`GpxTrack.objects.count() == 0` and `not default_storage.exists(name)`. Import
`User` from `django.contrib.auth.models` (not yet imported in this file).

#### 2. `reconcile_media` exact age-boundary test

**File**: `tests/gpx/test_reconcile_media.py`

**Intent**: Prove the documented strict `>` comparison at
`reconcile_media.py:218` — a file whose mtime equals the cutoff exactly is
treated as an orphan, not spared. A real-clock `back_date` cannot hit an exact
equality reliably (the cutoff is computed inside `handle()` at call time), so
this test freezes both sides of the comparison.

**Contract**: Monkeypatch `django.utils.timezone.now` to return a fixed
instant, write an orphan file, then monkeypatch `default_storage.get_modified_time`
for that key to return exactly `fixed_now - timedelta(minutes=ORPHAN_MIN_AGE_MINUTES)`
— i.e. equal to the cutoff the command will compute for its default
`min_age`. Run `call_command("reconcile_media")` and assert the key appears in
the orphan report (`"Orphan {key}"` in `captured.err`), following the existing
`monkeypatch.setattr(default_storage, "get_modified_time", ..., raising=True)`
idiom already used at `tests/gpx/test_reconcile_media.py:368-375`.

### Success Criteria:

#### Automated Verification:

- New tests pass: `uv run pytest tests/gpx/test_gpx_signals.py tests/gpx/test_reconcile_media.py`
- Full suite passes with coverage: `uv run pytest --cov`
- Lint, format, import order, strict typing: `/python-quality-gates`

#### Manual Verification:

- Temporarily invert the `>` to `>=` in `reconcile_media.py:218`, confirm the
  new boundary test goes red, then revert — proving the test bites (per
  test-plan.md §6.2's "prove the test bites" discipline, applied here to a
  non-route test).

---

## Phase 2: Deliberate storage-miss marker on the trip detail page

### Overview

Close the Risk #3 gap: give the trip detail page a way to show that a track's
file is missing from storage, instead of rendering as if it were healthy.

### Changes Required:

#### 1. Storage-presence check in the detail view

**File**: `trips/views.py`

**Intent**: Compute whether the current track's file actually exists in
storage, alongside the existing `track`/`map_config`/`stats` context the view
already builds — all from stored data, this is the one addition that touches
storage.

**Contract**: In `TripDetailView.get_context_data`, add
`context["track_file_available"]`: `False` when there is no track or its
stored file name is empty (covers the "never stored" row shape the suite
already fixtures), otherwise `track.file.storage.exists(track.file.name)`.
Compute this once per render; no new imports beyond what `FieldFile` already
exposes.

#### 2. Deliberate marker and disabled download link

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: When a track exists but its file is unavailable, show a visible
notice and stop offering a link that would only 404, following the same
"deliberate state, worded to name its own cause" convention the map-fallback
and stats-not-computed branches already use just above and below this spot.

**Contract**: Inside the existing `{% if track %}` block, guard the
`Track: …` / `Download …` paragraph pair (currently lines 66-69) on
`track_file_available`: when true, render exactly as today; when false,
render a `<p>` naming the fault (e.g. "Track file unavailable — the stored
file could not be found.") and replace the download link with plain text
(no `<a href>`), so nothing on the page still looks clickable to a dead
route. No change to `gpx:download` itself.

### Success Criteria:

#### Automated Verification:

- New test(s) pass: `uv run pytest tests/trips/test_trip_detail.py`
- Full suite passes with coverage: `uv run pytest --cov` (the coverage gate,
  `fail_under = 80`, must still pass with the new branch in `trips/views.py`
  and the new template branch both exercised)
- Lint, format, import order, strict typing: `/python-quality-gates`

#### Manual Verification:

- Upload a track to a trip, then delete its file directly from the
  `MEDIA_ROOT` directory on disk (bypassing the app, simulating an
  out-of-band loss) and reload the trip detail page in a browser — confirm
  the marker renders and the download link is no longer a live link, while
  the map and stats sections still render from stored data as before.

#### 3. New test: the detail page's storage-miss behavior

**File**: `tests/trips/test_trip_detail.py` (or a new sibling file if the
existing file's fixtures don't already support removing a stored file —
follow whichever the codebase's existing convention favors once written)

**Intent**: Prove the actual claim Risk #3 makes: a row with computed
statistics and a track whose file has vanished from storage does not render
as healthy.

**Contract**: `test_a_rider_sees_a_deliberate_marker_when_the_track_file_is_missing`
— build a trip with `make_stored_track`, delete the underlying file directly
via `default_storage.delete(name)` (not `track.delete()`, which would remove
the row too — this test needs the row to survive), request the detail page,
and assert: response is `200`, the marker text is present, and the download
`href` for `gpx:download` with that track's pk is absent from the body (the
link text may remain as plain text, but not as an `<a href=...>`). Pair with
a companion happy-path test (or extend an existing one) asserting
`track_file_available` is `True` and the live download link is present when
the file exists — the "both branches" discipline test-plan.md §6.2 already
established for the ownership matrix applies here too.

---

## Phase 3: Cookbook update

### Overview

Mandatory per test-plan.md's rollout convention: each phase's final sub-phase
updates the relevant §6 cookbook entries so `/10x-tdd` (Lesson 2) has a real
worked example, not a placeholder.

### Changes Required:

#### 1. Fill in §6.3 and §6.5, add a §6.7 phase-notes entry

**File**: `context/foundation/test-plan.md`

**Intent**: Replace the two `TBD — see §3 Phase 2` placeholders with the real
location/naming/reference-test/run-command answers this phase produced, and
record anything this phase learned that the existing §6 entries don't already
carry.

**Contract**:
- §6.3 ("Adding a test for a post-commit side effect"): location
  `tests/gpx/test_gpx_signals.py`, naming `test_<trigger>_removes_<what>`,
  reference test `test_a_trip_queryset_cascade_removes_the_track_files_it_never_loaded`
  (existing) plus this phase's new
  `test_a_user_queryset_cascade_removes_the_track_files_two_levels_down`, run
  command `uv run pytest tests/gpx/test_gpx_signals.py -v`. Must restate the
  `django_capture_on_commit_callbacks(execute=True)` requirement already
  established in the file's own module docstring.
- §6.5 ("Adding a test for a management command"): location
  `tests/gpx/test_reconcile_media.py`, naming pattern following the file's
  existing `test_a_<condition>_is_<outcome>` convention, reference test the
  new exact-boundary test, run command
  `uv run pytest tests/gpx/test_reconcile_media.py -v`, and a note that a
  boundary condition tied to `timezone.now()` needs `timezone.now` and the
  storage backend's modified-time both monkeypatched together, not a
  real-clock `back_date`.
- §6.7: one new bullet under a `**Phase 2 — File lifecycle and
  storage/row consistency.**` heading, following the existing Phase 1 bullet
  format, naming the one substantive lesson: statistics and map data are
  stored columns deliberately decoupled from file presence, so proving Risk
  #3 required adding the one storage read the render path did not previously
  have, not fixing a bug in the existing decoupling.

### Success Criteria:

#### Automated Verification:

- `test-plan.md` still parses as valid Markdown with no broken table/section
  structure (visual check via `git diff`, no gate runs Markdown lint on this
  file today)

#### Manual Verification:

- A reader following only §6.3/§6.5 (without reading this plan) can find the
  right file, naming convention, and run command to add a similar test.

---

## Testing Strategy

### Unit Tests:

- N/A for this phase — every change here is either an integration test
  against the full request/ORM stack, or a management-command test through
  `call_command`.

### Integration Tests:

- Phase 1: cascade deletion through the ORM (`User` → `Trip` → `GpxTrack`),
  and `reconcile_media`'s command-level behavior at an exact time boundary.
- Phase 2: the trip detail page's rendered response, in both the healthy and
  storage-miss states.

### Manual Testing Steps:

1. Invert `reconcile_media.py:218`'s `>` to `>=`, confirm the new boundary
   test fails, then revert.
2. Upload a GPX file to a trip, delete the stored file directly from
   `MEDIA_ROOT`, reload the trip detail page, and visually confirm the
   marker and disabled download link.
3. Confirm `gpx:download` for that same track still 404s as before (no
   regression to the existing behavior).

## Performance Considerations

One additional `storage.exists()` call per trip-detail render when a track is
present — a single filesystem `stat` at this project's scale (per the
confirmed design decision), no caching added.

## Migration Notes

No schema or data migration — `track_file_available` is computed at render
time, never persisted.

## References

- Research: `context/changes/testing-file-lifecycle-storage-consistency/research.md`
- Existing cascade test to mirror:
  `tests/gpx/test_gpx_signals.py:78-99`
  (`test_a_trip_queryset_cascade_removes_the_track_files_it_never_loaded`)
- Existing monkeypatch idiom to mirror for the boundary test:
  `tests/gpx/test_reconcile_media.py:351-381`
- Existing deliberate-empty-state template pattern to mirror:
  `trips/templates/trips/trip_detail.html:58-64` and `:116-123`
- Existing storage-miss download test:
  `tests/gpx/test_gpx_download.py:96-113`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Two-level cascade and reconcile_media boundary tests

#### Automated

- [x] 1.1 New tests pass: `uv run pytest tests/gpx/test_gpx_signals.py tests/gpx/test_reconcile_media.py` — 7eaf08a
- [x] 1.2 Full suite passes with coverage: `uv run pytest --cov` — 7eaf08a
- [x] 1.3 Lint, format, import order, strict typing: `/python-quality-gates` — 7eaf08a

#### Manual

- [x] 1.4 Invert the `>` to `>=` in `reconcile_media.py:218`, confirm the new boundary test goes red, then revert — 7eaf08a

### Phase 2: Deliberate storage-miss marker on the trip detail page

#### Automated

- [x] 2.1 New test(s) pass: `uv run pytest tests/trips/test_trip_detail.py` — 4ae92ed
- [x] 2.2 Full suite passes with coverage: `uv run pytest --cov` — 4ae92ed
- [x] 2.3 Lint, format, import order, strict typing: `/python-quality-gates` — 4ae92ed

#### Manual

- [x] 2.4 Delete a stored track's file on disk, reload the trip detail page, confirm the marker renders and the download link is no longer live — 4ae92ed

### Phase 3: Cookbook update

#### Automated

- [x] 3.1 `test-plan.md` still parses as valid Markdown with no broken table/section structure — 349fd13

#### Manual

- [x] 3.2 A reader following only §6.3/§6.5 can find the right file, naming convention, and run command to add a similar test — 349fd13
