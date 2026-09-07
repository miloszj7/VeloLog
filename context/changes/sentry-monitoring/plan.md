# Sentry Monitoring Implementation Plan

## Overview

Add Sentry error and light performance monitoring to VeloLog's Railway deploy. The integration is entirely optional at the settings layer — gated on a `SENTRY_DSN` env var — so local dev and CI (which never set it) are unaffected, and production picks it up purely through Railway env vars.

## Current State Analysis

`velo_log/settings.py` already follows a consistent env-gated pattern: `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` via `django-environ`, a `MEDIA_ROOT`/`DB_PATH` pattern for path-like optional vars (`env_or`), and a production-only hardening block at the bottom guarded by `if not DEBUG:`. There is no existing external monitoring — only the custom `LOGGING` dict (root + `velo_log` logger, `velo_log_console` handler) and the `/healthz/` probe in `velo_log/urls.py`. There is no git metadata in the running container: `.github/workflows/deploy.yml:96-107` deploys by `railway up --ci` under a `RAILWAY_TOKEN` — a CLI tarball upload, not Railway's git-repo build trigger — and `DEPLOY.md:15` records that `railway up` does not read `.railway/railway.ts`. The service's declared env map (`.railway/railway.ts:11`) carries seven variables, none of them `RAILWAY_*` git metadata, and `RAILWAY_GIT_COMMIT_SHA` appears nowhere in the repo. The release tag must therefore be supplied explicitly by the workflow, which already knows the SHA as `${{ github.sha }}`.

## Desired End State

`SENTRY_DSN` set in the Railway environment causes every unhandled exception and every `ERROR`-level log call in production to reach Sentry as an event, tagged with the deployed commit SHA and an `environment` value, with 10% of requests also carrying a performance trace. `WARNING` records attach as breadcrumbs to whatever event follows them, and produce nothing on their own — that is `LoggingIntegration`'s default `event_level=ERROR`, and it is the right threshold here: 15 of the app's 16 `logger.*` call sites are already `ERROR`-level. Local dev and CI, which never set `SENTRY_DSN`, see no behavior change and no network calls. The integration has been proven end-to-end against the real Sentry project before this plan is considered done.

### Key Discoveries:

- `velo_log/settings.py:26-36` (`env_or`) is the established pattern for an optional, blank-tolerant env var — the same shape `SENTRY_DSN`/`SENTRY_ENVIRONMENT` should follow, though a plain `env(..., default="")` suffices since Sentry's own `dsn=""` behaves as disabled with no extra handling needed.
- `velo_log/settings.py:291-300` — the existing `if not DEBUG:` block is the natural sibling location for the Sentry gate, though Sentry's own gate is on `SENTRY_DSN` presence, not `DEBUG`, so it should be its own `if` rather than nested inside that block (a developer could plausibly set `SENTRY_DSN` locally to test against a personal Sentry project with `DEBUG=True`). That local workflow has one sharp edge worth documenting rather than designing around: `tests/test_settings_security.py:25-30` re-executes `settings.py` via `spec_from_file_location`, and `tests/test_settings_env.py:61,103` plus `tests/test_suite_bites.py` spawn subprocesses that inherit `os.environ` and call `django.setup()` — so with `SENTRY_DSN` exported, a suite run fires `sentry_sdk.init()` repeatedly and ships test noise to that project. CI is unaffected (it never sets the var); the `.env.example` text in Phase 2 carries the warning.
- `velo_log/urls.py` has no existing pattern for a debug-only route; the verification view is added directly to `urlpatterns` and removed once verified, not left behind a feature flag — it is a one-time proof, not a permanent capability.
- `pyproject.toml:9-15` — dependencies are unpinned-minimum (`>=`), matching `sentry-sdk` addition via `uv add sentry-sdk`.
- `DEPLOY.md:3-15`'s "Known-good deployments" table is keyed by **Railway deployment UUID**, not by commit — a commit SHA appears only in Notes prose, on two of six rows. So a Sentry release tagged with a SHA does not join to that table on any shared key today. Rather than change the table's key, step 3.6 records both values in the new row, which makes the join possible at the one place an operator actually needs it: "this Sentry release corresponds to this known-good deploy."

## What We're NOT Doing

