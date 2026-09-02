<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Gate Credibility Implementation Plan

- **Plan**: `context/changes/testing-gate-credibility/plan.md`
- **Scope**: Phases 1–4 of 4 (all complete)
- **Date**: 2026-09-01
- **Verdict**: REJECTED
- **Findings**: 2 critical, 5 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | FAIL |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

**Scope Discipline — PASS.** All 18 changed files are under `tests/`, `pyproject.toml`,
`.github/workflows/deploy.yml`, `context/`, or `AGENTS.md`. Zero production modules touched.
No new dependency (`ast`, `subprocess` are stdlib). No mutmut/cosmic-ray/mutpy, no AI
reviewer, no risk-area or quality-gate redefinition, no e2e. Every "What We're NOT Doing"
guardrail held.

**Architecture — PASS.** The registry/hook/harness split is clean: `tests/mutations.py`
declares shapes as importable data with no side effects, `tests/conftest.py` applies one,
`tests/test_suite_bites.py` reads the same tuple. The audit follows the
`test_coverage_scope.py` / `test_ownership_matrix.py` asserted-inventory precedent faithfully.

**Success Criteria — automated.** All green on a clean checkout, verified this session:
`pytest --cov` → 332 passed, 2 skipped, 5 deselected, 97.21% coverage; `pytest -m bite_proof`
→ 5 passed in 28.6 s; `ruff` / `black` / `isort` / `mypy --strict` all clean (81 files);
the inventory assertion is collected in the default run
(`test_every_risk_area_has_a_shape_and_every_guard_node_resolves`, 1/6 collected, 5
deselected). Marked WARNING rather than PASS for two reasons: the first `pytest --cov` of
this session was **red** (F2), and two manual criteria (3.6, 3.10) were recorded as verified
by a check that cannot fail (F1).

## Findings

### F1 — The `fragment` check matches pytest's printed source, so a shape can report green with no mutation applied

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Safety & Quality
- **Location**: `tests/test_suite_bites.py:96`, `tests/mutations.py:161`, `context/foundation/test-plan.md:293-301`
- **Detail**: The harness's fourth condition is `shape.fragment in output`, searched over the
  child's entire captured output. On failure pytest prints every source line of the guard
  function from its `def` down to the failing statement — so a fragment that is not the
  guard's *last* assertion appears whenever that test fails **for any reason at all**.

  Demonstrated empirically this session. With `media-misconfigured-probe/` present in the
  repo root (the state F2 leaves behind) and **`VELOLOG_MUTATION` unset**:

  ```
  $ uv run pytest tests/test_media_storage.py::test_healthz_fails_when_media_root_is_inside_base_dir_and_debug_is_false \
        -o addopts= -p no:cacheprovider --no-header -q
  E       AssertionError: assert not True          # the LAST assert, line 159
  1 failed in 0.47s
  $ grep -c 'assert response.status_code == 500' out.txt
  1                                                # the fragment, printed as source context
  ```

  Zero errors ✓, one failure ✓, guard node named ✓, fragment present ✓ — all four conditions
  of "red for the right reason" satisfied by a run with no mutation in it. `mutations.py:161`'s
  fragment is that guard's *first* assertion (`test_media_storage.py:147`), and the guard's own
  docstring at `:134-139` documents a spurious failure mode at its last assertion.
  `unscoped_trip_detail_queryset` has the same shape: `"confirms the pk exists"` lives in the
  first assert's message (`test_ownership_matrix.py:564-568`) with `route.probe(...)` after it.

  Compounding this: `test-plan.md:293-296` prescribes verifying discrimination by running the
  guard node **unmutated** and confirming the fragment is absent. On a clean tree that run
  *passes*, pytest prints no source at all, and every possible fragment is trivially absent.
  The documented verification cannot fail, which is why Progress 3.10 recorded it as passing.
- **Fix A ⭐ Recommended**: Match the fragment only against pytest's failure-marked lines — the
  `> ` flow-marker line and the `E ` explanation lines — rather than the whole captured output.
  - Strength: Fixes the mechanism for all five shapes at once, keeps every current fragment
    value valid, and makes `test-plan.md` §6.8's verification step meaningful instead of
    vacuous. Directly reproducible: re-run the experiment above and the check must go red.
  - Tradeoff: `mutations.py:161`'s fragment (`assert response.status_code == 500`) will no
    longer match, because under the mutation that assertion is the one that trips and pytest
    renders it as `E assert 200 == 500` rather than as source — so that shape needs a fragment
    drawn from the `E ` line or from the guard's later, semantically richer assertions.
  - Confidence: HIGH — the failure mode was reproduced end to end, and the fix was verified
    against the actual output shape.
  - Blind spot: pytest's `-q` traceback rendering is version-dependent; pinning the parse to
    `E `/`> ` prefixes is stable across 7.x–9.x but is a text contract, not an API.
