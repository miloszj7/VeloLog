<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Sentry Monitoring Implementation Plan

- **Plan**: context/changes/sentry-monitoring/plan.md
- **Scope**: Full plan (Phases 1–3, all complete)
- **Date**: 2026-09-07
- **Verdict**: REJECTED
- **Findings**: 1 critical, 1 warning, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | FAIL |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Sentry's default scrubber does not redact Django's registration/password-change field names

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (data safety)
- **Location**: `velo_log/settings.py:59-72` (Sentry init, `send_default_pii=False` with default `max_request_body_size="medium"`); `DEPLOY.md:339-342` (the claim); `accounts/forms.py:7` (`SignUpForm(UserCreationForm[User])`)
- **Detail**:
  The plan's "What We're NOT Doing" section explicitly accepted request-body capture on the strength of Sentry's server default scrubbing removing fields "named `password` (and `secret`, `token`, `api_key`)". `DEPLOY.md:339-342` repeats this as verified fact: "a denylist that includes `password`... redacted in-process."

  Verified against the installed `sentry-sdk` 2.68.1 source (`sentry_sdk/scrubber.py`): `EventScrubber.scrub_dict` matches by **exact, case-insensitive key equality** (`k.lower() in self.denylist`, line 117) against `DEFAULT_DENYLIST` (line 15), which contains the literal string `"password"` — not a substring/prefix match. Django's built-in `UserCreationForm` (which `accounts/forms.py`'s `SignUpForm` extends unmodified) names its fields `password1` and `password2`, not `password`. Neither matches the denylist. The same gap applies to Django's password-change form (`old_password`, `new_password1`, `new_password2`).

  Net effect: an unhandled exception during registration or password change ships the **plaintext submitted password(s)** to Sentry in the request body, unscrubbed — the exact outcome the plan's own risk analysis said was mitigated. Only the login form (`AuthenticationForm`, field literally `password`) is actually covered by the default denylist. This has been live in production since deploy #1 of Phase 3.

- **Fix A ⭐ Recommended**: Pass an explicit `event_scrubber` to `sentry_sdk.init()` extending the default denylist with the real field names:
  ```python
  from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
  ...
  event_scrubber=EventScrubber(
      denylist=DEFAULT_DENYLIST + ["password1", "password2", "old_password", "new_password1", "new_password2"]
  ),
  ```
  - Strength: Closes the exact gap found, keeps request-body capture (still useful for debugging other form fields), matches the plan's own stated intent (scrub by name, not disable entirely).
  - Tradeoff: A hardcoded field-name list is coupled to Django's internal form field naming; if a future custom form uses a different password field name, it needs adding here too.
  - Confidence: HIGH — verified directly against installed SDK source and the actual form field names in this codebase.
  - Blind spot: Haven't grepped for every current/future form with a credential-shaped field name outside `accounts/`.

- **Fix B**: Set `max_request_body_size="never"` (the escape hatch the plan itself already named).
  - Strength: Simpler, one kwarg, no per-field-name coupling; eliminates the whole class of body-capture risk permanently.
  - Tradeoff: Loses all request-body context for every future exception, not just credential-related ones — reduces debuggability the plan valued enough to explicitly keep body capture on.
  - Confidence: HIGH — trivially correct, documented SDK behavior.
  - Blind spot: None significant.

- **Decision**: FIXED (via Fix A) — `velo_log/settings.py` now passes an explicit `EventScrubber` extending `DEFAULT_DENYLIST` with `password1`, `password2`, `old_password`, `new_password1`, `new_password2`. `DEPLOY.md`'s "What reaches Sentry" section corrected to describe the exact-match gap and the applied mitigation. All quality gates (`black`, `isort`, `ruff`, `mypy --strict`, `manage.py check`) re-verified passing.

### F2 — "Set Sentry release" CI step has no failure isolation from the app deploy

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (reliability)
- **Location**: `.github/workflows/deploy.yml:105-116`
- **Detail**:
  The new step calls `railway variables --set ... --skip-deploys` with no `continue-on-error` and no fallback. A transient failure (Railway API hiccup, network blip) fails the whole `deploy` job, so the actual app deploy (`Deploy to Railway`, the next step) never runs — a real, user-facing deploy is blocked purely because a monitoring-metadata write failed. The app would deploy fine without a release tag; only Sentry's release attribution on the next event would be missing.
- **Fix**: Add `continue-on-error: true` to the step, so a failure there degrades gracefully (deploy proceeds, that one deploy's events are just untagged) instead of blocking the app deploy.
  - Strength: The rest of the deploy pipeline is unaffected by a monitoring side-channel failure; matches the "optional, gated" spirit of the whole Sentry integration (inert-by-default philosophy) applied to the CI side too.
  - Tradeoff: A silently-swallowed failure here means release tags could go missing without anyone noticing, unless the step's output is otherwise surfaced (e.g., in Actions summary).
  - Confidence: MED — this is a deliberate fail-fast-vs-fail-soft tradeoff the plan didn't explicitly address, so it may have been an intentional (if unstated) choice by the implementer to keep it fail-fast.
  - Blind spot: Haven't confirmed how often this step has actually failed in practice (no evidence of flakiness yet, this is a preventive finding).
- **Decision**: FIXED — `.github/workflows/deploy.yml`'s "Set Sentry release" step now has `continue-on-error: true`, with an inline comment explaining why.

## Success Criteria Verification

**Automated** (re-run 2026-09-07):
- `uv run python manage.py check` → pass
- `uv run mypy --strict .` → pass (89 source files, no issues)
- `uv run black --check .` → pass
- `uv run isort --check .` → pass
- `uv run ruff check .` → pass
- CI-equivalence (`SECRET_KEY=... DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`, `SENTRY_DSN` unset) → pass, 403 passed / 2 skipped / 6 deselected, 96.55% coverage

**Manual** (per plan's `## Progress`, all checked with commit references — ed5a052, 4ddfb05, 5577d7e, a3d9f28, 246a464): all Phase 1–3 manual criteria marked complete, including the Phase 3 blocking gate (temporary debug route confirmed removed, 404 confirmed, `DEPLOY.md` known-good-deployments table updated with deployment UUID + commit SHA).

## Plan Adherence Detail (via sub-agent, all files verified against current repo state)

All 6 planned artifacts (dependency, settings.py init block, deploy.yml CI step, `.env.example`, `DEPLOY.md`, temporary-then-removed debug view) MATCH the plan exactly — no drift, no missing items, no unplanned extras. The temporary `/__sentry-debug__/` route is confirmed absent from the current codebase (correct final state per Phase 3's gate).
