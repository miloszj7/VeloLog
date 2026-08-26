<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Upload a GPX file and view the route as a map

- **Plan**: `context/changes/upload-gpx-and-view-map/plan.md`
- **Scope**: Phase 3 of 6 — Trip detail view (commit `2110c32`)
- **Date**: 2026-08-25
- **Verdict**: NEEDS ATTENTION → all findings triaged 2026-08-25 (8 fixed, 1 accepted)
- **Findings**: 0 critical, 3 warnings, 6 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

All six planned changes MATCH their contracts; nothing is MISSING. Security is clean —
ownership scoping verified airtight at the queryset, XSS escaping verified empirically
against hostile `trip.name` and `original_filename` values, `LoginRequiredMixin` MRO
position confirmed correct and fail-closed if reversed. The detail page issues a fixed
4 queries; no N+1. All six automated gates pass (ruff, black, isort, mypy strict,
`manage.py check`, migration guard, `pytest --cov` 62 passed / 99.60%).

Every finding below is about the *test net* and one docstring — not about shipped behaviour.
The two Safety & Quality warnings matter because each currently lets a wrong implementation
pass green, and Phase 4 builds directly on this page.

## Findings

### F1 — `get_absolute_url` docstring claims a centralization that does not exist

- **Severity**: WARNING
- **Impact**: MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Pattern Consistency
- **Location**: `trips/models.py:24-30`
- **Detail**: The method has zero production callers — a repo-wide grep finds only its own
  definition and `tests/trips/test_trip_model.py:43-46`. Its docstring states, in the present
  tense, "Every redirect that lands a user back on a trip resolves the route here, so the URL
  name lives in one place rather than being repeated across views." Neither half is true today:
  no redirect resolves through it (`TripCreateView.success_url` is a hardcoded
  `reverse_lazy("trips:list")`, `trips/views.py:39`), and the one place in this very commit that
  builds a trip URL bypasses it (`trips/templates/trips/trip_list.html:11` uses the `url` tag).
  Per `lessons.md` rule #5, a stale claim in a file the next agent reads actively misdirects
  rather than merely being out of date.
- **Fix A (Recommended)**: Route the list template through it — `{{ trip.get_absolute_url }}` at
  `trip_list.html:11`.
  - Strength: Makes the docstring true immediately instead of deferring to Phase 4, and gives the
    method a production caller so `test_get_absolute_url_...` stops guarding dead code.
  - Tradeoff: Diverges from the sibling templates' `url`-tag idiom (`trip_list.html:7`,
    `trip_detail.html:6`), so the file mixes two URL-building styles.
  - Confidence: HIGH — one-line template change; the existing list-link test covers it.
  - Blind spot: None significant.
