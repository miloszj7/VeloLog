---
project: VeloLog
version: 4
status: draft
created: 2026-09-02
context_type: brownfield
product_type: web-app
target_scale:
  users: small
timeline_budget:
  delivery_weeks: 1
  hard_deadline: "2026-09-10"
  after_hours_only: true
---

> **Supersedes** `context/foundation/archive/prd-2026-05-29-v3.md` — the archived document is the v1 **greenfield** PRD (versions 1–3, covering the original register/login/create-trip/upload-one-GPX/static-map flow, all shipped and archived). This document is v4: the v1.5 **brownfield** delta PRD for multi-stage trips and the interactive map, generated from `context/foundation/shape-notes.md`. Version numbering continues from the archived document's `version: 3` rather than restarting, since this PRD describes the next change to the same product, not a new one.

## Current System Overview

**System purpose**: VeloLog is a trip-centric personal diary for multi-day cycling tours, aggregating GPX tracks and trip context into a single view.

**Key architecture**: A monolithic web application deployed as a single service.

**Tech stack**: Django 6 (Python), deployed on Railway.

**Current user base**: A single solo touring cyclist (the product owner), logging their own tours. Small/solo scale.

**Core functionality (v1, shipped and archived)**: register/login; create a trip (name, single date, description); upload exactly one GPX track file per trip; view the trip on a static (non-interactive) map with distance, recorded-time, and elevation stats; edit and delete the trip. Ownership scoping is enforced project-wide (a 404-not-403 contract, tested via an ownership matrix). Upload storage lifecycle is fully handled by the application (signals plus a reconciliation backstop). All 5 v1 roadmap slices (S-01–S-05) are done.

## Problem Statement & Motivation

Two gaps remain between v1 and the original core insight — that a trip is a first-class multi-stage entity, not a single activity:

1. **Data-fidelity gap**: the trip model still represents a single day and a single GPX file. A real multi-day tour — the product's actual subject — cannot be represented.
2. **Presentation gap**: the map is static and its points are unstyled. Interactive map support was explicitly deferred as "the first feature after the core flow is validated" — that validation is now done, since v1 has shipped and is in use.

**Why now**: one week of remaining after-hours time is available before a 2026-09-10 deadline. Both gaps are already named and reasoned about in the project's parked backlog; this change scopes how much of that cluster fits in a week, without introducing new scope.

## User & Persona

**Primary persona**: unchanged from v1 — a solo touring cyclist (the product owner) who logs their own multi-day tours. No new persona is introduced by this change.

## Success Criteria

### Primary
A user opens an existing trip, uploads a second (and further) GPX file as an additional stage, and the trip detail view renders all stages as visually distinct, chronologically-ordered segments on an interactive (pan/zoom) map, with distinct markers for the trip's start, end, and each inter-stage boundary ("stage break"). A single-GPX v1 trip continues to render correctly, unchanged, on the same interactive map.

### Secondary
None promoted for this change — whole-trip/per-stage statistics and standalone accommodation waypoints are explicitly fast-follow (see Non-Goals).

### Guardrails
- **Data never lost**: every uploaded stage file is durably stored and retrievable, the same guarantee as v1.
- **v1 trips unaffected**: existing single-GPX, single-date trips keep working through the data-model change with no manual migration step from the user.
- **User data isolation**: unchanged from v1 — no cross-user access to trips or stage files under any circumstance.

## User Stories

### US-02: Multi-day trip logged as one interactive journey

- **Given** a user has an existing trip with one GPX stage already uploaded
- **When** they upload a second GPX file to the same trip and open the trip detail view
- **Then** they see both stages as visually distinct, chronologically-ordered segments on an interactive map, with markers at the trip's start, end, and the "stage break" between the two stages

# TODO: US-02 has no separate Acceptance Criteria checklist beyond its Given/When/Then — see Open Questions.

## Scope of Change

- [new] User can upload a second (and further) GPX file to an existing trip as an additional stage. Priority: must-have.
  > Socrates: No counter-argument; it stands as written — this is the core data-fidelity fix the whole change is about.
