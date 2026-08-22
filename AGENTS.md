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

No linting tools are configured yet. Before writing business logic, wire `ruff`, `black`, and `mypy` into `pyproject.toml` per the global standard.

## Testing

No test infrastructure exists yet. When adding tests: use `pytest` + `pytest-django`, place tests in `tests/` at the repo root, and configure via `[tool.pytest.ini_options]` in `pyproject.toml`. See `@~/.claude/CLAUDE.md` for fixture patterns, coverage thresholds (`fail_under = 80`), and integration-test skip conventions.

## Commits & Git Workflow

Follow `@~/.claude/rules/git-workflow.md`: Conventional Commits format, feature branches
only (never commit straight to `master`), merge with `--no-ff`, never squash. Use the
`create-pr` skill to open a GitHub/GitLab PR or MR, or complete a local no-remote merge.
