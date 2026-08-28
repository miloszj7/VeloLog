---
date: 2026-08-28T15:29:25+0200
researcher: Miłosz Jarzynka
git_commit: d8933a8f33e84da2de05addc4b7128f1846a17ec
branch: master
repository: VeloLog
topic: "Detect and reclaim unreferenced GPX files in MEDIA_ROOT (roadmap E-11, reframed)"
tags: [research, codebase, gpx, storage, media-root, orphan-files, signals, admin, management-command, railway]
status: complete
last_updated: 2026-08-28
last_updated_by: Miłosz Jarzynka
---

# Research: Detect and reclaim unreferenced GPX files in MEDIA_ROOT

**Date**: 2026-08-28T15:29:25+0200
**Researcher**: Miłosz Jarzynka
**Git Commit**: `d8933a8f33e84da2de05addc4b7128f1846a17ec`
**Branch**: `master`
**Repository**: VeloLog

## Research Question

Following `context/changes/gpx-upload-orphan-file/frame.md`, which reframed roadmap **E-11**
from "the upload transaction's rollback window" to "**VeloLog cannot detect or reclaim an
unreferenced file in `MEDIA_ROOT`, and the orphan population is dominated by paths that
succeed**": map the whole code-level surface a plan would act on — every path that can strand
a file, everything needed to build a detection/reclamation instrument, the test and CI gates
such work must pass, the prior art for this problem shape, and how anything would actually be
run in production.

Scope confirmed by the user before research: **whole class + reclamation**, including storage
API capabilities, test/CI surface, ops runbook procedures, and archive prior art.

## Summary

Five parallel investigations (code paths, reclamation surface, test/CI, prior art, ops)
converged. The frame's reframe **holds in full**, with three refinements and one decisive new
constraint it did not have.

**What the frame got right, now verified against the working tree:**

- The atomic block is `gpx/views.py:104-119`, the write is at `:117` — the roadmap's cite of
  `gpx/views.py:100-113` is stale, as the frame said.
- The admin change form is a **deterministic, live orphan source**: `gpx/admin.py:27` excludes
  only `points` and `:29` marks only `uploaded_at` readonly, so `file` is an editable upload
  widget; there is no `save_model` override, and Django has never auto-deleted a `FieldFile`'s
  previous value on reassignment. `post_delete` fires on DELETE, not UPDATE.
- **Nothing in the application can enumerate the filesystem.** Zero `listdir`/`walk`/`scandir`/
  `iterdir`/`glob` calls exist in `accounts/ trips/ gpx/ velo_log/`; the only hits in the repo
  are two test files. Detection is structurally absent, not merely unwritten.
- **No admin test exists anywhere** in `tests/`. No `admin_client` fixture, no superuser
  fixture, no request to `/admin/…`.
- **No admin-action precedent exists**: zero hits for `actions =`, `@admin.action`, or
  `get_urls` across the repo.

**Three refinements to the frame:**

1. **The logging formatter does not drop everything — it renders exactly one key.**
   `velo_log/settings.py:192-203` installs `_MediaRootDefaultFilter`, and the `verbose`
   formatter at `:232-235` renders `media_root={media_root}` unconditionally. `track_id` and
   `storage_key` are dropped because they are absent from the format string, and
   `context/archive/2026-08-26-logging-config/plan.md:85-88` shows this was a **deliberate
   deferral**, not an oversight. Widening it is a precedented, cheap edit — not new machinery.
2. **Row-preserving replacement is narrower than the frame's dimension 2.** The *upload view's*
   replacement path is covered and tested: `gpx/views.py:113` snapshots superseded rows under
   `select_for_update()` inside the block and `:118` deletes them by explicit pk, firing
   `post_delete`; `tests/gpx/test_gpx_upload.py:310-344` asserts the predecessor file is gone.
   **Only the admin change form strands a file.** The class is one path, not a family.
