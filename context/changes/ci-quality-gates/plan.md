# CI Quality Gates Implementation Plan

## Overview

Turn CI from a smoke check into a real merge gate. Today `.github/workflows/deploy.yml`
runs `manage.py check` plus a migration guard on `push: master` and then deploys — no
tests, no lint, no type check, and nothing at all on a pull request. This change adds a
`gates` job that runs the full quality suite, makes the deploy depend on it, and fires it
on pull requests as well as pushes to `master`.

The trigger for doing this now is the Engineering Backlog row in
`context/foundation/roadmap.md`: *before S-03*, the north star slice, which adds file
upload and map rendering — the place where a silent regression is most costly.

## Current State Analysis

**The gates all pass locally today.** Measured on this branch before planning:

| Gate | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run black --check .` | 30 files unchanged |
| `uv run isort --check-only .` | clean (3 files skipped) |
| `uv run mypy .` | Success: no issues in 30 source files |
| `uv run pytest --cov` | 28 passed, coverage 93.39% vs `fail_under = 80` |

So there is **no pre-existing lint/type debt to clean up**. This change is CI wiring plus
one test-environment fix.

**The suite cannot pass in CI as it stands.** `velo_log/settings.py:141` gates production
hardening on `if not DEBUG:`, which sets `SECURE_SSL_REDIRECT = True`. `DEBUG` comes from
`env.bool("DEBUG", default=False)` (`velo_log/settings.py:31`), read from `.env` via
`environ.Env.read_env` (`velo_log/settings.py:21`). CI has no `.env`, so `DEBUG` is
`False`, `SECURE_SSL_REDIRECT` is `True`, and every Django test-client request returns
`301` to `https://testserver/`. Verified:

```
DEBUG=False uv run pytest tests/trips/test_trip_list.py  →  5 failed, all 301
```

Locally the suite passes only because a `.env` file supplies `DEBUG`. The gate would be
red on its first run for a reason unrelated to the code under test.

**The fix is one autouse fixture, verified end to end.** Overriding *only*
`SECURE_SSL_REDIRECT` in `tests/conftest.py` makes the full suite pass with `DEBUG=False`
— 28 passed. `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` need no override: the
Django test client does not enforce the `Secure` cookie attribute, and CSRF checks are
off unless a client is constructed with `enforce_csrf_checks=True`.

**Workflow shape.** `deploy.yml` is a single `deploy` job in which `manage.py check` and
`railway up` are sequential *steps*. Gating therefore requires splitting into two jobs
linked by `needs:` — adding another step would not let a pull request run the checks
without also attempting a deploy.

### Key Discoveries:

- `velo_log/settings.py:141-151` — the `if not DEBUG:` production block is the sole reason
  the suite is environment-sensitive. `SECURE_SSL_REDIRECT` at `:147` is the only flag in
  it that breaks tests.
- `.github/workflows/deploy.yml:24-30` — `SECRET_KEY: ci-check-only-not-a-real-secret` is
  already supplied inline for `manage.py check`; the new `gates` job needs the same, since
  `SECRET_KEY` is the one env var with no default (`velo_log/settings.py:28`).
- `pyproject.toml:60-66` — `[tool.coverage.run] source = ["accounts", "trips", "velo_log"]`
  is a hand-maintained list. `lessons.md` #4 records that `fail_under` is silently defeated
  the moment a new app's code isn't in `source`. S-03 is expected to add a `gpx` app.
- `pyproject.toml:55-58` — pytest is already wired to `velo_log.settings` with
  `testpaths = ["tests"]`; no test-runner configuration change is needed.
- Django's SQLite backend uses an in-memory test database by default, so `DB_PATH`
  (`velo_log/settings.py:86`) needs no CI-specific value.
- `tests/conftest.py` already holds the shared fixtures (`rider`, `other_rider`,
  `auth_client`) — the autouse fixture belongs alongside them, not in a new file.

## Desired End State

A pull request targeting `master` runs a `gates` job covering lint, formatting, import
order, strict typing, Django checks, the migration guard, and the test suite with
coverage. A push to `master` runs the same job, and `railway up` executes only if it
passed. The suite's result no longer depends on `.env` for anything but `SECRET_KEY`,
which CI supplies explicitly at the job level.

Verify by: opening the PR for this branch and observing the `gates` check run and pass,
and confirming the deploy job reports as skipped on the PR run.

## What We're NOT Doing

- **GitHub branch protection** — requiring the `gates` check before merge is a repository
  setting, not a file in the repo. It cannot be done from a commit; flagged for the user
  to click after merge, and recorded as a successor Engineering Backlog row in Phase 4 so
  the reminder outlives this change folder.
