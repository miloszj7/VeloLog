---
bootstrapped_at: 2026-05-30T19:52:00Z
starter_id: django
starter_name: Django
project_name: velo-log
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: verified
phase_3_status: ok
audit_command: "pip-audit --format json"
---

## Hand-off

```yaml
starter_id: django
package_manager: uv
project_name: velo-log
hints:
  language_family: python
  team_size: solo
  deployment_target: fly
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: verified
  path_taken: standard
  quality_override: false
  self_check_answers: null
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: false
  has_background_jobs: false
```

### Why this stack

Solo Python developer shipping a multi-day cycling tour diary in 2 after-hours weeks. Django is the vetted default for `(web-app, python)` and clears three of four agent-friendly gates; its batteries-included design covers every must-have FR — auth, ORM with user-trip data isolation, file uploads for GPX tracks, and HTML templating for the map view — without assembling separate services. The user's existing Python familiarity eliminates language ramp, keeping the full learning budget on AI-agent-assisted development. Django's ubiquity in AI training data and strong convention-over-configuration model make it the most agent-friendly full-stack Python choice for this scope. Fly.io is the deployment target for a public-facing course project; GitHub Actions auto-deploys on merge to main.

---

## Pre-scaffold verification

| Signal      | Value                                            | Severity | Notes                                             |
| ----------- | ------------------------------------------------ | -------- | ------------------------------------------------- |
| npm package | not run                                          | —        | python-family starter; npm check skipped          |
| GitHub repo | not run                                          | —        | docs_url (https://docs.djangoproject.com) is not a GitHub URL; no recency signal available |

---

## Scaffold log

**Resolved invocation**: `django-admin startproject velo_log .`  
**Strategy**: native-cwd (scaffolding directly into the current directory)  
**Exit code**: 0  
**Pre-flight files-to-touch**: `manage.py`, `velo_log/__init__.py`, `velo_log/asgi.py`, `velo_log/settings.py`, `velo_log/urls.py`, `velo_log/wsgi.py`  
**Files written by CLI**: 6  
**Pre-existing files preserved**: `CLAUDE.md`, `.gitignore`, `context/`, `.venv/`, `VeloLog-ideas.md`

Note: `{name}` substituted with Python-compatible module name `velo_log` (derived from `velo-log`); the template already carries `.` as the target directory, so the generic `{name}=.` rule for native-cwd was not applicable. Django was pre-installed via `uv pip install django` (adapted from the card's `pre: "pip install django"` using the resolved package manager).

---

## Post-scaffold audit

**Tool**: `pip-audit --format json`  
**Summary**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW  
**Direct vs transitive**: not distinguished by pip-audit  

Clean tree — no known vulnerabilities in any of the 4 direct packages (django 6.0.5, asgiref 3.11.1, sqlparse 0.5.5, tzdata 2026.2).

---

## Hints recorded but not acted on

| Hint                    | Value                  |
| ----------------------- | ---------------------- |
| bootstrapper_confidence | verified               |
| quality_override        | false                  |
| path_taken              | standard               |
| self_check_answers      | null                   |
| team_size               | solo                   |
| deployment_target       | fly                    |
| ci_provider             | github-actions         |
| ci_default_flow         | auto-deploy-on-merge   |
| has_auth                | true                   |
| has_payments            | false                  |
| has_realtime            | false                  |
| has_ai                  | false                  |
| has_background_jobs     | false                  |

None of these fields triggered automated action in v1. The `has_auth: true` flag and `deployment_target: fly` / `ci_provider: github-actions` hints are preserved here for the future M1L4 skill (Memory Architecture) to act on.

---

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- `git add .` and your first commit to start tracking the scaffold in your repo history.
- Run `uv pip install django` is already done; consider creating a `pyproject.toml` via `uv init --no-workspace` and pinning your dependencies there for reproducibility.
- Verify Django works: `python manage.py check` (activate `.venv` first).
- Address any audit findings per your project's risk tolerance — the full breakdown is in this log (0 findings, clean).