3. **Root log level is `WARNING` in production** (`velo_log/settings.py:248,252`). Any
   reclamation instrument that reports at `INFO` produces nothing an operator can see in
   `railway logs`.

**The decisive new constraint the frame did not have — how anything runs in production:**

The only mechanism that exists today to execute code against the deployed app is an
**interactive `railway ssh` session** followed by hand-typing `uv run python manage.py <cmd>`
(`DEPLOY.md:184-186`, documented once, for `createsuperuser`). There is no `railway run`, no
release phase (`railway.json:4` is a single `startCommand`), no cron or scheduler anywhere in
the repo, and no `workflow_dispatch` on the one GitHub workflow
(`.github/workflows/deploy.yml:3-9`). Two further gates:
`railway service files delete` is documented as **refused for non-human callers**
(`DEPLOY.md:166-175`), and `context/foundation/infrastructure.md:82` requires human approval
for "any change to the Volume-mounted SQLite file outside the app itself."

That last clause is the load-bearing distinction for the plan: **a management command running
inside the container *is* the app itself acting**, and so sits on the permitted side of both
gates — whereas reclaiming files through the Railway CLI does not. It also means any
reclamation is necessarily **human-triggered and on-demand**; an automated sweeper has no
runtime to live in, and would have to be built before it could be scheduled.

## Detailed Findings

### 1. Every path that can put a file in MEDIA_ROOT

There are exactly **two** storage-write sites in the whole project, and exactly **one**
`FileField`.

| Site | Location | Row points at it? |
| --- | --- | --- |
| GPX upload | `gpx/views.py:117` (inside `atomic()` at `:104-119`) | Yes, unless the block rolls back |
| GPX admin change form | `gpx/admin.py:13-29` (default `ModelAdmin.save_model`) | New file yes — **predecessor is stranded** |
| `/healthz/` probe | `velo_log/urls.py:141` | No row by design; deleted in `finally` at `:147-152` |

- **`GpxTrack.file`** — `gpx/models.py:29`, `FileField(upload_to=gpx_upload_path, max_length=255)`.
  `gpx_upload_path` (`gpx/models.py:8-17`) returns
  `f"gpx/{instance.trip.owner_id}/{instance.trip_id}/{secrets.token_hex(16)}.gpx"` — 128 bits of
  randomness, so a replacement key can **never** collide with its predecessor. The strand is
  deterministic, not incidental, exactly as the frame argued.
- **No other `FileField`/`ImageField` exists** in `accounts/`, `trips/`, or `gpx/`. The
  "referenced set" for any reconciliation is therefore trivially
  `GpxTrack.objects.values_list("file", flat=True)` — one model, one column, no union.
- **Parsing precedes the write.** `gpx/forms.py:36-94` parses in memory in `clean_file`
  (`:60`), with `finally: uploaded.seek(0)` at `:78-82` rewinding for the later storage write.
  Nothing is on disk until `form.save()`. This confirms the frame's timing argument: the ~2 s
  parse at the point cap sits entirely *upstream* of the orphan window.
- **The upload's write/insert weld.** `gpx/views.py:117` is `super().form_valid(form)`;
  `FileField.pre_save` writes to storage inside the same `Model.save()` that then issues the
  INSERT. Everything in the block: `:113` snapshot under `select_for_update()`, `:117` write +
  insert, `:118` delete superseded by pk. If `:118` raises, the row rolls back and the file
  stays. That is E-11, and it is one file per failed upload.

### 2. The admin change form — the live, deterministic strand

- `GpxTrackAdmin` (`gpx/admin.py:13-29`): `raw_id_fields = ("trip",)` (`:26`),
  `exclude = ("points",)` (`:27`), `readonly_fields = ("uploaded_at",)` (`:29`). **`file` is
  neither excluded nor readonly** — it renders as an editable file input.
- **The class states the intent in its own docstring**: `"""Admin read/repair path for the
  GpxTrack model."""` (`gpx/admin.py:15`). The frame inferred from the owner's Step 4 answer
  that the admin is used as a repair path; the code says so directly. Every field-narrowing
  decision in the surrounding comments (`:17-26`) is reasoned about unbounded rendering — the
  superseded file is never considered.
