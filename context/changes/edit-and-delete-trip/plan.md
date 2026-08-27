# Edit and Delete a Trip (S-04) + Future-Date Validation (E-08) Implementation Plan

## Overview

Ship roadmap slice **S-04**: a rider can edit a trip's name, date and description
(FR-007), or delete the trip entirely (FR-008). Bundled in: **E-08**, the missing
future-date validation on `TripForm`, whose product decision the frame brief settled.

Delete is not the CRUD half of this slice. It is the slice that inherits a named data
obligation — S-03 deferred GPX orphan-file cleanup here three times, and today deleting a
trip cascades its `GpxTrack` rows while stranding every `.gpx` file on the Railway Volume
permanently. That obligation is discharged in its own phase, ahead of the delete view, so
delete inherits working cleanup rather than inventing it.

## Current State Analysis

**What exists.** `Trip` (`trips/models.py:6-30`) with `name`, `date`, `description`,
`owner`; `Meta.ordering = ["-date", "-id"]`; `get_absolute_url()` at `:24-30`. Three CBVs
(`TripListView:33`, `TripCreateView:41`, `TripDetailView:55`) and three routes
(`trips/urls.py:8-10`) under `app_name = "trips"`. `TripForm` (`trips/forms.py`, 22 lines
total) is a `ModelForm` over `("name", "date", "description")` with one widget override
and **no `clean_*()` method of any kind**.

**What is missing.** No edit view, no delete view, no edit/delete controls on either
template, no confirmation-page pattern anywhere in the repo, and no GPX file cleanup on
any deletion path.

**Key constraints discovered.**

- **Authorization has exactly one idiom, documented in-code**: an owner-scoped
  `get_queryset()` yielding **404, not 403** (`trips/views.py:59-66`). All five
  owner-scoped views use it; `grep 403 tests/` returns zero hits. `prd.md:43` names the
  verbs this slice adds — *"can never read, **modify, or delete** another user's private
  trips"* — and S-02/S-03 only ever exercised *read*.
- **`trip_form.html` is create-hardcoded and is `UpdateView`'s silent default template.**
  Title (`:3`), `<h1>` (`:6`), submit label (`:17`) and Cancel target (`:19`) are all
  literals for the create flow. Django's `UpdateView` resolves to this same
  `trips/trip_form.html` without being asked.
- **The Cancel affordance's exact markup is asserted verbatim** by
  `tests/trips/test_trip_creation.py:88-93`, and review F1 established it lives as
  `<p><a>…</a></p>` *outside* the `<form>`
  (`discard-new-trip-form/reviews/impl-review.md:23-36`).
- **`GpxTrack` is the only model pointing at `Trip`** (`gpx/models.py:28`, CASCADE), and
  it is a **ForeignKey, not OneToOne** — one-track-per-trip is enforced only in the upload
  view (`gpx/views.py:134-141`), so any delete path must assume N tracks.
- **Both models are admin-registered** (`trips/admin.py:13`, `gpx/admin.py:13`), so the
  admin's `delete_selected` bulk action is a live deletion path. `QuerySet.delete()` does
  **not** call `Model.delete()`.
- **`TIME_ZONE = "UTC"` with `USE_TZ = True`** (`velo_log/settings.py:130,134`) against a
  browser-local `type="date"` widget.
- **The suite sits at 99.78% with `branch = true`** and `fail_under = 80`
  (`pyproject.toml:61-71`). `fail_under` will never trip; the per-file column is the real
  gate, and a half-covered `clean_date()` shows as a branch gap.

## Desired End State

A rider on a trip's detail page sees **Edit** and **Delete** alongside the trip's fields.
Edit opens the same form they created the trip with, retitled and pre-filled, and saving
returns them to the trip with a confirmation message. Delete asks first, on its own page,
naming the trip; confirming removes the trip, its track rows, **and the track files from
the Volume**, and returns them to their trip list. Another rider's trip 404s on every one
of these routes, for every verb. A trip dated far in the future is rejected at the form
with a message, and the date field now says what it means.

