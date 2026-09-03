<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Multi-stage GPX upload

- **Plan**: `context/changes/multi-stage-gpx-upload/plan.md`
- **Scope**: Phases 1-5 of 7 (Phases 6-7 are the plan's nominated cuttable tail, unimplemented by design)
- **Date**: 2026-09-03
- **Verdict**: NEEDS ATTENTION (as found) → **all 10 findings fixed in triage**
- **Findings**: 0 critical, 7 warnings, 3 observations — 9 fixed, 1 (F3) resolved by unchecking
  the criterion it belongs to

## Post-triage state

Every finding was acted on; nothing was skipped, dismissed or accepted as risk. Gates on the
finished state:

- `pytest --cov` — **367 passed, 2 skipped**, coverage 97.15% (was 360 / 97.13%)
- `pytest -m bite_proof` — 6 passed
- `pytest tests/test_assertion_strength.py` — 3 passed, no new waivers
- `ruff` / `black` / `isort` / `mypy --strict` / `manage.py check` — clean
- `makemigrations --check --dry-run` — no changes detected
- `collectstatic --noinput` — clean
- `migrate` from zero, and backward through `0004`/`0003` — clean, including over a seeded
  pre-`0004` row

Seven new tests landed (five for F2, one each for F4 and F8). Three of them were mutated to
prove they bite for their named reason before being kept, per `test-plan.md` §6.8's rule that
a guard which stays green is a broken guard.

**One item remains open by decision, not by oversight:** criterion 3.15's page-weight and
time-to-interactive measurement, now unchecked in the plan's Progress. It cannot be produced
from a review — it needs a real multi-day export uploaded and the page observed.

Two things surfaced that are **out of this change's scope** and want their own change:

1. `pytest -m bite_proof` reports all six shapes broken when `FORCE_COLOR` is set (see F2's
   decision). Pre-existing, CI unaffected, but it makes the credibility harness lie in the
   direction that matters least safely.
2. `isort` silently skips `tests/gpx/test_gpx_parsing.py` and `tests/gpx/test_gpx_statistics.py`
   on a charmap `UserWarning` over a `→` character, while still exiting 0 — a gate that skips
   files and reports success. Also pre-existing on `master` (verified).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

## What was verified green

Run in this review, all passing:

- `makemigrations --check --dry-run` — no changes detected
- `collectstatic --noinput` — 400 post-processed
- `SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= pytest --cov` — **360 passed, 2 skipped**, coverage 97.13% (`fail_under = 80`)
- `pytest -m bite_proof -v` — **6 passed**, including the new `upload_replaces_instead_of_adding` shape
- `ruff` / `black` / `isort` / `mypy --strict` / `manage.py check` — all clean

The change's stated riskiest property holds. `gpx/views.py:94-114`'s `form_valid` is now two
statements; the `transaction` import, the `select_for_update` read and the explicit-pk delete
are gone outright, and no delete of a `GpxTrack` row remains anywhere in the file. Both
`gpx/signals.py` receivers were correctly left untouched and are still correct under ADD:
`pre_save` returns at `:160-164` on `instance.pk is None` before any query, and
`test_pre_save_removes_nothing_when_a_sibling_stage_is_inserted` pins `callbacks == []` —
proving *nothing was scheduled*, which is strictly stronger than proving the file survived.
Every new file-presence assertion wraps its request in
`django_capture_on_commit_callbacks(execute=True)`.

Security is clean on every dimension checked: both `build_stages` call sites receive a trip
from an owner-scoped queryset (`trips/views.py:82`, `gpx/views.py:59,69-71`),
`ordered_stage_tracks` starts from `trip.tracks` so it inherits that scope by construction,
the per-stage download link targets the independently-scoped `gpx:download`, no new
`<int:pk>` route was added, `stage.color` is provably from a frozen constant tuple, and no
`|safe` / `mark_safe` / `autoescape off` was introduced.

Architecture is clean: `gpx/stages.py` is well-placed and the import direction is acyclic
(`map_config` → `stages` → `{availability, statistics, models, constants}`, both views → both).

## Findings

### F1 — AGENTS.md and `gpx/stages.py` document a derived trip span that does not exist

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: AGENTS.md:23, gpx/stages.py:5-7, gpx/stages.py:44-47
- **Detail**: All three name "the derived trip span" as a live consumer of
  `chronology_is_established`. `gpx/stages.py:5-7` says "the **three** consumers of the
  chronology claim — the page's wording, the stage-break markers, and the derived trip span".
  The span is Phase 7 (`plan.md:933`, marked *cuttable*), which was not implemented — a
  repo-wide grep finds the phrase only in these docstrings and in `roadmap.md:127` describing
  a parked capability. `Min`/`Max` appear nowhere. There are two consumers today, not three.
  This is `lessons.md` #5 ("AGENTS.md loads every session — a stale claim actively misdirects
  the next agent") and #11 ("a docstring is a claim the body must fully honour") in one
  sentence; the next agent will look for a third consumer that was never written.
- **Fix**: In `gpx/stages.py:5-7` say "the two consumers … the page's wording and the
  stage-break markers"; reword `:44-47`'s `Min`/`Max` clause as a *forward* constraint ("if a
  trip span is ever derived, this predicate must gate it"); drop "and the derived trip span"
  from AGENTS.md:23 or mark it as a constraint on future work.
- **Decision**: FIXED via Fix now — `gpx/stages.py:5-8` now says "the two consumers … the page's wording and the stage-break markers" and names the span as Phase 7, cut; `chronology_is_established`'s docstring reframes the `Min`/`Max` clause as a forward constraint ending "Nothing derives a span today"; `AGENTS.md` names the two claims and states no span is derived anywhere.

### F2 — The plan's documented recovery path for null instants does not exist as shipped

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: plan.md:1096-1097, gpx/statistics.py:49-54
- **Detail**: `plan.md:1096-1097` states: "If Phase 6 is cut, `0004` ships alone and existing
  rows keep null instants — legal, handled by the ordering expression, and **re-fillable later
  by the command**." Phase 6 is not implemented, and the command cannot refill them.
  `backfill_track_statistics` saves `update_fields=list(STATS_FIELDS)`, and `STATS_FIELDS`
  (`gpx/statistics.py:49-54`) is the four statistics columns only — `started_at` / `ended_at`
  are absent. Phase 6 §1 (`plan.md:848-850`) is where the tuple "grows to include them"; that
  growth never happened. So as shipped, pre-`0004` rows have permanently null instants with no
  fill path at all: not the migration (cut), not the command (doesn't write those columns), not
  re-upload (that adds a stage rather than refilling one). The consequence the plan itself
  names (`plan.md:835-837`) is that **US-02's own scenario — an existing trip gaining a second
  stage — can never establish chronology**: such a trip permanently renders "Stages are shown
  in upload order" and draws no break markers, however many timed stages are added after.
  Production measured 4 such rows (`roadmap.md` E-11). Every code branch handles the null case
  correctly; what is wrong is the written recovery story, which is what makes cutting Phase 6
  look safe when it is not.
- **Fix A ⭐ Recommended**: Correct `plan.md:1096-1097` to say instants are *not* re-fillable by
  the current command, and that Phase 6 (or a standalone widening of `STATS_FIELDS`) is required
  — then open a backlog/roadmap row for the 4 production rows.
  - Strength: Keeps Phase 6 intact as a phase rather than smuggling half of it in, and makes the
    cut decision an informed one. The user-visible degrade is already correct and tested.
  - Tradeoff: The 4 existing rows stay chronology-less until Phase 6 or the backlog row lands.
  - Confidence: HIGH — verified directly: `STATS_FIELDS` has four entries and
    `grep started_at` finds no reader in `gpx/statistics.py`.
  - Blind spot: Whether the owner considers 4 rows worth a backlog row at all, versus just
    re-creating those trips by hand.
- **Fix B**: Pull Phase 6 §1 forward now — add both instants to `STATS_FIELDS` so the command's
  `--all` genuinely refills them.
  - Strength: Makes the existing sentence true and closes the US-02 gap immediately.
  - Tradeoff: `STATS_FIELDS` is load-bearing in three places by design — the helper's
    `update_fields`, migration `0003`'s `.only(...)` narrowing, and the command's narrowing.
    `0003` has already run; widening the tuple changes what it narrows on replay. That coupling
    is exactly why the plan made this a phase with its own migration and tests.
  - Confidence: MEDIUM — the edit is one tuple, but its three consumers each need re-verifying,
    and Phase 6's own success criteria (6.1-6.6) would go unrun.
  - Blind spot: Have not traced whether `0003`'s recorded state makes a replay under the widened
    tuple behave differently in practice.
- **Decision**: FIXED via Fix B — and that blind spot turned out to be a hard break, so it took
  three edits rather than one.

  **The blind spot, resolved by experiment.** The one-tuple version of Fix B fails `migrate`
  outright on any fresh database:

  ```
  django.core.exceptions.FieldDoesNotExist: GpxTrack has no field named 'started_at'
  ```

  `0003:69` narrowed with `.only("id", "file", *STATS_FIELDS)` — importing a **live** constant
  into a migration that runs at `0002`'s schema state. The raise comes out of
  `pending.iterator()`, *outside* the per-row guard, so the unattended `migrate` at container
  boot dies with it. Pinning `0003` alone was not enough either: the helper's
  `save(update_fields=list(STATS_FIELDS))` would then raise `ValueError` per row, be swallowed
  by `0003`'s broad catch, and silently reduce that migration to logged skips — `migrate`
  printing OK having filled nothing, the exact failure shape `0003`'s savepoint comment exists
  to prevent.

  **What landed:**
  1. `gpx/statistics.py` — `STATS_FIELDS` grew to six; `backfill_track_statistics` writes both
     instants; new `_writable_stats_fields(track)` builds `update_fields` from the row's *own*
     model, so the shared helper is safe under either schema state. Module docstring and the
     helper's `Args` corrected — both had claimed the four-column shape.
  2. `gpx/migrations/0003_backfill_gpxtrack_stats.py` — pins `STATS_COLUMNS_AT_0002` and no
     longer imports `STATS_FIELDS`. **This fixes a latent trap that predates this change**: the
     import was already wrong on `master`, the tuple just had not grown yet.
  3. Five new tests in `tests/gpx/test_gpx_statistics.py` — both instants filled from a stored
     timed file; both left null for an untimed one; `--all` refills instants on an
     already-filled row; and two guards built on the *real* migration graph
     (`MigrationExecutor.loader.project_state(("gpx", "0002_gpxtrack_stats"))`) asserting that
     `_writable_stats_fields` narrows against the historical model and that the pin matches the
     state it claims. That module's own docstring says `0003`'s loop is unreachable under
     `pytest`; these reach the *reason* it would break instead.
  4. `plan.md` Migration Notes and the `AGENTS.md` command row amended.

  **Verified, not assumed:**
  - `_writable_stats_fields` mutated to `return list(STATS_FIELDS)` → the new guard fails,
    naming `started_at` as the first extra item. It bites, for the named reason.
  - Seeded a genuine pre-`0004` row by raw SQL at `0002` state (confirmed the table lacked both
    columns), then migrated forward: `0003` applied OK and filled `distance=3661.09`,
    `duration=3600.0`, instants left null — correct, the columns did not exist yet.
  - `backfill_gpx_stats --all` then filled `started=2026-06-01 08:00+00:00`,
    `ended=2026-06-01 09:00+00:00`. The recovery path the plan promised now exists.
  - The default run afterwards reported `Filled 0, skipped 0.` — still converges, the property
    Phase 6 §3 refuses to trade away.
  - `migrate` also runs *backward* through `0004` and `0003` cleanly.
  - Full gates: 365 passed / 2 skipped, coverage 97.15%; `ruff` / `black` / `mypy --strict` /
    `manage.py check` / migration guard clean; `pytest -m bite_proof` 6 passed.

  **Harness note found while verifying** (not caused by this change, not a finding against it):
  `pytest -m bite_proof` fails all six shapes when `FORCE_COLOR` is set in the environment. The
  subprocess colourizes its output, so each shape's plain-string `fragment` no longer matches
  the ANSI-wrapped source line, and every shape reports "guard failed, but not for the named
  reason". Confirmed pre-existing by stashing every edit and reproducing on the untouched
  baseline. CI sets no `FORCE_COLOR`, so CI is unaffected — but the harness then reports absent
  protection for protection it actually has, which deserves its own change: strip ANSI from the
  captured output before matching, or pass `--color=no` to the subprocess.

### F3 — Criterion 3.15 is checked, but the measurement it exists to record was never written down

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: plan.md:1175, gpx/constants.py:16-22
- **Detail**: Progress item 3.15 — "Measurement: record a real multi-day tour's page weight and
  time-to-interactive; open a backlog row if unacceptable" — is marked `[x] — ac6ff25`. The
  criterion's entire deliverable is a recorded number, and no number exists anywhere:
  `gpx/constants.py:16-22` still reads verbatim "Provisional: calibrated against that synthetic
  worst case …, **not yet against a real multi-day tour export**"; `plan.md:1073-1075` still says
  in the future tense "this change is what produces that calibration"; no Engineering Backlog row
  was opened; `roadmap.md` carries no figure. Unlike the other manual items (visual checks that
  leave no artifact by nature), this one's output *is* an artifact. Marked complete with nothing
  to show is the rubber-stamping shape this dimension exists to catch.
- **Fix**: Either run the measurement and record the two figures in `gpx/constants.py:16-22`
  (replacing the "not yet" clause), or uncheck 3.15 and carry it as the one open item.
- **Decision**: FIXED via unchecking — 3.15 is back to `- [ ]` in the plan's Progress, annotated with what is missing (`gpx/constants.py:16-22` still says "not yet", no backlog row) and named as the one criterion outstanding across Phases 1-5. Not measurable from here: it needs a real multi-day export uploaded and the page observed.

### F4 — `timed-track-day-2.gpx` was created for a test that was never written

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: tests/gpx/fixtures/timed-track-day-2.gpx
- **Detail**: The fixture's content matches Phase 1 §5's contract exactly (well-formed GPX 1.1,
  `<time>` on 2026-06-02T08:00–09:00Z against `timed-track.gpx`'s 2026-06-01, coordinates
  49.55/49.45/49.30 disjoint from 50.06/50.07/50.05). But a repo-wide grep finds **zero
  references** outside the plan docs. Every ordering test hand-sets the columns through
  `GpxTrack.objects.create` instead — `tests/gpx/test_stages.py:44-57`,
  `tests/trips/test_trip_detail_map.py:96-150`. The plan justified the fixture on the grounds
  that "without a *second* timed fixture the ordering feature ships unexercised … so a test can
  upload it *first* and prove ride order beats upload order".

  Mitigating: the ORM-level tests *do* construct in reverse order (day-2 created first, asserted
  back day-1-first), so they genuinely discriminate against `uploaded_at` ordering, and
  `tests/gpx/test_gpx_upload.py:108-126` proves the upload path fills the column. The chain is
  covered in two halves. What no test covers is the whole path end to end: upload → `clean_file`
  → `started_at` → `ordered_stage_tracks`. Criterion 2.3 ("uploaded in reverse ride order") is
  met by construction, not by upload.
- **Fix**: Add one test uploading `timed-track-day-2.gpx` then `timed-track.gpx` and asserting
  `[t.original_filename for t in ordered_stage_tracks(trip)]` comes back day-1 first — or delete
  the fixture and accept the ORM-level coverage.
- **Decision**: FIXED via Write the missing test — `test_two_uploads_in_reverse_ride_order_come_back_in_ride_order` in `tests/gpx/test_gpx_upload.py` uploads `timed-track-day-2.gpx` **first**, then `timed-track.gpx`, through the real form, and asserts `ordered_stage_tracks` returns day 1 first, both `started_at` values, and `chronology_is_established`. The fixture Phase 1 §5 added is now used for the purpose it was added for. **Verified to bite**: dropping the `started_at` term from `ordered_stage_tracks` fails it with "stages came back in upload order rather than ride order". Recorded as a Phase 2 §6 plan addendum.

### F5 — `GpxTrack`'s class docstring still asserts the one-track-per-trip rule this change repealed

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: gpx/models.py:22-25
- **Detail**: "The FK is deliberately many-tracks-per-trip so FR-011 needs no migration rewrite,
  **even though v1 behaviour keeps exactly one track per trip.**" The final clause is precisely
  what this change repealed. Same `lessons.md` #5/#11 shape as F1, one file over — and the plan
  invoked #11 four separate times as a thing to avoid.
- **Fix**: Drop the "even though v1 behaviour keeps exactly one track per trip" clause.
- **Decision**: FIXED via Fix both now — `GpxTrack`'s docstring drops the repealed clause and now states that every upload adds a stage, with `gpx/stages.py` owning their order.

### F6 — A test docstring still names the retired `track_file_available` context key

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/trips/test_trip_detail.py:98
- **Detail**: "Both branches of `track_file_available` need their own assertion…" — the assertion
  below it was correctly moved to `response.context["stages"][0].file_available`, but the
  docstring still names the deleted key. This is the last surviving read of the retired shim
  anywhere in the repo (the mutation shape's `fragment` was correctly requoted at
  `tests/mutations.py:168`), so it is one word from clean.
- **Fix**: Change `track_file_available` to `stage.file_available` in the docstring.
- **Decision**: FIXED via Fix both now — the docstring reads "Both branches of a stage's `file_available`", matching the assertion beneath it. No read of the retired shim survives anywhere in the repo.

### F7 — An unplanned test deletion: `test_a_cleanup_failure_does_not_fail_an_upload_that_already_committed`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: tests/gpx/test_gpx_upload.py (master ~:386)
- **Detail**: Phase 2 §6 names exactly two tests to touch — the replace test (rewritten) and the
  cross-trip isolation test (expectations changed). This third test was removed outright with no
  plan clause covering it. The removal is defensible: it monkeypatched `FileSystemStorage.delete`
  to prove a failing deferred delete didn't 500 an already-committed upload, and the upload path
  no longer schedules a delete. The equivalent signal-level guard survives untouched
  (`tests/gpx/test_gpx_signals.py:514
  test_a_cleanup_failure_does_not_fail_a_replacement_that_already_committed`), so no coverage was
  actually lost. Flagged because a test deletion is the class of change a plan should authorise
  explicitly rather than have discovered at review.
- **Fix**: Record the deletion and its reason as a one-line plan addendum under Phase 2 §6.
- **Decision**: FIXED via plan addendum — Phase 2 §6 now records the deletion of `test_a_cleanup_failure_does_not_fail_an_upload_that_already_committed`, why it had no subject left once the upload path stopped scheduling a delete, and that the same guarantee for the path that still does is asserted by `tests/gpx/test_gpx_signals.py::test_a_cleanup_failure_does_not_fail_a_replacement_that_already_committed`.

### F8 — `STAGE_COLORS` cycling is never exercised

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: gpx/stages.py:82, tests/trips/test_trip_detail_map.py:149
- **Detail**: `STAGE_COLORS[index % len(STAGE_COLORS)]` is documented in three places as "stage 7
  reuses stage 1's colour", but the palette has six hues and the deepest test builds three stages
  (`assert colours == list(STAGE_COLORS[:3])`). Nothing exercises the modulo. Changing `%` to
  plain indexing would raise `IndexError` on a seven-stage trip and every test would stay green.
  `build_stages` also has no direct unit test — `tests/gpx/test_stages.py` covers
  `ordered_stage_tracks` and `chronology_is_established` only, so the `number`/`color`/`stats`/
  `file_available` assembly is pinned solely at the HTTP layer. Both gaps close with one test.
- **Fix**: Add a `build_stages` unit test over seven stages asserting `stages[6].color == STAGE_COLORS[0]`.
- **Decision**: FIXED via Fix now — `test_build_stages_numbers_from_one_and_cycles_the_palette` in `tests/gpx/test_stages.py` builds seven stages and asserts `stages[6].color == STAGE_COLORS[0]`, the full six-hue sequence before it, 1-based numbering, and per-stage `file_available`. Also the first direct unit test of `build_stages`' assembly. **Verified to bite**: replacing `% len(STAGE_COLORS)` with plain indexing fails it with `IndexError: tuple index out of range` at `gpx/stages.py:88`.

### F9 — `map.js`'s all-or-nothing catch now costs the whole tour, not one route

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: gpx/static/gpx/map.js:39-151
- **Detail**: The single `try` now wraps three loops instead of two fixed calls. A throw anywhere
  inside — a malformed `segment.points`, or `icons[marker.kind]` resolving `undefined` for an
  unrecognised kind (Leaflet then calls `.createIcon()` on `undefined`) — aborts before
  `fallback.parentNode.removeChild(fallback)` at `:117`, so **all N stages** fall to "The map
  could not be loaded", not just the bad one. Under single-track semantics one bad payload cost
  one route; now it costs a whole tour.

  Not currently reachable: `build_map_config` emits exactly the three kinds it builds icons for,
  skips point-less stages at `map_config.py:46` rather than aborting, and derives bounds from
  non-null columns. The file's header does document the all-or-nothing contract in general terms
  — but the *widened* radius is neither documented at `:143-150` nor guarded.
- **Fix A ⭐ Recommended**: Note the widened radius in the `catch` comment, so the next reader
  knows one bad stage costs every stage.
  - Strength: The all-or-nothing contract is deliberate and the payload is server-validated;
    documenting matches the file's existing discipline of explaining each choice in place.
  - Tradeoff: Leaves the behaviour as-is — a future payload change could make it reachable.
  - Confidence: HIGH — the three guards in `map_config.py` are verified present.
  - Blind spot: None significant.
- **Fix B**: Move the per-segment and per-marker bodies inside their own `try` so a bad stage is
  skipped and its siblings still draw.
  - Strength: Mirrors the server-side discipline `map_config.py:46` already applies to
    point-less stages, and degrades per stage rather than per page.
  - Tradeoff: Adds two nested try blocks to a file whose single-catch simplicity is itself
    documented as a decision; a partially-drawn map with no explanation may read as a bug.
  - Confidence: MEDIUM — depends whether a silently-missing stage is better or worse than an
    explicit whole-map fallback, which is a product call.
  - Blind spot: Haven't checked how `fitBounds` behaves if bounds reference a stage that failed to draw.
- **Decision**: FIXED via Fix A — `map.js`'s `catch` comment now states that the radius is a whole tour rather than one route since the payload went multi-stage, names the two throws that would reach it, records why all-or-nothing is preferred to a partially drawn tour, and points a future fix at `gpx/map_config.py` (or per-loop wrapping) rather than at widening what the catch tolerates.

### F10 — `build_stages` does N storage round-trips per render, unnamed in the plan's Performance Considerations

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: gpx/stages.py:78-87, gpx/availability.py:27
- **Detail**: `build_stages` calls `track_file_is_available(track)` once per stage, and that
  helper does hit storage: `return track.file.storage.exists(track.file.name)`. An N-stage trip
  performs N `storage.exists()` calls per page render, on both the detail path and the
  rejected-upload re-render. At current scale that is `os.path.exists` on a local volume —
  microseconds, and the honest price of the per-stage `file_available` accuracy that
  `test_a_missing_stage_file_renders_unavailable_while_siblings_keep_live_links` proves is worth
  having. There is no DB N+1: `gpx/stages.py:77` does `list(ordered_stage_tracks(trip))` — one
  query, one materialisation — and both views call `build_stages` once and pass the tuple on.

  The gap is documentary. `plan.md:1067-1080` covers only payload size and claims "neither the
  map box nor the statistics cost anything per point" — the per-stage I/O is the one per-stage
  cost in the render path and the one the section omits. It becomes a per-page network fan-out
  the day `MEDIA_ROOT` moves to an object store.
- **Fix**: Add a line to the plan's Performance Considerations naming the N storage calls and the
  local-filesystem assumption that makes them acceptable, so a storage-backend change has a
  written trigger.
- **Decision**: FIXED via Fix now — the plan's Performance Considerations now names the N `storage.exists()` calls per render, accepts them under `FileSystemStorage`, flags the object-store backend (not the stage count) as the assumption to watch, and states explicitly that there is no DB N+1 to confuse it with.

## Notes and nits (not findings)

- `MARKER_ICON` / `MARKER_ICON_RETINA` (`gpx/constants.py:65-66`) have no production consumer
  after Phase 5, but are still asserted collectable by `tests/test_static_references.py:53-54` —
  a test proving two unreferenced vendored PNGs survive `collectstatic`. Phase 5 §2 said "beside
  `MARKER_ICON`", so retaining them is not a contract breach; a one-line comment saying they are
  the deliberate fallback pin would settle it.
- `ended_at` is written but read by nothing. Deliberate forward-compat for the cut Phase 7 and the
  parked roadmap item, coherent because of the both-or-neither invariant at `gpx/parsing.py:132-133`,
  and asserted by `test_a_timed_upload_stores_its_first_and_last_gps_instants`. No action.
- `tests/trips/test_trip_detail_stats.py:39,280` — `DETAIL_PAGE_QUERIES = 4` is asserted against a
  single-stage trip only. It still passes correctly (`build_stages` adds no query), but no longer
  guards what its docstring says: a per-stage deferral regression would cost N and this test would
  still see 4. Parametrizing over one and three stages, same count, is one line.
- `trip_confirm_delete.html:19,23,25` — `trip.tracks.exists` then `trip.tracks.count` twice is
  `EXISTS` + `COUNT` + `COUNT`; templates don't memoize. Trivial on a page rendered once per delete.
- `trip_detail.html:115,176` — a stage whose file is missing renders its filename twice (bare, then
  "(download unavailable)"). Literal reading of the contract; just reads oddly on that one branch.
  The old `Track: ` prefix was dropped, which the plan did not require either way.
- `stage-start.svg` / `stage-finish.svg` — the drawn tip sits at y≈39.8 while `iconAnchor` is
  `[12, 41]`, so the pin floats ~1.2px above its coordinate. Leaflet's own PNG carries the same
  slack; noted only because criterion 5.6 says "exactly".
- `stage-break.svg:7` — the stem path has no `fill="none"`; zero-area today, so nothing renders
  wrong, but it relies on that.
- Phase 2's commit message (`92940a0`) does not carry the statement the plan asked for — "state in
  the commit message that the block was removed because the multi-statement write it guarded no
  longer exists, and that the storage-write orphan window it never covered is still covered by
  `reconcile_media`", per E-11's deliberate-reopening trigger (`roadmap.md:247`). The substance is
  recorded in full at `gpx/views.py:99-107`, which is arguably the better home, so this is noted
  rather than filed.
- `isort` skips `tests/gpx/test_gpx_parsing.py` and `tests/gpx/test_gpx_statistics.py` with a
  charmap `UserWarning` on a `→` character, so the import-order gate silently does not cover them.
  **Pre-existing on `master`** — verified — and therefore out of this review's scope, but worth its
  own change: a gate that skips files while exiting 0 is defeated.
- Working tree carries uncommitted edits to `plan.md` (commit-SHA annotations on the Phase 5
  checkboxes) at the time of review.