- Any edit here must keep the `mypy --strict` + `django-stubs` shim at `gpx/admin.py:1-10`:
  `admin.ModelAdmin[GpxTrack]` under `TYPE_CHECKING`, bare `admin.ModelAdmin` at runtime. A
  `save_model` override would need its signature typed against that generic base.
- No `save_model` override, no custom action. A staff replacement calls `instance.save()`
  directly: the new file is written under a fresh `token_hex` key, the row is `UPDATE`d, and
  **nothing consults or deletes the old key**.
- `delete_selected` on either `GpxTrackAdmin` or `TripAdmin` (`trips/admin.py:13-22`) *is*
  covered — the `post_delete` listener forces the collector to materialize rows, so per-row
  cleanup is scheduled.
- **`AGENTS.md:22` is wrong about this.** It enumerates the covered paths as "trip cascade,
  admin `delete_selected`, replacement upload, and any bare `QuerySet.delete()`" and names
  E-11 as "the one hole." The admin change form is a second hole, in a paragraph that claims
  the lifecycle is owned end-to-end. Per lesson 5 (`context/foundation/lessons.md`), a stale
  `AGENTS.md` claim actively misdirects the next agent.
- **Corroborating trace, weak but worth recording**: `tests/trips/__pycache__/test_admin_manual_check.cpython-314-pytest-9.1.1.pyc`
  (dated 2026-08-23) is the compiled artifact of a local admin test that was **never
  committed** — `git log --all -- tests/trips/test_admin_manual_check.py` returns nothing.
  Consistent with the frame's Step 4 finding that the owner drives the admin by hand.

### 3. The signals receiver — what it does and does not cover

`gpx/signals.py:66-99`, registered via `gpx/apps.py:8-18`.

- Fires on `post_delete` only. Closes over `(pk, storage_key, storage)` scalars (`:92,97-99`),
  never the instance — the memory fix from `9548b67`.
- Schedules via `transaction.on_commit` (`:97-99`), so a rolled-back *delete* correctly leaves
  the file (proved by `tests/gpx/test_gpx_signals.py:208-235`).
- `discard_file_by_key` (`:23-63`) catches bare `Exception` (`:59`) — deliberately wider than
  `OSError`, per `c517b8b` — logs `logger.exception(..., extra={"track_id", "storage_key"})`
  (`:60-63`) and **never re-raises**. A storage failure here therefore produces an orphan
  silently, and the two `extra=` keys that would identify it are dropped by the formatter
  (§5 below).
- **Never removes parent directories.** `gpx/<owner_id>/<trip_id>/` dirs accumulate empty.

### 4. What the storage API actually offers (Django 6.0.5, installed)

`STORAGES["default"]` is `django.core.files.storage.FileSystemStorage`
(`velo_log/settings.py:157-164`), so the concrete backend — not the abstract base — is what
matters. From `.venv/Lib/site-packages/django/core/files/storage/filesystem.py`:

| Capability | Location | Behavior relevant to a reclaim instrument |
| --- | --- | --- |
| `listdir(path)` | `:184-193` | `os.scandir` on `self.path(path)`; returns `(directories, files)` **names only**, and **does not recurse**. Keys are 3 levels deep, so a walk must be hand-rolled. |
| `delete(name)` | `:156-169` | Raises `ValueError` on falsy name; **`os.rmdir` if the target is a directory**, else `os.remove`; **swallows `FileNotFoundError`**. |
| `exists(name)` | `:181-182` | `os.path.lexists`. |
| `path(name)` | `:195-196` | `safe_join(self.location, name)` — traversal-safe. Implemented here; the base class raises `NotImplementedError` (`base.py:131-137`). |
| `size(name)` | `:198-199` | `os.path.getsize`. |
| `get_modified_time(name)` | `:217-224` | Timezone-aware (`USE_TZ = True`). **This is the only available age signal** — relevant if a plan wants to spare a file mid-upload. |

