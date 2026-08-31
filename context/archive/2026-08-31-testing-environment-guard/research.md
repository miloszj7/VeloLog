---
date: 2026-08-31T10:00:26+02:00
researcher: Claude
git_commit: a947127c525c5a1be97bcd51e444dc9d67a0ec3b
branch: master
repository: VeloLog
topic: "Rollout Phase 4 — Environment guard (Risk #7: a deployment stores uploads somewhere the next redeploy erases)"
tags: [research, codebase, healthz, media-root, settings-env, test-plan-phase-4]
status: complete
last_updated: 2026-08-31
last_updated_by: Claude
---

# Research: Rollout Phase 4 — Environment guard (Risk #7)

**Date**: 2026-08-31T10:00:26+02:00
**Researcher**: Claude
**Git Commit**: a947127c525c5a1be97bcd51e444dc9d67a0ec3b
**Branch**: master
**Repository**: VeloLog

## Research Question

Ground rollout Phase 4 of `context/foundation/test-plan.md`: "Environment guard" —
prove a media-root misconfiguration is refused rather than silently accepted.
Risk #7: a deployment stores uploads somewhere the next redeploy erases (High
impact, Low likelihood). Ground the guard's actual trigger conditions, what the
suite must prove with no environment file present, verify or correct the
Risk Response Guidance (`test-plan.md` §2), locate existing tests, identify the
cheapest useful test layer, and flag speculative risk or misleading hot-spot
evidence.

## Summary

