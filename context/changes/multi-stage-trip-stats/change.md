---
change_id: multi-stage-trip-stats
title: Whole-trip aggregate statistics on the trip detail view (stretch)
status: plan_reviewed
created: 2026-09-04
updated: 2026-09-04
archived_at: null
---

## Notes

Roadmap slice S-03 (`context/foundation/roadmap.md`) — stretch goal, prerequisite S-01
(`multi-stage-gpx-upload`, done). Whole-trip aggregate statistics (distance, duration,
elevation) summed across every stage, with a presentation rule for when not every stage
carries every figure. Per-stage display already shipped in S-01; this narrows to
aggregation only. Explicitly optional under the 1-week/after-hours deadline
(2026-09-10) — first item to drop if S-01/S-02 run long. GitHub issue #39.

UI ordering: show whole-trip aggregate stats first; per-stage stats become a
foldable section, collapsed/hidden by default.
