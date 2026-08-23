# CI Quality Gates — Plan Brief

> Full plan: `context/changes/ci-quality-gates/plan.md`

## What & Why

CI today runs `manage.py check` plus a migration guard on pushes to `master` and then
deploys — no tests, no lint, no type check, and nothing at all on a pull request. S-03
(`upload-gpx-and-view-map`, the north star) adds file upload and map rendering, where a
silent regression is most costly. This change makes CI a real merge gate and blocks the
Railway deploy on it.

## Starting Point

Every quality gate already passes locally: `ruff`, `black`, `isort`, `mypy --strict` all
clean across 30 files, and 28 tests pass with 93.39% coverage against `fail_under = 80`.
There is no lint or type debt to clean up. But the suite **cannot** pass in CI as it
stands: `velo_log/settings.py:141` turns on `SECURE_SSL_REDIRECT` whenever `DEBUG` is
false, and CI has no `.env` — so every test-client request 301-redirects to https.
Confirmed by experiment (`DEBUG=False uv run pytest tests/trips/test_trip_list.py` →
5 failed, all 301).

## Desired End State

A pull request to `master` runs a `gates` job covering lint, formatting, import order,
strict typing, Django checks, the migration guard, and the test suite with coverage. A
push to `master` runs the same job, and `railway up` executes only if it passed. The
suite's result no longer depends on whether a `.env` file happens to exist.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| CI test environment | Autouse fixture in `tests/conftest.py` overriding `SECURE_SSL_REDIRECT` | Keeps one settings module (AGENTS.md hard rule) and makes the suite `.env`-independent; verified — 28 passed with `DEBUG=False`. |
| Which flags to override | `SECURE_SSL_REDIRECT` only | `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` proved unnecessary: the test client ignores `Secure` and CSRF checks are off by default. |
| Workflow topology | Two jobs, `deploy` gains `needs: gates` | One workflow file, deploy provably blocked by a red gate, and pull requests skip the deploy job entirely. |
| Triggers | `pull_request` → `master` plus existing `push` → `master` | Matches the actual feature-branch + `--no-ff` merge workflow and keeps the deploy gated on the merge commit itself. |
| Coverage scope | Add a guard test asserting first-party `INSTALLED_APPS` ⊆ `[tool.coverage.run] source` | Closes the silent-defeat path in `lessons.md` #4, which bites immediately when S-03 adds a `gpx` app. |
| `fail_under` | Left at 80 | Ratcheting to 93 is a separate decision; the scope guard is the only coverage change here. |
| `.env.example` | Document `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_PATH` | The CI failure traced directly to an undocumented `DEBUG` default. |

## Scope

**In scope:** the autouse test fixture; a production security-settings test; a
coverage-scope guard test; `.env.example` keys; the `deploy.yml` job split and
`pull_request` trigger; `AGENTS.md` and roadmap status.

**Out of scope:** GitHub branch protection (a repo setting, not a commit — needs a click
after merge); dependency caching and CI speed tuning; raising `fail_under`; other
Engineering Backlog items; any application behavior change.

## Architecture / Approach

`deploy.yml` becomes two jobs. `gates` — checkout, `uv sync --locked`, then ruff, black,
isort, mypy, `manage.py check`, `makemigrations --check --dry-run`, `pytest --cov`, with a
CI-only `SECRET_KEY` in the environment. `deploy` keeps the Railway steps and gains
`needs: gates` plus `if: github.event_name == 'push'`, so it is skipped on pull requests
and blocked by a red gate on pushes. Nothing in the application changes; the only
production-code-adjacent edit is a test fixture.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Make the suite CI-safe | Autouse fixture, production security-settings test, `.env.example` keys | The security test must observe the real settings module, not the fixture-mutated live one |
| 2. Coverage-scope guard | Test asserting coverage source covers every first-party app | A meta-test reading `pyproject.toml` is unusual and must fail with a legible message |
| 3. Rewire the workflow | `gates` job + `deploy` gated on it, `pull_request` trigger | First real CI run; a YAML mistake shows up only on GitHub |
| 4. Docs and status | `AGENTS.md` CI section, roadmap row, `change.md` status | Leaving a stale claim that actively misdirects the next agent (`lessons.md` #5) |

**Prerequisites:** none — branch `ci/quality-gates` is cut and the work-start commit
(`fbb1ea6`) has landed. Phase 3 needs a pushed branch and an open PR to verify.
**Estimated effort:** ~1 session across 4 phases; Phases 1–2 are local, Phase 3 needs a
CI round-trip.

## Open Risks & Assumptions

- **Ordering is load-bearing:** Phase 1 must land before Phase 3, or the gate's first run
  is red for a reason unrelated to the code under test.
- The production security block stays unexercised by view tests once the fixture is in
  place; the Phase 1 settings test is what keeps it honest (`lessons.md` #3).
- `.env.example`'s current contents are unverified — the tooling denied read access to
  dotfiles at the repo root, so Phase 1 inspects it before editing.
- Branch protection is not applied by this change, so until it is clicked, a merge can
  still be forced past a red `gates`.

## Success Criteria (Summary)

- A pull request to `master` shows a `gates` check that runs the full quality suite, and
  `deploy` skipped.
- A red gate visibly prevents `railway up` from running.
- `DEBUG=False uv run pytest --cov` passes locally — the same command CI runs, with no
  `.env` required.
