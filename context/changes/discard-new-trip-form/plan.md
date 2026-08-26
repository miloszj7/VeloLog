# Discard/Cancel Button on New Trip Form Implementation Plan

## Overview

Add a Cancel link to the new trip creation form so a user can abandon the form and return to the trip list without saving anything.

## Current State Analysis

`trips/templates/trips/trip_form.html` renders the `TripCreateView` form (`trips/views.py`, `TripCreateView`) with only a `Save trip` submit button — there is no way to leave the form except the browser back button or the top-nav. The app is a plain server-rendered Django app (no SPA framework, no client-side form state, no CSS framework). Nothing is persisted until the form POSTs, so leaving the page via a plain link already discards any typed input — there is no server-side state to clean up.

### Key Discoveries:

- `trips/templates/trips/trip_form.html:17` — the only action in the form is `<button type="submit">Save trip</button>`.
- `trips/templates/trips/trip_detail.html:13` and `trips/templates/trips/trip_list.html:7` — the app's existing convention for non-destructive navigation is a plain `<a href="{% url 'trips:list' %}">...</a>` link; there is no precedent for JS-driven navigation or confirm dialogs anywhere in the codebase.
- `trips/urls.py:8` and `trips/views.py` (`TripListView`) — `trips:list` is the trip list, i.e. the "main page" a user returns to.
- `tests/trips/test_trip_creation.py` — trip creation is tested via `django.test.Client` + `reverse()`, asserting on response status/content/DB state; there is no browser/JS test tooling in this repo.

## Desired End State

The new trip form (`GET /trips/new/`) renders a `Cancel` link immediately after the `Save trip` button. Clicking it performs a plain GET navigation to `trips:list` (the trip list page) with no data submitted and no confirmation prompt. Verify by loading `/trips/new/` as a logged-in user, confirming the `Cancel` link is present and points at the trips list URL, and clicking it lands on the trip list without creating a trip.

## What We're NOT Doing

- No confirmation dialog ("are you sure you want to discard?") — out of scope per user decision; the form is short (3 fields) and nothing is persisted until POST.
- No client-side JS or dirty-state tracking.
- No changes to other forms (GPX upload form, any future edit-trip form) — scoped strictly to the new trip creation form.
- No visual styling/CSS — the app has no CSS framework and no button/link classes exist anywhere; the new link follows the same unstyled convention.

## Implementation Approach

Add one plain `<a href="{% url 'trips:list' %}">Cancel</a>` link to `trips/templates/trips/trip_form.html`, placed inside the form immediately after the `Save trip` submit button. This matches the codebase's existing pattern for non-destructive navigation and requires no view, URL, or model changes since `trips:list` already exists and already serves as the app's main page. Extend the existing trip-creation test file with one assertion that the Cancel link is present in the GET response and points at `trips:list`.

## Phase 1: Add Cancel link and test coverage

### Overview

Add the Cancel link to the template and cover it with a test, in one phase since this is a single-file template change plus one test assertion.

### Changes Required:

#### 1. Trip creation template

**File**: `trips/templates/trips/trip_form.html`

**Intent**: Give the user a way to leave the new trip form without submitting it, returning to the trip list.

**Contract**: Add `<a href="{% url 'trips:list' %}">Cancel</a>` immediately after the existing `<button type="submit">Save trip</button>` on line 17, inside the `<form>` block.

#### 2. Trip creation tests

**File**: `tests/trips/test_trip_creation.py`

**Intent**: Guard against the Cancel link being removed or its target changed by mistake.

**Contract**: Add a test that performs `auth_client.get(reverse("trips:create"))` and asserts the response content contains a link whose `href` resolves to `reverse("trips:list")` (e.g. assert `reverse("trips:list").encode()` appears within an `<a href="...">Cancel</a>` in `response.content`), following the same `Client` + `reverse()` pattern used by the existing tests in this file.

### Success Criteria:

#### Automated Verification:

- Unit/integration tests pass: `uv run pytest tests/trips/test_trip_creation.py`
- Full test suite passes: `uv run pytest`
- Linting passes: `uv run ruff check .`
- Type checking passes (if applicable to touched files): `uv run mypy .`

#### Manual Verification:

- Load `/trips/new/` as a logged-in user and confirm a `Cancel` link is visible next to `Save trip`.
- Click `Cancel` and confirm it navigates to the trip list without creating a trip.
- Confirm typing into the form fields and then clicking `Cancel` does not create a trip and does not prompt any confirmation dialog.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding.

---

## Testing Strategy

### Unit Tests:

- Assert the Cancel link is present in the `GET /trips/new/` response and points at `trips:list`.

### Integration Tests:

- Existing `tests/trips/test_trip_creation.py` suite continues to pass unchanged (POST flows unaffected).

### Manual Testing Steps:

1. Log in, navigate to `/trips/new/`.
2. Confirm `Cancel` link renders next to `Save trip`.
3. Type into the `name`/`date`/`description` fields, then click `Cancel`.
4. Confirm the browser lands on the trip list (`/trips/`) and no new trip was created.

## Performance Considerations

None — this is a static template link with no additional request or computation.

## Migration Notes

Not applicable — no data model or URL changes.

## References

- Similar implementation: `trips/templates/trips/trip_detail.html:13` (`Back to your trips` link pattern)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Add Cancel link and test coverage

#### Automated

- [x] 1.1 Unit/integration tests pass: `uv run pytest tests/trips/test_trip_creation.py`
- [x] 1.2 Full test suite passes: `uv run pytest`
- [x] 1.3 Linting passes: `uv run ruff check .`
- [x] 1.4 Type checking passes: `uv run mypy .`

#### Manual

- [x] 1.5 Cancel link visible next to Save trip on `/trips/new/`
- [x] 1.6 Clicking Cancel navigates to trip list without creating a trip
- [x] 1.7 Typing into fields then clicking Cancel creates no trip and shows no confirmation dialog
