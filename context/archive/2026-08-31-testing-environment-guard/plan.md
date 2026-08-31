# Environment Guard — Implementation Plan

## Overview

Rollout Phase 4 of `context/foundation/test-plan.md` targets Risk #7: a
deployment stores uploads somewhere the next redeploy erases. Research
(`research.md`) found the guard itself — `media_root_misconfiguration()` in
`velo_log/urls.py` — and both test layers named in §2's Risk Response Guidance
("unit on settings resolution, integration on the probe") already exist and
are already thorough: 12 tests in `tests/test_media_storage.py` plus
settings-resolution tests in `tests/test_settings_env.py`. This plan closes
the one gap research identified rather than rebuilding coverage that already
exists.

## Current State Analysis

- `media_root_misconfiguration()` (`velo_log/urls.py:97-123`) checks, under
  `DEBUG=False` only, that `MEDIA_ROOT` is absolute and does not resolve
  inside `BASE_DIR`. `healthz()` (`velo_log/urls.py:169-200`) surfaces the
  result as `media_error` in a 500 response, disclosing the raw path only
  under `DEBUG=True`.
- `tests/test_media_storage.py` already proves both failure codes
  (`not_absolute`, `inside_base_dir`), the `DEBUG`-skip, caching, cleanup
  resilience, and disclosure-gating — every case, with `settings.MEDIA_ROOT`
  and `settings.DEBUG` hand-set directly on the `settings` fixture.
- `tests/test_settings_env.py::test_blank_keys_resolve_to_the_project_defaults`
  already proves, via a real subprocess, that a blank `MEDIA_ROOT` (the
  no-`.env` shape) resolves to `BASE_DIR / "media"` — but that subprocess
  only reads back `settings.MEDIA_ROOT` and `DATABASES["default"]["NAME"]`;
  it never calls the guard.
- The autouse fixture `_media_root_in_tmp_path` (`tests/conftest.py:38-46`)
  redirects `MEDIA_ROOT` to `tmp_path` for every in-process test — correct
  isolation for the rest of the suite, but it also means no in-process test
  can currently observe the real `env_or()` fallback landing inside
  `BASE_DIR`. A subprocess is the only way around that fixture, and one
  already exists as a pattern to extend.

## Desired End State

A new test proves that, under the exact conditions that produced the
2026-08-26 production incident — a real process booted with `DEBUG=False`
and no `MEDIA_ROOT` set — `media_root_misconfiguration()` returns
`"inside_base_dir"`. `context/foundation/test-plan.md` §6.6 and §6.7 record
the pattern and what this phase found, so a future settings/environment guard
follows the same shape.

**Verification**: `uv run pytest tests/test_settings_env.py tests/test_media_storage.py -v`
passes with 14 tests (13 existing + 1 new), and §6.6 no longer reads `TBD`.

### Key Discoveries:

- `velo_log/urls.py:104-108` — the guard's own docstring: a writability-only
  check would pass on the misconfigured default, because the fallback
  directory is perfectly writable; only the location matters.
- `tests/test_settings_env.py:44-81` — the existing subprocess pattern
  (`django.setup()`, then read `django.conf.settings` in a foreign `cwd`) is
  exactly the mechanism needed to bypass `_media_root_in_tmp_path` and
  observe the real fallback.
- Calling `media_root_misconfiguration()` directly (rather than hitting
  `/healthz/` through a live server) needs no database and no WSGI process —
  the guard reads only `settings.DEBUG`, `settings.MEDIA_ROOT`, and
  `settings.BASE_DIR`.

## What We're NOT Doing

- Not adding a positive-case composition test (a correctly-configured env
  resolving to no misconfiguration) — the "working correctly" branch is
  already proven via hand-set settings in
  `test_media_root_location_check_is_skipped_under_debug` and its siblings;
  decided with the user to keep this phase to the negative case that
  reproduces the actual incident.
- Not adding a test for the `MSYS_NO_PATHCONV` Git-Bash path-mangling case
  specifically — it trips the same `not_absolute` branch already covered
  generically by `test_media_root_must_be_absolute_in_production`; a
  platform-specific test here would be testing the hosting platform, not the
  guard (§2's named anti-pattern for Risk #7).
- Not adding a manual verification step against staging/production —
  `DEPLOY.md`'s "Known-good deployments" checklist already owns that; this
  phase is regression coverage, not deploy verification.
- Not touching the restore-drill defects behind roadmap E-05 (nested media
  restore, DB restore refused without `--overwrite`) — those are CLI/runbook
  failures with no application code to test.

## Implementation Approach

Extend the existing subprocess pattern in `tests/test_settings_env.py` with
one new test that also imports and calls the guard, rather than building new
fixtures or a live-server integration test. This keeps the addition thin and
consistent with the file's existing convention (each test proves one fact via
a real subprocess), and avoids the anti-pattern warned against in §2: "asserting
current output" from within the same fixtures that mask the real fallback.

## Phase 1: Composition regression test

### Overview

