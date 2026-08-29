# Detect and Reclaim Unreferenced GPX Files in MEDIA_ROOT — Plan Brief

> Full plan: `context/changes/gpx-upload-orphan-file/plan.md`
> Frame brief: `context/changes/gpx-upload-orphan-file/frame.md`
> Research: `context/changes/gpx-upload-orphan-file/research.md`

## What & Why

**VeloLog cannot detect or reclaim an unreferenced file in `MEDIA_ROOT` — and the orphan
population is dominated by paths that *succeed*, not by the crash window E-11 names.** E-11's
observation is true and its stated cause is false: the storage write is welded to the INSERT by
`FileField.pre_save`, so the orphan reproduces with no transaction at all, and its first proposed
fix does nothing. Meanwhile a deterministic orphan — the admin change form the owner uses as a
repair path — sits outside the transaction entirely, in a path `AGENTS.md` claims is covered.

## Starting Point

`gpx/signals.py`'s `post_delete` receiver covers every path that *deletes* a row, and covers it
well. It cannot cover a row that survives: the admin change form leaves `file` editable
(`gpx/admin.py:27`), `save_form_data` never consults the previous value, the row is `UPDATE`d, and
`gpx_upload_path`'s fresh `token_hex(16)` guarantees the new key cannot overwrite the old. Nothing
in `accounts/ trips/ gpx/ velo_log/` can enumerate the filesystem — every touch is keyed by an
exact name from the database — so an orphan is not merely unfixed, it is invisible. The frame
measured both environments on 2026-08-28: **zero orphans** (production 4 rows ↔ 4 files exact,
1.38 MiB on a 500 MB volume), an answer that required a hand-rolled CLI walk plus a production
database download.

## Desired End State

Replacing a track's file — through the admin form or any other path that saves an existing row —
removes the predecessor on commit, exactly as a delete does. `uv run python manage.py
reconcile_media` answers "are there unreferenced files?" from inside the product in one
invocation, and with `--delete` reclaims them and prunes the emptied directories. `AGENTS.md`,
`DEPLOY.md` and the roadmap describe the lifecycle the code actually has, including what is
still *not* covered.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Problem to solve | The orphan class and its detection, not E-11's rollback window | E-11 is rank 6 of 6 by expected bytes and requires a crash; the deterministic source is the admin form | Frame |
| E-11's first fix | Refuted, not planned | `FileField.pre_save` welds the write to the INSERT; the orphan reproduces with no transaction | Frame |
| Scope | Prevention **and** reclamation | Prevention only ever closes the path it aims at — five prior occurrences prove it, and that is how the class stayed open | Plan |
| Admin strand fix | `pre_save` receiver on `GpxTrack` | Covers the admin form and any future non-view writer in one place, mirroring the existing `post_delete` design | Plan |
| Reclaim safety | Report by default, `--delete` to act, age threshold | `DEPLOY.md` gates file deletion behind a human, and the age guard is the only way to tell an in-flight write from an orphan | Plan |
| Instrument shape | Management command | The only runtime that exists — and a command inside the container is the app acting, clearing both ops gates | Research |
| Walk scope | All of `MEDIA_ROOT`, not just `gpx/` | The two highest-ranked sources (restore nesting, PIT skew) write outside `gpx/` by construction | Research |
| E-11's disposition | Correct its text and close it; reclamation covers it | Its only expressible prevention covers the exception path alone — process death stays irreducible either way | Plan |
| Operator signal | Widen the log formatter only | Discharges the recorded E-06 deferral and makes the one already-logged orphan reclaimable by key; a `/healthz/` scan would put a recursive walk on an unauthenticated, metered path | Plan |

## Scope

**In scope:** a `pre_save` receiver closing the row-preserving replacement strand; the project's
first admin test; a `reconcile_media` command (walk, set difference, age guard, `--delete`,
empty-directory prune); widening the log formatter to render `track_id` and `storage_key`;
correcting `AGENTS.md`, `DEPLOY.md` and roadmap E-11.

**Out of scope:** moving the file write outside `atomic()` (refuted); a hand-rolled rollback
compensation in `gpx/views.py`; making `file` readonly in the admin (removes the owner's repair
path); an orphan count in `/healthz/`; any scheduler; the inverse fault (a row whose file is
gone), already handled; covering `bulk_create`/`bulk_update`/`QuerySet.update` by signal — they
bypass signals by design, and the command is their backstop.

## Architecture / Approach

Two layers, because neither suffices alone. **Prevention** at the write site, as a model-level
receiver in the module that already owns the file lifecycle — so it catches the admin form and
any future writer going through `Model.save()`, rather than bolting an override onto one
`ModelAdmin`. **Reclamation** as a hand-run command, covering what prevention structurally
cannot: process death mid-save, the two ops-restore sources that write files no application code
ever touched, and every orphan that already exists. Both discard through the same
`discard_file_by_key` helper, both schedule on `transaction.on_commit`. No schema change, no
migration, in any phase.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Prevention | `pre_save` receiver + first admin test | The replacement predicate must not fire on the upload view's covered path, or a file is deleted twice |
| 2. Detection & reclamation | `reconcile_media` command + tests | `--delete` is the one irreversible action in the plan; there is no undo on the volume |
| 3. Observability | Formatter renders `track_id` / `storage_key` | A missing default raises `KeyError` at format time for every unrelated log record |
| 4. Docs & roadmap | `AGENTS.md`, `DEPLOY.md`, E-11 closed | A half-corrected claim misdirects worse than the current wrong one (lesson 5) |

**Prerequisites:** none beyond the working tree — no new dependency, no migration, no
infrastructure change. The uncommitted E-07 roadmap edit must be left alone.
**Estimated effort:** ~2 sessions across 4 phases; Phase 1 and Phase 2 carry nearly all of it.

## Open Risks & Assumptions

- The `pre_save` predicate rests on `instance.file.name` being a bare basename before the field
  commits the file. Verified against `django/db/models/base.py:946-952` and
  `fields/files.py:325-339,360-368` in the installed 6.0.5, and it is what Phase 1's tests exist
  to pin.
- Walking `healthz/` means the age threshold is the only thing keeping `--delete` off a live
  probe file. At a 60-minute default against a probe that writes and deletes within one request,
  the margin is roughly two orders of magnitude — but `--min-age-minutes 0` is unsafe on a
  serving instance, and the runbook says so.
- The starting set is empty, so Phase 2 ships without ever having reclaimed anything real. Its
  first genuine value is the next restore drill or the next admin replacement.
- Volume capacity (500 MB) exists only in the frame's measurement; `infrastructure.md:60` records
  IOPS and never size, and E-07 — the only channel that would surface metered storage — is
  blocked on the free trial.

## Success Criteria (Summary)

- Replacing a track's file through the admin leaves exactly one file in the trip's directory, and
  the normal upload flow still behaves exactly as it did.
- One command, run inside the container, answers whether orphans exist — and can reclaim them
  without a database download or a CLI file walk.
- No document in the repo still claims a coverage the code does not have, and E-11 is closed with
  a cause a reader can trust.
