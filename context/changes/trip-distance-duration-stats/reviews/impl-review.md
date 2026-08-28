<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Trip Distance and Duration Stats

- **Plan**: `context/changes/trip-distance-duration-stats/plan.md`
- **Scope**: Full plan — Phases 1–4 of 4 (all Progress items `[x]`)
- **Date**: 2026-08-28
- **Verdict**: NEEDS ATTENTION → **RESOLVED** (all 10 findings fixed; see per-finding decisions)
- **Findings**: 0 critical, 4 warnings, 6 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

**Plan Adherence** — every planned file exists with the planned contract; both
zero-versus-null gates are implemented exactly as specified, and every `None` assertion in
the new tests is `is None` rather than falsy. One minor drift (F9).

**Scope Discipline** — the changed-file set matches the plan's file set exactly. The only
unlisted additions are the two empty `__init__.py` files a management-command package
requires and the `TrackStatistics` carrier dataclass, which is a reasonable realization of
the plan's "extract the gating into a small module-level helper". No scope creep.

**Architecture** — `gpx/statistics.py` holding both the backfill helper (I/O, DB writes)
and the pure display builder is a departure from how the repo otherwise splits modules
(`gpx/map_config.py` pure, `gpx/signals.py` side-effecting), but the plan chose this
deliberately in Phase 2 §1 and Phase 3 §1, and `STATS_FIELDS` is a real shared coupling
between the halves. Sanctioned design, not drift.

**Success Criteria** — all automated verification re-run and green:

| Command | Result |
|---|---|
| `makemigrations --check --dry-run` | No changes detected |
| `manage.py check` | 0 issues |
| `SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= pytest --cov` | 200 passed, 98.61% coverage |
| `ruff` / `black --check` / `isort --check` / `mypy --strict` | all pass, 69 files |
| `collectstatic --noinput` + `pytest tests/test_static_references.py` | 8 passed |

Manual items are all `[x]`. The ones that can leave evidence in the diff do: `blank=True`
on all four columns backs 1.8, the `<dl>` markup backs 3.11, and the migration's logged
skip path backs 2.7. The rest (1.7, 2.6, 2.8, 3.7–3.10) require a human at a browser and
are accepted as attested. Commit ordering is clean against lessons.md #8 — the four phase
commits precede the epilogue that records their SHAs.

## Findings

