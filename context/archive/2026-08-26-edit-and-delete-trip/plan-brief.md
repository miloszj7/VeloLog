# Edit and Delete a Trip (S-04) + Future-Date Validation (E-08) — Plan Brief

> Full plan: `context/changes/edit-and-delete-trip/plan.md`
> Frame brief: `context/changes/edit-and-delete-trip/frame.md`
> Research: `context/changes/edit-and-delete-trip/research.md`

## What & Why

Roadmap slice S-04: a rider can edit a trip's name, date and description (FR-007) or
delete the trip entirely (FR-008) — both must-have PRD requirements, and the two verbs
`prd.md:43`'s isolation guardrail names that no view has ever exercised. Bundled in is
E-08, whose framing held: *"E-08 is a validation gap, and the cheap fix the row proposed is
the right one — but the product decision it was gated on is not open, and two coexisting
defects have been fused into one."*

The reason this is not routine CRUD: **delete is the slice that inherits a named data
obligation.** S-03 deferred GPX orphan-file cleanup here three times, including a comment
pinned inside a live test. Today, deleting a trip cascades its track rows and strands every
`.gpx` file on the Railway Volume permanently.

## Starting Point

`Trip` has `name`/`date`/`description`/`owner` and three views — list, create, detail — all
using one authorization idiom: an owner-scoped `get_queryset()` yielding **404, not 403**
(`trips/views.py:59-66`), documented in-code as *"the project's entire authorization
story"*. `TripForm` is a 22-line `ModelForm` with **no `clean_*()` method of any kind**.
There are no edit/delete controls anywhere, no confirmation-page pattern in the repo, and
no GPX file cleanup on any deletion path. The frame brief already established that a
future date's entire observable effect is sorting to the top of the trip list — five
consumers, zero computations, no downstream harm.

## Desired End State

A rider on a trip's detail page sees **Edit** and **Delete**. Edit opens the same form they
created the trip with, retitled and pre-filled; saving returns them to the trip. Delete
asks first, on its own page, naming the trip and warning that the GPX file goes too;
confirming removes the trip, its track rows, **and the files from the Volume**. Another
rider's trip 404s on every new route, for every verb. A trip dated far in the future is
rejected at the form, and the date field finally says what it means.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Future dates | Block them | Retrospective-only use ("always after riding") plus a named Non-Goal — *"not a planner"* — made the binary already-decided in committed documents. | Frame |
| E-08 also gets a field label | Yes | Choosing the constraint is choosing enough meaning to write the label; the second fused defect is a label, not a migration. | Frame |
| Orphan file cleanup | `post_delete` signal on `GpxTrack` | The only hook that also covers admin `delete_selected`, cascades, and future queryset deletes — and both models are admin-registered, so bulk delete is live today. | Plan |
| Upload path's explicit `on_commit` | Removed; the receiver owns cleanup | Keeping both would schedule two deletes of the same file; the receiver also fires per row *actually deleted*, subsuming review finding F2 by construction. | Plan |
| Delete confirmation | GET confirmation page | Deletion is irreversible with no soft-delete, and it destroys a GPX file the rider cannot re-derive; `DeleteView` gives the page for free. | Plan |
| Entry points | Detail page only | The detail page is the trip's canonical surface; a destructive control on the scan-oriented list is the highest-misclick placement available. | Plan |
| Edit template | Reuse `trip_form.html` with conditionals | Keeps the four non-negotiable form conventions in one place where they cannot drift, and turns `UpdateView`'s silent-default trap into a visible decision. | Plan |
| UTC boundary | `+1 day` tolerance | Provably exact — no timezone is more than 14h ahead of UTC, so a local date can never exceed the UTC date by more than one day. | Research + Plan |
| Existing future-dated trips | Stay editable via `changed_data` guard | An unguarded rule would make them uneditable in the very slice that introduces editing. | Research |
| Audit logging | None | An INFO line is invisible in production and the formatter ignores `extra={}` — it would log nothing useful while appearing to. | Plan |
| Start/end date split | Out of scope, new backlog row | A real owner insight, but it inverts S-04's Low risk basis, needs a PRD amendment, and touches ~31 test sites 15 days before the deadline. | Frame |

## Scope

