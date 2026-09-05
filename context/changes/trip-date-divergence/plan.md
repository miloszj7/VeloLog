# Trip Date Divergence Implementation Plan

## Overview

`Trip.date` is a single field the rider types in by hand ("the day the tour started");
`gpx.stages.trip_span` derives a separate, more precise span from the GPX stages'
timestamps. The two are never compared today. Real trips in this database (21, 22, 23)
show the two disagreeing by months with no indication anywhere in the UI — the trip list
and delete-confirmation pages show `Trip.date`, while the detail page shows `trip_span`
*instead of* `Trip.date` whenever chronology is established, silently dropping the
rider's own value. This plan adds a shared, tolerance-based divergence check and surfaces
it in three places: an inline note on the trip detail page, a non-blocking warning on GPX
upload, and a small indicator on the trip list.

## Current State Analysis

- `Trip.date` (`trips/models.py:10`) is a plain `DateField`, validated only for not being
  too far in the future (`trips/forms.py:46-62`, `FUTURE_TRIP_DATE_TOLERANCE = timedelta(days=1)`
  at `trips/constants.py:13`).
- `gpx.stages.trip_span(tracks)` (`gpx/stages.py:60-93`) returns `(min(started_at),
  max(ended_at))` only when `chronology_is_established(tracks)` is true, `None` otherwise.
  It is computed fresh on every render and stored nowhere (roadmap item E-10, closed —
  `context/foundation/engineering-backlog.md:119-124`).
- Two views build this context today, and must keep doing so identically:
  `TripDetailView.get_context_data` (`trips/views.py:85-107`) and
  `GpxUploadView.get_context_data` (`gpx/views.py:74-94`, re-rendering the same template
  on a rejected upload). Both docstrings already say explicitly that a context key present
  in one and missed in the other renders a wrong branch over healthy data — any new key
  this plan adds must go in both.
- `trip_detail.html` (`trips/templates/trips/trip_detail.html:32-40`) shows `trip_span`
  *or* `trip.date`, never both — the rider's own value disappears the moment chronology is
  established, with no note that it ever differed.
- `trip_list.html` (`trips/templates/trips/trip_list.html:15`) and
  `trip_confirm_delete.html` (`trips/templates/trips/trip_confirm_delete.html:9`) show only
  `trip.date` and never reference `trip_span` at all.
- No prior document (`context/archive/**`, `context/foundation/roadmap.md`) discusses a
  divergence check between the two — E-10 deliberately chose silent fallback, not
  comparison. This is genuinely new scope, not a revisit of a closed decision.
- No `messages.warning(...)`/`.info(...)` call exists anywhere in the codebase yet — only
  `SuccessMessageMixin`'s auto-generated success message. `base.html:35-39` already renders
  `alert-{{ message.tags }}`, and `MESSAGE_TAGS` (`velo_log/settings.py:287-289`) only
  remaps `ERROR`; `WARNING` already resolves to Bootstrap's `alert-warning` with no
  settings change needed.
- `GpxUploadForm.clean_file` (`gpx/forms.py:36-96`) sets `self.instance.started_at` from
  the parsed file but has no access to `self.instance.trip` — that is assigned later, in
  `GpxUploadView.form_valid` (`gpx/views.py:118`). The upload-time check therefore belongs
  in the view, not the form.

## Desired End State

- A shared, named tolerance and a single comparison helper decide "does this observed
  date diverge from `Trip.date`" — used identically everywhere the question is asked.
- The trip detail page shows the GPX-derived span as it does today, plus a small
  secondary note naming the logged `Trip.date` whenever the two diverge beyond tolerance.
- A successful GPX upload whose stage's `started_at` diverges from `Trip.date` raises a
  non-blocking `messages.warning`, shown once, after the redirect to the detail page. The
  upload still succeeds either way.
- The trip list shows a small warning indicator next to any trip whose earliest known
  stage timestamp diverges from its logged date, computed in one query with no N+1.
- Verification: visiting trips 21, 22, and 23 (documented above as real, currently-silent
  divergences) shows the note on the detail page and the indicator on the list; uploading
  a new stage with a wildly different date shows the warning message.

### Key Discoveries:

