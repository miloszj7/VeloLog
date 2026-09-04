<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Whole-Trip Aggregate Statistics on the Trip Detail View

- **Plan**: context/changes/multi-stage-trip-stats/plan.md
- **Scope**: Full plan (Phase 1, 2, 3 — all marked complete)
- **Date**: 2026-09-04
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 1 observation
- **Triage**: F1 FIXED (plan addendum added). F2 NO CHANGE NEEDED (verified the flagged code is required by mypy --strict, not dead).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Automated verification (re-run)

- `uv run pytest --cov -q` — 389 passed, 2 skipped, 6 deselected, 96.45% coverage (≥80% required)
- `uv run pytest -m bite_proof -q` — 6 passed
- `uv run mypy .` — Success, no issues
- `uv run ruff check .` — All checks passed
- `uv run black --check .` — 87 files unchanged
- `uv run isort --check-only .` — clean
- `uv run python manage.py check` — no issues
- `uv run python manage.py makemigrations --check --dry-run` — no changes detected

All Phase 1/2/3 Automated Verification checkboxes confirmed against a live re-run, not just trusted from the Progress section.

## Findings

### F1 — Unplanned "Totals across N stage(s)" line added after plan close

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; addition is sound and already tested
- **Dimension**: Scope Discipline
- **Location**: trips/templates/trips/trip_detail.html:118, tests/trips/test_trip_detail_stats.py
- **Detail**: Commit `6fd6834` ("show stage count in Trip totals") was made *after* all three phases were marked `[x]` and after the plan's own close-out ("epilogue") commit `add7b5c`. It adds a `<p class="text-muted small">Totals across {{ stages|length }} stage{{ stages|length|pluralize }}</p>` line under the "Trip totals" heading, with matching test assertions. Nothing in `plan.md` — no Changes Required item, no Testing Strategy bullet, no Progress entry — describes this. Verified sound: `stages` is the same list already in context, so the count matches exactly what the per-stage section below renders; Django's `pluralize` gives correct "1 stage"/"2 stages" wording (confirmed by a test asserting both forms); it sits inside the existing `{% if stages %}` guard, so it doesn't reappear for a zero-stage trip. No bug — purely a paper-trail gap.
- **Fix**: Record this addition as a plan addendum (or a short note in `change.md`) so the plan's Progress section reflects everything actually shipped, rather than leaving a shipped, untested-by-the-plan feature invisible to a future reader who trusts `plan.md` as the complete record.
- **Decision**: FIXED — addendum added to `plan.md` (new "Addendum — post-close: stage-count line in Trip totals" section, Progress entry A.1, commit `6fd6834` cited).

### F2 — Dead `is not None` filter inside `_summed_or_none`

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: gpx/statistics.py (`_summed_or_none`, ~lines 320-326)
- **Detail**: The function returns `None` early if `any(value is None for value in values)`. The subsequent `sum(value for value in values if value is not None)` can therefore never encounter a `None` — the inner filter is unreachable dead code. Harmless (no behavior change), but reads as if the sum still needs defending against `None` once it structurally can't.
- **Fix**: Simplify to `return formatter(sum(values))`, since by that point every element is known non-`None`.
- **Decision**: NO CHANGE NEEDED — tried the simplification; `mypy --strict` rejects `sum(values)` (`values: list[float | None]`, `sum` expects `Iterable[bool]`/numeric non-Optional). The `if value is not None` filter is the mechanism that narrows the comprehension to `list[float]` for the type checker — it's redundant at runtime but load-bearing for static typing, not dead code. Reverted.

