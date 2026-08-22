---
starter_id: django
package_manager: uv
project_name: velo-log
version: 2
created: 2026-05-29
updated: 2026-08-22
hints:
  language_family: python
  team_size: solo
  deployment_target: railway
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
---

## Why this stack

Solo Python developer shipping a multi-day cycling tour diary in 2 after-hours weeks. Django is the vetted default for `(web-app, python)` and clears three of four agent-friendly gates; its batteries-included design covers every must-have FR — auth, ORM with user-trip data isolation, file uploads for GPX tracks, and HTML templating for the map view — without assembling separate services. The user's existing Python familiarity eliminates language ramp, keeping the full learning budget on AI-agent-assisted development. Django's ubiquity in AI training data and strong convention-over-configuration model make it the most agent-friendly full-stack Python choice for this scope. Railway is the deployment target for a public-facing course project; GitHub Actions auto-deploys on merge to master.

## Changelog

- **v1 (2026-05-29)** — Initial stack choice: Django on `uv`, `deployment_target: fly`.
- **v2 (2026-08-22)** — `deployment_target` changed `fly` → `railway`. The later platform research in `infrastructure.md` (2026-08-20) scored Railway ahead of Fly.io (5/5 Pass vs. 3 Pass/2 Partial on the agent-friendliness criteria) and it was the platform actually provisioned and deployed to — see `context/changes/deployment/deployment-plan.md` and `DEPLOY.md`. This doc had not been updated to match that decision; it's now consistent with the other foundation docs.