### F1 — `save()` sits outside every guard, so one DB fault silently no-ops the whole backfill

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `gpx/statistics.py:104`, `gpx/migrations/0003_backfill_gpxtrack_stats.py:44-51`, `gpx/management/commands/backfill_gpx_stats.py:54`
- **Detail**: `backfill_track_statistics` deliberately keeps `track.save(update_fields=…)`
  (`statistics.py:104`) outside its own `try`, so the only exception class its callers can
  ever see from it is a save failure. Both callers handle that badly, and for the same
  root cause.

  In the migration, `Model.save_base` wraps the write in
  `transaction.mark_for_rollback_on_error` (verified at
  `.venv/…/django/db/models/base.py:957`), which sets `connection.needs_rollback = True`
  on any exception *before* re-raising — so the per-row `except Exception` at
  `0003:45` catches the error but cannot un-poison the transaction. Every subsequent row's
  `save()` then raises `TransactionManagementError`
  (`django/db/backends/base/base.py` `validate_no_broken_transaction`), which the same
  broad catch also swallows. The loop grinds through the remaining rows writing nothing,
  and `Atomic.__exit__` (`django/db/transaction.py:271`) sees `exc_type is None` with
  `needs_rollback` set, so it rolls the whole migration back **without raising**: `migrate`
  prints `OK` and exits 0 having written nothing. Django's docs warn against exactly this
  ("Avoid catching exceptions inside `atomic`").

  One mitigating fact, checked rather than assumed: `record_migration` runs *inside* the
  same atomic block (`django/db/migrations/executor.py:259`), so the recorder row rolls
  back too and `0003` replays on the next boot. The failure is a green, silent, no-op
  migration — not a permanently-lost one.

  In the command there is no guard at all (`backfill_gpx_stats.py:54`), so the same
  save failure aborts the run mid-way with an arbitrary prefix of rows filled and no tally
  printed — directly contradicting its own `handle` docstring ("it is a report rather than
  a crash"), which is the one operator path this command exists for.

  Trigger is remote on SQLite (locked database, disk full) and this project is SQLite-only,
  so likelihood is low; the structure is what's wrong, not today's behavior.
- **Fix A ⭐ Recommended**: Give each row its own savepoint in the migration
  (`with transaction.atomic():` inside the existing `try`, around the helper call) and wrap
  the command's helper call in `try/except Exception`, counting it as skipped.
  - Strength: An inner `atomic` creates a savepoint whose `__exit__` clears
    `needs_rollback`, so one bad row genuinely cannot poison the rest — which is what the
    comment at `0003:46-50` already claims the code does. Preserves the stated intent that
    "one bad row must not stop the deploy", and makes the command's docstring true.
  - Tradeoff: One savepoint per row (negligible at this project's scale); two small edits
    in two files rather than one.
  - Confidence: HIGH — the savepoint mechanism is read directly out of
    `django/db/transaction.py:277-289`, and the poisoning mechanism out of
    `models/base.py:957`.
  - Blind spot: Not exercised by a test — the suite runs migrations against an empty
    database, so this path stays unproven either way unless the helper is tested with a
    save that raises.
- **Fix B**: Let a database fault fail loudly — narrow the migration's catch so
  `DatabaseError` propagates, and add the command's guard.
  - Strength: A failed deploy is louder than a silent no-op, and the plan's own Migration
    Notes lean on visibility ("visible, not silent").
  - Tradeoff: Reverses the explicit design decision at `0003:46-50` that an unattended boot
    must not stop on one row; a single locked-database blip would then block the deploy.
  - Confidence: MEDIUM — correct mechanically, but it trades away a stated requirement.
  - Blind spot: Whether Railway's boot sequence retries a failed `migrate` at all.
- **Decision**: FIXED via Fix A — per-row savepoint in migration `0003`, plus a `try/except` around the command's helper call that counts the row as skipped (commit `63f6d2a`).

### F2 — A file with one elevated point renders "0 m" climbed — the exact string the gate exists to prevent

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `gpx/parsing.py:78-81`
- **Detail**: The elevation presence probe is
  `gpx.get_elevation_extremes().minimum is not None`, which a *single* elevated point
  satisfies. Probed against the installed gpxpy with a three-point track where only the
  middle point carries `<ele>`:

  ```
  elevation_extremes.minimum: 250.0        → gate passes
  get_uphill_downhill(): UphillDownhill(uphill=0, downhill=0)
  ```

  Those zeros are stored as real values and render as "0 m" gained and "0 m" lost. The
  plan anticipated partial files in "What We're NOT Doing" and accepted them on the grounds
  that "a subset-derived figure is an understated real number, not a fabricated one" — but
  that reasoning collapses at the degenerate case: with one elevated point the
  subset-derived figure *is* zero, indistinguishable from the fabricated zero the gate was
  built to stop. So this is a gap in the plan's own argument, not a coding slip. Barometric
  dropout is the realistic producer, though a file with exactly one surviving `<ele>` is
  unusual.
- **Fix A ⭐ Recommended**: Require at least two elevated points before trusting
  `get_uphill_downhill()` — count `point.elevation is not None` and gate on `>= 2`.
  - Strength: Restores the gate's actual promise (never report a climb figure the file
    cannot support) and closes the degenerate case without touching the accepted
    partial-file behavior for files with many elevated points. Two points is also the
    minimum from which any delta can be computed, so the threshold is principled rather
    than arbitrary.
  - Tradeoff: Needs a point count; cheapest place is the walk `parse_gpx` already performs,
    which means threading a value between two functions that are currently independent.
  - Confidence: HIGH — the failure is reproduced, and the fix is a strictly tighter gate.
  - Blind spot: Not verified whether the elevation walk and the existing point-extraction
    walk can share one pass without restructuring `parse_gpx`.
- **Fix B**: Accept it and narrow the plan's claim, adding a fixture that pins the current
  behavior so it is a documented decision rather than an untested one.
  - Strength: Zero production change; the case is genuinely rare and the number is not
    wrong so much as uninformative.
  - Tradeoff: Leaves "0 m climbed" on a page for a file that does carry elevation — the
    single user-visible defect the whole gating design was written against.
  - Confidence: MEDIUM — defensible, but it concedes the design's headline property.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — `_has_elevation_data` counts elevated points and gates on `MIN_ELEVATED_POINTS = 2`; both sides of the threshold pinned by tests (commit `68a0c11`).

### F3 — The page tells the rider a file "carried no timestamps" when it carried plenty

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/parsing.py:91-92`, `gpx/parsing.py:126`, `trips/templates/trips/trip_detail.html:92`
- **Detail**: `GPX.get_duration()` is `Optional[float]` and returns `None` whenever *any*
  segment's own duration is unavailable. Probed against the installed gpxpy with a
  two-segment file whose first segment is untimed and whose second runs 15:00→16:00:

  ```
  time_bounds.start_time: 2026-08-01 15:00:00+00:00   → gate passes
  get_duration(): None
  ```

  So `duration_seconds` is stored `None`. The stored data is fine — no bogus zero — but two
  statements about it are now false: `ParsedTrack.duration_seconds`'s docstring
  (`parsing.py:126`) says "`None` when no point in the file carried a `<time>`", and the
  template renders "Not recorded — the GPX file carried no timestamps" about a file that
  did. A partially-timed multi-segment export is an ordinary GPS-dropout artifact.
- **Fix**: Reword the docstring and the template note to "no usable timestamps" (or
  equivalent) so neither makes a false claim about the file's contents.
- **Decision**: FIXED — docstring and template both reworded to "no usable timestamps", with the multi-segment cause spelled out on `ParsedTrack.duration_seconds` (commit `6c64389`).

### F4 — The boot-time migration loads every `points` blob it never reads

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/migrations/0003_backfill_gpxtrack_stats.py:42`, `gpx/management/commands/backfill_gpx_stats.py:53`
- **Detail**: `for track in tracks.filter(distance_meters__isnull=True)` materializes the
  whole result set with full rows, including the `points` JSON blob — capped at
  `MAX_GPX_POINTS = 100_000`, roughly 15–20 MB per row once hydrated into a Python list of
  lists. This is the path that runs unattended at container boot on a memory-capped Railway
  dyno, and nothing in the loop reads `points`. The command does better with `.iterator()`
  but its default `chunk_size` of 2000 still holds up to 2000 whole rows resident. The
  plan's Performance Considerations waved at scale ("single-digit trips … negligible"),
  which is true today, but it costed the re-parse rather than the row residency.
- **Fix**: Add `.only("id", "file", *STATS_FIELDS).iterator()` in both places —
  `save(update_fields=…)` works on a deferred instance, and `points` is never touched.
- **Decision**: FIXED — `.only(...).iterator()` in both the migration and the command; `original_filename` kept loaded in the command because its skip line prints it (commit `9623a31`).

### F5 — The template gates on truthiness in a change whose whole thesis is `is None`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `trips/templates/trips/trip_detail.html:84, 92, 95, 98`
- **Detail**: `{% if stats.distance %}` is a falsy test where the contract says "when its
  field is `None`". It is safe today only because no formatter can return an empty string —
  `format_distance(0.0)` is `"0.0 km"`, `format_duration(0.0)` is `"0 min"`,
  `format_elevation(0.0)` is `"0 m"` — an accidental invariant standing in for the exact
  guarantee `build_trip_stats` documents structurally at `statistics.py:194-199`. One
  formatter edit away from collapsing a legitimate zero into "Not recorded". Note that
  `duration_seconds = 0.0` is genuinely reachable (a single-point *timed* file), so this is
  not a hypothetical value.
- **Fix**: Use `{% if stats.distance is not None %}` — Django's template `if` supports
  `is not` — so the guarantee is explicit rather than incidental.
- **Decision**: FIXED — all four template gates are `is not None`, with a test pinning the formatter invariant the truthiness gate had been leaning on (commit `efd2626`).

### F6 — The zero-new-queries property is claimed in three docstrings and pinned by nothing

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `gpx/statistics.py:182-211`, `tests/trips/test_trip_detail_stats.py`
- **Detail**: "The render path gains four column reads on a row it already fetches, and no
  new query" is a load-bearing claim of the plan's design (it is why stats are stored rather
  than re-parsed). It is true as written — `build_trip_stats` only does `getattr` over four
  already-loaded columns and never touches `track.file` — but the suite contains no
  `django_assert_num_queries` anywhere, so a future `.only()` on `tracks` or a deferred
  field would silently turn those four reads into four refresh queries per page view with
  no test failing.
