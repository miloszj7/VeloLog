<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Upload a GPX file and view the route as a map

- **Plan**: `context/changes/upload-gpx-and-view-map/plan.md`
- **Scope**: Phases 1–2 of 6 (Storage and media foundation; the `gpx` app and the `GpxTrack` model)
- **Commits**: `507ca9a`, `f4a599b`, `54b06a4`
- **Date**: 2026-08-24
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 6 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Gate results (run fresh, 2026-08-24)

| Gate | Result |
|---|---|
| `ruff` / `black --check` / `isort --check-only` | pass |
| `mypy .` (strict, django-stubs) | pass — 41 files |
| `manage.py check` | pass — 0 issues |
| `makemigrations --check --dry-run` | clean |
| CI-equivalent `pytest --cov` | 44 passed, TOTAL 99.50% (`fail_under = 80`) |
| `tests/test_coverage_scope.py` | pass — `gpx` in scope |

All 12 planned change items across the two phases (Phase 1 §1–§6, Phase 2 §1–§6) were verified
against their stated Contract and match. No planned item is missing, no "What We're NOT Doing"
boundary is crossed, and no runtime dependency was added. The findings below are all things the
plan did not anticipate or did not require proving.

## Findings

### F1 — `/healthz/` media probe accumulates orphan files and can misreport, contradicting its own comment

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `velo_log/urls.py:78-97` (comments at `:33-36`, `:80-82`)
- **Detail**: The comment at `:33-36` claims "A fixed key bounds that failure mode at one file"
  and `:80-82` claims "Deleting before saving keeps the write off `get_available_name`". Both are
  false when two probes overlap. `Storage.save()` *always* calls `get_available_name()`;
  `FileSystemStorage._save()` opens `O_EXCL` and retries under a suffixed name on
  `FileExistsError`. The return value of `default_storage.save(...)` at `:87` is discarded, and
  the `finally` at `:95` deletes only the constant `HEALTHZ_MEDIA_KEY`. Reproduced against this
  repo's Django by interleaving a second writer between the probe's delete and its save:

  ```
  probe reported ok: True
  files left behind: ['probe.txt', 'probe_H5A7Ai2.txt']
  ```

  `probe_H5A7Ai2.txt` is never deleted by anything. Three consequences, all on the persistent
  Railway Volume the app depends on: unbounded orphan accumulation drivable by an anonymous
  caller (the exact failure mode the fixed key was chosen to prevent); a *false positive* where
  the read-back succeeds against the other probe's identical payload while this probe's write
  went elsewhere; and a *false negative* 500 on a healthy store when the other probe's `finally`
  deletes the key between this one's save and open.

  **Mitigating context, verified**: `railway.json:4` starts gunicorn with no `--workers` flag, so
  production runs a single sync worker unless `WEB_CONCURRENCY` is set in the Railway
  environment. Requests therefore serialize today and the race is latent, not live. It becomes
  live the moment a worker count, a threaded worker, or a second replica is added — none of which
  would look like a change to this code.
- **Fix**: Capture the name `save()` actually returned and use it for both the read-back and the
  `finally` delete (`saved = default_storage.save(...)`; `default_storage.open(saved)`;
  `default_storage.delete(saved)`). Keep the fixed key as the prefix so the accumulation bound
  the comment wants is real, and correct the two comments to describe what the code does. Add the
  regression test that would have caught this: pre-create a stale `probe.txt`, hit `/healthz/`,
  assert `MEDIA_ROOT/healthz/` is empty afterwards — it fails today.
  - Strength: Removes the leak, the false positive and the false negative in one change; the
    corrected code then matches the reasoning the plan already committed to in writing.
  - Tradeoff: Small — four lines plus a comment rewrite and one test.
  - Confidence: HIGH — the failure was reproduced, not inferred, and the fix is the standard
    Django idiom of trusting `save()`'s return value.
  - Blind spot: Whether Railway sets `WEB_CONCURRENCY` in this project's environment has not been
    checked, so "latent today" rests on `railway.json` alone.