- [modified] User sees all of a trip's stages merged into one route, ordered chronologically by GPS timestamp, with each stage rendered as a visually distinct segment (e.g. a different line color per stage) — was: a trip renders exactly one uploaded track as a single undifferentiated line. Priority: must-have.
  > Socrates: Counter-argument considered: "chronological merge is wrong if stages have a time gap (rest day, or simply a new day) — a continuous unbroken line implies continuous riding." Resolution: revised — stages render as visually distinct segments (per-stage color) rather than one undifferentiated line, so a gap in time doesn't read as a gap that should exist in the geometry.
- [modified] User views the trip route on an interactive (pan/zoom) map instead of a static image — was: a static, non-interactive map image. Priority: must-have.
  > Socrates: No counter-argument; it stands as written — the static map was always a placeholder for the current validation stage.
- [new] User sees distinct markers for trip start, trip end, and each inter-stage boundary, labeled generically as a "stage break" rather than "accommodation". Priority: must-have.
  > Socrates: Counter-argument considered: "labeling a stage boundary as 'accommodation' asserts a fact the data doesn't support — it could be a lunch stop, a GPS pause, or any reason a rider split a stage into two files, not necessarily an overnight stay." Resolution: revised — marker labeled generically as "stage break". True accommodation semantics (a confirmed overnight stop with its own description/photo) is fast-follow (see Non-Goals).
- [preserved] Existing single-GPX v1 trips continue to render, edit, and delete correctly, unchanged.
  > Socrates: No counter-argument; it stands as written.

### Fast-follow (parked for this change — pick up only if the week's core scope finishes early)
- [new, deferred] User can add an accommodation waypoint (description, photo) between stages, as its own record rather than an inferred map marker. Priority: nice-to-have.
- [new, deferred] User can view whole-trip and per-stage statistics (distance, duration, elevation) on the trip detail view. Priority: nice-to-have.

## Constraints & Compatibility

- **No data migration required from the user**: existing v1 trips (one file, one date) must continue to work with no manual action required — any schema change (e.g. splitting the single-file relationship into a stage collection) must be backward-compatible or auto-backfilled.
- **Preserved behavior**: existing single-GPX, single-date trips must continue to render, edit, and delete correctly after the data-model change. Ownership scoping and the "data never lost" guardrail extend unchanged to any new upload paths.
- **Ownership matrix stays in sync**: any new per-object route this change introduces (e.g. removing a single stage from a trip) must be added to the project's ownership-scoping test inventory, per the project's standing rule.

## Business Logic Changes

**Current rule**: a trip is complete with exactly one uploaded track file; the system does not merge multiple files.

**Change**: a trip may now have multiple stages (track files). The system merges them into one route ordered chronologically by GPS timestamp, renders each stage as a visually distinct segment, and marks each inter-stage boundary as a "stage break". The system still does not infer trip boundaries or which files belong together — grouping stages under a trip remains an explicit user action (uploading to that trip), consistent with the current rule.

## Access Control Changes

No access control changes — current model preserved. Flat single-user role, email+password auth, strict per-owner scoping (404-not-403 contract) on every object-scoped route. New object types introduced by this change (additional stage files) are child records of a trip and inherit its ownership scope — no new access concept is required, but any new per-object route added must still be added to the project's ownership-scoping test inventory, per the project's standing rule.

## Non-Functional Requirements

Unchanged from v1: the trip map renders and the page reaches an interactive state within a time that does not feel broken on typical home broadband, with continuous visible feedback during load and no silent load failures. This property extends to the merged multi-stage render without a new target.

## Non-Goals

- **No accommodation waypoint entity in this change**: a standalone record with description/photo, placed between stages, is fast-follow, not built this week. Only the generic "stage break" marker ships.
- **No manual stage reordering**: stage order is always derived from GPS timestamp; there is no drag-to-reorder UI or manual override in this change.
- **No whole-trip/per-stage statistics in this change**: fast-follow — existing single-file distance/duration/elevation stats are not extended to multi-stage aggregation this week (v1's stats display continues to reflect only what it already covers).
- **No product type or scale change**: still a responsive web app at small/solo scale; unchanged from v1.

## Open Questions

1. **US-02 has no separate Acceptance Criteria checklist beyond its Given/When/Then.** — Owner: user. By: before implementation planning. Block: no — the Given/When/Then is sufficient to scope the change, but an explicit checklist would tighten testability.