- **Fix**: Add one `django_assert_num_queries` assertion on `TripDetailView` with a track
  present, in `tests/trips/test_trip_detail_stats.py`.
- **Decision**: FIXED — absolute-count query assertion on `TripDetailView`. Note the correction to the suggested fix: a delta against a stats-free baseline cannot see this regression, because deferral costs the null render as many refresh queries as the populated one. Verified by injecting a `.only()` on the track queryset — 4 queries becomes 13 (commit `b141023`).

### F7 — The `getattr` loop hides `STATS_FIELDS` from `mypy --strict`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `gpx/statistics.py:203`
- **Detail**: `stored = [getattr(track, field) for field in STATS_FIELDS]` types as
  `list[Any]`, so strict typing verifies nothing about the four column names matching real
  fields — a typo in `STATS_FIELDS` passes every gate and surfaces as an `AttributeError` on
  every detail page render. Everything else in this change is precisely typed, which is what
  makes this the one soft spot. The four attributes are already spelled out literally ten
  lines below at `statistics.py:207-210`.
- **Fix**: Build `stored` from an explicit tuple of the four attributes and keep
  `STATS_FIELDS` for `update_fields` and the queryset filters only.
- **Decision**: FIXED — `stored` is an explicit 4-tuple of attribute reads; `STATS_FIELDS` still names the set where the values are column names (commit `efd2626`).