- No custom Sentry alerting rules, issue-ownership routing, or Slack/email integration configuration — that's done in the Sentry dashboard, not in code.
- No `sentry_sdk` usage beyond `django.integrations.django` + `logging` (e.g. no custom `before_send` scrubbing, no manual `capture_exception` call sites) — default behavior is sufficient for a first integration. This is a decision about request data, not an omission, so it is recorded rather than left implicit: `send_default_pii=False` suppresses cookies and user identity, but it is **not** what governs request bodies — those are captured on the `max_request_body_size` budget, which defaults to `"medium"`. `accounts/` POSTs credentials on login and registration, so those form bodies are in scope. The accepted mitigation is Sentry's **server-side** default scrubbing, which removes fields named `password` (and `secret`, `token`, `api_key`) before storage; raw bodies and uploaded files (the GPX multipart path) are documented as never sent. If that mitigation is judged insufficient once real events are visible, the escape hatch is one kwarg — `max_request_body_size="never"` — and still needs no `before_send`.

  **Verify during Phase 1, don't assume**: confirm against the installed SDK that form-body capture is gated by `max_request_body_size` rather than by `send_default_pii`. The two are documented separately per-platform, and this plan's reading was not checked against Python's source. If it turns out `send_default_pii=False` already suppresses bodies, this whole note collapses to "no action needed" — which is worth knowing either way.
- No changes to the existing `LOGGING` dict's handlers/formatters — Sentry's `LoggingIntegration` observes existing `logging` calls without altering how they're formatted or where else they're routed.
- No staging/preview Railway environment — `SENTRY_ENVIRONMENT` is wired to be configurable, but only `production` will actually be set, since no second environment exists yet.

## Implementation Approach

Single settings.py block, gated on `SENTRY_DSN`, added as a sibling to the existing production-hardening block. One dependency addition via `uv add`. Docs handed to the user for `.env.example` (per this repo's rule that agents cannot write that file) and folded into `DEPLOY.md` directly. A temporary debug view proves the wiring against the real Sentry project, then is removed in the same phase so it never ships as a lasting attack surface.

## Phase 1: Add dependency and wire Sentry into settings

### Overview

Install `sentry-sdk`, initialize it in `velo_log/settings.py` gated on `SENTRY_DSN`.

### Changes Required:

#### 1. Dependency

**File**: `pyproject.toml` / `uv.lock`

**Intent**: Add the Sentry Python SDK as a runtime dependency.

**Contract**: Run `uv add sentry-sdk`, which appends an entry to `dependencies` in `pyproject.toml` and updates `uv.lock`. No manual edit — let `uv` write both files.

#### 2. Sentry init block

**File**: `velo_log/settings.py`

**Intent**: Initialize Sentry only when `SENTRY_DSN` is configured, wiring Django's own integration plus a logging integration so existing `ERROR`-level calls surface as Sentry events without new call sites. `LoggingIntegration` is what earns its place here, not merely a nicety: 13 of the app's 16 `logger.*` sites are `logger.exception` calls that **log and continue** rather than raise — `gpx/signals.py:76` (a stranded file after a failed storage delete), `gpx/views.py:172` (a track file missing from storage), `gpx/statistics.py:137`, and the five healthz probes at `velo_log/urls.py:81,114,117,145,152`. `DjangoIntegration` alone sees only exceptions that propagate out of a view, so it would miss every one of them.

The single `WARNING` in the codebase (`gpx/management/commands/reconcile_media.py:121`, refusing to walk a media directory that leaves `MEDIA_ROOT`) stays a breadcrumb rather than an event. Accepted: that command is run interactively behind the `DEPLOY.md:60` SSH alias, where the operator reads it on stdout.

**Contract**: two separate edits, because ruff's `E402` (active — `pyproject.toml:42` selects `E` with no `ignore`) rejects a module-level import placed after executable code, and the repo has no precedent for suppressing it (zero `noqa: E402` anywhere in the tree).

First, add the three imports to the **existing top-of-file import block** (`velo_log/settings.py:13-17`), where isort places them as third-party alongside `environ`:

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
```

Then add the init itself after the `env_or` helper's definition (i.e. after line 36) and before `SECRET_KEY = env("SECRET_KEY")` — after `env_or`, not merely after `read_env`, because the block calls it:

```python
SENTRY_DSN = env("SENTRY_DSN", default="")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), LoggingIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=env_or("SENTRY_ENVIRONMENT", "production"),
        release=env_or("SENTRY_RELEASE", "") or None,
    )
