<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Trip Distance and Duration Stats

- **Plan**: `context/changes/trip-distance-duration-stats/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-27
- **Verdict**: REVISE → **SOUND** after triage (2026-08-27, all 9 findings fixed)
- **Findings**: 1 critical, 4 warnings, 4 observations — 9 fixed, 0 skipped, 0 accepted,
  0 dismissed

## Verdicts

| Dimension | Verdict (at review) | After triage |
|-----------|---------------------|--------------|
| End-State Alignment | WARNING | PASS — F5 |
| Lean Execution | WARNING | PASS — F7 |
| Architectural Fitness | WARNING | PASS — F3 |
| Blind Spots | FAIL | PASS — F1, F2, F6, F9 |
| Plan Completeness | WARNING | PASS — F4, F8 |

Triage changed the slice's shape in two ways worth carrying forward: it now ships
**four** stats columns rather than five (F7 dropped `moving_seconds`, parked as a feature
item on the roadmap), and the time stat is **recorded time**, not elapsed time (F6). Two
new fixtures pin branches the original fixture set could not reach.

## Grounding

13/13 paths ✓, 9/9 symbols ✓, 8/8 line anchors ✓, brief↔plan ✓

Verified independently against the installed `gpxpy 1.6.2` in `.venv`, rather than
taking the plan's probe notes on faith:

- `GPX.length_2d() -> float` — sums track lengths, never `None` (`gpx.py:2266`). The
  plan's non-optional `distance_meters` is correct.
- `GPX.get_uphill_downhill() -> UphillDownhill(uphill: float, downhill: float)` —
  returns `(0, 0)` rather than `None` (`gpx.py:2363`, NamedTuple at `gpx.py:124`). The
  trap the plan names is real.
- `GPX.get_elevation_extremes() -> MinimumMaximum(Optional[float], Optional[float])`
  (`gpx.py:2405`, NamedTuple at `gpx.py:127`). Valid presence probe for elevation.
- `MovingData.moving_time: float` — never `None` (`gpx.py:118-123`). Second trap real.
- `GPX.get_duration() -> Optional[float]` (`gpx.py:2341`) — returns `None` only when a
  child segment does. **See F1: it does not always do so.**
- `GpxTrackAdmin` sets `exclude = ("points",)` with no `fields`/`fieldsets`
  (`gpx/admin.py:27`), so the plan's `blank=True` argument is genuinely load-bearing.
- `gpxpy` ships `py.typed`, so the new calls introduce no `mypy --strict` friction.
- `[tool.coverage.run] source` already includes `gpx`, so lessons.md #4 does not apply.
- `ParsedTrack` has exactly one construction site (`gpx/parsing.py:181`, kwargs), so
  adding five fields to the frozen dataclass breaks no caller.
- Progress↔Phase consistency: 4 phases matched, 20/20 success-criteria bullets mapped,
  one `## Progress` heading, no stray checkboxes in phase blocks. Clean.

## Findings

### F1 — The time-presence gate has a hole that stores the exact zero it exists to prevent

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details → "State sequencing"; Phase 1 §2
- **Detail**: The plan makes `get_duration() is None` the presence probe for time, on
  the verified basis that it returns `None` where `moving_time` returns `0.0`. That
  holds for the shapes probed — but `GPXTrackSegment.get_duration` (`gpx.py:1119`)
  opens with `if not self.points or len(self.points) < 2: return 0.0`. A segment with
  fewer than two points returns `0.0` and never reaches the `first.time`/`last.time`
  check that produces `None`. `GPXTrack.get_duration` (`gpx.py:1754`) and
  `GPX.get_duration` (`gpx.py:2341`) both propagate `None` only when a child returns
  `None`, so they sum those zeros and return `0.0`.

  `parse_gpx` rejects zero points but explicitly permits one (`gpx/parsing.py:166`).
  So a one-point untimed GPX — or any multi-segment file whose segments each hold a
  single point — stores `duration_seconds = 0.0`, which then un-gates
  `moving_seconds = 0.0`, and the page renders "0 min" for a file carrying no time
  data whatsoever. That is precisely the silent data defect the plan's Key Discoveries
  exist to prevent, reintroduced through an unexamined branch.

  Neither the specified tests nor any gate catches it: Phase 1's contract pins
  `second-track.gpx`, which has two untimed points and therefore *does* reach the
  `None` branch. The hole sits below the fixture set.