### F8 — Banker's rounding renders a 30-second recorded time as "0 min"

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/statistics.py:141`, `gpx/statistics.py:163`
- **Detail**: Python's `round()` is round-half-to-even, so the half boundary is
  inconsistent: `format_duration(30)` → `"0 min"` while `format_duration(90)` → `"2 min"`;
  `format_elevation(0.5)` → `"0 m"` while `format_elevation(1.5)` → `"2 m"`. Magnitude is
  trivial, but "0 min" for a track that recorded half a minute is one of the strings this
  change was written to avoid. Everything above the half-minute boundary is correct — the
  pre-split rounding was verified across 0, 59, 60, 3599, 3600, 3660, 86400 and 90000
  seconds, with no day wrap and no lost hours.
- **Fix**: Use `math.floor(x + 0.5)` if half-up is wanted, or add a line to the docstring
  recording banker's rounding as deliberate so it isn't read as a bug later.
- **Decision**: FIXED via half-up — shared `_round_half_up` helper used by both formatters, so the two cannot drift on the rule. Boundary pinned at 30 s and 0.5 m (commit `82e412e`).

### F9 — Migration 0003's import guard is narrower than the plan specified

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `gpx/migrations/0003_backfill_gpxtrack_stats.py:29`
- **Detail**: The guard is `except ImportError`, where the plan asks for the import to sit
  "under the same guard" with "any exception … logged and skipped … because application
  code changed shape" (plan.md:202, 416-417). The headline scenarios do work: a rename or
  move raises `ModuleNotFoundError` (an `ImportError` subclass) and is caught, and a changed
  helper signature raises `TypeError` at call time which the per-row guard catches. What
  escapes is a module-level `SyntaxError`, `NameError`, or a new circular import inside
  `gpx/statistics.py` — which would break `migrate`, `makemigrations --check` and
  `manage.py check` together, precisely the triple failure the design note at `0003:19-25`
  says the guard exists to avoid.
- **Fix**: Widen to `except Exception`.
- **Decision**: FIXED — guard widened to `except Exception`, with the reason recorded in the migration's docstring (commit `63f6d2a`).

### F10 — The distance fallback prints a sentence describing an impossible state

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `trips/templates/trips/trip_detail.html:84`
- **Detail**: The fallback reads "Not recorded — the GPX file carried no positions to
  measure", but a file with no positions is rejected outright at upload
  (`gpx/parsing.py:245-246`), and a row with null `distance_meters` and null everything else
  returns `None` from `build_trip_stats` and takes the `{% else %}` branch instead. The
  branch is therefore reachable only via a hand-nulled admin row, and the sentence it prints
  cannot be true.
- **Fix**: Reword to name the real cause (statistics not computed for this row), or drop the
  branch and let a null distance fall through to the `{% else %}` at line 106.
- **Decision**: FIXED via reword — the branch survives as a defensive fallback and no longer blames the file for a state the file cannot be in (commit `6c64389`).