- **Fix B**: Require each shape's fragment to be the guard test's *final* assertion, and assert
  that positionally in the unmarked inventory test (reusing the existing AST parse).
  - Strength: Deterministic and checked in the default suite, so it cannot rot; no dependence
    on pytest output formatting.
  - Tradeoff: Constrains which assertion a shape may target to whichever happens to be last,
    which is the opposite of the plan's own "a shape guards the one assertion it exercises"
    framing — and three of five current guards would need reordering or new fragments.
  - Confidence: MEDIUM — sound, but it trades a real limitation for a different one.
  - Blind spot: Does not help when a guard test's last assertion is itself the flaky one.
- **Decision**: FIXED via Fix A — `tests/test_suite_bites.py` now matches `shape.fragment`
  only against lines starting `>` or `E `. Verified empirically: the false-green scenario
  (leftover `media-misconfigured-probe/` present, `VELOLOG_MUTATION` unset) no longer
  matches the fragment, and all five shapes still discriminate correctly under real
  mutation. `uv run pytest -m bite_proof -v` → 5 passed.

### F2 — `pytest -m bite_proof` leaves a directory in the repo root that turns the next plain suite run red, invisibly to git

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/mutations.py:150-161` (`media_guard_always_clean`), `tests/test_media_storage.py:142,159`
- **Detail**: The `media_guard_always_clean` shape patches `media_root_misconfiguration` to
  return `None`, so `_probe_health`'s short-circuit (`velo_log/urls.py:163`) no longer fires and
  `_media_round_trips` writes its probe under `MEDIA_ROOT` — which the guard test has set to
  `BASE_DIR / "media-misconfigured-probe"` (`test_media_storage.py:142`). `FileSystemStorage`
  creates the parent directories; only the probe *file* is deleted. The directory survives the
  subprocess.

  The guard test's last assertion is `assert not in_container_media_root.exists()`
  (`:159`), so every subsequent run of the plain suite fails on it. Reproduced A→D on a clean
  tree this session:

  ```
  A) tree clean                                        → media-misconfigured-probe absent
  B) pytest -m bite_proof -k media_guard_always_clean   → 1 passed
  C) find media-misconfigured-probe                     → media-misconfigured-probe/healthz
  D) pytest <the guard node>                            → 1 failed
  ```

  Confirmed the harness is the *sole* source: `pytest tests/test_media_storage.py` on a clean
  tree is 13 passed and creates nothing.

  Three things make this worse than a stray file. `git status --porcelain` is **clean** —
  git does not track empty directories, so there is no signal. `.gitignore:84` covers `media/`
  but not this path. And CI masks it entirely: `deploy.yml` runs `Tests` *before*
  `Suite credibility` on a fresh runner, so the order that F1 justifies is also the order that
  hides F2. The failure lands only on a developer, and specifically on anyone re-running
  `AGENTS.md:57-60`'s two documented CI-equivalence commands a second time.
- **Fix**: Point the guard test's `MEDIA_ROOT` at a path inside `tmp_path` that is still
  `BASE_DIR`-relative, or give the shape a teardown that removes the tree it created — a
  `finally` in `_apply_mutation_shape` (`tests/conftest.py:101-104`) that unlinks
  `Path(settings.BASE_DIR) / "media-misconfigured-probe"` is the smallest change. Whichever is
  chosen, add the path to `.gitignore` as a belt-and-braces measure so it is at least visible.
- **Decision**: FIXED — `tests/conftest.py`'s `_apply_mutation_shape` now removes
  `BASE_DIR/media-misconfigured-probe` in a `finally` after every mutation run (harmless
  no-op for the other four shapes and for a normal run); also added to `.gitignore` as
  belt-and-braces. Verified: `uv run pytest -m bite_proof -v` then `ls
  media-misconfigured-probe` → does not exist; `pytest tests/test_media_storage.py` after →
  13 passed.

### F3 — The ownership shape's guard node is unparametrized and its fragment is shared by every cell

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `tests/mutations.py:99-104`
- **Detail**: `guard_node_id` names
  `test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object` with no param id, so
  the child runs every route×verb cell. The harness asserts only `failed >= 1` (correctly — the
  plan reasons this out at `plan.md:176-180`), and the fragment `"confirms the pk exists"` is the
  assertion message shared by **all** cells (`test_ownership_matrix.py:564-568`). So a failure in
  any unrelated cell — a `gpx` route, say — satisfies all four conditions while the
  `trips:detail` cell the mutation actually targets could be green. The mutation touches exactly
  one view, so the node id can be narrowed without losing anything.
- **Fix**: Pin the node id to the specific parametrization (the `trips-detail-*` cell ids), or
  assert that the `FAILED` lines name the expected cell. Narrowing the node also shortens that
  case's subprocess.
- **Decision**: FIXED — `guard_node_id` pinned to `[trips:detail-get]`. The AST inventory
  check (`_all_test_function_names`/`test_every_risk_area_has_a_shape_and_every_guard_node_
  resolves`) strips the `[...]` parametrize suffix before matching against the function
  inventory. Verified: `uv run pytest -m bite_proof -v` → 5 passed, and the harness's
  wall-clock dropped from ~28-30s to ~11-13s for five shapes, since only one cell of the
  matrix runs now instead of all eight.

### F4 — Phase 4 did not record either deviation Progress 3.8 and 3.9 said it would; three documents still assert a mechanism the implementation disproved

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: `context/foundation/test-plan.md:247-256`, `AGENTS.md:54`, `tests/mutations.py:14-19`, `pyproject.toml:64`, `tests/test_suite_bites.py:10`
- **Detail**: Two Progress entries record deviations and explicitly defer recording them to
  Phase 4. Neither was recorded.

  *The false-green trap.* `plan.md:713-717` (item 3.8) says the defining-module trap "does not
  reproduce under this harness's single-guard-node-per-subprocess isolation (Django's lazy
  view/form import means the defining-module patch propagates through anyway); recorded as a
  finding for Phase 4". Phase 4 wrote the opposite. `test-plan.md:250-253` states that patching
  `gpx.availability.track_file_is_available` "leaves the view's own module attribute untouched
  and the harness **would report a false green**"; `AGENTS.md:54` repeats "or the harness reports
  a false green"; `mutations.py:14-19` repeats it a third time. Patching the imported name is
  still the right convention, but the stated *consequence* is one the implementation tested and
  could not reproduce, and no document says so. Note the irony against F1: a false green is
  genuinely reachable here — just by a different route than the one all three documents warn about.

  *The wall clock.* `plan.md:718-721` (item 3.9) measured ~33-38 s locally, ~6-7 s per boot, and
  says "the real figure is what Phase 4 records instead of the 10-20s estimate". Measured
  independently this session: **28.6 s** for five shapes (~5.7 s per boot). Still recorded:
  `pyproject.toml:64` "~10-20 s", `AGENTS.md:54` "~10-30s", and `test_suite_bites.py:10` "each
  case pays a cold Django boot (~2-4 s)" — the exact per-case figure 3.9 says was wrong.
  `test-plan.md` gives no figure at all. Nothing in the repo contains the measured number.
  `plan.md:192` makes the budget load-bearing ("If a sixth shape is ever added, that budget is
  the thing to re-check"), so a 2-3× understatement is not cosmetic.
- **Fix**: Amend the three false-green sentences to state the convention as a convention and
  record 3.8's finding — that the trap did not reproduce, and why — in §6.7 alongside the other
  Phase 5 notes. Replace the three timing figures with the measured one (~30 s for five shapes,
  ~6 s per boot) and drop `test_suite_bites.py:10`'s per-case estimate.
- **Decision**: FIXED — added a Phase 5 note to `test-plan.md` §6.7 recording that the
  defining-module trap did not reproduce (Django's lazy view import propagates the patch
  through regardless) and that patching the importing module is a convention, not a proven
  false-green guard; reworded the three "would report a false green" sentences in
  `test-plan.md`, `AGENTS.md`, `tests/mutations.py` accordingly. Replaced all timing figures
  with the current measured number (~12-13s for five shapes after F3's narrowing, re-measured
  three times) in `test-plan.md`, `AGENTS.md`, `pyproject.toml`, `tests/test_suite_bites.py`.
  Also updated `test-plan.md` §6.8's "Verify before committing" step, which was itself the
  vacuous check F1 flagged, to describe the new failure-marked-line verification.

### F5 — No timeout on the harness subprocess

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/test_suite_bites.py:46-64`
- **Detail**: `subprocess.run` is called with no `timeout=`, and nothing else bounds the child
  (`-x` absent, no pytest timeout plugin). A mutation that removes a short-circuit or a guard is
  exactly the kind of change that can make a child loop or block on a lock — and the parent then
  waits forever. In CI that burns the runner's job limit with no diagnostic pointing at which
  shape hung. The existing subprocess precedent (`tests/test_settings_env.py`) runs bounded
  work, so this is new exposure introduced by mutating behavior deliberately.
