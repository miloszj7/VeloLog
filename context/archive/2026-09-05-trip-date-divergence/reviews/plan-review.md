<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Trip Date Divergence Implementation Plan

- **Plan**: context/changes/trip-date-divergence/plan.md
- **Mode**: Deep
- **Date**: 2026-09-05
- **Verdict**: SOUND (after fixes)
- **Findings**: 1 critical, 1 warning, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | PASS (after fix) |
| Plan Completeness | PASS (after fixes) |

## Grounding

Grounding: 10/10 paths ✓, 5/5 symbols ✓, brief↔plan ✓

## Findings

### F1 — Phase 4's data flow breaks mypy --strict

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Blind Spots
- **Location**: Phase 4 — Changes Required #1
- **Detail**: No `.annotate()` exists anywhere in this codebase yet. `TripListView.get_queryset` declares `-> QuerySet[Trip]:`, which erases django-stubs' annotation typing the moment it's returned, so `trip.earliest_started_at` fails mypy. Setting `trip.date_diverges` directly on `Trip` instances afterward fails mypy too — that attribute doesn't exist on the model and django-stubs' annotate-typing support doesn't cover ad hoc extra attributes. `uv run mypy .` is a required Success Criterion on this exact phase.
- **Fix ⭐ Recommended**: Compute a `set[int]` of diverging trip pks via a separate small aggregate query (`GpxTrack.objects.filter(trip__in=...).values("trip_id").annotate(earliest=Min("started_at"))`), turned into a dict then a set of diverging pks, checked via `{% if trip.pk in diverging_trip_ids %}` in the template instead of mutating `Trip` instances or relying on `QuerySet[Trip]` carrying annotate typing.
  - Strength: Zero new mypy surface — no ad hoc instance attributes, dict/set membership is plain Python mypy already handles, still one extra query for the whole list.
  - Tradeoff: Slightly more code than a one-line `.annotate()` on the main queryset.
  - Confidence: HIGH — grounded in django-stubs plugin source read during this review.
  - Blind spot: Not verified against a live mypy run yet (no code written) — confirm with `uv run mypy .` once Phase 4 lands.
- **Decision**: FIXED (Fix applied — Phase 4 rewritten to use the diverging-pk-set approach; plan.md and plan-brief.md updated)

### F2 — Phase 4 test names a query-count API this codebase doesn't use that way

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 — New tests
- **Detail**: Plan said to assert query count via "`assertNumQueries` or `CaptureQueriesContext`". `assertNumQueries` is a `TestCase` method — this suite is all pytest-style function tests, no `TestCase` subclasses exist. The codebase already has real precedents: the `django_assert_num_queries` pytest-django fixture (`tests/gpx/test_gpx_signals.py`) and `CaptureQueriesContext` (`tests/trips/test_trip_detail_stats.py`).
- **Fix**: Name `django_assert_num_queries` (the fixture `tests/test_assertion_strength.py` already calls out as the established idiom) as the primary choice, dropping the bare `assertNumQueries` mention.
- **Decision**: FIXED (plan.md Phase 4 "New tests" updated)

### F3 — Context key and function share one name

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — Changes Required #1
- **Detail**: `context["trip_date_diverges"] = ...trip_date_diverges(...)` — the context key and the imported function shared the identical name. Not a bug, but read oddly at the call site and in the template.
- **Fix**: Renamed the context key to `date_diverges` throughout Phase 2 (already scoped to one trip's page, doesn't need the `trip_` prefix).
- **Decision**: FIXED (plan.md Phase 2 updated — context key, template references)
