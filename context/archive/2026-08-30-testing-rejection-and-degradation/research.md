---
date: 2026-08-30T18:59:20+02:00
researcher: Claude
git_commit: a7cc8e44c46e861422dbaa4c01cd250ccadf6d76
branch: master
repository: VeloLog
topic: "Rejection and degradation — Risk #5 (hostile/malformed upload) and Risk #6 (trip detail degrades, never breaks)"
tags: [research, codebase, gpx, trips, upload-validation, empty-state]
status: complete
last_updated: 2026-08-30
last_updated_by: Claude
---

# Research: Rejection and degradation (test-plan.md Phase 3)

**Date**: 2026-08-30T18:59:20+02:00
**Researcher**: Claude
**Git Commit**: a7cc8e44c46e861422dbaa4c01cd250ccadf6d76
**Branch**: master
**Repository**: VeloLog

## Research Question

For Phase 3 of `context/foundation/test-plan.md` — "Rejection and degradation" (Risks #5 and #6) — ground where the actual rejection and degradation contracts live in the codebase today, what already proves them, and what (if anything) is genuinely missing, so `/10x-plan` can scope real work rather than re-prove settled ground.

## Summary

**Both risks are already substantially implemented and tested** — this phase's premise is partially false in the same way Phase 1's was (test-plan.md §6.7): the product behavior test-plan.md worried about mostly already exists, with content-level (not status-code-only) assertions already in place. The real work for this phase is closing a small number of concrete, named gaps rather than building the rejection/degradation contract from scratch:

- **Risk #5 (upload rejection)**: `GpxUploadForm.clean_file()` (`gpx/forms.py:36-94`) already rejects oversized, wrong-extension, malformed-XML, non-GPX-XML, too-many-points, and undecodable uploads — each with a distinct, content-asserted message, and each leaving `GpxTrack.objects.count() == 0` (`tests/gpx/test_gpx_upload.py:142-289`). Parsing happens entirely inside form validation, before `.save()` is ever called, so on rejection no model instance is created and no `FileField` write is triggered (`gpx/forms.py:59-94`, confirmed structurally, not by a storage-emptiness assertion). **Two concrete gaps**: (a) no test asserts the *file* side of "no debris" — every existing rejection test checks `GpxTrack.objects.count() == 0` but none checks `default_storage` for an orphaned write (`tests/gpx/test_gpx_upload.py:142-289` — `default_storage` is imported and used elsewhere in the file for successful-path assertions, e.g. line 307, 358, but never in a rejection test); (b) a genuinely empty (0-byte) upload is not tested at either the parsing-unit or upload-integration layer — the closest existing case, `empty-track.gpx` (`tests/gpx/test_gpx_parsing.py:246-253`), is a well-formed GPX document with zero *trackpoints*, not a zero-byte file, and a raw truncated-mid-tag XML case has no test of its own name (it likely resolves via the same `GPXXMLSyntaxException` → `GpxSyntaxError` path as the existing malformed-XML test, but that's an inference, not a proven fact).
- **Risk #6 (trip detail degradation)**: `TripDetailView` (`trips/views.py:85-102`) already delegates a missing track (`track = self.object.tracks.first()` → `None`) to two total, `None`-safe builder functions — `build_map_config` (`gpx/map_config.py:38-39`) and `build_trip_stats` (`gpx/statistics.py:225-239`) — and the template (`trips/templates/trips/trip_detail.html`) already has a distinct, content-asserted empty-state sentence for every combination: no track at all (line 153, "No route yet…"), an unrenderable/empty map (line 76, "This route could not be displayed…"), a missing stored file (line 89, "Track file unavailable…"), and unbackfilled stats (line 147, "These stats have not been worked out…") plus per-field "Not recorded" gating (lines 124-138, deliberately `is not None`, not truthy, to preserve a real `0` from being mistaken for "absent"). All of these already have passing tests asserting body content, not just status code (`tests/trips/test_trip_detail.py:56-64`, `test_trip_detail_stats.py` five cases, `test_trip_detail_map.py` three cases). **One concrete gap**: no test exercises the *combined* case of a track whose stored file is missing from storage **and** whose statistics are null simultaneously (each is tested in isolation only).

This phase's plan should therefore scope narrowly: (1) a storage-emptiness assertion added to the existing rejection tests (or one new test using the existing pattern) for Risk #5's debris question, (2) a genuinely empty (0-byte) upload test and — if distinguishable from the malformed-XML path — a named truncated-file test, and (3) optionally one combined-degradation test for Risk #6 if `/10x-plan` judges the isolated coverage insufficient signal. This is a much smaller phase than "build rejection and degradation tests" — it is "close two named debris/empty-input gaps and confirm one combination."

## Detailed Findings

### Upload rejection path (Risk #5)

- **View entry and authorization**: `GpxUploadView` (`gpx/views.py:29-122`), POST-only. `post()` (`gpx/views.py:47-55`) resolves the target `Trip` via an owner-scoped `get_object_or_404` in `get_trip()` (`gpx/views.py:57-66`) *before* the file is touched — a cross-user POST 404s regardless of upload content.
- **Validation order in `clean_file()`** (`gpx/forms.py:36-94`), cheapest check first:
  1. Size: `uploaded.size > MAX_GPX_FILE_BYTES` → `ValidationError` ("larger than 10 MB") — `gpx/forms.py:53-54`; `MAX_GPX_FILE_BYTES = 10 * 1024 * 1024` (`gpx/constants.py:7-8`).
  2. Extension: must end `.gpx`, case-insensitive — `gpx/forms.py:55-57`; `ALLOWED_GPX_EXTENSIONS = (".gpx",)` (`gpx/constants.py:13`), explicitly documented as "a convenience filter for the user, not a security control" (`gpx/constants.py:10-12`).
  3. Parse: `parse_gpx_bytes(uploaded.read())` (`gpx/forms.py:59-77`), wrapped in try/except mapping each parsing exception to a distinct `ValidationError` message.
- **Parsing internals** (`gpx/parsing.py`):
  - Single `gpxpy.parse()` call site at `gpx/parsing.py:258`, preceded by a hand-rolled `<!DOCTYPE` guard (`gpx/parsing.py:254-255`) blocking billion-laughs-style entity expansion (the pinned stdlib ElementTree backend doesn't guard this itself).
  - `GPXXMLSyntaxException` → `GpxSyntaxError` ("not well-formed XML"); `GPXException` (base) → `GpxContentError` ("not valid GPX") — `gpx/parsing.py:257-264`.
  - Zero track points (well-formed GPX, no points): explicit post-parse check, `GpxContentError` — `gpx/parsing.py:281-282`.
  - Too many points: `len(points) > MAX_GPX_POINTS` (100,000) → `GpxTooManyPointsError` — `gpx/parsing.py:288-289`, `gpx/constants.py:22`.
  - Encoding: `parse_gpx_bytes()` (`gpx/parsing.py:196-213`) tries UTF-8, falls back to a declared encoding sniffed from the XML declaration, re-raises `GpxEncodingError` if both fail.
  - Every exception type gpxpy can raise for empty/truncated/malformed/non-GPX/oversized content is caught by name; an uncaught, non-`GPXException` failure (e.g. a bug elsewhere in the point-processing loop, `gpx/parsing.py:269-277`, which sits outside the try/except) is the only remaining path to a genuine 500 — this is a residual risk, not something the plan needs to close by itself, but the plan should decide whether it's in scope.
- **Row/file ordering and transaction boundary**: `clean_file()` parses and populates derived fields on `self.instance` (`gpx/forms.py:84-93`) but never calls `.save()`. Persistence happens only in `GpxUploadView.form_valid()` → `super().form_valid(form)` (`gpx/views.py:120`), Django's standard `ModelFormMixin.form_valid` → `form.save()`, inside `transaction.atomic()` (`gpx/views.py:107`). **On a rejected upload, this code path is never reached at all** — `ValidationError` in `clean_file` stops Django's form machinery before `.save()`. This is the structural reason no row and no file exist after rejection, but no existing test verifies the storage side of that claim (see Summary).
- **Documented ordering risk (not this phase's target, but adjacent)**: `gpx/constants.py:48-51` notes `FileField.pre_save` commits the upload to storage *before* the row's INSERT on the *success* path — a possible file-without-row window on a mid-`save()` failure, which `manage.py reconcile_media` exists to reconcile. This is Risk #1/#7 territory (Phases 2/4), not Risk #5.
- **User-facing surfacing**: standard Django ModelForm errors — the view re-renders `trips/trip_detail.html` at 200 with the bound form's errors inline, not a redirect (`gpx/views.py:39`, confirmed by `tests/gpx/test_gpx_upload.py:186-199`).
- **Settings**: `FILE_UPLOAD_MAX_MEMORY_SIZE` / `DATA_UPLOAD_MAX_MEMORY_SIZE` both `2621440` (2.5 MB), explicitly written out rather than left as Django defaults (`velo_log/settings.py:177-186`) — `DATA_UPLOAD_MAX_MEMORY_SIZE` bounds non-file request data only, so there is **no hard server-side ceiling on upload body size** before `MAX_GPX_FILE_BYTES` is checked in `clean_file`; this is a documented, accepted v1 gap (`gpx/constants.py:3-6`), not something this phase should try to close.

### Trip detail degradation path (Risk #6)

- **View**: `TripDetailView.get_context_data` (`trips/views.py:85-102`) does `track = self.object.tracks.first()` (→ `None` if no `GpxTrack` row, no exception on an empty related manager), then passes `track` straight into `build_map_config(track)`, `build_trip_stats(track)`, `track_file_is_available(track)` — all three are `GpxTrack | None`-total, so the view itself never branches on "no track"; it delegates entirely.
- **`build_trip_stats`** (`gpx/statistics.py:206-245`): returns `None` if `track is None` (line 225-226) or if all four stat columns are `None` (deliberate legacy/never-backfilled case, `all(...)` rather than falsy check to preserve a real `0.0`, comment `gpx/statistics.py:219-223`). Otherwise returns a `TripStats` dataclass where each field can *independently* be `None` (partial data).
- **`build_map_config`** (`gpx/map_config.py:22-54`): returns `None` if `track is None or not track.points` (line 38-39) — covers both "no track" and "a track row with an empty points list" (documented as reachable only via admin/legacy rows, since `parse_gpx` rejects zero-point tracks at upload time).
- **Template branches** (`trips/templates/trips/trip_detail.html`):
  - `{% if track %}` (line 41) / `{% else %}` (150-154): no-track case renders "No route yet — this trip has no GPX file uploaded, so there is nothing to map." and *no* stats section at all.
  - `{% if map_config %}` (44) / `{% else %}` (70-77): unrenderable map renders "This route could not be displayed. The file is still attached and can be downloaded below." with no `<div id="map">`.
  - `{% if track_file_available %}` (78) / `{% else %}` (83-91): missing stored file renders "Track file unavailable — the stored file could not be found."
  - `{% if stats %}` (113) / `{% else %}` (140-148): unbackfilled stats render "These stats have not been worked out for this route. Uploading the GPX file again will calculate them."; when `stats` exists, each field is separately gated `{% if stats.X is not None %}` (124, 132, 135, 138) with its own "Not recorded — …" sentence.
  - No generic "empty state" CSS marker exists — every case has its own distinguishing prose sentence, and existing tests assert those sentences as content.
- **Already-passing content-level tests** (not status-code-only):
  - `tests/trips/test_trip_detail.py:56-64` — no track → 200, "No route yet" in body.
  - `tests/trips/test_trip_detail_stats.py` — partial-null stats (line 95), all-elevation-null (122), all-stats-null "point at re-upload" (137), no-track "no stats section at all" (159), stored-zero-renders-as-value (212).
  - `tests/trips/test_trip_detail_map.py` — no-track "no map container" (160), stored zero-points track "says so instead of rendering empty map" (174), map fallback paragraph present alongside a healthy map (70).

## Code References

- `gpx/forms.py:36-94` — `GpxUploadForm.clean_file`, the full validation chain (size → extension → parse)
- `gpx/parsing.py:196-213,246-289` — encoding fallback, DOCTYPE guard, `gpxpy.parse` call, zero-point and too-many-points checks
- `gpx/constants.py:3-22` — `MAX_GPX_FILE_BYTES`, `ALLOWED_GPX_EXTENSIONS`, `MAX_GPX_POINTS`, with the "validation rule, not a resource bound" comment
- `gpx/views.py:47-66,89-122` — `GpxUploadView.post`/`get_trip` (owner scoping) and `form_valid` (atomic save + supersede-delete)
- `velo_log/settings.py:177-186` — `FILE_UPLOAD_MAX_MEMORY_SIZE`/`DATA_UPLOAD_MAX_MEMORY_SIZE`, explicitly literal
- `tests/gpx/test_gpx_upload.py:142-289` — every existing rejection test (size, extension, malformed XML, non-GPX XML, point cap, encoding, no-file); none asserts `default_storage` emptiness
- `tests/gpx/test_gpx_upload.py:307,358,371-372,413,443` — the file's only `default_storage.exists(...)` assertions, all on success/replace paths, showing the pattern to reuse for a debris check
- `tests/gpx/test_gpx_parsing.py:246-253` — `empty-track.gpx` fixture: zero *trackpoints*, not a zero-byte file — the nearest existing case to, but not actually, "empty upload"
- `trips/views.py:85-102` — `TripDetailView.get_context_data`, the `None`-delegation pattern
- `gpx/statistics.py:206-245` — `build_trip_stats`, the `all(None)` legacy-row check
- `gpx/map_config.py:22-54` — `build_map_config`, the `track is None or not track.points` check
- `trips/templates/trips/trip_detail.html:41-154` — all four degradation branches with their literal copy
- `tests/trips/test_trip_detail.py:56-64`, `tests/trips/test_trip_detail_stats.py`, `tests/trips/test_trip_detail_map.py` — existing content-level degradation tests

## Architecture Insights

- **The project consistently treats "clean rejection" as: reject inside form validation, before any `.save()` call, so debris is structurally impossible rather than cleaned up after the fact.** This is a stronger guarantee than a try/except-and-rollback pattern would give, but it has never been *proven* by a storage-side assertion — only inferred from `GpxTrack.objects.count() == 0`.
- **Degradation is achieved by making the render-path builder functions total over `Optional[GpxTrack]`, not by exception handling in the view.** `build_map_config` and `build_trip_stats` are pure functions that return `None` for every "nothing to show" case, and the template is the only place that turns `None` into user-facing copy. This mirrors the Phase 2 finding (`context/archive/2026-08-30-testing-file-lifecycle-storage-consistency/research.md:178`) that statistics/map rendering is deliberately decoupled from file presence.
- **Every degradation branch has its own distinct sentence, asserted as content in existing tests** — this project already follows the `lessons.md` #1 rule ("a test whose name claims an assertion must actually make it") for this risk area, unlike the situation that rule was originally written to correct.

## Historical Context (from prior changes)

- `context/foundation/prd.md:91` (Non-Functional Requirements) — "Silent failures on map generation are not acceptable — if the map cannot be rendered, the user receives a clear error state, not a blank page." Direct source for Risk #6's must-challenge column in test-plan.md §2.
- `context/foundation/prd.md:97` (Business Logic) — "A trip with no uploaded file is a valid empty draft — the map and stats views are unavailable until a file is attached." Confirms the no-track empty state is intended product behavior, not a defect being tested defensively.
- `context/foundation/prd.md:54-56` (US-01 acceptance criteria) — "A trip with no uploaded GPX file does not show a broken map — it shows a clear empty state." Matches the already-implemented `{% else %}` branch verbatim in intent.
- `context/archive/2026-08-23-upload-gpx-and-view-map/plan.md:627-663` — the original design of `parse_gpx`/`clean_file`, including the explicit note: "`clean_file()` reads the upload to parse it and must `seek(0)` before returning, or the subsequent storage write persists a truncated file — a bug that passes a status-code test and fails only a content test." This is the same "debris is separate from rejection" concern the current phase's intent restates; it was already solved for the *successful*-upload byte-fidelity case (`tests/gpx/test_gpx_upload.py:33`, "persists the exact bytes that were submitted") but never extended to a *rejected*-upload storage-emptiness case.
- `context/archive/2026-08-23-upload-gpx-and-view-map/plan.md:750-769` — the original test contract already included malformed XML, non-GPX XML, zero-point track, XXE, and nested-entity payloads, all asserted with error text rather than status code alone, per `lessons.md` #1.
- `context/archive/2026-08-30-testing-file-lifecycle-storage-consistency/plan.md:279` ("What We're NOT Doing") — "Not touching `gpx/statistics.py`, `gpx/map_config.py`, or the backfill command — all three are already correctly decoupled from file presence and already tested for their own storage-miss behavior." Phase 3 inherits this as settled ground for the *presence-but-gone-from-storage* case; the *absence* case (no track row, or null stats) is this phase's actual territory and is, per the findings above, also already covered.
- `context/foundation/test-plan.md` §6.7 Phase 1 note — "The brief's premise was already false… worth remembering when opening the remaining phases: verify the gap before building for it." This phase's finding follows the same shape: verify before build, and here too the premise is largely already true.

## Related Research

- `context/archive/2026-08-23-upload-gpx-and-view-map/research.md` and `plan.md` — original upload/parsing design
- `context/archive/2026-08-30-testing-file-lifecycle-storage-consistency/research.md` and `plan.md` — Phase 2, storage/row consistency for the *presence* side of the same decoupling this phase's Risk #6 exercises on the *absence* side

## Open Questions

1. **Storage-debris assertion for rejected uploads**: should `/10x-plan` add a `default_storage`-emptiness (or directory-listing) assertion to each existing rejection test, or write one new consolidated test? The existing pattern at `tests/gpx/test_gpx_upload.py:307` (`assert default_storage.exists(...)`) is directly reusable in the negative.
2. **Genuinely empty (0-byte) upload**: does it need its own test, or is it provably equivalent to the existing malformed-XML path? A 0-byte file fails `gpxpy.parse` differently than a partial/truncated XML document (likely a different `GPXXMLSyntaxException` message, or possibly an entirely empty string bypassing the DOCTYPE check trivially) — worth a quick confirming run before deciding whether it's a distinct test or covered by assertion generalization.
3. **Truncated (cut-off mid-document) upload**: same question as above — is a dedicated test warranted, or does "malformed XML" already stand in for it structurally? The phase's own intent names it explicitly ("empty, truncated, non-GPX, and oversized"), so `/10x-plan` should decide deliberately rather than let it fall through as "close enough to malformed."
4. **Combined degradation (missing stored file + null stats)**: is isolated per-dimension coverage sufficient signal, or does the phase want one test proving the two branches compose correctly (i.e., the template doesn't short-circuit one degradation state and hide the other)?
5. **Should the residual "uncaught non-`GPXException` failure → possible 500" path (`gpx/parsing.py:269-277`, outside any try/except) be in scope for this phase, or is it accepted risk** (analogous to the accepted `DATA_UPLOAD_MAX_MEMORY_SIZE` gap)? Not raised by the original phase intent, but surfaced by this research — `/10x-plan` should make an explicit call rather than let it be silently out of scope.
