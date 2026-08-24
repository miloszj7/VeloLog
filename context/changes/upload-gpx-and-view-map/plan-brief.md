# Upload a GPX file and view the route as a map — Plan Brief

> Full plan: `context/changes/upload-gpx-and-view-map/plan.md`
> Research: `context/changes/upload-gpx-and-view-map/research.md` (+ `research/` for library docs)
> Settled decisions D1–D4: `context/changes/upload-gpx-and-view-map/change.md`

## What & Why

Roadmap slice **S-03**, the product's north star: a logged-in user uploads a GPX file to a
trip and opens the trip detail view to see the route drawn on a map. This is the smallest
end-to-end slice that proves the core hypothesis — the PRD's Primary Success Criterion is
literally this flow. Everything else in VeloLog only matters once this works.

## Starting Point

S-01 (auth) and S-02 (create/list trips) are shipped and archived. But there is **no trip
detail view and no detail URL at all**, and the repo has never had a `FileField`, a
`{% static %}` reference, a line of CSS, or an `enctype` attribute. Research found five
blockers between the current repo and any upload — four of which pass every CI gate green.
I confirmed the two worst firsthand: `default_storage` raises `InvalidStorageError` because
`STORAGES` has no `"default"` alias, and `MEDIA_URL` resolves to `"/"`, colliding with the
root redirect.

## Desired End State

A user opens a trip from their list and lands on a detail page. With no track, they see a
clear empty state and an upload form. They pick a `.gpx` file; it is validated, parsed, and
stored on the Railway Volume, and the page comes back with the route drawn as a polyline on
an OpenStreetMap layer — start and end marked, view fitted to the track, all pan/zoom/drag
disabled. They can download the original file back. Uploading again replaces the track. A
bad file is rejected inline with a visible message and nothing is written.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Data model | Separate `GpxTrack` with FK to `Trip` | v1 stores one track per trip, but the schema supports many so FR-011 never needs a migration rewrite | Frame/change.md (D1) |
| Raw file access | Ownership-scoped `FileResponse` behind `LoginRequiredMixin` | A bare `MEDIA_URL` path is unauthenticated static serving, which `prd.md:104-105` forbids outright | change.md (D2) |
| Infra hardening | `STORAGES` fix + env-driven media on the Volume + CI `collectstatic` + media round-trip in `/healthz/` | Four of five blockers are first-use or deploy-time failures no current gate can see | change.md (D3) |
| Map rendering | Core Leaflet **1.9.4** vendored, server-side `gpxpy` parse, points via `json_script` | Leaflet 2.0 is still alpha with no release date; no GPX plugin, no d3, no unverified API surface | change.md (D4) + Research |
| App boundary | New `gpx/` app at repo root | `AGENTS.md:21` pre-blesses it by name; keeps parsing and vendored assets out of the trip-CRUD app, and S-05 stats land in the same place | Plan |
| Parse timing | Parse once **at upload**, persist derived points and bounds | A file that parsed once can never fail at render, and the error reaches the user when they can still fix it | Plan |
| Bad GPX | Rejected at upload — form error, nothing saved | Puts the failure at the point of action; no unusable rows, no orphan files | Plan |
| Re-upload | Replaces the existing track; old file deleted | Matches `prd.md:96` ("exactly one associated track file") as v1 behaviour; "wrong file, let me fix it" is the common case | Plan |
| Upload location | On the trip detail page, below the map / empty state | Matches US-01's flow exactly, and makes upload, re-upload and empty state one coherent surface | Plan |
| Validation | 10 MB cap + `.gpx` extension + parse-must-succeed + documented XML entity hardening + explicit Django upload-size settings | ruff gives **zero** protection here — `gpxpy.parse` is opaque to every `S3xx` rule, so each measure must be deliberate and tested | Plan |
| CSS / assets | Real `static/css/style.css` + `extra_head`/`scripts` blocks in `base.html` | Exercises the `{% static %}` pipeline properly the first time, guarded by a new CI `collectstatic` step; explicitly reverses the standing "no CSS" decision | Plan |
| Map content | Polyline + start/end markers with **explicit** `L.icon` URLs | Leaflet's default icon builds image URLs at runtime that the hashed manifest never rewrites — silent production 404s | Plan |
| Deploy scope | Runbook + restore drill is the final phase, closing E-05 | E-05's own trigger is "before the deploy following S-03", and this is the first deploy with real user files to lose | Plan |
| Doc drift | Amend `prd.md` (FR-005, Non-Goals) and `roadmap.md` | Lessons rule #5 — a stale FR actively misdirects the next agent; FR-015 becomes a coherent delta instead of a contradiction | Plan |

## Scope

**In scope:** the five blockers; `gpx` app + `GpxTrack` model + migration; trip detail view
with owner-scoped 404; upload form with hardened validation; replace-on-re-upload;
authenticated file download; vendored Leaflet 1.9.4 + first project CSS; CI `collectstatic`
gate; media round-trip in `/healthz/`; PRD/roadmap/`AGENTS.md`/`DEPLOY.md` updates; restore
drill closing E-05.

