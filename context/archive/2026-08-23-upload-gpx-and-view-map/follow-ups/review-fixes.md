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

## Phase 6 — check whether Railway's edge gzips dynamic responses

- **From**: `reviews/impl-review-phase-5.md` F6 (WARNING, Safety & Quality) — decision FIXED
  in part via Fix A
- **Why deferred**: F6 had two halves. The precision half is closed — coordinates are now
  rounded to `COORDINATE_DECIMAL_PLACES` at the parse boundary, which roughly halves the
  JSON bytes per point. The compression half cannot be decided from here: `MIDDLEWARE` has
  no `GZipMiddleware` and whitenoise compresses collected static assets only, so the
  coordinate payload inlined into the trip detail page ships raw *unless* Railway's edge
  compresses it — and `DEPLOY.md` records nothing either way. Adding `GZipMiddleware`
  blind risks double compression and opens a BREACH conversation this slice never planned
  for.
- **Verify at Phase 6**: on the deployed instance, request a trip detail page with
  `Accept-Encoding: gzip` and read `Content-Encoding` off the response. If the edge already
  gzips, record that in `DEPLOY.md` as the reason no middleware is needed. If it does not,
  add `django.middleware.gzip.GZipMiddleware` directly below `SecurityMiddleware` and note
  the BREACH posture — Django masks the CSRF token per response, so the residual risk is
  the usual accepted one.
- **Pinned today by**: nothing — there is no test that can observe edge behaviour. The
  rounding half is pinned by
  `tests/gpx/test_gpx_parsing.py::test_coordinates_are_rounded_to_the_stored_precision`.
- **Also still unmeasured**: the only payload figure on record is the Phase 4 synthetic
  worst case (~24 bytes of JSON per point before rounding). Neither the cap nor the
  compression decision has been checked against a real multi-day tour export.
