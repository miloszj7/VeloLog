---
date: 2026-08-31T12:55:57+02:00
researcher: Miłosz Jarzynka
git_commit: af9fa054d2d47bc75afa64ba828f127e7874b376
branch: master
repository: VeloLog
topic: "Phase 5 — Gate credibility: prove the suite goes red when the behavior a test names is broken"
tags: [research, codebase, testing, ci, mutation-testing, test-plan-phase-5]
status: complete
last_updated: 2026-08-31
last_updated_by: Miłosz Jarzynka
---

# Research: Gate credibility (test-plan.md Phase 5)

**Date**: 2026-08-31T12:55:57+02:00
**Researcher**: Miłosz Jarzynka
**Git Commit**: af9fa054d2d47bc75afa64ba828f127e7874b376
**Branch**: master
**Repository**: VeloLog

## Research Question

Phase 5 of `context/foundation/test-plan.md` (§3 row 5, Risk #4: "a regression reaches
production with every gate green"). Three things need grounding before a plan can be
written:

1. Which existing tests assert only a status code (or otherwise assert too little to
   prove the behavior their name claims)?
2. What would a cost-proportionate "suite credibility gate" look like for this solo
   repo — full mutation testing, a scoped variant, or something else entirely?
3. Is "prove the test bites before trusting it" (test-plan.md §6.2) an established
   practice here already, or aspirational — and is there any existing automation for
   it?

## Summary

**The brief's premise is mostly false, the same shape Phases 1, 3, and 4 already
found.** This suite is unusually disciplined about the exact anti-pattern Risk #4
names: of 268 test functions read in full across all 25 test files, only **two**
assert nothing beyond a status code. The suite already contains explicit docstring
commentary in several places calling out *why* a bare status assertion would be
insufficient, then adding the extra probe — i.e. one hardening pass against this
anti-pattern has already happened. The real gap is narrower: those two tests, plus the
complete absence of any *mechanism* (automated or otherwise) that would catch a *third*
one from creeping in later, or that would catch a genuinely broken assertion (one that
asserts something, but the wrong thing, or asserts against a mock instead of real
behavior).

**Full mutation testing is not viable here as a PR gate**, and possibly not viable at
all without a spike: this project pins `requires-python = ">=3.14"` with no 3.13
fallback interpreter available, and the only serious contender (`mutmut`) has an
unresolved, recently-reported Python 3.14 / Pony-ORM incompatibility in its cache
layer. Even setting that risk aside, a full mutation run (hundreds to low-thousands of
mutants for ~3,000 LOC, each requiring a full suite re-run) is not proportionate to a
repo whose entire `gates` CI job — lint, format, isort, mypy, Django checks,
collectstatic, and the 331-test suite itself — currently runs in an estimated ~6
minutes total (the workflow's own inline comment states this budget).

**The manual practice test-plan.md §6.2 describes is real, not aspirational** — it has
a documented track record across at least two prior phases, always paired with a
revert before commit — but it has never been captured as reusable automation. That
absence, not a coverage gap, is the actual shape of Risk #4 for this repo: nothing
currently *prevents* a future regression from landing in a test that looks like it
proves something but doesn't, because the "break it and check" step lives only in a
human's head during `/10x-implement`, not in CI.

## Detailed Findings

### 1. Status-only and weak-assertion tests

268 test functions were read in full across all 25 files in `tests/`,
`tests/accounts/`, `tests/trips/`, `tests/gpx/`. Two are status-only:

- **`tests/gpx/test_gpx_download.py:96-113`** —
  `test_a_row_whose_file_is_gone_returns_404_not_500`. Asserts only
  `response.status_code == 404` when the DB row survives but the file is missing from
  storage. Its sibling three tests above it,
  `test_another_users_track_returns_404_not_403`, probes the response body for leaked
  filename/track data in addition to the status — this test does not carry that same
  probe, so a view that returned a differently-wrong 404 (leaking data, or silently
  deleting the surviving row) would still pass.
- **`tests/gpx/test_gpx_upload.py:488-497`** —
  `test_the_upload_url_does_not_serve_a_page_of_its_own`. Asserts only
  `response.status_code == 405` for a GET on the upload endpoint. Unlike the analogous
  405 test in `tests/trips/test_trip_edit.py`
  (`test_head_and_options_are_served_like_the_page_they_describe`, which asserts
  `"PUT" not in options.headers["Allow"]`), it checks neither the `Allow` header nor
  that no `GpxTrack` row was created.

Everything else — including the two large "contract" modules,
`tests/test_ownership_matrix.py` (966 lines, deliberately pairs every status assertion
with a body/DB/storage probe) and `tests/test_media_storage.py` — consistently pairs
status/redirect assertions with content, database, or storage-state checks. No test
function anywhere in the suite has zero assertions. No test relies solely on
assertions against a mock or patched object with no real-behavior check — several
tests use `monkeypatch` to simulate a broken dependency (`_BrokenStorage`, a storage
`.delete()` raising `PermissionError`, `get_modified_time` raising), but in every case
the actual `assert` runs against real HTTP responses, real filesystem/storage state,
or real captured logs, not against the mock.

Several tests carry explicit self-aware docstrings on exactly this point — e.g.
comments to the effect that "the 404/405 alone would pass against a view that mutated
state and refused afterward" — appearing in `test_trip_delete.py`, `test_trip_edit.py`,
and `test_gpx_upload.py`. This confirms the suite already had one deliberate hardening
pass against the Risk #4 anti-pattern; the two findings above are what that pass
missed, not evidence the pass never happened.

### 2. Mutation-testing tool landscape

- **mutmut** (current: 3.7.0, 2026-07-31) claims Python 3.10–3.14 support, and its own
  changelog records 3.4.0 adding "Support python 3.14." However, a separate, recent
  (Jan 2026) community-reported issue documents a real Python 3.14 incompatibility in
  mutmut's cache layer: `copy.deepcopy()` semantics changed in 3.14 and broke Pony
  ORM's query translator (used internally by mutmut for caching), with the reported
  workaround being to run under Python 3.13 instead. It is unverified whether later
  3.x releases actually fixed this or merely shipped classifier metadata claiming
  support. **This repo has no 3.13 interpreter available as a fallback**
  (`pyproject.toml: requires-python = ">=3.14"`) — so this must be spiked, not assumed,
  before mutmut is relied on for anything.
- **cosmic-ray** — actively maintained, pytest-compatible, but no confirmed 3.13/3.14
  compatibility statement found. Higher unknown-risk than mutmut.
- **mutpy** — mentioned as 3.14-compatible in the same issue thread, but far less
  maintained/mainstream; not a serious contender for a Django/pytest project.
- Neither tool has native pytest-django integration — both simply shell out to
  whatever test command is configured, so pytest-django is not the blocker; the
  mutation engine's own Python 3.14 compatibility is.
- **Cost, independent of the compatibility question**: mutation testing reruns the
  full suite once per generated mutant. For ~2,969 LOC across `accounts/`, `trips/`,
  `gpx/`, `velo_log/`, that's plausibly several hundred to low-thousands of mutants —
  not proportionate to run on every PR against a `gates` job whose own inline comment
  budgets the *entire* job (lint + format + isort + mypy + Django checks +
  collectstatic + pytest+coverage) at roughly six minutes.
- **Nothing currently in `pyproject.toml`'s dev dependencies** (`pytest`, `pytest-cov`,
  `pytest-django`) performs mutation testing or assertion-strength analysis. Branch
  coverage is already on (`tool.coverage.run: branch = true`) but says nothing about
  assertion strength — a branch can be "covered" by a test that only checks a status
  code, which is exactly the shape of the two findings in §1 above.

### 3. The manual "prove it bites" practice — real, with a track record, never automated

`test-plan.md:166` ("Prove the test bites before trusting it. Break the production
line it guards, confirm the cell goes red for the right reason, revert.") is not
aspirational. It has been exercised at least twice, always followed by a revert before
the commit that actually lands:

- `context/archive/2026-08-29-testing-data-isolation-contract/reviews/impl-review.md:50-64` —
  re-injected the exact `document_root`-based `re_path` mutation an earlier finding
  described; confirmed the relevant cells went red (previously green); reverted before
  commit. Repeated for a second finding at the same file, lines ~57-64, against three
  distinct mutation shapes.
- `context/archive/2026-08-29-testing-data-isolation-contract/plan.md:557` — a
  completed checklist item: "Temporary pk route makes the guard fail with an
  actionable message, then reverted — 50b6abf" (a real commit reference, not a
  proposal).
- `context/archive/2026-08-30-testing-rejection-and-degradation/plan.md:315` — "Confirm
  both new tests fail under a deliberately broken exception mapping, then revert —
  4e712b7."
- The rationale test-plan.md cites — `lessons.md` #1, #3, #4 — is present and on-point:
  #1 (`lessons.md:7-11`) is literally a test whose name claimed an assertion it never
  made, which let a real bug reach `master` with every gate green; #3 and #4
  (`lessons.md:19-28`) both record coverage percentage concealing an untested branch or
  an unmeasured package.

**No automation for this pattern exists anywhere in the repo.** No `mutmut`, no tox
environment, no `Makefile`, no `scripts/` directory, no custom `pyproject.toml`
command. The practice today is: a human, during `/10x-implement`, manually edits
production code to break it, runs the relevant test file, observes red, then runs
`git checkout`/reverts before the commit that ships. It is never captured in a form
that runs again later or that a future regression would be checked against.

### 4. CI budget grounding

`.github/workflows/deploy.yml` — single `gates` job (lines 15-72), 10 sequential
steps: checkout → two vendored-asset integrity checks (Leaflet, Bootstrap) → install
uv → `uv sync --locked` → ruff → black --check → isort --check-only → mypy →
`manage.py check` → migration guard → collectstatic → `pytest --cov`. An inline
comment at line 29 states the team's own intent and estimate: fail fast on asset
tampering "before six minutes of gates do" — i.e. the team already treats ~6 minutes
as the budget for the *entire* gate sequence, not just tests. `deploy` (lines 74-93)
runs only on push to `master` and only if `gates` passes.

`uv run pytest --collect-only -q tests/` collects **331 tests in 0.30s**, consistent
with test-plan.md §4's claim that the suite runs entirely in-memory. This is the
number a new gate's cost should be judged against: any addition that meaningfully
changes that ~6-minute total (e.g. hundreds of mutant re-runs) breaks the existing
cost model, not merely adds to it.

## Code References

- `tests/gpx/test_gpx_download.py:96-113` — status-only test, no leak/state probe
- `tests/gpx/test_gpx_upload.py:488-497` — status-only test, no `Allow` header or
  no-row-created probe
- `tests/test_ownership_matrix.py` — reference pattern: every status assertion paired
  with a body/DB/storage probe, 966 lines
- `.github/workflows/deploy.yml:15-72` — `gates` job, 10 steps, ~6-minute team-stated
  budget (comment at line 29)
- `pyproject.toml:6` — `requires-python = ">=3.14"`, no 3.13 fallback for a mutmut spike
- `pyproject.toml:61-71` — `[tool.coverage.run]`/`[tool.coverage.report]`, `branch =
  true`, `fail_under = 80` — the existing gate this phase must not merely duplicate

## Architecture Insights

- This repo already converged, independently, on the assertion pattern test-plan.md
  §6.2 recommends ("a status code plus a state or no-leak probe, always") — evidenced
  by docstrings in several tests explicitly naming the anti-pattern before guarding
  against it. Phase 5 doesn't need to *introduce* this discipline; it needs to
  **catch drift from it** and **catch the two places it already lapsed**.
- The `django_capture_on_commit_callbacks(execute=True)` idiom (Phase 2) and the
  storage-emptiness idiom `assert not (tmp_path / "media").exists()` (Phase 2→3) are
  both examples of a *pattern* generalizing across phases without new fixtures — the
  same is likely true here: a curated regression-proof fixture approach (§3 below)
  needs no new dependency and reuses the existing per-test `MEDIA_ROOT` and client
  fixtures already in `tests/conftest.py` / `tests/gpx/conftest.py`.
- The project's own layering philosophy (`CLAUDE.md`'s Lesson 3 material: per-edit →
  pre-commit → pre-push → CI, "keep per-edit hooks fast... move slow checks up a
  layer") directly answers the cost-proportionality question test-plan.md §4 poses:
  full mutation testing, if pursued at all, belongs at most as a scheduled/manual job,
  never as a per-PR `gates` step — it fails cost × signal (§1 principle #1) against a
  suite that already collects 331 tests in well under a second.

## Historical Context (from prior changes)

- `context/archive/2026-08-29-testing-data-isolation-contract/plan.md` and its
  `reviews/impl-review.md` — the only prior phase to actually execute the "prove it
  bites" practice with committed evidence (commit refs `50b6abf`, plus the impl-review
  re-injection). This is the closest existing analogue to what Phase 5 would formalize.
- `context/archive/2026-08-30-testing-rejection-and-degradation/plan.md:315` — second
  documented instance of the same manual practice (commit ref `4e712b7`).
- `context/foundation/lessons.md` #1, #3, #4 — the exact incidents Risk #4 exists to
  prevent from recurring; #1 in particular is structurally identical to the two
  findings in §1 above (a test that doesn't assert what it implies).
- Phases 1, 3, and 4 (`test-plan.md:206, 216-219, 222-223`) all record the same
  discovery shape this research reproduces: the brief's premise (a named gap) turns
  out narrower than assumed on inspection, and the real work is closing a small,
  specific residue rather than building the feature from scratch.

## Related Research

- `context/archive/2026-08-30-testing-file-lifecycle-storage-consistency/` (Phase 2) —
  established the post-commit-callback and storage-emptiness assertion idioms this
  phase's fixture approach would reuse.
- `context/archive/2026-08-31-testing-environment-guard/` (Phase 4) — most recent
  prior phase; same "brief's premise already false, gap was narrow and compositional"
  shape.

## Open Questions

- Should the two status-only tests found in §1 be fixed as part of this phase (a
  one-line addition each, consistent with the suite's own established pattern), or
  does that belong to a separate, smaller change since Phase 5's stated scope is the
  *gate*, not individual test fixes? Test-plan.md's Risk Response Guidance for #4
  frames the goal as "the suite goes red when the behavior a test names breaks" — the
  gate itself (§2/§3 below) would need at least one deliberately-broken scenario per
  risk area to prove itself, and these two tests are natural candidates for that
  proof.
- Is a mutmut spike (Python 3.14, scoped to a handful of risk-area files, per the
  external agent's recommendation) worth the investigation cost for this phase, given
  it would land as an optional/manual supplement at best — or should the plan treat
  full/scoped mutation testing as explicitly out of scope and rely entirely on curated
  regression-proof fixtures, revisiting mutation testing only if a 3.13-compatible
  interpreter becomes available or mutmut's 3.14 story is confirmed fixed?
  Test-plan.md §4 already frames mutation testing as "candidate... weighed against"
  the AI-native option — this research adds a third, cheaper option (curated
  fixtures) that wasn't named in the original framing and should be weighed
  alongside the other two during planning.
- What is the minimal set of regression-proof fixtures needed to cover Risk #4
  credibly without ballooning into "a mutation test suite hand-written one mutant at a
  time"? This is a planning-stage design decision, not something research can answer
  directly — but the existing manual precedent (§3) gives at least two ready-made
  mutation shapes (the `re_path`/`document_root` leak, the broken exception mapping)
  that already have a known-red/known-green history to build from.
