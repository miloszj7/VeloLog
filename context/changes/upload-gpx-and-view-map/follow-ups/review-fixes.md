# Review follow-ups — upload-gpx-and-view-map

Queued from implementation reviews. Each entry names the review, the finding, and what a
later phase has to verify.

## Phase 4 — enforce the one-track-per-trip invariant at the write boundary

- **From**: `reviews/impl-review-phase-3.md` F9 (OBSERVATION, Architecture) — decision ACCEPTED
- **Why deferred**: `TripDetailView` renders `self.object.tracks.first()` into a singular
  context key and a singular template branch, while the schema deliberately permits many
  tracks per trip (plan decision D1). That is correct only while uploads replace rather than
  create. Phase 3 owns the read side; the invariant belongs to whatever creates tracks.
- **Verify at Phase 4**: the upload path replaces the existing track rather than adding a
  second one, and the replaced file is not left orphaned on disk. If replacement is ever
  relaxed to append, the detail view needs to signal the displacement instead of silently
  showing the newest track.
- **Pinned today by**: `tests/trips/test_trip_detail.py::test_trip_with_a_track_renders_only_its_own_track`, whose docstring records the newest-wins
  ordering the view depends on.

- **Resolved at Phase 4** (2026-08-25): `GpxUploadView.form_valid` saves the new track
  inside `transaction.atomic()` and then deletes every other track on that trip, so the
  invariant holds at the only place tracks are created. The superseded *file* is removed
  through `transaction.on_commit`, so a rollback can never leave a row pointing at a file
  that is already gone. Pinned by
  `tests/gpx/test_gpx_upload.py::test_a_second_upload_replaces_the_first_and_removes_its_file`
  (which runs the deferred delete under `django_capture_on_commit_callbacks`) and
  `::test_a_second_upload_leaves_another_trips_track_alone`. Replacement is now a tested
  property rather than an assumption the detail view rests on.
