# File Lifecycle and Storage/Row Consistency — Plan Brief

> Full plan: `context/changes/testing-file-lifecycle-storage-consistency/plan.md`
> Research: `context/changes/testing-file-lifecycle-storage-consistency/research.md`

## What & Why

Test-plan Phase 2 covers Risk #1 (a delete/replace path strands or wrongly
removes a track file) and Risk #3 (a trip's row survives but its file becomes
unreachable, and nobody notices). Research found Risk #1 nearly fully proven
already; Risk #3 has a real, silent gap — the trip detail page currently looks
identical whether the file is present or gone.

## Starting Point

`gpx/signals.py`'s two receivers already reclaim files on every delete/replace
path except a two-level `User → Trip → GpxTrack` cascade, and
`reconcile_media`'s age guard is untested at its exact boundary. The trip
detail page (`trips/views.py` + `trip_detail.html`) builds everything from
stored columns and never checks whether the track's file still exists in
storage — `gpx:download` already 404s on a storage miss, but the page itself
gives no signal.

## Desired End State

Deleting a user reclaims their tracks' files two levels down. `reconcile_media`
treats a file aged to exactly the cutoff as an orphan. A trip whose file has
vanished shows a visible "file unavailable" marker on its detail page and a
disabled (non-clickable) download link, instead of looking healthy.
`test-plan.md`'s cookbook sections for this pattern are filled in.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Risk #3 remediation | Add a product-code marker (view + template) | Test-only coverage would just document the silent failure, not close it | Plan (user question) |
| Marker scope | Banner + disable the download link | A live-looking link that 404s partially defeats the point of a deliberate marker | Plan (user question) |
| Storage check cost | One `storage.exists()` per render, no caching | Acceptable at this project's near-private scale; caching would reintroduce staleness | Plan (user question) |
| Two-level cascade test location | `tests/gpx/test_gpx_signals.py` | Matches the risk's actual concern (file/row consistency), not account-deletion semantics | Plan (user question) |
| `reconcile_media` boundary test | Include it | Cheap, closes a known edge in code this phase already touches | Plan (user question) |
| Admin bulk-delete test | Skip — subsumed | Already covered by existing `QuerySet.delete()`/cascade tests; admin CRUD is out of scope per §7 | Plan (user question) |

## Scope

**In scope:**
- Two-level cascade test (`User` → `Trip` → `GpxTrack`)
- `reconcile_media` exact age-boundary test
- Trip detail view + template: storage-presence check and deliberate marker
- Tests for the new marker, both branches (present/missing)
- `test-plan.md` §6.3, §6.5, §6.7 cookbook updates

**Out of scope:**
- Admin "delete selected tracks" bulk-action test (subsumed)
- Caching or async deferral of the new storage check
- A new exception type for "file missing from storage"
- Any change to `gpx/statistics.py`, `gpx/map_config.py`, or the backfill command

## Architecture / Approach

Phase 1 closes the two residual Risk #1 gaps as pure test additions against
unchanged code. Phase 2 makes the one product change this rollout phase
needs — a boolean context value plus one template branch, mirroring the
project's existing "deliberate empty state" pattern already used for the map
fallback and unscored stats. Phase 3 is the mandatory cookbook write-back.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Cascade + boundary tests | Two-level cascade and exact age-boundary coverage | Boundary test needs precise clock control, not real-time back-dating |
| 2. Detail-page marker | Deliberate "file unavailable" state + disabled download link | Template branch must not leak into the map/stats sections it sits beside |
| 3. Cookbook update | §6.3/§6.5/§6.7 filled in with this phase's patterns | None — mechanical write-back |

**Prerequisites:** None beyond the existing test suite and fixtures.
**Estimated effort:** ~1 session across 3 phases — Phase 1 and 3 are small; Phase 2 is the only one touching product code.

## Open Risks & Assumptions

- The boundary test's precise clock-freezing approach (monkeypatching both
  `timezone.now` and `default_storage.get_modified_time`) is new to this test
  file — if it proves awkward in practice, a documented near-miss (cutoff ± 1
  second) with a comment explaining why exact equality isn't feasible is an
  acceptable fallback.
- The marker's exact wording is illustrative in the plan; the implementer
  should follow the file's existing deliberate-state phrasing conventions
  (naming the cause, not just "error").

## Success Criteria (Summary)

- A rider who deletes their account never leaves a track file behind, two
  cascade levels down.
- `reconcile_media` orphans a file at exactly its age cutoff, not just past it.
- A rider looking at a trip whose file has vanished sees that fact on the
  page itself, not only when they click Download.