Two consequences worth naming:

- **Idempotent reclaim is free** — `delete()` swallowing `FileNotFoundError` means a
  re-run over a stale list cannot fail on already-removed keys.
- **Empty-directory pruning is free too** — `delete()` calling `os.rmdir` on a directory means
  the frame's rank-4 item needs no new primitive, only a call. Note `os.rmdir` refuses a
  non-empty directory, which is the safety property you want.

`MEDIA_ROOT` derives from `env_or("MEDIA_ROOT", str(BASE_DIR / "media"))`
(`velo_log/settings.py:169`), where `env_or` (`:25-35`) treats a blank env var as unset.

### 5. Logging — precisely what an operator would see

- `_MediaRootDefaultFilter` (`velo_log/settings.py:192-203`) injects `media_root=""` onto any
  record missing the key; the `verbose` formatter (`:232-235`) renders `media_root={media_root}`
  unconditionally.
- **Every other `extra=` key is dropped**, including `track_id` and `storage_key` from
  `gpx/signals.py:62`, `gpx/views.py:149-152`, and
  `gpx/management/commands/backfill_gpx_stats.py:73`.
- `context/archive/2026-08-26-logging-config/plan.md:85-88` records this as an explicit
  out-of-scope decision for E-06, not a defect — so widening the formatter is a known,
  pre-reasoned follow-on rather than a new design question.
- Root level is `INFO if DEBUG else WARNING` (`:248,252`). Handler is a single
  `StreamHandler` on stdout (`:239-240`) — no file handler, no persistence. Logs are readable
  only by tailing `railway logs` (`context/foundation/infrastructure.md:83`).

### 6. The reference pattern for a management command

`gpx/management/commands/backfill_gpx_stats.py` (86 lines, read in full) is the only command in
the project and the template any new one should follow:

- `add_arguments` with a single `--all` boolean (`:28-36`).
- `.only(...)` field deferral to avoid loading the `points` blob, then `.iterator()`
  (`:47-59,63`) — memory-safe streaming.
- **Per-row failure is a tally, not a crash**: `try/except Exception` around the per-row
  helper, `logger.exception(..., extra={"track_id": ...})`, counted as skipped (`:64-75`).
- **Dual reporting channel**: `self.stderr.write` per skip naming the row (`:84`) plus a final
  `self.stdout.write(self.style.SUCCESS(...))` summary (`:86`).
- Always exits 0, even with skips. Idempotent by construction.

`gpx/management/` is **inside** the measured coverage source (`pyproject.toml:61-67` lists the
whole `gpx` package; `omit` names only `velo_log/*` files), so a new command is subject to
`fail_under = 80` with no config change. There is **no per-file lint/type dispensation** for
`*/management/*` — full `ruff` (`select = ["E","W","F","I","B","C4","S"]`) and `mypy --strict`
apply, as they already do to `backfill_gpx_stats`.

### 7. The `/healthz/` probe — and why it is a poor host for a scan

`velo_log/urls.py`, read in full:

- `_media_round_trips` (`:126-152`) defensively deletes the fixed key (`:140`), saves
  (`:141`), reads back the **returned** name rather than the constant (`:142-143`, the F1 fix),
  and deletes in a `finally` (`:147-152`) that logs and swallows failures.
- `media_root_misconfiguration` (`:97-123`) is a pure location check, skipped under `DEBUG`.
- Verdict cached 30 s in LocMem (`:53-54,177-182`); response is JSON with 200/500 (`:189-200`).
- **It has no notion of file counts or disk usage** — it is a binary reachability probe.
- The endpoint is **unauthenticated**. A recursive `listdir` walk added here would run on every
  anonymous cache-miss request, on a volume metered per-second
  (`context/foundation/infrastructure.md:63`). That is a cost and availability hazard, not a
  neutral placement choice.

