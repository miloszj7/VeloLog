# Detect and Reclaim Unreferenced GPX Files in MEDIA_ROOT — Implementation Plan

## Overview

Close the one *deterministic* orphan-file source in the codebase — the admin change form's
row-preserving file replacement — at the write site, then give the project its first
reconciliation instrument: a management command that can see an unreferenced file in
`MEDIA_ROOT` and, on an explicit flag, reclaim it. Finish by correcting the three documents
that currently describe a lifecycle the code does not have.

This plan implements the reframe in `frame.md`, not roadmap **E-11** as written. E-11's
observation is true and its stated cause is false; §"Phase 4" closes E-11 by correcting its
text, and the command built in Phase 2 is what covers its rollback window.

## Current State Analysis

**Two storage-write sites exist in the whole project, and exactly one `FileField`.**

| Site | Location | Row points at the file? |
| --- | --- | --- |
| GPX upload | `gpx/views.py:117`, inside `atomic()` at `:104-119` | Yes, unless the block rolls back |
| GPX admin change form | `gpx/admin.py:13-29`, default `ModelAdmin.save_model` | New file yes — **predecessor is stranded** |
| `/healthz/` probe | `velo_log/urls.py:141` | No row by design; deleted in `finally` at `:147-152` |

- **`post_delete` covers deletions and only deletions.** `gpx/signals.py:66-99` fires on
  `post_delete`, schedules `discard_file_by_key` via `transaction.on_commit`, and closes over
  `(pk, storage_key, storage)` scalars. Registering it is also the mechanism that stops the
  collector fast-deleting rows on cascade (lesson 10).
- **The admin change form strands a file on ordinary success.** `gpx/admin.py:27` excludes
  only `points`; `:29` marks only `uploaded_at` readonly — so `file` renders as an editable
  upload widget on a class whose own docstring calls itself the "read/repair path"
  (`admin.py:15`). `FileField.save_form_data` (`fields/files.py:360-368`) sets the new value
  without consulting the old one, the row is `UPDATE`d, and `post_delete` never fires.
  `gpx_upload_path` (`gpx/models.py:17`) mints a fresh `secrets.token_hex(16)` per write, so
  the new key can never overwrite the old — the strand is deterministic, not incidental.
- **Nothing in the application can enumerate the filesystem.** Zero `listdir` / `walk` /
  `scandir` / `iterdir` / `glob` calls exist across `accounts/ trips/ gpx/ velo_log/`. Every
  filesystem touch is keyed by an exact name read from the database, so detection is
  structurally unreachable rather than merely unwritten.
- **The orphan population is measured empty in both environments** (`frame.md`, 2026-08-28):
  production 4 rows ↔ 4 files exact in both directions, 1.38 MiB of content on a **500 MB**
  volume; local 3 ↔ 3 exact. The four empty `media/gpx/<owner>/<trip>/` directories are
  confirmed present locally, absent in production. That answer required a hand-rolled
  multi-step `railway service files list` walk plus a production database download — which is
  the finding, not a footnote.
- **`AGENTS.md:22` is wrong.** It enumerates the covered paths as "trip cascade, admin
  `delete_selected`, replacement upload, and any bare `QuerySet.delete()`" and names E-11 as
  "the one hole in the end-to-end claim." The admin change form is a second hole, inside a
  paragraph asserting the lifecycle is owned end-to-end.
- **No admin test exists anywhere in `tests/`** — no request to `/admin/…`, no superuser
  fixture. pytest-django 4.14.0 ships `admin_client` and `admin_user`, so the fixture itself
  needs no authoring.
- **The only runtime that exists for one-off code is a management command run by hand.**
  Interactive `railway ssh` + `uv run python manage.py <cmd>` (`DEPLOY.md:184-186`). No
  `railway run`, no release phase (`railway.json:4` is a single `startCommand`), no cron, no
  `workflow_dispatch`. `railway service files delete` is documented as refused for non-human
  callers (`DEPLOY.md:166-175`), and `infrastructure.md:82` gates volume changes made outside
  the app — a command running *inside* the container is the app acting, and clears both.

## Desired End State

1. Replacing a `GpxTrack`'s file through the admin change form — or through any other path
   that saves an existing row with a new file — removes the predecessor from storage on
   commit, exactly as a delete does today.
2. `uv run python manage.py reconcile_media` answers "are there unreferenced files under
   `MEDIA_ROOT`?" from inside the product, in one invocation, without a database download.
   With `--delete` it reclaims them and prunes the directories they leave behind.
3. A swallowed storage-cleanup failure in `gpx/signals.py` names the file it stranded in the
   log line, so it can be reclaimed by key.
4. `AGENTS.md`, `DEPLOY.md` and `roadmap.md` describe the lifecycle the code actually has —
   including the paths still *not* covered — and E-11 is closed with its cause corrected.

**Verification**: `reconcile_media` reports zero orphans against a clean tree; an admin
change-form replacement leaves exactly one file in the trip's directory; the four empty local
directories are gone after one `--delete` run.

### Key Discoveries:

- **The model-level `pre_save` signal fires before the field writes the file.**
  `Model.save_base` sends `pre_save` at `django/db/models/base.py:946-952`, *then* enters
  `_save_table`, where `FileField.pre_save` (`fields/files.py:325-339`) calls
  `file.save(file.name, file.file, save=False)` and only there does `self.name` become the
  final storage key. So at receiver time the database still holds the old key, and
  `instance.file.name` holds a not-yet-final name.
