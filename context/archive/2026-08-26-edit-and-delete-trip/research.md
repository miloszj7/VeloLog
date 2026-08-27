---
date: 2026-08-26T15:06:57+02:00
researcher: Miłosz Jarzynka
git_commit: 38ed37138d54741807bcbdeafc1727d5bc84af2c
branch: master
repository: miloszj7/VeloLog
topic: "S-04 edit and delete a trip, bundled with E-08 future-date validation"
tags: [research, codebase, trips, gpx, authorization, media-lifecycle, forms]
status: complete
last_updated: 2026-08-26
last_updated_by: Miłosz Jarzynka
---

# Research: Edit and delete a trip (S-04) + future-date validation (E-08)

**Date**: 2026-08-26T15:06:57+02:00
**Researcher**: Miłosz Jarzynka
**Git Commit**: `38ed37138d54741807bcbdeafc1727d5bc84af2c`
**Branch**: `master` (pushed; permalink base `https://github.com/miloszj7/VeloLog/blob/38ed371/`)
**Repository**: miloszj7/VeloLog

## Research Question

What does the codebase already establish that constrains adding trip edit and trip delete
(roadmap S-04, PRD FR-007/FR-008), and what is on the record about E-08 (`TripForm` accepts
a future-dated trip with no validation)?

## Summary

Five findings shape this slice.

1. **Delete is not a CRUD exercise — it is the slice that inherits a named data obligation.**
   S-03 explicitly deferred GPX orphan-file cleanup to S-04, in a plan handoff, in a review
   finding, and in a comment pinned inside a live test. Deleting a trip today cascades its
   `GpxTrack` rows and strands every `.gpx` file on the Railway Volume permanently. The
   mechanism to use is already implemented and review-hardened in `gpx/views.py:28-47`.

2. **Authorization has exactly one idiom and it is documented in-code as such**: an
   owner-scoped `get_queryset()` yielding **404, not 403**. It is used by all five existing
   owner-scoped views. An `UpdateView`/`DeleteView` without it is an IDOR.

3. **E-08 has no prior product lean.** The entire record is one three-column table row,
   twice re-deferred. The plan must *make* the decision, not inherit it. Two inputs that
   are not in that row: `TIME_ZONE = "UTC"` makes a naive `date > today` check falsely
   reject a genuinely-today trip for a UTC+2 rider between local 00:00 and 02:00; and
   adding the rule to `TripForm` makes an existing future-dated trip **uneditable** — in
   the very slice that introduces editing.

4. **`trip_form.html` is create-hardcoded and is `UpdateView`'s silent default template.**
   Title, heading, submit label, and Cancel target are all literals for the create flow.

5. **The suite sits at 99.78% with `branch = true`.** `fail_under = 80` will never trip;
   any untested branch is nonetheless immediately visible. Two agent claims I inherited were
   wrong and are corrected below — both are exactly the class of error that S-02's review
   caught (`plan.md` asserting a stub subscript that raises at import).

## Detailed Findings

### A. What exists today in `trips/`

`Trip` (`trips/models.py:6-30`) — `name` (CharField 200), `date` (DateField), `description`
(TextField, `blank=True`), `owner` (FK to `AUTH_USER_MODEL`, `on_delete=CASCADE`,
`related_name="trips"`). `Meta.ordering = ["-date", "-id"]`. `get_absolute_url()` returns
`reverse("trips:detail", kwargs={"pk": self.pk})` (`trips/models.py:24-30`), added by S-03 so
"redirect targets have one place to resolve".

Three views, all CBVs (`trips/views.py`): `TripListView:33`, `TripCreateView:41`,
`TripDetailView:55`. Three routes (`trips/urls.py:8-10`), `app_name = "trips"`, mounted at
`/trips/`: `list` (`""`), `create` (`"new/"`), `detail` (`"<int:pk>/"`). A trip is addressed
by integer `pk`; there is no slug. By the existing verb-segment convention the new routes read
`<int:pk>/edit/` and `<int:pk>/delete/`.