To extend it at all: add a field to `_HealthVerdict` (`:57-67`), a probe function, a call in
`_probe_health()` (`:155-166`), and fold into `ok`/`payload` in `healthz()` (`:184-200`).

### 8. Test surface — exact templates that exist, and the one gap

**MEDIA_ROOT isolation is automatic**: `tests/conftest.py:38-46`, autouse
`_media_root_in_tmp_path`, sets `settings.MEDIA_ROOT = str(tmp_path / "media")` through the
`settings` fixture (which fires `setting_changed` and resets cached `default_storage`). No
`override_settings` needed anywhere.

Reusable fixtures (`tests/conftest.py`):

- `make_stored_track` (`:140-166`) — creates a row **and writes real bytes** via
  `track.file.save(name, ContentFile(content), save=True)`. This is the fixture for anything
  that must see a file on disk.
- `make_gpx_track` (`:104-137`) — row with a file *name* only, no bytes. Useful for
  constructing the "row references a missing file" direction.
- `rider`, `other_rider`, `auth_client` (`:88-101`); `gpx_bytes`, `trip`
  (`tests/gpx/conftest.py:16-32`).

Assertion idioms already in use:

- On-commit capture — `with django_capture_on_commit_callbacks(execute=True):` wrapping the
  mutating call, at `tests/gpx/test_gpx_signals.py:43,68,92,132,172,202,227`. Without it a
  file-removal assertion passes while proving nothing (`AGENTS.md:22`).
- File presence — `default_storage.exists(stored_name(track))` before/after
  (`tests/gpx/test_gpx_signals.py:21-29`).
- Storage failure injection —
  `monkeypatch.setattr("django.core.files.storage.FileSystemStorage.delete", refuse_delete, raising=True)`
  (`tests/gpx/test_gpx_signals.py:99-142`, and a `SuspiciousFileOperation` variant at
  `:145-176`).
- **Replacement already tested for the upload path** —
  `test_a_second_upload_replaces_the_first_and_removes_its_file`
  (`tests/gpx/test_gpx_upload.py:310-344`) is the direct template for testing any new
  supersede-on-save hook.
- **Command testing** — `call_command("backfill_gpx_stats")` plus `capsys.readouterr()`
  asserting exact `captured.err` skip lines and `captured.out` tally
  (`tests/gpx/test_gpx_statistics.py:143,160,176,182-207`).

**The gap**: no admin test exists. No `admin_client` fixture, no `create_superuser` fixture,
no request to `/admin/…` anywhere in `tests/`. Testing an admin change-form fix means
introducing a superuser fixture and `reverse("admin:gpx_gpxtrack_change", args=[pk])` as a
first-of-its-kind pattern.

### 9. CI gates a change here must clear

`.github/workflows/deploy.yml`, `gates` job, in order: vendored-asset `sha256sum -c`
(`:30-32`, before `uv sync`) → `uv sync --locked` (`:37-38`) → `ruff` (`:40-41`) → `black
--check` (`:43-44`) → `isort --check-only` (`:46-47`) → `mypy` (`:49-50`) → `manage.py check`
(`:52-53`) → **`makemigrations --check --dry-run`** (`:55-56`) → `collectstatic --noinput`
(`:61-62`) → `pytest --cov` (`:64-65`). Deploy runs only on `push`, `needs: gates` (`:67-86`).
Job env: `SECRET_KEY=ci-check-only-not-a-real-secret`, `DEBUG=False`, `ALLOWED_HOSTS=""`
(`:17-20`) — no `.env`.

Relevant: a new signal receiver, a `save_model` override, or a management command requires
**no migration**, so the migration guard is satisfied without action. `pyproject.toml:69-71`
sets `fail_under = 80`; `tests/test_coverage_scope.py` guards only against a *new app* missing
from `source`, which does not apply here.

### 10. Ops — how anything is actually run or observed in production