- **Fix**: Pass `timeout=180` per case and catch `subprocess.TimeoutExpired`, failing with the
  shape name and the partial output.
- **Decision**: FIXED — `GUARD_SUBPROCESS_TIMEOUT_SECONDS = 180` passed to `subprocess.run`;
  `subprocess.TimeoutExpired` caught and `pytest.fail`s with the shape name, guard node id,
  and partial captured output. Verified: `uv run pytest -m bite_proof -v` → 5 passed
  (unaffected by the added `try`/`except`); `mypy`/`ruff`/`black`/`isort` clean.

### F6 — The audit's status-only predicate is defeated by three ordinary status-check idioms

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `tests/test_assertion_strength.py:153-173`
- **Detail**: `_is_status_only_assert` matches only `<...>.status_code <op> <int literal>`;
  everything else is classified as a behavior probe by construction (the contract is stated at
  `:158`). Running the predicate directly, all three of these are classified **not** status-only
  and therefore satisfy the rule vacuously:

  ```python
  assert response.status_code in (200, 302)        # tuple of int constants
  assert response.status_code == HTTPStatus.OK     # attribute, not an int literal
  assert response.status_code == expected_status   # parametrized name
  ```

  `grep` confirms none exists in the suite today, so this is a latent hole rather than a live
  false green — but a tuple-membership status check and a parametrized `expected_status` are
  precisely the next idioms someone reaches for, and the gate's whole value is that it holds
  *forever* without anyone remembering it.