`TripForm` (`trips/forms.py`, 22 lines, whole file) is a `ModelForm` over
`fields = ("name", "date", "description")` with one widget override,
`forms.DateInput(attrs={"type": "date"})` (`trips/forms.py:19-21`). **It has no `clean_*()`
method and no validators of any kind** — the only constraint on `date` is `DateField`'s parse
check. `owner` is deliberately absent from `fields`; it is assigned server-side in
`form_valid` (`trips/views.py:51`), a pattern S-02's plan flagged as propagating to S-04.

> Correction: a subagent cited `trips/forms.py:106-114` for `TripForm`. That is wrong — the
> file is 22 lines total. Verified by direct read.

### B. Authorization — one pattern, 404 not 403

Every owner-scoped view filters the queryset and lets the 404 fall out, rather than fetching
then checking. `TripDetailView.get_queryset`'s docstring is the canonical statement
(`trips/views.py:59-65`):

> Scoping here — rather than checking ownership after fetching — is what makes another user's
> trip 404 instead of 403, so a pk that exists is indistinguishable from one that does not.
> The owner-scoped queryset is the project's entire authorization story.

| View | Check | Anchor |
|---|---|---|
| `TripListView.get_queryset` | `Trip.objects.filter(owner=...)` | `trips/views.py:38` |
| `TripDetailView.get_queryset` | `Trip.objects.filter(owner=...)` | `trips/views.py:66` |
| `TripCreateView.form_valid` | `form.instance.owner = ...` | `trips/views.py:51` |
| `GpxUploadView.get_trip` | `get_object_or_404(Trip.objects.filter(owner=...))` | `gpx/views.py:85-87` |
| `GpxDownloadView.get` | `get_object_or_404(GpxTrack.objects.filter(trip__owner=...))` | `gpx/views.py:160-162` |

`grep 403 tests/` returns **zero hits**. Two ordering subtleties carried forward from S-03's
review:

- **Resolve the object before touching the form on POST.** `GpxUploadView.post` resolves the
  trip first (`gpx/views.py:68-76`) because doing it in `form_valid` would let an invalid
  submission against a foreign trip render a 200 and thereby confirm the trip exists. An edit
  view's invalid POST against another user's trip must 404, not re-render an error page.
- **Pair the 404 assertion with a leak/persistence assertion.** A status-code-only cross-user
  test was itself a review finding (`impl-review-phase-4.md:200-216`). S-02 also hit a
  vacuous-needle trap: `assert "Other's Trip" not in body` passed *while the trip leaked*,
  because Django escapes the apostrophe. The fixture was renamed `"Other Rider Trip"`
  (`tests/trips/test_trip_list.py:23`). Pick needles with no escapable characters.

The PRD guardrail names the verbs this slice adds: *"One authenticated user can never read,
**modify, or delete** another user's private trips under any circumstance"* (`prd.md:43`,
restated `prd.md:106`). S-02 and S-03 only ever exercised *read*.

### C. Delete — the cascade is solved, the files are not

`GpxTrack` is the **only** model pointing at `Trip` (`gpx/models.py:28`,
`on_delete=CASCADE`, `related_name="tracks"`). It is a **ForeignKey, not OneToOne** — v1's
one-track-per-trip rule is enforced only in the upload view (`gpx/views.py:134-141`), not by a
constraint, so a delete path must assume N tracks.

Row cascade already works and is proven (`tests/gpx/test_gpx_track_model.py:18-26`). Files do
not. Verified absent across the whole repo: no `post_delete`/`pre_delete` receiver, no
`signals.py`, no `AppConfig.ready()`, no overridden `delete()`, no `django-cleanup`, no custom
storage. Files land at `MEDIA_ROOT/gpx/<owner_id>/<trip_id>/<32-hex>.gpx`
(`gpx/models.py:8-17`) — conveniently already bucketed per trip.

This is a **named handoff to this slice**, recorded three times:

