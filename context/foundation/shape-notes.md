---
project: VeloLog
context_type: greenfield
updated: 2026-05-29
product_type: web-app
target_scale:
  users: small
timeline_budget:
  mvp_weeks: 2
  after_hours_only: true
  hard_deadline: "2026-06-30"
checkpoint:
  current_phase: 8
  phases_completed: [1, 2, 3, 4, 5, 6, 7]
  frs_drafted: 15
  quality_check_status: accepted
---

## Vision & Problem Statement

**Pain**: GPX tracks from multi-day cycling tours are scattered across devices (watch, phone) and third-party apps, with no way to group stages of a single trip into a coherent unit. No existing tool treats a "trip" as a first-class entity — all major platforms (Strava, Komoot, Wikiloc) are activity-centric: each GPX file is a standalone activity, not a stage of a larger journey.

**Person**: A touring cyclist who does multi-day bike tours and wants to keep a personal digital diary of those trips.

**Moment**: After a trip — or during a future trip — when trying to review, recall, or share the full journey across all its stages.

**Cost today**: Manually juggling multiple GPX files across disconnected apps, no single view of a multi-day tour, no narrative layer (where I slept, who I rode with, what it felt like).

**Core insight**: Existing platforms are activity-centric, not trip-centric. A "trip" with multiple stages, accommodation waypoints between stages, and a personal diary layer simply doesn't exist as a first-class concept anywhere.

## User & Persona

**Primary persona**: A solo touring cyclist — initially the product owner himself — who goes on multi-day bike tours and wants a single personal log that aggregates all stages of a trip (multiple GPX files), captures supporting context (accommodation, companions, photos, description), and presents a unified map and statistics view.

**Access model**: Multi-user from day one. Each user registers their own account and manages their own trips, which can be public or private. The primary development and validation user is the product owner himself.

## Access Control

- **Authentication**: Email + password registration and login.
- **Role model**: Flat — a single registered-user role. All authenticated users have identical capabilities on their own trips. No admin UI in MVP.
- **Visibility**: Each trip can be marked public (visible to anyone, including unauthenticated visitors) or private (visible only to the owner).
- **Data isolation**: Users can only read, edit, and delete their own trips. Public trips are read-only to other users.

## Functional Requirements

### Authentication
- FR-001: User can register with email and password. Priority: must-have
  > Socrates: Counter-argument considered: "Magic-link or OAuth would be faster to build and equally secure." Resolution: kept as email+password; no change to priority. Future: auth mechanism is a downstream stack decision — the FR specifies the capability, not the implementation.
- FR-002: User can log in and log out. Priority: must-have

### Trip Management
- FR-003: User can create a trip with a name, date, and description. Priority: must-have
- FR-004: User can upload a GPX file to a trip. Priority: must-have
  > Socrates: Counter-argument considered: "GPX is one format — locking to it may require migration if FIT/TCX support is added later." Resolution: kept. Naming note captured in NFRs — the product should refer to this as a 'track file'; GPX is the first supported format, not the only conceivable one.
- FR-005: User can view a static map image of a trip's route. Priority: must-have
  > Socrates: Counter-argument considered: "A static map thumbnail would be simpler." Resolution: revised — static map image accepted for v1. Interactive map moved to v2 as the first post-MVP enhancement.
- FR-006: User can view a list of their own trips. Priority: must-have
  > Socrates: Counter-argument considered: "A bare list with no filter/sort is enough for v1 with 1–2 trips." Resolution: kept as must-have, but scoped down — minimal list only, no filter/sort in MVP (FR-012 stays nice-to-have).
- FR-007: User can edit a trip's details (name, date, description). Priority: must-have
  > Socrates: No counter-argument; edit/delete is table stakes for personal data.
- FR-008: User can delete a trip. Priority: must-have

### Extended (Nice-to-have)
- FR-009: User can set a trip's visibility as public or private. Priority: nice-to-have
  > Socrates: Counter-argument accepted: "Default-private for MVP is enough; toggle can ship in v2 when there are multiple users to share with." Demoted from must-have. All trips are private in v1.
- FR-010: User can view basic trip stats (distance and duration) calculated from the GPX. Priority: nice-to-have
- FR-011: User can upload multiple GPX files to one trip (multi-stage grouping). Priority: nice-to-have
- FR-012: User can browse and filter their trip list. Priority: nice-to-have
- FR-013: User can add trip metadata (start location, photos, companions). Priority: nice-to-have
- FR-014: User can add accommodation waypoints between stages with a description and photo. Priority: nice-to-have
- FR-015: User can view the trip route on an interactive OpenStreetMap. Priority: nice-to-have
  > Note: v2 — first feature after the core upload-and-view flow is validated.

## Business Logic

**Domain rule**: A trip is a user-curated collection of one or more GPX track files (stages). The system treats the trip as the primary entity — stages belong to exactly one trip, and a trip must have exactly one uploaded track file in v1 to be considered complete. The system does not auto-detect or auto-group stages; grouping is always an explicit user action.

Supporting detail:
- The user defines trip boundaries manually (by creating a trip and uploading files to it). The system does not infer whether two GPX files belong to the same trip.
- A trip with zero uploaded track files is an empty draft — valid state, but the map and stats views are not available until at least one file is attached.
- Multi-stage grouping (multiple GPX files per trip) is a v2 feature (FR-011). When implemented, the system will merge them into a single rendered route in chronological order by GPS timestamp.

## Non-Functional Requirements

- **Perceived responsiveness**: The trip map renders and the page reaches an interactive state within a time that does not feel broken to a user on a typical home broadband connection. No persistent spinners or silent load failures.

## Non-Goals

- **No third-party integrations**: No import from or sync with Strava, Garmin Connect, Komoot, Google Maps, or any external cycling platform. Users upload GPX files manually. This keeps VeloLog independent and avoids API dependency and OAuth complexity in MVP.
- **No route planning or GPX editing**: VeloLog is a log and viewer, not a planner or editor. Users upload finished tracks; no in-app route building or track modification.
- **No native mobile app**: A responsive web app accessible from mobile browsers is sufficient. No iOS/Android app store distribution in MVP.
- **No AI / LLM features**: Geographic enrichment (landmarks, regions, administrative areas) and weather retrieval are explicitly deferred to v2+. Stated as an idea; ruled out of MVP scope.

## User Stories

### US-01: First successful trip log
Given a user has registered and is logged in,
When they create a trip, upload a valid GPX file, and open the trip detail view,
Then they see the route rendered on a map and a confirmation that the trip was saved.

## Success Criteria

### Primary
Register → log in → create a trip (name, description, date) → upload one GPX file → see the route rendered on an OpenStreetMap. If a new user can complete this flow end-to-end without assistance, VeloLog v1 works.

### Secondary
Basic trip stats (distance and duration) calculated from the uploaded GPX file and displayed on the trip detail view. Not required for the primary proof, but meaningfully raises the value of a successful upload.

### Guardrails
- **Data never lost**: Every uploaded GPX file is durably stored and always retrievable. Data loss is catastrophic for a personal diary product.
- **User data isolation**: One authenticated user can never read, modify, or delete another user's private trips under any circumstance.

## Quality Cross-Check

Completed on 2026-05-29. All elements present.

| Element | Status |
|---|---|
| Access Control | present |
| Business Logic (one-sentence rule) | present |
| Project artifacts | present |
| Timeline-cost acknowledged | present (2-week estimate ≤ 3-week threshold) |
| Non-Goals | present (4 entries) |

`quality_check_status: accepted`