Verify by: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run
pytest --cov` green with no coverage regression, plus the per-phase manual steps below.

### Key Discoveries

- **The `post_delete` receiver is what makes the cascade cleanable at all.**
  `Collector.can_fast_delete()` returns `False` when a model has `pre_delete`/`post_delete`
  listeners (`django/db/models/deletion.py:186-206`, checked against the installed
  source). With no receiver, a `Trip.delete()` cascade fast-deletes `GpxTrack` in one SQL
  statement and **never materializes the rows** — there is no instance to read a file
  path from. Registering the receiver is the mechanism, not just the hook.
- **The signal subsumes review finding F2.** `impl-review-phase-4.md:98-114` demanded the
  read-set equal the delete-set from a single snapshot, because the upload path computed
  the cleanup set separately from the delete. `post_delete` fires once per row **actually
  deleted**, so the two sets are the same set by construction. This is why the explicit
  `on_commit` call comes out of `GpxUploadView.form_valid` in Phase 2 rather than
  coexisting with the receiver.
- **`BaseDeleteView` resolves the object before the form**, in `post()` itself
  (`django/views/generic/edit.py`, `BaseDeleteView.post`) — `self.object =
  self.get_object()` precedes `get_form()`. So an owner-scoped `get_queryset()` gives the
  404-on-POST-against-a-foreign-trip behaviour for free; the explicit
  resolve-before-form dance `GpxUploadView.post:68-76` needed does **not** have to be
  repeated.
- **django-stubs arity, verified by direct read** of
  `.venv/Lib/site-packages/django-stubs/views/generic/edit.pyi:69,82`:
  `UpdateView[Trip, TripForm]` (two params) and `DeleteView[Trip, Form]` (**two** params,
  not one). `SuccessMessageMixin(Generic[_F])` is parameterized by the **form**
  (`contrib/messages/views.pyi:10`), so the existing `_SuccessMessageMixinBase =
  SuccessMessageMixin[TripForm]` (`trips/views.py:25`) is reusable for update but **not**
  for delete, which needs its own `SuccessMessageMixin[Form]` alias. Coding the wrong
  arity raises at import time — the exact error class
  `create-and-list-trips/reviews/impl-review.md:88-114` caught in a plan.
- **`SuccessMessageMixin` does work with `DeleteView` in Django 6.** `BaseDeleteView`
  sets `form_class = Form` and its `post()` routes through `form_valid()`. But
  `get_success_message(cleaned_data)` receives `{}` from the empty `Form`, so any
  `%(name)s` interpolation raises — the message must be a static string.
- **`+1 day` is provably the exact tolerance.** No real timezone is more than 14h ahead
  of UTC, so a rider's local date can never exceed the UTC date by more than one day.
- **A future-date rule breaks no existing test.** Every existing post uses `"2026-06-01"`
  or `"2026-07-01"` (`tests/trips/test_trip_creation.py:15,28,40,57,71,83`), both past.
  `TripForm.date` has **zero** negative-path coverage today.
- **`tests/trips/` has no `conftest.py`** — trips are built inline there. `tests/gpx/`
  has its own (`trip:35`, `gpx_bytes:21`, `make_stored_track:40`).

## What We're NOT Doing

- **Splitting `Trip.date` into start/end dates.** A legitimate product insight raised by
  the owner, but it inverts the exact basis of S-04's Low risk rating (*"no new domain
  concepts"*, `roadmap.md:98`), needs a PRD amendment (FR-003, FR-007 and the Primary
  Success Criterion all say "a date", singular), touches ~31 test sites across 9 files
  plus an unattended production migration, and lands 15 days before the `2026-09-10`
  deadline. Recorded as a new Engineering Backlog row in Phase 5; its natural trigger is
  FR-011, where multi-day chronology actually lives per `prd.md:99`.
- **Soft delete, undo, or a trash bin.** Never proposed anywhere in the archive.
  `prd.md:75` records edit/delete as table stakes with no counter-argument.
- **An audit log line for deletion.** An INFO line is invisible in production (root sits
  at WARNING when `DEBUG=False`, and `trips.views` is not a `velo_log` descendant), and
  the formatter ignores `extra={}` — it would log nothing useful while appearing to.
  Widening the formatter is a recorded separate decision (`logging-config/plan.md:85-90`).
- **Edit/delete controls on `trip_list.html`.** Detail page only.
- **Any CSS.** `static/css/style.css` is 21 lines with a standing "no CSS beyond what the
  map requires" decision. New UI ships unstyled.
- **`message.tags` rendering in `base.html`.** An error-level message is visually
  identical to a success one today (`base.html:29-35`); out of scope.
- **A permission mixin or object-permission layer.** S-03 explicitly declined one;
  consistency with the queryset idiom matters more than the mechanism.
- **Migrations.** No model field changes. `help_text` **is** a migration-generating
  change when applied to the model — see Phase 4's note.

## Implementation Approach

Five phases, ordered so each leaves the tree committable and so the deadline's cut line
falls after both must-have FRs.

Phase 1 delivers edit — non-destructive, independent, and the smallest surface. Phase 2
discharges the inherited file-cleanup obligation as a pure refactor with no new
user-facing verb, isolating a change to a path three review findings hardened into its own
reviewable commit. Phase 3 delivers delete on top of that working cleanup. Phase 4 closes
E-08 and is droppable. Phase 5 is bookkeeping, committed last so no decision record
predates the fix it describes (`lessons.md` #8).

Every new owner-scoped surface reproduces the fixed test matrix: owner → 200; other user
→ **404 plus a no-leak or persistence assertion**; anonymous → 302 to login with `?next=`;
wrong verb → 405.

The 405 leg is **not** free from the framework — both new views must narrow
`http_method_names` to earn it. See *Critical Implementation Details → Verb narrowing*
below; without it, a raw HTTP `DELETE` on the delete route destroys the trip and its GPX
file with no confirmation page at all.

## Critical Implementation Details

**Timing & lifecycle.** `post_delete` fires **inside** the collector's transaction, so the
receiver must schedule `transaction.on_commit(...)` and must not touch storage inline. A
storage delete performed inside `atomic()` is already gone if the block later raises,
which rolls the row back into existence pointing at a missing file — precisely the silent
partial-delete state `prd.md:91` forbids. Scheduling on commit also means a rolled-back
delete never fires the callback, so the file correctly survives.

**Test mechanics.** `on_commit` callbacks do not fire under pytest-django's default
transactional wrapping. Every test asserting a file was removed must wrap the request in
`django_capture_on_commit_callbacks(execute=True)`, per the exemplars
`tests/gpx/test_gpx_upload.py:272` and `:309`. Without it the assertion passes while
proving nothing.

**Verb narrowing.** `BaseDeleteView` still inherits `DeletionMixin.delete()`
(`django/views/generic/edit.py:215-232`, `:240`), and `View.dispatch` resolves its handler
with `getattr(self, request.method.lower(), ...)` (`django/views/generic/base.py:139-142`),
while `_allowed_methods` lists any method the class merely has an attribute for
(`base.py:181-182`). So a raw HTTP `DELETE` at `/trips/<pk>/delete/` runs `get_object()`
→ `get_success_url()` → `self.object.delete()` → 302 — bypassing the confirmation page and
the empty `Form` entirely, and, via Phase 2's receiver, taking the GPX file with it. The
Django test client does not enforce CSRF by default, so `client.delete(url)` succeeds.
`UpdateView` has the milder half of the same problem: `ProcessFormView.put` calls
`self.post(*args, **kwargs)` (`edit.py:155-157`) and `ModelFormMixin.get_form_kwargs`
binds `request.POST` — empty on a PUT — so PUT 200-re-renders with field errors rather
than returning 405.

Both new views therefore set `http_method_names = ["get", "post"]`, each with a comment
naming what it closes. This is already the repo's idiom, not a new pattern:
`GpxUploadView.http_method_names = ["post"]` (`gpx/views.py:62-64`), asserted at
`tests/gpx/test_gpx_upload.py:420` — the suite's only existing 405.

**Cross-app context coupling.** Any new context key added to
`TripDetailView.get_context_data` must also be added to `GpxUploadView.get_context_data`
(`gpx/views.py:89-101`), which re-renders the same template — the trap documented at
`trips/views.py:69-76`. This plan adds no new context key to the detail page (the Edit and
Delete links resolve from `trip.pk`, already present), so no `gpx/views.py` context change
is required. Stated because the absence is a deliberate check, not an oversight.

**Needle selection in leak assertions.** S-02 hit a vacuous-needle trap: `assert "Other's
Trip" not in body` passed *while the trip leaked*, because Django escapes the apostrophe.
The fixture was renamed `"Other Rider Trip"` (`tests/trips/test_trip_list.py:23`). Pick
needles with no escapable characters.

**Rendered-date assertions.** Use `django.utils.formats.date_format`, never a literal —
hardcoding `"June 1, 2026"` was review finding F3 (`impl-review-phase-3.md:83-97`). The
`type="date"` widget takes ISO input while the template renders locale-formatted; do not
mix the two.

---

## Phase 1: Edit a Trip (FR-007)

### Overview

Add `TripUpdateView`, its route, the template conditionals that stop the edit page calling
itself "New trip", and an Edit link on the detail page.

### Changes Required

#### 1. The update view

**File**: `trips/views.py`

