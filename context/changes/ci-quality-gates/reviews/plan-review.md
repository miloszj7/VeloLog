<!-- PLAN-REVIEW-REPORT -->
# Plan Review: CI Quality Gates

- **Plan**: `context/changes/ci-quality-gates/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-23
- **Verdict**: REVISE
- **Findings**: 2 critical, 3 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | WARNING |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

## Grounding

7/7 paths ✓, 5/5 symbols ✓, brief↔plan ✓.

Line references drift slightly (cosmetic, not filed as findings): `[tool.coverage.run]`
is `pyproject.toml:60-62`, not `:60-66`; the inline-`SECRET_KEY` step is
`.github/workflows/deploy.yml:20-25`, not `:24-30`. All `velo_log/settings.py`
references (`:21`, `:28`, `:31`, `:86`, `:141-151`, `:147`) are exact.

Codebase claims were verified inline rather than via a sub-agent (session policy).
Live checks run:

- `uv run python -c "import velo_log.settings"` → `DEBUG=True`,
  `hasattr(s, "SECURE_SSL_REDIRECT")` → `False`
- `git show HEAD:.env.example` → four keys, no comments
- `velo_log/settings.py:38-47` INSTALLED_APPS, `pyproject.toml` coverage/mypy/pytest
  config, `.github/workflows/deploy.yml` in full, `context/foundation/roadmap.md:144-158`

Progress↔Phase mechanical contract: **PASS**. One `## Progress` heading; all four
phase headings match verbatim; every success-criteria bullet has a numbered checkbox
(1.1–1.7, 2.1–2.4, 3.1–3.7, 4.1–4.4); no stray checkboxes in phase bodies.

## Findings

### F1 — `gates` job will fail on mypy and pytest for a missing SECRET_KEY

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 3 — Workflow split, Contract bullet 2
- **Detail**: The contract says "All Django-touching steps need `SECRET_KEY` in the
  environment" without naming which steps those are. An implementer copying the
  existing pattern at `deploy.yml:20-25` — where `env:` sits on the `manage.py check`
  step only — will plausibly conclude that only that step qualifies. Two more steps
  import the settings module and hard-fail without it: `mypy .`, because
  `[tool.django-stubs] django_settings_module = "velo_log.settings"`
  (`pyproject.toml:52-53`) makes the plugin import the module at type-check time; and
  `pytest --cov`, because pytest-django runs `django.setup()` from
  `DJANGO_SETTINGS_MODULE` (`pyproject.toml:56`). `SECRET_KEY = env("SECRET_KEY")`
  (`velo_log/settings.py:28`) is the one var with no default and CI has no `.env`, so
  both raise ImproperlyConfigured. This is exactly the class of failure Phase 1 exists
  to prevent — the gate's first run goes red for an environment reason, not a code one.
- **Fix**: Put `env: SECRET_KEY: ci-check-only-not-a-real-secret` at the **job** level
  on `gates` rather than per-step, and state that explicitly in the contract so the
  choice isn't left to inference.
  - Strength: One declaration covers check, makemigrations, mypy and pytest, and stays
    correct when a future step is added — ruff/black/isort simply ignore it. Removes
    the "which steps count?" judgment call entirely.
  - Tradeoff: Slightly less explicit than per-step `env:` about which steps consume it;
    diverges from the existing per-step style in `deploy.yml`.
  - Confidence: HIGH — `SECRET_KEY` has no default in `settings.py:28`, and both
    django-stubs and pytest-django import that module by design.
  - Blind spot: Not reproducible locally — `.env` supplies `SECRET_KEY` via `read_env`,
    so the failure only appears on the first CI run. Same root cause as F3.
- **Decision**: PENDING

### F2 — Security test offers two mechanisms; one of them fails locally

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — Change 2, Contract
- **Detail**: The contract says the test must read from a freshly-evaluated settings
  module "e.g. via `importlib` reload under a patched environment, **or** by asserting
  on the module-level constants," presenting the two as interchangeable. They are not.
  Verified on this branch: `DEBUG=True` locally, and
  `hasattr(velo_log.settings, "SECURE_SSL_REDIRECT")` is `False` — the `if not DEBUG:`
  block at `settings.py:141` never executes, so those constants do not exist as module
  attributes. The second mechanism raises AttributeError under a plain
  `uv run pytest`, directly failing the phase's own success criterion 1.2 ("Full suite
  still passes normally"). It would pass only in CI — the worst possible split.
- **Fix**: Drop the "or by asserting on the module-level constants" alternative.
  Mandate `importlib.reload` under `mock.patch.dict(os.environ, {"DEBUG": "False"})`
  — `read_env` uses setdefault semantics, so the patched value wins — and require a
  reload back to the unpatched state afterwards so the mutated `sys.modules` entry
  doesn't leak into later tests.
- **Decision**: PENDING