| Question | Answer today | Evidence |
| --- | --- | --- |
| Run a one-off command? | Interactive `railway ssh` + `uv run python manage.py <cmd>`, by hand. Nothing else. | `DEPLOY.md:184-186`; no `railway run` anywhere in repo |
| Release/pre-deploy hook? | None. `railway.json` has one key: `startCommand` = `collectstatic && migrate && gunicorn`. | `railway.json:4` |
| Scheduler / cron / dispatch? | **None anywhere.** One workflow, triggers `push` + `pull_request` on `master` only. | `.github/workflows/deploy.yml:3-9` |
| Delete a stray file via CLI? | **Refused for non-human callers**; a person must run `MSYS_NO_PATHCONV=1 railway service files delete -y …`. | `DEPLOY.md:166-175` |
| Change Volume files outside the app? | Requires human approval. Agents may run `railway logs`, routine `railway up`, read-only checks. | `context/foundation/infrastructure.md:82` |
| Disk usage / file count signal? | None in the codebase. `/healthz/` is binary reachability only. Railway dashboard or a manual `railway service files list`. | `velo_log/urls.py:189-200`; `DEPLOY.md:132` |
| Log persistence? | None configured — stdout only, tailed via `railway logs`. | `velo_log/settings.py:239-240`; `infrastructure.md:83` |
| Gunicorn concurrency? | Unconfigured → defaults: 1 sync worker, 30 s timeout. | `railway.json:4` (absence) |

The **2026-08-26 restore drill** (`DEPLOY.md:138-175`, closing E-05) is the precedent the frame
ranked #1: `files upload <media-dir> /data/media` created a nested
`/data/media/<backup-name>/` and **reported success** while restoring nothing Django could see
(`:151`). `--overwrite` fixes the file case but not the directory-nesting case (`:152`). The
runbook also states plainly that **no scratch-target restore path exists** — "the only way to
rehearse it is to risk the real thing" (`:160-164`). A scripted reclamation routine that used
`files upload/download` carelessly could recreate exactly the mess it exists to clean.

`context/foundation/infrastructure.md:60` records the volume's 3,000 IOPS cap and single-region
single-instance model but **never its size**; the frame's production measurement (500 MB,
holding 1.38 MiB) remains the only capacity figure available, and it is not in the repo.
E-07 — the `$5` spend alert, the sole channel through which metered volume storage could ever
surface — is still `open` and un-reverified since 2026-08-21 (`roadmap.md:159`,
`DEPLOY.md:193-197`).

## Code References

- `gpx/views.py:104-119` — the upload `atomic()` block; `:113` superseded snapshot under
  `select_for_update()`, `:117` file write + INSERT, `:118` delete superseded by pk
- `gpx/views.py:136-158` — download view; `:141` open, `:149-153` log + `Http404` on missing file
- `gpx/models.py:8-17` — `gpx_upload_path`, `secrets.token_hex(16)` key
- `gpx/models.py:29` — the project's only `FileField`
- `gpx/forms.py:36-94` — parse in `clean_file`, entirely before any storage write; `:78-82` rewind
- `gpx/signals.py:23-63` — `discard_file_by_key`, bare-`Exception` swallow at `:59`, log at `:60-63`
- `gpx/signals.py:66-99` — the `post_delete` receiver; `:97-99` `on_commit` scheduling
- `gpx/admin.py:26-29` — `raw_id_fields` / `exclude = ("points",)` / `readonly_fields` — `file` left editable
- `gpx/management/commands/backfill_gpx_stats.py:28-86` — the command reference pattern
- `velo_log/settings.py:157-164` — `STORAGES`; `:169` `MEDIA_ROOT`; `:192-203,232-235` logging filter + formatter; `:248,252` root level
- `velo_log/urls.py:97-152` — media misconfiguration check and probe round-trip; `:155-200` verdict assembly
- `.venv/.../django/core/files/storage/filesystem.py:156-169,181-199,217-224` — `delete`/`exists`/`listdir`/`path`/`size`/`get_modified_time`
- `tests/conftest.py:38-46,104-166` — autouse tmp `MEDIA_ROOT`, `make_gpx_track`, `make_stored_track`
- `tests/gpx/test_gpx_signals.py:21-29,99-176,208-235` — presence idiom, failure injection, rollback mirror
- `tests/gpx/test_gpx_upload.py:310-344` — supersede-and-remove template
- `tests/gpx/test_gpx_statistics.py:182-207` — `call_command` + `capsys` tally assertions
- `.github/workflows/deploy.yml:17-20,30-65` — gate env and gate order
- `pyproject.toml:38-42,48-51,61-71` — ruff select, mypy strict, coverage source and `fail_under`