- **Dependency caching or CI speed tuning** — no `actions/cache`, no uv cache key, no
  `concurrency: cancel-in-progress`. The whole suite runs in ~25s; optimizing is premature.
- **Raising `fail_under`** — it stays at 80 despite actual coverage being 93%. The scope
  guard in Phase 2 is the only coverage-related change.
- **Other Engineering Backlog items** — structured logging, the `/data/db.sqlite3` restore
  drill, the `railway.json` → `.railway/railway.ts` migration. Each has its own trigger.
- **Any application behavior change** — no view, model, form, template, or URL is touched.
- **Testing the production security branch through the test client** — the settings
  assertion in Phase 1 covers its configuration, not its runtime HTTP behavior.

## Implementation Approach

Fix the test environment first, then the workflow. Phase 1 must land before Phase 3, or
the first CI run is red for an unrelated reason and the gate's first impression is a false
positive on a real problem. Phases 1 and 2 are both verifiable locally with the exact
command CI will run, so the workflow change in Phase 3 carries almost no risk by the time
it lands.

## Critical Implementation Details

**Ordering.** Phase 1's fixture must be committed before Phase 3's workflow change. The
converse order produces a red gate whose cause is the settings divergence, not the code.

**Reproducing the CI environment locally.** `.env` is read via `os.environ.setdefault`
semantics, so explicit shell variables win over the file — but only for the vars actually
overridden. `DEBUG=False` alone is *not* a CI simulation: `.env` still supplies
`SECRET_KEY`, `ALLOWED_HOSTS` and `DB_PATH`, which is precisely the blind spot that made
F1 possible. Override everything `.env` provides:

```
SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov
```

This exact string is the **CI-equivalence command**, and it is the string that goes into
`AGENTS.md` in Phase 4 and into every success criterion below. Running the suite the normal
way will not catch a regression in it. (`DB_PATH` needs no override — the SQLite backend
uses an in-memory test database.)

**Do not override `DEBUG` itself in the fixture.** Overriding `DEBUG` would re-run the
whole `if not DEBUG:` block's inverse and defeat the point of keeping the suite
production-like. Override the single flag that breaks the test client.

## Phase 1: Make the test suite CI-safe

### Overview

Neutralize the one production setting that breaks the Django test client in a `.env`-less
environment, cover the production security branch that the override now hides, and
document `DEBUG` so the divergence doesn't bite the next contributor.

### Changes Required:

#### 1. Autouse test fixture

**File**: `tests/conftest.py`

**Intent**: Make every test run against HTTP regardless of whether `DEBUG` resolves true
or false, so the suite's result is independent of the presence of a `.env` file.