- **Fix**: Probe time presence with `gpx.get_time_bounds()` (`gpx.py:2118`) instead —
  `TimeBounds.start_time is None` means no point carried a `<time>`, the exact
  structural mirror of the elevation gate already using
  `get_elevation_extremes().minimum is None`. Keep `get_duration()` as the *value*,
  gated on that probe. Add a one-point untimed fixture (or build one inline in the
  Phase 1 test contract) so the branch is pinned.
  - Strength: Makes both gates symmetric and structural rather than one structural and
    one incidental; `TimeBounds` is a documented public API with the same
    `Optional`-fielded NamedTuple shape as `MinimumMaximum`.
  - Tradeoff: One extra gpxpy call per parse (negligible — it walks points already in
    memory).
  - Confidence: HIGH — read directly from the installed source, not inferred.
  - Blind spot: `get_time_bounds` behaviour on a partial-time file (some points timed)
    is unverified; expected to return the bounds of the timed subset, which is the
    same all-or-nothing limitation F9 notes for elevation.
- **Decision**: FIXED — the probe is now `get_time_bounds().start_time is None`, applied
  in Key Discoveries, in the "State sequencing" gate, and in Phase 1 §2. A
  `single-point-track.gpx` fixture (Phase 1 §6) pins the branch, and the Phase 1 §8 test
  contract requires it to fail if the probe is ever changed back to `get_duration()`.
  The blind spot this fix carries — partial-time files — is now stated explicitly in
  "What We're NOT Doing" as part of F9's fix.

### F2 — One-shot backfill, with the project's most-documented fault as its silent failure

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 2; "What We're NOT Doing"; Migration Notes
- **Detail**: Migration Notes already states the trap and then accepts it: "If
  `MEDIA_ROOT` is misconfigured at migrate time … the backfill fills nothing …
  Re-running the migration is not possible once applied; a re-upload of the affected
  file is the recovery path."

  A wrong `MEDIA_ROOT` is not hypothetical here — it is the single fault this repo has
  escalated to a Hard Rule in `AGENTS.md`, documented in `DEPLOY.md` with a named Git
  Bash trap, and wired into `/healthz/` as the only probe that reports it. The plan
  pairs the project's highest-likelihood operational fault with a mechanism that can
  only run once, unattended, at boot — and whose recovery is the user manually
  re-uploading every file, permanently.

  "What We're NOT Doing" rejects a management command as "warranted only if the
  migration proves insufficient in practice". Given the above, "in practice" is a coin
  flip on one deploy, and the cost of being wrong is unrecoverable by any automated
  means.
- **Fix A ⭐ Recommended**: Keep migration 0003, and add a thin management command
  (`gpx/management/commands/backfill_gpx_stats.py`) looping the same helper Phase 2
  already extracts.
  - Strength: ~15 lines over a helper the plan builds regardless; turns the recovery
    path from "re-upload every file by hand, permanently" into "run one command".
    Deploy-time automation is unchanged.
  - Tradeoff: One more file and one more test; two entry points to the same helper.
  - Confidence: HIGH — the helper's contract (open file → `parse_gpx_bytes` → save with
    `update_fields`) is already specified to be callable outside a migration, which is
    the whole reason it lives in `gpx/statistics.py`.
  - Blind spot: The command needs its own coverage to stay above `fail_under = 80`.