**Intent**: Add `TripUpdateView` so a rider can change their own trip's name, date and
description. Reuse the existing `_SuccessMessageMixinBase` alias — it is parameterized by
`TripForm`, which is this view's form too.

**Contract**: `class TripUpdateView(LoginRequiredMixin, _SuccessMessageMixinBase,
_TripUpdateViewBase)` with `form_class = TripForm`, an explicit `template_name =
"trips/trip_form.html"`, `success_message`, `http_method_names = ["get", "post"]`, and an
owner-scoped `get_queryset() -> QuerySet[Trip]` returning `Trip.objects.filter(owner=cast(User, self.request.user))` —
the same body and the same reason as `TripDetailView.get_queryset:58-66`. No
`success_url`: `ModelFormMixin.get_success_url` falls through to
`Trip.get_absolute_url()`, which is why S-03 added it. Add
`_TripUpdateViewBase = UpdateView[Trip, TripForm]` to the `TYPE_CHECKING` block at
`:21-30` and `UpdateView` to the `django.views.generic` import at `:9`.

The `template_name` is set explicitly even though it is also `UpdateView`'s silent
default. Naming it is what turns a documented trap into a decision a reader can see.

`http_method_names` is what makes this surface's 405 leg true. Left at the default, a
`PUT` re-enters `post()` against an empty `request.POST` and returns a 200 re-render with
field errors — not a 405. Carry a comment saying so; the mechanism is in *Critical
Implementation Details → Verb narrowing*.

#### 2. The route

**File**: `trips/urls.py`

**Intent**: Expose the edit view at the verb-segment path the existing routes imply.

**Contract**: `path("<int:pk>/edit/", views.TripUpdateView.as_view(), name="edit")`, after
the `detail` route.

#### 3. Template conditionals

**File**: `trips/templates/trips/trip_form.html`

**Intent**: Branch the four create-hardcoded strings on whether the form is bound to a
saved trip, so one template serves both flows and the form conventions stay in one place.

**Contract**: `{% if form.instance.pk %}` drives the `{% block title %}` (`:3`), the
`<h1>` (`:6`), the submit button label (`:17`), and the Cancel `href` (`:19`) — which
points at `form.instance.get_absolute_url` when editing and stays `{% url 'trips:list' %}`
when creating. The `<p><a>…</a></p>` wrapper stays outside the `<form>` per review F1, and
**the create branch's rendered markup must stay byte-identical** — the exact string
`<p><a href="/trips/">Cancel</a></p>` is asserted verbatim at
`tests/trips/test_trip_creation.py:88-93`. Leave `csrf_token`, `non_field_errors` and the
per-field `<p>` loop untouched.

#### 4. The detail-page entry point

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: Give the rider a way to reach the edit form from the page they are looking at.

**Contract**: An `<a>` to `{% url 'trips:edit' pk=trip.pk %}` in the trip's own block,
after the description at `:19` and before the `<h2>Route</h2>` heading. No new context key
— `trip.pk` is already available on both render paths.

#### 5. Tests

**File**: `tests/trips/test_trip_edit.py` (new)

**Intent**: Cover the fixed matrix for a new owner-scoped surface, plus the two things
specific to editing: that a GET pre-fills the form, and that the create flow's asserted
strings survived the template conditionals.

**Contract**: Pure pytest functions, `@pytest.mark.django_db` per test, fully annotated
(`mypy --strict` covers the suite), trips built inline (no `tests/trips/conftest.py`).
Cases: owner GET → 200 with the trip's current values in `response.context["form"].initial`
and the edit-specific heading in the body; owner POST → 302 to the trip's detail URL, with
the changed values reloaded from the database **and** the success message asserted on the
next page's body per `tests/trips/test_trip_list.py:49-58`; other user's pk GET **and**
POST → 404 each, paired with an assertion that the trip's fields are unchanged in the
database (status code alone was itself a review finding,
`impl-review-phase-4.md:200-216`); anonymous GET → 302 to `reverse('login')` with
`?next=`; a POST attempting to set `owner` → owner unchanged, mirroring the
mass-assignment test at `tests/trips/test_trip_creation.py:48-64`; an invalid POST (blank
`name`) → 200 re-render carrying `form.errors["name"]`; and an owner `PUT` → 405, which
holds only because of `http_method_names` and fails loudly the moment it is dropped.

**File**: `tests/trips/test_trip_creation.py`

**Intent**: Confirm the create flow still renders its own strings after the template gained
conditionals. The existing Cancel assertion at `:88-93` already does this — verify it
passes unchanged rather than editing it. Add nothing unless it fails.

### Success Criteria

#### Automated Verification

- `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` passes with no coverage regression
- `uv run ruff check .`, `uv run black --check .`, `uv run isort --check-only .` pass
- `uv run mypy .` passes — in particular the two-parameter `UpdateView[Trip, TripForm]` alias imports without raising
- `uv run python manage.py check` passes
- `uv run python manage.py makemigrations --check --dry-run` reports no missing migration
- `tests/trips/test_trip_creation.py:88-93` passes unchanged, proving the create branch's markup is byte-identical

#### Manual Verification

- The edit page is titled and headed for editing, not "New trip", and its submit button reads as a save-changes action
- Cancel on the edit page returns to the trip; Cancel on the new-trip page still returns to the trip list
- Editing a trip's name updates it on both the detail page and the trip list, and the success message appears
- The Edit link is present on the detail page and absent from the trip list

**Implementation Note**: After this phase and all automated verification passes, pause for
manual confirmation before proceeding.

---

## Phase 2: A `post_delete` Signal Owns GPX File Cleanup

### Overview

Move GPX file cleanup from an explicit call in the upload view to a `post_delete` receiver
on `GpxTrack`, so **every** deletion path — trip cascade, admin `delete_selected`, upload
replace, and any future `QuerySet.delete()` — removes its file. No new user-facing
behaviour; this discharges the obligation S-03 handed over
(`upload-gpx-and-view-map/plan.md:1233-1239`) so Phase 3 inherits working cleanup.

### Changes Required

#### 1. The receiver

**File**: `gpx/signals.py` (new)

**Intent**: On every `GpxTrack` row deletion, schedule its file for removal once the
transaction commits.

**Contract**: A `@receiver(post_delete, sender=GpxTrack)` function taking the standard
`(sender, instance, **kwargs)` signature, whose body is
`transaction.on_commit(partial(discard_track_file, instance))`. It must **not** delete
inline: `post_delete` fires inside the collector's transaction, and a storage delete there
is already gone if the block later raises — resurrecting a row that points at a missing
file. Scheduling on commit also means a rolled-back delete correctly leaves the file
alone.