- `context/archive/2026-08-23-upload-gpx-and-view-map/plan.md:1233-1239` — *"S-04 must pair
  its delete with file cleanup — whichever mechanism it chooses, on the same
  `transaction.on_commit` footing as the replace path… The Volume is single-region and 3,000
  IOPS; an unbounded orphan set is not a cost that stays invisible forever."*
- Same plan, `:466-472` — the cascade test is rows-only by design: *"Do not 'fix' it by
  asserting the file is gone; that test would fail correctly."*
- Pinned in the live test as a comment (`tests/gpx/test_gpx_track_model.py:24-25`):
  *"orphan cleanup is handed to S-04."* **That comment goes stale the moment this slice
  lands** — `lessons.md` #5 applies.

**The mechanism to copy** is `discard_superseded_file` (`gpx/views.py:28-47`) invoked via
`transaction.on_commit(partial(...))` (`gpx/views.py:141`). Three review findings hardened it,
and a delete path re-encounters all three:

1. **Read-set must equal delete-set, from one snapshot** (`impl-review-phase-4.md:98-114`) —
   read inside `atomic()`, delete by explicit `pk__in`, never `exclude(pk=...)`.
2. **A cleanup failure must not fail an already-committed operation**
   (`impl-review-phase-4.md:150-164`) — `try/except OSError`, log, return.
3. **Delete on commit, not inside `atomic()`** (`plan.md:167-179`) — storage deletes do not
   participate in the transaction; a rollback would resurrect a row pointing at a deleted
   file, producing exactly the silent-failure state `prd.md:91` forbids.

**Both models are admin-registered** (`trips/admin.py:13`, `gpx/admin.py:13`), so the admin's
`delete_selected` bulk action is a live path — and `QuerySet.delete()` does **not** call
`Model.delete()`. An overridden `delete()` would miss it; a `post_delete` signal would not.
This is a real fork for the plan, not a detail.

**Test mechanics**: `on_commit` callbacks do not fire under pytest-django's default
transactional wrapping. Use `django_capture_on_commit_callbacks`, per the existing exemplars
`tests/gpx/test_gpx_upload.py::test_a_second_upload_replaces_the_first_and_removes_its_file`
and `::test_a_cleanup_failure_does_not_fail_an_upload_that_already_committed`.

**"Data never lost" is not in tension with FR-008.** S-03 read the guardrail as durability
against accidental/infrastructural loss, never as a bar on user-initiated deletion, and
`prd.md:75` records *"No counter-argument; edit/delete is table stakes for personal data."*
What the guardrail *does* forbid is a **silent partial delete** — row gone with file stranded,
or file gone with row rolled back. No soft-delete, undo, or trash-bin was ever proposed.

### D. E-08 — the future-date decision

**The entire original record is one table row**
(`context/archive/2026-08-23-create-and-list-trips/plan.md:462`):

> | `TripForm` accepts a future-dated trip with no validation (found during Phase 3 manual
> verification) | Decide product intent (block future dates? allow and label as "planned"?)
> then add `clean_date()` if blocking is the answer | When trip-date semantics are next
> revisited, e.g. alongside S-03/S-04 |

No repro steps, no severity, no date used. Transcribed to `roadmap.md:159` (status `open`),
cited once as evidence that manual testing genuinely ran
(`create-and-list-trips/reviews/impl-review.md:36-38`), and deliberately re-deferred by S-03
(`upload-gpx-and-view-map/plan-brief.md:121-122`). **Nothing in the PRD, roadmap, shape-notes,
or any plan expresses a preference.** The fix was explicitly gated on a product decision that
was never made.

**PRD evidence for blocking** (none of it decisive, none of it cited in the row):

- Persona: *"He reaches for VeloLog after completing a tour, when he wants to record and
  relive it before the details fade"* (`prd.md:29`) — retrospective by construction.
- Vision: *"A personal diary of multi-day tours"* (`prd.md:23`).
- Non-Goals: *"VeloLog is a log and viewer, not a planner or editor. Users upload finished
  tracks"* (`prd.md:112`). A future-dated trip is a plan.

**PRD evidence against a hard block:**