```

`release` reads `SENTRY_RELEASE`, set by the deploy workflow (§3 below) rather than
inherited from the platform — see Current State Analysis: this deploy path carries no
git metadata. Both optional vars go through `env_or` (`velo_log/settings.py:26`), not
`env(..., default=...)`, because a key that is *present but blank* yields `""` rather
than the default — the exact failure `env_or` exists for and that
`tests/test_settings_env.py` pins. A blank `SENTRY_RELEASE` must reach `sentry_sdk` as
`None` (no release), not as `""`, hence the trailing `or None`.

Placement before `SECRET_KEY`/`DEBUG` is deliberate: Sentry's own SDK init should be live as early as possible so that any error later in settings module load (unlikely, but this is the standard placement Sentry's own Django docs recommend) is itself capturable. `LoggingIntegration()` with no args uses Sentry's own defaults (`level=INFO` → breadcrumb, `event_level=ERROR` → event) without needing to duplicate this project's own `LOG_CONTEXT_KEYS`/formatter logic — Sentry's logging integration reads the stdlib `logging` record directly, independent of this project's custom formatter. Note that the `level=INFO` breadcrumb threshold is moot in production: `velo_log/settings.py:292-302` sets both the root and `velo_log` loggers to `WARNING` when `DEBUG=False`, so an `INFO` record is dropped before Sentry ever sees it. Breadcrumbs will in practice contain `WARNING`+ only.

#### 3. Supply the release SHA from the deploy workflow

**File**: `.github/workflows/deploy.yml`

**Intent**: Give the deployed container a `SENTRY_RELEASE` value, since the platform supplies no git metadata on this deploy path (see Current State Analysis).

**Contract**: In the `deploy` job, add a step before `Deploy to Railway` that sets the variable on the Railway service without triggering its own redeploy, so the `railway up` that follows is the deploy which picks it up:

```yaml
      - name: Set Sentry release
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: >-
          railway variables
          --service=fa5fd9c7-8cd0-47de-bf1b-3515e1f62583
          --project=d0f372e3-e9a6-4a70-bf9a-73d85cdda226
          --environment=production
          --set "SENTRY_RELEASE=${{ github.sha }}"
          --skip-deploys
```

Two things to confirm during implementation rather than assume:

- **`--skip-deploys` exists on `railway variables` in CLI v5.43.1** (the pinned version at `deploy.yml:97`). Check `railway variables --help` first. If the flag is absent, the fallback is to accept the extra redeploy it triggers — `railway up` immediately after supersedes it — or to drop the variable approach and have the workflow write the SHA to a file that `railway up` uploads.
- **`MSYS_NO_PATHCONV` does not apply here**: this step runs on `ubuntu-latest`, not Git Bash, and a bare SHA is not path-shaped. The `DEPLOY.md:30-43` trap is a local-CLI concern only.

The variable is set by CI on every deploy and is never set by hand, locally or in the Railway dashboard.

### Success Criteria:

#### Automated Verification:

- `uv run python manage.py check` passes with the new settings block
- `uv run mypy --strict .` passes (sentry-sdk ships inline type hints; no stub package needed)
- Full quality gate suite passes: `uv run black --check .`, `uv run isort --check .`, `uv run ruff check .`, `uv run pytest --cov`
- `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` passes with `SENTRY_DSN` unset (proves the gate is inert in CI)

#### Manual Verification:

- `uv run python manage.py runserver` boots cleanly with no `SENTRY_DSN` set locally
- Confirm no Sentry SDK log output appears when `SENTRY_DSN` is unset

---

## Phase 2: Document environment variables

### Overview

Surface the two new env vars in `.env.example` (handed to the user per this repo's rule) and `DEPLOY.md`, and set the real values in Railway.

### Changes Required:

#### 1. `.env.example`

**Intent**: Document `SENTRY_DSN` and `SENTRY_ENVIRONMENT` alongside the existing optional-var comments, following the file's established comment-then-value style.

**Contract**: Hand the user this exact text to append (not written by the agent — see repo rule):

```
# Sentry DSN for error/performance monitoring. Optional — when unset or blank, Sentry
# is never initialized and no network calls are made (see velo_log/settings.py). Only
# set in the Railway environment; never set locally or in CI.
#
# If you do set it locally to test against a personal Sentry project, unset it again
# before running the test suite. Several tests re-import settings in-process or in a
# subprocess that inherits your environment (tests/test_settings_security.py,
# tests/test_settings_env.py, tests/test_suite_bites.py), so a suite run would fire
# sentry_sdk.init() repeatedly and ship test noise to that project.
#SENTRY_DSN=