Docstring must state the load-bearing mechanism: registering this receiver is what makes
`Collector.can_fast_delete()` return `False` for `GpxTrack`
(`django/db/models/deletion.py:186-206`), so a `Trip.delete()` cascade materializes the
rows instead of fast-deleting them in one SQL statement with no instance to read a path
from.

#### 2. Registration

**File**: `gpx/apps.py`

**Intent**: Import the receiver module at app-ready time so the connection actually
happens.

**Contract**: Add `def ready(self) -> None:` to `GpxConfig` importing `gpx.signals` for
its side effect, with a `# noqa: F401`-style suppression carrying an inline reason (the
project forbids unexplained suppressions). `INSTALLED_APPS` needs **no** change —
`"gpx"` (`velo_log/settings.py:61`) already resolves to `GpxConfig` through Django's
app-config autodiscovery.

#### 3. Repoint and rename the cleanup helper

**File**: `gpx/views.py`

**Intent**: `discard_superseded_file` is now called for deletions as well as replacements,
so its name and docstring are wrong. Rename it and correct the prose. Then remove the
explicit `on_commit` scheduling from `form_valid`, because the receiver now fires for
exactly the rows the queryset delete removes — leaving both would schedule two deletes of
the same file.

**Contract**: Rename `discard_superseded_file` → `discard_track_file` (`:28-47`), keeping
the `try/except OSError` + `logger.exception` body intact: a cleanup failure must never
fail an already-committed operation (`impl-review-phase-4.md:150-164`). Move it out of
`views.py` to sit beside the receiver — a signal module importing from a views module is
the wrong direction — and have `gpx/views.py` import it from there if it still needs it.

In `GpxUploadView.form_valid` (`:106-142`), drop the
`for old in superseded: transaction.on_commit(...)` loop and the `partial` import if it
becomes unused. **Keep** the snapshot and the explicit `pk__in` delete: `select_for_update`
plus an explicit pk set is what stops two concurrent uploads racing on which rows get
deleted at all, which is a correctness property of the *delete*, not of the cleanup. Update
the `form_valid` docstring: the read-set/delete-set argument at `:126-133` now explains the
row delete only, and the cleanup ordering rationale moves to the receiver's docstring.

Note in a comment why the receiver is strictly stronger than what it replaces: it fires
once per row **actually deleted**, so the cleanup set equals the delete set by
construction — which is what review finding F2 (`impl-review-phase-4.md:98-114`) had to
enforce by hand.

#### 4. Retire the stale deferral comment and prove the file is gone

**File**: `tests/gpx/test_gpx_track_model.py`

