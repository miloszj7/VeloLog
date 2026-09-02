---
project: velolog
assessed_at: 2026-09-02T00:00:00Z
agent_readiness: ready
context_type: brownfield
stack_components:
  language: Python 3.14
  framework: Django 6.0.5
  build_tool: uv
  test_runner: pytest + pytest-django + pytest-cov
  package_manager: uv
  ci_provider: GitHub Actions
  deployment_target: Railway
gates_passed: 9
gates_failed: 0
---

## Stack Components

**Language**: Python 3.14 (`requires-python = ">=3.14"` in `pyproject.toml`). Type-checked project-wide with `mypy --strict` and the `django-stubs` plugin (`[tool.mypy] strict = true`, `plugins = ["mypy_django_plugin.main"]`), rather than relying on the language's own (optional) type hints.

**Framework**: Django 6.0.5 (`django>=6.0.5` dependency), with `gpxpy` for GPX parsing, `whitenoise` for static-file serving, and `gunicorn` as the WSGI server.

**Build tool / package manager**: `uv`, with a committed `uv.lock`. Tooling (`black`, `isort`, `ruff`, `mypy`, `pytest`) is declared as a `[dependency-groups] dev` block and configured entirely inside `pyproject.toml` — no scattered `.flake8`/`setup.cfg`/`mypy.ini` files.

**Test runner**: `pytest` + `pytest-django` + `pytest-cov`, configured under `[tool.pytest.ini_options]`. Coverage is scoped to `accounts`, `trips`, `gpx`, `velo_log` with `fail_under = 80` and branch coverage on.

**CI/CD**: GitHub Actions (`.github/workflows/deploy.yml`) — a `gates` job (vendored-asset integrity, lint, format, import order, strict typing, `manage.py check`, migration-drift check, `collectstatic`, `pytest --cov`, and a bite-proof mutation-testing gate) must pass before a separate Railway deploy job runs.

**Deployment target**: Railway (`railway.json`), with `DEPLOY.md` documenting `MEDIA_ROOT` and other environment-specific gotchas.

**Instruction files**: both `CLAUDE.md` and `AGENTS.md` are present at the repo root and are substantial — they already document hard rules (ownership scoping, media-root handling, GPX file lifecycle, testing conventions, git workflow) well beyond a stub.

**PRD context used**: `context/foundation/prd-v2.md` (the v1.5 brownfield delta PRD — multi-stage trips, interactive map). Note: `context/foundation/prd.md` on disk is still the original v1 **greenfield** PRD (`context_type: greenfield`, `version: 3`); it was not used as brownfield context here since it predates this change. Its `## Scope of Change` names the same components already detected above — no new stack components are introduced by the v1.5 change; this is a data-model and front-end (map interactivity) change on the existing stack, not a new dependency category, aside from Leaflet's *interactive* mode (already a vendored asset per `gpx/static/gpx/vendor/SHA256SUMS`, so likely a configuration change rather than a new library).

## Quality Gate Assessment

| Component  | Typed | Convention | Training Data | Documented | Verdict |
|------------|-------|------------|----------------|------------|---------|
| Language (Python 3.14) | ✓ | — | — | — | pass |
| Framework (Django 6.0.5) | — | ✓ | ✓ | ✓ | pass |
| Build tool (uv) | — | ✓ | ✓ | ✓ | pass |
| Test runner (pytest + pytest-django) | — | — | ✓ | ✓ | pass |

Legend: ✓ = pass, ✗ = fail, ~ = partial, — = not applicable

### Gate Details

**Typed — pass.** Plain Python has no static typing by default, but this project turns that gate on explicitly: `[tool.mypy] strict = true` plus `plugins = ["mypy_django_plugin.main"]` and the `django-stubs[compatible-mypy]` dev dependency (`pyproject.toml:17-19,48-54`) give an agent real signal on ORM field types, queryset return types, and view signatures without running the app. This is the criteria doc's named pass case ("Python + mypy/pyright in deps/config").

**Convention-based — pass.** Django is the canonical example the criteria doc cites for convention strength ("apps + manage.py + admin"). The repo confirms it's followed as documented, not just installed: `AGENTS.md`'s Project Structure section names exactly where each app (`accounts/`, `trips/`, `gpx/`) lives and what it owns, and states new apps belong at the repo root alongside `velo_log/` — i.e., the project both inherits Django's own conventions and has written them down.

**Popular in training data — pass (per Python-family assessment).** Django is named directly in the criteria doc's Python pass list. `uv` is younger than `pip`/`poetry` but has become the de facto modern Python package manager over the last two years, with heavy adoption and a large, current body of usage examples; not a niche or forked tool. `pytest` is the dominant Python test framework.

**Well-documented — pass.** Django's docs are the criteria doc's canonical "batteries-included docs" example, versioned per release. `uv`'s docs (Astral) are current, versioned, and directly tied to the tool's fast release cadence. `pytest`/`pytest-django` both have mature, current official documentation.

## Gaps & Compensation

No gate failures were found — none of the four criteria fail for any detected component. This section is intentionally empty rather than manufacturing friction to fill it.

One soft observation, not a gate failure: `uv` is newer than `pip`/`poetry`, so an agent's internalized idioms for it are somewhat shallower than for the older tools. The project already compensates for this on its own: `AGENTS.md`'s Hard Rules section states "Use `uv add <pkg>` to install packages, not `pip install`" up front, which is exactly the kind of explicit steering the compensation path (see `references/agent-friendly-criteria.md`) recommends when a tool's training-data depth is thinner than an older alternative's — no further action needed.

### Recommended Instruction File Additions

None required — the existing `CLAUDE.md`/`AGENTS.md` pair already documents the project-specific conventions (ownership scoping, GPX file lifecycle, `uv` usage, testing gates) that a stack at this readiness level would otherwise need spelled out.

## Summary

**Overall verdict: ready.** Every detected stack component — Python 3.14 with `mypy --strict` + `django-stubs`, Django 6.0.5, `uv`, and `pytest`/`pytest-django` — passes all four agent-friendliness criteria, with strict typing added on top of a language that doesn't enforce it by default. This is a stack an agent can navigate largely from convention and typed signatures alone, backed by an unusually thorough pair of instruction files that already codify the project's non-obvious rules (ownership scoping, media lifecycle, testing credibility gates).

**Key strengths**: strict typing enforced project-wide via CI (`makemigrations --check`, `mypy`, `pytest --cov`, plus a bite-proof mutation-testing gate that checks the test suite itself, not just the code); a convention-heavy framework with the project's own conventions layered on top in `AGENTS.md`; a CI pipeline (`.github/workflows/deploy.yml`) that gates deploy on all of the above.

**Key gaps**: none at the stack level. The only open item is process, not stack: `context/foundation/prd.md` is stale relative to the in-flight v1.5 change (it's still the greenfield v1 PRD) — the actual brownfield delta lives in `context/foundation/prd-v2.md`. Worth reconciling naming/versioning before the change ships, but this is a documentation-hygiene note, not an agent-readiness gap.

**Recommended next step**: `/10x-health-check` — dependency audit, security scan, and CI/CD coverage check, focused since this assessment found no stack-level gaps to compensate for.