**Out of scope:** `leaflet-gpx`, `@raruto/leaflet-elevation`, d3, elevation charts; Leaflet
2.0; `lxml`; any CDN; interactive map (FR-015); multiple tracks per trip in v1 *behaviour*
(FR-011); trip stats (S-05); trip edit/delete (S-04); point-count cap or downsampling;
quarantine store for rejected files; `LOGGING` config (E-06); branch protection (E-02).

## Architecture / Approach

```
POST .gpx ──> GpxUploadForm.clean_file()          [10MB cap, .gpx, gpxpy.parse]
                    │  reject ──> ValidationError rendered inline on the detail page
                    ▼ accept
              GpxTrack row: file ──> Volume (/data/media)
                            points + 4 bounds floats  (parsed ONCE, here)
                    │
GET detail ──> TripDetailView (owner-scoped)
                    │  no track ──> empty state
                    ▼ track
              {{ config|json_script }} ──> map.js ──> L.polyline + L.marker + fitBounds
                                                       (all interaction disabled)
GET download ──> ownership-scoped FileResponse   [never MEDIA_URL — whitenoise sits
                                                  before AuthenticationMiddleware]
```

The whole design turns on parsing at upload rather than at render: the detail view does no
XML work, so it cannot fail or degrade, and the error state lives where the user can act.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Storage & media foundation | `STORAGES["default"]`, env-driven media on the Volume, `/healthz/` media round-trip, a test that does a **real** storage write | B1 is invisible to every gate — only a real `storage.save` catches it |
| 2. `gpx` app + `GpxTrack` | New root-level app, model, hand-verified migration, coverage registration | Coverage guard has two known traps: bare string `"gpx"`, app at repo root |
| 3. Trip detail view | `trips:detail` route, owner-scoped 404, empty state, link from the list | First pk-capturing route in the project; 404-not-403 must hold |
| 4. Upload, validation, download | `gpxpy` added, `clean_file()` hardening, replace semantics, authenticated `FileResponse` | Missing `seek(0)` persists a truncated file and passes a status-code test |
| 5. Map + static pipeline | Vendored Leaflet 1.9.4, first CSS, `base.html` blocks, CI `collectstatic` gate, the map itself | An unresolvable `leaflet.css` reference fails `collectstatic`, which is a **boot outage** |
| 6. Docs & deploy hardening | PRD/roadmap/`AGENTS.md`/`DEPLOY.md` updates, media backup, restore drill, E-05 closed | Manual-only; needs a live Railway session |

**Prerequisites:** S-02 shipped (done, archived 2026-08-23); E-01 CI gates merged (done);
Railway Volume mounted at `/data` with `RAILWAY_RUN_UID=0`; a real multi-day-tour GPX file
for manual verification; Railway SSH key registered for the Phase 6 drill.

**Estimated effort:** ~4–6 sessions across 6 phases. Phases 1–3 are small and mostly
mechanical; Phase 4 and Phase 5 each carry the bulk of the code and test surface; Phase 6 is
short but gated on a live deploy.

## Open Risks & Assumptions

- **No bound on track point count.** The 10 MB size cap is the only volume limit, and a
  10 MB GPX can embed a very large coordinate array in the page. A point cap was considered
  and declined. Parse-on-upload means downsampling can be added later without touching the
  render path — but the PRD's responsiveness NFR is the thing at risk, so measure point count
  on the first real multi-day tour.
- **`MEDIA_ROOT=/data/media` must be set in Railway before the first upload**, or files land
  on ephemeral disk and vanish on redeploy. The Phase 1 `/healthz/` round-trip is what
  surfaces this, including the `RAILWAY_RUN_UID` silent-write-failure mode
  (`infrastructure.md:59`).
- **`/websites/leafletjs` can flip to 2.0 syntax on a re-crawl.** The plan carries the
  verified 1.9.4 API inline, and the durable check is the syntax (`L.map(...)` = 1.x,
  `new LeafletMap(...)` = 2.0), not the library ID.
- **OSM tile availability is outside our control.** An outage degrades the map to blank tiles
  with the route still drawn; it does not fail the page. No server-side OSM dependency exists.
- **E-08 (`TripForm` accepts future dates) is untouched** and its trigger names S-03/S-04 as
  a natural moment. Deliberately left open — it is not on this slice's path.

## Success Criteria (Summary)

- A new user can register, log in, create a trip, upload one GPX file, and see the route on a
  map — end to end, without assistance. That is the PRD's Primary Success Criterion met.
- A trip with no file shows a deliberate empty state; a bad file shows a deliberate inline
  error. Neither is ever a blank page or a broken map.
- No user can reach another user's trip, track, or file by any route — all three surfaces
  return 404, asserted in tests.
