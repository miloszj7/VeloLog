# Rejection and Degradation Coverage Implementation Plan

## Overview

Close the named gaps `research.md` found in Risk #5 (upload rejection) and Risk #6
(trip detail degradation). Both risks are already substantially implemented and
tested — rejection happens entirely inside form validation before any `.save()` call,
and every degradation branch already has its own content-asserted test. This plan adds
the four specific proofs that were missing: a storage-emptiness assertion on rejection,
two named edge-case unit tests, and one test proving two degradation branches compose
correctly — plus documenting what stays deliberately out of scope.

## Current State Analysis

- `GpxUploadForm.clean_file()` (`gpx/forms.py:36-94`) rejects oversized, wrong-extension,
  malformed-XML, non-GPX-XML, too-many-points, and undecodable uploads, each with a
  distinct message, and each already asserted against `GpxTrack.objects.count() == 0`
  in `tests/gpx/test_gpx_upload.py:142-289`. No existing rejection test checks whether
  a file was written to storage.
- `tests/conftest.py`'s autouse `_media_root_in_tmp_path` fixture points `MEDIA_ROOT` at
  a fresh `tmp_path / "media"` per test. `tests/gpx/test_reconcile_media.py:558` already
  establishes the idiom for asserting nothing was written there:
  `assert not (tmp_path / "media").exists()`.
- `gpx/parsing.py:196-213` decodes, then `parse_gpx` (`gpx/parsing.py:231-289`) checks
  DOCTYPE, parses via `gpxpy.parse`, and rejects zero-point and over-cap tracks. A 0-byte
  input and a truncated-mid-tag input both resolve via `gpxpy.parse` raising
  `GPXXMLSyntaxException` → `GpxSyntaxError` — the same branch the existing
  `test_malformed_xml_is_a_syntax_error` test already exercises, confirmed by reading
  the parse path directly (no DOCTYPE match on either input; both fail XML well-formedness
  before any GPX-specific check runs).
- `trips/views.py:85-102` delegates a missing track to `build_map_config` and
  `build_trip_stats`, both total over `GpxTrack | None`. `tests/trips/test_trip_detail.py`
  already covers "file missing from storage, stats present" (line 115-136) in isolation;
  `tests/trips/test_trip_detail_stats.py` already covers "stats null, file present" (line
  137-155) in isolation. Neither combines both conditions on one track.
- `GpxTrack`'s four statistics columns are `null=True` with no default
  (`gpx/models.py:46-57`). `make_stored_track` (`tests/conftest.py:157-184`) never sets
  them, so a track it builds already has null stats — combining it with
  `default_storage.delete(name)` (the existing storage-miss idiom from
  `tests/trips/test_trip_detail.py:114-136`) produces the combined case with no new
  fixture required.

## Desired End State

- Every existing rejection test in `tests/gpx/test_gpx_upload.py` that currently
  asserts `GpxTrack.objects.count() == 0` also asserts storage received no write.
- `tests/gpx/test_gpx_parsing.py` has a named test for a 0-byte upload and a named test
  for a truncated-mid-document upload, each pinning today's behavior (rejection via the
  syntax-error branch) so a future change that splits that branch is caught.
- One integration test proves the trip detail page renders both the "file unavailable"
  marker and the "stats not worked out" sentence together, on the same track, without
  either branch suppressing the other.
- `test-plan.md` §6.1, §6.4, and §6.7 name this phase's reference tests.

### Key Discoveries:

- `gpx/forms.py:59-94` never calls `.save()` on a rejected upload — persistence happens
  only in `GpxUploadView.form_valid()` (`gpx/views.py:120`), so a rejected request
  structurally cannot write to storage. This plan adds the assertion that proves it, not
  a fix.
- `tests/gpx/test_reconcile_media.py:558` is the exact existing idiom to reuse:
  `assert not (tmp_path / "media").exists()`.
- `make_stored_track` already produces null stats as a side effect of not setting them —
  the combined-degradation test needs no new fixture.

## What We're NOT Doing

- Not adding a guard or a test for the uncaught, non-`GPXException` path in the
  point-processing loop (`gpx/parsing.py:269-277`, outside any try/except). Reachable
  only by a bug in gpxpy's own point typing (it types `lat`/`lon` as floats before this
  loop runs), and treated the same as the already-accepted
  `DATA_UPLOAD_MAX_MEMORY_SIZE` gap (`gpx/constants.py:3-6`): a documented, accepted
  residual risk, not something this phase closes.
- Not touching `gpx/parsing.py`, `gpx/forms.py`, `trips/views.py`, `gpx/statistics.py`,
  or `gpx/map_config.py` — every behavior this phase proves already exists correctly.
  This is a test-only phase.
- Not adding a dedicated oversized-upload debris test beyond the retrofit — the existing
  oversized-upload rejection test gets the same storage-emptiness assertion as the other
  six, not a new test of its own.

## Implementation Approach

Three phases, ordered cheapest-and-most-isolated first: retrofit existing tests, then
add two small new unit tests, then add one new integration test and update the cookbook.
Each phase is independently committable and touches a disjoint set of files.