- **Decision**: FIXED — `_media_round_trips` now captures `save()`'s return value and uses it for
  both the read-back and the `finally` delete (guarded on `saved is not None`, since a failed save
  wrote nothing); the fixed key is kept as the opening delete, which reclaims a file stranded by a
  probe that died before its cleanup. The two false comments (`velo_log/urls.py:33-36`, `:80-82`)
  were rewritten to describe what the code does.

  One deviation from the Fix as written: the proposed regression test (pre-create a stale
  `probe.txt`, assert the directory is empty afterwards) **passes today** — the opening delete
  reclaims the stale file, so that path was never broken. The failing case is the interleaving
  itself, so `test_healthz_reads_back_and_deletes_the_name_save_returned` drops the probe's *first*
  `delete` (`_ConcurrentProbeStorage`) to model a second probe re-taking the key in that window.
  Verified failing against pre-fix `velo_log/urls.py` (500 ≠ 200, plus the orphaned
  `probe_<suffix>.txt`) and passing after. The `saved is not None` guard means `_BrokenStorage` no
  longer reaches the `finally` cleanup branch, so `_CleanupFailsStorage` plus
  `test_healthz_survives_a_cleanup_that_cannot_delete` keeps that branch covered.

  Gates re-run after the fix: ruff / black / isort / `mypy` (41 files) / `manage.py check` /
  `makemigrations --check` all clean; CI-equivalent `pytest --cov` 46 passed (was 44), TOTAL
  99.51%, `velo_log/urls.py` still 100%.

### F2 — A verbatim copy of `.env.example` sends uploads into the repo root, unignored

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `velo_log/settings.py:149`, `.env.example:26`
- **Detail**: `MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))` returns the
  default only when the key is *absent*. `.env.example` ships it *present and blank*
  (`MEDIA_ROOT=`), and django-environ returns the empty string for a blank key — verified:
  `env('MEDIA_ROOT', default='FALLBACK')` → `''`. `FileSystemStorage` then resolves
  `location = os.path.abspath("")`, i.e. the process CWD. A local `runserver` upload therefore
  writes `gpx/<owner>/<trip>/<hex>.gpx` into the **repo root**, where the `media/` entry added in
  Phase 1 §6 does not match it — defeating that change's stated intent ("the next `git add` would
  commit a user's GPX file"). Under `DEBUG=True` the location guard short-circuits at
  `velo_log/urls.py:65-66`, so `/healthz/` reports 200 throughout. In production this is caught
  loudly by the `is_absolute()` branch, so the exposure is local only. The `.env.example` comment
  ("Defaults to media/ in the project root if unset") is accurate for *unset* and wrong for
  *blank*, which is how the file ships. `DB_PATH` carries the same shape but fails loudly at
  connect time.
- **Fix**: Make the settings line treat blank as absent —
  `env("MEDIA_ROOT", default="") or str(BASE_DIR / "media")` — and ship the key commented out in
  `.env.example`. Per `CLAUDE.md`, the `.env.example` edit must be handed to the user with line
  numbers, not written directly.
  - Strength: Fixes it at the source, so any future blank value (Railway included) also falls
    back rather than silently resolving to CWD.
  - Tradeoff: Diverges cosmetically from the `DB_PATH` line one screen above.
  - Confidence: HIGH — the empty-string return was reproduced directly.
  - Blind spot: Whether the same hardening is wanted for `DB_PATH` in this slice, or left for a
    separate change.
- **Decision**: FIXED — the blind spot was resolved in favour of hardening both keys in this
  slice. Rather than repeat `env(K, default="") or <fallback>` at two call sites, the rule is
  stated once as `env_or(key, fallback)` in `velo_log/settings.py`, and `DB_PATH` and `MEDIA_ROOT`
  both route through it. `DB_PATH` was the weaker half — verified that
  `django/db/backends/sqlite3/base.py:156` rejects an empty `NAME`, so it always failed loudly —
  but leaving it alone would have left the two adjacent lines gratuitously asymmetric.

  Extracting the helper is also what made the rule testable: both settings resolve at import time
  and `tests/conftest.py` re-points `MEDIA_ROOT` per test, so nothing in-process can observe what
  a blank key produces. `tests/test_settings_env.py` covers absent / blank / set against the
  helper, plus a subprocess that resolves both settings with the keys blank from a foreign cwd —
  so re-inlining either call site fails rather than passing on the helper's own coverage. Verified
  in both directions: with the call sites reverted the wiring test fails on
  `media_root == ''`; with them wired it passes.

  `.env.example` was handed to the user per `CLAUDE.md` and verified via `git diff` before
  staging. Note this half turned out **not** to be load-bearing: once blank resolves to the
  fallback, the blank key was already harmless. It was kept for the documentation signal — a
  commented-out key reads as an override to opt into, which leaves `SECRET_KEY` and
  `ALLOWED_HOSTS` as the only keys blank on purpose. The prose in `settings.py` and the test that
  cited `.env.example` as the reason for the rule was rewritten in the same commit, since the
  template no longer ships blanks.

  Landed as three commits, fixes before this record: `00f2682` (helper, both call sites, tests),
  `b0573cd` (template plus the prose it invalidated), then this one. Gates after each: ruff /
  black / isort / `mypy` (42 files) / `manage.py check` / `makemigrations --check` clean;
  CI-equivalent `pytest --cov` 50 passed (was 46), TOTAL 99.51%.