- **Fix**: Treat `In`/`NotIn` against a tuple or list of int constants as status-only, and treat
  a comparison whose only non-`status_code` side is a bare `Name` or `Attribute` as
  *unclassifiable* — reported as a finding requiring a waiver, i.e. fail closed rather than
  fail open.
- **Decision**: FIXED — `_is_status_only_assert` extended to treat `In`/`NotIn` against a
  tuple/list of int constants as status-only, and to treat `Eq`/`NotEq`/`Is`/`IsNot` against
  a bare `Name` or `Attribute` (e.g. `expected_status`, `HTTPStatus.OK`) as status-only too
  (fail closed). Verified with synthetic AST cases for all three idioms from the finding
  (all now correctly classified status-only) plus five known-good probe patterns (all still
  correctly classified as probes, no regression); `uv run pytest
  tests/test_assertion_strength.py` → 3 passed, no new findings against the real suite.

### F7 — Population detection fails open in three places

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `tests/test_assertion_strength.py:234-240`, `:268-276`, `:279-298`
- **Detail** (three related defects, one fix pass):
  1. **Class-based tests are wholly exempt.** `_module_test_functions` (`:268-276`) iterates only
     `tree.body`, so a `class TestUploads: def test_...` is never in the population — silently,
     since `test_the_population_is_non_empty` only fires when *nothing* matches. No class-based
     tests exist today (only helper classes), but `AGENTS.md` documents integration-test
     conventions using exactly that shape, and `_all_test_function_names` would also fail to
     resolve a guard node inside one.
  2. **`with`-wrapped acts are misordered.** The positional rule compares `node.lineno` against
     `_last_act_lineno` (`:234-240`, `:249-257`). An `ast.With` carries the lineno of its `with`
     keyword, which is *smaller* than the act nested in its body — so a test whose only probe is
     `with pytest.raises(...): client.get(url)` has that probe skipped and is reported as
     status-only. A false alarm rather than a false green, but it would send a future
     implementer to "fix" a correct test.
  3. **Unresolvable delegation is silently excluded.** `_is_act_helper` returns `False` for a
     second-level or unresolvable delegation (`:143`) and `_collect_analysis` then `continue`s at
     `:294` with no record — the test is never examined rather than reported as unclassifiable.
     137 of 273 top-level test functions are currently in the population and no out-of-population
     test takes a client-ish fixture, so the detector is sound today.