# Environment tag attached to every Sentry event. Defaults to "production" if unset or
# left blank. Only meaningful once SENTRY_DSN is also set.
#SENTRY_ENVIRONMENT=

# Release tag attached to every Sentry event — the deploying commit SHA. Set by
# .github/workflows/deploy.yml on every deploy; never set by hand, here or in Railway.
#SENTRY_RELEASE=
```

#### 2. `DEPLOY.md`

**File**: `DEPLOY.md`

**Intent**: Add a section documenting the Railway variables to set for Sentry and how to verify the integration is live, following the existing style of other env var sections (e.g. the `MEDIA_ROOT` section's `MSYS_NO_PATHCONV` warning, verify-after-setting convention).

**Contract**: New `## Sentry error monitoring` section covering: the two Railway variables to set (`SENTRY_DSN`, `SENTRY_ENVIRONMENT=production`), the `MSYS_NO_PATHCONV` consideration (a DSN URL contains no path Windows/MSYS would rewrite, so state explicitly that the trap does not apply here — avoids the reader wondering), and a pointer to Phase 3's verification method.

### Success Criteria:

#### Automated Verification:

- N/A (documentation only)

#### Manual Verification:

- User confirms `.env.example` was updated with the exact text above
- `railway variables --kv | grep '^SENTRY_'` shows both variables set in the Railway environment
- `DEPLOY.md` renders correctly (no broken markdown)

---

## Phase 3: Production verification via temporary debug endpoint

### Overview

Prove the Sentry init actually reaches the real Sentry project from the deployed app, then remove the proof.

**This phase costs two merges and two production deploys.** `.github/workflows/deploy.yml:91` deploys on every push to `master`, so the add-verify-remove cycle cannot happen in one shot. The sequence is:

1. Branch, add the route, PR, `--no-ff` merge to `master` → **deploy #1** puts the probe live.
2. Verify (steps 3.3–3.4 below).
3. Branch, remove the route, PR, `--no-ff` merge → **deploy #2** takes it back down.
4. Confirm the 404 (step 3.5).

Between deploys #1 and #2, `master` and production carry an unauthenticated endpoint that raises. The exposure is mild in itself — a generic Django 500 under `DEBUG=False`, no data disclosure, no amplification — so the risk being managed here is not the endpoint, it is **forgetting step 3**. Accordingly:

