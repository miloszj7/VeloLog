# Environment Guard — Plan Brief

> Full plan: `context/changes/testing-environment-guard/plan.md`
> Research: `context/changes/testing-environment-guard/research.md`

## What & Why

Rollout Phase 4 of `context/foundation/test-plan.md` targets Risk #7: a
deployment stores uploads somewhere the next redeploy erases (the
2026-08-26 production incident this project has already lived through).
Research found the guard and both named test layers already built and
thorough — this plan closes the one real gap, not a rebuild.

## Starting Point

`media_root_misconfiguration()` (`velo_log/urls.py:97-123`) already refuses
a `MEDIA_ROOT` that resolves inside `BASE_DIR` under `DEBUG=False`, surfaced
through `/healthz/`. 12 tests in `tests/test_media_storage.py` already prove
every branch of that guard and the probe around it. A subprocess test in
`tests/test_settings_env.py` already proves the blank-`.env` fallback
resolves to `BASE_DIR / "media"`. What's missing: nothing proves those two
facts *compose* — that a real process booted with no `.env` and `DEBUG=False`
actually trips the guard end-to-end.

## Desired End State

A new subprocess test reproduces the 2026-08-26 incident's exact trigger
shape and asserts the guard fires. `test-plan.md` §6.6 records the pattern
instead of reading `TBD`, and §6.7 carries a Phase 4 note for future readers.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Add new coverage vs. treat existing as sufficient | Add one composition test | The composition gap is real and cheap to close; existing coverage doesn't prove the two halves compose | Plan (user-confirmed) |
| Negative-only vs. also a positive-case composition test | Negative case only | The positive ("correctly configured") branch is already proven via hand-set settings; doubling up would be redundant | Plan (user-confirmed) |
| Manual staging smoke-check | Skipped | Already owned by `DEPLOY.md`'s known-good-deployment checklist; adding one here risks the "test the guard, not the platform" anti-pattern §2 names | Plan (user-confirmed) |
| MSYS_NO_PATHCONV-specific test | Not added | Trips the same `not_absolute` branch already covered generically; platform-specific test would test the hosting platform | Research |

## Scope

**In scope:**
- One new subprocess test in `tests/test_settings_env.py` proving the guard trips under real no-`.env`, `DEBUG=False` conditions.
- `test-plan.md` §6.6 cookbook entry and a §6.7 Phase 4 note.

**Out of scope:**
- Positive-case composition test, MSYS_NO_PATHCONV-specific test, manual staging verification, restore-drill CLI fixes (roadmap E-05 — not application code).

## Architecture / Approach

Extend the existing subprocess pattern already in `tests/test_settings_env.py`
(`django.setup()` in a fresh subprocess, foreign `cwd`, explicit env dict) with
one more test that, after `django.setup()`, imports and calls
`velo_log.urls.media_root_misconfiguration()` directly — no database, no live
server needed, since the guard reads only `settings.DEBUG`/`MEDIA_ROOT`/`BASE_DIR`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Composition regression test | New subprocess test proving the guard trips under real no-`.env` conditions | Low — extends an existing, working pattern |
| 2. Verify and document | Full suite green; `test-plan.md` §6.6/§6.7 filled in | Low — documentation only |

**Prerequisites:** None — no new fixtures, no schema or dependency changes.
**Estimated effort:** ~1 session, both phases.

## Open Risks & Assumptions

- Assumes `media_root_misconfiguration()` remains importable without triggering DB access at import time (verified in research — it doesn't).
- Assumes the CI-equivalence env shape in `AGENTS.md` (`SECRET_KEY=... DEBUG=False ALLOWED_HOSTS=`) stays the authoritative "no `.env`" reproduction — if that command's shape changes, this test's env dict should change with it.

## Success Criteria (Summary)

- A real subprocess booted with no `MEDIA_ROOT` and `DEBUG=False` produces `"inside_base_dir"` from the guard, proving the composition rather than each half in isolation.
- `uv run pytest --cov` and `/python-quality-gates` both pass.
- `test-plan.md` §6.6 no longer reads `TBD`.