**Intent**: The comment at `:24-25` says orphan cleanup is handed to S-04. This slice **is**
S-04, so it goes stale the moment this lands (`lessons.md` #5). The archive's instruction
was *"Do not 'fix' it by asserting the file is gone; that test would fail correctly"*
(`upload-gpx-and-view-map/plan.md:466-472`) — that instruction expires here, and asserting
it is now exactly right.

**Contract**: Rewrite `test_deleting_a_trip_cascades_its_tracks` to use `make_stored_track`
(bytes actually on disk) rather than `make_gpx_track` (a name only), wrap `trip.delete()`
in `django_capture_on_commit_callbacks(execute=True)`, and assert both
`GpxTrack.objects.count() == 0` **and** `not default_storage.exists(<stored name>)`.
Replace the deferral comment with one naming the receiver as the mechanism.
`make_stored_track` already lives in `tests/gpx/conftest.py:40`, the same package — no
fixture move needed.

**File**: `tests/gpx/test_gpx_signals.py` (new)

**Intent**: Cover the paths the receiver exists for and that no view test reaches.

**Contract**: Cases, each wrapping the deleting call in
`django_capture_on_commit_callbacks(execute=True)`: a direct `GpxTrack.delete()` removes
the file; a `QuerySet.delete()` over two tracks removes **both** files (the FK is
many-per-trip, so N tracks is the real shape); a `Trip.delete()` cascade removes the file
of a track it never loaded explicitly — the fast-delete case; and a cleanup failure does
not raise, by monkeypatching `FileSystemStorage.delete` to raise `PermissionError` exactly
as `tests/gpx/test_gpx_upload.py:324-335` does, asserting the delete still succeeded and
the row is gone. Add one test proving a **rolled-back** delete leaves the file in place:
delete inside an `atomic()` block that then raises, and assert the file still exists — that
is the property that makes `on_commit` the right hook rather than an inline delete.

**File**: `tests/gpx/test_gpx_upload.py`

**Intent**: The two existing `on_commit` tests (`:272`, `:309`) must still pass now that
the scheduling moved into the receiver. Their behaviour is unchanged; verify rather than
edit. Update any reference to `discard_superseded_file` by name.

### Success Criteria

#### Automated Verification

- `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` passes with no coverage regression
- `tests/gpx/test_gpx_upload.py::test_a_second_upload_replaces_the_first_and_removes_its_file` and `::test_a_cleanup_failure_does_not_fail_an_upload_that_already_committed` pass with the scheduling moved
- `grep -rn "discard_superseded_file\|handed to S-04" gpx/ tests/` returns no hits
- `uv run ruff check .`, `uv run black --check .`, `uv run isort --check-only .`, `uv run mypy .` pass
- `uv run python manage.py check` passes; `makemigrations --check --dry-run` reports nothing
- Every new file-removal assertion sits inside `django_capture_on_commit_callbacks` — verify by inspection, since without it the assertion passes vacuously

#### Manual Verification

- Uploading a replacement GPX still removes the previous file from `MEDIA_ROOT` (unchanged behaviour, new mechanism)
- Deleting a trip from the Django admin removes its GPX files from `MEDIA_ROOT`
- Selecting several trips in the admin and using **Delete selected trips** removes all their GPX files — the bulk path a view-level fix would have missed
- The upload flow and detail page are visibly unchanged

**Implementation Note**: After this phase and all automated verification passes, pause for
manual confirmation before proceeding. The admin bulk-delete check is the one that
justifies choosing a signal over a view-level hook — do not skip it.

---

## Phase 3: Delete a Trip (FR-008)

### Overview

Add `TripDeleteView` with a confirmation page — the repo's first — its route, and a Delete
link on the detail page. File cleanup comes for free from Phase 2.

### Changes Required

#### 1. The delete view

**File**: `trips/views.py`

**Intent**: Let a rider delete their own trip, asking on GET and performing on POST.

**Contract**: `class TripDeleteView(LoginRequiredMixin, _DeleteSuccessMessageMixinBase,
_TripDeleteViewBase)` with `success_url = reverse_lazy("trips:list")`, a static
`success_message`, `http_method_names = ["get", "post"]`, and the same owner-scoped
`get_queryset()` as the other views.

`http_method_names` is load-bearing here rather than stylistic. Without it,
`DeletionMixin.delete()` stays reachable and a raw HTTP `DELETE` destroys the trip **and
its GPX file** with no confirmation page — the very guard §4 leans on when it makes the
detail-page control a link instead of a form. Comment it as such; the full mechanism is in
*Critical Implementation Details → Verb narrowing*.

Three typing facts, each verified against the installed stubs — getting any of them wrong
raises at import:

- `_TripDeleteViewBase = DeleteView[Trip, Form]` — **two** parameters
  (`django-stubs/views/generic/edit.pyi:82`), with `Form` being `django.forms.Form`,
  `BaseDeleteView.form_class`'s default.
- A **separate** `_DeleteSuccessMessageMixinBase = SuccessMessageMixin[Form]` alias. The
  existing `_SuccessMessageMixinBase` at `:25` is `SuccessMessageMixin[TripForm]` and
  cannot be reused here, because the mixin is parameterized by the form
  (`contrib/messages/views.pyi:10`), and a delete view's form is the empty `Form`.
- `success_message` must be a **static string**. `get_success_message(cleaned_data)`
  receives `{}` from the empty `Form`, so a `%(name)s` placeholder raises at runtime. If
  the trip's name is wanted in the message, override `get_success_message` and read
  `self.object`, which survives in memory after the delete with `pk` set to `None`.

No resolve-the-object-before-the-form override is needed: `BaseDeleteView.post` already
sets `self.object = self.get_object()` before `get_form()`, so the owner-scoped queryset
404s a foreign POST on its own. This is the one place the `GpxUploadView.post:68-76`
pattern does **not** need repeating — worth a comment saying so, since the divergence
otherwise reads as an omission.

#### 2. The route

**File**: `trips/urls.py`

**Intent**: Expose delete at the path the verb-segment convention implies.

**Contract**: `path("<int:pk>/delete/", views.TripDeleteView.as_view(), name="delete")`.

#### 3. The confirmation page

**File**: `trips/templates/trips/trip_confirm_delete.html` (new)

**Intent**: Ask before destroying a trip and its GPX file, naming what is about to go and
saying plainly that it cannot be undone.

**Contract**: `DeleteView` resolves this filename by itself via
`template_name_suffix = "_confirm_delete"`; set `template_name` explicitly anyway, per the
Phase 1 reasoning. Extends `base.html`, fills `{% block title %}` and
`{% block content %}`. A POST form to the delete URL with `{% csrf_token %}` immediately
after `<form>` and a submit button; the trip's name in the prose; a sentence stating the
attached GPX file goes too, since that is the part a rider cannot re-derive — wrapped in
`{% if trip.tracks.all %}` so a trackless trip is not warned about losing a file it never
had (Manual Testing step 4 deletes exactly such a trip); and a Cancel
`<p><a>…</a></p>` **outside** the `<form>` pointing at `trip.get_absolute_url` — the
binding convention review F1 established. No `{% static %}` reference, so
`tests/test_static_references.py`'s hand-maintained tuple (`:45-53`) needs no change. No
CSS.

Branch in the template rather than on a new context key: `trip_confirm_delete.html` is
rendered only by `TripDeleteView`, so the cross-app context-coupling trap does not apply
either way, and `trip_detail.html` already branches on this same condition twice (`:22`,
`:61`) — following it keeps one idiom instead of introducing a second.

#### 4. The detail-page entry point

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: Put Delete next to the Edit link added in Phase 1.

**Contract**: An `<a>` to `{% url 'trips:delete' pk=trip.pk %}` beside the Edit link. A
link, not a form — the confirmation page is the guard, so this is a navigation to it. No
new context key.

#### 5. Tests

**File**: `tests/trips/test_trip_delete.py` (new)

**Intent**: The fixed matrix, plus the two things only delete has: a confirmation GET that
destroys nothing, and a POST that removes the row, its track rows **and** their files.

**Contract**: Same style rules as Phase 1. Cases: owner GET → 200 rendering the trip's name
and the irreversibility copy, with `Trip.objects.count()` unchanged — a confirmation page
that deletes on GET is the failure this asserts against; the same GET on a **trackless**
trip → 200 with the GPX sentence **absent**, which is the only automated check on the
`{% if trip.tracks.all %}` branch; owner POST → 302 to the trip list,
trip gone from the database, success message asserted on the next page's body; owner POST
on a trip with a stored track, wrapped in `django_capture_on_commit_callbacks(execute=True)`
→ the `GpxTrack` row **and** its file both gone (this is the end-to-end proof that Phase 2
wired into Phase 3, and it is the assertion the whole S-03 handoff was about); other
user's pk GET **and** POST → 404 each, paired with an assertion the trip still exists,
using a needle with no escapable characters; anonymous GET and POST → 302 to login with
`?next=`; `PUT` and `DELETE` verbs → 405 **each**, the `DELETE` case paired with an
assertion that the trip still exists — that pairing is what states the real stake, since a
dropped `http_method_names` turns this leg into a silent confirmation-free deletion.

### Success Criteria

#### Automated Verification

- `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` passes with no coverage regression
- `uv run mypy .` passes — the two-parameter `DeleteView[Trip, Form]` and the separate `SuccessMessageMixin[Form]` alias both import
- `uv run ruff check .`, `uv run black --check .`, `uv run isort --check-only .` pass
- `uv run python manage.py check` passes; `makemigrations --check --dry-run` reports nothing
- `uv run python manage.py collectstatic --noinput` succeeds and `tests/test_static_references.py` still passes
- The cross-user delete POST test asserts the trip **still exists**, not just the 404

#### Manual Verification

- The Delete link opens a page that names the trip and says the deletion is permanent and takes the GPX file with it
- Cancel on that page returns to the trip with nothing deleted
- Confirming returns to the trip list, the trip is gone, the success message shows, and the trip's `.gpx` file is gone from `MEDIA_ROOT`
- Reloading the deleted trip's detail URL gives a 404
- Deleting a trip that has no GPX file works, raises nothing, and its confirmation page does **not** mention a GPX file

**Implementation Note**: After this phase and all automated verification passes, pause for
manual confirmation. **Both must-have FRs are complete at this point** — Phase 4 is the
cut line and can be dropped if the deadline requires it.

---

## Phase 4: E-08 — Block Future Dates and Label the Date Field

### Overview

Add the `clean_date()` the E-08 row proposed, with the tolerance that keeps it from
misfiring and the escape that keeps it from trapping riders, plus the field label the
constraint implies. **Droppable phase** — if the `2026-09-10` deadline bites, stop after
Phase 3 and leave E-08 open with the frame brief as its record.

The product decision is **already made**, not open. E-08's binary was "block, or allow and
label as 'planned'" — and option two is excluded by a named Non-Goal (*"not a planner"*,
`prd.md:112`), reinforced by the persona (`prd.md:29`) and vision (`prd.md:23`), and
confirmed by the owner's "always after riding". See `frame.md` for the full derivation.

