<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Edit and Delete a Trip (S-04) + Future-Date Validation (E-08)

- **Plan**: `context/changes/edit-and-delete-trip/plan.md`
- **Scope**: All 5 phases (full plan review)
- **Date**: 2026-08-27
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 5 warnings, 5 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Success criteria re-run (all green)

Re-executed independently of the Progress checkboxes, under the CI-equivalence command:

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `black --check .` | 61 files unchanged |
| `isort --check-only .` | clean |
| `mypy .` | Success, no issues in 61 source files |
| `manage.py check` | no issues |
| `makemigrations --check --dry-run` | No changes detected (no migration needed or missing) |
| `collectstatic --noinput` | 142 unmodified, 377 post-processed |
| `pytest --cov` | **157 passed**, total coverage **99.80%** (baseline 99.78% — no regression) |
| 2.3 `grep discard_superseded_file\|handed to S-04` | no hits |
| 5.8 `git diff --name-only master...HEAD -- context/archive/` | empty |
| 4.6 future-date literals in new tests | none — all computed from `timezone.localdate()` |
| 5.5 commit ordering | every fix commit precedes the p5 decision commit |

Only uncovered line repo-wide is `trips/models.py:22` (`Trip.__str__`) — pre-existing, not
introduced by this change.

Manual criteria: every `- [x]` in `## Progress` has observable evidence in the diff or in a
test (e.g. 3.11 → `test_trip_delete.py:44`, 4.9 → `test_trip_creation.py:164`,
2.8/2.9 → `test_gpx_signals.py:74`). No rubber-stamping found.

## Scope discipline (no finding, recorded for the record)

`git diff --name-only master...HEAD -- static/ templates/ trips/templates/trips/trip_list.html
trips/models.py trips/admin.py` returns **empty**. Every "What We're NOT Doing" boundary held:
no CSS, no `message.tags` rendering, no edit/delete controls on the trip list (asserted absent
at `test_trip_edit.py:66`), no model change, no soft delete, no permission mixin, no deletion
audit log, no start/end date split.

Three additions the plan did not name, all benign and all justified:
`trips/constants.py` (satisfies the global magic-value rule and mirrors `gpx/constants.py`
exactly in shape); the help-text `<div>` at `trip_form.html:35` (without it, Phase 4's own
criterion "the date field **renders** a help text on the page" is unmeetable — the field loop
emits `label_tag`/`field`/`errors` only); and `model = Trip` at `trips/views.py:123`
(redundant with the `get_queryset` override two lines below).

## Findings