- **`old_key != instance.file.name` is a sound replacement predicate**, and this is the
  non-obvious part of Phase 1:
  - *New upload via the admin form* — `save_form_data` set `file` to the `UploadedFile`, so
    `instance.file.name` is a bare browser basename. A stored key is always a three-level
    path (`gpx/<owner>/<trip>/<32hex>.gpx`), so the two can never compare equal.
  - *Form submitted with no new file* — `forms.FileField.clean` returns `initial`, i.e. the
    existing committed `FieldFile`, so the names are equal and the receiver correctly skips.
  - *Field cleared* — `save_form_data` stores `""` (`files.py:368`, `data or ""`), which
    differs from the old key, so the predecessor is correctly reclaimed.
  - *`FieldFile.save(name, content, save=True)`* (the `make_stored_track` fixture idiom, and
    any programmatic replacement) — the file is already committed and `instance.file.name` is
    already the final key before `instance.save()` runs, so the comparison still holds.
- **The upload view is untouched by the new receiver.** `CreateView` inserts, so
  `instance.pk is None` and the receiver returns before issuing any query. The superseded rows
  are removed by `gpx/views.py:118`, which `post_delete` already covers and
  `tests/gpx/test_gpx_upload.py:310-344` already asserts. No double-scheduling.
- **`pre_save` carries `update_fields`** (`base.py:951`), so a save that cannot have touched
  `file` — e.g. `gpx/statistics.py:105`, `track.save(update_fields=list(STATS_FIELDS))` — can
  be skipped without a query.
- **Reclaim primitives are already free.** `FileSystemStorage.delete`
  (`filesystem.py:156-169`) swallows `FileNotFoundError`, so a re-run over a stale list cannot
  fail; and it calls `os.rmdir` when the target is a directory, so empty-directory pruning
  needs no new primitive — with `os.rmdir` refusing a non-empty directory, which is the safety
  property wanted.
- **`listdir` does not recurse and returns bare names** (`filesystem.py:184-193`), and raises
  `FileNotFoundError` from `os.scandir` when the directory is absent. Keys are three levels
  deep, so the walk is hand-rolled, and a missing `MEDIA_ROOT` must report zero rather than
  crash.
- **`get_modified_time` (`filesystem.py:223-224`) is the only age signal available**, and it
  is timezone-aware because `USE_TZ = True`.
- **Root log level is `WARNING` in production** (`velo_log/settings.py:248,252`), and the
  `verbose` formatter (`:232-235`) renders only `media_root` — every other `extra=` key is
  dropped. `context/archive/2026-08-26-logging-config/plan.md:85-88` records that as a
  deliberate E-06 deferral, so widening it is a pre-reasoned follow-on.
- **`velo_log/settings.py` is omitted from coverage** (`pyproject.toml:62`), so Phase 3 costs
  no coverage; `gpx/management/` is *inside* the measured source, so Phase 2 is subject to
  `fail_under = 80` with no config change.
- **No migration is required by anything in this plan**, so the CI migration guard
  (`makemigrations --check --dry-run`) is satisfied without action.

## What We're NOT Doing

- **Not moving the file write outside `atomic()`.** `frame.md` refuted it: `FileField.pre_save`
  welds `storage.save()` to the INSERT inside the same `Model.save()` field loop, and the
  orphan reproduces under plain autocommit with no transaction anywhere.
- **Not adding a hand-rolled `try/except` compensation around the upload's `with` block.** It
  covers the exception path only — process death (gunicorn `SIGABRT`/`SIGKILL`) drives the same
  rollback with no application exception — for the lowest-ranked source in the class. Phase 2's
  command covers it instead. The block stays closed.
- **Not making `file` readonly in the admin.** That would close the strand by removing the
  owner's confirmed repair path.
- **Not adding an orphan count to `/healthz/`.** The endpoint is unauthenticated and the volume
  is metered per second (`infrastructure.md:63`); a recursive walk on every anonymous
  cache-miss is a cost and availability hazard.
- **Not scheduling reclamation.** No scheduler, cron, release phase or `workflow_dispatch`
  exists to host one. Reclamation is human-triggered and on-demand.
- **Not touching the `points`/statistics columns, the parse path, or any template.**
- **Not reconciling the inverse fault** (a row whose file is gone). That direction is already
  caught, logged and answered 404 at `gpx/views.py:140-153`, and documented at
  `DEPLOY.md:110-113`.
- **Not covering `bulk_create` / `bulk_update` / `QuerySet.update(file=...)` by signal.** They
  bypass model signals by design. Phase 4 documents this rather than pretending otherwise; the
  command is the backstop.

## Implementation Approach

Two layers, deliberately, because neither is sufficient alone and the project's history shows
why. The codebase has met this problem shape five times and resolved it four ways, every one of
them prevention at the write site — and prevention only ever closed the path it was aimed at,
which is how the class stayed open. So:

- **Prevention (Phase 1)** closes the one deterministic source, in the module that already owns
  the file lifecycle, as a model-level receiver rather than a `ModelAdmin` override — so it
  covers the admin form *and* any future writer that goes through `Model.save()`, mirroring the
  existing `post_delete` design instead of bolting a fix onto one admin class.
- **Reclamation (Phase 2)** covers what prevention structurally cannot: process death mid-save,
  the two ops-restore sources that write files no application code ever touched, and every
  orphan that already exists. It is also the first thing in the project that can *answer the
  question at all*.

Phase 3 makes the one already-logged failure identifiable. Phase 4 makes the documents true.

## Critical Implementation Details

