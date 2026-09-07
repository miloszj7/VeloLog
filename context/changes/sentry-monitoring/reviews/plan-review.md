<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Sentry Monitoring Implementation Plan

- **Plan**: `context/changes/sentry-monitoring/plan.md`
- **Mode**: Deep
- **Date**: 2026-09-07
- **Verdict**: REVISE → **SOUND after triage** (all 7 findings fixed)
- **Findings**: 2 critical, 3 warnings, 2 observations

## Verdicts

| Dimension | Verdict (at review) | After fixes |
|-----------|---------------------|-------------|
| End-State Alignment | FAIL | PASS |
| Lean Execution | PASS | PASS |
| Architectural Fitness | PASS | PASS |
| Blind Spots | WARNING | PASS |
| Plan Completeness | FAIL | PASS |

## Grounding

5/5 paths ✓ · 4/4 line-refs ✓ (`env_or` :26, `if not DEBUG:` :291-300, deps :9-15, `read_env` :23) · `.env.example` style ✓ · Progress↔Phase mechanical contract ✓ · brief↔plan ✗ (1 mismatch — F7)

Verification performed: ruff E402 reproduced empirically against the repo's own config; Sentry `LoggingIntegration` defaults confirmed against Sentry's Python docs; deploy path, log-level inventory, URLconf test collection, DEPLOY.md conventions and settings import-time chain verified against the codebase.

## Findings

### F1 — Release tagging rests on an env var this deploy path never provides

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: End-State Alignment
- **Location**: Current State Analysis (:9), Phase 1 contract (:72), Phase 3 criterion (:167)
- **Detail**: The plan claimed "Railway automatically exposes `RAILWAY_GIT_COMMIT_SHA` to the running container". This app deploys via `.github/workflows/deploy.yml:96-107` — `railway up --ci` under a `RAILWAY_TOKEN`, a CLI tarball upload, not Railway's git-repo build trigger. `DEPLOY.md:15` states outright that `railway up` does not read `.railway/railway.ts`, and DEPLOY.md:14 records the E-04 incident proving the dashboard is authoritative. `RAILWAY_GIT_COMMIT_SHA` has zero hits anywhere in the repo; the service's declared env map (`.railway/railway.ts:11`) carries seven variables and none is git metadata. Because `env(..., default=None)` fails silently, the miss would surface only at step 3.4 — the last manual check, after two production deploys. Secondary: a present-but-blank value yields `""`, the exact class of bug `env_or` (:26) and `tests/test_settings_env.py` exist to pin.
- **Fix A ⭐ Recommended**: Set `SENTRY_RELEASE` from `${{ github.sha }}` in `deploy.yml`; read `env_or("SENTRY_RELEASE", "") or None` in settings.
  - Strength: The SHA is already in scope in the workflow; removes the dependency on unverified platform behavior entirely, and is blank-tolerant like every other optional var here.
  - Tradeoff: Touches `deploy.yml`; adds a third env var to document.
  - Confidence: HIGH.
  - Blind spot: Whether `railway variables --set` mid-workflow forces an extra redeploy.
- **Fix B**: Verify Railway's actual behavior first, then keep `RAILWAY_GIT_COMMIT_SHA` if present.
  - Strength: No workflow change if Railway does inject it.
  - Tradeoff: Costs a deploy to find out, and lands on Fix A anyway if absent.
  - Confidence: MEDIUM — absence not proven, only unsupported.
  - Blind spot: Railway's git-metadata behavior for token-authenticated CLI deploys is undocumented here.
- **Decision**: FIXED via Fix A. Current State Analysis rewritten; init block now `env_or("SENTRY_RELEASE", "") or None`; new Phase 1 §3 adds the `railway variables --skip-deploys` step to `deploy.yml`; criterion 3.4 and Progress 3.4 corrected; Progress 1.7 added. Knock-on caught while applying: `env_or` is defined at `settings.py:26-36`, so the block's original "after line 23" placement would have raised `NameError` — placement moved to after line 36 (still before `SECRET_KEY`, preserving the init-early rationale).

### F2 — Phase 1's own code block fails Phase 1's own success criterion

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 §2 contract (:56-76) vs. Success Criterion 1.3 (:84)
- **Detail**: The contract placed three `sentry_sdk` imports after executable code. `pyproject.toml:42` selects `E` with no `ignore`, so E402 is live — reproduced against the repo's own config on a file replicating that exact layout: 3 × `E402 Module level import not at top of file`. Criterion 1.3 requires `ruff check .` to pass. The gate runs in three places (`deploy.yml:57`, lefthook pre-commit, the post-edit hook), and there is no precedent to lean on — zero `noqa: E402` and zero post-code module imports anywhere in the tree. `isort --check` and `black --check` are both clean, so ruff is the sole blocker.
- **Fix**: Split the contract — imports into the existing top-of-file block (`settings.py:13-17`, where isort places them as third-party alongside `environ`); only `SENTRY_DSN = …` and the `if SENTRY_DSN:` init at the later position. The placement rationale concerns the `init()` call, not the imports, so it survives.
- **Decision**: FIXED — folded into the F1 edit, which rewrote the contract as two separate edits.

