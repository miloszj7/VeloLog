<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Upload a GPX file and view the route as a map

- **Plan**: `context/changes/upload-gpx-and-view-map/plan.md`
- **Scope**: Phase 4 of 6 — Upload, validation, and download (commits `2956494..fe520b6`)
- **Date**: 2026-08-25
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 6 warnings, 4 observations
- **Triage**: complete, 2026-08-25 — 8 fixed, 2 deferred (F3 to Phase 6, F7 to backlog E-06)

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Automated verification (re-run for this review)

| Gate | Result |
|---|---|
| `ruff check .` | pass |
| `black --check .` | pass — 53 files unchanged |
| `isort --check-only .` | pass |
| `mypy .` | pass — no issues in 53 source files |
| `manage.py check` | pass — 0 issues |
| `makemigrations --check --dry-run` | pass — no changes detected |
| `uv sync --locked` | pass — no lockfile drift |
| `pytest --cov` (CI-equivalent env) | **92 passed**, coverage **99.74%** (`fail_under = 80`) |
| `git status` after the suite | clean — no stray files in the working tree |

Every Phase 4 automated criterion (4.1–4.6) is backed by a named test and independently
reproduced. The load-bearing ones: `test_gpx_upload.py:55-56` asserts persisted bytes (the
`seek(0)` catcher), `test_gpx_parsing.py:77-87` and `:90-100` assert the XXE and
billion-laughs payloads are each rejected, `:9-18` pins the stdlib parser backend, and
`test_gpx_upload.py:278` / `test_gpx_download.py:61` assert cross-user 404 on both views.

## Triage outcome

| Finding | Decision | Commit |
|---|---|---|
| F1 point cap | Fixed (Fix A) | `6c3291a` |
| F2 orphan race | Fixed | `7d4a523` |
| F3 Volume gate | Deferred to Phase 6 (Progress 6.8) | `6029a1a` |
| F4 missing file 500 | Fixed | `d4df931` |
| F5 cleanup failure 500 | Fixed | `625233f` |
| F6 declared encoding | Fixed | `88c7276` |
| F7 logging | Deferred to backlog E-06 | — |
| F8 test hygiene | Fixed | `b19a453` |
| F9 coupling / URL | Fixed (documented) | `60ea2eb` |
| F10 progress stamps | Fixed | `7bbc205` |

After triage the full CI-equivalent suite passes: **102 tests, 99.77% coverage**, with ruff,
black, isort and mypy strict all clean.

## Findings

