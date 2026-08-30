# Rejection and Degradation Coverage — Plan Brief

> Full plan: `context/changes/testing-rejection-and-degradation/plan.md`
> Research: `context/changes/testing-rejection-and-degradation/research.md`

## What & Why

Test-plan Phase 3 covers Risk #5 (a hostile upload leaves a row or file behind) and
Risk #6 (the trip detail page blanks out instead of degrading). Research found both
risks already substantially proven — this plan closes the four specific, named gaps
that remain rather than re-building rejection/degradation coverage from scratch.

## Starting Point

`GpxUploadForm.clean_file()` already rejects every malformed/hostile input with a
distinct, content-asserted message, and never calls `.save()` on rejection — but no test
asserts storage stayed empty. `TripDetailView`'s render path already degrades cleanly
for a missing track, a missing file, or null statistics — each individually tested — but
never in combination.

## Desired End State

Every rejection test proves no file reached storage. Two named edge-case inputs (empty,
truncated) are pinned as their own tests even though they currently share a code branch
with existing coverage. One test proves the two Risk #6 degradation branches compose.
The cookbook (`test-plan.md` §6) names this phase's reference tests for future test
authors.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Storage-debris assertion | Retrofit all 7 existing rejection tests | Matches the risk's own wording ("a malformed **or hostile** upload") — one consolidated test would only prove it for one rejection reason | Plan |
| Combined degradation case | Add one new integration test | Isolated tests can't show whether one branch suppresses the other; `make_stored_track` + a storage delete gives the combination for free (stats already null) | Plan |
| Uncaught non-`GPXException` path (`gpx/parsing.py:269-277`) | Accept as documented residual risk | Only reachable via a bug in gpxpy's own point typing; same treatment as the already-accepted `DATA_UPLOAD_MAX_MEMORY_SIZE` gap | Plan |
| Empty/truncated upload tests | Add both as named unit tests, even though they share a branch today | Pins the phase's explicitly named scenarios at near-zero cost; protects against a future change that splits the branch | Plan |

## Scope

**In scope:**
- Storage-emptiness assertion added to 7 existing rejection tests
- Two new parsing-unit tests (empty upload, truncated upload)
- One new combined-degradation integration test
- `test-plan.md` §6.1, §6.4, §6.7 cookbook updates

**Out of scope:**
- Any change to `gpx/parsing.py`, `gpx/forms.py`, `trips/views.py`,
  `gpx/statistics.py`, or `gpx/map_config.py` — all already correct
- The uncaught non-`GPXException` point-processing path — documented, not closed
- The `DATA_UPLOAD_MAX_MEMORY_SIZE` upload-body-size gap — already an accepted v1 gap

## Architecture / Approach

Test-only phase. No production code changes. Reuses two existing idioms verbatim: the
`assert not (tmp_path / "media").exists()` storage-emptiness check from
`test_reconcile_media.py`, and the `make_stored_track` + `default_storage.delete(name)`
storage-miss pattern from the existing isolated degradation tests.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Storage-debris coverage | Every rejection test proves storage stayed empty | Retrofitting 7 tests touches a lot of lines for one assertion each — mechanical, low risk |
| 2. Empty & truncated upload rejection | Two new named unit tests, residual risk documented | Both tests currently exercise an already-covered branch — value is in the pin, not new coverage |
| 3. Combined degradation + cookbook | One new integration test; §6.1/§6.4/§6.7 filled in | Low — reuses existing fixtures with no new ones needed |

**Prerequisites:** None — all patterns already exist in the suite.
**Estimated effort:** ~1 session, 3 small phases.

## Open Risks & Assumptions

- The empty/truncated tests assume both inputs fail XML well-formedness before any
  GPX-specific check runs (confirmed by reading `gpx/parsing.py` directly, not by a
  prior test run) — if a future gpxpy version changes this, the tests will still pass,
  just via a different underlying path than described here.

## Success Criteria (Summary)

- No rejection test passes while a file was actually written to storage.
- The suite fails loudly if the empty/truncated upload paths, or the combined
  degradation branches, ever regress.
- A future contributor adding a similar test can follow `test-plan.md` §6.1/§6.4 without
  re-deriving these patterns.