> **Blocking exit condition**: this change is not complete, and must not be archived, while `/__sentry-debug__/` resolves in production. Step 3.5 is a gate, not a checklist row. If verification fails at step 3.4 and the cause needs investigation, remove the route first (deploy #2) and re-add it later — do not leave the probe live while debugging.

Open the second PR immediately after deploy #1 succeeds, before starting verification, so the removal is already in flight rather than depending on remembering it afterwards.

### Changes Required:

#### 1. Temporary debug view

**File**: `velo_log/urls.py`

**Intent**: A throwaway unauthenticated view that raises an exception, added solely to exercise the production WSGI → Sentry path once. Not a permanent capability — removed in this same phase after use.

**Contract**: A `path("__sentry-debug__/", ...)` entry added to `urlpatterns` (`velo_log/urls.py:203`), backed by a module-level view function that does `raise RuntimeError("Sentry verification probe — VeloLog sentry-monitoring change")`. No `name=` since nothing reverses it and it will be deleted shortly.

Annotate the view — `def sentry_debug(request: HttpRequest) -> HttpResponse:` — or `mypy --strict` rejects it; both names are already imported at `velo_log/urls.py:29`.

No existing test breaks: `tests/test_ownership_matrix.py` collects a route only when it is named *and* its pattern matches `PK_CONVERTER_RE` (`:65`, `:297-302`), so an unnamed pk-free route never enters `exposed` and neither the `unclassified` nor the `stale` assertion (`:323-339`) moves. `tests/test_smoke.py:5` asserts only `ROOT_URLCONF`. Do not add a test for this route — it is deleted two commits later, and `tests/test_assertion_strength.py`'s request-cycle rule would want a real assertion on a throwaway.

### Success Criteria:

#### Automated Verification:

- `uv run python manage.py check` passes with the temporary route present

#### Manual Verification:

- Deploy to Railway with `SENTRY_DSN` and `SENTRY_ENVIRONMENT` set
- `curl -s https://velolog-production.up.railway.app/__sentry-debug__/` returns a 500
- The corresponding event appears in the Sentry dashboard, tagged with the deploying commit's SHA as its release (the value CI put in `SENTRY_RELEASE`) and `production` as its environment
- Remove the temporary view and route, redeploy, and confirm `curl` against the same path now 404s
- `DEPLOY.md`'s "Known-good deployments" table gets a new row for this deploy, per existing convention — with the Railway deployment UUID in its keyed column **and** the commit SHA named in Notes, so the row joins to the Sentry release tag

---

## Testing Strategy

### Unit Tests:

- No new unit test required: the Sentry init is a one-line conditional gated on an env var absent in every test run (`SENTRY_DSN` is never set in `.env.example`, CI, or `tests/conftest.py`), so `sentry_sdk.init` never executes under test — there is no new branch of application logic to unit-test.
- The existing CI-equivalence command (`SECRET_KEY=... DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`) already proves the gate is inert without `SENTRY_DSN`, which is the only behavior this change adds that's within the test suite's reach.

### Integration Tests:

- None — the only way to prove the Sentry integration itself works is a real event reaching a real Sentry project, which Phase 3's manual production verification covers. A mocked/faked Sentry call would only prove the SDK API was called correctly, not that events actually arrive — not worth the added test surface for a one-time settings wire-up.

### Manual Testing Steps:

1. Confirm local `runserver` boots with no `SENTRY_DSN` in `.env` (Phase 1).
2. Confirm CI passes with `SENTRY_DSN` unset (Phase 1, already covered by existing CI-equivalence command).
3. Set Railway variables, deploy, hit the temporary debug endpoint, confirm the event in Sentry, remove the endpoint, redeploy, confirm 404 (Phase 3).

## Performance Considerations

`traces_sample_rate=0.1` samples 10% of requests for full performance tracing. Given VeloLog's traffic (personal, low-volume — see `DEPLOY.md`'s Volume capacity note), this is negligible overhead; there is no load-testing need for this change.

## Migration Notes

Not applicable — no data model or storage changes.

## References

- `velo_log/settings.py:22-48` — existing env-gated settings pattern this change follows
- `velo_log/urls.py` — existing view/route conventions (`healthz`) referenced for the temporary debug view's placement
- `DEPLOY.md` — existing Railway env var documentation conventions

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Add dependency and wire Sentry into settings

#### Automated

- [x] 1.1 `uv run python manage.py check` passes with the new settings block — ed5a052
- [x] 1.2 `uv run mypy --strict .` passes — ed5a052
- [x] 1.3 Full quality gate suite passes (`black`, `isort`, `ruff`, `pytest --cov`) — ed5a052
- [x] 1.4 CI-equivalence command passes with `SENTRY_DSN` unset — ed5a052
- [x] 1.7 `deploy.yml` sets `SENTRY_RELEASE` from `github.sha`; `--skip-deploys` confirmed against CLI v5.43.1 — ed5a052
- [x] 1.8 Request-body capture gating confirmed against the installed SDK (`max_request_body_size` vs `send_default_pii`) — ed5a052

#### Manual

- [x] 1.5 `runserver` boots cleanly with no `SENTRY_DSN` set locally — ed5a052
- [x] 1.6 No Sentry SDK log output when `SENTRY_DSN` is unset — ed5a052

### Phase 2: Document environment variables

#### Manual

- [x] 2.1 User confirms `.env.example` updated with the exact text provided
- [x] 2.2 `railway variables --kv | grep '^SENTRY_'` shows both variables set
- [x] 2.3 `DEPLOY.md` renders correctly

### Phase 3: Production verification via temporary debug endpoint

#### Automated

- [ ] 3.1 `uv run python manage.py check` passes with the temporary route present

#### Manual

- [ ] 3.2 Deploy to Railway with `SENTRY_DSN`/`SENTRY_ENVIRONMENT` set
- [ ] 3.3 `curl` against `/__sentry-debug__/` returns 500
- [ ] 3.4 Event appears in Sentry dashboard tagged with the deploying commit SHA as release and `production` as environment
- [ ] 3.5 **GATE** — temporary view removed, deploy #2 landed, `curl` now 404s (change cannot close while this is unchecked)
- [ ] 3.6 `DEPLOY.md` known-good-deployments table updated (deployment UUID + commit SHA in Notes)
