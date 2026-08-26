# Discard/Cancel Button on New Trip Form — Plan Brief

> Full plan: `context/changes/discard-new-trip-form/plan.md`

## What & Why

Add a Cancel control to the new trip creation form so a user can back out without saving anything and land back on the trip list. Currently the form has only a Save button, with no explicit way to abandon it.

## Starting Point

`trips/templates/trips/trip_form.html` renders `TripCreateView`'s form with a single `Save trip` submit button. The app is plain server-rendered Django with no CSS framework, no client-side JS for forms, and no confirmation-dialog pattern anywhere. Nothing is persisted server-side until the form POSTs, so leaving the page already discards any typed input.

## Desired End State

Loading `/trips/new/` shows a `Cancel` link right after `Save trip`. Clicking it takes the user straight to the trip list (`trips:list`) with no data saved and no confirmation prompt.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Control type | Plain `<a>` link | Matches the app's existing convention for non-destructive navigation; nothing is saved until POST, so navigating away already is the discard | Plan |
| Confirmation prompt | None | Form is short (3 fields), nothing is persisted until submit, and the app has no existing confirm/JS pattern to build on | Plan |
| Label | "Cancel" | Standard, familiar wording | Plan |
| Placement | Inside the form, right after Save | Keeps both trip actions together, minimal template change | Plan |
| Test coverage | Assert link presence + target in existing view test | Follows the codebase's existing Django-test-Client assertion pattern | Plan |

## Scope

**In scope:**
- Cancel link on the new trip creation form (`trips/templates/trips/trip_form.html`)
- A test asserting the link is present and points at the trip list

**Out of scope:**
- Confirmation dialog before discarding
- Any edit-trip or GPX-upload form (this change touches only the create-trip form)
- Styling/CSS

## Architecture / Approach

One-line template addition (`<a href="{% url 'trips:list' %}">Cancel</a>`) plus one new test assertion — no view, URL, or model changes since `trips:list` already exists.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Add Cancel link and test coverage | Cancel link on the form + regression test | None significant — single-file template change |

**Prerequisites:** None — builds on the existing `trips:create`/`trips:list` views.
**Estimated effort:** ~15–30 minutes, single phase.

## Open Risks & Assumptions

- Assumes no confirmation dialog is desired even for a partially-filled form (per user decision) — revisit if user feedback later shows accidental data loss is a real problem.

## Success Criteria (Summary)

- A logged-in user sees a Cancel link on the new trip form and can click it to return to the trip list without creating a trip.
- No trip is created and no dialog appears when Cancel is used, regardless of whether fields were filled in.
