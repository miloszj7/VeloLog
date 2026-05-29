---
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
---

## Why this stack

Solo Python developer shipping a multi-day cycling tour diary in 2 after-hours weeks. Django is the vetted default for `(web-app, python)` and clears three of four agent-friendly gates; its batteries-included design covers every must-have FR — auth, ORM with user-trip data isolation, file uploads for GPX tracks, and HTML templating for the map view — without assembling separate services. The user's existing Python familiarity eliminates language ramp, keeping the full learning budget on AI-agent-assisted development. Django's ubiquity in AI training data and strong convention-over-configuration model make it the most agent-friendly full-stack Python choice for this scope. Fly.io is the deployment target for a public-facing course project; GitHub Actions auto-deploys on merge to main.