- **Fix B**: Drop migration 0003 entirely; ship the helper plus the management command,
  run manually once after deploy.
  - Strength: Removes a migration that imports application code (see F3), removes the
    replay-forever coupling, and removes a phase's worth of migration-specific
    reasoning. Leanest option by a clear margin at single-digit-trip scale.
  - Tradeoff: Existing tracks stay blank until someone remembers to run it; loses the
    "gains stats on next deploy with no manual step" property the brief records as the
    reason for this decision.
  - Confidence: MEDIUM — correct on the engineering merits, but reverses a decision the
    brief made deliberately.
  - Blind spot: Whether the owner will actually run a post-deploy command.
- **Decision**: FIXED via Fix A — migration `0003` kept; Phase 2 gained §3, a
  `backfill_gpx_stats` management command over the same helper (`--all` to reprocess
  every row, per-row failures reported not raised, exit 0 on a partially unreadable media
  directory). Its tests are specified in Phase 2 §4, Migration Notes now names it as the
  recovery path instead of "re-upload the affected file", "What We're NOT Doing" was
  reworded from "no management command" to "no scheduled or automatic re-backfill", and
  Phase 4 adds it to the AGENTS.md Development Commands table. Progress bullet 2.8 added.

### F3 — The per-row `except` cannot catch the failure it is described as preventing

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architectural Fitness
- **Location**: Critical Implementation Details → "Backfill robustness"; Phase 2 §2
- **Detail**: The stated mitigation is: "Wrap each row's work in a broad
  `except Exception` … so a future incompatibility degrades to an unfilled column
  rather than a `migrate` that cannot replay on a fresh database."

  A per-row `try` inside the `RunPython` callable does not cover the thing most likely
  to break replay. If `gpx/statistics.py` is later renamed, moved, or has its helper
  signature changed, the failure is at `from gpx.statistics import …` at the *top of
  the migration module*, evaluated when Django builds the migration graph — before any
  row is touched, and early enough to break `migrate`, `makemigrations --check`, and
  `manage.py check` alike. The row-level guard never executes.

  The module-docstring convention ("must name migration 0003 as a consumer") is the
  real mitigation the plan has; the `except Exception` is doing less work than the plan
  credits it with.
- **Fix**: Move the import inside the `RunPython` function body and wrap it in the same
  guard as the row work, so an `ImportError` degrades to a logged skip instead of an
  unloadable migration. Correct the "Backfill robustness" paragraph to say what the
  guard actually covers — a per-row parse or storage failure — and name the docstring
  pin as the defence against deletion. (Moot under F2 Fix B.)
  - Strength: Makes the stated property true rather than aspirational; costs two lines.
  - Tradeoff: An import inside a loop-adjacent function reads oddly without a comment
    saying why.
  - Confidence: HIGH — this is Django migration-graph loading behaviour, not a
    judgement call.
  - Blind spot: None significant.
- **Decision**: FIXED — "Backfill robustness" now separates the two failures it was
  conflating: a per-row failure (broad `except`, row left null, `migrate` succeeds) and
  an import failure (evaluated at migration-graph build time, before any row, breaking
  `migrate`, `makemigrations --check` and `manage.py check` at once). The import moves
  inside the `RunPython` body under the same guard, with a comment saying why it is not
  at module level; Phase 2 §2's contract states the same. The docstring pin is now named
  as what defends against deletion, rather than the `except` being credited with it.