- `timed-track-day-2.gpx` (`tests/gpx/fixtures/`) is fixture data whose `started_at` is
  exactly one day after the `trip` fixture's date (`tests/gpx/conftest.py:31-32`,
  `2026-06-01` vs. `2026-06-02`) and is used by passing tests today
  (`tests/gpx/test_gpx_upload.py:130-164`). The tolerance chosen (`>1 day`, strictly
  greater) must not flag this case, or existing tests newly assert a warning that
  changes their behavior.
- `tests/trips/test_trip_detail_span.py` deliberately stores `STORED_TRIP_DATE = date(2026,
  5, 20)` *outside* every stage's instants (module docstring, lines 8-11) specifically so
  "the span rendered" and "the stored date rendered" are distinguishable substrings. Two
  of its tests assert `date_format(STORED_TRIP_DATE) not in body` — this plan's detail-page
  note intentionally reintroduces that formatted date into the page when the two diverge,
  so those two assertions must be rewritten (see Phase 2), not left to fail as an
  unnoticed regression.
- Every existing multi-stage test in `tests/trips/test_trip_detail_map.py` and
  `test_trip_detail_stats.py` includes a stage started on the trip's own fixture date
  (`2026-06-01`), so the *earliest* stage timestamp always matches `Trip.date` exactly in
  those fixtures — the new divergence note/flag will not fire for them, and no other test
  files need updating.

## What We're NOT Doing

- Not changing `Trip.date`'s storage, validation range, or the E-10 derivation itself —
  `trip_span`/`chronology_is_established` are untouched.
- Not auto-correcting or syncing `Trip.date` to match GPX data — divergence is surfaced,
  never resolved automatically.
- Not adding a link from the divergence note/warning to the trip edit form — purely
  informational, per the "diary not planner" framing already in `trips/forms.py:43`.
- Not touching `trip_confirm_delete.html` — out of scope, not part of the original ask.
- Not requiring `chronology_is_established` (full-trip timing) for the upload-time warning
  or the list-page indicator — both compare against a single observed timestamp (the
  uploaded stage's own `started_at`, or the list's per-trip earliest stage timestamp)
  independent of whether every stage is timed.

## Implementation Approach

Introduce one small pure module (`trips/dates.py`) holding the tolerance constant's
comparison logic, then wire it into the three existing render/upload paths without
touching the derivation logic those paths already trust. Each of the three surfaces reads
its own already-available datum (`trip_span[0]`, the just-uploaded stage's `started_at`,
or an annotated per-trip minimum) — there is no new query on the detail/upload paths, and
the list page gets exactly one added aggregate per request.

## Phase 1: Shared tolerance constant and comparison helper

### Overview

Add the named tolerance and the one function every other phase calls, with its own unit
tests, before anything reads it from a view or template.

### Changes Required:

#### 1. Divergence tolerance constant

**File**: `trips/constants.py`

**Intent**: Add a second named tolerance, modeled on `FUTURE_TRIP_DATE_TOLERANCE`
immediately above it, governing how far a GPX-observed date may drift from `Trip.date`
before it counts as "diverges."

**Contract**: `TRIP_DATE_DIVERGENCE_TOLERANCE: timedelta = timedelta(days=1)`. Document why
`1 day` (not `0`): it absorbs the same UTC-storage-vs-local-input slack
`FUTURE_TRIP_DATE_TOLERANCE` exists for, and must not flag `tests/gpx/fixtures/timed-track-day-2.gpx`
against the `trip` fixture (exactly one day apart) as diverging.

#### 2. Comparison helper

**File**: `trips/dates.py` (new)

**Intent**: One pure function comparing a stored `Trip.date` against an observed
timestamp, used identically by the detail page, the upload warning, and the list
indicator.

