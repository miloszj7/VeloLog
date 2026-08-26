---
change_id: upload-gpx-and-view-map
title: Upload a GPX file to a trip and see the route as a static map
status: archived
created: 2026-08-23
updated: 2026-08-26
archived_at: 2026-08-26T09:32:05Z
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

## Decisions (2026-08-24, post-research)

Settled with the user after `research.md`. These are inputs to `/10x-plan`, not
implementation detail.

- **D1 — Data model: a separate `GpxTrack` model with an FK to `Trip`**, so the schema
  supports many tracks per trip from day one (a 3-day tour is naturally 3 segments).
  **v1 behaviour is still one track per trip** — so `prd.md:96` ("a trip has exactly one
  associated track file") remains accurate as a behavioural statement, FR-011 stays
  parked, and no PRD amendment is needed. The forward-looking schema is the whole point:
  FR-011 must not require a migration rewrite.
  - *Assumption to confirm at plan review:* uploading again **replaces** the trip's
    existing track, rather than being rejected or creating a second one.
- **D2 — The GPX file is downloadable from VeloLog.** This requires an
  **ownership-scoped `FileResponse` view behind `LoginRequiredMixin`** — never a bare
  `MEDIA_URL` path, per `prd.md:105` ("no user can access another user's trips under
  any circumstances") and `prd.md:104` ("unauthenticated users cannot view any trip").
  Needs a cross-user 404 test and an unauthenticated-redirect test, matching the
  existing authz test conventions.
- **D3 — Infrastructure hardening: (a) + (b) as code in S-03, (c) as a deploy-phase step.**
  - In-slice code: the `STORAGES["default"]` fix, env-driven `MEDIA_ROOT`/`MEDIA_URL` on
    the Volume, a `collectstatic --noinput` step in the CI `gates` job, and a media
    write/read round-trip added to `/healthz/`.
  - Deploy phase: extend `DEPLOY.md` backup/restore to cover `/data/media`, and exercise
    the restore once — which also discharges the open **E-05** backlog row.
- **D4 — Map rendering: core Leaflet 1.9.4, server-side `gpxpy` parse.** Per `research.md`:
  points embedded via `{{ ...|json_script }}`, no `leaflet-gpx`, no `leaflet-elevation`,
  no d3. Implement against `research/leaflet-1.9.4-context7-docs.md`, not the 2.0-alpha
  capture. Vendor Leaflet with its complete `images/` directory.
  - Carried assumptions: vendored rather than CDN-loaded; a 10 MB upload cap enforced in
    `clean_gpx_file()`; the two Leaflet doc gaps (map interaction options, `fitBounds`
    padding) resolved during planning.
