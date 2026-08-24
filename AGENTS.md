# Repository Guidelines

VeloLog is a greenfield Django 6 web app — a trip-centric personal diary for multi-day cycling tours, aggregating GPX tracks and trip context into a single view. Stack: Python 3.14, Django 6.0.5, uv package manager, SQLite.

## Hard Rules

- **Never write to `context/archive/`** — content there is immutable; open a new change with `/10x-new` instead.
- **Use `uv add <pkg>` to install packages**, not `pip install`. Direct pip calls bypass the lockfile (`uv.lock`).
- The Django settings module is `velo_log.settings`. Do not create a parallel settings file without updating `manage.py` and `velo_log/wsgi.py`.

## Project Structure

- `velo_log/` — Django project package (settings, urls, wsgi, asgi). Not for application code.
- `manage.py` — Django CLI entry point; always invoke via `uv run python manage.py`.
- `pyproject.toml` — single source of truth for dependencies and tool config.
- `context/` — 10x PRD/shaping artifacts. See `@context/foundation/prd.md` for scope and `@context/foundation/tech-stack.md` for stack rationale.
- `templates/` — project-level shared templates (`base.html` and other cross-cutting chrome that doesn't belong to a single app). `TEMPLATES[0]["DIRS"]` points here; `APP_DIRS` stays `True` so app-namespaced templates still resolve.
- `accounts/` — registration, login/logout.
- `trips/` — the second feature app: create and list a user's trips.

New Django apps belong at the **repo root** alongside `velo_log/` (e.g. `trips/`, `gpx/`), registered in `velo_log/settings.py` under `INSTALLED_APPS`.

## Development Commands

| Command | Purpose |
|---|---|
| `uv run python manage.py runserver` | Start dev server |
| `uv run python manage.py migrate` | Apply migrations |
| `uv run python manage.py makemigrations <app>` | Create migration for an app |
| `uv add <package>` | Add dependency (updates `pyproject.toml` + `uv.lock`) |
| `uv sync` | Sync venv to lockfile after pulling |

## Coding Style & Naming

Python 3.14 — modern type syntax (`X | Y`, `list[str]`, `dict[str, Any]`) is native; `from __future__ import annotations` is not required. Follow `@~/.claude/CLAUDE.md` for all other Python standards: naming, type hints, logging, error handling, Pydantic vs dataclass choice, and project layout within each app.

Linting is configured in `pyproject.toml`: `ruff`, `black`, `isort`, and `mypy --strict` (with `django-stubs`). Run via `/python-quality-gates` before reporting a task done.

## Testing

`pytest` + `pytest-django` are configured; tests live in `tests/` at the repo root. Coverage runs against `accounts`, `trips`, and `velo_log` with `fail_under = 80` (`[tool.coverage.run]` / `[tool.coverage.report]` in `pyproject.toml`). See `@~/.claude/CLAUDE.md` for fixture patterns and integration-test skip conventions.

The suite must pass with **no `.env` present** — CI never has one. Reproduce a CI failure locally with the CI-equivalence command, which overrides every `.env` variable except `DB_PATH` (deliberately unset — the test suite uses an in-memory SQLite database, so no DB file path is ever read):

```
SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov
```

## Commits & Git Workflow

Follow `@~/.claude/rules/git-workflow.md`: Conventional Commits format, feature branches
only (never commit straight to `master`), merge with `--no-ff`, never squash. Use the
`create-pr` skill to open a GitHub/GitLab PR or MR, or complete a local no-remote merge.

`.github/workflows/deploy.yml`'s `gates` job runs lint (`ruff`), format (`black`), import order (`isort`), strict typing (`mypy`), `manage.py check`, the migration guard (`makemigrations --check --dry-run`), and `pytest --cov` on every pull request to `master` and every push to it. The Railway deploy job runs only if `gates` passes.
