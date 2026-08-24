<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: CI Quality Gates

- **Plan**: `context/changes/ci-quality-gates/plan.md`
- **Scope**: Full plan — Phases 1–4 of 4 (all 20 Progress checkboxes `[x]`)
- **Date**: 2026-08-23
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 6 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Success criteria verification

Every checkbox was verified independently rather than taken on trust.

| Check | Result |
|---|---|
| CI-equivalence command (`SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`) | 30 passed, 93.39% vs `fail_under = 80` |
| `uv run pytest --cov` (normal) | 30 passed, 93.39% |
| `uv run ruff check .` | All checks passed |
| `uv run black --check .` | 32 files unchanged |
| `uv run isort --check-only .` | clean (3 skipped) |
| `uv run mypy .` | Success, 32 source files |
| `manage.py check` / `makemigrations --check --dry-run` | no issues / no changes detected |
| **1.6** mutation: delete the `if not DEBUG:` block | `test_settings_security` fails with `AttributeError` — revert verified clean |
| **2.2** mutation: drop `trips` from `[tool.coverage.run] source` | guard fails naming `['trips']` and `pyproject.toml` — revert verified clean |
| **3.1/3.2** `gates` on the PR | run 32666170450 — `gates` success |
| **3.3** `deploy` skipped on PR | run 32666170450 — `deploy` skipped |
| **3.5** red gate blocks deploy | run 32665936138 — `gates` failure, `deploy` skipped |
| **3.6** `gates` before `railway up` | run 32666337077 — gates 21:03:42→21:04:04, deploy 21:04:07→21:04:55 |
| **3.7** deployed `/healthz/` | HTTP 200 `{"status": "ok"}` (first probe 404'd on cold start; three subsequent probes 200) |
| **4.5** successor backlog row | present in `roadmap.md` with the exact gap/fix/trigger wording |

Plan Adherence: every "Changes Required" item is a MATCH — the autouse fixture touches only
`SECURE_SSL_REDIRECT`, the security test uses the prescribed `reload`-inside-`patch.dict`
mechanism in a `finally`, `.env.example` is comments-only with the required `DEBUG` trap
warning, the coverage guard uses `tomllib` + top-level normalization + a repo-root directory
check (not the forbidden `startswith("django.")`), the workflow split matches step-for-step
with `SECRET_KEY` at job level, and `AGENTS.md` quotes the CI-equivalence command verbatim
(the forbidden `DEBUG=False uv run pytest` appears nowhere). No scope-guardrail violation:
zero files under `accounts/`, `trips/`, `velo_log/`, or `templates/` were touched;
`fail_under` is still 80; no `actions/cache` or uv cache key.

## Findings

### F1 — Settings reload leaks the production security names into `velo_log.settings`

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: tests/test_settings_security.py:28-31
- **Detail**: The `finally:` teardown is correctly built — `patch.dict` is *inside* the `try`,
  so `os.environ` is restored before the second reload, and `DEBUG` does not leak. But
  `importlib.reload` re-executes into the *existing* module namespace without clearing it, so
  the five names set by the `if not DEBUG:` block are never removed. On the teardown reload
  (`DEBUG=True` locally) the block simply doesn't run, so it cannot unset them. Reproduced
  with a probe module ordered after the security test:

  ```
  before test: DEBUG=True   hasattr(SECURE_SSL_REDIRECT)=False
  after  test: DEBUG=True   hasattr(SECURE_SSL_REDIRECT)=True   value=True   <-- leaked
  ```

  This contradicts the comment at `:29-30` ("so the mutated sys.modules entry does not leak
  DEBUG=False into later tests") — `DEBUG` is what *doesn't* leak. It also falsifies the plan's
  own stated invariant (`plan.md:177-178`: `hasattr(velo_log.settings, "SECURE_SSL_REDIRECT")`
  is `False` on this branch) for the remainder of any session in which this test has run.

  Blast radius today is nil: `django.conf.settings` is a value snapshot taken at
  `django.setup()`, so the reload cannot desynchronize the settings the test client actually
  uses, and the only other direct importer (`test_coverage_scope.py:11`) binds `INSTALLED_APPS`
  at collection time, before any test runs. The defect is a latent order-dependency: the first
  future test that asserts one of these names is *absent*, or compares the module against
  `django.conf.settings`, becomes silently order-dependent.
- **Fix A ⭐ Recommended**: Load the settings source into a throwaway module via
  `importlib.util.spec_from_file_location` + `exec_module`, never registered in `sys.modules`,
  and drop the `try/finally` entirely.
  - Strength: Makes the pollution structurally impossible rather than cleaned up after; removes
    the teardown that has to be correct. Also resolves F5 (no `unittest.mock` needed —
    `monkeypatch.setenv` suffices).
  - Tradeoff: Slightly more machinery in the test (~5 lines of loader boilerplate); a reader
    has to understand why a throwaway module is used.
  - Confidence: HIGH — verified that `django.conf.settings` is a value snapshot, so nothing
    depends on the reload actually mutating `sys.modules`.
  - Blind spot: None significant; the module has no import side effects beyond `read_env`.
- **Fix B**: Keep `reload` but explicitly `delattr` the five names in the `finally` before
  reloading.
  - Strength: Smallest diff; preserves the mechanism the plan prescribed verbatim.
  - Tradeoff: The teardown must be kept in sync by hand with `settings.py:141-150` — add a
    sixth setting to the block and the leak silently returns.
  - Confidence: MEDIUM — works, but it is the same class of hand-maintained list that
    `lessons.md` #4 exists to warn about.
  - Blind spot: Haven't checked whether any future settings name would be shadowed rather
    than added.
- **Decision**: FIXED (Fix A) — `tests/test_settings_security.py` now loads
  `velo_log/settings.py` via `spec_from_file_location`/`exec_module` into a throwaway
  module never registered in `sys.modules`, using `monkeypatch.setenv` instead of
  `mock.patch.dict` + manual reload/`try`/`finally`. Verified: `pytest
  tests/test_settings_security.py` passes, and `pytest --cov` still passes in full
  (30 passed, 93.39%). Also resolves F5's `unittest.mock` pattern-consistency note.

### F2 — The coverage guard defends `source` but not `omit`, and `velo_log/settings.py` is already omitted

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: tests/test_coverage_scope.py:19 (guard) / pyproject.toml:62 (the hole)
- **Detail**: The guard asserts every first-party `INSTALLED_APPS` package appears in
  `[tool.coverage.run] source`. It never looks at `omit`, which is the same silent-defeat path
  by a different route: adding `trips` to `omit` keeps the guard green while making `trips`
  invisible to coverage — exactly the `lessons.md` #4 failure the guard was written to prevent.

  This is not hypothetical. `pyproject.toml:62` already reads
  `omit = ["velo_log/wsgi.py", "velo_log/asgi.py", "velo_log/settings.py"]` (pre-existing,
  added in `c797e2e`, not introduced by this change). So `velo_log/settings.py` — the file
  holding the `if not DEBUG:` block that Phase 1 wrote a dedicated test for, precisely because
  `lessons.md` #3 says high coverage conceals the line that matters — is itself excluded from
  the coverage report. Confirmed: `settings.py` appears nowhere in the 93.39% report. If
  `test_settings_security.py` were deleted tomorrow, coverage would stay at 93.39% and no gate
  would notice.
- **Fix A ⭐ Recommended**: Extend the guard to assert no first-party *app* package appears in
  `omit`, leaving the three `velo_log/` module-level entries alone.
  - Strength: Closes the hole for the case that matters (a whole app going dark) without
    forcing a decision about `settings.py`, and keeps the guard's failure message just as
    actionable.
  - Tradeoff: Needs a distinction between app-package entries and file-path entries in `omit`,
    so the guard grows a little logic.
  - Confidence: HIGH — `omit` entries are paths and `source` entries are packages, so the two
    shapes are cheap to tell apart.
  - Blind spot: A glob in `omit` (e.g. `gpx/*`) would need handling; none exists today.
- **Fix B**: Un-omit `velo_log/settings.py` so the security block is measured, and let coverage
  report on it.
  - Strength: Directly attacks the concrete instance — the block Phase 1 cared about becomes
    visible to the gate rather than trusted to one hand-written test.
  - Tradeoff: `settings.py` is largely unexecutable-under-test boilerplate; measuring it adds
    a chunk of permanently-uncovered lines and pushes total coverage down, possibly needing
    `fail_under` renegotiation — which the plan explicitly ruled out of scope.
  - Confidence: MEDIUM — haven't measured the resulting percentage.
  - Blind spot: Whether the reloaded-module import pattern in F1 would double-count lines.
- **Decision**: PENDING

### F3 — Roadmap backlog table restructured and a second doc touched, beyond the Phase 4 contract

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: context/foundation/roadmap.md:150 / context/foundation/github-issues-migration.md:32
- **Detail**: Phase 4's contract was: flip the `ci-quality-gates` row to `done`, bump
  `updated:`, and add the successor branch-protection row. All three happened. But the
  Engineering Backlog table was also restructured from 3 columns to 6 (adding `Change ID`,
  `Status`, `GitHub Issue`) and rewritten for all eight rows, and
  `github-issues-migration.md` gained a `type:eng-backlog` label row — neither described in
  the plan. These landed in `355f2c9`/`33f80d7` on a separate `docs/ci-quality-gates-follow-up`
  branch, merged as PR #8, *after* `change.md` was already `implemented`, so they read as a
  deliberate follow-up rather than drift smuggled into the change. The commit message even
  self-declares the label as "not part of the original migration scope."

  Worth naming: adding a GitHub-issue link column is partial work on the still-`open` backlog
  row *"Tracker statuses never propagate — GitHub and Linear migrations are documented as
  one-way with no sync back"*, whose own `Change ID` is still `—`. Work was done inside that
  item's territory without touching its row — the same stale-status pattern that row describes.
  (Consistent with this: issue #7 carries `status:done` but is still OPEN on GitHub.)

  Also cosmetic: the roadmap frontmatter `updated:` was never actually edited by any commit in
  the range. Its value `2026-08-23` is correct only because it already matched the change date,
  so the contract's "bumped" step was a no-op rather than performed.
- **Fix**: Record the table restructure as a plan addendum and claim the tracker-sync backlog
  row (set its `Change ID`, or note that the issue-link column is a partial step) so the
  half-done work is visible in the row that owns it.
- **Decision**: PENDING

### F4 — The coverage guard can pass vacuously, and silently exempts apps outside the repo root

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: tests/test_coverage_scope.py:21-25
- **Detail**: Two narrow holes. (1) `first_party_apps` is a set comprehension with no
  non-empty assertion — if it ever computes empty, `missing` is empty and the test passes
  having asserted nothing. A guard that passes vacuously is worse than no guard, because it
  reports green. (2) The `(REPO_ROOT / top_level).is_dir()` filter is what distinguishes
  first-party from `django.contrib.*`, so it is *exemption by default*: an app at `src/gpx/`
  or `apps/gpx/` fails the check and is dropped from consideration — a false pass for exactly
  the case the guard exists to catch. This is acceptable given `AGENTS.md`'s "New Django apps
  belong at the repo root" rule, but the guard's correctness now silently depends on that
  convention holding.

  The path anchoring itself is clean — `REPO_ROOT` is `__file__`-derived (`:13`), so running
  pytest from a subdirectory is fine, and a missing `[tool.coverage.run] source` raises
  `KeyError` rather than passing quietly. Both were checked.
- **Fix**: Add `assert first_party_apps, "guard found no first-party apps — check REPO_ROOT / INSTALLED_APPS"`
  before the `missing` assertion.
- **Decision**: PENDING

### F5 — `unittest.mock` + hand-rolled teardown where `monkeypatch` is the house idiom

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/test_settings_security.py:9-18 / tests/conftest.py:6
- **Detail**: `test_settings_security.py` is the only place in the suite using `unittest` —
  every other test uses pytest idioms and the shared `conftest.py` fixtures. `patch.dict` plus
  a hand-written `try/finally` duplicates what `monkeypatch.setenv` does with automatic
  teardown. Separately, `conftest.py:6` imports `Settings` from `pytest_django.fixtures`, which
  is documented as "the type of the `settings` fixture" but is *not* in that module's `__all__`
  (verified against pytest-django 4.14.0) — correct and mypy-clean today, but off the declared
  public surface, so a minor pytest-django bump could break it. Neither is a defect; both fold
  into F1's rewrite.
- **Fix**: Adopt `monkeypatch.setenv` as part of F1 Fix A; leave the `Settings` import unless a
  pin bump breaks it.
- **Decision**: FIXED (via F1 Fix A) — `test_settings_security.py` now uses
  `monkeypatch.setenv` and no longer imports `unittest.mock`. The `pytest_django.fixtures`
  `Settings` import in `conftest.py:6` is unrelated and left as-is per the note above.

### F6 — The `deploy` job installs uv and syncs a dependency tree nothing uses

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: .github/workflows/deploy.yml:53-57
- **Detail**: With `manage.py check` moved to `gates`, nothing in the `deploy` job invokes
  Python. `railway up` uploads source and Railway builds remotely (the run log shows
  "exporting to docker image format"); `railway.json:4`'s `uv run …` start command executes
  inside the Railway container, not on the runner. So `Install uv` + `uv sync --locked` are
  dead steps: ~40–60s per deploy, and they install and execute the full third-party dependency
  tree (build backends included) inside the one job that carries `RAILWAY_TOKEN`.

  The plan's Performance Considerations framed the double sync as an accepted cost ("`uv sync
  --locked` runs twice per push to `master`… caching is out of scope"). That reasoning treated
  it as unavoidable; it is in fact now unnecessary. Deleting two dead steps is not the "CI
  speed tuning" the scope guard excluded (that was about caching).
  `.venv` is gitignored and the Railway CLI honours `.gitignore`, so nothing is uploaded — this
  is waste, not breakage.
- **Fix**: Delete the `Install uv` and `Install dependencies` steps from the `deploy` job.
- **Decision**: PENDING

### F7 — Unpinned `@railway/cli` runs in the job holding `RAILWAY_TOKEN`

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: .github/workflows/deploy.yml:60 (and :20, :54)
- **Detail**: `npm i -g @railway/cli` resolves to whatever is latest at run time, and the very
  next step passes `RAILWAY_TOKEN` into `railway up` — a compromised release exfiltrates the
  deploy token on the next push to `master`. `astral-sh/setup-uv@v3` is likewise a mutable
  major tag (and now emits a Node 20 deprecation warning in the run log). Both are
  **pre-existing**, not introduced here: the `npm i -g` step is unchanged context in the diff,
  and `setup-uv@v3` is what the plan explicitly specified, so this is plan-conformant. Raised
  because this change rewrote the file and doubled the number of jobs running `setup-uv`.
- **Fix**: Pin `@railway/cli` to an exact version and `astral-sh/setup-uv` to a commit SHA with
  a `# v3.x.y` trailing comment.
- **Decision**: PENDING

### F8 — `AGENTS.md` overstates the CI-equivalence command, and the `gates` job matches it only by coincidence

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: AGENTS.md:43-47 / .github/workflows/deploy.yml:14-15
- **Detail**: Two small inaccuracies, neither currently causing a wrong result.
  (1) `AGENTS.md` says the command "overrides every variable `.env` would otherwise supply",
  but it omits `DB_PATH`, the fourth key in `.env.example`. Harmless in practice — Django's
  SQLite backend uses an in-memory test database, which is why `plan.md:126` correctly decided
  no override was needed — but the "every variable" claim as written is false, and `AGENTS.md`
  loads every session.
  (2) The `gates` job sets only `SECRET_KEY`; `DEBUG` and `ALLOWED_HOSTS` come from the
  `settings.py:31,33` defaults. Those defaults happen to equal what the documented command
  forces (`ALLOWED_HOSTS=` parses to `[]` under django-environ, verified), so the reproduction
  is accurate *today*. But the coupling is invisible: flipping the `DEBUG` default in
  `settings.py` would make CI run `DEBUG=True` while the documented command still forces
  `False`, and the "CI-equivalence" claim would quietly become a lie with nothing failing.
- **Fix**: Set `DEBUG: "False"` and `ALLOWED_HOSTS: ""` explicitly in the `gates` job `env:` so
  the workflow literally matches the documented command, and soften the "every variable"
  sentence to name `DB_PATH` as deliberately unset.
- **Decision**: PENDING

### F9 — The fixture neutralizes one of five settings that still differ between local and CI

- **Severity**: 👁 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: tests/conftest.py:14
- **Detail**: The `if not DEBUG:` block sets five settings. The fixture overrides one
  (`SECURE_SSL_REDIRECT`); `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  `SECURE_PROXY_SSL_HEADER`, and `SECURE_HSTS_SECONDS` remain active in CI and inactive locally
  (where `.env` supplies `DEBUG=True`). The suite passes today only because `django.test.Client`
  returns cookies regardless of the `Secure` attribute and CSRF checks are off unless
  `enforce_csrf_checks=True` — properties of the test client, not of the configuration. So the
  change made CI *pass*; it did not make local and CI *equivalent*, and the next
  environment-sensitive test can still pass locally and fail in CI.

  This is a deliberate, documented plan decision, not drift: `plan.md:128-130` says "Do not
  override `DEBUG` itself in the fixture… Override the single flag that breaks the test client",
  with the rationale of keeping the suite production-like. Recorded so the residual risk is
  visible, not to reopen the call. The mitigation that exists is the CI-equivalence command in
  `AGENTS.md` — a habit rather than a gate.
- **Fix**: No change now. If a second environment-sensitive failure appears, switch
  `DJANGO_SETTINGS_MODULE` to a dedicated `velo_log.settings_test` module rather than adding a
  sixth per-setting override.
- **Decision**: PENDING

### F10 — No `permissions:` block and no `concurrency:` group

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: .github/workflows/deploy.yml:1-13, :46-49
- **Detail**: The workflow declares no `permissions:`, so `GITHUB_TOKEN` scope comes from the
  repository default while `gates` executes PR-branch code (`uv sync` runs build backends,
  `pytest` runs the PR's test files). **This risk is not live**: the repo's
  `default_workflow_permissions` is already `read` (checked via the API), so the token is
  read-only today. An explicit `permissions: contents: read` would make that independent of a
  future repo/org setting change. Choice of `pull_request` over `pull_request_target` is
  correct for this public repo — fork code runs without secret access, and `deploy` is fenced
  behind `github.event_name == 'push'`, so `RAILWAY_TOKEN` can never reach it.

  Separately, no `concurrency:` group means two quick pushes to `master` run two `railway up`
  invocations in parallel with last-writer-wins ordering. Note the plan explicitly excluded
  `concurrency: cancel-in-progress` as speed tuning; a serialization group is a different
  concern but still arguably out of this change's scope.
- **Fix**: Add `permissions:\n  contents: read` above `jobs:`. Leave `concurrency:` for a
  follow-up.
- **Decision**: PENDING

## Notes on what was checked and found clean

- **CI secret containment** — `SECRET_KEY: ci-check-only-not-a-real-secret` is job-scoped to
  `gates` only; the `deploy` job defines no `SECRET_KEY`, so the placeholder cannot reach
  `railway up`. `RAILWAY_TOKEN` is step-scoped inside a job that cannot run on a PR.
- **Deploy gating** — `needs: gates` + `if: github.event_name == 'push'`, with no `always()`,
  no `continue-on-error`, and no step-level `if:` anywhere. Empirically confirmed on three real
  runs (pass/PR, pass/push, fail/PR).
- **Data safety** — no destructive step; the migration gate is `--check --dry-run`; the
  in-memory test database means no run can touch `db.sqlite3` or a developer's `DB_PATH`.
- **Test placement and typing** — both new modules correctly sit at `tests/` root (they test
  project-level config, matching `test_smoke.py`) rather than in the per-app subpackages; both
  functions carry `-> None`; module docstrings explain *why* each guard exists.
- **Migration timing** (pre-existing, out of scope) — `makemigrations --check` proves models and
  migration files agree but never applies anything; migrations actually run at container boot
  via `railway.json`'s `startCommand`, *after* `deploy` reports success. A migration that
  satisfies `--check` but fails against the real database therefore fails post-deploy with
  `gates` green. Relevant to `lessons.md` #9 and worth naming in a change about what deployment
  is gated on; no action required here.