- **Fix**: Recurse one level into `ast.ClassDef` for `test_*` methods (keyed `path::Class::name`
  to match pytest node ids), use containment (`node.lineno <= last_act <= node.end_lineno`)
  instead of `node.lineno >= last_act`, and report a test that takes a client-ish parameter but
  yielded no act call as a finding rather than an exclusion.
- **Decision**: FIXED — all three sub-fixes applied in `tests/test_assertion_strength.py`.
  (1) New `_class_test_methods` recurses into top-level `Test*`-named classes for `test_*`
  methods, keyed `Class::name` to match pytest node ids; wired into `_collect_analysis` and
  (via the new `tests/astscan.py`, see F10) into `test_suite_bites.py`'s inventory check too.
  (2) `_has_behavior_probe`'s node filter now compares `end_lineno` (falling back to
  `lineno`) against `last_act_lineno` instead of `lineno` alone, so a `with pytest.raises(...):
  client.get(url)` block containing the act is no longer skipped. (3) `_collect_analysis`
  now records `False` (a finding) for a test with a client-ish parameter whose act call
  can't be resolved, instead of silently `continue`-ing past it unexamined.
  Verified: synthetic AST cases for all three (class-based test detected; `with`-wrapped act
  now correctly reads as a probe — confirmed the old logic returned the wrong answer first;
  second-level delegation now yields a finding) plus `uv run pytest
  tests/test_assertion_strength.py` → 3 passed against the real suite (no new findings) and
  the full `pytest --cov` → 333 passed, 97.21% coverage.

### F8 — The Phase 1 `Allow` fix leaves a numerically wrong docstring and swaps the sibling's membership idiom for exact string equality

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/trips/test_trip_creation.py:198`, `:208`
- **Detail**: The fix went in the right direction — the assertion was strengthened, not the
  docstring weakened, and `allow == "GET, POST, HEAD, OPTIONS"` matches
  `trips/views.py:64`. Two residues. The docstring at `:198` still says the assertion "pins the
  **pair** of verbs that stay open" while it now pins four — the overclaim is gone but the
  wording is numerically wrong, which is a small instance of the very lesson (#11) this test is
  the source of. And exact equality on the joined header binds the test to the order
  `View._allowed_methods()` happens to emit; the sibling fix in `test_gpx_upload.py:498-499`
  uses membership (`"GET" not in`, `"POST" in`), which is the repo's idiom and does not break on
  a Django upgrade.
- **Fix**: Reword `:198` to say the assertion pins the full set of verbs, and consider asserting
  the parsed `Allow` set rather than the joined string.
- **Decision**: FIXED — docstring reworded to "pins the full set of verbs"; assertion now
  parses the header into a set (`{verb.strip() for verb in allow.split(",")}`) and compares
  by set equality rather than exact string equality, matching the sibling's order-independent
  intent without weakening what it pins. Verified:
  `test_put_is_rejected_as_a_disallowed_method` → passed.

### F9 — Harness subprocess hygiene: no explicit encoding, `returncode` ignored, `COV_CORE_*` inherited

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/test_suite_bites.py:36-45`, `:61-63`, `:73-88`
- **Detail**: Three small robustness gaps, none currently biting:
  - `text=True` with no `encoding`/`errors` decodes with the process locale. This machine's
    locale is **cp1250**, and `tests/gpx/test_gpx_parsing.py` contains U+2192 (`→`) — child
    output carrying such a character garbles, and an undefined cp1250 byte slot can raise
    `UnicodeDecodeError`, turning a real result into an unrelated harness crash. Linux CI is
    unaffected; local runs are not.
  - `result.returncode` is never inspected; the counts come from regexes over the `-q` summary.
    An `INTERNALERROR`, a usage error (exit 4) or "no tests ran" (exit 5) yields
    `error_count == 0` **and** `failed_count == 0`, so it fails loudly on `failed_count >= 1` —
    but with the wrong diagnosis ("the guard was weakened or the patch target moved"). The
    precedent asserts the code explicitly (`tests/test_settings_env.py:78`, `:121`).
  - The docstring at `:36-45` says `-o addopts=` stops the child writing a competing coverage
    file. That holds for the child's own `--cov`, but pytest-cov's subprocess hook is env-driven
    (`COV_CORE_SOURCE`/`COV_CORE_CONFIG`) and `env = {**os.environ, ...}` inherits it — so
    `pytest --cov -m bite_proof`, a plausible local invocation, still instruments all five
    children and drops `.coverage.*` files. CI sidesteps this by keeping the steps separate.
