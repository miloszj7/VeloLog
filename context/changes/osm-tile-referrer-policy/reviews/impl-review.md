<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Restore OSM tile loading by sending a compliant Referer

- **Plan**: `context/changes/osm-tile-referrer-policy/plan.md`
- **Scope**: Phases 1–2 of 3 (Phase 3 is deploy-gated and not started)
- **Date**: 2026-09-13
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Evidence gathered

Automated criteria for both phases were re-run during this review, not taken from the
checkboxes:

- `ruff check .` / `black --check .` / `isort --check-only .` / `mypy .` — all clean (90 files)
- `manage.py check` — no issues; `makemigrations --check --dry-run` — no changes detected
- `collectstatic --noinput` — 1 copied, 406 post-processed
- `pytest --cov` — 406 passed, 2 skipped, coverage 96.55% (`fail_under = 80`)
- `pytest -m bite_proof` — 6 passed

The two Manual criteria that can be mechanically reproduced (2.5, 2.6) were reproduced rather
than trusted: deleting `SECURE_REFERRER_POLICY` turns `test_referrer_policy_is_osm_compliant_in_both_debug_modes`
red naming the consequence, and deleting the `referrerPolicy` line turns the source pin red
naming the consequence. Both bite for the stated reason. The remaining Manual items (1.6–1.8,
2.7) are browser observations or judgment calls with no diff-side evidence available; they are
accepted as reported, not rubber-stamp flags.

Production diff matches the plan exactly, and no "What We're NOT Doing" guardrail was crossed:
tile provider unchanged, Leaflet and both `SHA256SUMS` untouched, `gpx/map_config.py` untouched,
no e2e change, no CSP, and the `if not DEBUG:` block (settings.py:352–361) is absent from the diff.

## Findings

### F1 — The `map.js` source pin passes green when the option is commented out

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `tests/gpx/test_map_asset.py:38`
- **Detail**: `REFERRER_POLICY_OPTION` searches the raw text of the options group, so a
  commented-out option satisfies it. Reproduced during this review: replacing line 79 of
  `gpx/static/gpx/map.js` with `// referrerPolicy: "strict-origin-when-cross-origin", // disabled while debugging`
  leaves the pin **passing** (`1 passed in 0.41s`) while the shipped map sends no `Referer`.
  Commenting the line out while debugging tiles is a likelier regression than deleting it, and
  this is precisely the failure the module's own docstring says it exists to catch ("What it
  does catch is the failure that matters here — the option being dropped in a later edit").
  The docstring at lines 44–46 claims the scoped search defeats this, but the claim only holds
  for the *header* comment, not a comment inside the options object — so it is also a
  `lessons.md` #11 overclaim. The other two directions are safe: a nested object literal
  false-*fails* (documented at lines 29–33) and a template-literal URL fails at
  `assert call is not None`. Separately, `re.DOTALL` on line 36 is inert — the pattern contains
  no `.`.
- **Fix**: Anchor the option regex to the start of a line so a `//` prefix cannot satisfy it, and
  narrow the docstring claim to match:
  ```python
  REFERRER_POLICY_OPTION = re.compile(
      r"""^[^\S\n]*referrerPolicy:\s*["'](?P<value>[^"']+)["']""", re.MULTILINE
  )
  ```
  - Strength: One-line change; restores the bite the phase's whole purpose depends on, and is
    verifiable by the repo's own §6.8 ritual (force the guard to fail and read the reason).
  - Tradeoff: Still source-text matching, so it remains defeatable by a sufficiently creative
    edit — it closes the realistic shape, not every shape.
  - Confidence: HIGH — the false-pass was reproduced directly against the real file, and the
    anchored form was checked against the current line's leading whitespace.
  - Blind spot: A `/* ... */` block comment wrapping the line would still pass; not worth
    chasing.
- **Decision**: FIXED — regex anchored with `^[^\S\n]*` under `re.MULTILINE`; docstring narrowed to
  name both false passes separately. Verified by the §6.8 ritual: commenting the option out turns
  the pin red naming the consequence, and it is green again with the file restored.

