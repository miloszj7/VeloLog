<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Detect and Reclaim Unreferenced GPX Files in MEDIA_ROOT

- **Plan**: `context/changes/gpx-upload-orphan-file/plan.md`
- **Scope**: Full plan — Phases 1–4 of 4 (all Progress items `[x]`)
- **Date**: 2026-08-28
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 5 warnings, 5 observations
- **Triage**: F1–F10 FIXED

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Automated verification (all re-run for this review)

This table is the **as-reviewed** state, before any triage fix. Post-fix figures are recorded
under the finding that changed them.

| Check | Result |
|---|---|
| `uv run ruff check .` | pass |
| `uv run black --check .` | pass (73 files unchanged) |
| `uv run isort --check-only .` | pass |
| `uv run mypy .` | pass (no issues, 73 source files) |
| `uv run python manage.py check` | pass (0 issues) |
| `uv run python manage.py makemigrations --check --dry-run` | pass (no changes detected) |
| `SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` | **238 passed**, total coverage **98.27%** (`fail_under = 80`) |
| `reconcile_media --help` / `grep -- "--allow-full-sweep"` | pass |
| `reconcile_media` against clean tree | `Scanned 4, referenced 4, orphaned 0` — exit 0 |
| Criterion 4.1 (E-11 stale-reference guard) | pass |
| `pytest tests/gpx/test_gpx_upload.py -k replaces` | pass, unchanged |

Manual criteria corroborated independently: the local tree is 4 files ↔ 4 rows with the four
previously-empty directories gone (2.7–2.9); a live log emission renders
`track_id=42 storage_key=gpx/1/7/abc.gpx` and an unrelated line renders the keys empty
rather than raising (3.5–3.6).

`reconcile_media.py` is at 99% line coverage; the two uncovered lines are `:312-313`, the
`except OSError: continue` in `_prune`.

## What was checked and found sound

Recorded so it is not re-litigated:

- **Key-string parity on both sides of the set difference.** Verified empirically on Windows:
  the walk yields `gpx/1/10/bb1e…gpx` and the database holds byte-identical strings; zero false
  orphans. `FileSystemStorage._save` normalizes with `.replace("\\", "/")` and `_join` uses `/`
  unconditionally, so Windows and Linux agree. Keys are `secrets.token_hex(16)` ASCII — no
  NFC/NFD or case exposure.
- **`MEDIA_ROOT` itself can never be pruned.** `walk_storage` only ever appends *child* keys, so
  `""` is never passed to `delete`.
- **Deepest-first ordering is structural, not sort-dependent** — it falls out of post-order
  recursion, confirmed live: `['gpx/1/10', 'gpx/1/16', 'gpx/1/7', 'gpx/1', 'gpx/8/11', 'gpx/8', 'gpx']`.
- **The forbidden exit (files deleted, no tally) is genuinely prevented.** Both `_reclaim` and
  `_prune` catch `Exception` around `delete`; the only uncaught raise sites run *before* any
  deletion. Two tests exercise it with real monkeypatched failures.
- **A misconfigured `MEDIA_ROOT` pointing at a wider tree cannot pass the pairing guard** — no
  walked key could match a stored key, so `--delete` refuses. The guard covers the exact fault
  this repo escalated to a Hard Rule.
- **The `pre_save` receiver satisfies every AGENTS.md constraint**: schedules via
  `transaction.on_commit`, closes over scalars only (no instance closure, so no `points` blob
  held past commit), and its lookup is `values_list("file", flat=True)`. Guard order is exactly
  the specified 1–6, with guard 3 correctly preceding the query. Uploads (inserts) pay zero
  extra queries.
- **Every file-removal test wraps in `django_capture_on_commit_callbacks(execute=True)`**, and
  the negative cases assert `callbacks == []` rather than merely an absence of effect. Reconcile
  tests assert real filesystem state alongside the tally string, not tally-only.