- **Fix B**: Reword the docstring to the future tense the plan actually intended ("exists for
  Django's `get_absolute_url` protocol and for the Phase 4 redirect targets").
  - Strength: Keeps every template on one idiom; honest about a deliberately forward-looking
    method the plan asked for (`plan.md` Phase 3 §3).
  - Tradeoff: Leaves the method with no production caller until Phase 4 lands.
  - Confidence: HIGH — the plan's stated intent for §3 is verbatim "Give the redirect targets in
    Phase 4 one place to resolve".
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A (`76aebe1`) — `trip_list.html` now resolves the link through `get_absolute_url`, giving the method a production caller and making its docstring true.

### F2 — Track test cannot distinguish per-trip scoping from a global query

- **Severity**: WARNING
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/trips/test_trip_detail.py:60-81`
- **Detail**: `test_trip_with_a_track_renders_the_track_branch_instead_of_the_empty_state` creates
  exactly one trip and one track, so it passes identically against the correct implementation
  (`self.object.tracks.first()`, `trips/views.py:64`) and against a wrong one
  (`GpxTrack.objects.first()`, or any query not scoped to this trip). The scenario the code exists
  to handle is never exercised — the same class of gap as `lessons.md` rules #1 and #3.
- **Fix**: Create a second trip for the same rider with its own track; assert the detail page shows
  only its own track's `original_filename` and that the other's is absent.
- **Decision**: FIXED (`72bdbe3`) — a second trip with its own newer track now discriminates the two implementations. Verified by mutation: swapping the view to an unscoped `GpxTrack.objects.first()` fails this test and only this test.

### F3 — Locale-dependent date assertion

- **Severity**: WARNING
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/trips/test_trip_detail.py:22`
- **Detail**: `assert "June 1, 2026" in body` hardcodes the en-us rendering of the trip date. The
  same `date(2026, 6, 1)` renders as `1 Jun 2026` (en-gb), `1 czerwca 2026` (pl),
  `1. Juni 2026` (de). `velo_log/settings.py:127` sets `LANGUAGE_CODE = "en-us"` and `:131` sets
  `USE_I18N = True`; changing either, or adding a project-level `DATE_FORMAT`, breaks the assertion
  for a reason unrelated to the behaviour under test. (`LocaleMiddleware` is not installed, so an
  `Accept-Language` header cannot flip it today.) Both review agents flagged this independently.
- **Fix**: Compute the expected string with `django.utils.formats.date_format(trip.date)`, or pin
  the locale for this test via the `settings` fixture, so the assertion states intent rather than a
  locale accident.
- **Decision**: FIXED (`55be08e`) — the expected string is derived with `django.utils.formats.date_format`. Constructing the trip with a real `date` object was required for that. Verified by mutation: removing `{{ trip.date }}` from the template fails the assertion.

### F4 — List-page test placed in the detail module, and its name implies plurality it does not test

- **Severity**: OBSERVATION
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/trips/test_trip_detail.py:84-90`
- **Detail**: `test_list_page_links_each_trip_to_its_detail_page` asserts on the list page's
  rendered HTML but lives in the detail module; every other list-page rendering assertion lives in
  `tests/trips/test_trip_list.py`. Separately, the name says "each trip" while the test creates one,
  so it cannot catch a template that links every row to the same pk.
- **Fix**: Move it to `tests/trips/test_trip_list.py` and create two trips, asserting both hrefs.
- **Decision**: FIXED (`9607156`) — moved to `tests/trips/test_trip_list.py`, renamed, and given two trips so both hrefs are asserted.

### F5 — Two tests skip the status-code opener their siblings all use

- **Severity**: OBSERVATION
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/trips/test_trip_detail.py:79`, `:90`
- **Detail**: Every other test in this file and in both sibling files opens with
  `assert response.status_code == 200`. Without it, a regression that 404s the page surfaces as a
  `KeyError` on `response.context["track"]` rather than a legible status failure.
- **Fix**: Add `assert response.status_code == 200` as the first assertion in both.
- **Decision**: FIXED — the track-test location was resolved by the F2 rewrite (`72bdbe3`) and the list-test location by the F4 move (`9607156`). Both now open with the status-code assertion their siblings use.

### F6 — `GpxTrack` construction duplicated across two test packages

- **Severity**: OBSERVATION
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/trips/test_trip_detail.py:65-74`
- **Detail**: Inline `GpxTrack.objects.create(...)` with eight keyword arguments duplicates the
  `_make_track` helper at `tests/gpx/test_gpx_track_model.py:11-21`. Two packages now build tracks,
  and `tests/conftest.py` is the project's established single home for shared fixtures.
- **Fix**: Promote a `gpx_track` factory fixture to `tests/conftest.py` and use it from both.
- **Decision**: FIXED (`c10815c`) — a `make_gpx_track` factory fixture plus the shared `GPX_POINTS` / `GPX_BOUNDS` constants now live in `tests/conftest.py`; both packages build tracks through it and assert against the same values.

### F7 — Adding `get_absolute_url` silently turned on the admin's "View on site" link

- **Severity**: OBSERVATION
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `trips/admin.py:13-18` (behaviour change caused by `trips/models.py:24`)
- **Detail**: `ModelAdmin.view_on_site` defaults to `True`, so `TripAdmin` now renders a "View on
  site" link on every Trip change form. It resolves to the owner-scoped detail URL, so a staff user
  inspecting another rider's trip clicks it and gets a 404. Fail-closed and consistent with the
  project's 404-not-403 stance, but an undocumented side effect of this commit.
- **Fix**: Set `view_on_site = False` on `TripAdmin` if the admin repair path is meant to stay
  usable; otherwise record the behaviour deliberately.
- **Decision**: FIXED (`e7b72ea`) — `view_on_site = False` on `TripAdmin`, with a comment recording why the owner-scoped route makes the default link a 404 trap for staff.

### F8 — `get_absolute_url` test is tautological

- **Severity**: OBSERVATION
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/trips/test_trip_model.py:43-46`
- **Detail**: The test compares `reverse("trips:detail", ...)` against the implementation's own
  `reverse("trips:detail", ...)`. Both sides move together, so it pins the URL *name* but not the
  URL *shape* — a route path change that breaks existing bookmarks passes green.
- **Fix**: Assert the literal `f"/trips/{trip.pk}/"`, matching the concreteness of the ordering
  assertions elsewhere in the same file.
- **Decision**: FIXED (`9306651`) — asserts the literal `/trips/<pk>/`. Verified by mutation: changing the route path now fails the test, where previously it passed green.

### F9 — `.first()` is newest-wins, and nothing yet enforces the one-track invariant

- **Severity**: OBSERVATION
- **Impact**: MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: `trips/views.py:64`, `trips/templates/trips/trip_detail.html:15-20`
- **Detail**: `self.object.tracks.first()` resolves against
  `GpxTrack.Meta.ordering = ["-uploaded_at", "-id"]` (newest wins), while the context key and
  template branch are singular. The schema deliberately permits many tracks per trip
  (`gpx/models.py:21-26`, plan decision D1). v1 uploads one, so this is correct today — but if a
  second upload ever creates rather than replaces, the older track becomes invisible in the UI while
  its file stays on disk, with nothing in this view signalling the displacement.
- **Fix**: No change in Phase 3. The plan already commits to replace-on-upload (change.md D1;
  plan.md "Ordering on replace" under Critical Implementation Details). Verify at Phase 4 that the
  invariant is enforced at the boundary that creates tracks, not left to `.first()` alone.
- **Decision**: ACCEPTED — no Phase 3 change, as the finding itself recommends. The plan already commits to replace-on-upload (change.md D1, plan.md "Ordering on replace"), so the invariant belongs at the boundary that creates tracks. Queued for the Phase 4 review in `follow-ups/review-fixes.md`. The F2 fix incidentally pins the newest-wins ordering with a test and documents it in that test's docstring.
