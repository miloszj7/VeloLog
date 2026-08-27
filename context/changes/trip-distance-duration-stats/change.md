---
change_id: trip-distance-duration-stats
title: Show trip distance and duration stats on the trip detail view
status: plan_reviewed
created: 2026-08-27
updated: 2026-08-27
archived_at: null
---

## Notes

S-05 from `context/foundation/roadmap.md`: user can see basic trip stats (distance,
duration) calculated from the uploaded GPX file, on the trip detail view. PRD ref:
FR-010 (Secondary Success Criterion). Prerequisite S-03 (`upload-gpx-and-view-map`) is
done, so this slice is unblocked.

**E-11 considered and left out of this change.** E-11 (orphaned file on a rolled-back
GPX upload transaction) names its own trigger: "the next time `gpx/views.py`'s upload
transaction is touched." S-05 adds derived columns to `GpxTrack`, fills them inside the
existing `parse_gpx` call, and reads them back on the render path — in `gpx/views.py`
that means `GpxUploadView.get_context_data` (`gpx/views.py:66-78`) only. The transaction
block at `gpx/views.py:100-113` is never opened, so E-11's trigger does not fire. It
stays open on the roadmap engineering backlog until a change actually touches that block.