**Timing & lifecycle.** The `pre_save` receiver must schedule with `transaction.on_commit`, for
the same reason `discard_file_of_deleted_track` does (`gpx/signals.py:79-84`): a storage delete
performed inline is already gone if the surrounding block later raises, which rolls the row back
into existence pointing at a file that no longer exists. Deferring to commit also means a
rolled-back replacement correctly leaves the predecessor in place. Consequence for tests: any
assertion about file removal must wrap the request in
`django_capture_on_commit_callbacks(execute=True)` or it passes while proving nothing
(`AGENTS.md:22`).

**Reclamation safety ordering.** Within a `--delete` run, reclaim files first and prune
directories second, deepest-first — a directory is only empty *after* its orphans are gone, and
`os.rmdir` refuses a non-empty one, so the ordering is what makes the prune reach anything. Never
attempt to remove `MEDIA_ROOT` itself.

**The prune pass gets both of the file pass's protections, not neither.** `os.rmdir` refusing a
non-empty directory is a safety property only because the resulting `OSError` is caught:
`FileSystemStorage.delete` absorbs `FileNotFoundError` and nothing else
(`filesystem.py:164-169`), so a directory that became non-empty between the walk and the prune
raises straight out of `handle` — aborting the run *after* files have already been deleted and
*before* the tally prints, which is the one exit this command's contract forbids. And a directory
is as capable of being in flight as a file is: `FileSystemStorage._save` calls
`os.makedirs(directory, exist_ok=True)` and only then `os.open(full_path, …)`, so a prune landing
in that window removes the directory an upload is about to write into and the upload 500s.
`get_modified_time` reads `os.path.getmtime`, which answers for a directory exactly as it does
for a file, so the age guard costs nothing to extend.

**The set difference assumes the database and the volume are a matched pair, and nothing in the
walk can check that.** `walk(MEDIA_ROOT) - set(GpxTrack.file)` is a set of orphans only if both
halves describe the same point in time. Two states documented in this repo break that, and in
both, every file in the tree looks orphaned and is older than the age threshold by construction:
a database restored without its media (`DEPLOY.md:56` documents restoring the SQLite backup for a
schema revert with no media step; `:110` already warns the two halves must come from the same
point in time), and a misconfigured `MEDIA_ROOT` — the one fault this repo escalated to a Hard
Rule — where the walk enumerates a tree the database does not describe. The age guard says
nothing about a stale referenced set. This matters most because the runbook sits immediately
after the restore-drill material and names restore nesting as the top-ranked orphan source: it
directs an operator to the plan's one irreversible action in precisely the state where the
pairing is most likely broken. Both states produce one recognizable shape — files were found and
none of them is referenced — so the command refuses `--delete` there and requires
`--allow-full-sweep` to proceed, mirroring its existing posture of acting only on an explicit
flag. The refusal does not cover a *partial* restore where some rows survive; that is what the
runbook precondition in Phase 4 §2 is for.

**The age threshold is the only thing separating an orphan from an in-flight write.** A file
written seconds ago by a request still in `_save_table` is indistinguishable from an orphan by
set difference alone. This is also what makes walking `healthz/` safe: `/healthz/` writes and
deletes a probe file within one request, so a probe file older than the threshold is genuinely
stranded and reclaiming it generalizes the single reclamation precedent in the codebase
(`velo_log/urls.py:140`, review finding F1).

**Debug & observability.** The command reports through both channels the one existing command
uses (`backfill_gpx_stats`): `self.stderr.write` per item naming it, and a final
`self.stdout.write(self.style.SUCCESS(...))` tally. It must not rely on `logger.info` to tell an
operator anything — the production root logger is at `WARNING`.

---

## Phase 1: Prevention — reclaim a replaced file on save

### Overview

Close the row-preserving replacement strand with a `pre_save` receiver on `GpxTrack`, so
replacing a file on an existing row discards the predecessor on commit. Bring the project's
first admin test into the suite to prove it against the path that actually strands today.

### Changes Required:

#### 1. The receiver

**File**: `gpx/signals.py`

**Intent**: Add a `pre_save` receiver that detects a file replacement on an existing row and
schedules the superseded key for discard on commit, reusing `discard_file_by_key`'s body
unchanged. Update the module docstring, which currently describes the module as covering
deletions only — and the *helper's* docstring with it, which is delete-only in the same way:
`gpx/signals.py:24` opens "Delete a deleted track's file by storage key" and the paragraphs under
it reason entirely about `Collector` and the cascade. One added sentence naming both callers is
enough; the `Collector` reasoning stays, because it is still why the callback closes over scalars.

Widen the log message at `:60-63` from "Could not delete track file" to name the superseded case
too. Phase 3 exists to make exactly this line actionable, and an operator who reads the current
wording after a failed *replacement* goes looking for a deleted row that is still sitting there.

**Contract**: `@receiver(pre_save, sender=GpxTrack)` with the standard receiver signature
(`sender`, `instance`, `**kwargs`), returning `None`. Guard order matters and each guard earns
its place:

1. `kwargs.get("raw")` → return. Fixture loading must not delete files.
2. `instance.pk is None` → return. This is the insert path, i.e. every upload; returning here is
   what keeps the receiver off `gpx/views.py`'s covered path and costs it zero queries.
3. `update_fields` present and `"file"` not in it → return, before any query.
4. Read the stored key with a single deferred query — `GpxTrack.objects.filter(pk=instance.pk)
   .values_list("file", flat=True).first()` — so the `points` blob is never loaded. A `None`
   result (row not yet in the database despite a set pk) → return.
5. Falsy stored key, or stored key equal to `instance.file.name` → return.
6. Otherwise `transaction.on_commit(partial(discard_file_by_key, instance.pk, old_key,
   instance.file.storage))`.

