<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Detect and Reclaim Unreferenced GPX Files in MEDIA_ROOT

- **Plan**: `context/changes/gpx-upload-orphan-file/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-28
- **Verdict**: REVISE
- **Findings**: 1 critical, 3 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

## Grounding

16/16 paths ✓, 9/9 symbols ✓, brief↔plan ✓.

Django source claims spot-checked against the installed 6.0.5: `pre_save` send order and
`update_fields` kwarg (`db/models/base.py:946-952`), `FileField.pre_save` /
`save_form_data` (`db/models/fields/files.py:325-368`), `FileSystemStorage.delete` using
`os.rmdir` on a directory and absorbing `FileNotFoundError` only
(`core/files/storage/filesystem.py:156-169`), `listdir` non-recursive returning bare names
(`:184-193`), `get_modified_time` via `os.path.getmtime` (`:223-224`) — all confirmed as the
plan states them.

Progress↔Phase contract: exactly one `## Progress`, 4/4 phase headings matched, 30/30 success
criteria mapped to numbered items, no `- [ ]` outside the Progress section ✓.

Predicate cross-check against existing fixtures (the risk the brief names): `make_stored_track`
(`tests/conftest.py:157-163`) creates with `file=""` then calls `FieldFile.save(..., save=True)`
— guard 5 (falsy stored key) skips it. `tests/gpx/test_gpx_track_model.py:109` re-saves over
`gpx/1/1/deadbeef.gpx`, a name with no bytes on disk — `FileSystemStorage.delete`'s
`FileNotFoundError` absorb handles it. `STATS_FIELDS` (`gpx/statistics.py:47`) contains no
`file`, so guard 3 keeps `gpx/statistics.py:105` query-free. `GpxUploadView` resolves to
`CreateView` (`gpx/views.py:21`), so guard 2 holds for the upload path.

## Findings

### F1 — `--delete` trusts the database and MEDIA_ROOT are a matched pair, and nothing checks it

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Blind Spots
- **Location**: Phase 2 §2 — "Referenced set" / "Reclaim"; Phase 4 §2 — DEPLOY.md contract
- **Detail**: The orphan set is `walk(MEDIA_ROOT) - set(GpxTrack.file)`. That is only a set of
  orphans if the database and the media tree are the same point in time. Two states documented
  in this repo break that, and in both every file in the tree looks orphaned, is older than
  `ORPHAN_MIN_AGE_MINUTES` by construction, and is reclaimed permanently:
  (1) a database-only restore or rollback — `DEPLOY.md:56` documents restoring the SQLite backup
  for a schema revert with no media step, and `DEPLOY.md:110` already warns the two halves must
  come from the same point in time; with an older DB in place, `--delete` reclaims every file
  uploaded since that snapshot. (2) a misconfigured `MEDIA_ROOT` — the one fault this repo
  escalated to a Hard Rule — where the walk enumerates a tree the database does not describe.
  This is not a hypothetical pairing: the plan places the runbook section "after the restore-drill
  material" and names restore nesting (`DEPLOY.md:151`) as the top-ranked orphan source, so the
  runbook directs the operator to run this command in precisely the state where the DB/media
  pairing is most likely broken — for what the plan's own Migration Notes call "the one
  irreversible action in the plan — there is no undo on the volume." The age guard does not cover
  this: it separates an in-flight write from an orphan and says nothing about a stale referenced
  set.
- **Fix A ⭐ Recommended**: A precondition in the runbook plus a refusal in the command — abort a
  `--delete` run when the referenced set is empty or the orphan set is the entire tree, behind an
  explicit override flag.
  - Strength: Covers the operator who never reads the runbook, which is the one this hazard
    actually catches. Mirrors the command's existing posture — report-only by default, act only
    on an explicit flag — by making the dangerous shape need a second explicit flag. Cheap: one
    count query and one branch.
  - Tradeoff: One more flag on the command's surface, and a legitimate "reclaim everything, the
    DB really is empty" run needs the override.
  - Confidence: HIGH — the refusal condition is exactly the shape both failure states produce.
  - Blind spot: A partial restore where *some* rows survive still slips through; only the runbook
    precondition covers that.
- **Fix B**: Runbook precondition only — document the ordering, add no code.
  - Strength: No new command surface; keeps Phase 2 to the shape already planned.
  - Tradeoff: The single guard against irreversible loss is a paragraph in a document, on a path
    an operator reaches while already recovering from an incident.
  - Confidence: MEDIUM — DEPLOY.md's own restore drill found three defects in a runbook that had
    been written and never exercised.
  - Blind spot: Untested by construction — no automated criterion can assert a prose precondition
    was followed.
- **Decision**: FIXED via Fix A