**Contract**: A new autouse fixture, alongside the existing `rider` / `other_rider` /
`auth_client` fixtures, that sets `SECURE_SSL_REDIRECT = False` via pytest-django's
`settings` fixture. It must not touch `DEBUG`, `SESSION_COOKIE_SECURE`, or
`CSRF_COOKIE_SECURE` — verified unnecessary. Annotate the `settings` parameter so
`mypy --strict` passes (the fixture is untyped in pytest-django's stubs).

#### 2. Production security-settings test

**File**: `tests/test_settings_security.py` (new)

**Intent**: The Phase 1 fixture hides the production security branch from every view test,
so assert its configuration directly — otherwise the block at `velo_log/settings.py:141`
becomes code no test observes. This is `lessons.md` #3 applied: high coverage concealing
the one line that matters.

**Contract**: A test that, with `DEBUG` false, asserts `SECURE_SSL_REDIRECT`,
`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` are `True`, `SECURE_PROXY_SSL_HEADER`
equals `("HTTP_X_FORWARDED_PROTO", "https")`, and `SECURE_HSTS_SECONDS` is positive. It
must read the values from a freshly-evaluated settings module rather than the live
`django.conf.settings`, since the autouse fixture has already mutated the latter.

The mechanism is **`importlib.reload(velo_log.settings)` inside
`mock.patch.dict(os.environ, {"DEBUG": "False"})`** — `read_env` uses `setdefault`
semantics, so the patched value wins over `.env`. Reload the module again outside the
patch as teardown, so the mutated `sys.modules` entry does not leak into later tests.

Do **not** assert on the module-level constants directly instead: locally `DEBUG` is true,
the `if not DEBUG:` block at `settings.py:141` never executes, and those names do not
exist as module attributes — verified, `hasattr(velo_log.settings, "SECURE_SSL_REDIRECT")`
is `False` on this branch. That variant would pass in CI and raise `AttributeError` under a
plain `uv run pytest`, breaking success criterion 1.2.

The test must fail if the `if not DEBUG:` block is deleted.

#### 3. Environment documentation

**File**: `.env.example`

**Intent**: The CI failure traced directly to an undocumented `DEBUG` default; document it
so a fresh checkout knows which variables shape behavior.

**Contract**: All four keys are **already present** — verified: `SECRET_KEY=`,
`DEBUG=False`, `ALLOWED_HOSTS=`, `DB_PATH=`, with zero comments. So this change is purely
additive commentary: add a short comment to each key noting its default and effect. Do not
add keys and do not restructure the file.

The `DEBUG` comment must address the trap the committed value creates: a contributor who
copies `.env.example` to `.env` verbatim inherits `DEBUG=False`, which turns on the HTTPS
redirect and produces the 301 failures described in Current State Analysis. State that the
committed `False` is intentional (it matches the production default and CI) and that it is
safe under test only because the Phase 1 autouse fixture neutralizes
`SECURE_SSL_REDIRECT`.

### Success Criteria:

#### Automated Verification:

- Full suite passes under the CI-equivalence command: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- Full suite still passes normally: `uv run pytest --cov`
- Coverage remains at or above `fail_under = 80`
- Strict typing passes on the new fixture and test: `uv run mypy .`
- Lint and format gates pass: `uv run ruff check . && uv run black --check . && uv run isort --check-only .`
- The security test fails when the `if not DEBUG:` block is temporarily removed (mutation check, then revert)

#### Manual Verification:

- `.env.example` reads as useful guidance to someone cloning the repo for the first time

**Implementation Note**: After completing this phase and all automated verification
passes, pause for manual confirmation before proceeding.

---

## Phase 2: Coverage-scope guard

### Overview

Close the silent-defeat path recorded in `lessons.md` #4: a new app whose package is
absent from `[tool.coverage.run] source` is invisible to coverage, and `fail_under` passes
while that app is entirely untested. S-03 adds a `gpx` app, so this matters on the very
next slice.

### Changes Required:

#### 1. Coverage-scope test

**File**: `tests/test_coverage_scope.py` (new)

**Intent**: Fail the build when a local application package is in `INSTALLED_APPS` but not
in the coverage source list, so the coverage gate cannot be silently narrowed.

**Contract**: A test that reads `[tool.coverage.run] source` from `pyproject.toml` (via
`tomllib`, stdlib on 3.14) and asserts every first-party `INSTALLED_APPS` package appears
in it. The failure message must name the missing package and point at `pyproject.toml` so
the fix is obvious from CI logs alone.

**First-party detection**: normalize each `INSTALLED_APPS` entry to its top-level package
(`entry.split(".")[0]`) and treat it as first-party only if a directory of that name exists
at the repo root. Compare that normalized set against `source`.

Do **not** use "does not start with `django.`" as the test. It is accurate for today's
list (`settings.py:38-47` is `django.contrib.*` plus `accounts`, `trips`) but breaks on two
shapes the next slice can introduce, and in both directions:

- A third-party app (`whitenoise.runserver_nostatic`, `django_extensions`) would be wrongly
  demanded in coverage `source` — the repo-root directory check excludes it.
- A dotted AppConfig path (`gpx.apps.GpxConfig`, which `startapp` scaffolding encourages)
  would never string-match the `"gpx"` entry in `source` and would fail even when correctly
  configured — normalizing to the top-level package fixes it.

Either miss produces a false red on S-03, the exact slice this guard was written for.

### Success Criteria:

#### Automated Verification:

- Suite passes under the CI-equivalence command: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- The guard fails when an entry is temporarily removed from `[tool.coverage.run] source` (mutation check, then revert)
- Strict typing, lint, and format gates pass

#### Manual Verification:

- The assertion message, read cold, tells the reader exactly which package to add and where

**Implementation Note**: Pause for manual confirmation before proceeding.

---

## Phase 3: Rewire the deploy workflow

### Overview

Split the single `deploy` job into a `gates` job and a `deploy` job that depends on it,
and fire the workflow on pull requests to `master` as well as pushes to it.

### Changes Required:

#### 1. Workflow split

**File**: `.github/workflows/deploy.yml`

**Intent**: Run the full quality suite as its own job on both pull requests and pushes to
`master`, and make the Railway deploy conditional on that job succeeding — so a red gate
provably blocks a deploy, and a pull request gets checked without attempting one.

**Contract**:
- `on:` gains `pull_request: branches: [master]` alongside the existing
  `push: branches: [master]`.
- A new `gates` job on `ubuntu-latest`: checkout, `astral-sh/setup-uv@v3`,
  `uv sync --locked`, then `ruff check .`, `black --check .`, `isort --check-only .`,
  `mypy .`, `manage.py check`, `makemigrations --check --dry-run`, and `pytest --cov`.
- `SECRET_KEY: ci-check-only-not-a-real-secret` is declared **at the job level** on
  `gates` (a `env:` block on the job, not on individual steps), reusing the existing
  inline CI-only value from `deploy.yml`. This is deliberate and must not be narrowed to
  per-step: four of the steps import the settings module, and `SECRET_KEY` is the one env
  var with no default (`velo_log/settings.py:28`), so each would raise
  `ImproperlyConfigured` in a `.env`-less runner. `manage.py check` and
  `makemigrations --check` import it directly; `mypy .` imports it because
  `[tool.django-stubs] django_settings_module = "velo_log.settings"`
  (`pyproject.toml:52-53`) makes the plugin load it at type-check time; `pytest --cov`
  imports it because pytest-django calls `django.setup()` from `DJANGO_SETTINGS_MODULE`
  (`pyproject.toml:56`). The ruff/black/isort steps simply ignore it. Job-level scope also
  stays correct when a future step is added.
- The `deploy` job keeps its Railway steps, gains `needs: gates`, and gains
  `if: github.event_name == 'push'` so pull requests never deploy. Its now-redundant
  `manage.py check` / `makemigrations` step is removed, since `gates` owns it.
- Step names should read as gate names in the GitHub UI (e.g. "Lint", "Types", "Tests")
  rather than raw commands, so a failure is identifiable from the checks list.

The workflow name should stop claiming it only deploys — it now gates as well.

### Success Criteria:

#### Automated Verification:

- Workflow YAML parses and the run appears on the PR: the `gates` check is listed on the pull request for this branch
- `gates` passes on the pull request
- The `deploy` job reports as skipped on the pull-request run
- Every command in `gates` matches one that passes locally under the CI-equivalence command's environment (`SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS=`)

#### Manual Verification:

- On the PR's Checks tab, a deliberately-broken commit (e.g. a formatting violation) shows `gates` red and `deploy` skipped — then revert it
- After merge to `master`, `gates` runs first and `railway up` runs only after it is green
- The deployed app still responds on `/healthz/`

**Implementation Note**: Pause for manual confirmation before proceeding.

---

## Phase 4: Documentation and status

### Overview

Record the new gate where the next agent will read it, and advance the change and roadmap
status. `lessons.md` #5: update `AGENTS.md` in the same slice that invalidates it.

### Changes Required:

#### 1. Contributor documentation

**File**: `AGENTS.md`

**Intent**: The Testing section currently describes local tooling only; a reader cannot
tell that CI enforces it or that the suite must pass with no `.env`.

**Contract**: Extend the Testing / Commits sections to state that `gates` runs lint,
format, import order, strict typing, Django checks, the migration guard, and
`pytest --cov` on every pull request to `master` and every push to it, that the Railway
deploy is blocked on it, and that the suite must pass with no `.env` present. Quote the
CI-equivalence command verbatim as the way to reproduce a CI failure locally:
`SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`.
Do not write `DEBUG=False uv run pytest` — that leaves `.env` supplying `SECRET_KEY` and
`ALLOWED_HOSTS`, so it does not reproduce CI, and `AGENTS.md` loads every session.

#### 2. Roadmap and change status

**File**: `context/foundation/roadmap.md`, `context/changes/ci-quality-gates/change.md`

**Intent**: Reflect that the backlog item is done rather than in progress, and that the
change is implemented.

**Contract**: The Engineering Backlog row for `ci-quality-gates` moves to `done`; the
frontmatter `updated:` is bumped. `change.md` frontmatter `status:` advances per the
change lifecycle and `updated:` is bumped.

In the same edit, add a **new** Engineering Backlog row so the unapplied half of the gate
stays recorded in the repo: gap = "`gates` is not a required check — a merge can still be
forced past a red run", fix = "enable branch protection on `master` requiring the `gates`
check", trigger = "immediately after this change merges". Without it, the row being marked
`done` is the only durable trace of this work item, and the branch-protection reminder
survives only in `plan-brief.md`'s Open Risks — which nobody reads once the change closes.

### Success Criteria:

#### Automated Verification:

- Full gate suite passes locally: the CI-equivalence command (`SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`), `uv run mypy .`, `uv run ruff check .`, `uv run black --check .`, `uv run isort --check-only .`
- No stale claim remains in `AGENTS.md`: its description of coverage scope and CI matches `pyproject.toml` and `deploy.yml`

#### Manual Verification:

- `AGENTS.md` read cold explains what CI enforces and how to reproduce a CI failure locally
- The roadmap's Engineering Backlog row no longer claims the CI gap exists
- A successor Engineering Backlog row records that `gates` is not yet a required check

---

## Testing Strategy

### Unit Tests:

- Production security settings are configured when `DEBUG` is false (Phase 1)
- Coverage source list covers every first-party `INSTALLED_APPS` package (Phase 2)
- Both are mutation-checked: temporarily break the thing each guards, confirm the test
  goes red, revert

### Integration Tests:

- The workflow itself is the integration test. The pull request for this branch is the
  first real run, and a deliberately-broken commit confirms the gate blocks rather than
  merely reports.

### Manual Testing Steps:

1. Run the CI-equivalence command
   `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
   — this is what CI does; it must pass.
2. Open the PR and confirm `gates` appears and passes, and `deploy` is skipped.
3. Push a formatting violation; confirm `gates` fails and `deploy` does not run. Revert.
4. Merge and confirm `gates` → `deploy` ordering, then hit `/healthz/` on the deployed app.

## Performance Considerations

`uv sync --locked` runs twice per push to `master` (once per job), adding roughly a minute
of wall clock to a deploy. Accepted deliberately: caching is out of scope while the suite
finishes in ~25s, and correctness of the gate matters more than its speed at this size.

## Migration Notes

None — no schema, no data, no runtime behavior change. The only rollback needed is
reverting `deploy.yml`, which restores the previous ungated deploy exactly.

## References

- Roadmap Engineering Backlog row: `context/foundation/roadmap.md`
- Recurring rules applied: `context/foundation/lessons.md` #3 (coverage concealing the line
  that matters), #4 (widen coverage source when a package ships), #5 (update `AGENTS.md`
  in the same slice), #9 (the migration guard CI already runs)
- Existing workflow: `.github/workflows/deploy.yml`
- Settings block that forced Phase 1: `velo_log/settings.py:141-151`
- Existing fixtures the new one joins: `tests/conftest.py`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Make the test suite CI-safe

#### Automated

- [x] 1.1 Full suite passes under the CI-equivalence command (`SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`) — ac1356c
- [x] 1.2 Full suite still passes normally (`uv run pytest --cov`) — ac1356c
- [x] 1.3 Coverage remains at or above `fail_under = 80` — ac1356c
- [x] 1.4 Strict typing passes on the new fixture and test (`uv run mypy .`) — ac1356c
- [x] 1.5 Lint and format gates pass (ruff, black, isort) — ac1356c
- [x] 1.6 Security test fails when the `if not DEBUG:` block is removed (mutation check, then revert) — ac1356c

#### Manual

- [x] 1.7 `.env.example` reads as useful guidance for a first-time clone — ac1356c

### Phase 2: Coverage-scope guard

#### Automated

- [x] 2.1 Suite passes under the CI-equivalence command (`SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`) — c5d77ed
- [x] 2.2 Guard fails when an entry is removed from `[tool.coverage.run] source` (mutation check, then revert) — c5d77ed
- [x] 2.3 Strict typing, lint, and format gates pass — c5d77ed

#### Manual

- [x] 2.4 Assertion message names the missing package and where to add it — c5d77ed

### Phase 3: Rewire the deploy workflow

#### Automated

- [x] 3.1 `gates` check is listed on the pull request for this branch
- [x] 3.2 `gates` passes on the pull request
- [x] 3.3 `deploy` job reports as skipped on the pull-request run
- [x] 3.4 Every command in `gates` matches one that passes locally under the CI-equivalence command's environment

#### Manual

- [x] 3.5 A deliberately-broken commit shows `gates` red and `deploy` skipped, then reverted
- [ ] 3.6 After merge, `gates` runs before `railway up`
- [ ] 3.7 Deployed app still responds on `/healthz/`

### Phase 4: Documentation and status

#### Automated

- [ ] 4.1 Full gate suite passes locally under the CI-equivalence command (tests, mypy, ruff, black, isort)
- [ ] 4.2 No stale CI or coverage-scope claim remains in `AGENTS.md`

#### Manual

- [ ] 4.3 `AGENTS.md` read cold explains what CI enforces and how to reproduce a failure locally
- [ ] 4.4 Roadmap Engineering Backlog row no longer claims the CI gap exists
- [ ] 4.5 Successor Engineering Backlog row records that `gates` is not yet a required check