- FR-003 specifies only *"a name, date, and description"* (`prd.md:66`) — no constraint.
- Business Logic: *"A trip with no uploaded file is a valid empty draft"* (`prd.md:97`) — the
  model already tolerates a trip that exists before its data does.

**Two inputs absent from the record, surfaced here:**

1. **Timezone.** `TIME_ZONE = "UTC"` with `USE_TZ = True` (`velo_log/settings.py:130,134`).
   A naive `value > timezone.localdate()` compares against the **UTC** date. A rider in
   UTC+2 entering today's date between local 00:00 and 02:00 is entering *tomorrow* in UTC and
   gets falsely rejected — a ~2h window every day. Mitigations: compare with a one-day
   tolerance, or don't block.
2. **Blocking makes existing future-dated trips uneditable.** `TripForm` is shared by create
   and edit. If `clean_date()` rejects future dates, a rider with an already-saved
   future-dated trip cannot fix its *name* without also changing its date — a trap landing
   precisely in the slice that introduces editing. Mitigation if blocking is chosen: skip the
   rule when the date is unchanged (`"date" not in self.changed_data`). Note `TripAdmin`
   (`trips/admin.py:13-22`) declares no `form =`, so admin keeps a default `ModelForm` and
   remains an escape hatch — consistent with its *"Admin read/repair path"* docstring.

**One constraint on *how*.** `TripForm` has no `clean_*()` today, and that absence was a
reviewed decision: plan-review F3 killed a planned `clean_name()` as an inert, permanently
uncoverable branch in a newly coverage-gated package
(`create-and-list-trips/reviews/plan-review.md:52-64`). Its blind-spot line names this slice:
*"If S-04's edit form ever needs a different name rule, the hook has to be reintroduced."*
F3's objection does **not** transfer — a future-date branch is reachable and testable — but it
sets the bar: the branch must be exercised in both directions, and `branch = true` means a
half-covered `clean_date()` shows as a gap.

`TripForm.date` currently has **zero** negative-path coverage: no invalid-date test, no
blank-date test, no widget-rendering test. Existing tests post `"2026-06-01"` / `"2026-07-01"`
(`tests/trips/test_trip_creation.py:15,28,40,57,71,83`), both **past** relative to today
(2026-08-26), so adding the rule breaks no existing test.

### E. Templates — the create/edit collision

`trip_form.html` (20 lines) is the exact markup to mirror, and it is create-hardcoded:
`{% block title %}New trip — VeloLog{% endblock %}` (`:3`), `<h1>New trip</h1>` (`:6`),
`<button type="submit">Save trip</button>` (`:17`), and Cancel pointing at `trips:list`
(`:19`). **Django's `UpdateView` defaults to this same `trips/trip_form.html`** and will bind
to it silently. S-02's review already caught the general shape of this trap as CRITICAL:
*"a valid POST redirects without rendering, so 'a valid POST creates a trip and redirects'
passes green while `GET /trips/new/` and every invalid-POST re-render 500"*
(`create-and-list-trips/reviews/plan-review.md:48`). `UpdateView` and `DeleteView` have the
same GET-render/POST-redirect asymmetry.

