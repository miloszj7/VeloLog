<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: File Lifecycle and Storage/Row Consistency

- **Plan**: context/changes/testing-file-lifecycle-storage-consistency/plan.md
- **Scope**: Full plan (Phases 1–3, all complete)
- **Date**: 2026-08-30
- **Verdict**: NEEDS ATTENTION
- **Findings**: 1 critical, 1 warning, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | FAIL |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Findings

### F1 — `GpxUploadView`'s re-render never sets `track_file_available`, producing a false "file unavailable" marker on a healthy track

- **Severity**: CRITICAL
- **Impact**: MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: gpx/views.py:67-81 (`GpxUploadView.get_context_data`), contrasted with trips/views.py:99-103
- **Detail**: `TripDetailView.get_context_data` (trips/views.py:99-103) computes `context["track_file_available"]`, and `trips/templates/trips/trip_detail.html:66` branches on it. `GpxUploadView` renders that exact same template on a rejected upload (invalid form → 200 re-render, per its own docstring: "re-render with errors"), but its `get_context_data` (gpx/views.py:67-81) only sets `trip`, `track`, `map_config`, and `stats` — never `track_file_available`. Django templates evaluate an undefined context variable as falsy, so every rejected-upload re-render for a trip whose track file is perfectly healthy on storage renders the `else` branch: "Track file unavailable — the stored file could not be found," with the download link removed — a false negative shown for a file that is not missing at all.

  This is exactly the failure mode `TripDetailView.get_context_data`'s own docstring warns about for `map_config`/`stats` ("either key supplied here and missed there renders a failure branch over healthy data... one of them missed") — the same "two render paths, one template" discipline was not extended to the new key Phase 2 introduced. `tests/gpx/test_gpx_upload.py::test_a_rejected_upload_leaves_an_existing_track_untouched` asserts the row and file both survive a rejected upload, but never inspects the rendered body or `track_file_available`, so the gap shipped through every automated gate green.
- **Fix**: Add `context["track_file_available"] = ...` (the same storage-existence check, ideally factored into one shared helper both views call) to `GpxUploadView.get_context_data`, and add a regression test asserting a rejected-upload re-render still shows the live download link and `track_file_available: True` when the existing track's file is present on storage.
  - Strength: Matches the exact discipline the codebase already documents and enforces for `map_config`/`stats` on this same two-render-path template; a shared helper also removes the duplication between the two views' near-identical existence checks.
  - Tradeoff: Touches a file outside the plan's stated scope (gpx/views.py) — worth a short plan addendum noting the gap, since it wasn't anticipated by Phase 2's Changes Required.
  - Confidence: HIGH — directly reproduced by reading both context builders and the shared template's guard condition; no test currently exercises this path.
  - Blind spot: None significant — the shared-template contract and its failure mode are explicitly documented in-repo.
- **Decision**: FIXED — extracted `track_file_is_available()` into a new `gpx/availability.py` (mirroring the existing `gpx/map_config.py`/`gpx/statistics.py` shared-helper pattern for the two render paths), called from both `TripDetailView.get_context_data` and `GpxUploadView.get_context_data`. Added `tests/gpx/test_gpx_upload.py::test_a_rejected_uploads_rerender_still_shows_the_existing_tracks_live_download_link`, confirmed it fails without the fix and passes with it.

### F2 — `track.file.storage.exists()` call in `TripDetailView` is unguarded, unlike the analogous check in `gpx:download`

- **Severity**: WARNING
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: trips/views.py:99-103
- **Detail**: `gpx/views.py:140-153` wraps its equivalent "is this file actually there" check (`track.file.open("rb")`) in `try/except OSError`, with an explicit comment that a missing/unreachable file is an operational fault that must not fail the request. The new `track.file.storage.exists(track.file.name)` call in `TripDetailView.get_context_data` has no equivalent guard. With the project's current storage backend (`FileSystemStorage`, confirmed in `velo_log/settings.py`) this cannot actually raise — `os.path.exists()` swallows `OSError` internally and returns `False` — so it is not exploitable today, but it is the one "is the file present" check in the codebase that skips the guard discipline the neighboring, near-identical check documents and enforces. A future storage backend change (e.g. to a network/object-store backend, where `exists()` genuinely can raise on connectivity errors) would 500 every trip detail page instead of degrading the way `gpx:download` does.
- **Fix**: Wrap the call in the same `try/except OSError` pattern as `gpx/views.py:140-153` (treating an exception as "not available"), or leave a short comment explaining the call is intentionally unguarded because `FileSystemStorage.exists()` cannot raise — so a future reader doesn't have to rediscover the reasoning `gpx/views.py` already spells out inline.
- **Decision**: FIXED — `gpx/availability.py::track_file_is_available` now wraps `storage.exists()` in `try/except OSError`, returning `False` on failure, with a comment pointing at `GpxDownloadView.get`'s equivalent guard.

## Notes

- **Plan Adherence**: full MATCH across all 6 planned changes (two Phase-1 tests, the Phase-2 view/template change and its tests, the Phase-3 cookbook fill-ins) — no drift, no missing items, no unplanned files in the diff. Verified independently against `git diff --name-only 162992f..05024f9`.
- **Success Criteria**: full suite passes — 316 passed, 2 skipped, 97.35% coverage (`fail_under = 80`). The plan's Phase 1 manual check (invert `reconcile_media.py:218`'s `>` to `>=`, confirm the new boundary test fails) is recorded as done in `## Progress` (1.4) with no independent evidence beyond the checkbox; not re-verified in this review since it is a transient, revert-before-commit action with no artifact to inspect after the fact.
- **Scope Discipline**: "What We're NOT Doing" boundaries respected — no admin bulk-action test, no caching/async added, no new exception type, `gpx/statistics.py`/`gpx/map_config.py`/the backfill command untouched.
