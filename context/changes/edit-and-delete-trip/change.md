---
change_id: edit-and-delete-trip
title: Edit and delete a trip
status: plan_reviewed
created: 2026-08-26
updated: 2026-08-27
archived_at: null
---

## Notes

Roadmap slice S-04: user can edit a trip's name, date, and description, or delete the trip entirely. PRD refs FR-007, FR-008. Prerequisite: S-02 (`create-and-list-trips`, done). Parallel with S-03 (already done).

Also bundled into this change: E-08 from the Engineering Backlog — `TripForm` accepts a future-dated trip with no validation (found during S-02 Phase 3 manual verification). Decide product intent (block future dates? allow and label as "planned"?) then add `clean_date()` if blocking is the answer. Trigger was "when trip-date semantics are next revisited, e.g. alongside S-03/S-04" — this change is that trigger.