**Contract**: `trip_date_diverges(trip_date: date, observed: datetime, tolerance:
timedelta = TRIP_DATE_DIVERGENCE_TOLERANCE) -> bool`. Converts `observed` via
`django.utils.timezone.localtime(observed).date()` before comparing — the same conversion
`trip_detail.html`'s `|date` filter already performs on datetimes (its own comment notes
`expects_localtime`), so the boolean this function returns agrees with what the template
would show if it rendered both dates directly. Returns `abs(observed_date - trip_date) >
tolerance`, strictly greater — matching `TripForm.clean_date`'s `value >
localdate() + tolerance` boundary convention exactly (equal-to-tolerance does not diverge).

### Success Criteria:

#### Automated Verification:

- Unit tests pass: `uv run pytest tests/trips/test_dates.py -v`
- Type checking passes: `uv run mypy .`
- Linting passes: `uv run ruff check .`

#### Manual Verification:

- None — pure function, no user-facing surface yet.

---

## Phase 2: Trip detail page divergence note

### Overview

Show a secondary, muted note under the GPX-derived span whenever it diverges from
`Trip.date`, in both views that render `trip_detail.html`.

### Changes Required:

#### 1. Context key in both views

**File**: `trips/views.py`, `gpx/views.py`

**Intent**: Add one new context key, computed identically in `TripDetailView.get_context_data`
and `GpxUploadView.get_context_data`, following the same parity convention their docstrings
already document for `stages`/`map_config`/`chronology_established`/`trip_span`/`whole_trip_stats`.

**Contract**: `context["date_diverges"] = trip_span_value is not None and
trip_date_diverges(trip.date, trip_span_value[0])`, where `trip_span_value` is the same
`trip_span(tracks)` result already computed on that line. `False` (never `None`) when
`trip_span` itself is `None`, so the template needs only one boolean, not a three-state
check. Update both docstrings' enumerated context-key lists to name this key alongside the
existing four.

#### 2. Template note

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: Render a small muted line naming the logged `Trip.date` under the span, only
when `date_diverges` is true. Update the existing `{% comment %}` block (lines 19-31)
— it currently asserts the span and the stored date are mutually exclusive on the page,
which stops being true the moment this note exists.

**Contract**: Inside the existing `{% if trip_span %}` branch, after the same-day/range
paragraph, add `{% if date_diverges %}<p class="text-muted small mb-1">Logged as
{{ trip.date }}</p>{% endif %}`. The `{% else %}` branch (bare `trip.date`, no span) is
unchanged — divergence has nothing to compare against there.

#### 3. Existing test updates

**File**: `tests/trips/test_trip_detail_span.py`

**Intent**: `STORED_TRIP_DATE` (2026-05-20) is more than a day before every stage in this
file's fixtures, so it will now diverge and the new note will render. Update the two
tests currently asserting `date_format(STORED_TRIP_DATE) not in body`
(`test_a_fully_timed_multi_day_tour_shows_the_span_it_was_ridden_over`,
`test_a_single_day_span_prints_one_date_rather_than_a_range_repeating_itself`) to instead
assert the note renders (`"Logged as" in body` and `date_format(STORED_TRIP_DATE) in
body`), while still asserting the *primary* heading line shows the span, not the stored
date, as it does today. Update the module docstring (lines 1-11) — the "never share a
substring" framing needs a caveat for the new, deliberate exception.

### New tests

**File**: `tests/trips/test_trip_detail_span.py`

**Intent**: Add at least one case each for: divergence exactly at the tolerance boundary
(no note), one day beyond it (note renders), and the existing
`test_the_rejected_upload_re_render_keeps_the_span` case gaining an assertion that the note
also renders identically on the upload re-render path (context-key parity, exercised
end-to-end rather than only unit-tested in Phase 1).

### Success Criteria:

#### Automated Verification:

- Unit/integration tests pass: `uv run pytest tests/trips/test_trip_detail_span.py -v`
- Full suite still passes: `uv run pytest --cov`
- Type checking passes: `uv run mypy .`
- Linting and formatting pass: `uv run ruff check . && uv run black --check .`

#### Manual Verification:

- Visiting trips 21, 22, and 23 (the real divergent trips found during analysis) shows
  the "Logged as ..." note under the span.
- A trip whose `Trip.date` matches its stages (e.g. any fixture-created trip in this repo)
  shows no note.

---

## Phase 3: GPX upload-time warning

### Overview

Warn, without blocking the upload, when the just-uploaded stage's `started_at` diverges
from `Trip.date`.

### Changes Required:

#### 1. Divergence check in `form_valid`

**File**: `gpx/views.py`

**Intent**: After the new stage is known to be valid and before (or immediately after)
saving it, compare its `started_at` to `self.trip.date` and raise a `messages.warning`
if it diverges. Independent of `chronology_is_established` — this checks the one stage
just uploaded, not the whole trip's derived span, so it fires even on a trip whose other
stages aren't timed yet.

**Contract**: In `form_valid`, after `form.instance.trip = self.trip` and before returning
`super().form_valid(form)`: if `form.instance.started_at is not None and
trip_date_diverges(self.trip.date, form.instance.started_at)`, call
`messages.warning(self.request, ...)` naming both dates (formatted via
`django.utils.formats.date_format`, matching the formatting the templates already use).
No warning when `started_at` is `None` (untimed upload — nothing to compare).

### New tests

**File**: `tests/gpx/test_gpx_upload.py`

**Intent**: Cover: an upload whose stage date diverges beyond tolerance shows the warning
text on the post-redirect detail page; an upload exactly at the tolerance boundary
(`timed-track-day-2.gpx` against the `trip` fixture, already used by
`test_two_uploads_in_reverse_ride_order_come_back_in_ride_order`) shows no warning; an
untimed upload shows no warning; the upload still succeeds (stage persisted, "Stage
added." still shown) whether or not the warning fires.

### Success Criteria:

#### Automated Verification:

- Unit/integration tests pass: `uv run pytest tests/gpx/test_gpx_upload.py -v`
- Full suite still passes: `uv run pytest --cov`
- Type checking passes: `uv run mypy .`
- Linting and formatting pass: `uv run ruff check . && uv run black --check .`

#### Manual Verification:

- Uploading a GPX file whose recorded date is months from the trip's logged date (as with
  trips 21/22/23) shows a yellow warning banner after the redirect, and the stage is still
  saved.
- Uploading a normal same-week file shows no warning.

---

## Phase 4: Trip list divergence indicator

### Overview

Show a small per-row indicator on the trip list when a trip's earliest known stage
timestamp diverges from its logged date, in one query.

### Changes Required:

#### 1. Diverging-trip-ids lookup

**File**: `trips/views.py`

**Intent**: Compute which of the listed trips diverge in one extra query, without
annotating the `Trip` queryset itself or mutating model instances — `TripListView.get_queryset`'s
declared `-> QuerySet[Trip]:` return type would erase any `.annotate()`-added attribute's
django-stubs typing the moment it's returned, and `Trip` has no `date_diverges` field for
an ad hoc instance attribute to satisfy under `mypy --strict`. A separate small aggregate
query, reduced to a plain `set[int]` of pks, sidesteps both problems.

**Contract**: Add `get_context_data` to `TripListView`. Query
`GpxTrack.objects.filter(trip__in=context["object_list"]).values("trip_id").annotate(earliest=Min("started_at"))`,
build a `dict[int, datetime]` from the result, then `context["diverging_trip_ids"] =
{trip.pk for trip in context["object_list"] if (earliest := earliest_by_trip_id.get(trip.pk))
is not None and trip_date_diverges(trip.date, earliest)}`. One extra query for the whole
list, not per row.

#### 2. Template indicator

**File**: `trips/templates/trips/trip_list.html`

**Intent**: Show a small, unobtrusive marker next to `trip.date` when the trip's pk is in
the diverging set.

**Contract**: Inside the existing `<small class="text-muted">{{ trip.date }}</small>`,
add a conditional `<span>` (e.g. a warning-colored glyph with a `title` attribute
explaining it) rendered only when `{% if trip.pk in diverging_trip_ids %}`.

### New tests

**File**: `tests/trips/test_trip_list.py`

**Intent**: Cover: a trip with a diverging stage shows the indicator; a trip with no
stages, or with stages matching its date, shows none; a list of several trips issues a
fixed, small number of queries regardless of how many trips have stages (guard against a
future N+1 regression on this aggregate), asserted with the `django_assert_num_queries`
pytest-django fixture — the established idiom for this in the codebase
(`tests/gpx/test_gpx_signals.py:341-367`, called out explicitly in
`tests/test_assertion_strength.py:209`).

### Success Criteria:

#### Automated Verification:

- Unit/integration tests pass: `uv run pytest tests/trips/test_trip_list.py -v`
- Full suite still passes: `uv run pytest --cov`
- Type checking passes: `uv run mypy .`
- Linting and formatting pass: `uv run ruff check . && uv run black --check .`
- Suite credibility gate passes: `uv run pytest -m bite_proof`

#### Manual Verification:

- The trips list shows the indicator next to trips 21, 22, and 23.
- The list page's query count does not visibly regress (spot-check via Django Debug
  Toolbar or the query-count test above) when several trips have many stages each.

---

## Testing Strategy

### Unit Tests:

- `trips/dates.py`'s `trip_date_diverges`: same-day, at-tolerance-boundary (not
  diverging), one day beyond tolerance (diverging), and a non-UTC-`TIME_ZONE` override
  proving the `timezone.localtime` conversion is exercised, not just a bare `.date()` call.

### Integration Tests:

- Detail page renders/omits the note correctly across chronology states (span present and
  diverging, span present and not diverging, span absent).
- Upload view emits/omits the warning correctly, and the upload succeeds either way.
- List page renders/omits the indicator correctly and does not add a query per row.

### Manual Testing Steps:

1. Open trips 21, 22, and 23 in the running app; confirm the detail-page note, the list
   indicator, and (for a fresh upload against one of them) the upload warning all appear.
2. Create a trip and upload a GPX file whose date matches; confirm no note, no warning, no
   indicator anywhere.

## Performance Considerations

The only query-shape change is the list page's `annotate(Min(...))`, which adds one
aggregate to the existing owner-scoped query rather than a query per row — verified by the
`assertNumQueries`-style test in Phase 4.

## Migration Notes

None. No model or schema changes — every value used already exists (`Trip.date`,
`GpxTrack.started_at`) or is computed in Python/SQL at request time.

## References

- Real divergent data used to validate this plan: trips 21, 22, 23 in the local database
  (found via `manage.py shell`, `trip_span` vs. `Trip.date` diverge by 1-4 months on all
  three).
- E-10 closure reasoning: `context/foundation/engineering-backlog.md:119-124`,
  `context/archive/2026-09-02-multi-stage-gpx-upload/research.md:388-437`,
  `context/archive/2026-09-02-multi-stage-gpx-upload/plan.md` (where `trip_span` and
  `chronology_is_established` were built).
- Existing tolerance precedent: `trips/constants.py:13`, `trips/forms.py:46-62`.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Shared tolerance constant and comparison helper

#### Automated

- [x] 1.1 Unit tests pass: `uv run pytest tests/trips/test_dates.py -v` — f3df8b8
- [x] 1.2 Type checking passes: `uv run mypy .` — f3df8b8
- [x] 1.3 Linting passes: `uv run ruff check .` — f3df8b8

### Phase 2: Trip detail page divergence note

#### Automated

- [x] 2.1 Unit/integration tests pass: `uv run pytest tests/trips/test_trip_detail_span.py -v` — 496b4ae
- [x] 2.2 Full suite still passes: `uv run pytest --cov` — 496b4ae
- [x] 2.3 Type checking passes: `uv run mypy .` — 496b4ae
- [x] 2.4 Linting and formatting pass: `uv run ruff check . && uv run black --check .` — 496b4ae

#### Manual

- [x] 2.5 Trips 21, 22, and 23 show the "Logged as ..." note under the span — 496b4ae
- [x] 2.6 A trip whose Trip.date matches its stages shows no note — 496b4ae

### Phase 3: GPX upload-time warning

#### Automated

- [x] 3.1 Unit/integration tests pass: `uv run pytest tests/gpx/test_gpx_upload.py -v` — 34b531e
- [x] 3.2 Full suite still passes: `uv run pytest --cov` — 34b531e
- [x] 3.3 Type checking passes: `uv run mypy .` — 34b531e
- [x] 3.4 Linting and formatting pass: `uv run ruff check . && uv run black --check .` — 34b531e

#### Manual

- [x] 3.5 A wildly-diverging upload shows the warning banner after redirect and the stage still saves — 34b531e
- [x] 3.6 A normal same-week upload shows no warning — 34b531e

### Phase 4: Trip list divergence indicator

#### Automated

- [x] 4.1 Unit/integration tests pass: `uv run pytest tests/trips/test_trip_list.py -v` — 5644249
- [x] 4.2 Full suite still passes: `uv run pytest --cov` — 5644249
- [x] 4.3 Type checking passes: `uv run mypy .` — 5644249
- [x] 4.4 Linting and formatting pass: `uv run ruff check . && uv run black --check .` — 5644249
- [x] 4.5 Suite credibility gate passes: `uv run pytest -m bite_proof` — 5644249

#### Manual

- [x] 4.6 The trips list shows the indicator next to trips 21, 22, and 23 — 5644249
- [x] 4.7 List page query count does not regress with several multi-stage trips — 5644249