**The guard, and the tests the response guidance called for, already exist.**
[`velo_log/urls.py`](https://github.com/miloszj7/VeloLog/blob/a947127c525c5a1be97bcd51e444dc9d67a0ec3b/velo_log/urls.py#L97-L123)
implements `media_root_misconfiguration()`, which the `/healthz/` view consults
before every media round-trip probe. `tests/test_media_storage.py` already
carries 12 tests exercising exactly the two guard conditions (`not_absolute`,
`inside_base_dir`), the `DEBUG`-gating of both the check and the disclosure of
the raw path, caching behavior, and cleanup-failure resilience. There is no
`test_healthz.py` — everything lives inside `test_media_storage.py` alongside
the storage round-trip tests, because the guard and the round-trip probe share
one view and one cached verdict.

This is a genuine finding for the plan step, not a research failure: **the
"unit on settings resolution, integration on the probe" layer named in §2 Risk
Response Guidance is already fully built.** What is *not* covered — and is the
one concrete, evidence-backed gap this research found — is the **composition**
of the two facts that actually produced the 2026-08-26 production incident:
(1) `env_or()` resolves a blank/absent `MEDIA_ROOT` to `BASE_DIR / "media"`
(tested in isolation, via subprocess, in `test_settings_env.py`), and (2) that
value trips `inside_base_dir` under `DEBUG=False` (tested in isolation, with
`settings.MEDIA_ROOT` hand-set to an arbitrary in-`BASE_DIR` path, in
`test_media_storage.py`). No test proves the two compose — that a process
booted with the **exact** CI-equivalence env (`AGENTS.md`'s
`SECRET_KEY=... DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`, i.e. *no*
`.env`, *no* explicit `MEDIA_ROOT`) and no fixture override actually reproduces
the historical failure end-to-end when `/healthz/` is hit. That composition is
exactly what the autouse `_media_root_in_tmp_path` fixture prevents from ever
happening in-process for the rest of the suite — which is correct isolation for
every *other* test, but means the guard's real trigger path currently has no
regression net of its own outside that fixture's blind spot.

The restore-drill defects behind roadmap E-05 (nested media-restore upload,
DB restore refused without `--overwrite`) are operational CLI/runbook failures,
not application code — correctly out of pytest's reach, as §2 already says.

## Detailed Findings

### The guard: `media_root_misconfiguration()`

[`velo_log/urls.py:97-123`](https://github.com/miloszj7/VeloLog/blob/a947127c525c5a1be97bcd51e444dc9d67a0ec3b/velo_log/urls.py#L97-L123):

```python
def media_root_misconfiguration() -> str | None:
    ...
    if settings.DEBUG:
        return None
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.is_absolute():
        logger.error("healthz: MEDIA_ROOT is not an absolute path", extra=_media_root_context())
        return "not_absolute"
    if media_root.resolve().is_relative_to(Path(settings.BASE_DIR).resolve()):
        logger.error(
            "healthz: MEDIA_ROOT resolves inside BASE_DIR — uploads would land on ephemeral "
            "container disk instead of the mounted volume",
            extra=_media_root_context(),
        )
        return "inside_base_dir"
    return None
```

Docstring at `velo_log/urls.py:104-108` states the design rationale explicitly:
writability alone proves nothing, because an unset `MEDIA_ROOT` falls back
inside the container where a write still succeeds.

The check is **entirely skipped under `DEBUG=True`** — local dev never trips it.
It is invoked from `healthz()` at
[`velo_log/urls.py:161-166`](https://github.com/miloszj7/VeloLog/blob/a947127c525c5a1be97bcd51e444dc9d67a0ec3b/velo_log/urls.py#L161-L166),
which short-circuits the media round-trip write/read/delete probe
(`_media_round_trips()`, `velo_log/urls.py:126-152`) when the location check
already failed:

```python
misconfigured = media_root_misconfiguration()
return _HealthVerdict(
    database_ok=_database_round_trips(),
    media_ok=misconfigured is None and _media_round_trips(),
    media_misconfiguration=misconfigured,
)
```

### The response contract

`healthz()`, [`velo_log/urls.py:169-200`](https://github.com/miloszj7/VeloLog/blob/a947127c525c5a1be97bcd51e444dc9d67a0ec3b/velo_log/urls.py#L169-L200):

- Success (`database_ok and media_ok`): `200`, `{"status": "ok", "database": "ok", "media": "ok"}`.
- Failure: `500`, `{"status": "error", "database": ..., "media": ...}` plus
  `"media_error": "not_absolute" | "inside_base_dir"` when the location check
  is the cause.
- `payload["media_root"]` (the raw path) is added **only under `DEBUG=True`** —
  the comment at line 195-196 calls this "an unauthenticated disclosure of the
  server's filesystem layout" in production, deliberately kept out of the
  response body and left to the log instead.
- The verdict is cached 30s under `HEALTHZ_CACHE_KEY = "healthz:verdict"`
  (`velo_log/urls.py:53-54, 177-182`) — repeated hits inside that window return
  the stale verdict, not a fresh probe.

### `MEDIA_ROOT` resolution

[`velo_log/settings.py:170`](https://github.com/miloszj7/VeloLog/blob/a947127c525c5a1be97bcd51e444dc9d67a0ec3b/velo_log/settings.py#L170):
`MEDIA_ROOT = env_or("MEDIA_ROOT", str(BASE_DIR / "media"))`.

`env_or()` (`velo_log/settings.py:26-36`) treats a present-but-blank env var the
same as an absent one, specifically so `FileSystemStorage` never resolves an
empty string to `os.path.abspath("")` (the process CWD) instead of the intended
default.

Env loading is `django-environ`: `environ.Env.read_env(BASE_DIR / ".env")`
(`velo_log/settings.py:22-23`) is a silent no-op when `.env` is absent — with no
`.env`, everything falls to real environment variables or, for `MEDIA_ROOT`, to
`BASE_DIR / "media"`.

Composing these two facts is exactly the shape of the 2026-08-26 production
incident: no `.env` on a fresh Railway deploy → `MEDIA_ROOT` falls back to
`BASE_DIR / "media"` → `DEBUG=False` in production → `/healthz/` returns 500
`inside_base_dir`.

### Existing tests

All in `tests/test_media_storage.py` (no separate `test_healthz.py`):

- `test_healthz_reports_both_round_trips_ok` (:115) — happy path, 200.
- `test_healthz_fails_when_media_root_is_inside_base_dir_and_debug_is_false` (:126) —
  `DEBUG=False`, `MEDIA_ROOT` hand-set to a `BASE_DIR`-relative path never
  created beforehand → 500, `media_error == "inside_base_dir"`, path absent from
  both the body and the raw response content, and the misconfigured directory
  is never created (proves the check short-circuits before any write).
- `test_media_root_location_check_is_skipped_under_debug` (:162) — calls
  `media_root_misconfiguration()` directly under `DEBUG=True` → `None`.
- `test_media_root_must_be_absolute_in_production` (:174) — `DEBUG=False`,
  relative `MEDIA_ROOT` → non-`None` reason containing `"absolute"`.
- `test_healthz_blames_media_alone_when_the_store_is_unreachable` (:185) /
  `test_healthz_blames_the_database_alone_when_it_is_unreachable` (:200) —
  storage/DB failure isolation via `monkeypatch`.
- `test_healthz_reads_back_and_deletes_the_name_save_returned` (:219),
  `test_healthz_survives_a_cleanup_that_cannot_delete` (:244),
  `test_repeated_probes_leave_no_files_behind` (:256) — probe hygiene under
  concurrency/cleanup failure.
- `test_healthz_serves_a_cached_verdict_instead_of_reprobing` (:279) — proves
  the 30s cache, not something else, produces a stale-green result.
- `test_healthz_reports_the_media_root_only_under_debug` (:298) — disclosure
  gating.

`tests/test_settings_env.py` tests `env_or()` resolution directly
(`monkeypatch.setenv`/`delenv`, :23-41) and, separately, spawns a real
**subprocess** (:44-81) with `MEDIA_ROOT=""`, `DB_PATH=""` to prove the
blank-`.env` fallback resolves to the `BASE_DIR`-relative defaults — it does
**not** hit `/healthz/` in that subprocess, so the fallback and the guard are
proven independently, never together end-to-end.

`tests/conftest.py`'s autouse `_media_root_in_tmp_path` fixture (:38-46) points
`MEDIA_ROOT` at `tmp_path` for every test in the suite — correct isolation for
everything else, but it also means no in-process test can currently observe the
real `env_or()` fallback landing inside `BASE_DIR`; only a subprocess (as
`test_settings_env.py` already does elsewhere) can bypass that fixture.

### Test conventions to follow

- Plain pytest-django functions, not `TestCase`/`self.client.get`. Fixtures:
  `client: Client`, `settings: Settings`, `db: None`, `monkeypatch: pytest.MonkeyPatch`.
- Settings mutated as plain attribute assignment on the `settings` fixture
  (`settings.DEBUG = False`, `settings.MEDIA_ROOT = ...`) — `@override_settings`
  is not used anywhere in this codebase.
- URLs resolved via `reverse("healthz")`, never a hardcoded path.
- `cache.clear()` called explicitly whenever a prior request in the same test
  may have cached the healthz verdict (the autouse `_clear_cache` fixture only
  guarantees isolation *between* tests, not mid-test).
- Responses asserted via `response.json()`.
- The subprocess pattern in `test_settings_env.py:44-81` is this repo's
  precedent for testing "no `.env` present" behavior that the autouse fixtures
  would otherwise mask — the same pattern is what a composition test for this
  guard would need, extended to also `GET /healthz/` inside that subprocess.

### Historical/documentary context

`DEPLOY.md` §"MEDIA_ROOT — required, and easy to set wrongly from Git Bash"
(:15-48): the 2026-08-26 incident narrative — `/healthz/` caught the
misconfiguration in production ("`{"media": "error", "media_error":
"inside_base_dir"}` and a 500") within minutes of the first deploy shipping the
upload feature, before any file was actually lost; `railway.json` sets no
`healthcheckPath` so the deploy itself still reported success. Also documents
the `MSYS_NO_PATHCONV` Git Bash trap that mangles `MEDIA_ROOT` into a
Windows-style path, which would trip `not_absolute` rather than
`inside_base_dir` — same guard, different branch, already covered generically
by `test_media_root_must_be_absolute_in_production`.

Restore drill (`DEPLOY.md:138-164`, roadmap E-05,
[`roadmap.md:208-214`](https://github.com/miloszj7/VeloLog/blob/a947127c525c5a1be97bcd51e444dc9d67a0ec3b/context/foundation/roadmap.md#L208-L214)):
three runbook defects, all in the `railway files upload`/`files download`
restore procedure — refused without `--overwrite`, and a media restore that
reports success while nesting the backup and recovering nothing. These are CLI
runbook failures with no application code to test; §2's note that "the
platform itself is not testable from pytest, but the *guard* ... is" holds up.

PRD Guardrail ("Data never lost"),
[`prd.md:41-43`](https://github.com/miloszj7/VeloLog/blob/a947127c525c5a1be97bcd51e444dc9d67a0ec3b/context/foundation/prd.md#L41-L43):
"Every uploaded GPX file is durably stored and always retrievable. Data loss is
catastrophic for a personal diary product."

## Code References

- `velo_log/urls.py:97-123` — `media_root_misconfiguration()`, the guard itself
- `velo_log/urls.py:126-152` — `_media_round_trips()`, gated by the guard
- `velo_log/urls.py:161-166` — `_HealthVerdict` assembly, short-circuit logic
- `velo_log/urls.py:169-200` — `healthz()` view, response contract, caching, disclosure gating
- `velo_log/settings.py:26-36` — `env_or()`
- `velo_log/settings.py:170` — `MEDIA_ROOT` resolution
- `velo_log/settings.py:22-23` — `django-environ` `.env` loading, no-op when absent
- `tests/test_media_storage.py:92-315` — 12 existing tests covering the guard, probe, caching, disclosure
- `tests/test_settings_env.py:23-81` — `env_or()` unit tests + subprocess blank-`.env` fallback test
- `tests/conftest.py:38-46` — `_media_root_in_tmp_path` autouse fixture (the isolation that also masks the real fallback in-process)
- `tests/conftest.py:77-85` — `_clear_cache` autouse fixture
- `DEPLOY.md:15-48` — MEDIA_ROOT section, 2026-08-26 incident narrative, MSYS_NO_PATHCONV trap
- `DEPLOY.md:138-164` — Restore drill, roadmap E-05 origin
- `AGENTS.md:51-55` — CI-equivalence command (no `.env`, `DEBUG=False`)

## Architecture Insights

- The guard and the round-trip probe deliberately share one view and one cached
  verdict rather than being split into a Django system check and a separate
  health endpoint — the docstring at `velo_log/urls.py:104-108` explains why a
  writability-only probe is insufficient on its own.
- `env_or()` is a small but load-bearing idiom used identically for both
  `MEDIA_ROOT` and `DB_PATH` (`velo_log/settings.py:102`) — blank-vs-absent
  normalization exists specifically to prevent `FileSystemStorage` resolving an
  empty string to the process CWD.
- This codebase's settings-mutation test convention (`settings` fixture
  attribute assignment, never `@override_settings`) is consistent everywhere it
  appears — a plan should follow it, not introduce `@override_settings`.
- Autouse fixtures in `conftest.py` establish suite-wide isolation (media root,
  cache, SSL redirect, staticfiles storage) that is correct for the rest of the
  suite but specifically prevents this one guard's real trigger conditions from
  ever occurring in-process — the subprocess escape hatch already exists as
  precedent in `test_settings_env.py`.

## Historical Context (from prior changes)

- `context/changes/deployment/deployment-plan.md` — original Railway deploy
  plan (Phase 4) that set up `MEDIA_ROOT`/Volume config, and later recorded the
  never-exercised restore procedure as a follow-up (the origin of roadmap E-05).
- `context/foundation/roadmap.md:208-214` — E-05 entry, closed 2026-08-26,
  restore drill findings.
- `context/foundation/test-plan.md:51,69` — Risk #7 and its Risk Response
  Guidance row, the direct input to this research.

## Related Research

None — this is the first research artifact for `testing-environment-guard`.

## Open Questions

1. **Should Phase 4 add a composition test, or is the existing coverage
   sufficient?** The two halves of the historical failure (`env_or()` fallback,
   `inside_base_dir` check) are each tested in isolation; nothing proves they
   still compose to reproduce the exact incident end-to-end. This is a small,
   cheap addition (one subprocess test, following `test_settings_env.py`'s
   existing pattern, extended to `GET /healthz/`) — recommend the plan step
   decide whether this justifies its own sub-phase or is out of proportion to
   Risk #7's Low likelihood rating.
2. Given how much of §2's Risk Response Guidance for #7 is already satisfied,
   `/10x-plan` should size Phase 4 down accordingly rather than planning a full
   unit+integration buildout from scratch — the remaining work is verification
   plus, at most, the one composition test above.