## Phase 1: Storage-debris coverage for rejected uploads (Risk #5)

### Overview

Add a storage-emptiness assertion to every existing rejection test in
`tests/gpx/test_gpx_upload.py` that currently only asserts `GpxTrack.objects.count() ==
0`, proving no file reaches storage on a rejected upload.

### Changes Required:

#### 1. Rejection tests get a storage assertion

**File**: `tests/gpx/test_gpx_upload.py`

**Intent**: Each of the seven existing tests that reject an upload for a content or
form reason (oversized, wrong extension, malformed XML, non-GPX XML, over point cap,
undecodable encoding, no file provided) adds one line asserting the per-test `MEDIA_ROOT`
received no write.

**Contract**: Add `tmp_path: Path` to each affected test's parameters (import `Path`
from `pathlib`) and append `assert not (tmp_path / "media").exists()` after the existing
`GpxTrack.objects.count() == 0` assertion — the exact idiom already used in
`tests/gpx/test_reconcile_media.py:558`. Affected tests:
`test_a_file_over_the_size_cap_is_rejected_with_a_visible_message`,
`test_a_non_gpx_extension_is_rejected_with_a_visible_message`,
`test_malformed_xml_is_rejected_with_the_error_shown_on_the_page`,
`test_a_valid_xml_file_that_is_not_a_track_is_rejected_with_its_own_message`,
`test_a_track_over_the_point_cap_is_rejected_with_the_limit_named`,
`test_an_undecodable_file_is_rejected_for_its_encoding_not_its_xml`,
`test_a_post_with_no_file_is_rejected_without_reaching_the_parser`.

### Success Criteria:

#### Automated Verification:

- Unit/integration tests pass: `uv run pytest tests/gpx/test_gpx_upload.py -v`
- Full suite still passes: `uv run pytest --cov`
- Lint, format, import order, strict typing all pass (`/python-quality-gates`)

#### Manual Verification:

- Break the claim deliberately (temporarily call `.save()` before raising in one
  branch of `clean_file`), confirm the new assertion in that test goes red, then revert.

---

## Phase 2: Empty and truncated upload rejection (Risk #5)

### Overview

Add two named unit tests pinning the phase's explicitly stated "empty" and "truncated"
scenarios, and record the one deliberately-out-of-scope residual risk research surfaced.

### Changes Required:

#### 1. Two new parsing-unit tests

**File**: `tests/gpx/test_gpx_parsing.py`

**Intent**: Pin that a genuinely empty (0-byte) upload and a truncated (cut off
mid-tag) upload both reject via the same `GpxSyntaxError` branch the existing
`test_malformed_xml_is_a_syntax_error` exercises — named individually per the phase's
stated intent, even though today they share one branch, so a future change that splits
that branch is caught rather than silently passing.

**Contract**: Two new test functions, following the file's existing bare-`pytest.raises`
pattern (no fixture needed — both use inline bytes, not the `gpx_bytes` fixture):
`test_an_empty_upload_is_a_syntax_error` calling `parse_gpx_bytes(b"")`, and
`test_a_truncated_document_is_a_syntax_error` calling
`parse_gpx_bytes(b'<?xml version="1.0"?><gpx><trk><trkseg><trkpt lat="50.06" lon=')` —
each wrapped in `with pytest.raises(GpxSyntaxError):`.

#### 2. Document the accepted residual risk

**File**: `context/changes/testing-rejection-and-degradation/plan.md` (this file, already
done above in "What We're NOT Doing") — no code change; this sub-phase is the decision
record only, no separate file edit beyond what Phase 2 ships.

### Success Criteria:

#### Automated Verification:

- Unit tests pass: `uv run pytest tests/gpx/test_gpx_parsing.py -v`
- Full suite still passes: `uv run pytest --cov`
- Lint, format, import order, strict typing all pass (`/python-quality-gates`)

#### Manual Verification:

- Confirm both new tests fail if `GpxSyntaxError` is temporarily replaced with a bare
  `Exception` in `gpx/parsing.py`'s `GPXXMLSyntaxException` branch, then revert.

---

## Phase 3: Combined degradation coverage (Risk #6) and cookbook update

### Overview

Prove the trip detail page renders both the "file unavailable" marker and the "stats
not worked out" sentence together on one track, then fill in the test-plan.md cookbook
entries this phase's patterns answer.

### Changes Required:

#### 1. Combined degradation test

**File**: `tests/trips/test_trip_detail.py`

**Intent**: Prove the two Risk #6 degradation branches (missing stored file, null
statistics) compose — that rendering one does not suppress or corrupt the other. This is
the one combination the existing isolated tests (`test_trip_detail.py:114-136` for the
file, `test_trip_detail_stats.py:137-155` for the stats) do not exercise together.

**Contract**: New test `test_a_missing_file_and_unbackfilled_stats_both_render_together`
using `make_stored_track` (which leaves stats null by not setting them) plus
`default_storage.delete(name)` on the resulting track's file name — the same two steps
`test_a_rider_sees_a_deliberate_marker_when_the_track_file_is_missing` already performs —
then asserting both `"Track file unavailable" in body` and the stats module's
re-upload sentence (`RE_UPLOAD_SENTENCE` from `test_trip_detail_stats.py`, or the literal
string `"These stats have not been worked out for this route."`) are present in the same
response body.

