---
project: velolog
checked_at: 2026-09-02T00:00:00Z
health_status: needs-attention
context_type: brownfield
language_family: python
stack_assessment_available: true
checks_run:
  - lockfile
  - dependency_audit
  - outdated_deps
  - test_runner
  - ci_cd
  - configuration
audit_findings:
  critical: 0
  high: 2
  moderate: 0
  low: 0
test_runner_detected: true
ci_provider: GitHub Actions
recommended_fixes: 5
---

## Dependency Health

### Lockfile

```
Status: present (uv.lock)
Package manager: uv
```

### Security Audit

```
Tool: uvx pip-audit --format json (against `uv export`)
Summary: 0 CRITICAL, 2 HIGH, 0 MODERATE, 0 LOW
Direct vs transitive: both flagged packages are direct dependencies (django, sqlparse — the
latter pulled in transitively by django itself for SQL formatting)
```

#### HIGH findings

- **django** 6.0.5 — 9 advisories (PYSEC-2026-197/198/199/200/201/2090/2091/2092/3717), fixed in 6.0.6 through 6.0.8. The relevant ones for this app: `get_signed_cookie` salt-derivation weakness (CVE-2026-6873) and three `Vary`/`Cache-Control` header-handling bugs that leak private cached responses (CVE-2026-35193, CVE-2026-48587, CVE-2026-8404, CVE-2026-48588). These are dormant here — the project checks it does not use `UpdateCacheMiddleware`/`cache_page()` or `django.contrib.gis` (the remaining GDALRaster/GEOS advisories are GeoDjango-only and this app isn't on `INSTALLED_APPS`) — but the fix is a version bump, not a design change. Fix: `uv add "django>=6.0.8"` (or the latest 6.0.x patch) then `uv sync`.
- **sqlparse** 0.5.5 — 5 advisories (PYSEC-2026-3696/3697/3698/3699, CVE-2026-84305), fixed in 0.6.0. All are ReDoS/CPU-exhaustion or code-injection issues in sqlparse's debug-formatting paths (`reindent`, `strip_comments`, Python/PHP output modes). This project checks it does not import `sqlparse` directly and runs with `DEBUG=False` in CI/prod, so the vulnerable paths (Django's debug SQL panel) aren't reachable in this app's request path — but sqlparse is a transitive pin pulled in by Django and worth bumping opportunistically. Fix: no direct action needed beyond keeping Django current; `uv.lock` will pick up a compatible sqlparse on the next `uv lock --upgrade-package sqlparse` if Django's constraint allows it.

### Outdated Dependencies

```
Packages with major version gaps: 1
```

- **isort**: 8.0.1 → 9.0.1 (1 major version behind — dev dependency only, low risk)

Minor/patch gaps not requiring action: django (6.0.5 → 6.1, supersedes the security fix above), asgiref, click, coverage, gunicorn, platformdirs, ruff, sqlparse, tzdata.

## Test Suite

```
Test runner: pytest (+ pytest-django, pytest-cov)
Tests found: 335 collected (5 deselected — the `bite_proof` marker, run separately per project convention)
Test execution: collection successful, no collection errors
```

```
Configuration: pyproject.toml [tool.pytest.ini_options]
Framework: pytest 9.1.1, pytest-django 4.14.0, pytest-cov 7.1.0
```

## CI/CD

```
Provider: GitHub Actions
Configuration: .github/workflows/deploy.yml
```

| Stage      | Status | Notes                                                      |
|------------|--------|--------------------------------------------------------------|
| Lint       | ✓      | ruff check                                                    |
| Test       | ✓      | pytest --cov, plus a separate bite-proof mutation-testing gate |
| Build      | ✓      | manage.py check, migration-drift guard, collectstatic         |
| Type check | ✓      | mypy --strict (django-stubs)                                  |
| Security   | ✗      | no dependency-audit step, no Dependabot, no CodeQL configured |

## Configuration

```
All expected configuration files present, aside from one low-severity gap.
```

### Low severity

- **.editorconfig** — no cross-editor formatting baseline. Low impact here since `black`/`isort`/`ruff` already enforce formatting in CI, but a missing `.editorconfig` means a non-Claude-Code editor won't match indentation/line-ending conventions before those tools run. Fix: add a minimal `.editorconfig` (`indent_style = space`, `indent_size = 4`, `charset = utf-8`, `end_of_line = lf` for Python files).

