---
change_id: upload-gpx-and-view-map
title: Upload a GPX file to a trip and see the route as a static map
status: new
created: 2026-08-23
updated: 2026-08-24
archived_at: null
---

## Notes

from @context/foundation/roadmap.md

Roadmap slice **S-03** — the north star: the smallest end-to-end slice that proves the
core product hypothesis (PRD Primary Success Criterion: register → log in → create a
trip → upload one GPX file → see the route rendered as a static map image).

- **Outcome:** upload a GPX file to a trip and open the trip detail view to see the
  route rendered as a static map image, with a clear empty state if no file is uploaded yet.
- **PRD refs:** FR-004, FR-005, US-01
- **Prerequisites:** S-02 `create-and-list-trips` (done, archived 2026-08-23)
- **Risk (from roadmap):** uploaded files must land on the already-provisioned persistent
  Railway Volume (see `DEPLOY.md`), not ephemeral local disk. Silent map-render failures
  are disallowed by the PRD's NFR — the empty/error state must be deliberate.
- **Engineering backlog triggered by this slice:** E-01 (CI runs no tests/lint/type
  gates, trigger: "before S-03") is done — `ci-quality-gates` merged and archived,
  GitHub issue #7 closed. E-05 (the `/data/db.sqlite3` restore path has never been
  exercised, trigger: "before the deploy following S-03") is still open.