#### 2. Cookbook update

**File**: `context/foundation/test-plan.md`

**Intent**: Fill in the two `TBD` cookbook sub-sections this phase answers, and add the
Phase 3 retrospective note to §6.7, following the existing style of §6.7's Phase 1 and
Phase 2 entries.

**Contract**:
- §6.1 "Reference test" line: point at
  `test_an_empty_upload_is_a_syntax_error` in `tests/gpx/test_gpx_parsing.py` as the
  parse-rejection pattern (malformed/edge-case input yields a named error, not a server
  error).
- §6.4 "Adding a test for an empty or degraded page state": replace the `TBD` with the
  deliberate-empty-state pattern, referencing
  `test_a_rider_sees_a_deliberate_marker_when_the_track_file_is_missing` in
  `tests/trips/test_trip_detail.py` as the single-dimension reference test and
  `test_a_missing_file_and_unbackfilled_stats_both_render_together` as the
  combined-dimension reference test.
- §6.7: add a "Phase 3 — Rejection and degradation" bullet list following the existing
  Phase 1/Phase 2 style, noting: (a) the brief's premise was largely already true — both
  risks were substantially covered before this phase, and the actual gap was narrow and
  named; (b) the storage-emptiness idiom from Phase 2's `reconcile_media` tests
  generalizes cleanly to rejection tests; (c) two of the phase's four named scenarios
  (empty, truncated) turned out to share one code branch with an existing test, which is
  worth pinning explicitly rather than silently treating as already covered.

### Success Criteria:

#### Automated Verification:

- Unit/integration tests pass: `uv run pytest tests/trips/test_trip_detail.py -v`
- Full suite still passes: `uv run pytest --cov`
- Lint, format, import order, strict typing all pass (`/python-quality-gates`)

#### Manual Verification:

- Confirm the new combined test fails if either template branch is temporarily
  short-circuited by the other (e.g. wrap the stats section in the same `{% if
  track_file_available %}` it does not currently depend on), then revert.
- Read `test-plan.md` §6.1, §6.4, §6.7 after the edit and confirm no other `TBD` marker
  was accidentally touched.

---

## Testing Strategy

### Unit Tests:

- `tests/gpx/test_gpx_parsing.py`: empty-upload and truncated-upload rejection.

### Integration Tests:

- `tests/gpx/test_gpx_upload.py`: storage-emptiness on every rejection path.
- `tests/trips/test_trip_detail.py`: combined missing-file + null-stats degradation.

### Manual Testing Steps:

1. Temporarily break each new/modified assertion at its source (see each phase's Manual
   Verification) and confirm it goes red, then revert — per `lessons.md` #1, #3, #4 and
   the cookbook's "prove the test bites before trusting it" rule.

## Performance Considerations

None — this phase adds assertions to an in-memory SQLite test suite; no production code
changes.

## Migration Notes

Not applicable — test-only phase.

## References

- Research: `context/changes/testing-rejection-and-degradation/research.md`
- Existing storage-emptiness idiom: `tests/gpx/test_reconcile_media.py:558`
- Existing rejection tests: `tests/gpx/test_gpx_upload.py:142-289`
- Existing isolated degradation tests:
  `tests/trips/test_trip_detail.py:114-136`,
  `tests/trips/test_trip_detail_stats.py:137-155`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands.
> Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Storage-debris coverage for rejected uploads (Risk #5)

#### Automated

- [x] 1.1 Unit/integration tests pass: `uv run pytest tests/gpx/test_gpx_upload.py -v` — 00d31a3
- [x] 1.2 Full suite still passes: `uv run pytest --cov` — 00d31a3
- [x] 1.3 Lint, format, import order, strict typing all pass (`/python-quality-gates`) — 00d31a3

#### Manual

- [x] 1.4 Break the claim deliberately, confirm the new assertion goes red, then revert — 00d31a3

### Phase 2: Empty and truncated upload rejection (Risk #5)

#### Automated

- [x] 2.1 Unit tests pass: `uv run pytest tests/gpx/test_gpx_parsing.py -v` — 4e712b7
- [x] 2.2 Full suite still passes: `uv run pytest --cov` — 4e712b7
- [x] 2.3 Lint, format, import order, strict typing all pass (`/python-quality-gates`) — 4e712b7

#### Manual

- [x] 2.4 Confirm both new tests fail under a deliberately broken exception mapping, then revert — 4e712b7

### Phase 3: Combined degradation coverage (Risk #6) and cookbook update

#### Automated

- [x] 3.1 Unit/integration tests pass: `uv run pytest tests/trips/test_trip_detail.py -v`
- [x] 3.2 Full suite still passes: `uv run pytest --cov`
- [x] 3.3 Lint, format, import order, strict typing all pass (`/python-quality-gates`)

#### Manual

- [x] 3.4 Confirm the combined test fails if one branch is made to short-circuit the other, then revert
- [x] 3.5 Confirm test-plan.md §6.1, §6.4, §6.7 updated correctly with no other `TBD` touched