### F1 — The accepted unbounded point count now has a measurement, and Phase 5 is where it bites

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Safety & Quality
- **Location**: `gpx/parsing.py:104-127`, `gpx/models.py:30`
- **Detail**: The plan declined a point cap explicitly (`plan.md:1132-1140`: "a point cap or
  downsampling was considered and declined … If the detail page ever feels slow, point count
  is the first thing to measure"). This review measured it. A synthetic 10.00 MB GPX of
  minimal `<trkpt>` elements — accepted by every validation rule in `clean_file` — parses to
  **262,141 points in 6.6 s of blocking CPU with a 251 MB peak**, and stores a **6.00 MB JSON
  payload** in the `points` column. That column is re-read on every trip-detail render
  (`trips/views.py:70`), and per the Phase 5 placeholder at `trip_detail.html:16` it is
  destined to be inlined into the HTML via `json_script`. A 6 MB inline payload makes the page
  unrenderable *after* the upload already succeeded — which is the exact failure mode
  `gpx/parsing.py:24-27` says parse-at-upload exists to prevent. The decision was sound on the
  information the plan had; the numbers are new, and the last moment to act on them cheaply is
  before Phase 5 wires the render path.
- **Fix A ⭐ Recommended**: Add a `MAX_GPX_POINTS` constant and reject above it in `parse_gpx`, beside the existing zero-point rejection.
  - Strength: Sits at the boundary the module already owns, so the error still reaches the user at the one moment they can act on it — the stated design principle. One constant, one branch, one test; mirrors the `MAX_GPX_FILE_BYTES` precedent.
  - Tradeoff: A genuine ultra-dense multi-day track gets refused with no recourse. Picking the number needs one real tour file to calibrate against.
  - Confidence: HIGH — the rejection path, its message shape, and its test shape all already exist for the zero-point case.
  - Blind spot: Not measured against a real Garmin/Wahoo export, so the threshold is currently a guess.
- **Fix B**: Lower `MAX_GPX_FILE_MEGABYTES` from 10 to ~3, leaving the point count uncapped.
  - Strength: One-line change, no new concept; cuts parse time, peak memory, and stored payload roughly proportionally.
  - Tradeoff: Bounds the symptom by proxy rather than the quantity that actually drives render cost, and silently refuses large-but-sparse files that would render fine.
  - Confidence: MEDIUM — the ratio holds for the synthetic worst case; real files vary in bytes-per-point.
  - Blind spot: No data on how large a real multi-day tour export actually is, so 3 MB may be under a legitimate ceiling.
- **Decision**: FIXED via Fix A — `MAX_GPX_POINTS = 100_000` in `gpx/constants.py`, enforced in
  `parse_gpx` beside the zero-point rejection via a dedicated `GpxTooManyPointsError` so the
  user-facing message names the limit the way the size rejection does. Covered by
  `test_gpx_parsing.py::test_a_track_with_too_many_points_is_rejected` and
  `test_gpx_upload.py::test_a_track_over_the_point_cap_is_rejected_with_the_limit_named`. The
  plan's "What We're NOT Doing" entry and Performance Considerations section were rewritten to
  record the reversal and the measurement behind it.

### F2 — Concurrent uploads to the same trip can orphan a file on the Volume

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `gpx/views.py:91-98`
- **Detail**: `superseded = list(self.trip.tracks.all())` is evaluated at line 91, **outside**
  the `atomic()` block that opens at line 92, while the delete at line 96 is expressed as
  `exclude(pk=form.instance.pk)`. The set of rows deleted and the set of files scheduled for
  cleanup are therefore computed from different snapshots. Two concurrent POSTs to the same
  trip: A reads `superseded=[T0]`, B reads `superseded=[T0]`; A commits `TA`; B's
  `exclude(pk=TB)` then deletes **`TA`** — but `TA` is not in B's `superseded`, so no
  `on_commit` callback is ever scheduled for `TA`'s file. The row is gone, the file stays on
  the Volume permanently. SQLite's single-writer lock narrows the window but does not close
  it, since the racing read is outside the transaction entirely.
- **Fix**: Move the read inside `atomic()` as `superseded = list(self.trip.tracks.select_for_update())`, then delete by explicit pk set (`filter(pk__in=[t.pk for t in superseded])`) instead of `exclude(pk=...)`, so the rows deleted and the files scheduled are provably the same set. `select_for_update` is a no-op on SQLite, so the pk-set change is the half that carries the fix today.
- **Decision**: FIXED — the read moved inside `atomic()` as `select_for_update()` and ahead of the insert, and the delete now names the pk set that was read instead of excluding the new row. Commit `7d4a523`.

### F3 — Manual criterion 4.11 is a stated pre-merge gate marked done with no evidence

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: `plan.md:1259` (Progress 4.11)
- **Detail**: 4.11 requires `MEDIA_ROOT=/data/media` confirmed in Railway via
  `railway variables` **and** production `/healthz/` returning `"media": "ok"`, stated twice
  in the plan (§10 Intent and the success criterion) as a **before-merge** condition. It is
  checked `[x]` and stamped `7c11cf7`, but it lives entirely outside the repo and nothing in
  the diff or `DEPLOY.md` records the confirmation. This is the gate that decides whether
  uploads land on the persistent Volume or on ephemeral container disk, and merging Phase 4
  to `master` fires `deploy.yml`'s deploy job. 4.7–4.10 are also `[x]` without in-repo trace,
  but 4.7–4.9 have close automated analogues; **4.10** (the downloaded file opens in another
  GPX viewer) has none at all — byte-equality proves storage fidelity, not that a real tour
  file round-trips through a real viewer.
- **Fix**: Confirm the Railway variable and production `/healthz/` before merging, and record the confirmation (date + observed `/healthz/` body) in `DEPLOY.md`'s known-good section so the gate leaves a durable trace rather than only a checkbox.
- **Decision**: SKIPPED as a Phase 4 fix, DEFERRED to Phase 6 by the user's decision: the production deploy this gate checks is not live yet. 4.11 is unchecked again and carried over as Progress 6.8 with the reason recorded next to it; the §10 paragraph that named 4.11 as the gate now points at 6.8. Commit `6029a1a`.

### F4 — The download view 500s when the row exists but the file does not

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/views.py:120-121`
- **Detail**: `track.file.open("rb")` has no error handling. A row pointing at a missing file
  raises `FileNotFoundError` and the user gets an unhandled 500 with no application log line.
  This is not hypothetical: it is exactly the state `DEPLOY.md:73-76` now warns about — a
  database restored ahead of its media directory — and the state F2's orphan race and the
  `RAILWAY_RUN_UID` silent-write regression (`DEPLOY.md:63-70`) both produce. The runbook
  documents the incident; the code path that meets it is the one with no handling.
- **Fix**: Catch `OSError` around the open, log it, and raise `Http404` so the failure is diagnosable and matches the view's existing not-found answer.
- **Decision**: FIXED — `OSError` around the open is caught, logged with the track id and storage key, and answered with 404 to match the view's existing not-found response. Regression test `test_a_row_whose_file_is_gone_returns_404_not_500`. Commit `d4df931`.

### F5 — A failed cleanup delete turns a successful upload into a 500

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/views.py:97-98`
- **Detail**: `transaction.on_commit(partial(old.file.delete, save=False))` runs after the
  commit, synchronously, as the outermost `atomic()` exits (`ATOMIC_REQUESTS` is not set).
  `FileSystemStorage.delete` swallows `FileNotFoundError` only
  (`django/core/files/storage/filesystem.py:165-168`) — a `PermissionError` or an unmounted
  Volume propagates out of `form_valid`, so the user sees a 500 for an upload that already
  committed successfully, and the response they get contradicts the state of the database.
  There is also no log record, so accumulating orphans are invisible to an operator.
- **Fix**: Wrap the deferred delete in a module-level helper with `try/except OSError` that logs and returns. The upload succeeded; a cleanup failure must not fail the request.
- **Decision**: FIXED — the deferred delete now runs through a module-level `discard_superseded_file` helper that catches `OSError`, logs it, and returns, so a storage failure cannot fail an upload that already committed. Regression test `test_a_cleanup_failure_does_not_fail_an_upload_that_already_committed`. Commit `625233f`.

### F6 — A valid GPX declaring a non-UTF-8 encoding is rejected with a factually wrong message

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/parsing.py:61`, surfaced at `gpx/forms.py:53`
- **Detail**: `raw.decode("utf-8")` is unconditional and ignores the document's own XML
  declaration. Verified against this venv: a well-formed GPX declaring
  `encoding="ISO-8859-1"` with one accented character in a `<name>` is rejected as
  `GpxSyntaxError("The file is not UTF-8 text.")`, which reaches the user as **"That file
  could not be read as XML."** — a statement that is simply untrue of the file. Older GPS
  units and several desktop exporters still emit latin-1. Note the obvious fix does **not**
  work: `gpxpy.parse()` on raw bytes also raises `UnicodeDecodeError` (verified), because
  gpxpy decodes as UTF-8 itself — so honouring the declaration has to happen in
  `parse_gpx_bytes` before gpxpy sees anything.
- **Fix**: In `parse_gpx_bytes`, sniff the encoding from the XML declaration (or fall back to latin-1 on a UTF-8 failure) and decode accordingly, keeping the `DOCTYPE` guard where it is; give a genuinely undecodable file its own message rather than the XML one. Add a fixture for the declared-latin-1 case.
- **Decision**: FIXED — UTF-8 is still tried first; on failure `parse_gpx_bytes` consults the document's own XML declaration and decodes with what it names. Only a declaration, never a guess: latin-1 decodes anything, so a blind fallback would trade an honest rejection for silent mojibake. A new `GpxEncodingError` gives an undecodable file its own message ("That file's text encoding could not be read.") instead of the XML one. New fixture `latin1-declared.gpx`; four tests across parsing and upload. Commit `88c7276`.

### F7 — No logging anywhere in the new `gpx` package, on the first paths that need it

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `gpx/forms.py:50-55`, `gpx/views.py:97-98`
- **Detail**: No module in `gpx/` declares `logger = logging.getLogger(__name__)`, which the
  global Python standard requires. The package is internally consistent with the repo
  (`accounts/` and `trips/` have none either, and E-06 is deliberately open), but this slice
  is the first to create *silently discarded, security-relevant* events: `clean_file` converts
  a `GpxParseError` into a user message and drops the cause entirely, and the deferred file
  delete (F5) can fail with no trace. `velo_log/settings.py:184-196` already notes that a
  future `LOGGING` dict must name the `velo_log` logger — `gpx` will need adding to that list.
- **Fix**: Add module loggers to `gpx/views.py` and `gpx/forms.py`, log the rejection reason and the cleanup failures from F4/F5, and extend the settings note to name `gpx`.
- **Decision**: SKIPPED by the user's decision — logging will be added while resolving backlog row E-06 after this implementation. Partially addressed regardless: `gpx/views.py` gained a module logger under F4/F5 and both failure paths there log. What remains open is the rejection cause `clean_file` discards, and naming `gpx` in the settings note at `velo_log/settings.py:184-196`.

### F8 — Test hygiene: a shadowed fixture, a status-code-only authz test, and four missing regressions

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/gpx/test_gpx_track_model.py:10-12`, `tests/gpx/test_gpx_download.py:52-61`
- **Detail**: Three small things in an otherwise careful suite. (a) `test_gpx_track_model.py`
  redefines a `trip` fixture byte-identical to the one already in `tests/gpx/conftest.py:34-36`
  — dead weight that will drift. (b) `test_another_users_track_returns_404_not_403` asserts
  only the status code, while its sibling `tests/trips/test_trip_detail.py:33-41` also asserts
  the other rider's content does not appear in the body; the foreign track's bytes
  (`b"someone-elses-ride"`) are never checked against the response. That is the shape
  `lessons.md` rule #1 is about. (c) No test covers a hostile `original_filename` reaching
  `Content-Disposition`, a download whose file is missing (F4), a declared non-UTF-8 encoding
  (F6), or a POST with no file at all.
- **Fix**: Delete the shadowed fixture, add the no-leak assertion to the download authz test, and add the regression tests alongside whichever of F4/F6 are fixed.
- **Decision**: FIXED — the shadowed `trip` fixture is gone; the cross-user download test now asserts the other rider's bytes and filename are absent from the response, not just the status code; and the two regressions not already covered by F4 and F6 were added (a hostile `original_filename` in `Content-Disposition`, and a POST with no file). Commit `b19a453`.

### F9 — `trips` and `gpx` now import each other, and the upload URL sits under the wrong resource

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: `trips/views.py:11`, `gpx/urls.py:8`
- **Detail**: `trips.views` now imports `gpx.forms` while `gpx.models` imports `trips.models`,
  so the dependency arrow points both ways between two apps. There is no import cycle today
  (`trips.models` imports nothing from `gpx`), and the plan reasons the cross-app template
  reference explicitly at `gpx/views.py:27-30` — this is worth recording, not changing.
  Separately, the upload route resolves to `/gpx/trips/<pk>/upload/`, duplicating the `trips/`
  segment under the `gpx/` prefix, while every other trip-scoped URL lives under `/trips/`.
  URL namespacing conventionally follows the resource, not the code's home package.
- **Fix**: Leave the coupling as the deliberate decision it is, and note the URL-placement rationale next to `app_name` in `gpx/urls.py` so a reader looking for "everything that acts on a trip" knows why one route is elsewhere.
- **Decision**: FIXED as recommended — the coupling and the URL both stay; both are now explained where a reader meets them. `trips/views.py` records that `trips.models` importing nothing from `gpx` is the line that keeps the mutual dependency from becoming a cycle, and `gpx/urls.py` records why the upload route is namespaced by package rather than by resource. Commit `60ea2eb`.

### F10 — Progress stamps point at the docs commit, and `change.md` never left `impl_reviewed`

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `plan.md:1245-1262`, `context/changes/upload-gpx-and-view-map/change.md:4`
- **Detail**: All twelve Phase 4 boxes are stamped `7c11cf7`, the `DEPLOY.md` docs commit,
  though the evidence for 4.1–4.6 lives in `2956494`, `96b7480`, `45aca7a`, and `21a2f92`.
  `fe520b6`'s own body explains the choice ("the stamp names where the phase ends"), so this is
  deliberate — but only 4.12 is actually evidenced by the commit named. Separately, `fe520b6`'s
  body lists `change.md` among its files and the commit does not touch it: `change.md` has read
  `status: impl_reviewed` since `2110c32` (the Phase 3 review) and was never moved back to
  `implementing` while Phase 4 was in flight. Commit *ordering* is correct throughout —
  `fe520b6` lands after every commit it describes, satisfying `lessons.md` rule #8.
- **Fix**: Either stamp each row with the commit that actually landed it, or leave the phase-closing stamp and say so in the Progress note; and drop `change.md` from `fe520b6`'s file list if the history is ever amended.
- **Decision**: FIXED — each Phase 4 Progress row now names the commit its evidence actually landed in (`2956494`, `96b7480`, `45aca7a`, `21a2f92`, `7c11cf7`), with the convention written above the block. 4.11 is separately unchecked per F3. `change.md` is stamped `impl_reviewed` with today's date by this review. Commit `7bbc205`.

## Notes on what this review did not find

The security surface this phase exists to harden is genuinely closed, and worth recording so
a later reader does not re-derive it:

- **XML attacks** — the textual `<!DOCTYPE` pre-check (`gpx/parsing.py:89-90`) runs before any
  parser sees the text and fails closed, killing entity expansion and XXE together;
  `test_gpx_parsing.py:9-18` pins the stdlib backend so a transitive `lxml` cannot silently
  change entity semantics.
- **Path traversal** — `gpx_upload_path` (`gpx/models.py:8-17`) discards the user's filename
  entirely and builds the key from `secrets.token_hex(16)`; `test_gpx_track_model.py:77-105`
  pins that `upload_to` is actually wired to the field.
- **Header injection via `Content-Disposition`** — not reachable: Django's
  `content_disposition_header` escapes quotes and falls back to RFC 5987 encoding for anything
  outside quotable ASCII, and `sanitize_file_name` strips separators before the name is ever
  stored. The guarantee is inherited rather than owned, which is what F8(c) suggests pinning.
- **Authz** — `LoginRequiredMixin` first in MRO on both views, owner-scoped querysets giving
  404-not-403, and the upload view resolves the trip in `post()` *before* the form is touched
  so an invalid file against a foreign trip still 404s rather than confirming the trip exists.
- **XSS / CSRF** — every user value in `trip_detail.html` is auto-escaped; no `|safe`, no
  `autoescape off`, `{% csrf_token %}` present.
- **The `seek(0)` rewind** sits in a `finally` (`gpx/forms.py:56-60`), so it also rewinds on the
  rejection path, and `test_gpx_upload.py:33-56` reads the stored bytes back rather than
  asserting a status code.
- **Two deliberate plan drifts**, both behaviour-preserving and test-pinned: bounds derived from
  the retained points rather than `gpx.get_bounds()` (`gpx/parsing.py:116-126`), and the parse
  result written onto `self.instance` rather than stashed on the form (`gpx/forms.py:62-67`).
  Both are justified in-code.
- **No "What We're NOT Doing" boundary was crossed**, and no file outside the planned set was
  touched.