### F2 — Neither guard proves the header is actually emitted; two docstrings say it does

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `tests/test_settings_security.py:54`, `tests/gpx/test_map_asset.py:12`, `tests/conftest.py:32`
- **Detail**: `test_referrer_policy_is_osm_compliant_in_both_debug_modes` loads `settings.py`
  off disk via `spec_from_file_location` and reads the module attribute — it never goes through
  the request cycle. So the setting half stays green if
  `"django.middleware.security.SecurityMiddleware"` is dropped from `MIDDLEWARE`, at which point
  no `Referrer-Policy` header is emitted at all and both guards remain green. Confirmed: `grep`
  for `SecurityMiddleware` and `MIDDLEWARE` under `tests/` returns no assertion on either, and
  CI never runs `manage.py check --deploy` (only bare `check`), so nothing else covers it.
  The overclaim is stated twice: `tests/gpx/test_map_asset.py:12` says "Its counterpart in
  `tests/test_settings_security.py` pins the global response header", and `tests/conftest.py:32`
  repeats "the response header in `tests/test_settings_security.py`". Both pin the *setting*,
  not the header — a `lessons.md` #11 shape, the same rule the plan itself cited in Key Discoveries.
- **Fix A ⭐ Recommended**: Add one request-cycle assertion that reads the header off a real
  response, and leave both docstrings accurate as written.
  ```python
  response = client.get(reverse("accounts:login"))
  assert response.headers["Referrer-Policy"] in OSM_COMPLIANT_REFERRER_POLICIES
  ```
  - Strength: Closes the middleware gap and makes the two "response header" claims true in one
    line, instead of weakening the claims to match a thinner test.
  - Tradeoff: Enters `test_assertion_strength.py`'s request-cycle population — but a header
    subscript is classified as a probe, so no `WAIVER_INVENTORY` entry is needed.
  - Confidence: HIGH — the population rule and probe classification were read directly from
    `tests/test_assertion_strength.py`; the middleware gap was confirmed by grep.
  - Blind spot: Picks up a dependency on a specific URL name; any always-available unauthenticated
    route works equally well.
- **Fix B**: Leave the tests as they are and correct the two docstrings to say "the setting", not
  "the response header".
  - Strength: Zero new test surface; removes the false claim immediately.
  - Tradeoff: The middleware gap stays open — the thing a reader most wants proven (a compliant
    header actually leaves the app) still is not.
  - Confidence: HIGH — trivially correct.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — `test_referrer_policy_header_reaches_the_response` added at
  `tests/test_settings_security.py:88`, asserting presence, compliance and non-blocking on a real
  `GET reverse("login")` response. Both docstrings left as written; they are now true. Verified:
  commenting `SecurityMiddleware` out of `MIDDLEWARE` leaves the three setting-level assertions
  green and turns only the new one red, naming the consequence — which is the gap this closes.
  It classifies as a probe, so no `WAIVER_INVENTORY` entry was needed
  (`tests/test_assertion_strength.py` passes unchanged).

