<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Upload a GPX file and view the route as a map

- **Plan**: context/changes/upload-gpx-and-view-map/plan.md
- **Scope**: Phase 6 of 6 (full-plan review, all phases)
- **Date**: 2026-08-26
- **Verdict**: APPROVED
- **Findings**: 1 critical (found and fixed during this review) 0 warnings 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS (1 finding, found and fixed during this review) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Multi-line Django `{# #}` comments rendered as literal text in production

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `templates/base.html:5-8,12-13,33-34` (pre-fix line numbers); `trips/templates/trips/trip_detail.html:24-31,35-39,42-44,56-57` (pre-fix line numbers)
- **Detail**: User-reported: `https://velolog-production.up.railway.app/trips/` showed the literal
  text `{# The PRD scopes VeloLog to a responsive web app... #} {# Per-page stylesheets... #}`
  on the page. Root cause: Django's `{# comment #}` tag is matched by a regex without the
  `DOTALL` flag, so it can only match a comment that stays on a single line. Both
  `templates/base.html` and `trips/templates/trips/trip_detail.html` had several `{# ... #}`
  comments written across multiple lines (a documentation style used throughout this plan's
  commit history to explain non-obvious decisions inline). Since the tag regex never matched
  across the newline, Django's lexer treated the opening `{#` and its content as plain
  template text and emitted it verbatim — on every page that extends `base.html` (the whole
  site) and, worse, on `trip_detail.html` itself, the page the entire slice exists to
  deliver. No test in the suite renders a page and asserts the literal string is absent,
  because comment-stripping is normally implicit and free — this is the one case where it
  silently isn't.
- **Fix**: Converted every multi-line `{# ... #}` comment in both files to Django's
  `{% comment %}...{% endcomment %}` block tag, which does support multi-line content.
  Re-scanned every tracked `.html` file in the repo (a line-balance check for unmatched
  `{#`/`#}` pairs) and confirmed zero remaining instances anywhere, including
  `accounts/templates/`, `trips/templates/trips/trip_form.html`, and `trip_list.html`.
  Verified both edited templates still load and parse via `get_template()`, then ran the full
  gate suite (ruff, black, isort, mypy --strict, `manage.py check`, migration guard, and the
  CI-equivalence pytest command) — all green, 119/119 tests passing, coverage 99.78%.
  - Strength: Removes the defect class entirely rather than patching the two known
    instances — a repo-wide scan closes the door on a third occurrence surviving review.
  - Tradeoff: None — `{% comment %}` is a drop-in replacement with identical semantics for
    this use (non-rendering documentation), and no test or behavior depended on the `{# #}`
    spelling specifically.
  - Confidence: HIGH — reproduced the exact rendering behavior against this repo's Django
    version by rendering both templates before and after the fix, and the repo-wide balance
    scan is exhaustive, not sampled.
  - Blind spot: None significant. The only residual risk is a future contributor
    reintroducing a multi-line `{# #}` comment; nothing in the toolchain (ruff, black, mypy,
    the existing test suite) would catch a reintroduction, since none of them parse Django
    template syntax. Worth a lessons.md entry if this pattern recurs.
- **Decision**: FIXED (applied directly during this review, prior to formal triage — the
  finding was user-reported with an unambiguous single fix and no tradeoff to weigh)

## Verification performed

- **Plan drift** (sub-agent, all 6 phases against the plan's "Changes Required" sections):
  every planned file/contract MATCH. No MISSING items. Every unplanned addition found
  in the diff (`.gitattributes`, `gpx/map_config.py`, the `env_or()` helper, the
  `_plain_staticfiles_storage` test fixture, `SHA256SUMS`, the `MAX_GPX_POINTS` cap, admin
  `raw_id_fields`) is explicitly recorded in the plan's own "Discovered during implementation"
  notes or a phase review amendment — none is undocumented scope creep.
- **Safety, quality & pattern compliance** (sub-agent, full file set): no new CRITICAL or
  WARNING findings. Confirmed no regression in any of the five prior phase-review fixes
  (zoom-ceiling ordering, map fallback content, `/healthz/` path disclosure, `on_commit`
  ordering on file replace, DOCTYPE/entity-expansion rejection, `MAX_GPX_POINTS` cap).
  Confirmed `json_script` is used with no `|safe`/`mark_safe` anywhere in the repo, owner-scoped
  querysets and `LoginRequiredMixin`-first ordering are consistent across `gpx/` and `trips/`,
  and no N+1 query pattern exists in the admin or list/detail views. Independently re-scanned
  and confirmed the F1 fix above rendered cleanly with no other template affected.
- **Automated success criteria** (run directly): `ruff check`, `black --check`, `isort
  --check-only`, `mypy --strict`, `manage.py check`, `makemigrations --check --dry-run`, and
  the full CI-equivalence command (`SECRET_KEY=... DEBUG=False ALLOWED_HOSTS= pytest --cov`)
  all pass — 119 tests, 99.78% coverage against an 80% floor.
- **Manual success criteria**: all Phase 1–6 manual items are recorded `[x]` with commit SHAs
  in the plan's Progress section, including the two carried-over Volume/asset-hashing gates
  (6.8, 6.9) that were the last unverified items before this review.