### F4 — `build_trip_stats`'s all-null rule restates the zero-vs-null trap one layer up

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 §1
- **Detail**: The contract says `build_trip_stats` returns `None` "when `track is None`
  **or when all five stored values are null**". The plan is scrupulous about `is None`
  vs. falsy in its *test* contract ("asserted as `is None`, **not** as falsy, since `0`
  is precisely the wrong value this pins against") but leaves this builder's rule in
  prose that a natural implementation (`if not any([...])`) gets wrong.

  A track whose points are all identical stores `distance_meters = 0.0` — legal,
  non-null, and falsy. Under a falsy check the whole Stats section collapses to the
  "re-upload" sentence for a track that was parsed and stored perfectly.
- **Fix**: State the rule in the contract as `all(value is None for value in …)`, and
  add a test for a track with `distance_meters = 0.0` and four `None`s asserting a
  populated `TripStats` is returned.
- **Decision**: FIXED — Phase 3 §1 now pins the rule as `all(value is None for value in
  …)` and states why explicitly (`not any(...)` discards a legal all-identical-points
  track storing `distance_meters = 0.0`), naming it as the same zero-versus-null trap one
  layer up. The test is specified in Phase 3 §5 and in Testing Strategy. Under F7 the
  companion `None`s are three, not four.

### F5 — Phase 4 syncs AGENTS.md but not the roadmap, though it cites the rule naming both

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: End-State Alignment
- **Location**: Phase 4
- **Detail**: Phase 4's Overview cites lessons.md #5, which reads "Update `AGENTS.md`
  **and roadmap status** in the same slice that invalidates them." The phase covers only
  the `AGENTS.md` bullet. Two roadmap rows go stale the moment this ships:

  - `context/foundation/roadmap.md:34` — S-05 status column reads `planning`
  - `context/foundation/roadmap.md:122` — S-05 issue-table status reads "Waiting on
    S-03", which is already false today (S-03 is `done`)

  Precedent confirms this is the house convention: S-03 and S-04 both carry "Planned and
  implemented (…)" in that column, and E-08 carries a dated `done` entry attributed to
  the slice that closed it.
- **Fix**: Extend Phase 4 to cover the two roadmap rows alongside the `AGENTS.md`
  bullet, rename the phase to "Sync AGENTS.md and roadmap", and add a manual
  verification bullet (4.3) for the roadmap rows.
- **Decision**: FIXED — Phase 4 is renamed "Sync AGENTS.md and roadmap", its Overview
  quotes both halves of lessons.md #5, and a new §2 specifies both edits against the
  wording S-03/S-04 already use: slice-table status `planning` → `done`, issue-table
  `Waiting on S-03` → `Planned and implemented (…)` with the shipped column `no` → `yes`.
  Manual bullet 4.3 and the matching Progress entry added.

### F6 — "Elapsed duration" may not be what `get_duration()` measures on a tour export

- **Severity**: 💭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Desired End State; Phase 1 §2
- **Detail**: `GPX.get_duration` sums each *segment's* first-to-last span
  (`gpx.py:2341` → `1754` → `1119`). Inter-segment gaps are excluded. For a
  single-segment export the number is wall-clock elapsed; for a multi-segment one —
  recording paused and resumed, the normal shape for the multi-day tours this product
  is explicitly for — it silently omits every gap, including overnight.

  That is arguably the *better* number for a tour. But the plan calls it "elapsed
  duration" and contrasts it with moving time, and no fixture is multi-segment, so the
  semantic is neither stated nor pinned.
- **Fix**: Decide and state the semantic in `ParsedTrack`'s field docstring and the
  template label ("recorded time" rather than "elapsed" if the sum is kept), and
  consider a two-segment fixture so the behaviour is pinned rather than inherited.
- **Decision**: FIXED — the semantic is decided in favour of the per-segment sum and
  named **"recorded time"** throughout: a dedicated paragraph in the Overview, a Key
  Discoveries bullet tracing `2341 → 1754 → 1119`, a `ParsedTrack` field docstring and a
  model `help_text` (Phase 1 §2 and §3), and the template label in Phase 3 §4 ("Recorded
  time", not "Elapsed time"). A `two-segment-track.gpx` fixture pins it — two timed
  segments an hour each, six hours apart, so the sum and the first-to-last span cannot be
  confused — asserted in Phase 1 §8 and Testing Strategy. Manual step 1 asks for one
  check against a real multi-segment export.

### F7 — `moving_seconds` ships from the same call whose `max_speed` was excluded as unreliable

- **Severity**: 💭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Lean Execution
- **Location**: "What We're NOT Doing"; Key Discoveries
- **Detail**: "No average or max speed. `max_speed` read `0.0` on real timed input in
  the probe; a stat that unreliable is not worth shipping on a nice-to-have slice."
  Both values come out of the same `get_moving_data()` call, and the same probe
  recorded `moving_time` at `1800.0` against `7200.0` elapsed. The plan excludes one
  output of that call for unreliability and ships another, and the asymmetry is
  asserted ("elapsed is the headline figure") rather than argued.

  They are not in fact equally unreliable — `max_speed` is distorted by
  `speed_extreemes_percentiles` on a 3-point track, while `moving_time` is ordinary
  threshold classification that behaves sensibly on real 1 Hz data. But that
  distinction is nowhere in the plan, so the reader is left with a rule that
  contradicts itself.
- **Fix**: Either state why moving time survives the argument that killed max speed, or
  drop `moving_seconds` — which would remove a column, a migration field, a formatter,
  a template row and three tests.
- **Decision**: FIXED by dropping `moving_seconds` — the second branch of the fix. The
  slice now stores **four** columns, not five, and the whole of `get_moving_data()` is
  excluded rather than one of its outputs. "What We're NOT Doing" states the reason
  honestly: the two outputs are not equally suspect, but neither was probed against a
  real ride, so deferring both together is an argument the slice can actually make.
  Speed and moving-time stats are parked as a **feature** item in `roadmap.md`'s
  `## Parked` section (not the Engineering Backlog — this is deferred product scope, not
  debt), with the probe numbers, the reason, and the note that picking it up needs real
  timed exports in hand. Every "five" in the plan was re-counted to "four".

### F8 — `change.md`'s E-11 scope note describes an approach the plan replaced

- **Severity**: 💭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: `change.md`; "What We're NOT Doing" (which cites it)
- **Detail**: `change.md` justifies leaving E-11 open with: "S-05 reads GPX track data
  already stored on `GpxTrack` (likely `points`) to compute distance/duration for
  display." The plan rejects that approach outright — stats are computed at parse time,
  and `points` is never read for them. The plan then cites `change.md` as the authority
  for the exclusion.

  The *conclusion* still holds: Phase 3 touches `GpxUploadView.get_context_data`
  (`gpx/views.py:66-78`), not `form_valid`'s transaction (`gpx/views.py:100-113`), so
  E-11's own trigger is genuinely not fired. Only the reasoning is stale.
- **Fix**: Reword `change.md`'s E-11 paragraph to the actual basis — this change adds
  columns and a render path, and does not open `form_valid`'s transaction block.
- **Decision**: FIXED — `change.md`'s E-11 paragraph now states the actual basis: the
  slice adds derived columns, fills them inside the existing `parse_gpx` call, and in
  `gpx/views.py` touches `get_context_data` (`:66-78`) only, never opening the
  transaction block at `:100-113`. The stale "reads `points` to compute distance" claim
  is gone; the conclusion (E-11 stays open) is unchanged.

### F9 — Partial elevation passes the presence probe and reports gain over a subset

- **Severity**: 💭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details → "State sequencing"
- **Detail**: gpxpy's `get_uphill_downhill` docstring is explicit: "If elevation for
  some points is not found those are simply ignored." The elevation gate is
  all-or-nothing — `get_elevation_extremes().minimum is None` — so a file where only
  some points carry `<ele>` clears the probe and stores a gain computed over whatever
  subset happened to have data. No fixture covers this shape, and no note acknowledges
  it.
- **Fix**: Accept it explicitly in "What We're NOT Doing" (partial-elevation files
  report over the points that carry elevation), rather than leaving a reader to infer
  the gate is stronger than it is.
- **Decision**: FIXED — "What We're NOT Doing" gains a bullet stating that both gates are
  all-or-nothing by design, covering the new `get_time_bounds()` probe as well as
  elevation. It quotes gpxpy's "those are simply ignored", and argues the acceptance
  rather than merely recording it: the gates exist to stop a wholly absent input
  rendering as a confident `0`, and a subset-derived figure is an understated real number
  rather than a fabricated one.