Add one test proving the blank-`.env` fallback and the `inside_base_dir`
check compose to reproduce the 2026-08-26 incident.

### Changes Required:

#### 1. New subprocess test

**File**: `tests/test_settings_env.py`

**Intent**: Prove that a process booted under CI-equivalence conditions
(`DEBUG=False`, no `MEDIA_ROOT` set) trips the guard, not just that the two
underlying facts are each individually true.

**Contract**: New test function `test_blank_media_root_trips_the_guard_under_debug_false`,
placed after `test_blank_keys_resolve_to_the_project_defaults`. Mirrors that
test's subprocess shape (`sys.executable -c <code>`, `PYTHONPATH=BASE_DIR`,
`cwd=tmp_path`, `SECRET_KEY` set, `MEDIA_ROOT=""`) with two differences: the
subprocess env additionally sets `DEBUG=False`, and the subprocess code
calls `django.setup()` then imports and calls
`velo_log.urls.media_root_misconfiguration()`, printing its return value
instead of (or alongside) the settings readback. Assert the printed value
equals `"inside_base_dir"`.

Docstring should name what this closes: the composition gap between
`test_env_or_falls_back_when_the_key_is_present_but_blank` (this file) and
`test_healthz_fails_when_media_root_is_inside_base_dir_and_debug_is_false`
(`tests/test_media_storage.py`) — each proves one half; this proves they
compose.

### Success Criteria:

#### Automated Verification:

- [ ] New test passes: `uv run pytest tests/test_settings_env.py -v -k trips_the_guard`
- [ ] Full guard-relevant suite passes: `uv run pytest tests/test_settings_env.py tests/test_media_storage.py -v`
- [ ] Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- [ ] None required — this phase adds regression coverage only, no behavior change.

---

## Phase 2: Verify and document

### Overview

Confirm the full existing guard coverage plus the new test are green, and
record the pattern in `context/foundation/test-plan.md` so a future
settings/environment guard follows the same shape.

### Changes Required:

#### 1. Cookbook pattern

**File**: `context/foundation/test-plan.md`

**Intent**: Replace the §6.6 `TBD` placeholder with the real pattern this
phase established, and record what the phase found in §6.7 — that the guard
and its tests were already thorough, and the actual gap was a composition
test, not new coverage from scratch.

**Contract**: §6.6 body: Location (`tests/test_settings_env.py` for
composition/subprocess-level guard tests, `tests/test_media_storage.py` for
the guard's own unit tests and the probe's integration tests), Naming
(`test_<condition>_trips_the_guard_under_<debug-state>` for composition
tests), Reference test
(`test_blank_media_root_trips_the_guard_under_debug_false`, added this
phase), Run locally command. §6.7: add a `**Phase 4 — Environment guard.**`
entry following the existing per-phase note format (see Phase 1–3 entries
immediately above it), naming the "guard and tests already existed, only the
composition was untested" finding.

### Success Criteria:

#### Automated Verification:

- [ ] Full suite passes: `uv run pytest --cov`
- [ ] `/python-quality-gates` passes

#### Manual Verification:

- [ ] `context/foundation/test-plan.md` §6.6 no longer reads `TBD`, and §6.7 carries a Phase 4 entry consistent with the Phase 1–3 entries above it.

---

## Testing Strategy

### Unit Tests:

- The new subprocess test itself is the unit under test for this phase — it
  proves a fact about settings/guard composition, not application behavior.

### Integration Tests:

- None new — the existing `/healthz/` integration tests in
  `tests/test_media_storage.py` already cover the view-level contract.

### Manual Testing Steps:

- None — see Phase 1 and Phase 2 Manual Verification (both explicitly N/A).

## Performance Considerations

None — one subprocess test, same shape as an existing one; no runtime code
changes.

## Migration Notes

Not applicable — test-only change.

## References

- Research: `context/changes/testing-environment-guard/research.md`
- Existing subprocess pattern: `tests/test_settings_env.py:44-81`
- The guard under test: `velo_log/urls.py:97-123`
- Existing guard/probe tests: `tests/test_media_storage.py:92-315`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Composition regression test

#### Automated

- [x] 1.1 New test passes: `uv run pytest tests/test_settings_env.py -v -k trips_the_guard` — f932be2
- [x] 1.2 Full guard-relevant suite passes: `uv run pytest tests/test_settings_env.py tests/test_media_storage.py -v` — f932be2
- [x] 1.3 Quality gates pass: `/python-quality-gates` — f932be2

#### Manual

- [x] 1.4 None required — this phase adds regression coverage only, no behavior change. — f932be2

### Phase 2: Verify and document

#### Automated

- [x] 2.1 Full suite passes: `uv run pytest --cov` — 329 passed, 2 skipped, 97.21% coverage
- [x] 2.2 `/python-quality-gates` passes — black/isort/ruff/mypy strict/manage.py check/migration guard all clean

#### Manual

- [x] 2.3 `context/foundation/test-plan.md` §6.6 no longer reads `TBD`, and §6.7 carries a Phase 4 entry consistent with the Phase 1–3 entries above it.
