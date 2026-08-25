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
