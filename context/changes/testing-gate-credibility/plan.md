# Gate Credibility Implementation Plan

## Overview

Close rollout Phase 5 of `context/foundation/test-plan.md` (§3 row 5, Risk #4: "a
regression reaches production with every gate green") by giving that risk two
complementary gates instead of another coverage number:

1. **An assertion-strength audit** — a deterministic meta-test that walks every
   request-cycle test's AST and fails the suite when a test asserts nothing beyond a
   status code. Catches the "asserts too little" shape (`lessons.md` #1) across the whole
   population, forever, in microseconds.
2. **A bite-proof harness** — a registry of named mutation shapes, one per risk area,
   each shelling out to pytest with the mutation injected and asserting the named test
   goes red *for the named reason*. Catches the "asserts the wrong thing" shape that no
   AST rule can see, and turns the manual `test-plan.md` §6.2 ritual into automation.

Before either gate lands, the three genuinely status-only tests the audit finds — plus one
test whose assertion is narrower than its own docstring claims — are fixed, so the gate
ships green on a clean suite rather than green on a waiver list.

## Current State Analysis

**The gate mechanism already has a precedent in this repo.** `tests/test_coverage_scope.py`
is a meta-test that reads `pyproject.toml`, compares it against `INSTALLED_APPS`, and
fails with an actionable message — written because `lessons.md` #4 recorded `fail_under`
being silently defeated. `tests/test_ownership_matrix.py:312`
(`test_every_object_scoped_route_is_classified`) does the same for the route inventory,
asserting a hand-maintained declaration against reality so it cannot rot. Both live in
`tests/`, so `.github/workflows/deploy.yml`'s single `pytest --cov` step enforces them on
every PR with no extra job.

**The suite is already disciplined about the Risk #4 anti-pattern.** Research read 268
test functions across all 25 files and found the suite consistently pairs status
assertions with content, DB, or storage probes — several tests carry docstrings that name
the bare-status anti-pattern explicitly before guarding against it. One hardening pass has
already happened.

**What is missing is a mechanism, and a small residue.** Nothing prevents a third
status-only test from creeping in, and nothing captures the "prove it bites" practice.
Running a refined AST heuristic over the suite during planning found **5 findings out of a
129-test request-cycle population** — two that research named, and three it missed: one
genuinely status-only, one whose docstring overclaims what its assertion delivers, and one
a legitimate waiver:

| File:line | Test | Verdict |
|---|---|---|
| `tests/gpx/test_gpx_download.py:97` | `test_a_row_whose_file_is_gone_returns_404_not_500` | fix — only `== 404`; its own sibling at `:78` probes for leaked bytes and filename |
| `tests/gpx/test_gpx_upload.py:489` | `test_the_upload_url_does_not_serve_a_page_of_its_own` | fix — only `== 405`; no `Allow` header, no no-row-created probe |
| `tests/trips/test_trip_creation.py:191` | `test_put_is_rejected_as_a_disallowed_method` | fix — asserts only that `PUT` is absent from `Allow` (plus a DB probe); its docstring's closing sentence claims the assertion "pins the pair of verbs that stay open," a positive pin the body doesn't make — a narrower `lessons.md` #1 shape: a docstring overclaiming what its own assertion delivers |
| `tests/trips/test_trip_delete.py:110` | `test_deleted_trips_detail_url_returns_404` | fix — only `== 404`; never asserts the row is actually gone |
| `tests/test_media_storage.py:279` | `test_healthz_serves_a_cached_verdict_instead_of_reprobing` | **waiver** — the behavior under test genuinely *is* a status sequence (200 → 200 with the store broken → 500 after a cache clear); any added probe would be contrived |

**Full mutation testing is not available.** `pyproject.toml:6` pins
`requires-python = ">=3.14"` with no 3.13 fallback interpreter, and `mutmut`'s cache layer
has an unresolved Python 3.14 incompatibility (a `copy.deepcopy()` semantics change
breaking the Pony ORM query translator it uses internally), with "run under 3.13" as the
reported workaround. Independently of that, a full run reruns the whole suite once per
mutant — hundreds to low-thousands of runs for ~3,000 LOC — against a `gates` job whose
own inline comment (`deploy.yml:29`) budgets the *entire* sequence at roughly six minutes.

**The manual practice is real but unautomated.** `test-plan.md:166` ("Break the production
line it guards, confirm the cell goes red for the right reason, revert.") has a documented
track record — `50b6abf` and `4e712b7` are real commits, and
`context/archive/2026-08-29-testing-data-isolation-contract/reviews/impl-review.md:50-64`
records re-injecting the `document_root` leak and confirming the cells flipped. It has
never been captured as anything that runs again later.

## Desired End State

- `pyproject.toml` names a `bite_proof` marker and deselects it from the default run, so
  `uv run pytest` stays as fast as it is today.
- `uv run pytest --cov` (the CI Tests step) runs the assertion-strength audit. A new
  request-cycle test that asserts only a status code fails the suite with a message naming
  the file, the test, and what to add.
- A second CI step, `uv run pytest -m bite_proof`, injects each registered mutation shape
  and asserts the named guard test fails for the named reason. Deleting a guarded test, or
  removing the specific assertion its shape trips, turns that step red — a shape guards the
  one assertion it exercises, not every assertion in a multi-probe test.
- `test-plan.md` §5's "suite credibility gate" row is satisfied rather than planned, and
  §6.7/§6.8 record how to add a mutation shape.

**Verification**: `uv run pytest --cov` green; `uv run pytest -m bite_proof` green;
temporarily reverting any Phase 1 probe makes the audit red; temporarily deleting a
guarded test's key assertion makes the bite-proof step red.

### Key Discoveries

- `tests/test_coverage_scope.py:35` and `tests/test_ownership_matrix.py:312` — the
  asserted-inventory meta-test pattern to copy: a hand-maintained declaration checked
  against reality, so it cannot silently rot.
- `tests/test_settings_env.py` — the existing `sys.executable` subprocess idiom, and the
  precedent that a subprocess is sometimes the only honest way to observe a thing the
  in-process suite cannot.
- All five mutation targets are patchable module or class attributes, verified against the
  source: `gpx.signals.discard_file_by_key` (resolved as a module global inside
  `partial(...)` at receiver-call time), `trips.views.TripDetailView.get_queryset`,
  `trips.views.track_file_is_available`, `gpx.forms.MAX_GPX_FILE_BYTES`,
  `velo_log.urls.media_root_misconfiguration` (called as a module global by
  `_probe_health`).
- A naive "all asserts are status-only" rule flags 8 tests, 6 of them false positives. The
  two refinements that reduce it to 5 precise findings are **positional** (assertions
  *before* the request are setup guards, not behavior probes — this is what hides
  `test_gpx_download.py:97`, whose `assert track.file.name is not None` precedes the act)
  and **delegation-aware** (`route.probe(target, response)` in the ownership matrix is a
  probe; a call handed the response object counts).
- The audit's population must be **request-cycle tests only** — those that issue a call
  through the test client. `tests/gpx/test_gpx_parsing.py` has 12 tests with zero `assert`
  statements because `pytest.raises` *is* the assertion; a rule demanding asserts of them
  would be wrong.

## What We're NOT Doing

- **No mutmut, cosmic-ray, or mutpy**, and no spike of them. Blocked on Python 3.14 with
  no fallback interpreter, and the cost model does not fit a ~6-minute gates budget. If a
  3.13 interpreter or a confirmed 3.14 fix appears, that is a new change, not this one.
- **No AI-native assertion reviewer** (`test-plan.md` §4's optional row). A deterministic
  check answers this question, and §4's own "when NOT to use" line says not to put a
  judgement layer over one.
- **No change to any production module.** Every file this plan touches is under `tests/`,
  `pyproject.toml`, `.github/workflows/deploy.yml`, or `context/`. The mutations exist only
  inside a subprocess, applied to in-memory attributes; no source file is ever edited.
- **No new dependency.** `ast` and `subprocess` are stdlib.
- **No new risk areas, risk-map edits, or quality-gate redefinitions** — that is Lesson 1
  / `/10x-test-plan`.
- **No e2e, no Playwright, no browser scenarios.**
- **No attempt to catch every possible weak assertion.** The audit catches one precisely
  defined shape. Shapes it cannot see are what the bite-proof harness covers for the five
  risk areas, and nothing claims coverage beyond that.

## Implementation Approach

Two gates, built in dependency order, residue first.

The audit is a pure-AST meta-test in the same mould as `test_coverage_scope.py`: no
imports of application code, no database, no fixtures. It defines a population
(request-cycle tests), a rule (at least one post-act probe beyond the status code), and an
asserted waiver inventory that fails on a stale or unjustified entry.

The harness inverts the normal test relationship: it treats the suite as the thing under
test. A mutation registry declares, per shape, the attribute to patch, the replacement, the
guard test's node id, and a fragment expected in the failure output. `tests/conftest.py`
grows a hook that applies the shape named by `VELOLOG_MUTATION` — so the mutation is
inert in every normal run and active only in a subprocess the harness spawns. Each shape's
test asserts the subprocess reported *failures and no errors*, that the guard node is among
them, and that the expected fragment appears — the three conditions that separate "the
assertion bit" from "the mutation broke collection", which is the false-green
`test-plan.md` §6.2 warns about when it says "for the right reason".

## Critical Implementation Details

**Patch the name where it is *used*, not where it is defined.** `trips/views.py` does
`from gpx.availability import track_file_is_available`, so the live reference is
`trips.views.track_file_is_available`; patching `gpx.availability.track_file_is_available`
changes nothing the view sees and the harness would report a false green — the exact
failure mode this phase exists to prevent. The same applies to
`gpx.forms.MAX_GPX_FILE_BYTES` (imported by value from `gpx.constants`). Each registry
entry must therefore be verified to actually flip its guard test red; a shape whose guard
stays green is a broken shape, and the harness failing on it is correct behavior.

**Ordering and mechanism of mutation injection.** The patch must be in place before any
guarded code runs but after Django is configured. `pytest-django` sets up Django during
`pytest_configure`, so applying the patch there races app loading. Use a
session-scoped autouse fixture holding a `pytest.MonkeyPatch` context instead — it runs
after Django setup and unwinds cleanly. The hook must be a no-op when `VELOLOG_MUTATION`
is unset or empty, and must fail loudly (not skip) on an unrecognized shape name, so a
typo in the registry surfaces as an error rather than a vacuous pass.

**The subprocess must not inherit the default deselect.** Once `addopts` carries
`-m "not bite_proof"`, a naive `pytest <node-id>` subprocess inherits it. That happens to
be harmless for the five guard nodes (none is marked), but it also inherits `--cov` if
`addopts` ever grows it and would then write a competing coverage file. Neutralize
explicitly with `-o addopts=` and pass `-p no:cacheprovider`, so the child run is
reproducible and leaves nothing in `.pytest_cache`.

**A parametrized guard node fails more than once.** `trips.views.TripDetailView.get_queryset`
mutated to `Trip.objects.all()` turns several `trips:detail` cells of
`test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object` red at once. So the
harness asserts *at least one* failure and *zero* errors — never an exact failure count,
which would be brittle against a route or verb being added to `OBJECT_SCOPED_ROUTES`.

**No baseline run is needed, and adding one would be waste.** Every guard node is a real
test in the normal suite; if one were already failing or skipped, `pytest --cov` would
already be red. The harness may rely on that rather than paying a second subprocess per
shape to establish green.

**Cost budget.** Five shapes × one subprocess each, at roughly 2–4 s per cold Django boot,
is ~10–20 s locally — a separate step inside the `gates` job (Phase 3 §5), added to that
job's wall clock rather than sitting outside it; the CI figure is expected to run higher
than the local one, since each subprocess re-runs migrations on a GitHub Actions runner
slower than a local machine. Deselected locally by default, so the edit loop and any future
per-edit hook pay nothing. If a sixth shape is ever added, that budget is the thing to
re-check.

---

## Phase 1: Close the residue

### Overview

Add the missing post-act probe to the three genuinely status-only request-cycle tests, and
narrow a fourth test's `Allow` assertion to match what its docstring already claims, each
following the pattern `test-plan.md` §6.2 already prescribes ("a status code plus a state
or no-leak probe, always"). This must land before Phase 2 so the audit ships green against
a clean suite rather than green against a waiver list.

### Changes Required

#### 1. The download path's storage-miss test

**File**: `tests/gpx/test_gpx_download.py`

**Intent**: `test_a_row_whose_file_is_gone_returns_404_not_500` (line 97) proves the status
but not that the answer is clean. Its sibling `test_another_users_track_returns_404_not_403`
(line 78) already carries the right pattern and a docstring explaining it. Give this test
the equivalent probes, plus the assertion its own docstring implies but never makes — that
the surviving row is not silently deleted by the failed read.

**Contract**: after the request, assert the response body leaks neither the stored storage
key nor `original_filename`, and that `GpxTrack.objects.filter(pk=track.pk).exists()` is
still true. The `assert track.file.name is not None` on line 108 stays where it is — it is
a type-narrowing setup guard, not a behavior probe, and the audit in Phase 2 must go on
classifying it as such.

#### 2. The upload endpoint's method-narrowing test

**File**: `tests/gpx/test_gpx_upload.py`

**Intent**: `test_the_upload_url_does_not_serve_a_page_of_its_own` (line 489) asserts only
`405`. `GpxUploadView.http_method_names = ["post"]` is the thing under test, and the `Allow`
header is what makes the narrowing observable. Mirror
`tests/trips/test_trip_edit.py::test_head_and_options_are_served_like_the_page_they_describe`,
which already asserts against `Allow`.

**Contract**: assert `"GET" not in response.headers["Allow"]` and that `"POST"` is present,
and that the GET created no `GpxTrack` row.

#### 3. The create page's disallowed-verb test

**File**: `tests/trips/test_trip_creation.py`

**Intent**: `test_put_is_rejected_as_a_disallowed_method` (line 191) already asserts
`"PUT" not in ...headers["Allow"]` and `not Trip.objects.exists()`. Its docstring's closing
sentence claims the assertion "pins the pair of verbs that stay open" — a positive pin
(`Allow` is exactly `HEAD, OPTIONS`) the negative-only check doesn't deliver. This is a
narrower `lessons.md` #1 shape: the docstring overclaims, not a test that's silent. Make
the assertion match the docstring's claim.

**Contract**: replace the negative-only check with a positive assertion that
`response.headers["Allow"]` equals exactly the verbs `TripCreateView.http_method_names`
declares (`GET`, `POST`, `HEAD`, `OPTIONS`); the existing `not Trip.objects.exists()` DB
probe already covers the docstring's other concern (`ProcessFormView.put` re-entering
`post()`) and needs no change.

#### 4. The post-delete detail-URL test

**File**: `tests/trips/test_trip_delete.py`

**Intent**: `test_deleted_trips_detail_url_returns_404` (line 110) asserts the URL 404s but
never that the delete it depends on actually happened — the test's whole premise is
unasserted.

**Contract**: assert `not Trip.objects.filter(pk=trip.pk).exists()` after the delete POST
and before or after the detail GET.

### Success Criteria

#### Automated Verification

- Full suite passes: `uv run pytest --cov`
- The four touched files pass individually: `uv run pytest tests/gpx/test_gpx_download.py tests/gpx/test_gpx_upload.py tests/trips/test_trip_creation.py tests/trips/test_trip_delete.py -v`
- Lint, format, import order, typing: `uv run ruff check . && uv run black --check . && uv run isort --check-only . && uv run mypy .`

#### Manual Verification

- Each new assertion is confirmed to bite: break the production line it guards (narrow or
  widen `http_method_names`, remove the owner scoping, skip the row delete), confirm the
  new assertion — not merely the pre-existing status assertion — is the one that fails,
  then revert. This is `test-plan.md` §6.2's ritual, and Phase 3 is what stops it having to
  be remembered.
- `test_put_is_rejected_as_a_disallowed_method`'s docstring's positive-pin claim now matches
  an assertion the body actually makes (previously it only asserted `PUT`'s absence).

**Implementation Note**: After completing this phase and all automated verification
passes, pause for manual confirmation before proceeding.

---

## Phase 2: The assertion-strength audit

### Overview

A deterministic meta-test that fails the suite when a request-cycle test asserts nothing
beyond a status code. Pure `ast` over the files in `tests/`; no application imports, no
database, no fixtures.

### Changes Required

#### 1. The audit meta-test

**File**: `tests/test_assertion_strength.py` (new)

**Intent**: Make `lessons.md` #1 impossible to reintroduce silently. The module docstring
must state why the check exists (a status-only assertion passes against a view that read,
wrote or deleted the object and refused afterwards) and why the population is scoped to
request-cycle tests, so the next reader does not "fix" it by demanding asserts of the
parsing tests.

**Contract**: three definitions and one assertion, all in this module.

- **Population** — a test function is in scope when it issues a request through the test
  client: a call to `.get/.post/.put/.patch/.delete/.head/.options/.trace/.generic` on a
  name containing `client`, either directly or through a module-local helper (resolve one
  level; `tests/test_ownership_matrix.py`'s `_issue` is the case that needs it). Everything
  else — unit tests, parsing tests, settings tests — is out of scope and unexamined.
- **Rule** — at or after the last such call in the function, there must be at least one
  *behavior probe*: an `assert` whose expression references anything beyond `status_code`
  and integer literals; or a `with` block (`pytest.raises`, `django_assert_num_queries`);
  or a call handed the response object as an argument (`route.probe(target, response)`); or
  a call to a module-local helper that itself contains a non-status assertion. Assertions
  *before* the act are setup guards and are deliberately not counted — this is what makes
  the rule catch `test_gpx_download.py:97`. "At or after" (not strictly after) covers the
  suite's fused idiom, where the client call sits inside the assert expression itself
  (`assert "PUT" not in auth_client.options(...).headers["Allow"]`) — the statement is both
  the act and the probe, and the eight sites shaped like this (`test_trip_creation.py:207`,
  `test_trip_delete.py:245`, `test_trip_edit.py:257`, five in `test_media_storage.py`) must
  not be flagged just because nothing follows them.
- **Waiver inventory** — a module-level tuple of `(relative path, test name, reason)`.
  Exactly one entry at first:
  `tests/test_media_storage.py`, `test_healthz_serves_a_cached_verdict_instead_of_reprobing`,
  because the behavior under test genuinely *is* a status sequence — 200, then 200 with the
  storage backend broken, then 500 after a cache clear — and the middle 200 is the whole
  proof that the cache short-circuited the probe.
- The assertion fails on **findings not waived** *and*, separately, on **waivers that are
  stale** — a waived test that no longer exists, or one that now passes the rule. This is
  the `OBJECT_SCOPED_ROUTES` guarantee (`test_ownership_matrix.py:312`): the declaration is
  checked against reality, so it cannot rot silently. Both messages name the file, the test,
  and what to do.

The failure message for a finding should tell the implementer what to add, not just what
is wrong — the audit's value is that a future agent reading its output can fix the test
without reading this plan. Assert the population is non-empty, mirroring
`test_coverage_scope.py:47`'s guard against a heuristic that silently matches nothing.

### Success Criteria

#### Automated Verification

- Audit passes on the post-Phase-1 suite: `uv run pytest tests/test_assertion_strength.py -v`
- Full suite passes: `uv run pytest --cov`
- Lint, format, import order, typing: `uv run ruff check . && uv run black --check . && uv run isort --check-only . && uv run mypy .`

#### Manual Verification

- The audit bites: temporarily revert one Phase 1 probe, confirm the audit fails naming
  that exact test, then restore.
- The audit's precision is confirmed: temporarily empty the waiver inventory and confirm it
  reports exactly the one healthz test and nothing else — no false positives against the
  parsing tests, the ownership matrix's delegated probes, or the setup guard on
  `test_gpx_download.py:108`.
- Stale-waiver detection bites: temporarily add a waiver for a test that already passes the
  rule, confirm the audit fails, then remove it.

**Implementation Note**: After completing this phase and all automated verification
passes, pause for manual confirmation before proceeding.

---

## Phase 3: The bite-proof harness and its wiring

### Overview

Turn `test-plan.md` §6.2's manual ritual into automation: five named mutation shapes, one
per risk area, each proving a named guard test goes red for a named reason. Marked, so the
default local run is unchanged; wired as its own CI step, so every PR pays the ~10–20 s.

### Changes Required

#### 1. The mutation registry

**File**: `tests/mutations.py` (new)

**Intent**: Declare the shapes as data, importable without applying anything, so both the
`conftest.py` hook and the harness read one source of truth. The module docstring states the
contract: a shape is a claim that breaking *this* production behavior makes *that* test
fail, and a shape whose guard stays green is a broken shape.

**Contract**: a frozen dataclass and a module-level tuple of instances. Fields per shape:
a stable `name` (the `VELOLOG_MUTATION` value), the `risk` it covers (matching a
`test-plan.md` §2 row), the import target as a `(module path, attribute name)` pair, a
factory producing the replacement value, the guard test's pytest node id, and a `fragment`
expected in the failure output. The five shapes:

| Name | Risk | Patch target | Replacement | Guard node |
|---|---|---|---|---|
| `unscoped_trip_detail_queryset` | #2 | `trips.views.TripDetailView.get_queryset` | returns `Trip.objects.all()` | `tests/test_ownership_matrix.py::test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object` |
| `no_op_file_discard` | #1 | `gpx.signals.discard_file_by_key` | returns `None` without deleting | `tests/gpx/test_gpx_signals.py::test_a_trip_queryset_cascade_removes_the_track_files_it_never_loaded` |
| `file_always_available` | #3 | `trips.views.track_file_is_available` | returns `True` | `tests/trips/test_trip_detail.py::test_a_rider_sees_a_deliberate_marker_when_the_track_file_is_missing` |
| `no_upload_size_cap` | #5 | `gpx.forms.MAX_GPX_FILE_BYTES` | a value above any fixture | `tests/gpx/test_gpx_upload.py::test_a_file_over_the_size_cap_is_rejected_with_a_visible_message` |
| `media_guard_always_clean` | #7 | `velo_log.urls.media_root_misconfiguration` | returns `None` | `tests/test_media_storage.py::test_healthz_fails_when_media_root_is_inside_base_dir_and_debug_is_false` |

Each shape needs a one-line comment naming *why the patch target is that module* where the
name is imported rather than defined — `trips.views.track_file_is_available` and
`gpx.forms.MAX_GPX_FILE_BYTES` are both re-exported names, and patching the defining module
would silently do nothing.

`fragment` is the one condition in "red for the right reason" (§3, below) that actually
discriminates the guard test's own assertion failing from *anything* failing — the other
three (zero errors, ≥1 failure, guard node named) are near-tautological once the subprocess
runs only that node. A `fragment` must therefore be a distinctive substring of the guard
assertion's own message or expression, never a generic pytest token (`"AssertionError"`,
`"assert"`, `"FAILED"`) that would match any failure vacuously.

#### 2. The injection hook

**File**: `tests/conftest.py`

**Intent**: Apply the shape named by `VELOLOG_MUTATION` for the whole session, and nothing
at all when the variable is absent — which is every normal run, local and CI.

**Contract**: a session-scoped autouse fixture that reads the environment variable,
resolves the name against the registry, and applies the replacement through a
`pytest.MonkeyPatch` context yielded for the session. An unset or empty value is a no-op;
an unrecognized name raises rather than skips, so a registry typo surfaces. Session-scoped
rather than `pytest_configure`, because the patch must land after `pytest-django` has
configured Django.

#### 3. The harness

**File**: `tests/test_suite_bites.py` (new)

**Intent**: For each shape, prove the suite bites. This is the automated form of the ritual
`test-plan.md:166` describes and `50b6abf` / `4e712b7` record being done by hand.

**Contract**: one parametrized test over the registry, marked `bite_proof`, plus an
inventory assertion.

- Each case runs `sys.executable -m pytest <guard node>` in a subprocess with
  `VELOLOG_MUTATION=<name>` in the environment, `-o addopts=` to neutralize the default
  deselect, `-p no:cacheprovider`, and `--no-header -q`. It asserts **zero errors**, **at
  least one failure**, the guard node id present in the output, and the shape's expected
  `fragment` present. All four together are what "red for the right reason" means: an
  errors-only run means the mutation broke collection and proved nothing.
- An inventory assertion (unmarked, so it runs in the normal suite) asserts every
  `test-plan.md` §2 risk this phase claims to cover has at least one shape, and that every
  shape's guard node id resolves to a test that exists — resolved by reusing Phase 2's AST
  parse of `tests/` (the module that already extracts every test function name for
  `test_assertion_strength.py`), never `pytest --collect-only`: a whole-suite collection run
  inside the default suite is exactly the subprocess cost the marker and `addopts` in change
  4 below exist to keep out of the local edit loop.
- On failure the message must say which is more likely: the guard test was weakened, or the
  patch target moved. Those are the two real causes and they have opposite fixes.

#### 4. Marker registration and default deselect

**File**: `pyproject.toml`

**Intent**: Register the marker so it is not an unknown-mark warning, and keep the
subprocess cost out of every local run and any future per-edit hook — the layering
`CLAUDE.md` prescribes.

**Contract**: under `[tool.pytest.ini_options]`, add a `markers` entry describing
`bite_proof`, and `addopts = '-m "not bite_proof"'`. Note the interaction: `pytest -m bite_proof`
on the command line overrides `addopts`' `-m`, which is what makes the CI step work; this is
worth a comment, since the two `-m` flags looking contradictory is the first thing a reader
will question.

#### 5. The CI step

**File**: `.github/workflows/deploy.yml`

**Intent**: Satisfy `test-plan.md` §5's "CI on PR, required" for the suite credibility gate.

**Contract**: a new step after `Tests`, named distinctly (e.g. `Suite credibility`), running
`uv run pytest -m bite_proof`. No `--cov` — the harness spawns pytest subprocesses and a
coverage context would fight itself. Placed after `Tests` deliberately: if the suite itself
is red, which test bites is not yet the interesting question, and the existing step order in
this workflow is already load-bearing and commented as such.

### Success Criteria

#### Automated Verification

- Harness passes: `uv run pytest -m bite_proof -v`
- Default run still excludes it and is unchanged: `uv run pytest --cov`
- The inventory assertion runs in the default suite: `uv run pytest tests/test_suite_bites.py --collect-only -q`
- Lint, format, import order, typing: `uv run ruff check . && uv run black --check . && uv run isort --check-only . && uv run mypy .`
- CI-equivalence with no `.env` present: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- Same, for the harness: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest -m bite_proof`

#### Manual Verification

- Each of the five shapes is confirmed to actually flip its guard: run the harness and
  read the captured output for each case, confirming the failure is the guard's own
  assertion and not a collection or import error.
- The harness bites in the other direction: temporarily delete the key assertion from one
  guard test, confirm that shape's case fails with the "guard was weakened" message, then
  restore.
- A false-green is caught: temporarily point one shape at the *defining* module instead of
  the importing one (`gpx.availability.track_file_is_available`), confirm the harness fails
  rather than passing, then restore. This is the specific trap the registry's comments warn
  about.
- Harness wall-clock is confirmed at roughly 10–20 s, within the budget stated in Critical
  Implementation Details.
- Each shape's `fragment` is confirmed to discriminate: it is absent from that guard node's
  *unmutated* run output (`sys.executable -m pytest <guard node> -o addopts= -q`), so a
  generic pytest token could not have passed the check vacuously.

**Implementation Note**: After completing this phase and all automated verification
passes, pause for manual confirmation before proceeding.

---

## Phase 4: Documentation

### Overview

Record the gate where the next reader and the next agent will look: the test plan's gate
table and cookbook, `AGENTS.md`, and `lessons.md`.

### Changes Required

#### 1. Test plan — gate row, phase status, phase notes, cookbook

**File**: `context/foundation/test-plan.md`

**Intent**: §5's "suite credibility gate" row currently promises something that does not
exist; §3 row 5 is mid-flight; §6.7 needs this phase's notes, in the same shape Phases
1–4 already use.

**Contract**: five edits.
- §3 row 5 Status → `complete`; leave the change folder pointing at
  `context/changes/testing-gate-credibility/` — the archived path doesn't exist until
  `/10x-archive` runs after this phase, and `/10x-archive` is what updates it then.
- §5 "suite credibility gate" row — keep "required after §3 Phase 5", and name what
  satisfies it: the audit inside `pytest --cov` plus the `Suite credibility` CI step.
- §5's ownership-matrix row, which currently says `deploy.yml` "already runs `pytest --cov`
  … so no new CI job was needed" — amend it, since this phase adds a second `pytest` step
  (`Suite credibility`, running `pytest -m bite_proof`) to that same job.
- §6.7 — a "Phase 5 — Gate credibility" block. It must record, at minimum: that the
  premise was *partly* true here for the first time in the rollout (research found two
  status-only tests; a mechanized heuristic found five total — one genuinely status-only
  that research missed, one whose docstring overclaimed a positive `Allow` pin its
  negative-only assertion didn't deliver, and one legitimate waiver — the discovery that a
  human read of 268 tests missed three of five a 60-line AST rule caught); that mutation
  testing was ruled out on Python 3.14 grounds and cost, not preference; and the
  patch-the-imported-name trap.
- A new §6.8, "Adding a mutation shape to the credibility gate" — location, naming, the
  reference shape to copy, how to run it, and the requirement to verify the shape actually
  flips its guard before committing it. Must state two limitations explicitly: a shape
  guards the one assertion its mutation trips, not every assertion in the guard test — a
  multi-probe guard test (e.g. `test_a_second_rider_is_refused_on_every_verb_that_reaches_
  the_object`'s eight delegated `route.probe()` calls) is only as protected as the shapes
  that exercise each of its probes; and `fragment` must be a distinctive substring of the
  guard assertion's own message or expression, verified absent from that guard node's
  unmutated run output, never a generic pytest token.

#### 2. Agent-facing repository guide

**File**: `AGENTS.md`

**Intent**: The Testing section describes the suite and the CI gate order; both change here.
`lessons.md` #5 is explicit that a stale `AGENTS.md` actively misdirects the next agent.

**Contract**: extend the Testing section with the two new gates — the audit's rule and where
its waiver list lives, and the `bite_proof` marker being deselected by default with the
command to run it. Update the `.github/workflows/deploy.yml` gate sequence in the
Commits & Git Workflow section to include the new step, and while that sentence is open,
add the second vendored-asset integrity check (`deploy.yml` runs one for Leaflet and one for
Bootstrap; today's sentence names only one). Pair the existing CI-equivalence command
(`SECRET_KEY=… uv run pytest --cov`) with its `-m bite_proof` counterpart — once
`addopts` deselects the marker, the bare command alone no longer reproduces what CI runs.

#### 3. Lessons

**File**: `context/foundation/lessons.md`

**Intent**: Capture the class of defect this phase found, which #1 does not quite cover: #1
is "a test whose name claims an assertion must actually make it"; the new instance is a
*docstring* claiming a stronger assertion (a positive `Allow` pin) than the body's
negative-only check delivers, in a test whose name was accurate throughout.

**Contract**: one new numbered entry — a docstring that describes an assertion is a claim
the body must fully honour, not partially, sourced to
`test_put_is_rejected_as_a_disallowed_method`, with the reason: the docstring is what the
next reader trusts instead of re-deriving the assertions, so an overclaiming docstring is
worse than an absent one. Cross-reference #1 and the new gate.

### Success Criteria

#### Automated Verification

- Full suite passes: `uv run pytest --cov`
- Harness passes: `uv run pytest -m bite_proof`
- All quality gates: `/python-quality-gates`

#### Manual Verification

- §6.8 is followable: a reader who has never seen this change could add a sixth shape from
  it alone.
- No document claims a gate, path, or command that does not exist — every command in the
  edited sections is one that was actually run in Phases 1–3.

**Implementation Note**: This is the final phase. After it, run `/10x-impl-review`, then
`create-pr`.

---

## Testing Strategy

This change *is* tests, so the layers invert: the suite is the system under test.

### Unit tests

- The audit's own classification logic is exercised by the suite it reads — its Phase 2
  manual verification (empty the waiver list, confirm exactly one finding) is the
  precision test, and the post-Phase-1 suite is the fixture.
- Key edge cases the audit must get right, each already present in the suite as a live
  example: a test with zero `assert` statements whose `pytest.raises` is the assertion
  (`tests/gpx/test_gpx_parsing.py`); a test delegating its probe to a call handed the
  response (`tests/test_ownership_matrix.py`); a test whose only non-status assertion
  precedes the request (`tests/gpx/test_gpx_download.py:108`); a test issuing its request
  through a module-local helper (`_issue` in the ownership matrix).

### Integration tests

- The bite-proof harness is the integration test: five real pytest runs against real
  mutated behavior, asserting the real guard tests fail.

### Manual Testing Steps

1. Break each Phase 1 probe in turn; confirm the audit names that test; revert.
2. Empty the waiver inventory; confirm exactly one finding and no false positives; restore.
3. Delete a guard test's key assertion; confirm the matching shape's harness case fails
   with the "guard was weakened" message; restore.
4. Repoint one shape at its defining module rather than the importing one; confirm the
   harness fails rather than silently passing; restore.
5. Time `uv run pytest -m bite_proof` and confirm it sits in the 10–20 s range.

## Performance Considerations

The audit parses ~25 files with `ast` once — microseconds, invisible inside a suite that
collects 331 tests in 0.30 s. The harness costs one cold Django boot per shape (~2–4 s
each, ~10–20 s total) and is the only reason a marker and a default deselect exist: it must
not enter the local edit loop, the pre-commit layer, or any per-edit hook. Five shapes is
the budgeted size; a sixth is the point at which to re-measure rather than assume.

## Migration Notes

Not applicable — no model, schema, or stored data changes. `addopts` changing the default
`pytest` invocation is the only behavior change a contributor will notice, and `AGENTS.md`
plus §6.8 are where that is recorded.

## References

- Research: `context/changes/testing-gate-credibility/research.md`
- Test plan: `context/foundation/test-plan.md` §2 (Risk #4), §4 (stack), §5 (gate row),
  §6.2 ("prove the test bites")
- Lessons: `context/foundation/lessons.md` #1, #3, #4, #5
- Meta-test pattern to copy: `tests/test_coverage_scope.py:35`,
  `tests/test_ownership_matrix.py:312`
- Subprocess idiom precedent: `tests/test_settings_env.py`
- Prior manual "prove it bites" runs: `50b6abf`, `4e712b7`,
  `context/archive/2026-08-29-testing-data-isolation-contract/reviews/impl-review.md:50-64`
- CI gate sequence and its stated budget: `.github/workflows/deploy.yml:15-72` (comment at
  line 29)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Close the residue

#### Automated

- [x] 1.1 Full suite passes: `uv run pytest --cov` — 0d19821
- [x] 1.2 The four touched files pass individually — 0d19821
- [x] 1.3 Lint, format, import order, typing — 0d19821

#### Manual

- [x] 1.4 Each new assertion confirmed to bite, then reverted — 0d19821
- [x] 1.5 `test_put_is_rejected_as_a_disallowed_method`'s docstring matches its body — 0d19821

### Phase 2: The assertion-strength audit

#### Automated

- [x] 2.1 Audit passes on the post-Phase-1 suite
- [x] 2.2 Full suite passes: `uv run pytest --cov`
- [x] 2.3 Lint, format, import order, typing

#### Manual

- [x] 2.4 Audit bites: a reverted Phase 1 probe makes it fail by name
- [x] 2.5 Precision confirmed: empty waiver list yields exactly the one healthz finding
- [x] 2.6 Stale-waiver detection bites

### Phase 3: The bite-proof harness and its wiring

#### Automated

- [ ] 3.1 Harness passes: `uv run pytest -m bite_proof -v`
- [ ] 3.2 Default run excludes it and is unchanged
- [ ] 3.3 Inventory assertion runs in the default suite
- [ ] 3.4 Lint, format, import order, typing
- [ ] 3.5 CI-equivalence run with no `.env` present, both invocations

#### Manual

- [ ] 3.6 All five shapes confirmed to flip their guard for the right reason
- [ ] 3.7 Harness bites when a guard test is weakened
- [ ] 3.8 A shape pointed at the defining module fails rather than passing
- [ ] 3.9 Harness wall-clock within the 10–20 s budget

### Phase 4: Documentation

#### Automated

- [ ] 4.1 Full suite passes: `uv run pytest --cov`
- [ ] 4.2 Harness passes: `uv run pytest -m bite_proof`
- [ ] 4.3 All quality gates: `/python-quality-gates`

#### Manual

- [ ] 4.4 §6.8 is followable for adding a sixth shape
- [ ] 4.5 No document claims a gate, path, or command that does not exist
