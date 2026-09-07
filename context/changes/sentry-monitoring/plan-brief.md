# Sentry Monitoring — Plan Brief

> Full plan: `context/changes/sentry-monitoring/plan.md`

## What & Why

Add Sentry error and performance monitoring to VeloLog's Railway deploy, so an unhandled exception in production is no longer silent — it lands in a Sentry dashboard, tagged by deployed commit, instead of only surfacing if a user reports it or someone happens to check `railway logs`.

## Starting Point

`velo_log/settings.py` has a custom `LOGGING` dict and `/healthz/` probe, but no external error-monitoring service. Settings already follow a consistent env-gated pattern (`SECRET_KEY`, `DEBUG`, `MEDIA_ROOT` via `django-environ`), which the Sentry init slots into directly.

## Desired End State

With `SENTRY_DSN` set in Railway, every unhandled exception and every `ERROR`-level log call in production reaches Sentry as an event, tagged with the deployed commit SHA and `production` as environment, with 10% of requests also traced for performance. `WARNING` records attach as breadcrumbs only. Local dev and CI, which never set `SENTRY_DSN`, see zero behavior change.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Tracing | Errors + light tracing (0.1 sample rate) | Some latency visibility without meaningful overhead for a low-traffic app | Plan |
| Release tagging | `SENTRY_RELEASE`, set from `github.sha` by the deploy workflow | This deploy path (`railway up --ci`) carries no git metadata, so the SHA must be supplied explicitly | Plan |
| Logging integration | Default `LoggingIntegration()` | 13 of 16 `logger.*` sites log-and-continue rather than raise, so `DjangoIntegration` alone would miss them | Plan |
| Verification method | Temporary debug endpoint, hit once, removed | Proves the real production WSGI → Sentry path end-to-end, not just that the SDK call compiles | Plan |
| Environment tag | `SENTRY_ENVIRONMENT` env var, defaults to "production" | Matches the `env_or` pattern already used throughout settings.py | Plan |

## Scope

**In scope:**
- `sentry-sdk` dependency, gated Sentry init in `velo_log/settings.py`
- `SENTRY_RELEASE` supplied from `github.sha` by `.github/workflows/deploy.yml`
- `.env.example` and `DEPLOY.md` documentation
- One-time production verification via a temporary debug route (two deploys)

**Out of scope:**
- Sentry dashboard alerting rules, issue routing, Slack/email integration config
- Custom `before_send` scrubbing or manual `capture_exception` call sites
- A staging/preview Railway environment

## Architecture / Approach

A single `if SENTRY_DSN:` block near the top of `velo_log/settings.py`, calling `sentry_sdk.init()` with `DjangoIntegration` + `LoggingIntegration`. No new app code, no new dependencies beyond the SDK itself. Verification adds a throwaway view/route that's added and removed within the same phase.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Add dependency + wire settings + release SHA | Sentry SDK installed and gated-initialized; `deploy.yml` supplies `SENTRY_RELEASE` | Inert without `SENTRY_DSN`, which CI never sets. `railway variables --skip-deploys` needs confirming against CLI v5.43.1 |
| 2. Document env vars | `.env.example` + `DEPLOY.md` updated, Railway vars set | `.env.example` requires user's own edit per repo rule |
| 3. Production verification | Real event confirmed in Sentry dashboard, debug route removed | Two merges and two deploys. The 500-raising unauthenticated route is live in production between them; its removal is a blocking gate, not a checklist row |

**Prerequisites:** A Sentry account/project and its DSN (user needs to create this — not something the agent can do).
**Estimated effort:** ~1 session, 3 short phases.

## Open Risks & Assumptions

- Assumes a Sentry account/project already exists or will be created by the user before Phase 3.
- The temporary debug endpoint in Phase 3 is a real (if brief) unauthenticated attack surface — must be removed and redeployed before considering the change done.

## Success Criteria (Summary)

- A real exception raised in production shows up in the Sentry dashboard with the correct release and environment tags.
- Local dev and CI show no behavior change with `SENTRY_DSN` unset.
- No temporary debug route survives past Phase 3.
