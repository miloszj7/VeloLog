<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Data-Isolation Contract Implementation Plan

- **Plan**: `context/changes/testing-data-isolation-contract/plan.md`
- **Scope**: All 4 phases (full plan review)
- **Date**: 2026-08-29
- **Verdict**: REJECTED at review time — **all 10 findings triaged, 9 fixed, 1 accepted as-is**
- **Findings**: 1 critical, 3 warnings, 6 observations (all resolved — see Triage Outcome below)

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | WARNING |
| Safety & Quality | FAIL |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

The REJECTED verdict is mechanical: F1 is a critical Safety & Quality finding, and the rubric
fails the dimension on any critical. It is about the **proof value of the phase's headline test**,
not about a production defect — no production code was touched, no test fails, and no rider's data
is reachable today. What F1 says is that the guarantee the phase was opened to establish, and which
`AGENTS.md` now asserts as a Hard Rule, is not actually pinned under CI ordering.

## Triage Outcome

All 10 findings were triaged in one pass. **9 fixed, 1 accepted as-is (F10, per its own
"no fix needed" recommendation).** Every fix was verified either by re-running the affected
test module (and, where the finding was about detection power, by re-injecting the exact
mutation the finding described and confirming it now fails before reverting it) or, for F4,
by cross-checking the corrected prose against the artifacts it now cites.

| # | Title | Decision | Commit |
|---|---|---|---|
| F1 | Media probe passes green against a real media leak | FIXED | `a7e3269` |
| F2 | Inventory guard is fail-open outside `trips`/`gpx` | FIXED (Fix A, extended) | `de50f8c` |
| F3 | `_assert_track_bytes_were_not_served` has no state leg | FIXED | `c2784d6` |
| F4 | Progress step 3.5 records a mutation that is a no-op | FIXED | `e0aaf7a` |
| F5 | `PK_CONVERTER` is a single-converter substring match | FIXED | `a30e925` |
| F6 | Reverse-direction sweep never exercises a mutating verb | FIXED | `9ae5fe6` |
| F7 | Fixture-name-as-string + `getfixturevalue` has no precedent | FIXED | `e18e4f4` |
| F8 | Tautological meta-assertion, message-less `assert` | FIXED | `0bc5a35` |
| F9 | `other_auth_client`'s shared-session hazard | FIXED | `cf09ef7` |
| F10 | §6.7 filled in without being a contracted deliverable | ACCEPTED (no change) | — |

**Decision reasoning, one finding at a time:**

- **F1 (CRITICAL)** — Fixed as recommended: added a `pytest.raises(Resolver404): resolve(url)`
  leg to the media probe, independent of `DEBUG`, `document_root` binding, and test ordering.
  This was the blocking finding; fixing it is what moves the review from REJECTED to resolved.
  Verified by re-injecting the exact `document_root`-based `re_path` mutation the finding
  described and confirming all 3 media cells now go red running the *whole* module (previously
  64 passed / 0 red); mutation reverted before committing.

- **F2 (WARNING)** — Took Fix A (fail-closed), but implementation surfaced a second gap the
  finding's own text didn't fully anticipate: even inverting `GUARDED_NAMESPACES` to
  `UNGUARDED_NAMESPACES` left the walk starting from `URLResolver` children only, so a bare
  top-level `<int:pk>` pattern with no namespace at all — not just one under a new app's own
  namespace — still escaped. Fixed both by recursing from the root resolver with an empty
  prefix. Verified against three shapes: the original `path("share/<int:pk>/", ...)` mutation
  from this same review, a bare `path("leak/<int:pk>/", ...)`, and the unmutated baseline (64
  passed). All reverted before commit.

- **F3 (WARNING)** — Fixed as recommended: added row-existence and `file.name`-identity
  assertions to `_assert_track_bytes_were_not_served`, matching its two sibling probes, and
  reworded the docstring to credit the `make_stored_track` precondition rather than the body
  search as the load-bearing half.

