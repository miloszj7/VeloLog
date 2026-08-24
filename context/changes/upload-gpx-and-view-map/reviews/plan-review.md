<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Upload a GPX file and view the route as a map (S-03)

- **Plan**: `context/changes/upload-gpx-and-view-map/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-24
- **Verdict**: REVISE
- **Findings**: 3 critical, 3 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

## Grounding

19/19 paths ✓, 9/9 symbols ✓, brief↔plan ✓, Progress↔Phase contract ✓ (48/48 criteria
mapped across 6 phases, all `N.M`-numbered, no stray checkboxes in phase bodies).

Three runtime probes were run rather than inferred:

1. **Settings resolution** against `velo_log.settings` on Django 6.0.5 — reproduces the
   plan's B1/B2 claims exactly: `STORAGES` has only `staticfiles`, `MEDIA_ROOT == ''`,
   `MEDIA_URL == '/'`, both upload-size settings at `2621440`.
2. **`collectstatic` failure matrix** against this repo's actual
   `whitenoise.storage.CompressedManifestStaticFilesStorage` — see F2.
3. **`xml.etree.ElementTree` entity behaviour** on this venv's CPython 3.14 — see F3.

Lean Execution and Architectural Fitness pass on substance, not by default: the
"What We're NOT Doing" section is unusually complete, the declined point-cap is recorded
as an accepted risk rather than omitted, and every new surface follows an existing repo
convention (owner-scoped queryset, `TYPE_CHECKING` base alias, app at repo root,
project-level `static/` mirroring project-level `templates/`). The cross-app template
reference in Phase 4 §5 is documented as a decision rather than left implicit.

## Findings

### F1 — /healthz/ cannot detect the MEDIA_ROOT failure it is credited for

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Blind Spots
- **Location**: Phase 1 §3; Open Risks; Migration Notes
- **Detail**: The plan credits the Phase 1 `/healthz/` media round-trip with surfacing an
  unset `MEDIA_ROOT` in three separate places. It cannot. With `MEDIA_ROOT` unset, the
  Phase 1 default is `BASE_DIR / "media"` — inside the container. A `default_storage`
  write there **succeeds**, so `/healthz/` returns 200 with media "ok" while every
  uploaded file sits on ephemeral disk. The round-trip detects the `RAILWAY_RUN_UID`
  unwritable-volume mode (`infrastructure.md:59`) only once `MEDIA_ROOT` already points at
  the Volume. Compounding it: no phase owns the *act* of setting the variable. Phase 1 §2
  adds a commented `.env.example` key; Phase 6 §4 documents it in `DEPLOY.md`. Neither
  sets it in Railway, and no Progress checkbox (1.1–6.7) confirms it — while Phase 4 is
  the phase that makes uploads live.
- **Fix A ⭐ Recommended**: Make `healthz` assert the *location*, not just writability —
  report the resolved `MEDIA_ROOT` in the JSON body and, in production, require it to be
  an absolute path outside `BASE_DIR` (or the configured Volume mount); 500 otherwise.
  - Strength: Turns a silent pass into a red probe, in the same shape as the existing DB
    round-trip, failing loudly on the exact misconfiguration `infrastructure.md:59` warns
    is silent.
  - Tradeoff: Adds an environment-conditional branch to `healthz`, needing its own test
    at `DEBUG=False`.
  - Confidence: HIGH — the write-succeeds-anyway behaviour was verified directly against
    this settings module.
  - Blind spot: Does not cover `MEDIA_ROOT` pointing at a *wrong* absolute path that
    happens to be writable.
- **Fix B**: Add an explicit deploy gate to Phase 4 — a Progress checkbox
  ("`MEDIA_ROOT=/data/media` set in Railway, confirmed via `railway variables`") before
  the Phase 4 merge, and move the `DEPLOY.md` media note from Phase 6 up to Phase 4.
  - Strength: No code change; mechanically sufficient.
  - Tradeoff: Manual-only, and the plan's own Key Discoveries argue against exactly this
    class of mitigation ("needs a test that performs the real operation").
  - Confidence: HIGH as a step, weaker as a durable guard.
  - Blind spot: Relies on the operator remembering at merge time.
- **Note**: A and B compose — A is the guard, B is the step. Doing both is cheap.
- **Decision**: FIXED via Fix A + Fix B. Phase 1 §3 now reports the resolved `MEDIA_ROOT` and, at `DEBUG=False`, 500s unless it is absolute and outside `BASE_DIR`; Phase 1 §5 asserts that as an outcome (Progress 1.7). New Phase 4 §10 owns setting `MEDIA_ROOT=/data/media` in Railway and extending `DEPLOY.md` backup/restore to `/data/media`, gated pre-merge by Progress 4.11–4.12; Phase 6 §4 reduced to verifying those against production. Migration Notes now separate the two failure modes the probe covers.

### F2 — Vendored asset list omits leaflet.js.map; collectstatic fails

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 5 §1
- **Detail**: Phase 5 §1 enumerates the "complete" asset set as `leaflet.js`,
  `leaflet.css` and the `images/` directory, with emphatic reasoning about why the CSS
  `url(images/…)` references make `images/` non-optional. That reasoning applies verbatim
  to JS and the plan does not extend it. Verified: `leaflet@1.9.4/dist/leaflet.js` ends
  with `//# sourceMappingURL=leaflet.js.map`, and Django 6.0.5's
  `ManifestStaticFilesStorage` carries a `*.js` sourceMappingURL pattern
  (`django/contrib/staticfiles/storage.py:102`). All four cases run against this repo's
  actual whitenoise storage class:

  ```
  js  missing .map    : FAILED -> MissingFileError: 'leaflet.js.map'
  js  with .map       : SUCCEEDED
  css missing images  : FAILED -> MissingFileError: 'images/layers.png'
  css with images     : SUCCEEDED
  ```

  The plan's CSS reasoning is therefore confirmed, and the JS case is the same outage
  class, unlisted. Phase 5's own CI gate does catch it — but the plan presents this list
  as verified-exhaustive, and the likely misdiagnosis
  (`WHITENOISE_MANIFEST_STRICT`, or downgrading the storage class) is worse than the bug.