### F3 — No test proves `upload_to=gpx_upload_path` is actually wired to the field

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `tests/gpx/test_gpx_track_model.py:13`
- **Detail**: `_make_track` assigns `file="gpx/1/1/deadbeef.gpx"` as a hardcoded string, and
  `gpx_upload_path` is only ever called *directly* (`:57`, `:70-71`). No test ever saves a real
  file through the `FileField`. Changing `upload_to` to a different function, or removing it
  entirely, leaves all six tests green — and the path would then be built from the user-supplied
  filename, which is precisely the security property `gpx/models.py:9-16` documents.
  `gpx/models.py` reports 100% coverage while this hole is open, which is `lessons.md` #3 firing
  verbatim. `tests/test_media_storage.py:1-9` argues in its own docstring that settings-shaped
  assertions are worthless and "every test below does the real thing instead" — the model tests
  do not hold that line, and now that `default_storage` works they can.
- **Fix**: Add one test that saves through the field with a hostile name and asserts the
  generated path: `track.file.save("../../etc/passwd.gpx", ContentFile(b"<gpx/>"), save=True)`,
  then assert `track.file.name.startswith(f"gpx/{trip.owner_id}/{trip.pk}/")`, that `"passwd"` is
  absent from the name, and that the persisted bytes read back.
- **Decision**: FIXED in `80af474` —
  `test_saving_through_the_field_routes_the_name_through_gpx_upload_path` saves real bytes through
  the descriptor and asserts the stored name, that the row carries it too, and that the bytes read
  back.

  **The hostile filename the Fix specified is the wrong probe, and the test uses a benign one
  instead.** With `upload_to` removed, the hostile version does fail — but on
  `SuspiciousFileOperation` from Django's own `get_valid_name`, which rejects traversal before
  anything reaches `gpx_upload_path`. That asserts Django's guard, not ours, and would keep
  passing if `upload_to` were swapped for any other function. `ride.gpx` is a name storage would
  happily keep verbatim, so the assertions can only pass if `gpx_upload_path` actually replaced
  it. Verified in both directions: wired, 7 pass; with `upload_to` deleted from the field, it
  fails on the stored name being `'ride.gpx'`. Hostile-input coverage was already present at
  `tests/gpx/test_gpx_track_model.py:57` via the direct call, so nothing was lost.

  `FieldFile.name` is `str | None`, so the name is bound and narrowed with an explicit
  `is not None` before use — required by `mypy --strict`, and a real assertion in its own right
  since a saved file must have a name.

  Gates: ruff / black / isort / `mypy` (42 files) / `manage.py check` / `makemigrations --check`
  clean; CI-equivalent `pytest --cov` 51 passed (was 50), TOTAL 99.51%.

  Note this closes only the `upload_to` half of the coverage hole. F7 — `points` and the four
  bounds never round-tripped through the database — is the same `_make_track` shortcut and was
  still PENDING when this decision was written; it was fixed afterwards in `e85c19c`.