**In scope:** `TripUpdateView` + route + template conditionals; `TripDeleteView` + route +
the repo's first confirmation page; Edit and Delete links on the detail page; a
`post_delete` receiver owning GPX file cleanup on every deletion path; `clean_date()` with
the `+1 day` tolerance and the `changed_data` escape, plus the date field's label; two new
trips test files, one new gpx test file; roadmap/backlog/docs bookkeeping.

**Out of scope:** splitting `Trip.date` into start/end; soft delete, undo or a trash bin;
an audit log line; edit/delete controls on the trip list; any CSS; `message.tags` in
`base.html`; a permission mixin; migrations.

## Architecture / Approach

Both new views are CBVs following the one existing idiom — an owner-scoped `get_queryset()`
that turns another rider's pk into a 404. File cleanup moves from an explicit call inside
`GpxUploadView.form_valid` to a `post_delete` receiver on `GpxTrack` that schedules
`transaction.on_commit(...)`, so rows go inside `atomic()` and files go after commit. That
single move covers four deletion paths that previously had one between them.

The load-bearing mechanism is non-obvious and was verified against installed Django source:
`Collector.can_fast_delete()` returns `False` when a model has `post_delete` listeners
(`deletion.py:186-206`). Without a receiver, a `Trip.delete()` cascade fast-deletes
`GpxTrack` in one SQL statement and never materializes the rows — there is no instance to
read a file path from. Registering the receiver is what makes the cascade cleanable at all.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Edit a trip | `TripUpdateView`, route, template conditionals, Edit link, `test_trip_edit.py` | The create flow's Cancel markup is asserted verbatim; conditionals must leave it byte-identical |
| 2. Signal owns file cleanup | `gpx/signals.py`, `GpxConfig.ready()`, explicit `on_commit` removed, cascade test now asserts the file is gone | Refactors a path three review findings hardened; the two existing `on_commit` tests must survive unchanged |
| 3. Delete a trip | `TripDeleteView`, route, confirmation page, Delete link, `test_trip_delete.py` | django-stubs arity — `DeleteView` takes **two** params and needs its own `SuccessMessageMixin[Form]`; wrong arity raises at import |
| 4. E-08 (cut line) | `clean_date()` + tolerance + `changed_data` guard + field label | `branch = true` means a half-covered `clean_date()` shows as a gap; `help_text` on the model would generate a migration |
| 5. Bookkeeping | S-04 and E-08 closed, start/end backlog row opened, `AGENTS.md` updated | A decision commit landing before the fix it describes reads as a lie in the log |

**Prerequisites:** S-02 (`create-and-list-trips`, done). S-03 is done, so the cleanup
mechanism and its three hardening findings are already in the tree to copy. No new
dependency, no migration expected.

**Estimated effort:** ~4–5 sessions across 5 phases; Phase 4 droppable and Phase 5 is
documentation only.

## Open Risks & Assumptions

- **Phase 2 changes a review-hardened path.** Three findings hardened
  `GpxUploadView.form_valid`; removing its explicit `on_commit` loop is deliberate, not a
  regression, but the two existing `on_commit` tests are the only proof — they must pass
  unedited.
- **A silent-cleanup assertion is easy to fake.** Any file-removal test outside
  `django_capture_on_commit_callbacks(execute=True)` passes while proving nothing. Called
  out as a per-phase automated criterion rather than trusted.
- **Disabling fast-delete is an accepted cost.** One `DELETE` per row instead of one bulk
  statement, bounded by one track per trip in v1 and a rare user-initiated action.
- **The admin bulk-delete manual check is the one that justifies the signal.** If it is
  skipped, the whole mechanism choice goes unverified.
- **E-08 may not ship.** If the `2026-09-10` deadline bites, Phase 4 is dropped and E-08
  stays open for a third time — with the frame brief as its record rather than a bare row.
- **Assumption:** no model field change is needed, so no migration appears. Phase 4's
  label is the one thing that could break this, which is why the form's `Meta` is preferred
  over the model's.

## Success Criteria (Summary)

- A rider can fix a typo in a trip's name and can delete a trip they no longer want, and is
  asked before the deletion happens.
- Deleting a trip — from the app **or** the admin, singly **or** in bulk — leaves no `.gpx`
  file behind on the Volume.
- A second rider gets a 404 on every edit and delete URL of the first rider's trips, and
  the trips are provably still there afterwards.
