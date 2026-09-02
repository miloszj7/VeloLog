# Gate Credibility — Plan Brief

> Full plan: `context/changes/testing-gate-credibility/plan.md`
> Research: `context/changes/testing-gate-credibility/research.md`

## What & Why

Rollout Phase 5 of `test-plan.md` closes Risk #4: "a regression reaches production with
every gate green." `lessons.md` #1, #3 and #4 all record this having already happened here.
The project has a coverage gate, a typing gate and a 331-test suite — and nothing that
proves any of it would notice if the behavior a test names actually broke.

## Starting Point

The suite is already unusually disciplined about the anti-pattern: research read all 268
test functions and found status assertions consistently paired with content, DB or storage
probes, several with docstrings naming the anti-pattern before guarding against it. What is
absent is a *mechanism* — nothing stops a new weak test appearing, and `test-plan.md`
§6.2's "break the production line, confirm it goes red, revert" ritual lives only in a
human's head during `/10x-implement`, with a real but purely historical track record
(`50b6abf`, `4e712b7`).

Running a mechanized heuristic during planning made the case sharper than research could:
against a 129-test request-cycle population it found five findings, not two — three
genuinely status-only tests, one legitimate waiver, and one docstring overclaim. That last
one, `tests/trips/test_trip_creation.py:191`, has a docstring ending *"The `Allow`
assertion pins the pair of verbs that stay open"* while its body only asserts `PUT`'s
absence from `Allow`, not the positive pin the docstring claims. That's a narrower
`lessons.md` #1 shape — a docstring overclaiming its own assertion — and a careful human
read of the whole suite walked past it.

## Desired End State

`uv run pytest --cov` fails when a new request-cycle test asserts nothing beyond a status
code, naming the test and what to add. A second CI step mutates five named production
behaviors — one per risk area — and fails if the guard test for any of them stays green.
Deleting a guarded test, or removing the specific assertion a shape's mutation trips, turns
CI red instead of shipping quietly — a shape guards the one assertion it exercises, not
every assertion in a multi-probe test.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Gate mechanism | AST assertion audit **plus** a bite-proof harness | The two sub-shapes of Risk #4 need different tools: "asserts too little" is AST-visible across the whole suite; "asserts the wrong thing" is only observable by mutating and re-running. | Plan |
| Mutation testing | Explicitly out of scope, not deferred-with-a-spike | `requires-python = ">=3.14"` with no 3.13 fallback, mutmut's unresolved 3.14 cache incompatibility, and a per-mutant full-suite cost that breaks a ~6-minute gates budget. | Research |
| AI-native assertion reviewer | Not used | A deterministic check answers this question, and §4's own "when NOT to use" line forbids a judgement layer over one. | Research |
| The residue (weak tests) | Fixed in Phase 1, before the gate exists | The gate then ships green on a clean suite rather than green on a four-entry waiver list — which is how a waiver list rots. | Plan |
| Mutation injection | Subprocess pytest + env-var-selected monkeypatch | Mutates real production behavior the guard test traverses, reuses the existing `test_settings_env.py` subprocess idiom, and never edits a source file so nothing can be left mutated on disk. | Plan |
| "Red for the right reason" | Zero errors + ≥1 failure + guard node named + expected fragment | A mutation that breaks collection makes everything red while proving nothing about any assertion — the exact false green §6.2 warns about. | Plan |
| Waivers | Explicit in-module allowlist with a written reason, asserted against reality | Mirrors `OBJECT_SCOPED_ROUTES`: a stale or no-longer-needed waiver fails the suite, so the list cannot silently grow into an escape hatch. | Plan |
| Harness placement | In `tests/`, behind a `bite_proof` marker, deselected by default, own CI step | Enforced on every PR without putting ~10–20 s of subprocess cost into the local edit loop or any per-edit hook. | Plan |

## Scope

**In scope:** four weak-test fixes; `tests/test_assertion_strength.py`; `tests/mutations.py`;
a session-scoped injection fixture in `tests/conftest.py`; `tests/test_suite_bites.py`;
marker + `addopts` in `pyproject.toml`; one new CI step; `test-plan.md` §3/§5/§6.7/§6.8,
`AGENTS.md`, `lessons.md`.