### F4 — `/healthz/` performs unthrottled DB and volume I/O for any anonymous caller

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `velo_log/urls.py:100-121`
- **Detail**: Every anonymous GET now runs a session INSERT + SELECT + DELETE (pre-existing), two
  `Path.resolve()` calls, and **four** filesystem operations against the mounted Volume
  (`delete`, `save`, `open`+read, `delete`). Nothing rate-limits it. On SQLite's single writer
  lock a burst of anonymous probes serializes against real user writes and is a plausible source
  of `database is locked` for logged-in users; the media half adds Volume I/O on top. The plan
  specified the round-trip but never weighed it against the endpoint being unauthenticated.
  Separately, `FileSystemStorage._save` calls `os.makedirs(..., exist_ok=True)` while only the
  *file* is deleted, so the first probe permanently creates `MEDIA_ROOT/healthz/` on the
  production Volume. Mitigating: `railway.json` sets no `healthcheckPath`, so a 500 here does not
  gate a deploy.
- **Fix A ⭐ Recommended**: Cache the verdict for a short window — run the full round-trip at most
  once every N seconds and return the cached result otherwise.
  - Strength: Bounds the cost per unit time regardless of request rate, keeps the endpoint
    anonymous and useful to an external monitor, and needs no auth scheme invented.
  - Tradeoff: The reported verdict can be up to N seconds stale.
  - Confidence: MEDIUM — the shape is right, but the window has to be picked against whatever
    monitor interval is eventually used, which is not decided yet.
  - Blind spot: With more than one worker the cache is per-process, so the effective rate is
    N seconds × worker count.
- **Fix B**: Split the endpoint — a cheap unauthenticated liveness response, and the full
  round-trip behind a shared-secret query token.
  - Strength: Removes the anonymous cost entirely rather than bounding it, and pairs naturally
    with fixing the disclosure in F5.
  - Tradeoff: Introduces a secret to manage, and any external monitor must be reconfigured to
    carry it.
  - Confidence: MEDIUM — depends on what is actually probing this URL, which is unknown.
  - Blind spot: Whether anything outside Railway currently polls `/healthz/` has not been checked.
- **Decision**: FIXED via Fix A. Both blind spots were resolved before deciding. Nothing polls this
  URL — `railway.json` sets no `healthcheckPath` and `deploy.yml` never curls it; every reference
  in `DEPLOY.md` (`:9`, `:10`, `:47`, `:56`) is a human checking it by hand after a deploy or a
  restore. That removed Fix B's "external monitor must be reconfigured" cost *and* Fix A's "keeps
  it useful to an external monitor" strength, so neither survived as stated. The start command
  passes no `--workers`, so gunicorn runs one and a per-process cache is service-wide today —
  unless the platform injects `WEB_CONCURRENCY`, which is not visible from the repo; the bound
  merely loosens to N × workers if it does.
  What actually decided it: the probe is expensive *on purpose*. Only a real write proves the
  Volume is mounted and writable, which is the failure it exists to catch, so the work cannot be
  made cheaper without discarding the point of it. The only lever left is frequency — which is
  caching. Fix B was also weaker than written: its "pairs naturally with F5" claim does not hold,
  since F5's fix stands alone and needs no token.
  Implemented as a 30-second cache over a `_HealthVerdict` dataclass rather than over the rendered
  response, so F5 can reshape the body without touching what is cached.
  Two consequences recorded rather than fixed: `FileSystemStorage._save` still creates
  `MEDIA_ROOT/healthz/` once on the Volume — caching changes nothing there — and the cached verdict
  is stale by up to 30s, which costs nothing because both consumers restart the process first and
  no `CACHES` setting exists, so LocMem is cleared on restart.
  The fix silently gutted an existing test: `test_repeated_probes_leave_no_files_behind` drives
  three probes, and with the cache in place only the first did real I/O — it would have passed
  against a cleanup that stranded a file on every call. Restored by clearing the cache per
  iteration. Both that test and the new cache test were mutation-checked: disabling the cache fails
  the new one, removing the probe's `finally` cleanup fails the restored one.

### F5 — `/healthz/` discloses the absolute server media path to anonymous callers

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `velo_log/urls.py:117`, `:120`
- **Detail**: The endpoint has no auth (`velo_log/urls.py:127`) and the body now always carries
  `"media_root": "/data/media"`, plus a `media_error` string that repeats the path and leaks
  `BASE_DIR` semantics. Absolute filesystem layout is standard recon material to chain with any
  later traversal or LFI bug, and Phase 4 adds exactly such a filesystem-touching surface. The
  plan asked for the body to "report the resolved `MEDIA_ROOT`" but did not weigh that against
  the endpoint being anonymous — so this is a plan-level gap, not an implementation slip.
