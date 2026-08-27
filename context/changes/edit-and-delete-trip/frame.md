# Frame Brief: E-08 — future-dated trips in `TripForm`

> Framing step before /10x-plan. This document captures what is *actually*
> at issue, separated from what was initially assumed.

## Reported Observation

`TripForm` accepts a future-dated trip and saves it. No validation rejects it.
Found during S-02 Phase 3 manual verification
(`context/archive/2026-08-23-create-and-list-trips/plan.md:462`).

## Initial Framing (preserved)

- **User's stated cause or approach**: a missing-validation gap on the date field.
- **User's proposed direction**: *"Decide product intent (block future dates? allow and
  label as 'planned'?) then add `clean_date()` if blocking is the answer."*
- **Pre-dispatch narrowing** (user's own words, 2026-08-26):
  - Date meaning — *"i havent think about it. for one day trip it is simple, for mulit
    day, better will be two date fields - start and end"*
  - Usage — **"Always after riding"**
  - Observed harm — **"Nothing broke, it just saved"**

## Dimension Map

1. **Validation gap** — `TripForm` has no `clean_*()` hook at all. ← initial framing
2. **Undefined date semantics** — nothing defines what `Trip.date` *means*, so "future"
   has no referent to be evaluated against.
3. **Wrong field shape** — one `DateField` on a multi-day-tour product; any rule written
   now would be provisional against a future start/end split.
4. **No downstream harm** — a future date may be entirely inert, making E-08 a row to
   close rather than a defect to fix.
5. **Product intent** — retrospective diary vs. planner. *(Settled by the user's
   "always after riding"; not investigated further.)*

## Hypothesis Investigation

| Hypothesis | Evidence | Verdict |
| --- | --- | --- |
| 1. Validation gap (initial framing) | `TripForm` has no `clean_*()` of any kind (`trips/forms.py:13-21`); `date` has zero negative-path coverage — posted 6×, asserted 0×, while `name` has a blank-rejection test (`tests/trips/test_trip_creation.py:36`) | **STRONG** |
| 2. Undefined date semantics | Confirmed absent everywhere: bare `models.DateField()` (`trips/models.py:10`), zero `help_text`/`verbose_name`/`label=` in any app package, unlabelled `{{ trip.date }}` in both templates (`trip_list.html:11`, `trip_detail.html:16`). Archive reasoned about the *type* (`DateField` vs `DateTimeField`, `create-and-list-trips/plan.md:103`) but never cardinality or meaning | **STRONG as observation, NONE as cause** |
| 3. Wrong field shape | Never discussed anywhere — `grep` for start/end/date-range across `context/`, all `*.md`, and `git log -S` returns zero hits. Not in any FR, Parked row, Non-Goal, or backlog item. Cost: ~31 test touch points across 9 files, 5 production files, a migration against live data, plus PRD + roadmap amendments | **REAL but OUT OF SCOPE** |
| 4. No downstream harm | Five consumers total: one sorts (`trips/models.py:19`), four display (`trips/admin.py:17`, two templates, field decl). **Zero computations.** No `date.today()`, `timezone.now()`, `timedelta`, or date comparison anywhere in app code. GPX timestamps are parsed over and discarded (`gpx/parsing.py:154-162`), so no second source of truth exists that could contradict `trip.date` | **STRONG** |

## Narrowing Signals

- **"Always after riding"** — settles product intent. A retrospective-only user never
  legitimately needs a future date. Combined with `prd.md:112` (*"not a planner"*, a
  named Non-Goal), the binary E-08 posed was **already decided in committed documents**;
  "allow and label as planned" is excluded by a Non-Goal.
- **"Nothing broke, it just saved"** — sets severity. Confirmed structurally: a future
  date's entire observable effect is sorting to the top of the trip list, which is
  `ordering = ["-date", "-id"]` correctly ordering the value it was given.
- **"Better will be two date fields"** — a genuine forward-looking product insight, but
  the user volunteered it as an idea, not a current pain. It has never been raised
  before in the project's history.
- **The adversarial pass found the reframe's own premise already answered**: `prd.md:99`
  assigns multi-day stage chronology to **GPS timestamps**, not `Trip.date`. The
  feature that most needs multi-day temporal semantics explicitly routes around this field.

## Cross-System Convention

This project has an established, repeatedly-used move for closing a backlog row by
**decision rather than code**: E-05 marked `done` with a narrative note and zero
application code (`roadmap.md:157`); E-03 marked partial with the residue stated inline
(`roadmap.md:154`); review findings closed as `ACCEPTED — no code change` with a stated
revisit trigger (`ci-quality-gates/reviews/impl-review.md:327`). A planned `clean_name()`
was deleted rather than written, on coverage grounds
(`create-and-list-trips/reviews/plan-review.md` F3) — whose blind-spot line names S-04 as
the moment a `clean_*()` hook returns. Both resolution modes are live in this repo.

## Reframed (or Confirmed) Problem Statement

> **The initial framing held. E-08 is a validation gap, and the cheap fix the row
> proposed is the right one — but the product decision it was gated on is not open,
> and two coexisting defects have been fused into one.**

I tested a reframe — *"E-08 is a symptom of undefined date semantics, not a validation
gap"* — and an adversarial pass broke it on five grounds. The decisive one: for a
retrospective-only user, `date > today` is invalid under **every** candidate referent
(start, end, loose label), so the semantic ambiguity does not block the validation
decision. The one reading that permits a legitimate future date — an end-date entered on
a tour's final evening — presupposes the very start/end split it was used to justify, and
is bounded by ~1 day.

Three refinements survive and change what /10x-plan should do:

1. **The "product intent" question was never actually open.** E-08's binary was "block?
   or allow and label as 'planned'?" — and option two is excluded by a named Non-Goal
   (`prd.md:112`), reinforced by the persona (`prd.md:29`) and vision (`prd.md:23`).
   The decision is derivable from committed artifacts; the user's answer confirms it.
2. **Two defects were fused.** A missing `clean_date()` *and* a field the user sees as an
   unlabelled "Date:" box with no stated meaning. Un-fused, both are cheap — the second
   is a **label**, not a migration. Note the arrow: choosing the constraint *is* choosing
   enough meaning to write the label.
3. **The real hazard in the naive rule is the UTC boundary, not the semantics.**
   `TIME_ZONE = "UTC"` + `USE_TZ = True` (`velo_log/settings.py:130,134`) with a
   browser-local `type="date"` widget falsely rejects a UTC+2 rider for ~2h daily. A
   start/end split would **not** fix this — both fields compare against the same clock.

## Confidence

**HIGH** — three independent investigations plus an adversarial pass that was explicitly
tasked with breaking the leading hypothesis and succeeded. Evidence is anchored
throughout; the user's three narrowing answers were decisive; and the conclusion matches
the project's own conventions for both the fix and the deferral.

## What Changes for /10x-plan

Plan the cheap fix, not a redesign. Specifically: E-08 is in scope for S-04 as a
`clean_date()`-shaped item whose product decision is **already made** (block future
dates — planning is a Non-Goal), and it should carry a **field label** stating what the
date means, since the constraint implies the meaning anyway. The plan must handle the UTC
boundary (a tolerance window) and the shared create/edit form making an existing
future-dated trip uneditable (`"date" not in self.changed_data`); admin remains the
repair path (`trips/admin.py:13-22`, no `form =`).

**Out of scope, and should be recorded as a new Engineering Backlog row rather than
actioned**: splitting `Trip.date` into start/end. It is a legitimate insight — raised by
the product owner — but it inverts the exact basis of S-04's Low risk rating (*"no new
domain concepts"*, `roadmap.md:98`), requires a PRD amendment (FR-003, FR-007, and the
Primary Success Criterion all say "a date", singular), touches ~31 test sites across 9
files plus an unattended production migration, and lands 15 days before the
`2026-09-10` hard deadline with S-05 already nominated for deferral (`roadmap.md:112`).
Its natural trigger is FR-011 (multi-stage grouping), which is where multi-day chronology
actually lives per `prd.md:99`.

## References

- Source files: `trips/forms.py:13-21`, `trips/models.py:10,19`, `trips/admin.py:17`,
  `trips/templates/trips/trip_list.html:11`, `trips/templates/trips/trip_detail.html:16`,
  `gpx/parsing.py:154-162`, `velo_log/settings.py:130,134`
- Documents: `prd.md:23,29,66,74,97,99,112`, `roadmap.md:92,98,112,157,159`
- Origin of E-08: `context/archive/2026-08-23-create-and-list-trips/plan.md:462`
- Re-deferral: `context/archive/2026-08-23-upload-gpx-and-view-map/plan-brief.md:121-122`
- Related research: `context/changes/edit-and-delete-trip/research.md` (§D, lines 171-227)
- Investigation dimensions: (2) undefined semantics, (3) field shape + prior occurrences,
  (4) downstream harm, plus one adversarial pass against the leading hypothesis