### F3 — "Reproducing the CI environment locally" doesn't reproduce it

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Critical Implementation Details; Phase 4 Change 1; Desired End State
- **Detail**: The plan states that prefixing `DEBUG=False` "simulates the `.env`-less
  CI environment." It does not. `read_env` (`settings.py:21`) still loads `.env`, which
  continues to supply `SECRET_KEY`, `ALLOWED_HOSTS` and `DB_PATH`; only `DEBUG` is
  overridden. That is exactly the blind spot F1 falls into. The consequence compounds:
  Phase 4 writes this same command into `AGENTS.md` as the way to reproduce a CI
  failure, making an inaccurate claim permanent in the file that loads every session
  (`lessons.md` #5 in spirit). And the Desired End State's promise — "the suite's
  result no longer depends on whether a `.env` file happens to exist" — is only true
  for `DEBUG`; without `.env` and without an explicit `SECRET_KEY`, the suite cannot
  start at all.
- **Fix**: Define the reproduction as overriding every var `.env` supplies, e.g.
  `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`,
  and use that exact string in Phase 4's `AGENTS.md` text and in the Phase 1/2/3
  success criteria that currently read `DEBUG=False uv run pytest --cov`. Soften the
  Desired End State to "no longer depends on `.env` for anything but `SECRET_KEY`,
  which CI supplies explicitly."
  - Strength: Makes the local command genuinely equivalent to the CI step, so
    F1-class failures surface before the push rather than on GitHub. Costs nothing —
    `read_env` setdefault semantics mean explicit shell vars already win.
  - Tradeoff: A longer, less memorable command in the docs; four criteria lines and one
    `AGENTS.md` paragraph need the updated string.
  - Confidence: HIGH — confirmed `.env` is present and supplies `DEBUG=True`;
    `.env.example` shows the same four keys are the full set.
  - Blind spot: Whether the local `.env` sets `ALLOWED_HOSTS` to a non-empty value
    wasn't readable (dotfile access denied), so the exact divergence on that one var is
    unverified. `setup_test_environment()` appends `testserver` regardless, so it
    shouldn't matter.
- **Decision**: PENDING

### F4 — Coverage guard's "first-party" heuristic will misfire

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architectural Fitness
- **Location**: Phase 2 — Change 1, Contract
- **Detail**: The contract defines first-party as "any `INSTALLED_APPS` entry that does
  not start with `django.`". Correct for today's list (`settings.py:38-47` is
  `django.contrib.*` plus `accounts`, `trips`), but it breaks on two shapes the very
  next slice can introduce. A third-party app (`whitenoise.runserver_nostatic`,
  `django_extensions`) would be wrongly demanded in coverage source. A dotted AppConfig
  path (`gpx.apps.GpxConfig`, which `startapp` scaffolding encourages) would never
  string-match the `"gpx"` entry in `source` and would fail even when correctly
  configured. Either way the guard produces a false red on S-03 — the exact slice it
  was written for.
- **Fix**: Normalize each entry to its top-level package (`entry.split(".")[0]`) and
  treat it as first-party only if a directory of that name exists at the repo root.
  Compare that normalized set against `source`.
- **Decision**: PENDING

### F5 — Backlog row marked `done` while the thing that makes it a gate is unapplied

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: End-State Alignment
- **Location**: Phase 4 — Change 2; "What We're NOT Doing"
- **Detail**: Branch protection is correctly scoped out (it's a repo setting, not a
  commit). But Phase 4 moves the Engineering Backlog row (`roadmap.md:152`) to `done`,
  and that row is the only durable record of this work item. After the merge, nothing
  in the repo says a merge can still be forced past a red `gates` — the reminder lives
  only in `plan-brief.md`'s Open Risks, which nobody reads once the change closes.
- **Fix**: In Phase 4, alongside marking the row `done`, add a new Engineering Backlog
  row: "`gates` is not a required check — a merge can still be forced past a red run",
  fix = enable branch protection on `master` requiring `gates`, trigger = "immediately
  after this change merges".
- **Decision**: PENDING

### F6 — `.env.example` already has all four keys

- **Severity**: 💭 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — Change 3
- **Detail**: The brief listed `.env.example` contents as unverified. They are:
  `SECRET_KEY=`, `DEBUG=False`, `ALLOWED_HOSTS=`, `DB_PATH=` — all four keys present,
  zero comments. So the contract's "add only what is missing" reduces to "add
  comments"; there are no missing keys. Worth noting because the committed
  `DEBUG=False` is itself the trap: a contributor who copies `.env.example` to `.env`
  verbatim gets the 301 failure the plan describes.
- **Fix**: Reword the contract to "the keys are already present — add a comment to
  each" and require the `DEBUG` comment to say that copying `False` here is intentional
  and safe only because the Phase 1 fixture neutralizes the HTTPS redirect under test.
- **Decision**: PENDING

## Notes

**Lean Execution: PASS.** Every phase is load-bearing — remove Phase 1 and the gate is
red on arrival; remove Phase 2 and lesson #4's silent-defeat path stays open right
before S-03 adds `gpx`; Phase 3 is the change itself; Phase 4 is lesson #5. Scope
exclusions (caching, `fail_under` ratchet, branch protection) hold — nothing excluded
reappears in a phase.

The approach is sound. F1 is the one that would actually cost a CI round-trip, and it
and F3 share a root cause: `.env` masks the missing-`SECRET_KEY` condition locally.