- **Fix**: `encoding="utf-8", errors="replace"`; require `returncode == 1` and map 2/3/4/5 to
  their own harness-error message; pop `COV_CORE_*` from the child env.
- **Decision**: FIXED — all three applied. `encoding="utf-8", errors="replace"` added to
  `subprocess.run`. `_run_guard_under_mutation` now returns a `_GuardRun(returncode, output)`
  `NamedTuple`; the test checks `returncode != 1` first and reports a distinct diagnosis via
  `PYTEST_EXIT_CODE_MEANINGS` (0/2/3/4/5) before falling through to the existing
  error/failed-count checks. `COV_CORE_*` is now stripped from the child env instead of
  inherited. Verified: an unresolvable guard node id now reports `returncode: 4` with "pytest
  raised a usage error" instead of a misdiagnosed failed-count message (confirmed via a
  standalone repro); `pytest --cov -m bite_proof` → 5 passed, no stray `.coverage.*` files
  (confirmed via `git status --porcelain`, clean); `uv run pytest -m bite_proof -v` → 5
  passed.

### F10 — Unexplained `# noqa`, cross-module private import, and a redundant AST re-parse

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/test_suite_bites.py:46`, `:24`, `tests/test_assertion_strength.py:279-281`, `:301-343`
- **Detail**:
  - `# noqa: S603` at `:46` carries no reason, while both precedents do
    (`tests/test_settings_env.py:60`, `:102`: "S603: argv is entirely literal — this interpreter
    and the constant source above"), and the global standard requires an inline explanation for
    every new suppression.
  - `:24` imports a private helper across test modules
    (`from tests.test_assertion_strength import REPO_ROOT, TEST_DIR, _module_test_functions`).
    The reuse is well-motivated in the docstring and correctly avoids `--collect-only`, but it is
    new to this repo — both existing meta-tests are self-contained — and `REPO_ROOT` is now
    defined three ways under `tests/`. A rename in the audit module breaks the harness at import
    time.
  - The declared return type at `:279-281` (`dict[..., bool | None]`) never holds `None`, because
    `:294` `continue`s instead of storing — so the docstring's "or `None` if out of population"
    and the `if found is not None` filter at `:304` are dead. `_collect_analysis()` also
    re-parses every file under `tests/` once per audit test (three times), plus a fourth pass in
    `_all_test_function_names()`.
- **Fix**: Add the `noqa` reason; if the sharing stays, promote the shared AST helpers into a
  non-`test_` module (`tests/astscan.py`, alongside `tests/mutations.py`) with public names; add
  a module-level `functools.cache` and narrow the return type to `dict[..., bool]`.
- **Decision**: FIXED — all three applied. Added the `noqa: S603` reason comment matching the
  `test_settings_env.py` precedent. Created `tests/astscan.py` with public `module_test_
  functions`/`class_test_methods` (plus `REPO_ROOT`/`TEST_DIR`/`FuncDef`); both
  `test_assertion_strength.py` and `test_suite_bites.py` now import from there instead of one
  reaching into the other's private names, so `REPO_ROOT` is defined once, not three times.
  `_collect_analysis` is now `@functools.cache`d (safe — no caller mutates the returned dict)
  and its return type narrowed to `dict[tuple[str, str], bool]`; the dead `is not None`
  filter in `test_the_population_is_non_empty` removed. Verified: `ruff`/`black`/`isort`/
  `mypy` clean on all three files; `uv run pytest tests/test_assertion_strength.py
  tests/test_suite_bites.py::test_every_risk_area_has_a_shape_and_every_guard_node_resolves`
  → 4 passed; `uv run pytest -m bite_proof -v` → 5 passed; full `pytest --cov` → 333 passed,
  97.21% coverage.

## Post-triage verification

All ten findings fixed. Full CI-equivalence sweep run after the last fix:

- `uv run pytest --cov` → 333 passed, 2 skipped, 5 deselected, 97.21% coverage.
- `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
  → 333 passed, 2 skipped, 5 deselected, 97.21% coverage.
- `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest -m
  bite_proof -v` → 5 passed.
- `ruff check .` / `black --check .` / `isort --check .` / `mypy .` → all clean (82 files).
- `manage.py check` → no issues. `manage.py makemigrations --check --dry-run` → no changes
  detected.
- `git status --porcelain` → clean of stray artifacts (the `media-misconfigured-probe/`
  directory F2 flagged does not reappear after any of the above runs).