### F3 — Asset path re-derives the repo root instead of using the repo's own finder idiom

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/gpx/test_map_asset.py:27`
- **Detail**: `MAP_JS = Path(__file__).resolve().parents[2] / "gpx" / "static" / "gpx" / "map.js"`
  is arithmetically correct and uses `pathlib`, but it hardcodes the `<app>/static/<app>/` layout
  and re-derives the repo root a third way — `tests/astscan.py:14` defines `REPO_ROOT`, and
  `tests/test_settings_security.py:27` uses `parent.parent`. `tests/test_static_references.py`
  already resolves this exact asset as `finders.find("gpx/map.js")`, with `"gpx/map.js"` in its
  `STATIC_REFERENCES` tuple — the same lookup `collectstatic` uses, and one that knows nothing
  about app-static layout.
- **Fix**: Resolve the asset with `finders.find("gpx/map.js")` inside the test body (needs no
  `django_db`, same as the sibling), or at minimum import `REPO_ROOT` from `tests.astscan`.
- **Decision**: FIXED — module-level `MAP_JS` path arithmetic replaced by
  `MAP_JS_REFERENCE = "gpx/map.js"` plus `finders.find` inside the test body, matching
  `tests/test_static_references.py`. `mypy --strict` clean; the `isinstance(located, str)` guard
  both satisfies the finder's `str | list[str] | None` return and fails naming the lookup.

### F4 — Shared constants added to `tests/conftest.py`, which the plan never mentions

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: `tests/conftest.py:28-44`
- **Detail**: `OSM_COMPLIANT_REFERRER_POLICIES` and `OSM_BLOCKING_REFERRER_POLICIES` are a
  17-line additive hunk not described in any phase. The plan required the same five-value set in
  two modules but never said where it should live. The addition is behaviorally inert (two
  module-level `frozenset`s, no fixture, no autouse hook, no import-time side effect) and follows
  the file's established role exactly — `GPX_POINTS`, `GPX_BOUNDS` and the factory aliases already
  live there and are imported the same way by 15 modules. Flagged only because the plan is the
  ground truth future reviews read.
- **Fix**: Record it as a one-line addendum in the plan's Phase 2 "Changes Required"; no code change.
- **Decision**: FIXED — recorded as item 3 under Phase 2 "Changes Required" in `plan.md`, labelled
  as a review addendum. Item 4 was added alongside it for the F2 test, which is outside the plan
  for the same reason. No code change.

### F5 — The source pin has no negative assertion, so widening the shared set makes it vacuous

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/gpx/test_map_asset.py:64`
- **Detail**: The pin asserts only `option.group("value") in OSM_COMPLIANT_REFERRER_POLICIES`.
  Now that the set is shared (F4), someone readmitting `same-origin` to it would silently
  neuter this guard. `tests/test_settings_security.py:85` carries exactly that counterpart
  (`assert policy not in OSM_BLOCKING_REFERRER_POLICIES`) and its docstring explains why it is
  not redundant — the same reasoning applies here. The plan specified the negative assertion for
  the settings test only, so this is as-specified, not drift.
- **Fix**: Add `assert option.group("value") not in OSM_BLOCKING_REFERRER_POLICIES` alongside line 64.
- **Decision**: FIXED — negative assertion added, plus a docstring paragraph explaining why it is
  not redundant, mirroring the settings guard's counterpart.

### F6 — No bite-proof mutation shape, and no record of why not

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/mutations.py` (N/A — absence)
- **Detail**: The repo's convention is a named mutation shape per risk area proving a named guard
  bites. None was added. This is defensible on two grounds: the change maps to Risk #6, which
  `CLAIMED_RISK_AREAS = {"#1", "#2", "#3", "#5", "#7"}` (`tests/test_suite_bites.py:34`) does not
  claim, so the harness gate stays correctly green; and a shape is mechanically infeasible
  anyway, since `apply_mutation_shape` monkeypatches a live module attribute while both guards
  read from disk (`spec_from_file_location` into a throwaway module, and a file read). The gap is
  the missing *record* — a future reader sees an absence and cannot tell it from an oversight.
  Note that the §6.8 ritual this convention exists to enforce is exactly what would have caught F1.
- **Fix**: Add a sentence to `change.md` (or the plan's Testing Strategy) stating that no mutation
  shape exists because the harness patches module attributes and both guards read from disk.
- **Decision**: FIXED — a "Bite-proof harness" subsection added to the plan's Testing Strategy
  recording both grounds (Risk #6 unclaimed; attribute patching vs. disk reads) and noting the
  §6.8 ritual was performed by hand. No code change.

## Note outside the findings

An untracked `todo` file sits at the repo root (`git status` → `?? todo`). It is unrelated to this
change and is not in any commit, but worth deleting or gitignoring before opening a PR.