- **Fix**: Log the path and the reason via `logger.error`, and return only coarse verdicts to the
  caller (`"media": "misconfigured"`, plus a stable machine code such as
  `"media_error": "not_absolute"` / `"inside_base_dir"`). Gate the literal path on
  `settings.DEBUG` if it is wanted for local convenience.
- **Decision**: FIXED as written. `media_root_misconfiguration` returns `"not_absolute"` /
  `"inside_base_dir"`; the path reaches the response only under `DEBUG`.
  One judgement call inside the fix: the path goes to the log via `extra=`, per the project
  logging rule, rather than interpolated into the message. That was chosen knowing it makes the
  path **invisible in production today** — F9 is precisely that no `LOGGING` dict exists, so this
  logger falls through to `logging.lastResort`, whose formatter renders the message and drops
  `extra`. Until E-06 lands, the path is withheld from the caller and not yet visible in the log.
  `_media_root_context`'s docstring carries that obligation so E-06 cannot drop it silently; this
  tightens F9 from a note into a concrete requirement.
  Both halves of the `DEBUG` gate were mutation-checked — disclosing unconditionally and never
  disclosing each fail a different test.
  **Two plan statements are now stale, one of them load-bearing.** Phase 1 §5 (`plan.md:333`) says
  the test asserts `/healthz/` "names the media root as the reason"; it now asserts the code. That
  is wording only — the intent, asserting an outcome rather than a settings read, is intact.
  The original sentence is left standing rather than rewritten, since Phase 1 is complete and its
  contract is a record of what was agreed; a "Superseded after implementation" note beneath it
  states what the test asserts now.
  The second was load-bearing and has been amended. **Phase 4's** manual criterion
  (`plan.md:804`, mirrored at Progress 4.11) required that "production `/healthz/` reports that
  media root" before the phase merges; production runs `DEBUG=False`, so that check could no
  longer be performed as written. Phase 4 has not run yet, so this was a live obligation. It now
  reads that production `/healthz/` returns `"media": "ok"` — a stronger check than the
  original, because a passing verdict *proves* the guard accepted the root as absolute and
  outside `BASE_DIR`, where reading the echoed string only proved it had been printed.

### F6 — The gates cannot see F1: 100% statement coverage, no branch coverage, no cleanup assertion

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `pyproject.toml` (`[tool.coverage.run]`), `tests/test_media_storage.py`
- **Detail**: `velo_log/urls.py` sits at 100% statement coverage while F1 — a defect in the exact
  line the surrounding comment is defending — goes undetected. Of the plan's three Phase 1 §3
  probe contracts, only one is actually proven: nothing asserts the write overwrites rather than
  suffixing, nothing asserts N probes leave ≤1 file, and the `finally` test proves only that a
  failing cleanup's *exception is swallowed*, not that the file is *gone*. `[tool.coverage.run]`
  also does not set `branch = true`, so the short-circuit at `velo_log/urls.py:110`
  (`misconfigured is None and _media_round_trips()`) reads as fully covered from a single path.
  This is `lessons.md` #3 recurring on a second slice.
- **Fix**: Add `branch = true` to `[tool.coverage.run]`, and add a
  `test_healthz_leaves_no_probe_file_behind` assertion alongside the F1 regression test.
- **Decision**: FIXED — both halves applied, but **two of this finding's claims did not survive
  checking** and are corrected here:

  1. **The branch-coverage claim was wrong.** F6 asserted the short-circuit at
     `velo_log/urls.py:110` "reads as fully covered from a single path". Run with
     `--cov-branch`, `velo_log/urls.py` reports 8 branches and **0 partial** — both sides are
     covered, by the misconfigured-root test and the healthy-path test respectively. `branch =
     true` was still added, but as a forward guard for code not yet written, not because it
     closed a gap. The comment in `pyproject.toml` says so, rather than implying it caught
     something.
  2. **Part of the test half had already landed under F1.** `8dfdee6` added
     `test_healthz_reads_back_and_deletes_the_name_save_returned`, which covers the "probe
     deletes what it wrote" contract for the concurrent case.

  What was genuinely still open was F6's *accumulation* contract — nothing asserted that N
  sequential probes leave the directory empty. `test_repeated_probes_leave_no_files_behind` does
  that now. Verified in isolation that it bites: with the probe's `finally` cleanup replaced by
  `pass`, it fails on a leftover `probe.txt`. The remaining sub-claim — "nothing asserts the write
  overwrites rather than suffixing" — is covered transitively, since a suffixing write whose
  cleanup targets the wrong name is exactly what leaves files behind.

  Gates: ruff / black / isort / `mypy` (42 files) / `manage.py check` / `makemigrations --check`
  clean; CI-equivalent `pytest --cov` 53 passed (was 52), TOTAL 99.53% with branch mode now on by
  default.