### Changes Required

#### 1. The validation rule and the label

**File**: `trips/forms.py`

**Intent**: Reject a date far enough in the future that it cannot be a ride that happened,
and say on the field what the date means — choosing the constraint is choosing enough
meaning to write the label.

**Contract**: Add `def clean_date(self) -> date:` to `TripForm`, raising
`forms.ValidationError` when the value is later than one day past the current date, and
returning it otherwise. Add `help_texts = {"date": ...}` to `Meta` stating the date is when
the ride happened.

The key is `help_texts`, **plural**. `ModelFormOptions` reads
`getattr(options, "help_texts", None)` (`django/forms/models.py:268`, applied at
`:231-232`), so a singular `help_text = {...}` on `Meta` is silently ignored — no error,
nothing rendered, every automated gate green. One mechanism, not "and/or": `labels` is not
the one to reach for, because the auto-derived label is already "Date" and what is missing
is the sentence saying *which* date, not a better caption.

Three things the rule must get right:

1. **The tolerance is `+1 day`, and the reason is exact.** `TIME_ZONE = "UTC"` with
   `USE_TZ = True` (`velo_log/settings.py:130,134`) means `timezone.localdate()` returns
   the **UTC** date, while the `type="date"` widget submits the rider's **local** date. A
   rider at UTC+2 entering today between local 00:00 and 02:00 is submitting tomorrow's
   UTC date. Comparing against `timezone.localdate() + timedelta(days=1)` closes that
   window, and one day is provably sufficient: no real timezone is more than 14h ahead of
   UTC, so a local date can never exceed the UTC date by more than one. The comment must
   carry this reasoning — a bare `+ timedelta(days=1)` reads as a fudge.
2. **Skip the rule when the date is unchanged.** `TripForm` is shared by create and edit,
   so an unguarded rule makes an already-saved future-dated trip **uneditable** — a rider
   could not fix its name without also changing its date, a trap landing precisely in the
   slice that introduces editing. Guard on `"date" not in self.changed_data`. `TripAdmin`
   (`trips/admin.py:13-22`) declares no `form =`, so admin keeps a default `ModelForm` and
   stays the repair path its docstring claims.
3. **The branch must be covered in both directions.** `plan-review.md` F3 killed a planned
   `clean_name()` as an inert, permanently uncoverable branch in a coverage-gated package.
   That objection does not transfer — a future-date branch is reachable and testable — but
   it sets the bar, and `branch = true` means a half-covered `clean_date()` shows as a gap.