## Architecture Insights

- **The project's convention for this problem shape is prevention at the write site, and it has
  never once been reconciliation.** Five prior occurrences, four fixed that way — F1 (healthz
  probe, plus the one reclaiming delete in the codebase at `velo_log/urls.py:140`, never
  generalized), F2 (`7d4a523`), the delete lifecycle (`d746f0f`, refined by `c517b8b` and
  `9548b67`), and E-11 accepted rather than fixed (`6b10cee`). Prevention only ever closes the
  path it was aimed at, which is why the class stayed open.
- **Registering a signal receiver is a mechanism, not just a hook** (lesson 10). The
  `post_delete` listener is what forces `Collector.can_fast_delete()` to return `False` and
  materialize rows on cascade. A `pre_save` receiver on `GpxTrack` would be the architecturally
  consistent way to cover row-preserving replacement — it would catch the admin change form and
  any future non-view write path in one place, mirroring the existing design rather than
  bolting a `save_model` override onto one `ModelAdmin`.
- **The instrumentation asymmetry is total.** The inverse fault — a row whose file is gone — is
  caught, logged with context, and answered 404 (`gpx/views.py:141-153`, `d4df931`), documented
  at `DEPLOY.md:110-113`, and tested (`tests/gpx/test_gpx_download.py:109` deliberately unlinks
  a file). The orphan direction has no log line, no doc line, and no test.
- **A management command is the only instrument whose runtime already exists.** It has a
  precedent to copy, lands inside the coverage source, needs no migration, and executes inside
  the container — the side of `infrastructure.md:82`'s approval gate that does not require a
  human decision per invocation. The alternatives each require inventing something: an admin
  action has zero precedent and zero admin test coverage; a `/healthz/` check would put an
  unauthenticated recursive scan on a metered volume.
- **The PRD is silent on this entire concern.** No mention of storage limits, retention, or
  operational cost; the closest text is the NFR "Data never lost" (`prd.md:42`). Orphan files
  originate purely from implementation-time review findings, so there is no product requirement
  to size the work against — only the volume's bytes.

## Historical Context (from prior changes)

- `context/archive/2026-08-23-upload-gpx-and-view-map/reviews/impl-review-phases-1-2.md:40-102`
  (F1) — the `/healthz/` probe discarded `save()`'s return value, leaving
  `probe_<suffix>.txt` files "nobody deletes"; fixed by capturing `saved`. `:244-256` (F8)
  pinned the probe to a single fixed key.
- `.../reviews/plan-review.md:169-186` (F4) — storage deletes do not participate in the DB
  transaction; fixed by moving to `transaction.on_commit`. `:227-242` (F7) — "Django has not
  deleted `FileField` files on model delete since 1.3."
- `.../reviews/impl-review-phase-4.md:98-114` (F2) — the concurrent-upload race: two POSTs, B's
  `exclude(pk=...)` deletes A's row with no callback scheduled; "the row is gone, the file stays
  on the Volume permanently." Fixed by `7d4a523`.
