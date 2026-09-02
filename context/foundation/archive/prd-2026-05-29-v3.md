---
project: VeloLog
version: 3
status: draft
created: 2026-05-29
updated: 2026-08-26
context_type: greenfield
product_type: web-app
target_scale:
  users: small
  qps: low
  data_volume: small
timeline_budget:
  mvp_weeks: 2
  hard_deadline: "2026-09-10"
  after_hours_only: true
---

## Vision & Problem Statement

GPX tracks from multi-day cycling tours are scattered across devices (watch, phone) and third-party apps, with no way to group stages of a single trip into a coherent unit. No existing tool treats a "trip" as a first-class entity — all major platforms (Strava, Komoot, Wikiloc) are activity-centric: each GPX file is a standalone activity, not a stage of a larger journey. A touring cyclist who completes a multi-day tour is left manually juggling disconnected files, with no single view of the full journey and no narrative layer capturing where they slept, who they rode with, or what the experience felt like.

The key insight is that the problem is not the GPX format or the tracking device — it is the absence of a trip-centric data model. Existing platforms optimise for sharing and performance metrics on individual activities. A personal diary of multi-day tours, where the trip is the primary entity and individual day-tracks are its stages, does not exist as a product.

## User & Persona

**Primary persona**: A solo touring cyclist who undertakes multi-day bike tours and wants a single personal log of those trips. Initially the product owner himself. He captures GPS tracks on a variety of devices (watch, phone, dedicated GPS unit) and wants to aggregate all stages of a trip, attach supporting context (accommodation, companions, photos, description), and view the full journey on a map with statistics.

He is technically literate, not technical-first — he wants a tool that works, not a project to maintain. He reaches for VeloLog after completing a tour, when he wants to record and relive it before the details fade.

**Access model**: Multi-user from day one. Each user registers their own account and manages their own trips. The primary development and validation user is the product owner himself.

## Success Criteria

### Primary
A new user can register, log in, create a trip (name, date, description), upload one GPX file, and see the route drawn on a non-interactive map — end to end, without assistance. If this flow completes, VeloLog v1 works.

### Secondary
Basic trip stats (distance and duration) calculated from the uploaded GPX file and displayed on the trip detail view. Not required for the primary proof, but meaningfully raises the value of a completed upload.

### Guardrails
- **Data never lost**: Every uploaded GPX file is durably stored and always retrievable. Data loss is catastrophic for a personal diary product.
- **User data isolation**: One authenticated user can never read, modify, or delete another user's private trips under any circumstance.

## User Stories

### US-01: First successful trip log

- **Given** a user has registered and is logged in
- **When** they create a trip, upload a valid GPX file, and open the trip detail view
- **Then** they see the route drawn on a non-interactive map and a confirmation that the trip was saved

#### Acceptance Criteria
- The trip appears in the user's trip list after creation
- The uploaded GPX file is associated with the trip and the map renders without error
- A trip with no uploaded GPX file does not show a broken map — it shows a clear empty state

## Functional Requirements

### Authentication
- FR-001: User can register with email and password. Priority: must-have
  > Socrates: Counter-argument considered: "Magic-link or OAuth would be faster to build and equally secure." Resolution: kept as email+password; no change to priority. Auth mechanism is a downstream stack decision — the FR specifies the capability, not the implementation.
- FR-002: User can log in and log out. Priority: must-have

### Trip Management
- FR-003: User can create a trip with a name, date, and description. Priority: must-have
- FR-004: User can upload a GPX file to a trip. Priority: must-have
  > Socrates: Counter-argument considered: "GPX is one format — locking to it may require migration if FIT/TCX support is added later." Resolution: kept. The product refers to this capability as uploading a 'track file'; GPX is the first supported format.
- FR-005: User can view a trip's route drawn on a non-interactive map. Priority: must-have
  > Socrates: Counter-argument considered: "A static map image would be simpler than an interactive map." Resolution: revised — a non-interactive map accepted for v1. Interactive map is the first v2 enhancement (FR-015).
  > Amended v3 (2026-08-26): the wording was "a static map image" until implementation. What shipped renders the route client-side onto a raster tile map with panning, zooming, and keyboard navigation all disabled — visually static, but not a server-rendered image. The delta FR-015 still owns is therefore *interactivity*, not *the map*: v2 re-enables the controls this deliberately turns off. Kept as a wording amendment rather than a scope change because the user-visible outcome is unchanged.