Form-rendering conventions, all present in that file and non-negotiable: `{% csrf_token %}`
directly after `<form>` (`:8`), `{{ form.non_field_errors }}` (`:9`, `lessons.md` #2),
per-field `<p>` loop with `{{ field.errors }}` (`:10-16`), no `action` attribute.

**The Cancel affordance's binding convention is `<p><a>…</a></p>` *outside* the `<form>`** —
the `discard-new-trip-form` plan-brief put it inside, and review F1 moved it out to match
`trip_detail.html:13` and `trip_list.html:7`
(`discard-new-trip-form/reviews/impl-review.md:23-36`). Its exact string is asserted verbatim
by `tests/trips/test_trip_creation.py:88-93`, so reusing the template for edit must keep that
assertion true.

That change **explicitly excluded** an edit form from scope, twice
(`discard-new-trip-form/plan.md:26`, `plan-brief.md:35`) — so no inherited decision says an
edit form gets a Cancel link. But its rationale ("nothing is persisted until POST, so
navigating away already is the discard") applies identically, and the *absence* of the
affordance was framed as the defect. Its no-confirmation-dialog decision was justified on that
same "nothing is persisted" ground and therefore **does not transfer to delete**.

**There is no confirmation-page pattern anywhere in the repo.** `trip_confirm_delete.html`
would be the project's first. `templates/base.html` renders messages without `message.tags`
(`:29-35`), so an error-level message is visually identical to a success one today.
`static/css/style.css` is 21 lines containing one `#map` rule, and its header records a
standing "no CSS beyond what the map requires" decision — new UI should stay unstyled.

There are currently **no edit or delete controls** on either `trip_detail.html` or
`trip_list.html`. Note the cross-app trap documented at `trips/views.py:69-76`: any new context
key added to `TripDetailView.get_context_data` must also be added to
`GpxUploadView.get_context_data` (`gpx/views.py:89-101`), which re-renders the same template.

### F. Testing conventions

Layout is by app (`tests/trips/`, `tests/gpx/`, `tests/accounts/`) with project-level tests
flat; no `unit/`/`integration/` split. Naming is `test_<feature>_<surface>.py`, one file per
user action — so `tests/trips/test_trip_edit.py` and `tests/trips/test_trip_delete.py`.
`tests/trips/` has **no `conftest.py`**; trips are built inline. Pure pytest function style
(zero test classes), `@pytest.mark.django_db` applied per-test, every signature fully
annotated (`mypy --strict` covers the suite).

Fixtures (`tests/conftest.py`): `rider:86`, `other_rider:91`, `auth_client:96`,
`make_gpx_track:102`, plus four autouse fixtures (`_disable_ssl_redirect:26`,
`_media_root_in_tmp_path:36`, `_plain_staticfiles_storage:47`, `_clear_cache:75`).

The fixed test matrix every owner-scoped surface reproduces: owner → 200; other user → **404
plus a no-leak/persistence assertion**; anonymous → 302 to login with `?next=`; wrong verb →
405. Success messages are asserted on the *next* page's body
(`tests/trips/test_trip_list.py:49-58`). Forms are exercised **only through views** — no test
in the suite instantiates a form class — via `response.context["form"].errors["<field>"]`.

Assert rendered dates with `django.utils.formats.date_format`, never a literal: hardcoding
`"June 1, 2026"` was review finding F3 (`impl-review-phase-3.md:83-97`). The `type="date"`
widget takes ISO input while the template renders locale-formatted — don't mix the two.

Coverage: `source = ["accounts", "trips", "gpx", "velo_log"]`, `branch = true`,
`fail_under = 80` (`pyproject.toml:61-71`). Current: **120 passed, 99.78%**; the only uncovered
line in the repo is `trips/models.py:22`. There is no `addopts`, so `--cov` must be passed
explicitly. `tests/test_static_references.py` only validates `{% static %}` names listed in its
hand-maintained tuple (`:45-53`) and only renders the *detail* page under the production
manifest — a typo in a new template's `{% static %}` passes the whole suite locally and 500s
the site (`impl-review-phase-5.md:186-195`). New templates that add no `{% static %}` need no
change there.

### G. Typing, logging, gates

**Typing — two corrections to inherited claims.** The project's idiom is a `TYPE_CHECKING`
base alias (`trips/views.py:21-30`) because django-stubs generics are not subscriptable at
runtime. Verified against the installed stubs
(`.venv/Lib/site-packages/django-stubs/views/generic/edit.pyi`):

- `UpdateView(SingleObjectTemplateResponseMixin, BaseUpdateView[_M, _ModelFormT])` — **two**
  params → `UpdateView[Trip, TripForm]`.
- `DeleteView(..., BaseDeleteView[_M, _FormT], Generic[_M, _FormT])` — **two** params, not
  one → `DeleteView[Trip, Form]` (`django.forms.Form`, `BaseDeleteView.form_class`'s default).
  A subagent reported this as taking one param; that is wrong, and it is precisely the error
  class S-02's review caught in a plan (*"Coding the plan literally would have raised at
  import time"* — `create-and-list-trips/reviews/impl-review.md:88-114`).
- `SuccessMessageMixin(Generic[_F])` is parameterized by the **form**, so the existing
  `_SuccessMessageMixinBase = SuccessMessageMixin[TripForm]` (`trips/views.py:25`) is reusable
  for the update view but **not** for a delete view, which needs its own
  `SuccessMessageMixin[Form]` alias.

**`SuccessMessageMixin` does work with `DeleteView` in Django 6.** Verified from installed
source: `BaseDeleteView(DeletionMixin, FormMixin, BaseDetailView)` with `form_class = Form`,
whose `post()` routes through `form_valid()`. A subagent claimed the opposite. Caveat:
`get_success_message(cleaned_data)` receives `{}` (the empty `Form`), so `%(name)s`
interpolation would raise — a static string is safe, or override `get_success_message` and read
`self.object`, which survives in memory after delete (with `pk` set to `None`).

**Logging: an INFO audit line for a deletion will not appear in production.**
`velo_log/settings.py:225-256` — the root logger's level is `"INFO" if DEBUG else "WARNING"`,
and `trips.views` is not a descendant of `velo_log`, so it reaches stdout only via root. The
formatter is `"{asctime} {levelname} {name} {message} media_root={media_root}"`, so
`extra={"trip_id": ...}` **will not render**; widening it was recorded as "a separate, later
decision" (`logging-config/plan.md:85-90`). The existing cleanup helper uses
`logger.exception` (ERROR), which does clear the threshold — so copying that pattern is safe.
Destructive-action/audit logging was never discussed anywhere in the archive.

**Gates** (`.github/workflows/deploy.yml`): vendored-asset integrity → ruff → black → isort →
mypy → `manage.py check` → `makemigrations --check --dry-run` → `collectstatic` → `pytest
--cov`. CI-equivalence command is exact and mandatory (`AGENTS.md`):
`SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`.
E-02 remains open — `gates` is not a required check, so a red run does not mechanically block
a merge (`roadmap.md:153`). No migration is expected in this slice (no model change), but
`lessons.md` #9 still applies if one appears.

## Code References

- `trips/models.py:6-30` — `Trip`; `:24-30` `get_absolute_url`, the canonical redirect target
- `trips/forms.py:13-21` — `TripForm`; no `clean_*()` exists (E-08's subject)
- `trips/views.py:21-30` — the `TYPE_CHECKING` base-alias idiom to extend
- `trips/views.py:41-52` — `TripCreateView`, the mixin order and server-side owner assignment
- `trips/views.py:59-66` — the authorization docstring + owner-scoped queryset
- `trips/urls.py:8-10` — route/verb conventions (`new/`, `<int:pk>/`)
- `trips/templates/trips/trip_form.html:1-20` — form markup + create-hardcoded strings
- `trips/admin.py:13-22` — default `ModelForm`; `view_on_site = False`
- `gpx/models.py:8-17` — `gpx_upload_path`, per-trip bucketing
- `gpx/models.py:28` — the only FK to `Trip`, `on_delete=CASCADE`
- `gpx/views.py:28-47` — `discard_superseded_file`, the cleanup helper to reuse
- `gpx/views.py:106-142` — `atomic()` + `on_commit` ordering to mirror
- `gpx/views.py:68-87` — resolve-object-before-form-on-POST
- `velo_log/settings.py:130,134` — `TIME_ZONE = "UTC"`, `USE_TZ = True` (E-08 input)
- `velo_log/settings.py:225-256` — `LOGGING`; root at WARNING when `DEBUG=False`
- `tests/conftest.py:86-120` — `rider`, `other_rider`, `auth_client`, `make_gpx_track`
- `tests/trips/test_trip_detail.py:32-41` — the cross-user 404 idiom to copy
- `tests/trips/test_trip_creation.py:48-64` — mass-assignment test, closest edit analogue
- `tests/gpx/test_gpx_track_model.py:18-26` — cascade test + the S-04 deferral comment

## Architecture Insights

- **Authorization is a queryset property, not a permission layer.** There is no object-permission
  mixin and S-03 explicitly declined to introduce one. Consistency matters more than the
  mechanism here: five views, one shape, documented in-code.
- **The file/row pair is the project's only genuine consistency problem**, and it has one
  answer: rows inside `atomic()`, files on `on_commit`, failures logged not raised. Delete is
  the second place that answer is needed; upload was the first.
- **`Model.delete()` vs `QuerySet.delete()` is a live fork** because both models are
  admin-registered. A view-level cleanup matches the existing idiom; a `post_delete` signal is
  the only hook that also covers admin bulk delete and any future queryset delete. The plan
  should pick deliberately and say why.
- **Template defaults are a silent-coupling hazard in this codebase.** `UpdateView` will grab
  `trip_form.html` without being asked, and `GpxUploadView` already re-renders
  `trip_detail.html` from another app. Both are documented traps that have already produced
  findings.
- **The suite's effective ceiling is ~100%, not 80%.** `fail_under` is not the real gate;
  the per-file column is.

## Historical Context (from prior changes)

- `context/archive/2026-08-23-upload-gpx-and-view-map/plan.md:1233-1239` — the orphan-file
  handoff to S-04, with the prescribed mechanism
- `.../plan.md:466-472` — the cascade test is rows-only by design; do not "fix" it
- `.../plan.md:167-179` — save-then-delete and delete-on-commit ordering rationale
- `.../reviews/impl-review-phase-4.md:98-164` — F2 snapshot mismatch, F4 row-exists-file-gone,
  F5 cleanup-failure-must-not-500
- `context/archive/2026-08-23-create-and-list-trips/plan.md:462` — E-08's origin (one row)
- `.../plan.md:69` — owner must never be client-supplied; "propagates to S-03 and S-04"
- `.../reviews/plan-review.md:52-64` — F3 killed `clean_name()`; blind spot names S-04
- `.../reviews/impl-review.md:88-114` — F2, django-stubs subscript arity errors in a plan
- `context/archive/2026-08-26-discard-new-trip-form/reviews/impl-review.md:23-36` — F1,
  Cancel is `<p><a>…</a></p>` outside the `<form>`
- `.../plan-brief.md:19-25,53` — the accepted Cancel design and the no-confirmation rationale
  that does not transfer to delete
- `context/foundation/lessons.md` — #1 vacuous tests, #2 `non_field_errors`, #3 coverage vs
  scenarios, #5 update docs the slice invalidates, #9 migrations

## Related Research

- `context/archive/2026-08-23-upload-gpx-and-view-map/research.md:343-348` — the ownership
  pattern as S-03 recorded it; `:502-505` — how "data never lost" was read
- `context/archive/2026-08-23-create-and-list-trips/research.md:206-214` — the house plan
  skeleton and phase-ordering rationale this slice's plan should mirror

## Open Questions

**For the user (product decisions, not derivable from the repo):**

1. **E-08: block future dates, or allow and label?** No prior lean exists. Blocking is
   well-supported by the PRD's diary/log framing; if chosen, decide whether "today" is valid
   (it should be), how to handle the UTC boundary, and whether the rule applies when editing a
   trip whose date is unchanged.
2. **Is a delete confirmation step wanted?** Django's `DeleteView` gives one free on GET. The
   repo has no confirmation precedent, and the one recorded no-confirmation decision was
   explicitly scoped to a non-destructive action.

**For `/10x-plan` (technical, decidable from the evidence above):**

3. Orphan cleanup via `post_delete` signal (covers admin bulk delete) or view-level
   `on_commit` (matches the existing idiom)? Evidence leans signal + `on_commit`.
4. Does the edit form reuse `trip_form.html` with conditionals, or get its own template?
   Where does its Cancel link point — `trips:list` or `Trip.get_absolute_url()`?
5. Where do edit/delete entry points live — trip detail, trip list rows, or both?
6. Should a deletion emit an audit log line at all, given root-logger WARNING in production?