### F7 — `points` and the four bounds are never round-tripped through the database

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `tests/gpx/test_gpx_track_model.py`
- **Detail**: `_make_track` assigns `POINTS` in memory and no test calls `refresh_from_db()` or
  re-reads `.points` from a fresh query, so nothing proves the `JSONField` returns
  `list[list[float]]` rather than a string on SQLite. Phase 5's entire map render depends on that
  shape, and the plan chose four explicit `FloatField`s over a nested blob specifically so the
  types would be unambiguous — a property no test currently checks.
- **Fix**: `assert GpxTrack.objects.get(pk=track.pk).points == POINTS`, plus the same for the four
  bound floats.
- **Decision**: FIXED — `test_points_and_bounds_survive_a_round_trip_through_the_database` re-reads
  from a fresh query and pins the values *and* the types: every coordinate in `points` and all four
  bounds must be `float`. Value equality alone would already catch a JSON string, but the property
  the plan actually relies on is the type, so it is asserted rather than inferred.

  Verified the test bites, rather than assuming it would: with `points` redeclared as a
  `TextField`, it fails on the reloaded value being the string
  `'[[50.06, 19.94], [50.07, 19.95]]'`. That is the plausible regression — the SQLite column is
  text either way, so nothing else in the suite would have noticed.

  Together with F3 this closes the `_make_track` shortcut in both directions: the file field is now
  exercised through a real save, and the JSON and float columns through a real read.

  Gates: ruff / black / isort / `mypy` (42 files) / `manage.py check` / `makemigrations --check`
  clean; CI-equivalent `pytest --cov` 52 passed (was 51), TOTAL 99.51%.

### F8 — `GpxTrackAdmin` changelist is tuned; the change form is not

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/admin.py:18-19`
- **Detail**: The changelist is correct — `list_select_related = ("trip",)` covers `list_display`,
  and `Trip.__str__` returns `self.name` only (`trips/models.py:20-21`), so there is no
  second-hop N+1 on `owner`; `points` is correctly excluded. The *change form* is untouched: it
  renders a `<select>` containing every `Trip` in the database across all users, and the full
  unbounded `points` JSON in a textarea. For the "read/repair path" the plan intends, that
  degrades as data grows.
- **Fix**: Add `raw_id_fields = ("trip",)` (or `autocomplete_fields` once `TripAdmin` gains
  `search_fields`) and `readonly_fields = ("points", "uploaded_at")`.
- **Decision**: FIXED, with the fix corrected on two points as it was applied. `raw_id_fields =
  ("trip",)` landed as written. `points` went to `exclude`, not `readonly_fields`: readonly stops
  the editing but still renders the whole JSON payload into the page, so it would not have
  addressed the degradation this finding's own Detail describes. `uploaded_at` is `auto_now_add`
  and therefore already absent from the form — naming it in `readonly_fields` protects nothing, so
  it stays only to make the timestamp visible on a repair page. Consequence accepted deliberately:
  adding a `GpxTrack` by hand through the admin now fails, because `points` is NOT NULL with no
  default. That is the intended direction — tracks arrive through the upload flow, and the admin is
  a read/repair path. `manage.py check` passes, so the admin system checks accept the combination.

### F9 — The new logger has no configured handler, and E-06 could silently remove its last one

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `velo_log/urls.py:31`, `:51`, `:90`, `:96`
- **Detail**: The three broad `except Exception` blocks are right for a health probe, and
  `logger.exception` is the right call in each. But there is no `LOGGING` dict in
  `velo_log/settings.py` (E-06 is deliberately open, and adding one would have breached "What
  We're NOT Doing"), so `velo_log.urls` propagates to a handler-less root and is served by
  `logging.lastResort` → stderr. That works today. When E-06 lands a `LOGGING` dict scoped to
  `django`/`django.server`, handler scoping or `disable_existing_loggers` can silently swallow the
  *only* diagnostic channel this probe has — the response body deliberately carries no detail for
  the store-unreachable case.
- **Fix**: Note the coupling in a comment beside the media settings block, so E-06 adds an
  explicit `velo_log` logger entry rather than discovering this later.
- **Decision**: FIXED, and noted in both places rather than one. The finding's fix put the note in
  `velo_log/settings.py`, which is where the dict gets written; it is also on the E-06 row in
  `roadmap.md`, which is where the work gets picked up. A note in only the first is not read until
  someone has already decided how to scope the dict.
  The obligation is larger than the finding stated, because F5 landed in between. It is no longer
  only "add a `velo_log` logger": the media path now travels as `extra={"media_root": ...}` and
  `logging.lastResort` renders the message alone, so that field is **already invisible** rather
  than merely at risk. E-06 therefore owes a formatter that emits it as well. Both halves are
  written out in each place.
  Deliberately not fixed here: no `LOGGING` dict was added. The plan's "What We're NOT Doing"
  excludes it and E-06 owns it — this records the constraints so E-06 inherits them instead of
  rediscovering them after an incident.

### F10 — Two tests bind to a private function name instead of asserting through HTTP

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/test_media_storage.py:118`, `:126`
- **Detail**: These two call `velo_log_urls.media_root_misconfiguration()` directly, where every
  other test in the repo — including the other five in the same file — asserts through the test
  client. Both docstrings justify it (routing a real request would write into the working tree)
  and the justification is sound, but the coupling means a rename or an inline silently drops the
  only coverage of the absolute-path and DEBUG-skip branches.