### F1 — `except OSError` is narrower than the receiver's own stated contract

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/signals.py:37`
- **Detail**: The docstring promises "never letting the attempt fail the request", but
  `FileSystemStorage.delete` calls `self.path(name)` before touching the filesystem
  (`.venv/.../files/storage/filesystem.py:156-159`), and `path()` goes through `safe_join`,
  which raises `SuspiciousFileOperation` — a subclass of `Exception`, **not** `OSError`. A
  non-filesystem backend (S3/boto) raises `ClientError`, also not `OSError`. Either escapes the
  `on_commit` callback and produces a 500 for a delete the database has already committed —
  the exact contradiction the module exists to prevent. `test_gpx_signals.py:113` raises
  `PermissionError`, which *is* an `OSError`, so the test cannot detect this gap.
  Verified: the `ValueError("The name must be given")` branch is **not** reachable —
  `FieldFile.delete` early-returns on an empty name (`fields/files.py:108-110`).
- **Fix**: Widen to `except Exception:` (keeping `logger.exception`) — this is fire-and-forget
  post-commit cleanup, so a broad catch is the correct shape. Add a test patching the storage
  to raise a non-`OSError`.
  - Strength: Makes the code match the contract its own docstring states; one line.
  - Tradeoff: A broad `except Exception` can mask a programming error in the callback — mitigated
    because `logger.exception` records the traceback.
  - Confidence: HIGH — exception surface read directly from the installed Django source.
  - Blind spot: None significant.
- **Decision**: PENDING

### F2 — Registering the receiver also disables field deferral, so a cascade now loads every `points` blob

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `gpx/signals.py:70`
- **Detail**: The plan documented one consequence of registering the receiver (`can_fast_delete`
  returns `False`, so rows materialize — the mechanism the whole phase depends on). There is a
  second, undocumented one from the same source: `deletion.py:328-337` skips the collector's
  **field-deferral** optimization when `self._has_signal_listeners(related_model)` is true.
  Verified in the installed source. So a cascade now `SELECT`s full `GpxTrack` rows *including
  the `points` JSONField*, whose ceiling `gpx/constants.py:22` sets at `MAX_GPX_POINTS = 100_000`.
  On top of that, `partial(discard_track_file, instance)` closes over the whole instance, keeping
  every row resident **past** commit rather than only for the duration of the delete. An admin
  `delete_selected` over a few dozen track-bearing trips is the realistic trigger; nothing in the
  suite exercises more than 2 tracks.
- **Fix A ⭐ Recommended**: Close over the two scalars the callback needs —
  `partial(discard_file_by_key, instance.pk, instance.file.name)` calling
  `default_storage.delete(key)` — so instances become collectable at commit. Add the deferral
  amplification to the `AGENTS.md` note, since it comes from the same source line as the
  fast-delete property already documented there.
  - Strength: Removes the post-commit half of the retention entirely, and keeps the receiver's
    load-bearing property intact. The callback genuinely needs nothing else.
  - Tradeoff: Loses `track.file.delete(save=False)`'s field bookkeeping — irrelevant for a row
    that no longer exists, but the code reads slightly less idiomatically.
  - Confidence: HIGH — both source lines read directly; the change is mechanical.
  - Blind spot: The during-delete half (full rows in the collector) is unavoidable while the
    receiver is registered; this fix addresses only the retention past commit.
- **Fix B**: Leave as is and document the amplification in `AGENTS.md` only.
  - Strength: Zero code risk on a path three review findings have already hardened.
  - Tradeoff: The memory ceiling stays; a bulk admin delete on a small container is the failure
    mode, and it is the one deletion path with no user watching it.
  - Confidence: MEDIUM — depends on whether bulk admin deletes over many trips ever happen.
  - Blind spot: Haven't measured actual resident memory for a realistic bulk delete.
- **Decision**: PENDING

### F3 — Confirmation page materializes every track (with `points`) to answer an emptiness question

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `trips/templates/trips/trip_confirm_delete.html:17`
- **Detail**: `{% if trip.tracks.all %}` evaluates and caches the whole queryset, pulling the
  `points` JSONField for every track, just to decide whether to print one sentence. Combined with
  the `MAX_GPX_POINTS = 100_000` ceiling that is up to megabytes of JSON loaded and discarded.
  `trip_detail.html`'s analogue is fine — `TripDetailView.get_context_data` actually needs the
  row for the map. The template comment's reasoning (branch here, not on a new context key) is
  sound; only the accessor is wrong.
- **Fix**: Change to `{% if trip.tracks.exists %}` — a `SELECT 1 … LIMIT 1`.
- **Decision**: PENDING

### F4 — The one form template in the repo without `{{ form.non_field_errors }}`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `trips/templates/trips/trip_confirm_delete.html:21-24`
- **Detail**: Recorded lesson #2 (`context/foundation/lessons.md:13`) is *"Render
  `{{ form.non_field_errors }}` in every form template"*. Every other form template in the repo
  does — `accounts/login.html:10`, `accounts/signup.html:9`, `trips/trip_form.html:20`,
  `trips/trip_detail.html:81`. `BaseDeleteView` is form-based in Django 4+ and does put a `form`
  in this template's context, so a `form_invalid` re-render would show a Delete button with no
  indication anything failed. Practical reachability is nil (the empty `Form` always validates),
  which is why this is a consistency finding rather than a UX defect — but the rule is recorded
  and `trips/views.py:129-131` shows the author already reasoning about that empty form.
- **Fix**: Add `{{ form.non_field_errors }}` after `{% csrf_token %}`.
- **Decision**: PENDING

### F5 — The `+1 day` boundary tests cannot detect a widened tolerance

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/trips/test_trip_creation.py:140,155`
- **Detail**: Both boundary tests compute the expected boundary from the same constant the
  production code reads: `trips/forms.py:50` compares against
  `timezone.localdate() + FUTURE_TRIP_DATE_TOLERANCE`, and the tests build `tomorrow` and
  `beyond` from `timezone.localdate() + FUTURE_TRIP_DATE_TOLERANCE` too. Change
  `trips/constants.py:14` to `timedelta(days=5)` and both tests still pass. The tests *do* catch
  the direction their docstring names (tightening to `> localdate()` breaks the `tomorrow` case),
  so the gap is one-sided: silent widening. The plan asked the boundary test to "document the
  tolerance as intentional rather than an off-by-one" (`plan.md:684-686`), which needs the test to
  pin the value independently. `test_trip_edit.py:228,247` uses a literal `timedelta(days=365)`
  and is unaffected.
- **Fix**: Add `assert FUTURE_TRIP_DATE_TOLERANCE == timedelta(days=1)` to one of the two tests
  (keeping the constant in the arithmetic, so the intent stays readable).
- **Decision**: PENDING

