<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Trip Date Divergence Implementation Plan

- **Plan**: context/changes/trip-date-divergence/plan.md
- **Scope**: Phase 1-4 of 4 (full plan)
- **Date**: 2026-09-05
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | WARNING |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — List-page and detail-page divergence checks use different chronology requirements

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: trips/views.py:67-78 (TripListView) vs. trips/views.py:137-139 / gpx/views.py:99-100 (TripDetailView / GpxUploadView)
- **Detail**: `TripListView.diverging_trip_ids` flags a trip off the earliest **known** `started_at` via `Min()`, with no requirement that every stage be timed. `TripDetailView`/`GpxUploadView`'s `date_diverges` is gated behind `trip_span(tracks) is not None`, which requires `chronology_is_established` — i.e. every stage timed. This is explicitly sanctioned by the plan's "What We're NOT Doing" section ("Not requiring `chronology_is_established`... for the upload-time warning or the list-page indicator"), so it is not implementation drift — but the consequence is real: a trip with one timed stage and one untimed stage can show the ⚠ list-page icon while its own detail page shows no "Logged as ..." note at all, a visible contradiction for the same underlying data. No test exercises this mixed-stage case on both surfaces together (`tests/trips/test_trip_list.py` only covers fully-timed vs. zero-stage; `tests/trips/test_trip_detail_span.py` only covers fully-timed vs. fully-untimed).
- **Fix A ⭐ Recommended**: Add a regression test documenting the intentional asymmetry (mixed-stage trip: list shows the indicator, detail page shows no note) and a one-line comment at both call sites cross-referencing the other surface's different criterion, so a future reader doesn't mistake it for a bug.
  - Strength: Cheapest option; makes the already-deliberate design decision self-documenting and locks current behavior with a test, without touching working code.
  - Tradeoff: The user-visible contradiction remains — a rider can still see one page disagree with the other.
  - Confidence: HIGH — matches the plan's own explicit scope choice; no behavior change needed.
  - Blind spot: Whether real users find the inconsistency confusing enough to matter hasn't been checked against actual usage.
- **Fix B**: Make `TripListView`'s check require full chronology too (reuse `chronology_is_established` semantics), so both surfaces agree.
  - Strength: Removes the contradiction entirely; one consistent divergence definition everywhere.
  - Tradeoff: Silently reduces the list indicator's usefulness on partially-timed trips — it would stop firing for exactly the case the plan's "not doing" section deliberately kept it firing for (a trip with some untimed stages), so this narrows the plan's stated scope after implementation, not before.
  - Confidence: MEDIUM — technically straightforward, but reverses a decision the plan made intentionally, not accidentally.
  - Blind spot: Haven't checked whether any of trips 21/22/23 (the real-world validation data) rely on the current partial-chronology behavior to show the indicator.
- **Decision**: FIXED via Fix B — `TripListView.get_context_data` (trips/views.py) now aggregates `total`/`timed`/`earliest` per trip via `Count`/`Min` and only flags a trip when `total == timed and total > 0`, matching `chronology_is_established`'s all-stages-timed gate. New regression test `tests/trips/test_trip_list.py::test_a_trip_with_an_untimed_stage_shows_no_indicator_even_when_the_timed_stage_diverges` locks the mixed-stage case. All 11 tests in `tests/trips/test_trip_list.py` pass; `mypy`/`ruff`/`black --check` clean.

### F2 — Divergence-flag one-liner duplicated across two views

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: trips/views.py:137-139, gpx/views.py:99-100
- **Detail**: `TripDetailView.get_context_data` and `GpxUploadView.get_context_data` both compute the identical `span is not None and trip_date_diverges(trip.date, span[0])`. `gpx/statistics.py`'s own module docstring documents this project's rationale for pulling such logic out of views into a shared helper ("a value derived in a template would have to be derived twice") — the same reasoning applies here but wasn't followed, risking future drift between the two call sites if one is edited without the other.
- **Fix**: Extract a small helper (e.g. `span_date_diverges(trip_date, span)` in `trips/dates.py`) that both views call instead of repeating the one-liner.
- **Decision**: FIXED — added `span_date_diverges(trip_date, span)` to `trips/dates.py`; `TripDetailView.get_context_data` and `GpxUploadView.get_context_data` both now call it instead of repeating the inline check. 48 affected tests pass; `mypy`/`ruff`/`black --check` clean.