- **All eight "What We're NOT Doing" guardrails hold**; no scope creep in application code.
- **All 15 required Phase 2 test cases exist** (plus 2 extra), and all 6 Phase 1 receiver cases.
- **Commit story** is one phase per commit in dependency order, with the plan-review decision
  commit following the plan edits it describes (lessons.md #8 honored).

## Findings

### F1 — A symlinked directory under `MEDIA_ROOT` lets `--delete` remove files outside the tree

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `gpx/management/commands/reconcile_media.py:60-75`, `:296`
- **Detail**: Three facts compose into an escape from the tree. `FileSystemStorage.listdir`
  classifies entries with `entry.is_dir()`, which follows symlinks, so `walk_storage` recurses
  into a symlinked directory. `FileSystemStorage.path` → `safe_join` uses `abspath`, **never
  `realpath`** — verified directly in `django/utils/_os.py:65-92` — so `MEDIA_ROOT/link/file.gpx`
  passes the containment check. `FileSystemStorage.delete` then calls `os.remove`, which follows
  the symlinked parent and unlinks the real file outside the tree. Nothing in the codebase
  handles symlinks: `grep -rn "symlink\|islink" gpx/ velo_log/ tests/` returns nothing.
  Secondary: a symlink loop makes `walk_storage` recurse without bound (`RecursionError`) — that
  aborts before any delete, so it is loss of signal rather than loss of data, but the recursion
  has no depth cap.
- **Failure scenario**: an operator runs `ln -s /data/backups /data/media/archive` (plausible
  next to the restore material this command's runbook sits beside). `reconcile_media --delete`
  enumerates `archive/*.gpx`, finds none referenced and all older than the threshold, and
  deletes the real backups. Blast radius is whatever is behind the link, and there is no undo
  on the Volume.
- **Fix A ⭐ Recommended**: Refuse to descend into or delete anything whose resolved path leaves
  `MEDIA_ROOT` — in `walk_storage`, skip a child where
  `Path(default_storage.path(child)).resolve()` is not relative to
  `Path(settings.MEDIA_ROOT).resolve()`, writing one stderr line naming what was skipped.
  - Strength: Closes the walk *and* the delete in one place, since nothing enters the orphan
    list that the walk did not yield; also bounds the symlink loop, because a loop's resolved
    path leaves the tree at the first hop.
  - Tradeoff: One `resolve()` syscall per directory; a deliberate symlink farm under
    `MEDIA_ROOT` would silently stop being reconciled (mitigated by the stderr line).
  - Confidence: HIGH — `safe_join`'s use of `abspath` over `realpath` was read directly in the
    installed Django source, and the repo's own Python standards already prescribe exactly this
    `is_relative_to` containment idiom for path sanitization.
  - Blind spot: Not verified whether Railway's Volume mount is itself reached via a symlink at
    `/data/media`; if it were, a naive check would refuse the whole tree. Resolving *both* sides
    (as written above) handles that, but it is untested on the real mount.
- **Fix B**: Document in `DEPLOY.md` that `MEDIA_ROOT` must contain no symlinks, and leave the
  code alone.
  - Strength: Zero code risk on a path that is already irreversible; consistent with the plan's
    stated posture that the operator owns preconditions the walk cannot check.
  - Tradeoff: A documented precondition is not a guard — this is the one command in the project
    that deletes, and F4 shows the operator is not currently told which tree it walked.
  - Confidence: MEDIUM — depends on accepting that no symlink will ever appear under the Volume.
  - Blind spot: No inventory of the production Volume's current contents beyond the 2026-08-28
    four-file baseline.
- **Decision**: FIXED via Fix A

**Correction made while implementing Fix A.** As written above, Fix A claimed the containment
check would also bound the symlink loop. It would not: `ln -s . loop` resolves to `MEDIA_ROOT`
itself, which *is* relative to `MEDIA_ROOT`, so containment alone still recurses
`loop/loop/loop/…` without limit. The implemented guard therefore tests **both** properties,
and neither subsumes the other — `is_symlink()` is what terminates the walk (every loop needs a
symlink), and the resolved-containment check is what catches a non-symlink escape such as a bind
mount or a Windows junction.

**What landed:**

- `gpx/management/commands/reconcile_media.py` — new `_is_walkable_directory(key)` helper
  (`:46-78`) returning `False` for a symlinked child, for a child resolving outside
  `Path(settings.MEDIA_ROOT).resolve()`, and for a `SuspiciousFileOperation` /
  `NotImplementedError` / `ValueError` / `OSError` while resolving. `walk_storage` consults it
  before descending (`:107-115`) and emits `logger.warning("Refusing to walk a media directory
  that leaves MEDIA_ROOT", extra={"storage_key": child})` — `logger.warning` rather than a
  `self.stderr` line because this is a refusal to look rather than a per-item finding, and the
  production root logger sits at `WARNING`, so it still reaches `railway logs`.
  A symlinked *file* deliberately needs no guard: `os.remove` on a symlink unlinks the link, not
  its target, so only the directory case can reach outside the volume.
- `tests/gpx/test_reconcile_media.py` — three tests.
  `test_a_symlinked_directory_is_never_walked_or_reclaimed` stages a file outside `MEDIA_ROOT`,
  links it in, and asserts the real file survives `--delete` and never entered the tally.
  `test_a_symlink_loop_does_not_run_the_walk_out_of_stack` covers the termination half. Both
  skip where the platform refuses directory symlinks (Windows outside Developer Mode), so
  `test_the_walk_guard_rejects_a_directory_that_resolves_outside_media_root` unit-tests the
  containment half by injecting the escape at `storage.path` — the single point every real
  escape arrives through — and runs everywhere, so the guard is not proven only in CI.

**Verification after the fix**: ruff, black, isort, `mypy --strict`, `manage.py check` all pass;
full suite under the CI-equivalent env is **239 passed, 2 skipped** (the two symlink tests, which
run on Linux CI), total coverage **97.29%**. `reconcile_media` against the real tree still reports
`Scanned 4, referenced 4, orphaned 0`.

### F2 — `--min-age-minutes` accepts a negative value, putting the cutoff in the future

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/management/commands/reconcile_media.py:88-99`, `:134`
- **Detail**: `type=int` with no validation. Confirmed empirically: `manage.py reconcile_media
  --min-age-minutes -30` is accepted by argparse without error, and
  `timezone.now() - timedelta(minutes=-30)` places the cutoff 30 minutes in the **future**.
  Every unreferenced file then clears `modified > cutoff`, including one a request is writing
  right now. This is strictly more dangerous than the documented `0`, and neither the help text
  nor `DEPLOY.md` mentions it. `gpx/constants.py` calls this threshold "the only thing separating
  a genuinely unreferenced file from one a request is in the middle of writing" — a negative
  value silently inverts it.
- **Failure scenario**: an operator fat-fingers `--min-age-minutes -30` intending `30` on a live
  service. An upload mid-`_save_table` — file on disk, INSERT not yet committed — is reclaimed,
  and the request 500s or the row commits pointing at a file that no longer exists.
- **Fix**: Raise `CommandError` when `min_age < 0`, and say so in the `--min-age-minutes` help
  text alongside the existing note about `0`.
- **Decision**: FIXED

**What landed:** `handle` raises `CommandError` before the walk when `min_age < 0`; the
`--min-age-minutes` help text now says so alongside the existing note about `0`.
`test_a_negative_min_age_minutes_is_refused` asserts the refusal via
`pytest.raises(CommandError, match=...)`. Commit: `9f925a1`.

### F3 — `walk_storage` catches only `FileNotFoundError`, so any other `OSError` aborts the run with no tally

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/management/commands/reconcile_media.py:60-63`
- **Detail**: The walk guards its `listdir` with `except FileNotFoundError` only. A
  `PermissionError`, `NotADirectoryError` or stale-handle `OSError` on **any** subdirectory
  propagates out of `handle`. That contradicts the contract the command states about itself at
  `:119` ("Always exits 0. A per-item failure is a counted skip") and is internally inconsistent
  with `_prune:293-296`, which catches the broader `OSError` around the very same `listdir` call.
  Not the forbidden mid-run exit — the walk precedes every delete, so no partial reclamation is
  possible — but a total loss of signal.
- **Failure scenario**: after a restore, one `gpx/<owner>/` directory carries bad permissions.
  The operator runs the command precisely *because* the volume is in a bad state, and gets a
  traceback plus zero information about the other 99% of the tree.
- **Fix**: Catch `OSError` rather than `FileNotFoundError`, write a `Could not read <key>.` line
  to stderr, and continue — matching what `_prune` already does for the same call.
- **Decision**: FIXED

**What landed:** `walk_storage` (a module-level function with no `self.stderr`) now catches
`OSError` alongside `FileNotFoundError`, writes `Could not read {prefix}.` to `sys.stderr`, and
returns `([], [])` for that branch rather than propagating. `test_an_unreadable_subdirectory_is_a_counted_skip_not_a_crash`
monkeypatches `default_storage.listdir` to raise `PermissionError` for one subdirectory and
asserts the rest of the tree is still scanned and tallied. Commit: `9f925a1`.

### F4 — No output names the `MEDIA_ROOT` the run actually walked

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/management/commands/reconcile_media.py:167-173`, `:229-278`
- **Detail**: `MEDIA_ROOT` appears in this file only inside docstrings. The tally, the per-orphan
  lines and the skew warning all print bare relative keys. Yet the command's entire safety story
  rests on the operator knowing *which tree* was scanned: `DEPLOY.md`'s precondition says "never
  with a `MEDIA_ROOT` whose value has not been confirmed", and the runbook itself documents the
  `MSYS_NO_PATHCONV` trap that silently mangles the value. The repo already has
  `media_root_misconfiguration()` at `velo_log/urls.py:97` encoding the Hard Rule, and this
  command does not consult or echo it. The pairing guard does catch the *complete* misconfiguration
  (F-sound list above), but the operator still cannot see what they confirmed.
- **Failure scenario**: `MEDIA_ROOT` is set to `/data` rather than `/data/media`. The command
  refuses `--delete` correctly. The operator reads "only correct when the database really is
  empty", misjudges the situation, adds `--allow-full-sweep`, and clears the wrong tree — having
  never been shown its path.
- **Fix**: Print the resolved `settings.MEDIA_ROOT` as the first stderr line of every run. It is
  already surfaced in `railway logs` through the `media_root` log-context key, so this is no new
  exposure.
- **Decision**: FIXED

**What landed:** `handle` writes `MEDIA_ROOT: {settings.MEDIA_ROOT}` to stderr as the first
thing it does after the `--min-age-minutes` guard. `test_the_resolved_media_root_is_the_first_stderr_line`
asserts it is literally `captured.err.splitlines()[0]`. Commit: `3ca9adc`.

### F5 — The rewritten E-11 roadmap row lost its trailing table delimiter

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `context/foundation/roadmap.md:163`
- **Detail**: The rewritten row ends at `…implementation review (F10)` with no closing `|`. Pipe
  counts: line 161 → 8, line 162 → 8, line 163 → **7**. `master`'s version of the row ended
  `… | open | — |`, so this is a regression introduced by this change, not pre-existing. Cell
  count still parses as 7 under GFM so it renders, but every sibling row in the table is
  terminated and a future column-aware edit or script could trip on the odd one out.
- **Fix**: Append ` |` to the end of line 163.
- **Decision**: FIXED

**What landed:** Appended ` |` to close the row; pipe count on line 163 now matches the 8
of its sibling rows. Commit: `fec0506`.

### F6 — Spared-file lines omit the size the plan specified

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `gpx/management/commands/reconcile_media.py:146`, `:150`
- **Detail**: The plan's reporting contract reads "one `self.stderr.write` line per orphan **and
  per spared file**, naming the key **and its size**." The orphan line does carry it
  (`Orphan {key} ({size} bytes).`); the two spared lines name only the key. `_stat` already
  returns the size, so it is discarded at the call site rather than unavailable.
- **Fix**: Include `({size} bytes)` on the spared lines, matching the orphan line.
- **Decision**: FIXED

**Deviation from the finding as written:** only the "modified in the last N minute(s)" line
was given a size, not the "it could not be read" line. `_stat` returns `(None, 0)` on failure,
so the "unreadable" branch never actually has a real size in hand — the `0` is a sentinel, not
a reading. Adding `(0 bytes)` there would misreport an unknown size as a known zero, which is
the same class of bug F7 fixes for directories. The recently-modified line does have a real
size from a successful `_stat` call, so it gets the annotation the finding asked for.

**What landed:** `Spared {key}: modified in the last {min_age} minute(s) ({size} bytes).`
`test_a_freshly_written_orphan_spared_line_reports_its_size` asserts the exact line. Commit:
`3ca9adc`.

### F7 — A directory whose mtime could not be read is reported as "modified recently"

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/management/commands/reconcile_media.py:206-211`
- **Detail**: `if modified is None or modified > cutoff:` collapses two distinct states into one
  message — `Spared directory {key}: modified in the last {min_age} minute(s).` When `_stat`
  returned `None` the mtime was *unreadable*, not recent. The file path gets this right, with a
  separate `Spared {key}: it could not be read.` line at `:146`. Sparing is the correct action in
  both cases; only the reported reason is wrong.
- **Fix**: Split the branch and reuse the file path's "it could not be read" wording for the
  `modified is None` case.
- **Decision**: FIXED

**What landed:** `_empty_directories` now branches on `modified is None` first, writing
`Spared directory {key}: it could not be read.`, before falling through to the existing
"modified in the last N minute(s)" line. `test_a_directory_whose_mtime_cannot_be_read_is_not_called_recently_modified`
monkeypatches `get_modified_time` to raise `FileNotFoundError` for one directory and asserts
the new wording, not the old one. Commit: `3ca9adc`.

### F8 — `DEPLOY.md` does not warn against staging a backup inside `MEDIA_ROOT`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `DEPLOY.md:177-266`
- **Detail**: The referenced set is `GpxTrack.file` alone, and the walk is deliberately unscoped
  — `test_an_orphan_outside_the_gpx_prefix_is_found` makes that a tested property. The new
  section explains *why* the walk is unscoped but never draws the operator-facing consequence:
  any file staged under the Volume that is not a `GpxTrack.file` is reclaimable. The section sits
  immediately after the restore drill, which is exactly the moment someone would stage a copy at
  `/data/media/pre-migration-2026-09-01/`. Composes with F1: a backup *symlinked* in is worse
  than one copied in.
- **Fix**: Add one line to the `### Before --delete` precondition: never stage a backup, export
  or scratch copy inside `MEDIA_ROOT` — the walk will call it an orphan.
- **Decision**: FIXED

**What landed:** Added a bullet to the precondition list naming the risk directly, including
the F1 compound case (a symlinked-in backup is worse than a copied one). Commit: `db9dc9a`.

### F9 — `change.md`'s Notes body still asserts the cause this change proved false

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `context/changes/gpx-upload-orphan-file/change.md:12-28`
- **Detail**: The `## Notes` body still carries the pre-framing E-11 text verbatim: the drifted
  cite `gpx/views.py:100-113`, the claim that `super().form_valid(form)` writing "inside
  `transaction.atomic()`" is the cause, and the proposed fix ("move the file write outside the
  atomic block, or register a compensating rollback hook") that `frame.md` refuted and that the
  same change's own roadmap row now records as **"Original proposal refuted"**. It also still
  says "Two follow-ups when this lands", both of which have landed. The plan did not ask for the
  body to be updated, so this is not drift against the plan — but the change folder now
  contradicts the roadmap that this change wrote, and lessons.md #5 is precisely about a stale
  document misdirecting the next reader. This one is archive-bound.
- **Fix**: Add one line under `## Notes` marking the original observation as superseded and
  pointing at `frame.md` and the closed E-11 row, rather than rewriting the history.
- **Decision**: FIXED

**What landed:** A `**Superseded**` paragraph now opens `## Notes`, pointing at `frame.md` and
the closed E-11 roadmap row, with the original text kept verbatim below it as the historical
record. Commit: `3c4fccf`.

### F10 — Two docstrings claim a zero-query property that no test asserts

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `gpx/signals.py:163`, `:168`; `tests/gpx/test_gpx_signals.py`
- **Detail**: `signals.py:163` states the insert path "costs the hot path zero queries" and `:168`
  that the `update_fields` path "is answered without a query" — the performance claim the plan
  made for the receiver. No test uses `django_assert_num_queries`, so a future edit that moves the
  query above guard 2 or 3 would break the property with every gate green. Note the *test names*
  claim only "removes nothing", which is genuinely asserted, so this is not a lessons.md #1
  violation — it is an unasserted docstring claim. Also untested: the `walk_storage` mid-walk
  `OSError` path (F3) and any negative `--min-age-minutes` (F2); `reconcile_media.py:312-313`
  (`_prune`'s `except OSError`) is the file's only uncovered line pair.
- **Fix**: Add `django_assert_num_queries(0)` around the insert and `update_fields` saves in the
  two existing tests.
- **Decision**: FIXED

**Deviation from the finding as written:** wrapping `track.save()` itself in
`django_assert_num_queries(0)` is not possible — an insert or an `UPDATE` always costs at least
one real query, so the literal instruction would fail against the very save it names. Both new
tests instead call `discard_superseded_file_of_saved_track` directly — once on an unsaved
instance (`pk is None`), once with `update_fields` excluding `file` — which is the only way to
observe the receiver's own contribution to the query count in isolation, and is what the
docstrings actually claim ("costs the hot path zero queries" / "answered without a query").

**What landed:** `test_the_insert_path_costs_the_receiver_no_query` and
`test_the_update_fields_guard_costs_the_receiver_no_query` in `tests/gpx/test_gpx_signals.py`,
each wrapping a direct receiver call in `django_assert_num_queries(0)`. Commit: `ef423dc`.

## Full re-verification after triage (F2–F10)

| Check | Result |
|---|---|
| `uv run ruff check .` | pass |
| `uv run black --check .` | pass (73 files unchanged) |
| `uv run isort --check-only .` | pass |
| `uv run mypy .` | pass (no issues, 73 source files) |
| `uv run python manage.py check` | pass (0 issues) |
| `uv run python manage.py makemigrations --check --dry-run` | pass (no changes detected) |
| `SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` | **246 passed, 2 skipped**, total coverage **97.34%** (`fail_under = 80`) |

All ten findings from the full-plan implementation review are now FIXED. Commits, in order:
`1df3f04` (F1), `9f925a1` (F2, F3), `3ca9adc` (F4, F6, F7), `ef423dc` (F10), `fec0506` (F5),
`db9dc9a` (F8), `3c4fccf` (F9).