- **F4 (WARNING)** — Fixed as recommended: added parentheticals to Progress steps 3.5 and 3.6
  naming the substituted mutation, the `DEBUG=False` no-op it works around, and the ordering
  caveat F1's fix now supersedes. Docs-only; no code re-verification needed beyond confirming
  the cited artifacts (`test-plan.md` §6.7, `a7e3269`) say what the parenthetical claims.

- **F5 (OBSERVATION)** — Fixed as recommended: replaced the `"<int:pk>"` substring check with
  `re.search(r"<\w+:\w*(pk|id)>", ...)`. Verified the regex against all four escape cases the
  finding named (`<uuid:pk>`, `<slug:pk>`, `<int:track_id>` match; `<str:name>` does not).

- **F6 (OBSERVATION)** — Fixed as recommended: added a second-rider reverse-direction sweep on
  the write verb for `trips:edit`/`trips:delete`. Verified by mutating
  `TripDeleteView.get_queryset` to `Trip.objects.all()` — the new cell caught it (302 instead
  of 404) — then reverting.

- **F7 (OBSERVATION)** — Fixed as recommended: replaced `getfixturevalue`-by-string with
  `Literal` actor labels resolved through an explicit if/elif/else branch in each test,
  removing the associated `cast()`s. Verified full module + `ruff`/`black`/`mypy --strict`
  clean.

- **F8 (OBSERVATION)** — Fixed as recommended: dropped the tautological
  `len(ACCEPTED_CELLS) == sum(...)` assert; kept the genuine sibling guard on the next line.

- **F9 (OBSERVATION)** — Fixed as recommended: `other_auth_client` now builds its own
  `Client()` instead of sharing `client` with `auth_client`, closing the shared-session hazard
  mechanically instead of leaving it as a prose warning.

- **F10 (OBSERVATION)** — Accepted as-is: the finding's own text already concluded "no fix
  needed" — the §6.7 addition is in-spirit scope creep (high-value notes, and §6.7's header
  says each phase fills it in), recorded only so the diff was fully accounted for.

**Final verification, after all nine fixes**: CI-equivalence run
(`SECRET_KEY=... DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`) — 312 passed, 2 skipped,
97.34% coverage; `manage.py check` and `makemigrations --check --dry-run` clean;
`mypy --strict .` clean across 74 source files.

## Verification performed by this review

| Check | Result |
|---|---|
| `uv run pytest tests/test_ownership_matrix.py -q` | 64 passed |
| `SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` | 310 passed, 2 skipped, 97.34% |
| `ruff` / `black --check` / `isort --check-only` / `mypy --strict` | all clean |
| `manage.py check` / `makemigrations --check --dry-run` | clean |
| `grep -n TBD context/foundation/test-plan.md` | §6.2 filled; remaining TBDs belong to Phases 2–5 |
| Mutation: import-time `document_root` media serve route | **full module 64 passed — probe did not bite** (F1) |
| Mutation: project-level `<int:pk>` route | **guard passed green** (F2) |
| Mutation (agent-run): unscoped `get_queryset` on 3 trip views + download | 15 cells red — core contract genuinely defended |
| Mutation (agent-run): `http_method_names` dropped + upload ordering inverted | 9 cells red, incl. `trips:delete-delete`, `gpx:upload-post` |

Git scope is exactly the planned set — `AGENTS.md`, `context/foundation/test-plan.md`,
`tests/conftest.py` (+16, additive), `tests/test_ownership_matrix.py` (+869), plus the four change
artifacts. No `trips/`, `gpx/`, `velo_log/`, `.github/` or `context/archive/` change: every
"What We're NOT Doing" guardrail held.

## Findings

