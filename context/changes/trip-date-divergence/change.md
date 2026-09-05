---
change_id: trip-date-divergence
title: Surface Trip.date vs GPX-derived span divergence instead of hiding it
status: impl_reviewed
created: 2026-09-05
updated: 2026-09-05
archived_at: null
---

## Notes

Surface the divergence between Trip.date (user-entered) and the GPX-derived trip_span on the trip detail page, and warn on GPX upload when a stage's started_at diverges sharply from Trip.date

## Triage

4 findings from the impl-review triaged and fixed (2026-09-05): see
`reviews/impl-review.md` and commits c2409ed, 12c9e35, 041b71e.
