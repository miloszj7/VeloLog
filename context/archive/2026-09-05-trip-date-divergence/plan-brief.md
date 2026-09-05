# Trip Date Divergence — Plan Brief

> Full plan: `context/changes/trip-date-divergence/plan.md`

## What & Why

`Trip.date` is a date the rider types by hand; `trip_span` is derived separately from GPX
stage timestamps. The two can diverge — confirmed on real trips 21, 22, and 23, where the
gap is 1-4 months — and today nothing shows that anywhere: the trip list shows only
`Trip.date`, and the detail page shows only `trip_span` once chronology is established,
silently dropping the rider's own value with no hint the two ever disagreed.

## Starting Point

`gpx.stages.trip_span` and `chronology_is_established` (built in the archived
`multi-stage-gpx-upload` change, closing roadmap item E-10) already compute the derived
span correctly and are fully trusted — this plan does not touch them. E-10 deliberately
chose a silent fallback over any comparison, so a divergence check is new scope, not a
revisit.

## Desired End State

Opening a trip whose logged date and GPX data disagree shows a small note under the span
("Logged as ..."); uploading a stage whose date is far from the trip's logged date shows a
non-blocking warning after the upload succeeds; the trip list shows a small indicator next
to any trip with this kind of mismatch — all computed from a single shared tolerance rule,
no new database migration.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Divergence tolerance | `>1 day` (strictly greater), mirroring `FUTURE_TRIP_DATE_TOLERANCE` | Absorbs the same UTC-storage-vs-local-input slack already reasoned about elsewhere, and must not flag the existing `timed-track-day-2.gpx` fixture (exactly 1 day off) | Plan |
| Upload-time comparison basis | The just-uploaded stage's own `started_at`, independent of `chronology_is_established` | Fires even before every stage on the trip is timed, rather than waiting on the whole-trip derivation | Plan |
| Detail-page UI | Inline muted note beside the span | Matches the page's existing quiet typographic treatment; this is informational, not a validator | Plan |
| Upload-time signal | `messages.warning(...)`, shown after redirect | Reuses the exact mechanism the existing "Stage added." success message already uses | Plan |
| Constant location | `trips/constants.py`, beside `FUTURE_TRIP_DATE_TOLERANCE` | Both constants govern `Trip.date` semantics and belong together | Plan |
| Actionability | Purely informational, no edit link | A mismatch isn't always wrong — `Trip.date` is deliberately the rider's own memory, not required to match GPS | Plan |
| List-page scope | Included, via a single annotated query | User expanded scope to cover the list page too, using `Min("tracks__started_at")` to avoid N+1 | Plan |

## Scope

**In scope:**
- Shared tolerance constant + comparison helper (`trips/constants.py`, `trips/dates.py`)
- Trip detail page divergence note
- GPX upload-time non-blocking warning
- Trip list divergence indicator

**Out of scope:**
- Any change to `Trip.date` storage, validation, or the E-10 derivation itself
- Auto-syncing `Trip.date` to GPX data
- `trip_confirm_delete.html`
- Any link from the note/warning to the trip edit form

## Architecture / Approach

One pure function (`trips/dates.py::trip_date_diverges`) is the single source of truth for
"do these two dates diverge," called from three places that each already have the datum
they need: `trip_span[0]` on the detail page, the just-uploaded stage's `started_at` on
upload, and a `set[int]` of diverging pks (from one extra `Min()`-aggregate query, kept
separate from the `Trip` queryset to avoid tripping `mypy --strict`) on the list. No new
queries beyond that one added aggregate; no new tables or migrations.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Tolerance & helper | `TRIP_DATE_DIVERGENCE_TOLERANCE` + `trip_date_diverges()`, unit-tested | Getting the tolerance boundary and timezone conversion exactly right, since three other phases depend on it |
| 2. Detail page note | Inline "Logged as ..." note when the span diverges | Two existing tests in `test_trip_detail_span.py` assert the stored date is *absent* from the body — those must be deliberately updated, not left to silently fail |
| 3. Upload warning | `messages.warning(...)` on a divergent upload | First-ever use of Django's warning-level messages in this codebase — low risk, but sets the pattern |
| 4. List indicator | Per-row warning icon on the trip list | Must stay one query for the whole list (`annotate(Min(...))`), not one per trip |

**Prerequisites:** None — no external dependencies, no schema changes.
**Estimated effort:** ~1 session across 4 phases; each phase is a small, independently
shippable slice.

## Open Risks & Assumptions

- The tolerance value (`>1 day`) is a judgment call, not derived from data — if it proves
  too noisy or too quiet in practice, it's a one-line constant change, not a redesign.
- The list-page indicator (Phase 4) was an in-session scope expansion beyond the original
  two-surface ask; it's designed to stay cheap (one annotated query), but is the most
  optional phase if time is tight.

## Success Criteria (Summary)

- Trips 21, 22, and 23 show the note, the warning (on a fresh upload), and the list
  indicator — the divergence is visible instead of silent.
- No existing test regresses; the two `test_trip_detail_span.py` assertions that would
  otherwise break are updated deliberately, not left red.
- The trip list's query count does not grow with the number of trips shown.