### F1 — Media probe passes green against a real media leak

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `tests/test_ownership_matrix.py:769-822`
- **Detail**: I added the realistic shape of the regression to `velo_log/urls.py` —
  `re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})`, which is
  `DEBUG`-independent and is the closer analogue §6.7 itself recommends over `static()`. The full
  module ran **64 passed, zero red**, against a URLconf that genuinely serves every rider's stored
  GPX to any URL holder. Run in isolation (`-k media`) the owner cell *does* go red with
  `assert 200 == 404` on a `FileResponse`. The cause is ordering: `document_root` is bound when the
  URLconf is imported, and the autouse `_media_root_in_tmp_path` (`tests/conftest.py:38-46`) gives
  every test its own `MEDIA_ROOT`, so `django.views.static.serve` searches a stale directory and
  404s for file-not-found. That is a pass for the wrong reason — precisely the hazard the probe's
  own docstring at `:792-795` claims to have been designed around. In CI the whole suite runs, so
  the probe is green. This is `lessons.md` #1 and #3 in their exact recorded form, on the test the
  plan calls "the highest-value single test in this phase".
- **Fix**: Add a resolver-level leg that no `DEBUG` value and no `document_root` binding can
  satisfy — assert the URL resolves to no pattern at all
  (`with pytest.raises(Resolver404): resolve(url)`), keeping the existing request leg, which is
  what covers the lazily-resolved-route and platform-handler shapes.
  - Strength: independent of test ordering, of `DEBUG`, and of when `MEDIA_ROOT` is read; catches
    every shape of the regression including the two (`static()`, `WHITENOISE_ROOT`) that are
    structurally invisible to a request-based assertion under test.
  - Tradeoff: minor — a few lines in one test; it does partially overlap
    `tests/test_media_storage.py:106-107`, but that one asserts a settings value, not the resolver.
  - Confidence: HIGH — the blind spot is reproduced and the missing assertion is mechanical.
  - Blind spot: I have not checked whether a resolver assertion would need special handling for the
    `RedirectView` at the project root catching `""`.
- **Decision**: FIXED — added `pytest.raises(Resolver404): resolve(url)` leg
  (`a7e3269`). Verified: full module 64 passed post-fix; re-injected the
  `document_root` mutation and all 3 media cells went red running the whole
  module (previously 64 passed / 0 red). Mutation reverted before commit.

### F2 — Inventory guard is fail-open outside `trips` and `gpx`

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `tests/test_ownership_matrix.py:68` (`GUARDED_NAMESPACES`), `:276-282`
- **Detail**: I added `path("share/<int:pk>/", RedirectView.as_view(url="/"), name="share")` at
  project level in `velo_log/urls.py`; both guard tests passed green. The guard only descends
  resolvers whose top-level namespace is `trips` or `gpx`. `AGENTS.md` states new Django apps belong
  at the repo root with their own namespace registered in `INSTALLED_APPS` — so the most likely way
  "route number six" actually appears is in a *new* app, which is exactly the case the guard cannot
  see. The plan's Phase 1 contract did scope the walk to those two namespaces, and `AGENTS.md:11`
  and `test-plan.md:127` both scope the promise honestly, so this is a design limit rather than a
  false claim. But G2's stated purpose — "route #6 forgetting the idiom ships green" — is only
  partly closed.
- **Fix A ⭐ Recommended**: Invert to fail-closed — walk the whole URLconf and subtract an explicit
  `UNGUARDED_NAMESPACES = ("admin",)` plus a named project-level allowlist.
  - Strength: closes the regression path that is actually most likely, and the module's own failure
    message at `:306-308` already recommends the allowlist shape for public routes.
  - Tradeoff: introduces the allowlist constant the plan deliberately declined to add while empty,
    and `admin` / `accounts` / the root redirect must be enumerated once.
  - Confidence: HIGH — the walk already recurses generically; only the entry filter changes.
  - Blind spot: whether any third-party app's URLconf would need an entry (none installed today).
- **Fix B**: Keep the scope and add the two-namespace limit to the `AGENTS.md` rule as an explicit
  maintenance obligation.
  - Strength: no test churn; the limit becomes visible where an agent reads it every session.
  - Tradeoff: relies on a human remembering to extend `GUARDED_NAMESPACES`, which is the exact
    reliance G2 existed to remove.
  - Confidence: MEDIUM — depends on how soon a sixth object-scoped app is likely.
  - Blind spot: None significant.