**Out of scope:** any production module (nothing outside `tests/`, `pyproject.toml`,
`deploy.yml`, `context/` is touched); mutmut/cosmic-ray/mutpy and any spike of them; an
AI-native reviewer; new dependencies; risk-map or quality-gate redefinitions; e2e.

## Architecture / Approach

Two gates in the suite itself, in the mould `tests/test_coverage_scope.py` already
established — a meta-test asserting a property of the suite, so CI's existing `pytest --cov`
enforces it with no new job.

```
tests/test_assertion_strength.py     pure ast over tests/  →  µs, runs in pytest --cov
    population: tests that issue a client request
    rule: ≥1 post-act probe beyond status_code
    waivers: asserted inventory (1 entry)

tests/mutations.py  ──┬──►  tests/conftest.py   (applies VELOLOG_MUTATION for the session)
   5 shapes, 1/risk   └──►  tests/test_suite_bites.py  [bite_proof]
                                └─ subprocess pytest <guard node>  →  must go red, for the named reason
```

The five shapes patch `trips.views.TripDetailView.get_queryset` (#2),
`gpx.signals.discard_file_by_key` (#1), `trips.views.track_file_is_available` (#3),
`gpx.forms.MAX_GPX_FILE_BYTES` (#5), and `velo_log.urls.media_root_misconfiguration` (#7) —
all verified as patchable attributes with existing guard tests.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Close the residue | Missing probes on three genuinely status-only tests, plus one docstring-vs-assertion gap | A probe that looks right but doesn't bite — mitigated by breaking each guarded line and confirming the *new* assertion is the one that fails |
| 2. Assertion-strength audit | The deterministic gate, with an asserted waiver inventory | False positives making the gate annoying enough to remove; the precision check (empty the waiver list, expect exactly one finding) is the acceptance test |
| 3. Bite-proof harness + wiring | Five shapes, injection hook, marker, `addopts`, CI step | Patching the *defining* module instead of the importing one — a silent false green, and the plan's headline trap; verified deliberately in manual testing |
| 4. Documentation | `test-plan.md` §3/§5/§6.7 + new §6.8, `AGENTS.md`, `lessons.md` | A doc claiming a command that was never run |

**Prerequisites:** none — Phases 1–4 of the rollout are complete and archived; no new
dependency, no infrastructure, no access needed.
**Estimated effort:** ~2–3 sessions across 4 phases. Phase 3 carries most of the
engineering; Phases 1 and 4 are short.

## Open Risks & Assumptions

- The AST heuristic was validated against today's suite (5 findings from 129 request-cycle
  tests, no false positives). A future test written in a shape the rule does not model — a
  probe delegated two helper levels deep, or a response bound to an unusual name — would be
  a false positive. The waiver inventory is the release valve, and its
  stale-entry assertion is what keeps that from becoming a habit.
- The harness assumes each guard node currently passes, rather than paying a baseline
  subprocess per shape to prove it. That holds because every guard node is a real test in
  the default suite, so a broken one already turns `pytest --cov` red.
- Five shapes is the budgeted size at ~2–4 s each. A sixth is the point to re-measure the
  CI step rather than assume it still fits.
- Mutation testing stays unavailable until a 3.13 interpreter or a confirmed mutmut 3.14 fix
  exists. If either appears, revisiting is a new change — this gate is not designed to grow
  into a mutation suite hand-written one mutant at a time.

## Success Criteria (Summary)

- A new request-cycle test that asserts only a status code cannot reach `master` — CI names
  it and says what to add.
- Deleting a guarded test, or removing the specific assertion a shape's mutation trips,
  turns CI red rather than quietly removing a protection nobody notices is gone — a shape
  guards the one assertion it exercises, not every assertion in a multi-probe test.
- `test-plan.md` §5's "suite credibility gate" row describes something that exists and runs
  on every PR, and §6.8 tells the next contributor how to add a shape.
