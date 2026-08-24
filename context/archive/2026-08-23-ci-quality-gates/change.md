---
change_id: ci-quality-gates
title: Run tests and lint/type gates in CI on pull requests, gating the Railway deploy
status: archived
created: 2026-08-23
updated: 2026-08-24
archived_at: 2026-08-24T09:15:12Z
---

## Notes

Run `pytest` with coverage plus `ruff`/`black`/`isort`/`mypy --strict` on `pull_request`
and gate the Railway deploy on them.

Engineering Backlog item from `context/foundation/roadmap.md` — trigger: **before S-03**
(`upload-gpx-and-view-map`), because the north star slice adds file upload and map
rendering, where a silent regression is most costly.

- **Today:** `.github/workflows/deploy.yml` runs only on `push: master` and only does
  `manage.py check` + `makemigrations --check --dry-run` before `railway up`. No tests,
  no lint, no type check, and nothing runs on a PR.
- **Deliberately separate from S-03:** enabling the gates for the first time may surface
  pre-existing lint/type debt, and quality-gate fixes must not be mixed into a feature
  diff (global standard). The gate also only pays for itself if it is green *before*
  the feature branch lands.
- **Main unknown for planning:** making `pytest --cov` (with `fail_under = 80`) pass in
  a CI environment with no `.env` and no dev database.