### F3 — `trip_date_diverges` docstring omits Args/Returns sections

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: trips/dates.py:16-24
- **Detail**: The docstring is prose-only despite three parameters and a boolean return worth documenting individually (especially `tolerance`'s default). Only 1 of 4 functions in the closest sibling module (`gpx/stages.py`, `trip_span`) uses Google-style `Args:`/`Returns:` sections, so this is a soft inconsistency rather than a clear convention violation — noted for awareness, not a strong finding.
- **Fix**: Add `Args:`/`Returns:` sections for consistency with `trip_span`'s docstring style.
- **Decision**: FIXED — `trip_date_diverges`'s docstring now carries `Args:`/`Returns:` sections (also folds in F4's precondition note). `tests/trips/test_dates.py` (4/4), `mypy`, `ruff`, `black --check` all pass.

### F4 — Undocumented aware-datetime precondition

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: trips/dates.py:23
- **Detail**: `timezone.localtime(observed)` raises `ValueError` if `observed` is naive. All current callers pass DB-sourced, timezone-aware datetimes (`GpxTrack.started_at` / `Min()` results), so this is safe today, but the function has no docstring note stating this precondition — a future caller passing a naive datetime would get an unexplained `ValueError` traced into `timezone.localtime` rather than a clear expectation.
- **Fix**: Add a one-line docstring note: "`observed` must be timezone-aware."
- **Decision**: FIXED (folded into F3's edit) — the `Args:` section for `observed` now states the timezone-aware precondition and what happens if violated.

## Verification notes

- **Plan drift**: zero. All 10 changed/new files (`trips/constants.py`, `trips/dates.py`, `trips/views.py`, `gpx/views.py`, both templates, and 4 test files) match the plan's contracts exactly — signatures, the strict `>` operator, context-key parity between `TripDetailView`/`GpxUploadView`, template placement, and required test cases all verified by reading actual file contents.
- **Scope**: `git diff` shows only files the plan names, plus `context/changes/trip-date-divergence/{plan.md,change.md}` bookkeeping. No unplanned files.
- **Ownership/authorization**: `TripListView`'s new aggregate query (`GpxTrack.objects.filter(trip__in=trips)`) only ever runs over the already owner-scoped `object_list`; no unscoped queryset introduced anywhere in the diff.
- **N+1**: verified as one extra aggregate query for the whole list (not per-row), and locked by `tests/trips/test_trip_list.py::test_the_list_costs_a_fixed_small_number_of_queries_regardless_of_stage_count` using `django_assert_num_queries`.
- **Automated verification run directly**:
  - `uv run pytest tests/trips/test_dates.py tests/trips/test_trip_detail_span.py tests/gpx/test_gpx_upload.py tests/trips/test_trip_list.py -v` → 47 passed
  - `uv run mypy .` → Success, no issues in 89 source files
  - `uv run ruff check .` → All checks passed
  - `uv run black --check .` → all 89 files unchanged
  - `uv run pytest -m bite_proof` → 6 passed, 404 deselected
  - `uv run pytest --cov` (full suite) → 402 passed, 2 skipped, 6 deselected; 96.54% total coverage (required 80.0%)

## Triage summary

All 4 findings fixed, one commit per finding:

- F1 → Fix B (`c2409ed`): `TripListView` now requires full chronology, matching the detail page.
- F2 (`12c9e35`): extracted shared `span_date_diverges` helper.
- F3 + F4 (`041b71e`): `trip_date_diverges` docstring gained `Args:`/`Returns:` and the aware-datetime precondition note.

Re-verified after all three fix commits: `uv run pytest --cov` → 402 passed, 2 skipped, 6 deselected, 96.54% coverage; `mypy`/`ruff`/`black --check`/`pytest -m bite_proof` all pass.