Note: JS/TS-specific files (`.prettierrc`, `.eslintrc`, `tsconfig.json`) are not applicable — this is a pure Python/Django project with no frontend build toolchain.

## Stack Assessment Cross-Reference

```
Stack assessment: context/foundation/stack-assessment.md
Agent readiness (from stack-assess): ready
```

| Quality Gate Gap | Health-Check Finding | Status |
|---|---|---|
| (none — stack-assess found no quality-gate failures) | CI already runs `mypy --strict`, `ruff`, `pytest --cov`, and a bite-proof mutation gate — all four quality-gate dimensions (typed, convention, popularity, documentation) stay enforced in CI, not just locally | Mitigated / reinforced |
| n/a | Dependency-audit step absent from CI — the 2 HIGH findings above would have gone undetected by the existing gate pipeline | New gap, not previously surfaced by stack-assess (which scores the stack choice, not its CI's dependency-hygiene coverage) |

## Recommended Fixes

### Fix before agent work (Category A)

### 1. Bump Django to patch known CVEs

**Impact**: Django 6.0.5 carries 9 published advisories, several of which affect cache/cookie handling. The exploitable surface in this specific app looks dormant today (no cache middleware, no GeoDjango), but an agent making unrelated changes could unknowingly introduce a `cache_page()` call or similar and silently reactivate a known, patched bug.
**Severity**: high
**Effort**: quick (< 5 min)
**Fix**:

```bash
uv add "django>=6.0.8,<6.1"
uv sync
uv run python manage.py check
uv run pytest --cov
```

### 2. Add a dependency-audit step to CI

**Impact**: The `gates` job in `.github/workflows/deploy.yml` covers lint/format/types/tests but has no security-scan stage, so the findings above would not have been caught automatically — they'd ship silently on every PR until someone runs a manual audit.
**Severity**: high
**Effort**: moderate (15–30 min)
**Fix**: add a step to the `gates` job, e.g.

```yaml
      - name: Dependency audit
        run: uvx pip-audit -r <(uv export --no-hashes --format requirements-txt)
```

Decide up front whether a HIGH finding should fail the build or just annotate it (pip-audit's default exit code is non-zero on any finding) — CI-as-gate vs CI-as-report is a call worth making deliberately, not by accident of the tool's default.

### 3. Track the isort major-version bump

**Impact**: Dev-tooling only — no runtime risk — but isort 9 may change import-sort output slightly, which would show up as a `ruff`/`isort --check-only` CI failure the next time someone bumps it blind.
**Severity**: low
**Effort**: quick (< 5 min)
**Fix**: `uv add --dev "isort>=9"`, then run `uv run isort .` once locally and review the diff before committing.

### 4. Add .editorconfig

**Impact**: Minor — `black`/`isort`/`ruff` already enforce the real formatting contract in CI, so this only affects the editing experience before a tool touches the file.
**Severity**: low
**Effort**: quick (< 5 min)
**Fix**: add a repo-root `.editorconfig` with `indent_style = space`, `indent_size = 4`, `end_of_line = lf`, `charset = utf-8`, matching `black`'s defaults.

### 5. Keep sqlparse current opportunistically

**Impact**: Not independently exploitable in this app's current configuration (no direct `sqlparse` usage, `DEBUG=False` in prod), but it's a transitive dependency of Django itself and costs nothing to keep current alongside fix #1.
**Severity**: low
**Effort**: quick (< 5 min)
**Fix**: covered by fix #1's `uv sync` — re-run `uv lock --upgrade-package sqlparse` if it doesn't move on its own.

## Summary

Health status: needs-attention

VeloLog's test infrastructure and CI pipeline are unusually strong for this stage — 335 collected tests, a bite-proof mutation-testing gate, `mypy --strict` enforced in CI, and a locked `uv.lock` for reproducible builds. The gap is dependency hygiene: Django 6.0.5 and its transitive `sqlparse` pin carry known, patched CVEs, and nothing in the CI pipeline would have caught that — there's no audit step. Both issues look dormant in this app's current code paths (no cache middleware, no GeoDjango, `DEBUG=False` in prod), but patching is a five-minute version bump and adding an audit step closes the detection gap for next time.

Next step: apply fix #1 (Django bump) and fix #2 (CI audit step) — both quick — then proceed to agent onboarding.