- **Fix**: Add `leaflet.js.map` to the vendored file list in Phase 5 §1, and state the
  rule once — every vendored asset's `sourceMappingURL` and `url()` targets must be
  vendored alongside it, or the comment stripped.
- **Decision**: FIXED. Phase 5 §1 now lists `leaflet.js.map` and states the sibling-reference rule once, covering both reference kinds (`url()` and `sourceMappingURL`) with the storage class that resolves them. It also records the correct response to a `MissingFileError` — vendor the missing sibling, never relax `WHITENOISE_MANIFEST_STRICT` or downgrade the storage class.

### F3 — The specified entity-expansion test is unsatisfiable, and the DoS it names is unmitigated

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 4 §9 (Parsing tests); `plan-brief.md` Validation row
- **Detail**: Phase 4 §9 specifies "an XXE / entity-expansion payload is **rejected
  rather than expanded**, asserted on the outcome". Those are two different things, and
  the stdlib backend the plan deliberately pins behaves oppositely on them. Verified
  against this venv's CPython 3.14:

  ```
  external entity (XXE)    -> REJECTED (ParseError: undefined entity)
  internal nested entities -> EXPANDED, 4 levels -> 10,000 chars
  ```

  The XXE half passes trivially and proves nothing. The expansion half, as written,
  fails — `xml.etree.ElementTree` is documented-vulnerable to billion laughs. Four more
  nesting levels inside a file well under the 10 MB cap expands to gigabytes of memory at
  upload time, on an endpoint any authenticated user can hit. The brief's Validation row
  promises "documented XML entity hardening", but no phase specifies a hardening
  *measure* — only a test. That is the promise gap: the implementer will discover the test
  cannot pass, weaken it to XXE-only, and the concern disappears silently.
- **Fix A ⭐ Recommended**: Reject any DOCTYPE/DTD in `gpx/parsing.py` before handing the
  decoded text to `gpxpy`.
  - Strength: Three lines, zero dependencies, closes XXE and billion laughs together, and
    keeps the plan's "one reviewable security file" architecture intact. A legitimate GPX
    file has no internal DTD, so there is no false-positive cost, and it is testable as a
    real outcome assertion.
  - Tradeoff: A text-level pre-check sitting slightly outside `gpxpy` — needs a comment
    explaining why, since the plan already notes ruff will never prompt for it.
  - Confidence: HIGH — expansion behaviour measured directly, not inferred.
  - Blind spot: Does not bound plain non-entity payload size; that is F5.