### F6 — `make_stored_track` moved against an explicit plan statement

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `tests/conftest.py:126` (was `tests/gpx/conftest.py:40`)
- **Detail**: `plan.md:418-419` states "`make_stored_track` already lives in
  `tests/gpx/conftest.py:40`, the same package — **no fixture move needed**". The fixture was
  moved to the root `tests/conftest.py`, with `StoredTrackFactory` re-exported at `:25` and
  `tests/gpx/test_gpx_download.py:10` repointed. The plan's claim was scoped to Phase 2 and
  became false in Phase 3, where `tests/trips/test_trip_delete.py:119` needs a stored track from
  a different test package. The move is the correct call; the plan sentence is what went stale.
  This is the only drift found in the whole change — there are no MISSING items.
- **Fix**: None to the code. Optionally note the Phase-3 correction in the plan so a future
  reader of `plan.md:418-419` isn't misled.
- **Decision**: PENDING

### F7 — `test_trip_edit.py` has no unauthenticated-POST test

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/trips/test_trip_edit.py:184`
- **Detail**: The plan's fixed matrix requires, for every new owner-scoped surface, "anonymous →
  302 to login with `?next=`". `test_trip_delete.py` covers both verbs — GET at `:179` and POST
  at `:189`, the latter with a survival assertion. `test_trip_edit.py` covers only the GET leg.
  The missing test is the one that would catch a `LoginRequiredMixin` ordering regression on the
  *write* path, which is the leg that matters.
- **Fix**: Add `test_unauthenticated_post_redirects_and_changes_nothing`, mirroring
  `test_trip_delete.py:189`.
- **Decision**: PENDING

### F8 — `TripCreateView` is the one form view that does not narrow `http_method_names`

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `trips/views.py:47-58`
- **Detail**: `TripUpdateView:109`, `TripDeleteView:139` and `GpxUploadView` all narrow;
  `TripCreateView` does not. `TripUpdateView`'s own comment names the resulting behavior as the
  thing worth closing: *"`ProcessFormView.put` re-enters `post()` against an empty
  `request.POST`, so a `PUT` would 200-re-render with every field in error instead of returning
  405."* `PUT /trips/new/` does exactly that today, untested. Harmless (nothing is written), but
  it undercuts the claim that narrowing is the project idiom.
- **Fix**: Add `http_method_names = ["get", "post"]` to `TripCreateView` with the same comment,
  plus a `PUT → 405` test alongside the existing create tests.
- **Decision**: PENDING

### F9 — Narrowing to `["get", "post"]` also drops HEAD and OPTIONS

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `trips/views.py:109`, `trips/views.py:139`
- **Detail**: Measured directly with an authenticated client: `HEAD /trips/<pk>/` → **200**,
  `HEAD /trips/<pk>/edit/` → **405**, `HEAD /trips/<pk>/delete/` → **405** (OPTIONS likewise).
  Two pages that answer GET now refuse HEAD, unlike every other page in the app.
  `GpxUploadView`'s `["post"]` has no such issue — it serves no page. Practical impact is very
  low because both routes sit behind `LoginRequiredMixin`, so an anonymous HEAD gets the login
  redirect and never reaches the method check; only an authenticated HEAD sees the 405.
- **Fix**: Use `["get", "post", "head", "options"]` on the two page-serving views, keeping the
  comments that explain what the narrowing closes.
- **Decision**: PENDING

### F10 — The one orphan path the branch's cleanup story still does not cover

- **Severity**: 📋 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `gpx/views.py:100-113`
- **Detail**: Inside `with transaction.atomic():`, `super().form_valid(form)` writes the **new**
  file to storage. Storage writes do not participate in the transaction. If anything later in the
  block raises, the new row rolls back while its file remains — a file with no row, which the
  `post_delete` receiver by construction can never reach (it fires on deletes, not failed
  inserts). Pre-existing and untouched by this branch; raised because the branch's whole premise
  is that GPX file lifecycle is now owned end-to-end, and this is the remaining hole in that
  claim. Blast radius is one file per failed upload.
- **Fix A ⭐ Recommended**: Record it as an Engineering Backlog row, triggered the next time
  `gpx/views.py`'s upload transaction is touched.
  - Strength: Keeps this change's scope intact — it is not a defect this branch introduced — while
    stopping the "lifecycle fully owned" claim in `AGENTS.md` from being read as complete.
  - Tradeoff: The hole stays open.
  - Confidence: HIGH — matches how E-08 and E-10 were handled in this very change.
  - Blind spot: None significant.
- **Fix B**: Close it now by moving the file write outside `atomic()` or adding a compensating
  rollback hook.
  - Strength: Makes the `AGENTS.md` lifecycle claim literally true.
  - Tradeoff: Reopens the upload transaction, a path three prior review findings hardened, for a
    one-file-per-failed-upload leak — after the change is already implemented and gates are green.
  - Confidence: MEDIUM — the ordering inside that block is subtle and previously contested.
  - Blind spot: Haven't worked out whether moving the write out breaks the "new row and file saved
    first" invariant the docstring depends on.
- **Decision**: PENDING