### F3 — "WARNING+ reaches Sentry" is not what the chosen config delivers

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Desired End State (:13), Phase 1 Intent (:54), plan-brief (:15, :23)
- **Detail**: Desired End State promised "every unhandled exception and `WARNING`+ log call in production to reach Sentry". Bare `LoggingIntegration()` defaults to `event_level=logging.ERROR` (confirmed in Sentry's Python docs) — WARNING records become breadcrumbs, and a breadcrumb only ships attached to an event, so a WARNING with no accompanying error produces nothing at all. The plan's own line :76 states `event_level=ERROR`, so the document contradicted itself between its acceptance contract and its implementation note. Two factual errors underneath: `gpx/signals.py:76` is `logger.exception`, not a warning, and healthz failures are `.exception`/`.error` (`velo_log/urls.py:81,114,117,145,152`). Full app tally: 1 WARNING vs 15 ERROR-level; the sole WARNING (`gpx/management/commands/reconcile_media.py:121`) is in a management command, not a request path.
- **Fix A ⭐ Recommended**: Correct the end state to `ERROR`-level, note WARNING→breadcrumb, fix the call-site errors.
  - Strength: The default is right for this codebase — 15 of 16 sites are ERROR-level.
  - Tradeoff: `reconcile_media`'s traversal refusal stays out of Sentry; it runs interactively behind the `DEPLOY.md:60` SSH alias where an operator reads it on stdout.
  - Confidence: HIGH — call-site levels enumerated exhaustively across all four apps.
  - Blind spot: None significant.
- **Fix B**: Set `event_level=logging.WARNING` to keep the promise literally.
  - Strength: Delivers the stated end state; the one WARNING site is a genuine operational signal.
  - Tradeoff: Contradicts "no usage beyond defaults" (:26); Django's own WARNING loggers (DisallowedHost, `django.request` 404s) would start creating events.
  - Confidence: MEDIUM — cheap, but thin value for one CLI call site.
  - Blind spot: Framework-logger event volume unmeasured.
- **Decision**: FIXED via Fix A. Desired End State and Phase 1 Intent rewritten in `plan.md`; matching corrections in `plan-brief.md` (Desired End State + Key Decisions row). The rewritten Intent is a *stronger* justification for `LoggingIntegration` than the original: 13 of 16 sites are `logger.exception` calls that log-and-continue, which `DjangoIntegration` alone would miss entirely. Also noted that `level=INFO` for breadcrumbs is moot in production, since `settings.py:292-302` puts both root and `velo_log` at `WARNING` when `DEBUG=False`.

### F4 — "No before_send scrubbing" is decided without pricing what gets sent

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: What We're NOT Doing (:26), Phase 1 contract (:70)
- **Detail**: The plan ruled out `before_send` scrubbing on the grounds that "default behavior is sufficient", and set `send_default_pii=False`. That flag gates cookies and user identity — it is not what governs request bodies, which are captured on the `max_request_body_size` budget (default `"medium"`). `accounts/` POSTs credentials on login and registration, and this repo's security baseline is "never log passwords, tokens, or PII". Sentry's server-side default scrubbers do catch fields named `password`, so residual risk is modest — but that is a mitigation to lean on knowingly, and the plan stated no position at all.
- **Fix**: Record the decision and its basis in "What We're NOT Doing"; note `max_request_body_size="never"` as the one-kwarg escape hatch.
  - Strength: Turns an implicit exposure into a recorded, reversible decision.
  - Tradeoff: None — a documentation edit unless the kwarg is chosen.
  - Confidence: MEDIUM — the PII/body split is documented per-platform in Sentry's docs; Python's exact gating was not verified in an installed SDK, since `sentry-sdk` is not yet in the venv.
  - Blind spot: Whether Django multipart GPX uploads leak filenames into the event body (raw bodies and files are documented as never sent).
- **Decision**: FIXED. Decision recorded with its mitigation and escape hatch; Progress step 1.8 added to confirm the gating against the installed SDK during Phase 1 rather than trusting the review's reading of it.

### F5 — Phase 3 costs two merges and two production deploys; the plan prices neither

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 3 (:141-169)
- **Detail**: `deploy.yml` deploys on every push to `master`, so add-verify-remove is two branches, two PRs, two `--no-ff` merges and two production deploys — and between them `master` and production carry a deliberately-500-raising unauthenticated endpoint. The brief flagged the attack surface (:57) but no phase stated the sequence, and step 3.5 was an ordinary checklist row rather than a blocking exit condition. The exposure itself is mild (generic Django 500 under `DEBUG=False`, no disclosure); the real risk is the removal being forgotten. Confirmed non-issue: no existing test breaks — `tests/test_ownership_matrix.py` collects a route only when named *and* matching `PK_CONVERTER_RE` (:65, :297-302), so an unnamed pk-free route never enters `exposed`.
- **Fix A ⭐ Recommended**: Spell out the two-deploy sequence; make removal a blocking gate.
  - Strength: Preserves the reason the route exists — proving the real WSGI → Sentry path, the plan's stated rationale and a genuinely stronger proof than any alternative.
  - Tradeoff: Still two deploys and a window of exposure.
  - Confidence: HIGH — mechanics only; the approach is unchanged.
  - Blind spot: None significant.
- **Fix B**: Verify from inside the container via the `DEPLOY.md:60` SSH alias plus `capture_message()`.
  - Strength: Zero code, zero deploys, zero exposure; DEPLOY.md:249 already argues for this class of work from inside the container.
  - Tradeoff: Does not exercise `DjangoIntegration`'s middleware hook — the one thing that turns an unhandled view exception into an event.
  - Confidence: MEDIUM — proves less, which is the objection the plan itself raised against a mocked test (:182).
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A. Phase 3 Overview now states the four-step sequence explicitly, carries a blocking exit condition (the change cannot close or be archived while `/__sentry-debug__/` resolves), and advises opening the removal PR immediately after deploy #1 so it is in flight rather than remembered. Contract additions: the view needs a `HttpRequest`/`HttpResponse` annotation for `mypy --strict` (both already imported at `velo_log/urls.py:29`), the ownership-matrix non-issue is recorded, and no test should be written for a route deleted two commits later. Progress 3.5 marked **GATE**.

### F6 — The plan's endorsed local workflow collides with the test suite

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Key Discoveries (:18), Testing Strategy (:177)
- **Detail**: Key Discovery #2 justifies the `if SENTRY_DSN:` gate (rather than nesting in `if not DEBUG:`) on the grounds that a developer might set `SENTRY_DSN` locally with `DEBUG=True`. In that configuration the suite fires real `sentry_sdk.init()` calls repeatedly: `tests/test_settings_security.py:25-30` re-executes `settings.py` via `spec_from_file_location`, `tests/test_settings_env.py:61,103` spawn subprocesses inheriting `os.environ`, and `tests/test_suite_bites.py` adds five cold Django boots. Test-run noise would ship to the real project. CI is unaffected — it never sets the var — so Testing Strategy's inertness claim holds for CI but not for the local workflow the plan itself endorses.
- **Fix**: Note it in the `.env.example` comment text handed to the user in Phase 2.
- **Decision**: FIXED. Warning added to the Phase 2 `.env.example` text (naming the three test files) and to Key Discovery #2.

### F7 — Release↔deploy correlation doesn't join on a shared key

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Key Discoveries (:21), plan-brief Key Decisions (:22)
- **Detail**: Both documents claimed DEPLOY.md "already tracks every production deploy by commit ID", used as the rationale that SHA-based release tagging mirrors existing practice. The table's keyed column is `Deployment ID` — a Railway deployment UUID (`DEPLOY.md:7-8`, e.g. `f2197620-9267-4a92-b9e2-40abbf84b9fa` at :11). Commit SHAs appear only in Notes prose on two of six rows. So a Sentry event tagged with a SHA and a known-good row keyed by UUID share no join key. This was the only brief↔plan grounding mismatch found.
- **Fix**: Correct the rationale, and have step 3.6 record both the deployment UUID and the SHA so the two systems actually join.
- **Decision**: FIXED. Key Discovery corrected in `plan.md`; Key Decisions row rewritten in `plan-brief.md` (now describing `SENTRY_RELEASE` from `github.sha`, per F1); criterion 3.6 and Progress 3.6 now require both values in the new row.

## Notes on what passed

Two dimensions passed cleanly and are worth not re-litigating:

- **Lean Execution** — scope is tight and the "What We're NOT Doing" list is honored by every phase.
- **Architectural Fitness** — the `if SENTRY_DSN:` gate as a sibling to `if not DEBUG:` is the correct read of the existing env-gated settings pattern; no new patterns are introduced. `LoggingIntegration` earns its place rather than being redundant with `DjangoIntegration`: 13 of 16 `logger.*` sites log-and-continue rather than raise, so `DjangoIntegration` alone would see none of them.

Also confirmed clean at review time: the `## Progress` section satisfies the mechanical contract in `.claude/skills/10x-plan/references/progress-format.md` (one heading at the bottom, phase headings matched, indices unique, no checkboxes outside Progress). Steps 1.7 and 1.8 were appended during triage per the "new steps get the next available index" rule.