- **Fix B**: Route parsing through `defusedxml`.
  - Strength: Library-grade, covers classes not enumerated here.
  - Tradeoff: Requires swapping gpxpy's parser backend — which the plan explicitly forbids
    and pins a test against — and adds a dependency to a slice that argued hard against
    adding any.
  - Confidence: MEDIUM — the swap mechanism inside gpxpy is unverified.
  - Blind spot: Interaction with the backend-pinning test is unresolved.
- **Decision**: FIXED via Fix A. `gpx/parsing.py` (Phase 4 §3) now rejects any `<!DOCTYPE` in the decoded text before parsing, raising `GpxParseError`, with a comment recording why the guard sits outside `gpxpy`. The measured stdlib behaviour is in Key Discoveries and the mitigation in Critical Implementation Details, so the brief's "documented XML entity hardening" now has a measure behind it. The single unsatisfiable test is split into two outcome assertions — XXE rejected, nested-entity rejected — the second being what proves the guard exists (Progress 4.5).

### F4 — File deletion inside atomic() is not transactional

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 4 §5; Critical Implementation Details ("Ordering on replace")
- **Detail**: The plan calls the ordering load-bearing and gets it half right: "save the
  new row and file first, delete the old file after, inside a transaction — the reverse
  loses both if the save fails." Storage deletes do not participate in the transaction. If
  the block raises or the commit fails *after* the delete, the DB rolls back and restores
  the old `GpxTrack` row — now pointing at a file that no longer exists. The download view
  404s on a row the detail page still renders a map for: precisely the silent-failure state
  the PRD's NFR forbids, produced by the mitigation meant to prevent it.
- **Fix**: Defer the delete with `transaction.on_commit(...)` rather than performing it
  inside the atomic block, so it runs only once the new row is durable. Update the
  Critical Implementation Details paragraph to say so — that is the paragraph an
  implementer will follow literally.
- **Decision**: FIXED. "Ordering on replace" now splits the two rules — save-before-delete, and delete via `transaction.on_commit(...)` outside the atomic block — and states the rolled-back-row-with-missing-file failure explicitly. Phase 4 §5 matches. Phase 4 §9 adds that `on_commit` callbacks must be captured (`django_capture_on_commit_callbacks`) or the deferred delete is never exercised by the replace test.

### F5 — The 10 MB cap is a validation rule, not a resource bound

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: What We're NOT Doing; Performance Considerations; Open Risks
- **Detail**: The plan states the 10 MB cap is "the only volume bound in v1". It is not a
  volume bound at all — `clean_file()` runs after Django has already received the entire
  request body and spooled it to a `TemporaryUploadedFile`. Nothing upstream limits body
  size: gunicorn has no body cap, and `DATA_UPLOAD_MAX_MEMORY_SIZE` does not apply to
  file-upload fields. A single multi-gigabyte POST fills the container's temp disk before
  any validation code executes. Blast radius is genuinely small — the endpoint is behind
  `LoginRequiredMixin` on a near-private app, consistent with the accepted-risk posture
  already recorded for concurrent signup. The problem is the plan asserting a bound it
  does not have, which is what would stop a future reader from revisiting it.
- **Fix**: Restate it accurately in Open Risks — the cap rejects oversized files but does
  not prevent their upload, and no request-body limit exists in v1. Accept the risk
  explicitly rather than describing it as bounded.
- **Decision**: FIXED. "What We're NOT Doing" gains an explicit "No request-body size limit" entry naming why the cap runs too late, and Performance Considerations separates what the cap bounds (render-time point count) from what it does not (upload-time body size and parse cost). Both are recorded as accepted, not bounded, and the amplification case the F3 DTD guard closes is distinguished from the plain large-payload case it does not.

### F6 — Upload-size settings specified without values

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 §1
- **Detail**: "`DATA_UPLOAD_MAX_MEMORY_SIZE` and `FILE_UPLOAD_MAX_MEMORY_SIZE` are set
  explicitly rather than inherited, making the in-memory vs `TemporaryUploadedFile`
  switchover a deliberate, tested choice." No values are given, and only
  `FILE_UPLOAD_MAX_MEMORY_SIZE` governs that switchover — the rationale attributes it to
  both. Current runtime values are `2621440` each. An implementer reading this could
  reasonably set either to 10 MB, which for `FILE_UPLOAD_MAX_MEMORY_SIZE` means every
  upload is buffered whole in RAM.
