# Repository Guidelines

VeloLog is a greenfield Django 6 web app — a trip-centric personal diary for multi-day cycling tours, aggregating GPX tracks and trip context into a single view. Stack: Python 3.14, Django 6.0.5, uv package manager, SQLite.

## Hard Rules

- **Never write to `context/archive/`** — content there is immutable; open a new change with `/10x-new` instead.
- **Use `uv add <pkg>` to install packages**, not `pip install`. Direct pip calls bypass the lockfile (`uv.lock`).
- The Django settings module is `velo_log.settings`. Do not create a parallel settings file without updating `manage.py` and `velo_log/wsgi.py`.
- **`MEDIA_ROOT` must be set in every deployed environment**, to the mounted volume (`/data/media` on Railway). Unset, it falls back to `BASE_DIR / "media"` inside the container and every uploaded file is lost on the next redeploy. `/healthz/` refuses to return 200 when it resolves inside `BASE_DIR` at `DEBUG=False` — that probe is the only thing that reports this. See `DEPLOY.md`, which also documents the Git Bash `MSYS_NO_PATHCONV` trap that silently mangles the value.

## Project Structure

- `velo_log/` — Django project package (settings, urls, wsgi, asgi). Not for application code.
- `manage.py` — Django CLI entry point; always invoke via `uv run python manage.py`.
- `pyproject.toml` — single source of truth for dependencies and tool config.
- `context/` — 10x PRD/shaping artifacts. See `@context/foundation/prd.md` for scope and `@context/foundation/tech-stack.md` for stack rationale.
- `templates/` — project-level shared templates (`base.html` and other cross-cutting chrome that doesn't belong to a single app). `TEMPLATES[0]["DIRS"]` points here; `APP_DIRS` stays `True` so app-namespaced templates still resolve.
- `static/` — project-level shared static assets. `STATICFILES_DIRS` points here, mirroring the `templates/` convention above exactly; app-owned assets live inside the app (e.g. `gpx/static/gpx/`), resolved by staticfiles' `AppDirectoriesFinder` — the exact analogue of `APP_DIRS` for templates.
- `accounts/` — registration, login/logout.
- `trips/` — the second feature app: create, list, edit and delete a user's trips.
- `gpx/` — the third: upload, parse, store and download a trip's GPX file, derive and store its statistics (distance, recorded time, elevation gain/loss), build the map config and stats blob its detail page renders, and **own the stored file's lifecycle**. Two receivers on `GpxTrack` in `gpx/signals.py` (registered by `gpx/apps.py` importing the module) are the only places a `.gpx` file is removed from storage, and they split the lifecycle between them: `post_delete` covers a file whose row is gone — trip cascade, admin `delete_selected`, an upload replacing its predecessor, and any bare `QuerySet.delete()`; `pre_save` covers a file superseded on a row that *survives*, which is what the admin change form does. Do not reintroduce inline storage deletes — registering the `post_delete` receiver is also what stops the collector fast-deleting `GpxTrack` rows, and without materialized rows a trip cascade has no instance to read a storage key from. The same listener check also disables the collector's field-deferral optimization, so a cascade now selects whole `GpxTrack` rows including the `points` blob — which is why both receivers schedule a callback closing over the pk and storage key rather than the instance; an instance closure would hold every one of those rows resident past commit. Both schedule with `transaction.on_commit`, so a test asserting a file was removed must wrap the request in `django_capture_on_commit_callbacks(execute=True)` or it passes while proving nothing. **What no signal covers**: `bulk_create`, `bulk_update` and `QuerySet.update(file=...)` bypass model signals by design, and process death between the storage write and the commit leaves a file no receiver ever fires for — `reconcile_media` is the backstop for all four, not a second receiver.
  - **Statistics** are captured inside the single `gpxpy` parse at upload and read back as plain columns, so rendering can never fail on a parse. `gpx/statistics.py` holds both ends: the backfill helper for rows that predate those columns, and the display builder the detail page reads. **That backfill helper cannot be deleted while `gpx/migrations/0003_backfill_gpxtrack_stats.py` exists** — the migration imports it inside its `RunPython` body, under a guard, so a rename degrades to one logged skip and leaves every pre-existing row's statistics null instead of breaking loudly. Two gpxpy calls answer `0` where a caller would read `None`, so presence gets its own probe in each case; a `0` stored there would render as "no climbing" rather than as "not recorded".

New Django apps belong at the **repo root** alongside `velo_log/` — as `accounts/`, `trips/` and `gpx/` all are — registered in `velo_log/settings.py` under `INSTALLED_APPS`.

## Development Commands

| Command | Purpose |
|---|---|
| `uv run python manage.py runserver` | Start dev server |
| `uv run python manage.py migrate` | Apply migrations |
| `uv run python manage.py makemigrations <app>` | Create migration for an app |
| `uv add <package>` | Add dependency (updates `pyproject.toml` + `uv.lock`) |
| `uv sync` | Sync venv to lockfile after pulling |
| `uv run python manage.py backfill_gpx_stats` | Refill `GpxTrack` statistics from the stored files, for rows where they are null (`--all` reprocesses every row). The documented recovery path when migration `0003` ran against a misconfigured `MEDIA_ROOT` and filled nothing — a migration cannot be re-applied once recorded. Per-row failures are a tally, not a crash |
| `uv run python manage.py reconcile_media` | Report files under `MEDIA_ROOT` that no `GpxTrack` row references. Report-only by default; `--delete` reclaims them and prunes the directories they emptied, behind an age threshold (`--min-age-minutes`) that keeps an in-flight upload from looking orphaned. Refuses `--delete` when *nothing* on the volume is referenced — the shape a point-in-time skew makes — unless `--allow-full-sweep`. The backstop for every path the two `gpx/signals.py` receivers cannot see; see `DEPLOY.md` before running it with `--delete` |
| `uv run python manage.py collectstatic --noinput` | Build `staticfiles/` and its hashed manifest. `railway.json` chains this ahead of gunicorn, so an unresolvable static reference is a failed boot rather than a broken site |

## Coding Style & Naming

Python 3.14 — modern type syntax (`X | Y`, `list[str]`, `dict[str, Any]`) is native; `from __future__ import annotations` is not required. Follow `@~/.claude/CLAUDE.md` for all other Python standards: naming, type hints, logging, error handling, Pydantic vs dataclass choice, and project layout within each app.

Linting is configured in `pyproject.toml`: `ruff`, `black`, `isort`, and `mypy --strict` (with `django-stubs`). Run via `/python-quality-gates` before reporting a task done.

## Testing

`pytest` + `pytest-django` are configured; tests live in `tests/` at the repo root. Coverage runs against `accounts`, `trips`, `gpx`, and `velo_log` with `fail_under = 80` (`[tool.coverage.run]` / `[tool.coverage.report]` in `pyproject.toml`). See `@~/.claude/CLAUDE.md` for fixture patterns and integration-test skip conventions.

The suite must pass with **no `.env` present** — CI never has one. Reproduce a CI failure locally with the CI-equivalence command, which overrides every `.env` variable except `DB_PATH` (deliberately unset — the test suite uses an in-memory SQLite database, so no DB file path is ever read):

```
SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov
```

## Commits & Git Workflow

Follow `@~/.claude/rules/git-workflow.md`: Conventional Commits format, feature branches
only (never commit straight to `master`), merge with `--no-ff`, never squash. Use the
`create-pr` skill to open a GitHub/GitLab PR or MR, or complete a local no-remote merge.

`.github/workflows/deploy.yml`'s `gates` job runs the vendored-asset integrity check (`sha256sum -c gpx/static/gpx/vendor/SHA256SUMS`), lint (`ruff`), format (`black`), import order (`isort`), strict typing (`mypy`), `manage.py check`, the migration guard (`makemigrations --check --dry-run`), `collectstatic --noinput`, and `pytest --cov` on every pull request to `master` and every push to it. That order is load-bearing: `tests/test_static_references.py` renders a page through the production manifest backend and skips itself when no manifest has been collected, so it only runs because `collectstatic` precedes the test step. The integrity check runs first, before `uv sync`, because it needs nothing from the venv and a tampered asset should fail in seconds. The Railway deploy job runs only if `gates` passes.
