<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Gate Credibility Implementation Plan

- **Plan**: `context/changes/testing-gate-credibility/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-31
- **Verdict**: REVISE
- **Findings**: 1 critical, 5 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | FAIL |

## Grounding

11/11 paths ✓, 5/5 mutation patch targets ✓, 5/5 guard test nodes ✓, brief↔plan ✓
(both carry the same false premise — see F1).

Verified in this pass:

- All five patch targets resolve, and the plan's "patch the imported name" analysis is
  correct: `trips/views.py:17` does `from gpx.availability import track_file_is_available`,
  `gpx/forms.py:9` imports `MAX_GPX_FILE_BYTES` by value from `gpx.constants`,
  `gpx/signals.py:111-113,182` build `partial(discard_file_by_key, …)` inside the receiver
  body so the name is a module-global lookup at signal-fire time, and
  `velo_log/urls.py:161` calls `media_root_misconfiguration()` as a module global.
- `tests/` is a real package (`tests/__init__.py`, `tests/gpx/__init__.py`,
  `tests/trips/__init__.py`) with 15 existing cross-imports, so
  `from tests.mutations import …` works from both `tests/conftest.py` and
  `tests/test_suite_bites.py`. No `pythonpath` setting needed.
- The Phase 2 precedent is exactly as described: `tests/test_coverage_scope.py` uses
  `REPO_ROOT` resolution, a non-empty-population guard at `:47`, and actionable failure
  messages.
- The audit's claimed edge cases all exist: `_issue` helper at
  `tests/test_ownership_matrix.py:489-499`; eight `route.probe(target, response)` delegated
  probes; exactly 12 zero-assert `pytest.raises` tests in `tests/gpx/test_gpx_parsing.py`.
- `TripCreateView` does declare `http_method_names = ["get", "post", "head", "options"]`
  (`trips/views.py:64`), so the plan's claimed `Allow` verb set is correct.
- `addopts` blast radius is genuinely narrow: no `lefthook.yml`, no
  `.pre-commit-config.yaml`, no `.husky/`, no `hooks` key in either `.claude/settings*.json`,
  and README.md/DEPLOY.md contain no pytest references.

## Findings

### F1 — The plan's headline evidence is false

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Plan Completeness
- **Location**: Overview (line 18); Current State table row 3 (line 47); Phase 1 §3;
  Phase 4 §1 and §3; plan-brief lines 25–28 and 99
- **Detail**: The plan states that `test_put_is_rejected_as_a_disallowed_method` has a
  docstring promising an `Allow` assertion and that "There is no `Allow` assertion.
  `lessons.md` #1 verbatim, live in `master`". The body at
  `tests/trips/test_trip_creation.py:205-207` is:

  ```python
  assert response.status_code == 405
  assert not Trip.objects.exists()
  assert "PUT" not in auth_client.options(reverse("trips:create")).headers["Allow"]
  ```

  There *is* an `Allow` assertion, and a DB probe besides. The test is not status-only.
  Consequences: "the four genuinely status-only tests" is three, not four; plan-brief's
  "no false positives" claim (line 99) is wrong, since one of the five findings is a false
  positive; and Phase 4 §3 creates a **new permanent `lessons.md` entry** whose entire
  premise is this fiction — a foundation doc read at the start of every `/10x-implement`
  run. A real but much smaller gap survives: line 207 asserts only PUT's *absence*, so it
  passes if `Allow` were `"HEAD, OPTIONS"`, while the docstring claims it "pins the pair of
  verbs that stay open".
- **Fix A ⭐ Recommended**: Correct the evidence; keep a narrowed finding and lesson.
  - Strength: The residual gap (negative-only `Allow` assertion vs. a docstring claiming a
    positive pin) is real and still `lessons.md` #1-shaped. Phase 1 §3's contract as
    written — read `Allow` off the 405 response directly — already fixes it, and
    incidentally removes the trailing `options()` call that triggers F2's false positive.
  - Tradeoff: Requires rewriting six passages across plan.md and plan-brief.md, and the
    change's headline narrative gets materially less dramatic.
  - Confidence: HIGH — body read directly at `test_trip_creation.py:199-208`.
  - Blind spot: Whether the weakened lesson still earns its own numbered entry, or belongs
    as a clause on existing entry #1, is a judgment call.
- **Fix B**: Drop this test from Phase 1 and drop the new `lessons.md` entry.
  - Strength: Fastest correction; nothing false survives anywhere.
  - Tradeoff: Loses a genuine (if minor) assertion gap, and Phase 4 §1's §6.7 note loses
    its most interesting content — "a mechanized rule caught what a human read of 268 tests
    missed" becomes 3-of-5 rather than 5-of-5.
  - Confidence: HIGH — same evidence.
  - Blind spot: None significant.
- **Decision**: FIXED (Fix A) — corrected across plan.md (Overview, Current State table,
  Phase 1 §3, Phase 4 §1/§3) and plan-brief.md (Overview, Phases at a Glance).

### F2 — The audit rule has an unmodelled false-positive class

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — Rule definition (plan.md:305-310); Success Criteria 2.5
- **Detail**: The rule counts probes only "after the last such call in the function".
  Eight sites in the suite fuse a client call *into* the assertion itself, so the last act
  and the last probe are the same statement and nothing follows it:
  `tests/trips/test_trip_creation.py:207`, `tests/trips/test_trip_delete.py:245`,
  `tests/trips/test_trip_edit.py:257`, `tests/test_media_storage.py:273,289,292,295,309`.
  `test_trip_creation.py:207` is confirmed to be the final statement of its function —
  which is why the planning heuristic flagged it (F1). This is the same positional
  refinement the plan credits with catching `test_gpx_download.py:97`; it cuts both ways,
  and the plan does not say so. Phase 2 criterion 2.5 is specified as an exact expectation
  ("exactly the one healthz test and nothing else"); if any of the seven other fused sites
  is its function's last statement, 2.5 fails and the implementer's cheapest path is to
  waive rather than fix — precisely how a waiver list rots into an escape hatch.
- **Fix A ⭐ Recommended**: Count non-status assertions *at or after* the last act.
  - Strength: Models the suite's real idiom instead of dictating style; the fused statement
    is genuinely both act and probe. Removes the false positive on
    `test_trip_creation.py:207` without touching it.
  - Tradeoff: Slightly weakens the rule — a status-only fused assert
    (`test_trip_delete.py:245`) would need a separate sub-check.
  - Confidence: MEDIUM — verified the shape exists at 8 sites; have not confirmed which are
    terminal statements in their functions.
  - Blind spot: The exact count 2.5 should expect is unknown until the refined rule runs
    against the post-Phase-1 suite.
- **Fix B**: Keep the rule; restructure the fused tests in Phase 1.
  - Strength: Keeps the rule simple and its "act then probe" story clean.
  - Tradeoff: Expands Phase 1 from 3 files to up to 4, and lets the gate dictate test style
    across tests the plan never examined.
  - Confidence: MEDIUM — same evidence gap.
  - Blind spot: `test_media_storage.py`'s five fused sites are the waived test's own idiom;
    restructuring them fights the waiver's rationale.
- **Decision**: FIXED (Fix A) — Phase 2's rule now counts probes at-or-after the last act.

### F3 — Desired End State overclaims the harness, and Phase 4 writes the overclaim into two foundation docs

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Desired End State bullet 3 (plan.md:73-75); plan-brief Success Criteria;
  Phase 4 §1 (test-plan §5 row) and §2 (AGENTS.md)
- **Detail**: "Deleting or weakening any of the five guarded tests turns that step red."
  Deletion is caught. *Weakening* is caught only when the weakening removes the one
  assertion its shape's mutation happens to trip.
  `test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object` carries eight
  delegated `route.probe(target, response)` calls (`tests/test_ownership_matrix.py:569,
  626, 664, 701, 731, 761, 788, 818`) spanning every object-scoped route, while the
  `unscoped_trip_detail_queryset` shape only exercises the `trips:detail` cells — gutting
  the `gpx:download` probe leaves that shape green, and no other shape covers it. Phase 4
  then copies this guarantee into `test-plan.md` §5 and `AGENTS.md`, where the next agent
  will trust it. Given `lessons.md` #5 (a stale `AGENTS.md` actively misdirects) and #1 (a
  claim must be honoured by the thing making it), a change built to eliminate overclaimed
  protection should not ship one.
- **Fix**: Restate the guarantee as what it is — "deleting a guarded test, or removing the
  specific assertion its shape trips, turns the step red" — in Desired End State,
  plan-brief, and both Phase 4 doc contracts. Add the limitation to §6.8 so the next shape
  author knows a shape guards one assertion, not a whole test.
  - Strength: Costs four sentences and makes the docs survive scrutiny.
  - Tradeoff: The gate sounds weaker in `test-plan.md` §5 than "five tests protected" —
    which is the honest reading.
  - Confidence: HIGH — eight probe sites confirmed in the guard test.
  - Blind spot: None significant.
- **Decision**: FIXED — restated in Desired End State, plan-brief, and §6.8.

### F4 — Phase 3's inventory assertion leaves an unresolved choice that can violate the plan's own cost rule

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 3 §3 (plan.md:423-424); Performance Considerations
- **Detail**: The inventory assertion is deliberately unmarked, so it runs in every default
  `pytest` and in the CI `Tests` step. The plan leaves its mechanism to the implementer:
  "collected via `pytest --collect-only` or by parsing the target file, whichever stays
  honest without a second subprocess per shape." `--collect-only` means a pytest collection
  of the whole suite inside the default suite. Performance Considerations says the harness
  "must not enter the local edit loop, the pre-commit layer, or any per-edit hook" — the
  marker and `addopts` exist for exactly that reason. The two options are not equivalent,
  and one contradicts the section three paragraphs above it.
- **Fix**: Mandate the AST-parse option. Phase 2 already builds a module that parses every
  file under `tests/` and extracts test function names — the inventory assertion should
  import and reuse it, resolving each guard node id against that parse. Zero subprocesses,
  one parser instead of two.
  - Strength: Removes the choice, removes the cost, and makes Phase 2 a dependency Phase 3
    reuses rather than duplicates.
  - Tradeoff: Couples `test_suite_bites.py` to `test_assertion_strength.py`'s internals;
    the shared helper may want its own module.
  - Confidence: HIGH — the Phase 2 module is specified to build this exact index.
  - Blind spot: Whether node ids with parametrization brackets need special handling in the
    resolve step.
- **Decision**: FIXED — Phase 3 §3 now mandates reuse of Phase 2's AST parse.

### F5 — `fragment` is load-bearing but never validated

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Implementation Approach; Phase 3 §1 and §3 (plan.md:416-419); Manual
  Verification
- **Detail**: "Red for the right reason" is defined as four conditions: zero errors, ≥1
  failure, guard node named, expected `fragment` present. Two are near tautological — the
  subprocess runs only the guard node, so its id necessarily appears in the output. That
  leaves `fragment` as the sole discriminator between "the assertion bit" and "something
  bit". Yet the plan gives no rule for choosing one, and no verification exercises it:
  manual step 3 (delete an assertion) is caught by the ≥1-failure condition, and step 4
  (repoint to the defining module) by the zero-errors condition. A fragment of
  `"AssertionError"` or `"assert"` would pass all five cases vacuously and nothing in the
  plan would notice.
- **Fix**: State the selection rule in Phase 3 §1 — a fragment must be a distinctive
  substring of the guard assertion's own message or expression, never a generic pytest
  token — and add a manual verification step confirming each fragment is absent from the
  *unmutated* run's output. Carry the rule into §6.8's checklist for adding a sixth shape.
  - Strength: Turns the one condition doing real work into something checkable, for the
    cost of one verification step.
  - Tradeoff: A distinctive fragment couples the shape to the guard's assertion text, so
    rewording a message breaks the harness — arguably correct, but a maintenance edge.
  - Confidence: HIGH — the four conditions are enumerated at plan.md:416-419.
  - Blind spot: None significant.
- **Decision**: FIXED — selection rule stated in §1, verification step added, carried into
  §6.8.

### F6 — Two documented claims go stale and are not in Phase 4's scope

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 Changes Required; criterion 4.5
- **Detail**: Adding `addopts = '-m "not bite_proof"'` changes the meaning of every bare
  `pytest` invocation. Two documented ones become misleading and neither is in Phase 4's
  contract: `AGENTS.md:54` — the CI-equivalence command
  (`SECRET_KEY=… uv run pytest --cov`) stops being CI-equivalent once CI runs a second
  pytest step the command does not; and `context/foundation/test-plan.md:127` — the §5
  ownership-matrix row states `deploy.yml` "already runs `pytest --cov` … so no new CI job
  was needed", which stops describing the workflow once a second step exists. Criterion 4.5
  ("No document claims a gate, path, or command that does not exist") cannot pass while
  these stand. Blast radius is otherwise genuinely narrow — no `lefthook.yml`, no
  `.pre-commit-config.yaml`, no `.husky/`, no `hooks` key in either `.claude/settings*.json`,
  and README.md/DEPLOY.md contain no pytest references, so no doc edits are needed there.
- **Fix**: Add both lines to Phase 4 §1 and §2's contracts — pair the CI-equivalence command
  with its `-m bite_proof` counterpart, and amend the §5 ownership-matrix row.
- **Decision**: FIXED — both added to Phase 4 §1/§2's contracts.

### F7 — Phase 4 writes an archive path that does not exist yet

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 §1, first bullet (plan.md:504)
- **Detail**: Phase 4 says §3 row 5's change folder should point "at this change's archived
  path", but archiving happens after `/10x-impl-review` and `create-pr` — so the path and
  its date prefix are a guess at write time, contradicting criterion 4.5. Precedent allows
  either: rows 2–4 use `context/archive/<date>-<id>/`, but row 1 is `complete` while still
  pointing at `context/changes/testing-data-isolation-contract/`.
- **Fix**: Leave the `context/changes/` path in Phase 4 and let `/10x-archive` update it, or
  state explicitly that the archive path is written at archive time, not in Phase 4.
- **Decision**: FIXED — Phase 4 §1 now leaves the `context/changes/` path and states
  `/10x-archive` updates it later.

### F8 — AGENTS.md's gate sequence is already stale in the sentence Phase 4 edits

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 §2
- **Detail**: `AGENTS.md:63` names one vendored-asset integrity check; `deploy.yml` has two
  (`Vendored asset integrity` for Leaflet, `Vendored asset integrity (Bootstrap)`). Phase 4
  rewrites that exact sentence and criterion 4.5 forbids inaccurate gate claims.
- **Fix**: Add the Bootstrap step to the sentence while it is open.
- **Decision**: FIXED — added to Phase 4 §2's contract.

### F9 — The cost claim contradicts the step's placement

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details ("Cost budget", plan.md:183-186); Phase 3 §5
- **Detail**: The plan calls the harness "a separate CI step, not part of the ~6-minute
  `gates` sequence", but Phase 3 §5 places it inside the `gates` job, so it adds to that
  job's wall clock. The 10–20 s figure is also measured locally (criterion 3.9) while each
  subprocess re-runs migrations on a slower GitHub Actions runner.
- **Fix**: Say "a separate step, ~10–20 s added to the gates job" and note the CI figure is
  expected to exceed the local one.
- **Decision**: FIXED — Cost budget rewritten to reflect gates-job placement.