- **Fix**: Name the two values and which behaviour each one controls. Keeping
  `FILE_UPLOAD_MAX_MEMORY_SIZE` at the 2.5 MB default — so a real tour GPX spools to disk
  rather than RAM — makes the Phase 4 `seek(0)` contract the tested path rather than the
  rare one.
- **Decision**: FIXED. Phase 1 §1 now pins both at `2621440` (2.5 MB, the current values), splits what each controls, and states the reason not to raise `FILE_UPLOAD_MAX_MEMORY_SIZE` to the 10 MB cap — doing so would buffer every upload in RAM and make `seek(0)` dead code that only breaks in production. `DATA_UPLOAD_MAX_MEMORY_SIZE` is marked as not applying to file fields, cross-referencing the F5 entry.

### F7 — Nothing removes files when a GpxTrack row is deleted

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2 §2, §6
- **Detail**: Django has not deleted `FileField` files on model delete since 1.3. Phase 2's
  test asserts "deleting the trip cascades to its tracks" — and every one of those tracks
  leaves its file on the Volume permanently. No trip-delete UI exists yet (S-04), so
  nothing leaks today, but S-04 will inherit an unbounded orphan-file leak on a
  single-region 3,000-IOPS Volume without knowing it. Separately, the Phase 1 local
  default (`BASE_DIR / "media"`) is not in `.gitignore`, so a dev-server upload lands in
  the working tree — the Phase 1 autouse fixture only covers the test suite.
- **Fix**: Note the orphan-file gap in Migration Notes as a handoff to S-04, and add
  `media/` to `.gitignore` in Phase 1.
- **Decision**: FIXED. Migration Notes gains an explicit S-04 handoff for orphan files, on the same `on_commit` footing as the Phase 4 replace path. Phase 2 §6 now states that the cascade test deliberately asserts rows only, so nobody "fixes" it into a failing file assertion. New Phase 1 §6 adds `media/` to `.gitignore` with manual check 1.10 (a `runserver` write leaves `git status` clean).

### F8 — /healthz/ becomes an unauthenticated filesystem write

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1 §3
- **Detail**: `healthz` is unauthenticated (`velo_log/urls.py:39`) and already writes a
  session row per request; adding a media write/delete makes every anonymous probe touch
  the Volume. Low severity, but if the delete ever fails, storage name-collision
  suffixing means throwaway keys accumulate silently on the same Volume the app depends on.
- **Fix**: Use a single fixed throwaway key so a failed delete overwrites rather than
  accumulates, and delete in a `finally` block.
- **Decision**: PENDING

## Phase Independence — one branch per phase, merged before the next

**Yes, this works.** The dependency graph is strictly linear with no back-edges
(P1 → P2 → P3 → P4 → P5 → P6) and each phase leaves the repo green and committable.
Four caveats:

1. **Six merges to `master` means six production deploys.** `deploy.yml`'s deploy job is
   `if: github.event_name == 'push'` and `gates` runs on pushes to master, so `railway up`
   fires on every merge. This escalates F1 from a plan nit to a live one: **Phase 4 is the
   merge that puts uploads in production**, while the `MEDIA_ROOT` env var (Phase 1's
   `.env.example` only) and the media backup procedure (Phase 6 §4) currently land
   elsewhere. Set the Railway variable and extend `DEPLOY.md`'s backup section *before*
   merging Phase 4, not in Phase 6.
2. **Phases 3, 4 and 5 all edit `trips/views.py` and
   `trips/templates/trips/trip_detail.html`.** Serial merge is what keeps that
   conflict-free — do not run two of them as parallel branches.
3. **Phase 2 alone deploys a migration.** Additive, single new table, safe on the
   unattended `migrate` — but it is the deploy that wants the pre-migration DB backup
   `DEPLOY.md` already prescribes.
4. **Phase 6 cannot be gated by CI** (docs plus a live restore drill). Fine as its own
   branch; its value is the E-05 drill, not the diff.

To cut deploy count, the natural seam is merging P1+P2 together — neither is user-visible.
There is no correctness reason to.

## Incidental notes (not findings)

- `.claude/skills/10x-plan-review/references/progress-format.md`, referenced by the
  skill's mechanical Progress contract, does not exist on disk — only `SKILL.md` is
  present. The Progress block was checked against `SKILL.md`'s inline contract and passes.
- The plan cites `prd.md:104-105` for the data-isolation requirement; the sentence is at
  `prd.md:105`. Cosmetic.