- `context/archive/2026-08-26-edit-and-delete-trip/reviews/impl-review.md:242-270` (F10, origin
  of E-11) — **accepted via Fix A**, recorded as a backlog row rather than fixed. Fix B ("move
  the write outside `atomic()` or add a compensating rollback hook") was declined at MEDIUM
  confidence, with the reviewer's own blind spot recorded: "Haven't worked out whether moving
  the write out breaks the 'new row and file saved first' invariant." The frame has since
  refuted Fix B's first half outright.
- `context/archive/2026-08-26-logging-config/plan.md:85-88` — `gpx/views.py`'s
  `extra={"track_id", "storage_key"}` deliberately left unrendered; only `media_root` was in
  scope for E-06.
- Commits: `7d4a523` (pk-set delete under `select_for_update`), `d746f0f` (the receiver),
  `c517b8b` (non-`OSError` absorption), `9548b67` (bind callback to key, not instance),
  `6b10cee` (docs-only, records E-11), `d4df931` (404 on missing file). All six resolve.
- Roadmap: **E-11** `open` (`roadmap.md:163`, stale cite `gpx/views.py:100-113`), **E-07**
  `open` (`:159`, spend alert un-reverified, itself citing a stale `DEPLOY.md:43`), **E-05**
  `done (2026-08-26)` (`:157`, the restore drill), **E-06** `done` (`:158`, logging).

## Related Research

- `context/changes/gpx-upload-orphan-file/frame.md` — the framing brief this research serves;
  its hypothesis table, bytes/year ranking, and the 2026-08-28 production measurement (4 rows ↔
  4 files, zero orphans; 500 MB volume holding 1.38 MiB) are inputs here, not re-derived.
- `context/archive/2026-08-23-create-and-list-trips/research.md:174` — earlier note confirming
  the workflow has no `workflow_dispatch`.

## Open Questions

1. **Is E-11 itself worth building?** It is rank 6 of 6 by expected bytes, requires a crash, has
   never fired, and its only expressible fix is a hand-rolled `try/except` around the `with`
   (needed because `connection.commit()` can raise in `Atomic.__exit__`, where no in-block
   handler sees it). The plan may reasonably close E-11 by *correcting its text* and covering
   the class elsewhere. That is a scoping decision, not a research finding.
2. **What triggers a reclamation run, given no scheduler exists?** On-demand via `railway ssh`
   is the only option today. Whether the plan accepts that, or also builds a signal that tells
   an operator a run is *warranted* (a count in `/healthz/`'s payload, a `WARNING` log line),
   is open — and note the root logger is at `WARNING` in production, so anything quieter is
   invisible.
3. **Should the command default to dry-run?** No precedent exists either way;
   `backfill_gpx_stats` mutates by default. Given `DEPLOY.md:166-175` gates file deletion behind
   a human, a report-only default with an explicit `--delete` flag would keep the destructive
   step deliberate, but this is the plan's call.
4. **How is "recently written" distinguished from "orphaned"?** A file written seconds ago by an
   in-flight upload is indistinguishable from an orphan by set difference alone.
   `get_modified_time` (`filesystem.py:217-224`) is the only available age signal; an age
   threshold would be the standard guard, but none is established here.
5. **Should the admin change form be fixed, or the field simply made readonly?** Removing `file`
   from the editable set closes the strand without new machinery, but removes the owner's
   confirmed repair path. A `pre_save` receiver preserves the path and covers future writers.
6. **The 2026-08-26 restore-drill stray tree** — the frame's production enumeration found no
   timestamp-named directory at `/data` or `/data/media`, so it was either never left or already
   reclaimed. Recorded as resolved-by-observation; no action indicated.
7. **Volume capacity is still undocumented in the repo.** `infrastructure.md:60` records IOPS,
   never size. The 500 MB figure exists only in the frame's measurement, and E-07 — the one
   channel that would ever surface metered storage — remains un-reverified.

## A Note on References

Local `path:line` references are used throughout rather than GitHub permalinks. Every reference
is a live pointer the next step (`/10x-plan`) will open in this working tree, and the frame this
document extends uses the same convention; converting ~120 anchors to permalinks would make both
documents harder to read for no gain at the point of use.