- **Decision**: FIXED — Fix A (`de50f8c`). Walk found a second gap beyond the plan's own
  namespace-scoped exclusion while implementing: a bare top-level `<int:pk>` pattern (no
  namespace at all) also escaped the original recursive walk's entry point, not just the
  fixed two-namespace list. Fixed both in the same commit by recursing from the root
  resolver with `prefix=""`. Verified: baseline 64 passed; re-injected both the original
  project-level `path("share/<int:pk>/", ...)` shape and a bare `path("leak/<int:pk>/",
  ...)` — guard now fails on each; mutations reverted before commit.

### F3 — `_assert_track_bytes_were_not_served` has no state leg

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `tests/test_ownership_matrix.py:172-189`
- **Detail**: The plan's Phase 2 item 1 required that for HEAD and OPTIONS "the descriptor's probe
  must tolerate an empty body rather than assert against it blindly" and that "their probe leg is
  the state assertion (object survives / no row created) rather than a body search". Both sibling
  probes carry one — `_assert_trip_neither_leaked_nor_mutated` has existence plus field comparison
  (`:138-150`), `_assert_no_track_was_attached` has the row-list comparison (`:160-165`). This one
  asserts only `target.track_content not in _body(response)`, so on the OPTIONS cell, the three
  anonymous 302 cells and the four 405 cells the body is empty and the probe is a guaranteed pass.
  Its genuine value is the precondition at `:181-185`, which forces real bytes on disk so an
  observed 404 cannot be `gpx:download`'s "file missing from storage" 404 — worth saying, since the
  docstring at `:176` instead calls it "the load-bearing probe of the pair".
- **Fix**: Add a state leg — the `GpxTrack` row still exists and its `file` key is unchanged — and
  reword `:176` to credit the precondition rather than the body search.
- **Decision**: FIXED (`c2784d6`) — added row-existence and `file.name` identity assertions;
  reworded docstring. Verified: full module 64 passed.