**Migration note**: adding `help_text` or `verbose_name` **to the model** generates a
migration; adding `labels`/`help_texts` to the **form's** `Meta` does not. Prefer the form
if no migration is wanted. If the model is touched instead, generate and commit the
migration by hand and verify with `makemigrations --check --dry-run` — `manage.py check`
passes with a model/schema mismatch, and the deploy pipeline runs `migrate` unattended
(`lessons.md` #9).

#### 2. Tests

**File**: `tests/trips/test_trip_creation.py`

**Intent**: `TripForm.date` has zero negative-path coverage today. Add the future-date
rejection and the boundary that proves the tolerance is deliberate.

**Contract**: Forms are exercised **only through views** in this suite — no test
instantiates a form class — so assert via `response.context["form"].errors["date"]`. Cases:
a far-future date → 200 re-render with a `date` error and nothing persisted; today's date
→ accepted; the `+1 day` boundary → accepted, which is the test that documents the
tolerance as intentional rather than an off-by-one; one day past the boundary → rejected.
Add one more, cheap and non-negotiable: a GET of the create form asserts the help-text
sentence appears in `response.content`. A misspelled `Meta` key fails no gate and renders
nothing — this assertion is the only thing standing between that typo and a green build.
Compute dates relative to `timezone.localdate()`, never as literals, or the tests expire.
Existing tests post `2026-06-01`/`2026-07-01`, both past — they need no change.

**File**: `tests/trips/test_trip_edit.py`

**Intent**: Prove the `changed_data` escape works, because it is the part that prevents a
trap rather than adding a rule.

**Contract**: Two cases: editing only the **name** of a trip whose stored date is in the
future → succeeds, date unchanged; editing that trip's date to another future date →
rejected with a `date` error. Build the future-dated trip directly via
`Trip.objects.create`, bypassing the form — the form is what now refuses to make one.

### Success Criteria

#### Automated Verification

- `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` passes with no coverage regression
- `clean_date()` shows **no partial branch** in the coverage report — both directions exercised, and the `changed_data` guard exercised both ways
- All six existing `tests/trips/test_trip_creation.py` posts still pass unchanged
- `uv run ruff check .`, `uv run black --check .`, `uv run isort --check-only .`, `uv run mypy .` pass
- `uv run python manage.py check` passes; `makemigrations --check --dry-run` reports nothing — or, if the model was touched, the generated migration is committed and the check is clean
- No future-date literals in the new tests: they compute from `timezone.localdate()`

#### Manual Verification

- Submitting a trip dated next year shows an error next to the date field and does not save
- Submitting today's date saves normally
- The date field **renders** a help text on the page saying it is when the ride happened — visible in the browser, not merely present in `Meta`
- A future-dated trip created through the admin can still have its **name** edited through the app without touching its date
- The admin can still change that trip's date, as its repair-path docstring claims

**Implementation Note**: After this phase and all automated verification passes, pause for
manual confirmation before Phase 5.

---

## Phase 5: Bookkeeping — Roadmap, Backlog, Docs

### Overview

Record what shipped and what was deliberately deferred. Committed **last**, after every
fix it describes already exists in history (`lessons.md` #8,
`~/.claude/rules/git-workflow.md`).

### Changes Required

#### 1. Roadmap status

**File**: `context/foundation/roadmap.md`

**Intent**: Close S-04 and E-08, and record the start/end date split as a new open row so a
real product insight is not lost by being out of scope.

**Contract**: Set S-04's status to `done` in all **three** places the `/10x-roadmap`
template keeps it — the `## At a glance` row (`:33`), the item body's `- **Status:**` line
(`:101`), and the **Backlog Handoff** row (`:121`), whose `Ready for /10x-plan` cell still
reads `no` and whose Notes still read "Waiting on S-02" although S-02 shipped long ago.
Follow the S-02 precedent two rows up (`:118`): `yes`, with Notes reading "Planned and
implemented (Phase 5, `/10x-implement edit-and-delete-trip`)". The Backlog Handoff table is
the site a `grep` for the first two forms misses — the `lessons.md` #5 shape exactly.

Fix S-03's Backlog Handoff row (`:120`) in the same pass: it reads `no` / "Waiting on S-02"
even though S-03 shipped, and this slice is already opening the table. S-05's "Waiting on
S-03" note (`:122`) is knowingly **left alone** — declaring S-05 ready is a sequencing
judgment for the next roadmap pass, not a bookkeeping correction this slice can make.
Set E-08's `Status` cell to `done` (`:159`) with the `Change ID` cell filled in as
`edit-and-delete-trip`, following the E-05 precedent of a narrative close (`:157`). If
Phase 4 was dropped, leave E-08 `open` and name the frame brief as its record instead.

Add a new Engineering Backlog row: split `Trip.date` into start and end dates. Proposed fix
and trigger per `frame.md` — the trigger is FR-011 (multi-stage grouping), where multi-day
chronology actually lives per `prd.md:99`. Note in it that this needs a PRD amendment
(FR-003, FR-007 and the Primary Success Criterion all say "a date", singular).

Bump the frontmatter `updated:` if the file has one.

#### 2. Change identity

**File**: `context/changes/edit-and-delete-trip/change.md`

**Intent**: Reflect the shipped state.

**Contract**: `status` and `updated` per the change-chain conventions; note in `## Notes`
whether E-08 shipped or was re-deferred.

#### 3. Docs the slice invalidated

**Files**: `AGENTS.md`, `context/foundation/lessons.md`

**Intent**: `AGENTS.md` loads every session, so a stale claim actively misdirects the next
agent rather than merely being out of date (`lessons.md` #5).

**Contract**: Check `AGENTS.md`'s `trips/` and `gpx/` app descriptions — `gpx/` is
described as "upload, parse, store and download a trip's GPX file, and build the map
config"; it now also owns file lifecycle on deletion via a signal, which is a genuinely
new responsibility a future agent needs to know about. Update the `trips/` line for
edit/delete. Add nothing about coverage scope — no new package shipped, so
`[tool.coverage.run] source` is unchanged (`lessons.md` #4 does not apply).

Consider a `lessons.md` entry for the fast-delete finding: *a `post_delete` receiver is
what makes a cascade's rows materialize at all, so file cleanup on cascade is impossible
without one.* It is a non-obvious framework property that cost real verification effort
here and would cost it again. Add via `/10x-lesson` if it survives review.

### Success Criteria

#### Automated Verification

- `grep -n "S-04" context/foundation/roadmap.md` shows `done` in the glance table and the item body, and `yes` in the Backlog Handoff row; `grep -n "Waiting on S-02" context/foundation/roadmap.md` returns **nothing** (clears both the S-04 and the S-03 row)
- `grep -n "E-08" context/foundation/roadmap.md` shows a status consistent with whether Phase 4 shipped
- The new start/end-date backlog row exists with a trigger and a PRD-amendment note
- `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov` still passes
- `git log --oneline master..HEAD` shows every fix commit preceding the commit that records its decision

#### Manual Verification

- `AGENTS.md` describes `gpx/`'s file-lifecycle responsibility and `trips/`'s edit/delete accurately enough that a fresh agent would not have to rediscover the signal
- The roadmap reads correctly end to end, including the case where E-08 was re-deferred
- No file under `context/archive/` was modified (`lessons.md` #7)

**Implementation Note**: This phase is documentation only. Commit it after every code
commit it references.

---

## Testing Strategy

### Unit Tests

- `clean_date()` at all four points around the tolerance: far future rejected, today
  accepted, the `+1 day` boundary accepted, one day past it rejected — computed relative
  to `timezone.localdate()`, never as literals
- The `changed_data` escape in both directions, exercised through the edit view
- The `post_delete` receiver on each path it exists for: direct `Model.delete()`,
  `QuerySet.delete()` over N tracks, `Trip.delete()` cascade, and a rolled-back delete
  that must **not** remove the file
- A cleanup failure that must not raise, via a monkeypatched `FileSystemStorage.delete`

### Integration Tests

- The fixed owner-scoped matrix on both new surfaces: owner → 200; other user → 404 **plus**
  a persistence assertion; anonymous → 302 with `?next=`; wrong verb → 405 — the last leg
  holding only because both views narrow `http_method_names`, and the `DELETE` case pairing
  the status code with a still-exists assertion
- Edit: GET pre-fills, POST persists and redirects to the trip, invalid POST re-renders
  with a field error, `owner` cannot be mass-assigned
- Delete: GET destroys nothing, POST removes the trip **and** its track rows **and** their
  files end to end
- The create flow's Cancel markup survives the template conditionals byte-identically

### Manual Testing Steps

1. Create a trip, upload a GPX, then edit the trip's name from its detail page — confirm the change lands on both the detail page and the list, and the GPX is untouched
2. Confirm the edit page is not titled "New trip", and that Cancel returns to the trip while the new-trip page's Cancel still returns to the list
3. Delete that trip: confirm the page names it and warns about the file, that Cancel leaves it intact, and that confirming removes the trip **and** its `.gpx` from `MEDIA_ROOT`
4. Delete a trip that has no GPX file at all — nothing should raise, and its confirmation page must **not** claim a GPX file is about to go
5. In the Django admin, select several trips and use **Delete selected trips**; confirm every GPX file is gone from `MEDIA_ROOT`. This is the bulk path a view-level cleanup would have missed and is the check that justifies the signal
6. Submit a trip dated next year — expect a rejection next to the date field; submit today's date — expect success
7. Create a future-dated trip through the admin, then edit only its **name** through the app — expect success
8. Log in as a second rider and request the first rider's edit, delete and confirm-delete URLs by pk — expect 404 on every one, and confirm the trip still exists afterwards

## Performance Considerations

Registering a `post_delete` receiver on `GpxTrack` disables Django's fast-delete
optimization for that model, so a cascade now issues one `DELETE` per row instead of one
bulk statement, and materializes the instances. That is the point — without it there is no
instance to read a file path from. The cost is bounded: v1 keeps one track per trip, and
deletion is a rare, single-trip, user-initiated action. The Volume is single-region at
3,000 IOPS, and the archive's warning was about an *unbounded orphan set* being the real
cost (`upload-gpx-and-view-map/plan.md:1233-1239`) — this trades a negligible per-delete
cost for eliminating it.

No new queries on any read path. The detail page's two new links resolve from `trip.pk`,
already loaded, so no extra context key and no extra query.

## Migration Notes

No model field changes are expected, so no migration should appear. The one way this slice
generates one is Phase 4 adding `help_text`/`verbose_name` to the **model** rather than the
**form** — prefer the form. If a migration does appear, generate and commit it by hand and
verify with `makemigrations --check --dry-run`: `manage.py check` passes with a
model/schema mismatch, and the deploy pipeline runs `migrate` unattended before starting
gunicorn, so a forgotten migration ships green through every gate and surfaces as a
production `no such column` (`lessons.md` #9).

Existing future-dated trips in production are **not** migrated or repaired. Phase 4's
`changed_data` guard leaves them editable, and admin remains the repair path.

## References

- Frame brief: `context/changes/edit-and-delete-trip/frame.md`
- Research: `context/changes/edit-and-delete-trip/research.md`
- The cleanup mechanism to reuse: `gpx/views.py:28-47`, invoked at `:141`
- The authorization idiom and its docstring: `trips/views.py:58-66`
- The `TYPE_CHECKING` base-alias idiom to extend: `trips/views.py:21-30`
- `on_commit` test exemplars: `tests/gpx/test_gpx_upload.py:272`, `:309`
- The cross-user 404 idiom to copy: `tests/trips/test_trip_detail.py:32-41`
- The mass-assignment test, closest edit analogue: `tests/trips/test_trip_creation.py:48-64`
- Fast-delete signal gating: `django/db/models/deletion.py:186-206`
- `BaseDeleteView.post` / `form_class = Form`: `django/views/generic/edit.py`
- Stub arity: `django-stubs/views/generic/edit.pyi:69,82`; `contrib/messages/views.pyi:10`
- The orphan-file handoff: `context/archive/2026-08-23-upload-gpx-and-view-map/plan.md:1233-1239`
- Review findings a delete path re-encounters: `.../reviews/impl-review-phase-4.md:98-164`
- Cancel binding convention: `context/archive/2026-08-26-discard-new-trip-form/reviews/impl-review.md:23-36`
- `clean_name()`'s deletion and the bar it set: `context/archive/2026-08-23-create-and-list-trips/reviews/plan-review.md:52-64`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Edit a Trip (FR-007)

#### Automated

- [x] 1.1 CI-equivalence pytest run passes with no coverage regression
- [x] 1.2 ruff, black, isort pass
- [x] 1.3 mypy passes — two-parameter `UpdateView[Trip, TripForm]` alias imports
- [x] 1.4 `manage.py check` passes
- [x] 1.5 `makemigrations --check --dry-run` reports no missing migration
- [x] 1.6 `test_trip_creation.py:88-93` passes unchanged (create markup byte-identical)

#### Manual

- [x] 1.7 Edit page is titled and headed for editing, not "New trip"
- [x] 1.8 Cancel targets differ correctly between edit and create
- [x] 1.9 Editing a name updates detail and list, success message appears
- [x] 1.10 Edit link present on detail page, absent from trip list

### Phase 2: A `post_delete` Signal Owns GPX File Cleanup

#### Automated

- [ ] 2.1 CI-equivalence pytest run passes with no coverage regression
- [ ] 2.2 Both existing upload `on_commit` tests pass with scheduling moved
- [ ] 2.3 `grep -rn "discard_superseded_file\|handed to S-04" gpx/ tests/` returns no hits
- [ ] 2.4 ruff, black, isort, mypy pass
- [ ] 2.5 `manage.py check` and `makemigrations --check --dry-run` clean
- [ ] 2.6 Every new file-removal assertion sits inside `django_capture_on_commit_callbacks`

#### Manual

- [ ] 2.7 Replacement upload still removes the previous file from `MEDIA_ROOT`
- [ ] 2.8 Admin single-trip delete removes its GPX files
- [ ] 2.9 Admin **Delete selected trips** bulk action removes all their GPX files
- [ ] 2.10 Upload flow and detail page visibly unchanged

### Phase 3: Delete a Trip (FR-008)

#### Automated

- [ ] 3.1 CI-equivalence pytest run passes with no coverage regression
- [ ] 3.2 mypy passes — `DeleteView[Trip, Form]` and the separate `SuccessMessageMixin[Form]` alias import
- [ ] 3.3 ruff, black, isort pass
- [ ] 3.4 `manage.py check` and `makemigrations --check --dry-run` clean
- [ ] 3.5 `collectstatic --noinput` succeeds and `test_static_references.py` passes
- [ ] 3.6 Cross-user delete POST test asserts the trip still exists, not just the 404

#### Manual

- [ ] 3.7 Confirmation page names the trip and warns the GPX file goes too
- [ ] 3.8 Cancel returns to the trip with nothing deleted
- [ ] 3.9 Confirming removes trip, redirects to list, shows message, and the `.gpx` is gone from `MEDIA_ROOT`
- [ ] 3.10 Deleted trip's detail URL gives 404
- [ ] 3.11 Deleting a trip with no GPX file raises nothing and its confirmation page omits the GPX sentence

### Phase 4: E-08 — Block Future Dates and Label the Date Field

#### Automated

- [ ] 4.1 CI-equivalence pytest run passes with no coverage regression
- [ ] 4.2 `clean_date()` shows no partial branch; `changed_data` guard exercised both ways
- [ ] 4.3 All six existing `test_trip_creation.py` posts pass unchanged
- [ ] 4.4 ruff, black, isort, mypy pass
- [ ] 4.5 `manage.py check` clean; `makemigrations --check --dry-run` clean or migration committed
- [ ] 4.6 No future-date literals in the new tests

#### Manual

- [ ] 4.7 Trip dated next year shows a date error and does not save
- [ ] 4.8 Today's date saves normally
- [ ] 4.9 Date field renders a help text on the page saying it is when the ride happened
- [ ] 4.10 A future-dated trip's name can still be edited without touching its date
- [ ] 4.11 Admin can still change that trip's date

### Phase 5: Bookkeeping — Roadmap, Backlog, Docs

#### Automated

- [ ] 5.1 S-04 `done` in glance table, item body and Backlog Handoff row; no "Waiting on S-02" text left on the S-04 or S-03 rows
- [ ] 5.2 E-08 status consistent with whether Phase 4 shipped
- [ ] 5.3 New start/end-date backlog row exists with trigger and PRD-amendment note
- [ ] 5.4 CI-equivalence pytest run still passes
- [ ] 5.5 `git log --oneline master..HEAD` shows every fix commit preceding its decision commit

#### Manual

- [ ] 5.6 `AGENTS.md` accurately describes `gpx/`'s file-lifecycle role and `trips/`'s edit/delete
- [ ] 5.7 Roadmap reads correctly end to end, including the E-08-deferred case
- [ ] 5.8 No file under `context/archive/` was modified