### F2 — Phase 4 edits a roadmap "notes column" that does not exist, and leaves E-11's refuted fix standing

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Phase 4 §3 — E-11 and the roadmap
- **Detail**: The Engineering Backlog header is
  `| ID | Item | Proposed fix | Trigger | Change ID | Status | GitHub Issue |`
  (`context/foundation/roadmap.md:152`). The contract says "record in the notes column" — there is
  no notes column. E-02, E-05 and E-08 all put closing prose in `GitHub Issue`, so the convention
  exists, but the plan names a column the implementer has to guess at, and adding one would
  rewrite all eleven rows. Separately, the contract directs a rewrite of the observation (the
  `Item` column), the cite, `Change ID` and `Status` — and says nothing about `Proposed fix`,
  which currently reads "Move the file write outside the atomic block, or register a compensating
  rollback hook." That is the exact approach `frame.md` refuted and the plan's own "What We're NOT
  Doing" rejects. Closing the row while leaving it in place ships a done item asserting a fix that
  provably does not work — the misdirection lesson 5 exists for, and what manual criterion 4.6 is
  meant to catch without the contract ever directing the edit that would satisfy it.
- **Fix**: Restate the contract against the real columns — `Item` (rewrite the observation),
  `Proposed fix` (replace with what was actually built, or state the original was refuted and
  why), `Trigger` (leave), `Change ID` = `gpx-upload-orphan-file`, `Status` = `done (<date>)`,
  `GitHub Issue` = the closing prose, following E-05's precedent.
- **Decision**: FIXED

### F3 — The directory prune has no age guard and no per-item failure absorption

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 2 §2 — "Prune"; Critical Implementation Details — "Reclamation safety ordering"
- **Detail**: The plan reasons carefully about in-flight writes for *files* and gives them
  `ORPHAN_MIN_AGE_MINUTES`. The prune pass inherits none of it. First,
  `FileSystemStorage.delete` absorbs `FileNotFoundError` and nothing else
  (`filesystem.py:164-169`); `os.rmdir` on a directory that became non-empty between the walk and
  the prune raises `OSError`, which propagates. The Contract wraps only the file reclaim ("each
  wrapped so one failure is a counted skip"), so one such `OSError` aborts the run after files
  have already been deleted and before the tally prints — the worst possible exit for a command
  whose contract, copied from `backfill_gpx_stats`, is "always exits 0, per-item failure is a
  tally rather than a crash." Second, `FileSystemStorage._save` calls
  `os.makedirs(directory, exist_ok=True)` and *then* `os.open(full_path, ...)`; a prune landing in
  that window removes the directory an upload is about to write into and the upload 500s — rare,
  but the same class of hazard the age guard was introduced for, applied to files only.
  `get_modified_time` reads `os.path.getmtime`, which works on directories, so the same guard is
  available at no new cost.
- **Fix**: Apply the file pass's two protections to the prune pass — wrap each `delete(dir_key)`
  so a failure is a counted skip, and require a pruned directory to be older than
  `--min-age-minutes` like a file is. Add both to the Contract text and add a Phase 2 §3 test case
  ("a directory younger than the threshold is spared").
- **Decision**: FIXED

### F4 — Phase 4's automated criterion 4.1 cannot fail

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 — Automated Verification; Progress item 4.1
- **Detail**: `grep -rn "E-11" AGENTS.md context/foundation/roadmap.md` is listed as "No stale
  reference to E-11 as an open hole survives." Phase 4 keeps a closed E-11 row in the roadmap, so
  the pattern always matches there and `grep` always exits 0 — the criterion passes whether or not
  AGENTS.md was corrected, which is the only thing it was meant to assert. Lesson 1 ("a test whose
  name claims an assertion must actually make it") applies to verification criteria too.
- **Fix**: Split it into two commands with real pass conditions: `! grep -q "E-11" AGENTS.md` and
  `grep "^| E-11" context/foundation/roadmap.md | grep -q "done ("`.
- **Decision**: FIXED

### F5 — `discard_file_by_key` is reused "unchanged" but its docstring and log line are delete-only

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 §1 — "reusing `discard_file_by_key` unchanged"
- **Detail**: Phase 1 updates the module docstring but lists no change to the helper. After
  Phase 1 the helper serves replacement as well as deletion, yet `gpx/signals.py:24` opens
  "Delete a deleted track's file by storage key", the whole docstring reasons about `Collector`
  and cascade, and `:60-63` logs "Could not delete track file". Phase 3 exists specifically to
  make that line actionable — and an operator who reads it after a failed *replacement* will go
  looking for a deleted row that is still there.
- **Fix**: Add the helper's docstring first line to Phase 1 §1's file list — one sentence naming
  both callers — and either keep the message or widen it to "Could not delete superseded track
  file".
- **Decision**: FIXED