### F4 — Progress step 3.5 records a mutation that is a documented no-op

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `context/changes/testing-data-isolation-contract/plan.md` Progress steps 3.5, 3.6
- **Detail**: Step 3.5 reads "Adding a `static(MEDIA_URL, …)` route turns all three media cells red"
  and is checked `[x]` against `2efa865`, while `test-plan.md:193` and `change.md:32` both record
  that this exact mutation returns `[]` at `DEBUG=False` and therefore cannot turn anything red. The
  step title was preserved per the plan's own "do not rename step titles" convention and the
  correction is written down in two places, so the paper trail is honest overall — but the checked
  line, read alone, claims a verification that was not performed as written. Step 3.6 ("fails
  because bytes are served, not merely on a status change") is true only when the media test runs
  first in the process, per F1.
- **Fix**: Append a parenthetical to 3.5 and 3.6 naming the substituted `re_path` mutation and the
  ordering caveat, pointing at `test-plan.md` §6.7. F1's fix supersedes the 3.6 half.
- **Decision**: FIXED (`e0aaf7a`) — added parentheticals to both steps.

### F5 — `PK_CONVERTER` is a single-converter substring match

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/test_ownership_matrix.py:64`
- **Detail**: `PK_CONVERTER = "<int:pk>"` matched as a substring, so `<uuid:pk>`, `<slug:pk>` or a
  differently-named kwarg such as `<int:track_id>` escapes the guard silently. Every route in the
  project uses `<int:pk>` today, so there is no false negative now; the comment at `:61-63` states
  the substring choice deliberately.
- **Fix**: Match `re.search(r"<\w+:\w*(pk|id)>", str(entry.pattern))`, or flag any converter at all
  under the guarded namespaces.
- **Decision**: FIXED (`a30e925`) — replaced with the recommended regex. Verified against
  `<int:pk>`, `<uuid:pk>`, `<slug:pk>`, `<int:track_id>` (all match) and `<str:name>`
  (does not).

### F6 — Reverse-direction sweep never exercises a mutating verb

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/test_ownership_matrix.py:387-393`, `:654-681`
- **Detail**: `_primary_verb` returns `accepted_verbs[0]`, which is `get` for both `trips:edit` and
  `trips:delete`, so the second-rider-as-intruder direction is proven only on reads for the two
  destructive routes. The plan asked for the primary verb only and called a second full matrix
  unnecessary, so this is compliant — but the write verb is the leg worth pinning symmetrically, and
  it is one extra parametrization.
- **Fix**: Sweep each route's write verb in the reverse direction too, where it has one.
- **Decision**: FIXED (`9ae5fe6`) — added `test_the_first_riders_objects_resist_the_second_riders_write`
  parametrized over `trips:edit`/`trips:delete`. Verified: mutating `TripDeleteView.get_queryset`
  to `Trip.objects.all()` turned the new `trips:delete` cell red (302 instead of 404); mutation
  reverted; full module 66 passed clean.

### F7 — Fixture-name-as-string plus `getfixturevalue` has no precedent in the suite

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/test_ownership_matrix.py:755-766`, `:798-799`, `:851`
- **Detail**: `MEDIA_PROBE_ACTORS` / `ADMIN_BOUNDARY_ACTORS` carry fixture *names* resolved through
  `request.getfixturevalue` with three `cast()`s. The suite's declared parametrize template
  (`tests/test_static_references.py:45-69`) parametrizes over real typed values. The casts assert
  nothing to mypy, and a renamed fixture degrades to a runtime `KeyError` inside the test rather
  than a collection error.
- **Fix**: Parametrize over a small frozen dataclass or a `Literal` and resolve the client in one
  explicit branch.
- **Decision**: FIXED (`e18e4f4`) — parametrized over `Literal` actor labels; client/owner
  resolved in an explicit if/elif/else branch in each test. No more `getfixturevalue`/`cast`.
  Verified: full module 66 passed; ruff/black/mypy --strict clean.

### F8 — Tautological meta-assertion, and the module's only message-less `assert`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/test_ownership_matrix.py:471`, `:475`
- **Detail**: `len(ACCEPTED_CELLS) == sum(len(r.accepted_verbs) …)` is true by construction of the
  comprehension at `:348-350`, and `:475` holds unless a route lists `options` twice — neither can
  fail against the current source. `:471` is additionally the only bare `assert` in the module with
  no failure message, against the house style at `tests/test_static_references.py:66-69`. The
  sibling assertion at `:472-474` *is* a genuine guard (it catches an `accepted_verbs` entry outside
  `PROBED_VERBS`) and should stay.
- **Fix**: Drop `:471`, or give it a message naming what its failure would mean.
- **Decision**: FIXED (`0bc5a35`) — dropped the tautological assert; kept the genuine sibling
  guard. Verified: full module 66 passed; ruff/black/mypy --strict clean.

### F9 — `other_auth_client`'s shared-session hazard is documented in prose only

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/conftest.py:104-117`
- **Detail**: The fixture depends on the same `client` fixture as `auth_client`, so a test
  requesting both gets one client logged in twice rather than two sessions. The docstring says
  "Request exactly one", and no test currently violates it — only
  `test_the_first_riders_objects_are_equally_unreachable_from_the_second` uses it, alongside the
  `rider` *user* fixture. Nothing mechanically prevents a future one, and the failure would be a
  silently passing isolation test.
- **Fix**: Build a fresh session instead of documenting the hazard — `c = Client()`,
  `assert c.login(...)`, `return c`.
- **Decision**: FIXED (`cf09ef7`) — `other_auth_client` now builds its own `Client()` rather
  than sharing `client` with `auth_client`. Verified: full `tests/` suite passed.

### F10 — §6.7 filled in without being a contracted Phase 4 deliverable

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: `context/foundation/test-plan.md:190-195`
- **Detail**: Phase 4's Changes Required covered §6.2, the §3 row, the §5 gate note and `change.md`.
  The four Phase-1 notes added to §6.7 are an EXTRA. They are high-value — the `static()` no-op and
  the drained-streaming-response findings are exactly the kind of thing that would otherwise be lost
  — and §6.7's own header says each phase's final sub-phase fills it, so the addition is in spirit.
  Recorded only so the diff is fully accounted for.
- **Fix**: None needed; keep it.
- **Decision**: ACCEPTED — no change; kept as-is per the review's own recommendation.
