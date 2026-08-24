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
- **Decision**: PENDING

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
- **Decision**: PENDING

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
- **Decision**: PENDING

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
- **Decision**: PENDING

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
- **Decision**: PENDING

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
- **Decision**: PENDING

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
- **Decision**: PENDING

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
- **Decision**: PENDING

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
- **Decision**: PENDING

### F10 — Two tests bind to a private function name instead of asserting through HTTP

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/test_media_storage.py:118`, `:126`
- **Detail**: These two call `velo_log_urls._media_root_misconfigured()` directly, where every
  other test in the repo — including the other five in the same file — asserts through the test
  client. Both docstrings justify it (routing a real request would write into the working tree)
  and the justification is sound, but the coupling means a rename or an inline silently drops the
  only coverage of the absolute-path and DEBUG-skip branches.
- **Fix**: Promote the function to a public name (e.g. `media_root_misconfiguration()`) if it is
  going to serve as a test seam.
- **Decision**: PENDING

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
