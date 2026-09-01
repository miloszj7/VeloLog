# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-08-31

## 1. Strategy

Tests follow three non-negotiable principles for this project:

1. **Cost × signal.** The cheapest test that gives a real signal for the
   risk wins. Do not promote to e2e because e2e "feels safer." Do not put a
   vision model on top of a deterministic visual diff that already catches
   the regression.
2. **User concerns are first-class evidence.** Risks anchored in "the owner
   is worried about X, and the failure would surface somewhere in `<area>`"
   carry the same weight as PRD lines or hot-spot data.
3. **Risks are scenarios, not code locations.** This plan documents *what
   could fail* and *why we believe it's likely* — drawn from documents,
   interview, and codebase *signal* (churn, structure, test base). It does
   NOT claim to know which line owns the failure. That knowledge is
   produced by `/10x-research` during each rollout phase. If the plan and
   research disagree about where the failure lives, research is the
   ground truth.

Hot-spot scope used for likelihood weighting: `accounts/`, `trips/`, `gpx/`,
`velo_log/` — excluding `context/`, `tests/`, migrations, docs,
`staticfiles/`, and vendored assets. 75 commits in the 30 days to
2026-08-29; ample signal.

## 2. Risk Map

The top failure scenarios this project must protect against, ordered by
risk = impact × likelihood. Risks are failure scenarios in user / business
terms, not test names. The Source column cites the *evidence that surfaced
this risk* — never a specific file as "where the failure lives" (that is
research's job, see §1 principle #3).

| # | Risk (failure scenario) | Impact | Likelihood | Source (evidence — not anchor) |
|---|---|---|---|---|
| 1 | Deleting or replacing a trip's track leaves its file on the volume forever — or removes a file that is still in use | High | High | interview Q2 (already burned here), interview Q3 (self-reported lowest-confidence area); roadmap E-11; `lessons.md` #10; hot-spot dir `gpx/` — 52 file-touches/30d |
| 2 | A logged-in user reaches another user's trip, or downloads their track file | High | Medium | PRD Guardrails ("under any circumstance") and Access Control; interview Q4; hot-spot dirs `trips/` — 26/30d, `gpx/` — 52/30d |
| 3 | A trip's row survives but its track becomes unreachable — the page still shows statistics while the file is gone, and nobody notices for months | High | Medium | PRD Guardrail "Data never lost"; interview Q1 (the failure is *silent*, which is what makes it the top fear); hot-spot dir `gpx/` — 52/30d |
| 4 | A regression reaches production with every gate green | High | Medium | `lessons.md` #1, #3, #4 — all three record this having already happened; roadmap E-01, E-02 |
| 5 | A malformed or hostile upload returns a server error instead of a clean rejection, and may leave a row or a file behind | Medium | Medium | PRD FR-004; PRD Non-Functional Requirements ("silent failures … are not acceptable"); hot-spot dir `gpx/` — 52/30d |
| 6 | The trip detail page breaks instead of degrading — no track, absent statistics, or an unrenderable map yields a blank or broken page | Medium | Medium | PRD Business Logic (a trip with no file is a valid empty draft); US-01 acceptance criteria; PRD Non-Functional Requirements; hot-spot dirs `trips/templates/trips/` — 22/30d, `trips/` — 26/30d |
| 7 | A deployment stores uploads somewhere the next redeploy erases | High | Low | `AGENTS.md` Hard Rules; roadmap E-05 (the restore drill found three documented steps that reported success and recovered nothing); PRD Guardrail "Data never lost" |

Risk #2 is the abuse-lens row: authorization/ownership, not merely
authentication. Risk #7 is High × Low — the platform itself is not testable
from pytest, but the *guard* that refuses a misconfigured media root is, and
that guard is the only thing standing between the owner and Risk #1's
consequence at deploy scale.

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|---|---|---|---|---|---|
| #1 | A trip removed through any path leaves nothing behind on the volume, and a surviving trip's file is never collected | That a passing deletion test proves deletion at all — a post-commit side effect asserted before the commit passes vacuously | Every path that removes or supersedes a track row, and which of them bypass model signals entirely | integration | Asserting a receiver fired instead of asserting the file is gone |
| #2 | Every trip and track route returns not-found to a second logged-in user, not only to an anonymous one | That anonymous-redirect coverage implies ownership coverage — they are different failures with different causes | The full route inventory, and whether not-found or forbidden is the contract (not-found avoids disclosing existence) | integration, parametrized over routes × actors | Testing three routes and declaring the guardrail covered |
| #3 | A trip whose file is missing from storage renders a deliberate error state and never claims success | That statistics rendering means the file is present — statistics are stored columns, deliberately decoupled from the file | What the detail view and the download path do when storage misses | integration with a storage-miss fixture | Only exercising the happy path where row and file agree |
| #4 | The suite goes red when the behavior a test names is actually broken | Coverage percentage as evidence of protection — `lessons.md` #3 and #4 record it being exactly the opposite | Which existing tests assert only a status code, and what a cost-proportionate credibility gate looks like for a solo repo | a gate (mutation-style spot check or assertion audit) | Adding tests to raise coverage rather than to catch a named regression |
| #5 | Empty, truncated, non-GPX, and oversized uploads all yield the user-facing error state, with no row and no file left behind | That "the parser raised" equals "the request was handled" — the debris question is separate from the rejection question | The rejection contract and where the transaction boundary sits relative to the storage write | unit for parsing, integration for the request | Copying the expected message out of the implementation under test (**oracle problem**) |
| #6 | A trip with no track, and one with absent statistics, both render a deliberate empty state | That a 200 means the page is usable — the requirement forbids a blank page, not merely a server error | Which template branches exist for an absent map and absent statistics | integration asserting the empty-state marker | Status-code-only assertions — `lessons.md` #1 verbatim |
| #7 | A misconfigured media root is refused rather than silently accepted | That the check works because it exists — the restore drill found three documented steps that reported success and did nothing | The guard's actual trigger conditions, and what the suite must prove with no environment file present | unit on settings resolution, integration on the probe | Testing the hosting platform instead of testing the guard |

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right through the values below; the
orchestrator updates Status as artifacts appear on disk.

| # | Phase name | Goal (one line) | Risks covered | Test types | Status | Change folder |
|---|---|---|---|---|---|---|
| 1 | Data-isolation contract | Prove no route lets one user read, modify, or delete another user's trip or track | #2 | integration (route × actor matrix) | complete | `context/changes/testing-data-isolation-contract/` |
| 2 | File lifecycle and storage/row consistency | Prove every delete and replace path reclaims exactly what it should — asserted after commit, not before | #1, #3 | integration (commit-callback aware), management-command | complete | `context/archive/2026-08-30-testing-file-lifecycle-storage-consistency/` |
| 3 | Rejection and degradation | Prove bad input and absent data produce deliberate states, never a server error or a blank page | #5, #6 | unit (parsing) + integration (view/template) | complete | `context/archive/2026-08-30-testing-rejection-and-degradation/` |
| 4 | Environment guard | Prove a media-root misconfiguration is refused rather than silently accepted | #7 | unit + integration on the health probe | complete | `context/archive/2026-08-31-testing-environment-guard/` |
| 5 | Gate credibility | Prove the suite actually goes red when the behavior it names breaks | #4 | gate (mutation-style or assertion audit) | complete | `context/changes/testing-gate-credibility/` |

Ordering rationale: Risk #1 is the only High × High row, yet Phase 1 goes to
Risk #2 first. Phase 1 is the cheapest phase, the most likely to surface a
live gap, and it depends on nothing but the route list — whereas Phase 2
cannot be written well until research has grounded the file-lifecycle
machinery. Phase 5 is last because gate credibility cannot be measured
before the tests it would measure exist.

## 4. Stack

The classic test base for this project. AI-native tools (if any) carry a
`checked:` date so future readers can see which lines need re-verification.

| Layer | Tool | Version | Notes |
|---|---|---|---|
| unit + integration | pytest + pytest-django | 9.1.1 / 4.14.0 | `testpaths = ["tests"]`; 25 test files across `tests/accounts/`, `tests/trips/`, `tests/gpx/` and the root. Test base profile: **meaningful** — this rollout closes gaps, it does not bootstrap |
| coverage | pytest-cov | 7.1.0 | Over `accounts`, `trips`, `gpx`, `velo_log`; `fail_under = 80`, `branch = true` |
| framework under test | Django | 6.0.5 | SQLite; suite runs in-memory, and must pass with no environment file present |
| domain parsing | gpxpy | 1.6.2 | Two of its calls answer `0` where a caller would read "not recorded" — presence needs its own probe |
| post-commit side effects | `django_capture_on_commit_callbacks` | pytest-django 4.14.0 | The fixture that makes Phase 2 possible; without `execute=True` a deletion assertion passes while proving nothing. checked: 2026-08-29 |
| e2e | none yet | — | Not proposed by any rollout phase. The primary flow is a small number of server-rendered pages; Phases 1–3 reach every step of it at the integration layer for a fraction of the cost |
| (optional) AI-native | assertion-audit reviewer — checked: 2026-08-29 | n/a | Candidate for Phase 5 only, weighed against classic mutation testing. **When NOT to use**: anywhere a deterministic check already answers the question. It is a judgement layer over test *quality*, never a substitute for an assertion |

**Stack grounding tools (current session):**
- Docs: Context7 — verified the `django_capture_on_commit_callbacks` contract (`using`, `execute`, and its incompatibility with `transaction=True`) against pytest-django's own `docs/helpers.md` before relying on it in §2 and §3; checked: 2026-08-29
- Search: Exa.ai — available, not used. Every stack fact needed came from the lockfile or primary docs; checked: 2026-08-29
- Runtime/browser: Playwright MCP — **not available in current session**. Browser automation exists only as a local `claude-in-chrome` skill, which is interactive and not a CI gate. This is one reason no rollout phase proposes e2e; checked: 2026-08-29
- Provider/platform: Linear MCP available (issue tracking only, no quality-gate relevance). No GitHub MCP in session — CI gate facts were read from the workflow file and `AGENTS.md`; checked: 2026-08-29

## 5. Quality Gates

The full set of gates that must pass before a change reaches production.
"Required after §3 Phase `<N>`" means the gate is enforced once that rollout
phase lands; before that, the gate is planned.

| Gate | Where | Required? | Catches |
|---|---|---|---|
| vendored-asset integrity | CI (`gates`, first step) | required | a tampered or drifted vendored asset, before anything is installed |
| lint + format + import order | local + CI | required | syntactic and style drift |
| strict typing | local + CI | required | type drift |
| migration guard | CI | required | a model change shipped without its migration — invisible to every other gate |
| collectstatic | CI | required | an unresolvable static reference; must precede the test step, which skips itself without a manifest |
| unit + integration | local + CI | required | logic regressions |
| ownership/isolation matrix | CI | required | one user reaching another user's data. Satisfied by `tests/test_ownership_matrix.py` existing in the suite — `.github/workflows/deploy.yml`'s `gates` job runs two `pytest` steps on every PR to `master` and every push to it: `Tests` (`pytest --cov`) and, since §3 Phase 5, `Suite credibility` (`pytest -m bite_proof`) — this row means "the matrix exists in the suite", not a separate job. The gate has teeth because the module asserts its own inventory against the URLconf: a new `<int:pk>` route under `trips` or `gpx` fails the suite until it is classified |
| post-commit side-effect assertions | CI | required after §3 Phase 2 | file-lifecycle regressions that a pre-commit assertion cannot see |
| environment-guard check | CI | required after §3 Phase 4 | a media-root misconfiguration reaching a deploy |
| suite credibility gate | CI on PR | required after §3 Phase 5 | tests that stay green when the behavior they name is broken. Two parts: the assertion-strength audit (`tests/test_assertion_strength.py`, inside `pytest --cov`) fails a request-cycle test that asserts only a status code; the bite-proof harness (`tests/mutations.py` + `tests/test_suite_bites.py`, the `Suite credibility` step running `pytest -m bite_proof`) proves five named mutation shapes each flip a named guard test red for a named reason. See §6.7 Phase 5 and §6.8 |
| e2e on critical flows | — | not planned | see §4: no phase proposes it; the primary flow is covered at the integration layer |
| pre-prod smoke | between merge and production | optional | environment-specific failures the health probe would report |

## 6. Cookbook Patterns

How to add new tests in this project. Each sub-section is filled in once
the relevant rollout phase ships; before that, the sub-section reads
"TBD — see §3 Phase `<N>`."

### 6.1 Adding a unit test

- **Location**: `tests/<app>/`, mirroring the app package under test.
- **Naming**: `test_<behavior>.py`.
- **Reference test**: `test_an_empty_upload_is_a_syntax_error` in `tests/gpx/test_gpx_parsing.py` — the parse-rejection pattern (malformed or edge-case input yields a named error, not a server error).
- **Run locally**: `uv run pytest tests/<app>/test_<name>.py`.

### 6.2 Adding an integration test through the request cycle

- **Location**: `tests/test_ownership_matrix.py` for anything the route inventory drives — a new object-scoped route belongs in `OBJECT_SCOPED_ROUTES` there, and every actor × verb cell then covers it for free. `tests/<app>/` for a route's own behavior (what it renders, what it saves, what it says when input is bad).
- **Naming**: `test_<actor>_<outcome>_<on_what>` — the actor is part of the name because each actor is a different mechanism: `test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object`, `test_an_anonymous_visitor_is_sent_to_login_on_every_verb_a_route_accepts`.
- **Reference test**: `test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object` in `tests/test_ownership_matrix.py`. For a one-off (non-inventory) route, `tests/trips/test_trip_delete.py::test_another_users_trip_post_returns_404_and_the_trip_survives`.
- **Run locally**: `uv run pytest tests/test_ownership_matrix.py -v`.

**The pattern: a status code plus a state or no-leak probe, always.** A bare `assert response.status_code == 404` passes against a view that read, wrote or deleted the object and refused afterwards, and it cannot tell `gpx:download`'s three distinct 404 causes apart (not yours / does not exist / file missing from storage). So every cell pairs its status with an assertion about what did *not* happen: the foreign object's name absent from the body, the row still present, its stored fields unchanged, no new row created, the stored bytes absent from the response. Needles must be escape-free — `"Other Rider Trip"`, never an apostrophe, which Django autoescapes into a form the raw needle no longer matches.

**What the contract actually is**, so a new cell asserts the right thing rather than a copied one:

| Actor | Verb | Expected | Produced by |
|---|---|---|---|
| second logged-in rider | any verb that reaches the object | `404` | the owner-scoped queryset |
| second logged-in rider | `OPTIONS` | `200` + `Allow`, empty body | `View.options`, before `get_queryset` — assert non-disclosure by comparing against a nonexistent pk, not a refusal |
| second logged-in rider | a verb outside `http_method_names` | `405` | `View.dispatch`'s method lookup, before `get_queryset` |
| anonymous | any accepted verb, `OPTIONS` included | `302` to `reverse("login")` with an exact `?next=` | `LoginRequiredMixin.dispatch`, which runs first |
| non-staff or anonymous | an admin object route | `302` to `reverse("admin:login")` with `?next=` | `AdminSite.admin_view` — **not** 404; nothing scopes a queryset there |

**Prove the test bites before trusting it.** Break the production line it guards, confirm the cell goes red for the right reason, revert. `lessons.md` #1, #3 and #4 all record a green gate concealing a real regression.

### 6.3 Adding a test for a post-commit side effect

- **Location**: `tests/gpx/test_gpx_signals.py`.
- **Naming**: `test_<trigger>_removes_<what>` — the trigger names the path (a model delete, a queryset delete, a cascade, a replace), because each one reaches the receiver through a different mechanism and a name that only says "removes the file" hides which one is under test.
- **Reference test**: `test_a_trip_queryset_cascade_removes_the_track_files_it_never_loaded` (one-level cascade) and its sibling `test_a_user_queryset_cascade_removes_the_track_files_two_levels_down` (two-level cascade, added in Phase 2) — the second is the pattern to copy for any new cascade depth: build the stored track, assert the file exists, delete from the *top* of the chain inside `django_capture_on_commit_callbacks(execute=True)`, then assert both the row count and `default_storage.exists()` afterward.
- **Run locally**: `uv run pytest tests/gpx/test_gpx_signals.py -v`.
- **Restated from the file's own module docstring**: both receivers schedule their storage delete through `transaction.on_commit`, and pytest-django wraps each test in a transaction that never commits — so every test here must wrap the mutating call in `django_capture_on_commit_callbacks(execute=True)`, or the deferred callback is silently skipped and the assertion passes while proving nothing about it.

### 6.4 Adding a test for an empty or degraded page state

- **Location**: `tests/trips/test_trip_detail.py` for a single degradation dimension or a combination; `tests/trips/test_trip_detail_stats.py` / `test_trip_detail_map.py` for a dimension's own field-level detail.
- **Naming**: `test_a_<condition>_<outcome>` for a single dimension; `test_a_<condition_1>_and_<condition_2>_both_render_together` when proving two degradation branches compose without one suppressing the other.
- **Reference test**: `test_a_rider_sees_a_deliberate_marker_when_the_track_file_is_missing` in `tests/trips/test_trip_detail.py` for the single-dimension pattern (deliberate empty-state marker, asserted as content); `test_a_missing_file_and_unbackfilled_stats_both_render_together` (added in Phase 3) for the combined-dimension pattern — build the degraded state each single-dimension test builds on its own, on the same track, and assert both markers are present in the same response body.
- **Run locally**: `uv run pytest tests/trips/test_trip_detail.py -v`.

### 6.5 Adding a test for a management command

- **Location**: `tests/gpx/test_reconcile_media.py`.
- **Naming**: `test_a_<condition>_is_<outcome>`, following the file's existing convention (e.g. `test_a_referenced_file_is_never_reported`).
- **Reference test**: `test_a_file_aged_to_exactly_the_cutoff_is_treated_as_an_orphan` (added in Phase 2) — the pattern for a boundary condition tied to a computed cutoff.
- **Run locally**: `uv run pytest tests/gpx/test_reconcile_media.py -v`.
- **Note learned in Phase 2**: a boundary tied to `timezone.now()` cannot be hit reliably with a real-clock helper like `back_date` (`os.utime`, moving a file's actual mtime) — the cutoff is computed inside `handle()` at call time, so a wall-clock race separates the two. Freeze both sides instead: monkeypatch `django.utils.timezone.now` to a fixed instant for the command's cutoff, and monkeypatch `default_storage.get_modified_time` for the specific key under test to return exactly that instant minus the age threshold. Freezing only one side leaves the other still driven by the real clock and the boundary is no longer exact.

### 6.6 Adding a test for a settings or environment guard

- **Location**: `tests/test_settings_env.py` for a composition/subprocess-level test proving a real boot sequence trips a guard; `tests/test_media_storage.py` for the guard's own unit tests (each branch, hand-set on the `settings` fixture) and the `/healthz/` probe's integration tests.
- **Naming**: `test_<condition>_trips_the_guard_under_<debug-state>` for a composition test.
- **Reference test**: `test_blank_media_root_trips_the_guard_under_debug_false` (`tests/test_settings_env.py`, added in Phase 4).
- **Run locally**: `uv run pytest tests/test_settings_env.py tests/test_media_storage.py -v`.
- **Restated from Phase 4's finding**: a guard's own unit tests and its probe's integration tests can each be fully thorough in isolation and still miss the one thing that actually caused a real incident — that two independently-tested facts *compose* at boot. When an autouse fixture (here, `_media_root_in_tmp_path` in `tests/conftest.py`) exists specifically to isolate the rest of the suite from a real environment fallback, it also means no in-process test can observe that fallback landing where production would — a subprocess (`sys.executable -c <code>`, `django.setup()`, a foreign `cwd`, an explicit env dict with no `.env`) is the only way to see it.

### 6.7 Per-rollout-phase notes

(Filled in by each phase's final sub-phase — anything surprising the phase
taught that the entries above do not already carry.)

**Phase 1 — Data-isolation contract.**

- *The brief's premise was already false.* The phase was opened to prove routes refuse a second logged-in user; research found all five object-scoped routes already had a foreign-actor test asserting 404 plus a leak or persistence assertion, and `grep 403 tests/` returned nothing. What was missing was structural, not per-route: no assertion of the route *inventory*, no coverage of verbs beyond GET/POST, no request ever issued at a `/media/` path, no admin boundary cell, and `other_rider` never once logged in. Worth remembering when opening the remaining phases — verify the gap before building for it.
- *`static(MEDIA_URL, …)` is a no-op under test.* `django.conf.urls.static.static()` opens with `if not settings.DEBUG: return []`, and the suite runs at `DEBUG=False`. Mutation-checking the media probe with that line therefore passes green against a config that would genuinely leak. Use an explicit `re_path(r"^media/(?P<path>.*)$", …)` serving from `settings.MEDIA_ROOT` — which is also the closer analogue of the real threat (a platform static handler or `WHITENOISE_ROOT`, neither of which consults `DEBUG`).
- *A drained streaming response reads as empty forever.* `FileResponse.streaming_content` is a one-shot iterator, so a helper that joins it without memoizing returns `b""` on every later call — and a leak assertion searching that empty body passes. Any body helper used by more than one assertion must cache what it drained.
- *Assert the absence of a route as a request, not as a settings value.* The whole defense on "downloads their track file" is that nothing serves `MEDIA_URL`. A settings assertion stays true after a route, a middleware or a platform handler has overridden it; only a request at a real `file.url` notices. Build the URL from the model — `gpx/models.py` names files with `secrets.token_hex(16)`, so a hardcoded path 404s for the wrong reason and keeps passing after the leak is introduced.

**Phase 2 — File lifecycle and storage/row consistency.**

- *Statistics and map data are stored columns, deliberately decoupled from file presence — proving Risk #3 meant adding a read, not fixing a bug.* `build_map_config` and `build_trip_stats` already read only stored columns and never touch storage, so a trip whose file vanished rendered identically to a healthy one — not because of a defect, but because nothing on the render path had ever needed to check. Closing the gap meant adding the one storage read (`track.file.storage.exists(track.file.name)`) the detail view did not previously have, and a template branch to show what it found — not repairing the existing decoupling, which stays exactly as designed.

**Phase 3 — Rejection and degradation.**

- *The brief's premise was largely already true, the same shape Phase 1's research found.* Both Risk #5 (upload rejection) and Risk #6 (trip detail degradation) were already substantially implemented and tested with content-level assertions before this phase opened — every rejection path had its own distinct message, and every degradation branch had its own distinct sentence. The actual gap was narrow and named: a storage-side debris assertion missing from every rejection test, and one untested combination of two already-tested degradation dimensions.
- *The storage-emptiness idiom generalizes cleanly across risk areas.* `assert not (tmp_path / "media").exists()`, first established for `reconcile_media`'s empty-volume case in Phase 2, reused verbatim as the "no debris on rejection" assertion for Risk #5 — the same per-test `MEDIA_ROOT` fixture makes the idiom portable with no new fixture required.
- *Two of the phase's four named scenarios shared one code branch with an existing test — worth pinning explicitly rather than treating as already covered.* "Empty" (0-byte) and "truncated" (cut off mid-tag) uploads both resolve via the same `GpxSyntaxError` branch `test_malformed_xml_is_a_syntax_error` already exercised — a true fact, but not one any test asserted by name before this phase. Naming them individually pins today's shared-branch behavior so a future change that splits that branch is caught by name, not silently passed because a different-looking input happened to land in the same except clause.

**Phase 4 — Environment guard.**

- *The brief's premise was already false, the same shape as Phase 1 and Phase 3.* The guard (`media_root_misconfiguration()`) and both test layers §2's Risk Response Guidance named — unit on settings resolution, integration on the probe — already existed and were already thorough: 12 tests in `tests/test_media_storage.py` plus `env_or()` unit and subprocess tests in `tests/test_settings_env.py`. The actual gap was narrow: nothing proved the two independently-tested facts (the blank-`MEDIA_ROOT` fallback, and the `inside_base_dir` check) compose at a real process boot — the exact shape of the 2026-08-26 production incident. Closing it meant one new subprocess test, not a rebuild.

**Phase 5 — Gate credibility.**

- *The brief's premise was only partly true here — the first rollout phase where that
  happened.* Every earlier phase (1, 3, 4) found the premise already false: the tested
  behavior existed and was already covered. Here, research read all 268 request-cycle test
  functions across 25 files and found two genuinely status-only tests. A mechanized AST
  heuristic, run during planning, found five: the same two, plus a third genuinely
  status-only test research missed (`test_deleted_trips_detail_url_returns_404`), a fourth
  whose docstring overclaimed a positive `Allow` pin its negative-only assertion never
  delivered (`test_put_is_rejected_as_a_disallowed_method`), and one legitimate waiver (the
  `/healthz/` cached-verdict test, where the sequence of status codes genuinely *is* the
  behavior under test). A 60-line-class AST rule caught three of five findings a careful
  human read of 268 tests missed — the reason this phase exists as a mechanism, not a
  one-time cleanup.
- *Mutation testing was ruled out on tooling and cost grounds, not preference.* `mutmut`'s
  cache layer has an unresolved incompatibility with Python 3.14 (a `copy.deepcopy()`
  semantics change breaks the Pony ORM query translator it uses internally), and this
  project's `pyproject.toml` pins `>=3.14` with no 3.13 fallback interpreter. Independently,
  a full mutation run reruns the whole suite once per mutant — hundreds to low-thousands of
  runs for ~3,000 LOC — against a `gates` job budgeted at roughly six minutes end to end. The
  five-shape bite-proof harness is the cost-proportionate substitute: one subprocess per
  named risk area, not one per surviving mutant.
- *Patch the name where it is used, not where it is defined — the trap a false-green would
  hide behind.* `trips/views.py` does `from gpx.availability import track_file_is_available`,
  so the view's live reference is `trips.views.track_file_is_available`; patching
  `gpx.availability.track_file_is_available` leaves the view's own module attribute
  untouched and the harness would report a false green. `gpx.forms.MAX_GPX_FILE_BYTES` is the
  same trap — imported by value from `gpx.constants`. Every shape in `tests/mutations.py`
  patches the importing module's attribute, with a comment naming why, for exactly this
  reason.

### 6.8 Adding a mutation shape to the credibility gate

- **Location**: `tests/mutations.py` — add one `MutationShape` instance to the
  `MUTATION_SHAPES` tuple. No other file needs an edit: `tests/conftest.py`'s injection
  fixture and `tests/test_suite_bites.py`'s harness both iterate the registry.
- **Naming**: `name` is the `VELOLOG_MUTATION` value — a short phrase naming the broken
  behavior, not the guard test (`no_op_file_discard`, not
  `test_a_trip_queryset_cascade_...`).
- **Reference shape to copy**: `file_always_available` in `tests/mutations.py` — a plain
  module-attribute patch (not a nested class attribute like
  `unscoped_trip_detail_queryset`), with the imported-name-vs-defining-module comment this
  pattern always needs.
- **Fields to fill**: the `(module_path, attribute)` pair naming where the target is
  *imported*, not where it is defined (see the trap above — read the call site with `grep`
  before guessing); a `replacement` factory building the broken value (deferred imports of
  Django models inside the factory, never at module level — `tests/mutations.py`'s own
  module docstring explains why); a `guard_node_id` naming the one existing test that should
  go red; and a `fragment` that is a distinctive substring of that guard test's own
  assertion message or expression — never a generic pytest token (`"AssertionError"`,
  `"FAILED"`) that would match any failure vacuously.
- **Verify before committing**: run the guard node unmutated
  (`sys.executable -m pytest <guard node id> -o addopts= -q`) and confirm `fragment` is
  *absent* from that output — otherwise it could have passed the harness's fragment check
  vacuously. Then run
  `VELOLOG_MUTATION=<name> sys.executable -m pytest <guard node id> -o addopts= -q` (or add
  the shape and run `uv run pytest -m bite_proof -v`) and confirm the guard actually goes
  red for the fragment reason, not a collection error. A shape whose guard stays green, or
  goes red for an unrelated reason, is a broken shape — do not commit it un-verified.
- **Run locally**: `uv run pytest -m bite_proof -v` (deselected from the default
  `uv run pytest` / `uv run pytest --cov` by `pyproject.toml`'s `addopts`).

**Two limitations, stated so a future reader does not read more protection into a shape than
it gives:**

- **A shape guards the one assertion its mutation trips, not every assertion in the guard
  test.** `test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object` delegates to
  eight `route.probe(target, response)` calls across the ownership matrix; the
  `unscoped_trip_detail_queryset` shape only proves the harness catches the `trips:detail`
  route's own probe going unscoped. A different route in that same test going unscoped is
  only caught if a shape exists that mutates *its* queryset — the guard test being
  comprehensive does not make the shape comprehensive.
- **`fragment` must be verified, not assumed, to discriminate.** It has to be a substring
  that appears in the guard's *mutated* failure output and is absent from its *unmutated*
  run — the verification step above is what confirms this, not a read of the assertion by
  eye.

## 7. What We Deliberately Don't Test

Exclusions agreed during the rollout (Phase 2 interview, Q5). Future
contributors should respect these unless the underlying assumption changes.

- **Django admin as a product surface** — the owner is the only admin, so admin CRUD, list columns, and filters are Django's code carrying a trusted-user blast radius. Re-evaluate if a second admin account is ever created. The admin's *file-replacement* path stays tested, because it is a file-lifecycle path (Risk #1), not an admin feature. (Source: Phase 2 interview Q5.)
- **Map rendering visuals and tile fetching** — a mapping library drawing a polyline and a public basemap serving tiles are both third-party. Assert the map configuration the server hands the page; do not diff the rendered canvas or reach the tile server. Re-evaluate if the map ever becomes server-rendered. (Source: Phase 2 interview Q5; consistent with PRD Non-Goals, which state a tile outage degrades to blank tiles with the route still drawn.)
- **Django framework internals** — password hashing, ORM query correctness, CSRF, form field coercion. The framework is its own test; assert the project's rules layered on top of it. Re-evaluate on a major framework upgrade. (Source: Phase 2 interview Q5.)
- **The hosting platform itself** — volume mounting, application-server boot, and deploy mechanics belong to the deployment runbook and the health probe, not to pytest. Note this is *not* a blanket exclusion of deployment concerns: Q5 explicitly declined to exclude them, and §3 Phase 4 tests the configuration guard for exactly that reason. (Source: Phase 2 interview Q5, by exclusion.)

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-08-29
- Stack versions last verified: 2026-08-29
- AI-native tool references last verified: 2026-08-29

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