Document in the receiver's docstring, as a named limitation rather than an omission, that
`bulk_create`, `bulk_update` and `QuerySet.update` do not send `pre_save`, so `reconcile_media`
is the backstop for them.

#### 2. Registration

**File**: `gpx/apps.py`

**Intent**: No change expected — `GpxConfig.ready` imports the whole `gpx.signals` module, so a
second `@receiver` in it registers automatically. Verify rather than assume.

**Contract**: `GpxConfig.ready` continues to import `gpx.signals`; no per-receiver wiring exists
to extend.

#### 3. Receiver tests

**File**: `tests/gpx/test_gpx_signals.py`

**Intent**: Cover the replacement predicate directly at model level, mirroring the existing
presence/absence idiom and failure-injection patterns already in this file.

**Contract**: New tests, each wrapping the mutating save in
`django_capture_on_commit_callbacks(execute=True)` and asserting with
`default_storage.exists(...)`:

- replacing a stored track's file removes the predecessor and keeps the new file;
- saving a stored track with no file change removes nothing;
- saving with `update_fields` that exclude `file` removes nothing;
- a rolled-back replacement leaves the predecessor in place (the mirror of the existing
  rolled-back-delete test at `:208-235`);
- a row whose stored key is empty schedules nothing;
- a storage failure during the replacement discard is swallowed and logged, not raised — reuse
  the `monkeypatch.setattr("django.core.files.storage.FileSystemStorage.delete", …)` injection
  at `:99-142`.

#### 4. The first admin test

**File**: `tests/gpx/test_gpx_admin.py` (new)

**Intent**: Prove the fix against the path that actually strands — a staff replacement through
the admin change form — since that is the source the frame confirmed is in live use, and no
admin request exists anywhere in the suite today.

**Contract**: Uses pytest-django's built-in `admin_client` fixture (no new conftest fixture
needed) and `reverse("admin:gpx_gpxtrack_change", args=[track.pk])`. The POST must carry every
field the change form requires: `trip`, `file`, the four bounds, and `original_filename` —
`points` is excluded from the form and the four statistics are `blank=True`. Assertions: the
response redirects, the row still exists with a new key, the predecessor key no longer exists in
storage, and the trip's directory holds exactly one file. Wrap the POST in
`django_capture_on_commit_callbacks(execute=True)`.

### Success Criteria:

#### Automated Verification:

- Lint passes: `uv run ruff check .`
- Format check passes: `uv run black --check .`
- Import order passes: `uv run isort --check-only .`
- Strict typing passes: `uv run mypy .`
- Django system check passes: `uv run python manage.py check`
- No migration is pending: `uv run python manage.py makemigrations --check --dry-run`
- Full suite with coverage passes under CI-equivalent env: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- The pre-existing upload replacement test still passes unchanged: `uv run pytest tests/gpx/test_gpx_upload.py -k replaces`

#### Manual Verification:

- Replacing a track's file through the real admin change form at `/admin/gpx/gpxtrack/<pk>/change/` leaves exactly one `.gpx` in `media/gpx/<owner>/<trip>/`
- Uploading a new track through the normal trip-detail flow still replaces its predecessor and leaves exactly one file, i.e. the new receiver did not disturb the covered path
- The trip detail page still renders the map and statistics after an admin replacement

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human before proceeding to the next phase.

---

## Phase 2: Detection & reclamation — the `reconcile_media` command

### Overview

Give the project its first instrument that can see an unreferenced file. Report by default;
reclaim only under an explicit flag, behind an age threshold; prune the empty directories left
behind.

### Changes Required:

#### 1. The age threshold constant

**File**: `gpx/constants.py`

**Intent**: Name the minimum age a file must have before reconciliation will call it an orphan,
with a comment stating what it is protecting against — a file written seconds ago by a request
still inside `_save_table`, and the `/healthz/` probe's own in-flight file.

**Contract**: `ORPHAN_MIN_AGE_MINUTES = 60`. Sized against the real upper bound on a request:
gunicorn's default 30 s timeout with the ~2 s parse entirely upstream of the write, so an hour
is roughly two orders of magnitude of headroom.

#### 2. The command

**File**: `gpx/management/commands/reconcile_media.py` (new)

**Intent**: Walk `MEDIA_ROOT` through `default_storage`, set-difference the keys found against
the keys the database references, and report the difference. Under `--delete`, discard the
orphans and then prune the directories that became empty. Lives in `gpx/` because that app owns
the stored file's lifecycle per `AGENTS.md`, and because `backfill_gpx_stats` is the pattern to
copy.

**Contract**: A `BaseCommand` subclass mirroring `backfill_gpx_stats` in shape — typed
`add_arguments(self, parser: CommandParser) -> None`, typed `handle(self, *args: Any,
**options: Any) -> None`, always exits 0, per-item failure is a tally rather than a crash.

