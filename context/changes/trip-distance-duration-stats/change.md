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
transaction is touched." S-05 reads GPX track data already stored on `GpxTrack`
(likely `points`) to compute distance/duration for display — it does not touch
`GpxUploadView.form_valid` or the upload transaction in `gpx/views.py:100-113`. E-11
stays open on the roadmap engineering backlog until a change actually opens that block.