- FR-006: User can view a list of their own trips. Priority: must-have
  > Socrates: Counter-argument considered: "A bare list with no filter/sort is enough for v1 with 1–2 trips." Resolution: kept as must-have, scoped to minimal list only — no filter/sort in v1 (FR-012 is nice-to-have).
- FR-007: User can edit a trip's details (name, date, description). Priority: must-have
  > Socrates: No counter-argument; edit/delete is table stakes for personal data.
- FR-008: User can delete a trip. Priority: must-have

### Extended (Nice-to-have)
- FR-009: User can set a trip's visibility as public or private. Priority: nice-to-have
  > Socrates: Counter-argument accepted: "Default-private for v1 is enough; toggle ships in v2 when multiple users are active." Demoted from must-have. All trips are private in v1.
- FR-010: User can view basic trip stats (distance and duration) calculated from the GPX. Priority: nice-to-have
- FR-011: User can upload multiple GPX files to one trip (multi-stage grouping). Priority: nice-to-have
- FR-012: User can browse and filter their trip list. Priority: nice-to-have
- FR-013: User can add trip metadata (start location, photos, companions). Priority: nice-to-have
- FR-014: User can add accommodation waypoints between stages with a description and photo. Priority: nice-to-have
- FR-015: User can view the trip route on an interactive map. Priority: nice-to-have
  > Note: v2 — first feature after the core upload-and-view flow is validated in production.

## Non-Functional Requirements

- **Perceived responsiveness**: The trip detail view, including the map image, reaches a usable state within a time that does not feel broken to a user on a typical home broadband connection. Silent failures on map generation are not acceptable — if the map cannot be rendered, the user receives a clear error state, not a blank page.

## Business Logic

A trip is a user-curated collection of track files; the system treats the trip as the primary entity, not the individual file.

In v1, a trip has exactly one associated track file. A trip with no uploaded file is a valid empty draft — the map and stats views are unavailable until a file is attached. The system does not auto-detect or auto-group tracks; all grouping is an explicit user action.

Multi-stage grouping (multiple track files per trip, FR-011) is a v2 feature. When implemented, the system will merge track files into a single rendered route in chronological order by GPS timestamp.

## Access Control

- **Authentication**: Email and password registration and login.
- **Role model**: Flat — a single registered-user role. All authenticated users have identical capabilities on their own trips. No admin UI in v1.
- **Visibility**: All trips are private in v1. Unauthenticated users cannot view any trip. A public/private toggle is a v2 feature (FR-009).
- **Data isolation**: Users can only read, edit, and delete their own trips. No user can access another user's trips under any circumstances.

## Non-Goals

- **No external platform integration**: No import from or sync with any external cycling, fitness, or mapping platform. Users upload track files manually. This keeps VeloLog independent and removes third-party API dependency and OAuth complexity from v1.
  > Clarified v3 (2026-08-26): rendering the route requires map tiles, which v1 fetches from OpenStreetMap in the browser. This is consistent with the non-goal rather than an exception to it — there is no import, no sync, no account, no API key, and no server-side dependency, so an OSM outage degrades the map to blank tiles with the route still drawn. What the non-goal excludes is integration with a *platform holding user data*; a public basemap is not that. See `DEPLOY.md` for the tile-usage policy and privacy consequences.
- **No route planning or track editing**: VeloLog is a log and viewer, not a planner or editor. Users upload finished tracks; no in-app route building or track modification.
- **No native mobile app**: A responsive web app accessible from mobile browsers is sufficient. No app store distribution in v1.
- **No AI or geographic enrichment features**: Automatic geographic enrichment (landmarks, regions, administrative areas) and weather retrieval are deferred to v2+.

## Changelog

- **v1 (2026-05-29)** — Initial PRD: hard deadline `2026-06-30`.
- **v2 (2026-08-22)** — `hard_deadline` changed `2026-06-30` → `2026-09-10`.
- **v3 (2026-08-26)** — FR-005, the Primary Success Criterion, and US-01 reworded from "static map image" to a non-interactive map, matching what shipped in slice S-03; FR-015's remaining v2 delta narrowed to interactivity. Non-Goals clarified that browser-fetched OSM raster tiles are in scope and why that does not contradict "no external platform integration". No scope change — user-visible outcome is unchanged.

## Open Questions

_No open questions._