- Arguments: `--delete` (store_true, "reclaim the orphans found rather than only reporting
  them"); `--min-age-minutes` (int, default `ORPHAN_MIN_AGE_MINUTES`, "spare files modified more
  recently than this — 0 disables the guard"); `--allow-full-sweep` (store_true, "permit
  `--delete` even when nothing on the volume is referenced — only correct when the database
  really is empty").
- **Walk**: recursive over `default_storage.listdir`, starting at `""`, yielding
  forward-slash-joined keys. `listdir` returns bare names and does not recurse
  (`filesystem.py:184-193`), so the join is the caller's job. A `FileNotFoundError` at the root
  means `MEDIA_ROOT` does not exist yet — report zero and exit 0, do not crash.
- **Referenced set**: `set(GpxTrack.objects.values_list("file", flat=True))`, minus falsy
  values. One model, one column — the project has exactly one `FileField`.
- **Scope**: the whole of `MEDIA_ROOT`, not the `gpx/` prefix. The two highest-ranked sources in
  `frame.md` (restore nesting, point-in-time skew) write outside `gpx/` by construction, so a
  prefix-scoped walk would miss them by design. No directory is excluded; the age threshold is
  the only guard, and it is what makes walking `healthz/` safe.
- **Age guard**: a candidate whose `default_storage.get_modified_time(key)` is newer than
  `timezone.now() - timedelta(minutes=min_age)` is reported as spared, not as an orphan. Reading
  the mtime of a file that vanished mid-walk raises `OSError`; treat that as spared.
- **Pairing guard**: the set difference only names orphans if the database and the media tree
  are the same point in time, and nothing in the walk can tell that they are. Before removing
  anything, check the shape both skew states produce (for the reasoning, see *Critical
  Implementation Details*): the walk found at least one file and **not one of them is
  referenced**. In that shape, `--delete` refuses — report the orphans, remove nothing, name the
  two likely causes (a database restored without its media, or a `MEDIA_ROOT` pointing at a tree
  this database does not describe) and the `--allow-full-sweep` flag that overrides, then exit 0.
  Report-only mode emits the same warning line without needing the flag, so an operator meets it
  before reaching for `--delete`. Costs one membership test over the two sets already built.
- **Reclaim**: `default_storage.delete(key)` per orphan, each wrapped so one failure is a
  counted skip. `delete` swallowing `FileNotFoundError` is what makes a re-run idempotent.
- **Prune**: after the file pass, remove empty directories deepest-first via
  `default_storage.delete(dir_key)` — `FileSystemStorage.delete` calls `os.rmdir` on a
  directory and `os.rmdir` refuses a non-empty one, so this needs no new primitive and cannot
  over-reach. Never pass `""`; `MEDIA_ROOT` itself is not a candidate. A directory is subject to
  the same two guards as a file, for the reasons in *Critical Implementation Details*: it is
  pruned only if `get_modified_time` puts it outside the age threshold, and each
  `delete(dir_key)` is wrapped so a failure is a counted skip rather than an abort —
  `os.rmdir`'s refusal to remove a non-empty directory arrives as an `OSError` that
  `FileSystemStorage.delete` does *not* absorb.
- **Reporting**: one `self.stderr.write` line per orphan and per spared file, naming the key and
  its size; a final `self.stdout.write(self.style.SUCCESS(...))` tally counting scanned,
  referenced, orphaned, spared, reclaimed, skipped and directories pruned. Report-only mode says
  plainly that nothing was removed and names the flag that would.

#### 3. Command tests

**File**: `tests/gpx/test_reconcile_media.py` (new)

**Intent**: Cover the set difference, both modes, the age guard, the prune, and the degenerate
cases. `tests/conftest.py:38-46` already points `MEDIA_ROOT` at `tmp_path` autouse, so no
`override_settings` is needed.

**Contract**: `call_command("reconcile_media", ...)` plus `capsys.readouterr()` assertions on
exact tally text, following `tests/gpx/test_gpx_statistics.py:182-207`. Cases:

- a referenced file (via `make_stored_track`) is never reported;
- a file written straight to `default_storage` with no row is reported as an orphan;
- report-only mode leaves it on disk; `--delete` removes it;
- a freshly written orphan is spared by the default threshold, and reported as an orphan with
  `--min-age-minutes 0` — control the clock by back-dating with `os.utime`, since
  `get_modified_time` reads `os.path.getmtime`;
- an orphan outside `gpx/` (the restore-nesting shape) is found;
- `--delete` prunes an emptied `gpx/<owner>/<trip>/` directory and leaves `MEDIA_ROOT` itself
  alone;
- a directory younger than the threshold is spared, on the same `os.utime` back-dating idiom as
  the file case above — the guard that keeps the prune off a directory an upload has just
  created and not yet written into;
- a directory that is non-empty at prune time is a counted skip, not a crash — `os.rmdir`'s
  `OSError` is not one `FileSystemStorage.delete` absorbs, so this is the case that would abort
  the run mid-tally if the wrapping were missing;
- a tree in which no file is referenced (the point-in-time-skew shape: back-dated orphans, no
  `GpxTrack` rows) refuses `--delete` — the files are still on disk afterwards, the tally reports
  zero reclaimed, the output names `--allow-full-sweep`, and the exit code is still 0;
- the same tree with `--delete --allow-full-sweep` does reclaim, so the override is real and not
  a permanent block;
- one referenced file alongside the orphans suppresses the refusal — this is the ordinary case,
  and the guard must not turn a normal `--delete` into a no-op;
- report-only mode over the no-file-referenced tree emits the same warning without the flag;
- a missing `MEDIA_ROOT` reports zero and exits 0;
- a `delete` that raises is a counted skip, not a crash — reuse the `FileSystemStorage.delete`
  monkeypatch idiom from `tests/gpx/test_gpx_signals.py:99-142`;
- a second `--delete` run over the same tree is a clean no-op (idempotence).

### Success Criteria:

#### Automated Verification:

- Lint, format, import order, strict typing all pass: `uv run ruff check . && uv run black --check . && uv run isort --check-only . && uv run mypy .`
- The command is registered and self-describes: `uv run python manage.py reconcile_media --help`
- The full-sweep refusal is on the command's surface, not only in its code: `uv run python manage.py reconcile_media --help | grep -q -- "--allow-full-sweep"`
- A clean tree reports zero orphans and exits 0: `uv run python manage.py reconcile_media`
- Full suite with coverage passes under CI-equivalent env: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- Coverage still meets `fail_under = 80` with `gpx/management/` in scope (reported by the run above)

#### Manual Verification:

- Run against the local working copy: the report names the four known empty
  `media/gpx/<owner>/<trip>/` directories (`1/6`, `1/7`, `1/8`, `8/12`) and no orphaned files
- `--delete` removes those four directories and leaves every referenced file untouched; the
  trip list and every trip detail page still render
- A second `--delete` run reports zero and changes nothing
- Report-only output is legible enough to act on when read as plain `railway logs`-style text
- The refusal message, read cold by someone who has not read this plan, says what state the
  volume is probably in, why reclaiming now would be wrong, and which flag overrides it

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human before proceeding to the next phase.

---

## Phase 3: Observability — make a stranded key identifiable in the log

### Overview

`gpx/signals.py:57-63` already logs when a storage delete fails, and already passes
`track_id` and `storage_key` in `extra=` — but the formatter drops both, so an operator learns
that a delete failed and never which file. Widen the formatter so the one orphan source that
already announces itself names the key you would feed to reclamation.

### Changes Required:

#### 1. The logging filter and formatter

**File**: `velo_log/settings.py`

**Intent**: Extend the existing default-injecting filter to cover `track_id` and `storage_key`
alongside `media_root`, and render them in the `verbose` format string. This is the E-06
deferral recorded at `context/archive/2026-08-26-logging-config/plan.md:85-88`, not new design.

**Contract**: `_MediaRootDefaultFilter` generalizes to default every optional context key from
one named tuple, keeping its `filter(self, record: logging.LogRecord) -> bool` signature and its
existing behavior for `media_root` exactly (unconditional rendering, empty string when absent).
The `verbose` format string gains `track_id={track_id} storage_key={storage_key}` after the
existing `media_root={media_root}`. If the class is renamed, the `"()"` dotted path in
`LOGGING["filters"]` must move with it — that string is the only reference to it.

#### 2. Filter test

**File**: `tests/test_logging_context.py` (new)

**Intent**: Prove the filter defaults each key and does not overwrite one that a caller supplied
— the assertion the widening exists to make, and there is no test on `LOGGING` today.

**Contract**: Construct a bare `logging.LogRecord`, run it through the filter, assert every
context key is present and empty; construct a second with `storage_key` already set and assert
it survives. `velo_log/settings.py` is omitted from coverage (`pyproject.toml:62`), so this test
is for correctness, not for the gate.

### Success Criteria:

#### Automated Verification:

- Lint, format, import order, strict typing all pass: `uv run ruff check . && uv run black --check . && uv run isort --check-only . && uv run mypy .`
- Django loads the logging config without error: `uv run python manage.py check`
- Full suite with coverage passes under CI-equivalent env: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- The existing `caplog`-based signal tests still pass: `uv run pytest tests/gpx/test_gpx_signals.py`

#### Manual Verification:

- A forced cleanup failure (temporarily make the media directory unwritable, delete a track)
  prints one log line naming both the track id and the storage key
- An ordinary log line unrelated to storage still formats correctly, with the new keys empty
  rather than raising a `KeyError` at format time
- Local `runserver` output is still readable — the added fields have not made routine lines
  unusable

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation from the human before proceeding to the next phase.

---

## Phase 4: Documentation and roadmap — make the written record true

### Overview

Three documents currently describe a lifecycle the code does not have. Correct them, add the
runbook entry for the new command, and close E-11 with its cause fixed rather than its fix
implemented.

### Changes Required:

#### 1. The coverage claim

**File**: `AGENTS.md`

**Intent**: Correct the `gpx/` bullet at line 22. The `post_delete` receiver is no longer the
only place a file is removed; the admin change form was never covered by it; and E-11 is no
longer "the one hole." State what the two receivers cover together, and name what neither
covers, so the next agent is not misdirected (lesson 5). Add `reconcile_media` to the
Development Commands table.

**Contract**: The rewritten bullet must say: `post_delete` covers deletions (cascade,
`delete_selected`, replacement upload, bare `QuerySet.delete()`); the new `pre_save` receiver
covers a file replaced on an existing row, which is what the admin change form does; both
schedule on commit, so a test asserting removal still needs
`django_capture_on_commit_callbacks(execute=True)`; and the paths still uncovered by signal are
`bulk_create`, `bulk_update`, `QuerySet.update(file=...)`, and process death between the storage
write and the commit — for which `reconcile_media` is the backstop. Drop the E-11 sentence. New
Development Commands row: `uv run python manage.py reconcile_media` — reports unreferenced files
under `MEDIA_ROOT`; `--delete` reclaims them and prunes emptied directories; report-only by
default.

#### 2. The runbook

**File**: `DEPLOY.md`

**Intent**: Add a section telling an operator how to answer "are there orphaned media files?"
and how to reclaim them, and record why this is done from inside the container rather than
through the Railway CLI. Place it as a new `##` section after the restore-drill material, since
the two highest-ranked sources are restore procedures.

**Contract**: A new `## Orphaned media files — detect and reclaim` section covering: the
`railway ssh` + `uv run python manage.py reconcile_media` invocation; that it is report-only
until `--delete`; a **precondition stated before the `--delete` step** — never reclaim while the
database and the volume may be from different points in time, which means after a restore of
either half, and never with a `MEDIA_ROOT` whose value has not been confirmed (cross-referencing
the `:110` point-in-time warning and the Hard Rule); that the command refuses a `--delete` run in
which nothing on the volume is referenced and that `--allow-full-sweep` is correct only when the
database is genuinely empty, never as a way past an unexpected refusal; that a partial restore
leaves surviving rows and so is *not* covered by that refusal, which is why the precondition is
the operator's responsibility; that a command inside the container is the app acting, and so
clears both the
`railway service files delete` non-human refusal (`DEPLOY.md:166-175`) and the
`infrastructure.md:82` approval gate that reclaiming through the CLI does not; the age threshold
and why `--min-age-minutes 0` should only be used on an idle service; and the 2026-08-28
measurement as the baseline (production 4 ↔ 4 exact, 1.38 MiB on a 500 MB volume) — including
that 500 MB is the only capacity figure that exists anywhere, and it is not otherwise in the
repo.

#### 3. E-11 and the roadmap

**File**: `context/foundation/roadmap.md`

**Intent**: Rewrite E-11's row so it states the true cause, then close it. Its current text
names a cause that is provably false and a fix that provably does not work, and its line cite
has drifted.

**Contract**: The Engineering Backlog table's header is
`| ID | Item | Proposed fix | Trigger | Change ID | Status | GitHub Issue |` — there is no notes
column, and E-02, E-05 and E-08 all carry their closing prose in `GitHub Issue`. Edit row `E-11`
column by column, and add no column:

- **`Item`** — correct the observation to say the storage write is welded to the INSERT by
  `FileField.pre_save`, so the orphan reproduces with no transaction at all and the atomic block
  is not the cause; fix the cite `gpx/views.py:100-113` → `gpx/views.py:104-119`, write at `:117`.
- **`Proposed fix`** — must not be left as written. It currently reads "Move the file write
  outside the atomic block, or register a compensating rollback hook", which is exactly what
  `frame.md` refuted and what this plan's "What We're NOT Doing" rejects; closing the row over it
  ships a `done` item asserting a fix that provably does not work (lesson 5). Replace it with what
  was actually built — prevention for the deterministic admin strand, reclamation for the rest —
  and say in one clause that the original proposal was refuted, so a reader who remembers the old
  text learns why it is gone rather than assuming it shipped.
- **`Trigger`** — leave as written. It named a condition that never fired, and that is true.
- **`Change ID`** — `gpx-upload-orphan-file`.
- **`Status`** — `done (<date>)`.
- **`GitHub Issue`** — the closing prose, following E-05's precedent: the measured-empty starting
  position, and that the crash window itself is now covered by reclamation rather than prevented.
  E-11 has no issue link and this plan opens none.

Leave every other row untouched, including the in-flight E-07 edit already in the working tree.

#### 4. Change status

**File**: `context/changes/gpx-upload-orphan-file/change.md`

**Intent**: Advance the change's own frontmatter as the work lands.

**Contract**: `status: planned` on plan approval, `in-progress` once Phase 1 lands, `complete`
after Phase 4; `updated:` tracks each transition.

### Success Criteria:

#### Automated Verification:

- No stale reference to E-11 as an open hole survives — `AGENTS.md` no longer names it at all, and the roadmap's row is closed rather than merely present: `! grep -q "E-11" AGENTS.md && grep "^| E-11" context/foundation/roadmap.md | grep -q "done ("` (a bare `grep -rn "E-11"` over both files cannot fail — Phase 4 keeps a closed E-11 row, so the pattern always matches there and the exit code says nothing about `AGENTS.md`)
- The command named in `AGENTS.md` actually exists and runs: `uv run python manage.py reconcile_media --help`
- Full suite still passes under CI-equivalent env: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`

#### Manual Verification:

- `AGENTS.md`'s `gpx/` bullet, read cold, correctly predicts which paths clean up a file and
  which do not
- The `DEPLOY.md` section is followable by someone who has never run the command, with no step
  requiring knowledge that is not on the page
- E-11's rewritten row would not mislead a reader who arrives at it with no other context

**Implementation Note**: This is the final phase. After automated verification passes, pause for
manual confirmation before the change is archived.

---

## Testing Strategy

### Unit Tests:

- The replacement predicate at model level: replacement, no-change, `update_fields` exclusion,
  empty stored key, `raw` save.
- Rollback: a replacement inside a block that raises leaves the predecessor in place.
- Storage-failure absorption on the replacement path — logged, never raised.
- The walk and set difference: referenced vs unreferenced, inside and outside `gpx/`.
- The age guard, driven by back-dating mtimes with `os.utime`.
- Empty-directory pruning, including that `MEDIA_ROOT` itself is never a candidate.
- Degenerate inputs: missing `MEDIA_ROOT`, empty tree, second `--delete` run.
- The logging filter's defaulting and non-overwrite behavior.

### Integration Tests:

- Admin change-form replacement end to end through `admin_client`: redirect, row updated,
  predecessor gone, one file in the trip directory.
- The normal upload flow still replaces and reclaims exactly as before — the existing
  `tests/gpx/test_gpx_upload.py:310-344` test is the regression guard for the new receiver not
  disturbing the covered path.
- `call_command("reconcile_media")` against a tree built from real fixtures, asserting the exact
  tally text on both streams.

### Manual Testing Steps:

1. Upload a GPX to a trip; confirm one file under `media/gpx/<owner>/<trip>/`.
2. Upload a second GPX to the same trip; confirm still exactly one file (covered path unchanged).
3. Replace the file through `/admin/gpx/gpxtrack/<pk>/change/`; confirm still exactly one file.
4. Run `uv run python manage.py reconcile_media`; confirm zero orphans and the four known empty
   directories reported.
5. Run it with `--delete`; confirm the four directories are gone and every trip page still
   renders.
6. Run it once more; confirm a clean no-op.
7. Write a stray file into `media/` by hand, back-date it, and confirm it is found — then that
   `--delete` reclaims it.

## Performance Considerations

- The `pre_save` receiver adds **one deferred query per `GpxTrack` update**, and none on insert
  or on a save whose `update_fields` exclude `file`. Uploads — the only hot path — are inserts,
  so they pay nothing.
- The walk is `O(files under MEDIA_ROOT)` `scandir` calls plus one `getmtime` per unreferenced
  candidate, run by hand on a volume currently holding four files. Volume I/O is metered per
  second (`infrastructure.md:63`), which is the reason this is a command rather than a
  `/healthz/` probe: it runs when an operator asks, not on every anonymous request.
- The referenced set is one `values_list` over a single column and never loads `points`.

## Migration Notes

No schema change and no migration in any phase, so `makemigrations --check --dry-run` passes
untouched. Rollback is per-phase and independent: reverting Phase 1 restores the previous
strand, reverting Phase 2 removes the command, and neither leaves data in an intermediate state.
Phase 2's `--delete` is the one irreversible action in the plan — there is no undo on the volume
— which is why report-only is the default, the age guard exists, and a run in which nothing on
the volume is referenced refuses to proceed without `--allow-full-sweep`.

## References

- Frame brief: `context/changes/gpx-upload-orphan-file/frame.md`
- Research: `context/changes/gpx-upload-orphan-file/research.md`
- The receiver to mirror: `gpx/signals.py:66-99`; the helper reused unchanged: `:23-63`
- The command to copy: `gpx/management/commands/backfill_gpx_stats.py:28-86`
- The covered replacement path, and its test: `gpx/views.py:104-119`,
  `tests/gpx/test_gpx_upload.py:310-344`
- Signal ordering and the file write: `django/db/models/base.py:946-952,1154-1170`,
  `django/db/models/fields/files.py:325-339,360-368`
- Storage primitives: `django/core/files/storage/filesystem.py:156-169,184-193,223-224`
- Test idioms: `tests/conftest.py:38-46,140-166`, `tests/gpx/test_gpx_signals.py:99-176,208-235`,
  `tests/gpx/test_gpx_statistics.py:182-207`
- Logging deferral this plan discharges: `context/archive/2026-08-26-logging-config/plan.md:85-88`
- Ops constraints: `DEPLOY.md:166-175,184-186`, `context/foundation/infrastructure.md:82`
- Origin of E-11: `context/archive/2026-08-26-edit-and-delete-trip/reviews/impl-review.md:242-270`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Prevention — reclaim a replaced file on save

#### Automated

- [x] 1.1 Lint passes
- [x] 1.2 Format check passes
- [x] 1.3 Import order passes
- [x] 1.4 Strict typing passes
- [x] 1.5 Django system check passes
- [x] 1.6 No migration is pending
- [x] 1.7 Full suite with coverage passes under CI-equivalent env
- [x] 1.8 The pre-existing upload replacement test still passes unchanged

#### Manual

- [x] 1.9 Admin change-form replacement leaves exactly one file in the trip directory
- [x] 1.10 The normal upload flow still replaces and leaves exactly one file
- [x] 1.11 Trip detail page still renders map and statistics after an admin replacement

### Phase 2: Detection & reclamation — the `reconcile_media` command

#### Automated

- [ ] 2.1 Lint, format, import order, strict typing all pass
- [ ] 2.2 The command is registered and self-describes
- [ ] 2.3 The full-sweep refusal is on the command's surface
- [ ] 2.4 A clean tree reports zero orphans and exits 0
- [ ] 2.5 Full suite with coverage passes under CI-equivalent env
- [ ] 2.6 Coverage still meets `fail_under = 80` with `gpx/management/` in scope

#### Manual

- [ ] 2.7 Report names the four known empty local directories and no orphaned files
- [ ] 2.8 `--delete` removes those directories and leaves every referenced file untouched
- [ ] 2.9 A second `--delete` run reports zero and changes nothing
- [ ] 2.10 Report-only output is legible as plain log-style text
- [ ] 2.11 The refusal message, read cold, names the likely state, why reclaiming is wrong, and the override flag

### Phase 3: Observability — make a stranded key identifiable in the log

#### Automated

- [ ] 3.1 Lint, format, import order, strict typing all pass
- [ ] 3.2 Django loads the logging config without error
- [ ] 3.3 Full suite with coverage passes under CI-equivalent env
- [ ] 3.4 The existing `caplog`-based signal tests still pass

#### Manual

- [ ] 3.5 A forced cleanup failure prints one line naming both track id and storage key
- [ ] 3.6 An unrelated log line still formats, with the new keys empty rather than raising
- [ ] 3.7 Local `runserver` output is still readable

### Phase 4: Documentation and roadmap — make the written record true

#### Automated

- [ ] 4.1 No stale reference to E-11 as an open hole survives
- [ ] 4.2 The command named in `AGENTS.md` actually exists and runs
- [ ] 4.3 Full suite still passes under CI-equivalent env

#### Manual

- [ ] 4.4 `AGENTS.md`'s `gpx/` bullet, read cold, correctly predicts which paths clean up a file
- [ ] 4.5 The `DEPLOY.md` section is followable by someone who has never run the command
- [ ] 4.6 E-11's rewritten row would not mislead a reader arriving with no other context