- **Fix**: Promote the function to a public name (e.g. `media_root_misconfiguration()`) if it is
  going to serve as a test seam.
- **Decision**: FIXED — `_media_root_misconfigured` renamed to `media_root_misconfiguration` across
  all four sites (`velo_log/urls.py` definition and `healthz` call site, both test call sites). The
  seam is now a deliberate public name rather than a private one reached around, so a future rename
  has to confront the tests instead of silently orphaning the absolute-path and DEBUG-skip branches.
  The tests keep asserting against the function directly — routing them through `/healthz/` would
  write the probe file into the working tree, which is exactly what the location guard exists to
  prevent.

## Notes carried forward (no finding)

- **`f4a599b` was a test-only defect, not a production one.** The original Phase 1 assertion
  depended on `BASE_DIR / "media"` not pre-existing — a directory a local `runserver` hit on
  `/healthz/` leaves behind. It was flaky on a dirty tree and blind on a clean one: had the
  location guard stopped short-circuiting, the probe would have written inside an already-existing
  directory and the assertion would have had nothing to detect. The fix re-points the root at a
  path guaranteed not to pre-exist and widens the assertion, which is strictly stronger in both
  directions. Phase 1 manual criterion 1.8 was stamped `[x]` in the same commit that shipped that
  test — the criterion was true as written (the *suite* leaves no strays) and still missed the
  interaction, because the leftover comes from `runserver`.
- **Doc edits in the diff are legitimate chain-stamping, not Phase 6 encroachment.**
  `roadmap.md`'s two lines are the S-03 slice status only, which Phase 6 §2 explicitly excludes
  from its amendment set; `change.md` moved `plan_reviewed` → `implementing`; `plan.md` is
  checkbox stamping for Phases 1–2 alone. No PRD, `AGENTS.md` or `DEPLOY.md` edit — all correctly
  deferred.
- **Plan text is stale in one place**: Phase 1 §6 says `media/` sits beside `backup/db/`; the tree
  already widened that to `backup/` in `39cc2e3`. The implementation is right, the plan sentence
  is not.
- **Orphan GPX files on trip delete** remain correctly deferred to S-04, as the plan's Migration
  Notes and the test comment at `tests/gpx/test_gpx_track_model.py:41-42` both record.
- **No upload size bound exists anywhere yet**, as the plan accepts explicitly under "What We're
  NOT Doing". `railway.json` sets no gunicorn body limit. The decision point is Phase 4's merge.
