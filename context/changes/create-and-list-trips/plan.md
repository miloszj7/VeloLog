# Create and List Trips (S-02) Implementation Plan

## Overview

Deliver roadmap slice S-02: a user can create a trip with a name, date, and description, and see it in a list of their own trips. Along the way this slice establishes the repo's first model, first migration, first authorization surface, and first shared template — and retires the throwaway `accounts.landing` page that S-01 built as a placeholder and explicitly designated S-02 to delete.

## Current State Analysis

- **No models, no migrations anywhere.** `accounts/` has no `models.py` and no `migrations/` directory; the S-01 review confirms this is correct for that slice, not an oversight (`context/archive/2026-08-22-user-registration-login/reviews/impl-review.md:361-363`). The only migrations that have run against production are Django's contrib ones.
- **No authorization beyond "is logged in".** No queryset in the repo is scoped to a user — no `filter(owner=...)`, no `get_queryset()` override, no object-level check. No test creates a second user (`tests/accounts/`, 11 tests, all single-user).
- **`accounts/` is the only house-style reference.** Files are `apps.py`, `forms.py`, `urls.py`, `views.py`, and three templates. No `services.py`, no service layer anywhere; validation lives in forms, orchestration in views.
- **The mypy-strict CBV shim is mandatory** (`accounts/views.py:21-24`). Django's generic CBVs have no `__class_getitem__`, so subscripting them raises at import time while django-stubs requires the subscript. The repo has zero `# type: ignore` and zero `# noqa`.
- **Templates are three standalone HTML5 documents** under `accounts/templates/accounts/`. No `base.html`, no `{% extends %}`, no `{% block %}`, no CSS, not a single `class=` attribute. `TEMPLATES["DIRS"]` is `[]` with `"APP_DIRS": True` (`velo_log/settings.py:64-65`).
- **`accounts/landing.html:9-12` holds the app's only logout control** — a POST form, as Django ≥4.1 requires.
- **All redirect targets are settings-sourced URL names** (`velo_log/settings.py:136-138`), and `SignUpView.success_url` reads `settings.LOGIN_REDIRECT_URL` (`accounts/views.py:32`). Repointing the post-login destination is therefore a one-line change that propagates.
- **The messages framework is fully wired with zero consumers** (`settings.py:43`, `:55`, `:70`) — no render markup exists anywhere.
- **The site root `/` is unrouted and 404s** (`velo_log/urls.py:36-46`).
- **`trips` is invisible to the coverage gate.** `pyproject.toml:63` reads `source = ["accounts", "velo_log"]` with `fail_under = 80` at `:67` — a new app's code would be unmeasured and the gate would pass regardless.
- **CI is weaker than it looks.** `.github/workflows/deploy.yml` triggers on push to `master` only and gates on bare `manage.py check`. Tests, ruff, black, isort, and mypy do not run in CI at all. `manage.py check` does **not** detect a model/schema mismatch.
- **Migrations run unattended in production.** `railway.json` chains `collectstatic --noinput && migrate && gunicorn velo_log.wsgi`, so a failing migration aborts before gunicorn starts — a hard outage, not a degraded deploy. There is no atomic rollback; recovery is redeploy-by-ID from `DEPLOY.md:5-10`.

## Desired End State

An authenticated user lands on their trip list after logging in. The list shows only their own trips, newest tour date first, and shows a clear empty state when they have none. A "New trip" action opens a form for name, date, and description; submitting it saves the trip owned by that user, redirects back to the list with a flash confirmation, and the new trip is visible. A second user's trips are never visible, and a trip with no attached file is a perfectly valid row — the state S-03 will build its upload and map path on top of.

Verify via:

```bash
uv run python manage.py makemigrations --check --dry-run   # exits 0 — no pending model changes
uv run pytest --cov                                        # all tests pass, fail_under=80 met with trips in scope
uv run python manage.py check --deploy                     # with DEBUG=False and a real SECRET_KEY
```

### Key Discoveries

- The `AUTH_USER_MODEL` decision becomes permanent with this migration. S-01 accepted stock `django.contrib.auth.models.User` as residual risk (`impl-review.md:196-207`), and the review flagged that swapping after the first migration is "significantly more difficult" (`impl-review.md:178-180`). `Trip.owner` uses the portable `settings.AUTH_USER_MODEL` form against stock `auth.User`.
- `ListView[Trip]` takes **one** type parameter; `CreateView[Trip, TripForm]` takes **two** (`accounts/views.py:21-24` shows the two-arg case).
- `{{ form.non_field_errors }}` is load-bearing — omitting it was critical review finding F1, which shipped to `master` with all gates green and rendered a blank form on invalid login (`impl-review.md:44-75`).
- `accounts/apps.py:1-6` sets `default_auto_field` per AppConfig; there is no project-level `DEFAULT_AUTO_FIELD`, so `trips/apps.py` must set it or the model silently gets an `AutoField` PK and raises `models.W042` — a warning that would not fail the CI gate either.
- `pyproject.toml:60` sets `python_files = ["tests.py", "test_*.py"]`, so a `startapp`-generated `trips/tests.py` **would be collected**; and since the `S101` assert exemption is keyed to `"tests/**"` (`pyproject.toml:44`), an app-local `tests.py` would fail ruff. Delete it.
- `include("accounts.urls")` at `velo_log/urls.py:39` precedes the concrete `accounts/login/` route, so route ordering at project level is already delicate.

## What We're NOT Doing

- **No edit or delete** — that is S-04 (`roadmap.md:33`).
- **No GPX upload, file storage, map rendering, or `MEDIA_ROOT` configuration** — that is S-03 (`roadmap.md:32`). No media config exists at all today and this slice does not add any.
- **No trip detail view.** S-02's outcome is create + list; detail is where S-03 hangs the map.
- **No filtering, sorting controls, search, or pagination** — FR-012 is explicitly parked (`roadmap.md:135`), and the PRD scopes v1 to a minimal list.
- **No visibility toggle** — FR-009 is parked; all trips are private in v1 (`prd.md:104`).
- **No CSS, no stylesheet, no static asset.** Continuing the S-01 decision (`plan.md:41`); `base.html` leaves one obvious insertion point for later.
- **No custom `AUTH_USER_MODEL`, no user profile model.** The stock-`User` decision stands.
- **No `services.py` or repository layer** for a single-model CRUD slice — the repo has no service layer and this is not the slice to introduce one.
- **No logging configuration.** The project has none and `roadmap.md:46` acknowledges the gap; introducing it here is unrelated scope.
- **No new CI jobs.** Adding a test/lint/type job to CI is real and needed, but landing it on the same deploy as the first production migration stacks two risky firsts. It goes to the Engineering Backlog (Phase 5) instead. The single exception is one flag-only command appended to the `manage.py check` step that already exists (Phase 1 #7) — it adds no job, no secret, and no database, and it guards the exact failure this slice names as a hard outage.
- **No new dependencies.** Everything this slice needs is already installed (`pyproject.toml:7-12`).

## Implementation Approach

Five phases, ordered so the irreversible and highest-risk decisions land first and the configuration-only switchovers land last — following S-01's stated ordering rationale (`plan.md:53`).

Phase 1 carries the schema, the `AUTH_USER_MODEL` lock-in, and the first production migration. Phase 2 pulls the shared template forward because both remaining UI phases depend on it, and because it is what lets the logout control survive the landing page's deletion. Phase 3 builds the actual slice outcome. Phase 4 is a clean switchover that flips the post-login destination and deletes the placeholder. Phase 5 records what this slice learned and what it deliberately left undone, then walks the deploy ritual.

Each phase leaves the repo working, tested, and committable. One commit per phase, matching S-01's practice.

## Critical Implementation Details

**Ordering requirement — the migration must be generated and committed by hand.** CI cannot catch its absence: `manage.py check` passes with a model/schema mismatch, and `railway.json` then runs `migrate` before gunicorn. A forgotten migration file ships green and surfaces as production 500s with `no such column`. `makemigrations --check --dry-run` is the gate — run locally, and appended to the existing CI merge-gate step in Phase 1 #7 so the deploy cannot proceed without it. Its meaning inverts from S-01's usage — S-01 expected no changes because there were no models; S-02 expects a *committed* migration that leaves nothing pending.

**Owner assignment must never be client-supplied.** `owner` is excluded from `TripForm.Meta.fields` entirely and set in `form_valid` from `self.request.user`. A form field that merely defaults to the current user is bypassable by POSTing another user's ID, which would breach the PRD guardrail at `prd.md:43`. This pattern propagates to S-03 and S-04, so getting it right here matters beyond this slice.

**Local manual verification needs `DEBUG=True` in `.env`.** `SECURE_SSL_REDIRECT` and Secure-flagged cookies activate whenever `DEBUG` is falsy (`settings.py:140-149`), and browsers silently drop Secure cookies over the plain-HTTP dev server, making login appear broken. Django's test `Client` is unaffected.

## Phase 1: Trip model, app scaffold, and the first migration

### Overview

Create the `trips` app, define the `Trip` model with its owner relationship and default ordering, generate and commit the repo's first migration, and bring the app into coverage scope so its later code is actually measured.

### Changes Required

#### 1. App scaffold

**File**: `trips/apps.py`, `trips/__init__.py`

**Intent**: Create the `trips` app at the repo root per `AGENTS.md`, mirroring `accounts/`'s structure. Delete the `startapp` output `accounts/` has no use for — `tests.py` (which pytest would collect and ruff would then fail on) and the placeholder `views.py` body; the empty `migrations/` scaffolding is kept. `admin.py` is the one deliberate departure from `accounts/`'s shape and is kept — see #8.

**Contract**: `TripsConfig` sets `default_auto_field = "django.db.models.BigAutoField"` and `name = "trips"`. `__init__.py` is empty, with no `__all__`, matching `accounts/__init__.py`.

#### 2. App registration

**File**: `velo_log/settings.py`

**Intent**: Register the new app so its models and templates are discovered.

**Contract**: Append the bare label `"trips"` after `"accounts"` at `:45`, relying on app-config auto-discovery exactly as `accounts` does.

#### 3. The Trip model

**File**: `trips/models.py`

**Intent**: Define the single domain entity for this slice — a trip a user owns, with the three fields FR-003 names. Description is optional so that a minimal trip is quick to create; name and date are required.

**Contract**: `Trip` with `name` (`CharField`), `date` (`DateField` — a user-entered calendar date, deliberately not `DateTimeField`, since `USE_TZ = True` at `settings.py:118` would make a datetime ambiguous), `description` (`TextField`, blank-permitted), and `owner` (`ForeignKey` to `settings.AUTH_USER_MODEL` with `on_delete=models.CASCADE` and a `related_name` for reverse access from a user). `Meta.ordering = ["-date", "-id"]` — newest tour date first, with the id tiebreak making the order deterministic when two trips share a date, which matters for test stability. A one-line Google-style docstring on the class, and `__str__` returning the trip name.

**Caution**: `owner` must be non-nullable. Because there are no existing rows and no existing migrations, this is free now — adding a non-null FK later would require a data migration.

#### 4. The first migration

**File**: `trips/migrations/0001_initial.py`

**Intent**: Generate and commit the migration. This is the artifact CI cannot verify and production runs unattended.

**Contract**: Produced by `uv run python manage.py makemigrations trips`. Committed verbatim — never hand-edited. `makemigrations --check --dry-run` must exit 0 afterwards.

#### 5. Coverage scope and test collection scope

**File**: `pyproject.toml`

**Intent**: Bring `trips` under the coverage gate. Without this, `fail_under = 80` passes no matter how untested the new app is — review finding F10 established widening `source` as the standing obligation whenever a new package ships (`impl-review.md:308-321`). And fix the collection hazard structurally rather than by hand, since `startapp` will generate a `tests.py` again for S-03's `gpx/` app.

**Contract**: `[tool.coverage.run] source` at `:63` becomes `["accounts", "trips", "velo_log"]`. `[tool.pytest.ini_options]` gains `testpaths = ["tests"]`, so an app-local `tests.py` can never be collected regardless of `python_files`.

This is complementary to, not a replacement for, deleting `trips/tests.py` in #1 — the delete keeps the app directory matching `accounts/`, and `testpaths` makes the collection outcome independent of anyone remembering to delete it.

#### 6. Model tests

**File**: `tests/trips/__init__.py`, `tests/trips/test_trip_model.py`

**Intent**: Prove the model's contract — that a trip persists with its owner, that description is genuinely optional, and that the default ordering is what the list view will rely on.

**Contract**: A real package with an empty `__init__.py`, matching `tests/accounts/`. Plain module-level functions, `@pytest.mark.django_db` per test, full `-> None` annotations, `User.objects.create_user(...)` for setup with `"correct-horse-battery-staple"` as the password. Tests: a trip saves with an owner and is reachable via the reverse accessor; a trip saves with an empty description; two trips with different dates come back newest-first; two trips sharing a date come back in a deterministic order. These are the repo's first tests that do not go through `client`.

#### 7. CI migration guard

**File**: `.github/workflows/deploy.yml`

**Intent**: Make the slice's worst failure mode — a forgotten migration file shipping green — impossible to deploy, instead of relying on someone remembering a local command. This is the one CI edit this slice takes; see the reworded scope line above.

**Contract**: Append `uv run python manage.py makemigrations --check --dry-run` to the **existing** "Django check (merge gate)" step, which already injects `SECRET_KEY` and already runs before the "Deploy to Railway" step. No new job, no new secret, no database — `--check --dry-run` compares migration files to models and touches no DB. A non-zero exit fails the workflow, so `railway up` never executes.

**Caution**: This workflow triggers on push to `master` only, so the guard catches the mistake post-merge and pre-deploy, not pre-merge. That gap is what the queued CI job in the Phase 5 backlog closes; this is the cheap half that protects *this* deploy.

#### 8. Admin registration for Trip

**File**: `trips/admin.py`

**Intent**: Keep one read/repair path into the repo's first persisted domain data. `accounts/` skipped `admin.py` for free — it has no models. `Trip` ships onto a SQLite volume with no atomic rollback and a restore path never exercised against production (see Migration Notes), so the cost of *not* having an escape hatch is a `railway ssh` shell session against production data. `django.contrib.admin` is already in `INSTALLED_APPS` (`settings.py:39`) and already routed (`velo_log/urls.py:37`), so this is a ~4-line file.

**Contract**: Register `Trip` with `@admin.register(Trip)` and a `TripAdmin(admin.ModelAdmin[Trip])` — `ModelAdmin` subscripts directly under django-stubs, like `ModelForm` — carrying `list_display = ("name", "date", "owner")`. No other customization.

**Caution**: The admin is only reachable in production if a superuser exists there, and **none does** — no `createsuperuser` step appears in `railway.json`, `DEPLOY.md`, or `deployment-plan.md`. Phase 5's deploy ritual therefore adds creating one as an explicit step; until that runs, this registration buys local and staging value only.

#### 9. Repo-root and lint-config cleanups

**File**: `main.py`, `pyproject.toml`

**Intent**: Two one-line items whose "next slice that touches these files" trigger this slice meets — Phase 1 already edits `pyproject.toml` (including the lint config's own file) and Phase 5 edits repo-root docs. Deferring them to a backlog whose triggers already fired teaches the next reader to ignore the triggers.

**Contract**: Delete the dead `main.py` placeholder at the repo root — it is not referenced by `manage.py`, the WSGI entry point, or `railway.json`. Remove `[tool.ruff.lint] ignore` (`pyproject.toml:39-41`) entirely: its only entry, `S608`, exempts raw-SQL f-strings the project does not have, and an inapplicable blanket exemption is a live hazard the day someone does write raw SQL. `ruff check .` must still pass with the key gone.

### Success Criteria

#### Automated Verification

- Migration is generated and committed: `git status` shows `trips/migrations/0001_initial.py` tracked
- No pending model changes: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies cleanly to a fresh database: `uv run python manage.py migrate`
- Model tests pass: `uv run pytest tests/trips/`
- Full suite still passes: `uv run pytest`
- `trips` appears in the coverage report: `uv run pytest --cov`
- No `models.W042` or other system-check warnings: `uv run python manage.py check`
- Quality gates pass: `/python-quality-gates`
- No `trips/tests.py` exists: the file `startapp` generates is deleted
- CI gate carries the migration check: `.github/workflows/deploy.yml`'s merge-gate step runs `makemigrations --check --dry-run` before the deploy step
- Lint passes with the `S608` ignore removed and `main.py` gone: `uv run ruff check .`

#### Manual Verification

- `uv run python manage.py shell` — a `Trip` can be created against a real user and read back with the expected ordering
- The Django admin loads and lists `Trip` with name, date, and owner (against a local superuser)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Base template and shared chrome

### Overview

Introduce the repo's first shared template so that the logout control survives the landing page's deletion, the messages framework gets a single render site, and S-03/S-04 inherit page chrome instead of re-copying it. Retrofit the two surviving auth templates onto it.

### Changes Required

#### 1. Template directory configuration

**File**: `velo_log/settings.py`

**Intent**: Give the project a place for cross-cutting templates that does not live inside a feature app.

**Contract**: `TEMPLATES[0]["DIRS"]` at `:64` becomes `[BASE_DIR / "templates"]`, keeping `"APP_DIRS": True` so app-namespaced templates continue to resolve.

#### 2. The base template

**File**: `templates/base.html`

**Intent**: Own the document shell, the site-wide header including the logout affordance, and the flash-message render block — the three things that currently either do not exist or are trapped inside `landing.html`.

**Contract**: A complete HTML5 document with `<meta charset="utf-8">` and a `{% block title %}` defaulting to `VeloLog`, following the existing `"<Page> — VeloLog"` em-dash convention. A `<header>` rendering the POST logout form (lifted from `accounts/landing.html:9-12`, `{% csrf_token %}` included) wrapped in `{% if user.is_authenticated %}` so anonymous pages do not show it. A messages block iterating `{% if messages %}{% for message in messages %}`. A `{% block content %}` for page bodies. No CSS, no `class=` attributes — consistent with the standing decision.

**Caution**: The logout form's `action` is `{% url 'logout' %}` — the project-level unnamespaced name, not an `accounts:` one.

#### 3. Retrofit the auth templates

**File**: `accounts/templates/accounts/login.html`, `accounts/templates/accounts/signup.html`

**Intent**: Converge the surviving auth pages onto the base so the repo ends this slice with one template idiom rather than two.

**Contract**: Each becomes `{% extends "base.html" %}` with a `{% block title %}` and a `{% block content %}` holding its existing body. The form-rendering block is preserved **exactly**, including `{{ form.non_field_errors }}` — its omission was critical finding F1 and its presence must not regress. `landing.html` is deliberately **not** retrofitted; Phase 4 deletes it.

#### 4. Template render coverage

**File**: `tests/accounts/test_login_logout.py`, `tests/accounts/test_registration.py`

**Intent**: The existing suite must keep passing unchanged — that is the retrofit's proof. Review finding F4 warned that a high coverage headline can hide the one uncovered line that matters, and every template the suite never renders is unproven.

**Contract**: No test changes expected in this phase. If the existing `non_field_errors` assertion at `test_login_logout.py:32-33` still passes, the retrofit preserved the load-bearing behavior.

### Success Criteria

#### Automated Verification

- Full suite passes with no test modifications: `uv run pytest`
- The invalid-login error assertion still passes: `uv run pytest tests/accounts/test_login_logout.py::test_login_with_invalid_credentials_shows_error`
- Templates resolve: `uv run python manage.py check`
- Quality gates pass: `/python-quality-gates`

#### Manual Verification

- With `DEBUG=True` in `.env`, the login and signup pages render correctly with their titles intact
- The logout button appears in the header on an authenticated page and is absent on the login page
- Submitting invalid login credentials still displays the "Please enter a correct username and password" error

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Create and list views

### Overview

The slice's actual outcome: a form, two views, two templates, and the repo's first authorization surface — plus the first cross-user negative test proving the PRD's data-isolation guardrail holds.

### Changes Required

#### 1. The trip form

**File**: `trips/forms.py`

**Intent**: Collect name, date, and description. Deliberately exclude `owner` so it can never be supplied by the client.

**Contract**: `TripForm(forms.ModelForm[Trip])` — `ModelForm` subscripts directly, unlike the generic views (`accounts/forms.py:7` shows the pattern). `Meta.model = Trip`, `Meta.fields = ("name", "date", "description")` as a tuple. A `widgets` entry giving `date` a `forms.DateInput(attrs={"type": "date"})` so browsers show a native date picker — this is the repo's first widget override and is justified because a bare text input for a date is a usability failure, not a styling preference.

**No `clean_name()`.** Django already delivers the whitespace rule: `forms.CharField` takes `strip=True` by default (`django/forms/fields.py:276`) and the ModelForm-generated field inherits it, so `to_python` strips whitespace-only input to `""` and `validate()` then raises the `required` error — a `clean_name()` hook would never be reached, and when it *is* reached its input is already stripped. The `accounts/forms.py:16-21` idiom does not transfer: `clean_email()`'s guard runs a duplicate query and is reachable; a `clean_name()` guard is not. Phase 1 has just brought `trips` under `fail_under = 80`, so adding one would plant a permanently uncoverable branch in the newly measured package. The Phase 3 test "blank name re-renders with a field error and creates nothing" passes on the built-in validation unchanged.

#### 2. The views

**File**: `trips/views.py`

**Intent**: A list scoped to the requesting user, and a create view that assigns ownership server-side and confirms the save.

**Contract**: The `TYPE_CHECKING` shim from `accounts/views.py:21-24`, copied with **three** aliases, not two — every base whose django-stubs declaration is generic but whose runtime class is not:

- `_TripListViewBase = ListView[Trip]` (one parameter)
- `_TripCreateViewBase = CreateView[Trip, TripForm]` (two parameters)
- `_SuccessMessageMixinBase = SuccessMessageMixin[TripForm]` — bare `SuccessMessageMixin` in the `else` branch

`SuccessMessageMixin` has the same split personality the shim exists for: `django-stubs/contrib/messages/views.pyi:10` declares `class SuccessMessageMixin(Generic[_F])`, so mypy `--strict` rejects the bare form with `Missing type arguments for generic type "SuccessMessageMixin"  [type-arg]`, while `django/contrib/messages/views.py:4` is a plain class, so `SuccessMessageMixin[TripForm]` raises `TypeError: type 'SuccessMessageMixin' is not subscriptable` at import. The repo has zero `# type: ignore`, so the shim is the only way through. `LoginRequiredMixin` is genuinely non-generic (`mixins.pyi:18`) and must **not** be shimmed.

`TripListView(LoginRequiredMixin, _TripListViewBase)` overrides `get_queryset()` to return `Trip.objects.filter(owner=self.request.user)`. `template_name` may be left to the `trips/trip_list.html` default: `MultipleObjectTemplateResponseMixin` derives the name from `self.object_list.model`, which `get_queryset()` supplies.

`TripCreateView(LoginRequiredMixin, _SuccessMessageMixinBase, _TripCreateViewBase)` sets `form_class = TripForm`, **`template_name = "trips/trip_form.html"`**, `success_url = reverse_lazy("trips:list")`, and a `success_message` confirming the trip was saved (satisfying the US-01 acceptance line at `prd.md:51`). `form_valid()` sets `form.instance.owner = self.request.user` before delegating to `super()`.

**Caution**: `template_name` on the create view is **not** optional — `ListView`'s implicit resolution does not generalize to `CreateView`. With only `form_class` set, `ModelFormMixin.get_form_class()` returns early and never assigns `self.model` (`edit.py:81-89`), `self.object` is `None` (`edit.py:176,180`), and `SingleObjectTemplateResponseMixin.get_template_names()` therefore finds no candidate and re-raises `ImproperlyConfigured`. Setting it explicitly matches `SignUpView` (`accounts/views.py:31`); `model = Trip` plus the default `template_name_suffix = "_form"` would also work. The failure is asymmetric and hides from the happy path: a *valid* POST redirects without rendering, so "a valid POST creates a trip and redirects" passes green while `GET /trips/new/` and every invalid re-render 500.

**Caution**: `LoginRequiredMixin` must precede the shim base in the MRO. This is the repo's first mixin-based protection; S-03 and S-04 will copy whatever lands here, so it is worth being deliberate.

#### 3. URLs

**File**: `trips/urls.py`, `velo_log/urls.py`

**Intent**: Route the two views under a namespace, and include them from the project URLconf.

**Contract**: `app_name = "trips"`, absolute import (`from trips import views`), trailing slashes on every pattern. Names are `list` (at the app's empty path, i.e. `/trips/`) and `create` (at `new/`). Project wiring adds `path("trips/", include("trips.urls"))` to `velo_log/urls.py`, placed so it does not disturb the existing `accounts/`-prefixed ordering hazard at `:39-45`.

#### 4. The list template

**File**: `trips/templates/trips/trip_list.html`

**Intent**: Render the user's trips, and — equally importantly — render a deliberate empty state. `roadmap.md:75` names the empty-draft state as the specific thing S-03 depends on being handled cleanly.

**Contract**: `{% extends "base.html" %}`. A `{% for trip in object_list %}` over a `<ul>` showing each trip's name, date, and description, with an `{% empty %}` clause carrying a plain-English message inviting the user to create their first trip. A link to `{% url 'trips:create' %}`. This is the repo's first `{% for %}` over data and its first `{% empty %}`.

#### 5. The form template

**File**: `trips/templates/trips/trip_form.html`

**Intent**: Render the create form using the established block.

**Contract**: `{% extends "base.html" %}`, mirroring the form-rendering block from `accounts/signup.html:9-20` verbatim — `{% csrf_token %}`, then **`{{ form.non_field_errors }}`**, then the `{% for field in form %}` loop with `label_tag` / field / `errors`. The `non_field_errors` line is non-negotiable per finding F1.

#### 6. Tests

**File**: `tests/conftest.py`, `tests/trips/test_trip_creation.py`, `tests/trips/test_trip_list.py`

**Intent**: Prove the slice works and, critically, prove the isolation guardrail. This is the first cross-user negative test in the repo.

**Contract**: `conftest.py` gains its first real fixtures — an authenticated client and a second user — an addition the S-01 plan explicitly anticipated (`plan.md:83`). Fixtures follow the existing auth idiom: `User.objects.create_user(...)` then `client.login(...)`, never `force_login`.

Creation tests: a valid POST creates a trip owned by the requesting user and redirects to the list; a trip created with an empty description succeeds (the valid-empty-draft case); an invalid POST (blank name) re-renders with a field error and creates nothing; the owner cannot be overridden by POSTing an `owner` field; an unauthenticated POST redirects to login and creates nothing.

List tests: the list shows the user's own trips; **the list does not show another user's trips** (assert against `response.context["object_list"]` as well as the decoded body, so a template-only pass cannot fake it); a user with no trips sees the empty-state text; an unauthenticated GET redirects to login with `?next=`; the success message renders on the list page after a create.

Naming follows `test_<subject>_<expected-outcome>` with verbs from `creates` / `rejects` / `redirects_to` / `shows`. Happy path first, then error and edge cases.

**Caution**: Per finding F2, a test whose name claims an assertion must actually make it — the isolation test must assert the *absence of the other user's trip*, not merely a 200 response.

### Success Criteria

#### Automated Verification

- All new tests pass: `uv run pytest tests/trips/`
- Full suite passes: `uv run pytest`
- Coverage gate met with `trips` in scope: `uv run pytest --cov`
- Type checking passes, including both shim arities: `uv run mypy .`
- No pending model changes: `uv run python manage.py makemigrations --check --dry-run`
- Quality gates pass: `/python-quality-gates`

#### Manual Verification

- With `DEBUG=True`, logging in and visiting `/trips/` shows the empty state
- Creating a trip redirects to the list, shows the flash confirmation, and the trip is visible
- The date field renders a native browser date picker
- Submitting the form with a blank name shows an inline error and does not create a trip
- Logging in as a second user shows that user's own empty list, not the first user's trips
- Visiting `/trips/` while logged out redirects to login, and logging in returns to `/trips/`

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Retire the landing page and claim the site root

### Overview

Flip the post-login destination to the real trip list, delete the placeholder S-01 built for exactly this moment, and stop the bare domain from returning a 404.

### Changes Required

#### 1. Repoint the post-login destination

**File**: `velo_log/settings.py`

**Intent**: Send users to their trip list after login and after signup.

**Contract**: `LOGIN_REDIRECT_URL` at `:137` becomes `"trips:list"`. `SignUpView.success_url` needs no change — it reads the setting at `accounts/views.py:32` and follows automatically.

#### 2. Delete the landing page

**File**: `accounts/views.py`, `accounts/urls.py`, `accounts/templates/accounts/landing.html`

**Intent**: Remove the throwaway. S-01's plan named S-02 as its executioner (`plan.md:57`, `plan-brief.md:63`).

**Contract**: Remove the `landing` view (`accounts/views.py:15-18`) and its now-unused `login_required`, `render`, and `HttpRequest` imports; remove the `landing/` pattern (`accounts/urls.py:8`); delete the template. The logout form it carried already lives in `templates/base.html` from Phase 2 — verify this before deleting, not after.

#### 3. Route the site root

**File**: `velo_log/urls.py`

**Intent**: Turn the bare domain from a 404 into the app's front door without breaking the app-namespace convention every other route follows.

**Contract**: A `RedirectView` at `path("")` targeting the `trips:list` URL name, non-permanent so the destination can change without poisoning browser caches. The canonical list stays at `/trips/`. An unauthenticated visitor to `/` therefore chains: redirect to `/trips/`, then `LoginRequiredMixin` bounces to login with `?next=/trips/`.

#### 4. Re-point the landing tests

**File**: `tests/accounts/test_login_logout.py`

**Intent**: Four tests reference `accounts:landing` and must move to trips targets rather than being dropped — the `?next=` test in particular is the only assertion of that shape in the suite.

**Contract**:
- `test_login_with_valid_credentials_redirects_to_landing` (`:8`) — rename to reflect the trip list and assert the redirect target is `reverse("trips:list")`.
- `test_logout_clears_session_and_landing_requires_login_again` (`:37`) — re-point the post-logout protected-page GET at `trips:list`.
- `test_unauthenticated_landing_redirects_to_login_with_next` (`:52`) — re-point at `trips:list`, preserving the exact `?next=` string assertion.
- `test_authenticated_landing_shows_username` (`:60`) — this asserted the landing page showed the username. Since the base template's header is now the thing that renders authenticated chrome, re-point it at `trips:list` and assert the logout control is present, keeping the test's real intent (authenticated chrome renders) rather than deleting it.

Add a test that `/` redirects to the trip list.

### Success Criteria

#### Automated Verification

- Full suite passes: `uv run pytest`
- No dangling references remain: a repo-wide search for `accounts:landing` and `landing.html` returns nothing
- No unused imports left in `accounts/views.py`: `uv run ruff check .`
- URL configuration resolves: `uv run python manage.py check`
- Coverage gate still met: `uv run pytest --cov`
- Quality gates pass: `/python-quality-gates`

#### Manual Verification

- Logging in lands on the trip list, not the old landing page
- Signing up as a brand-new user lands on the trip list with an empty state
- Visiting `/` while logged in redirects to the trip list
- Visiting `/` while logged out ends at the login page, and logging in from there returns to the trip list
- Logging out from the trip list works and the session is cleared

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 5: Documentation, deferred-work register, and deploy readiness

### Overview

Correct the docs this slice invalidates, create the foundation file that has been advertised but missing since the project started, record the engineering debt so it stops being rediscovered by research, and walk the mandatory pre-migration deploy ritual.

Review finding F7 established that stale agent-facing docs are a defect class, not a nicety: `AGENTS.md` is loaded every session, so a wrong claim actively misdirects the next agent (`impl-review.md:253-254`).

### Changes Required

#### 1. Correct the stale coverage claim

**File**: `AGENTS.md`

**Intent**: The Testing section says coverage runs against `accounts`. That was already wrong before this slice (it covers `accounts` + `velo_log`) and Phase 1 changed it again.

**Contract**: The coverage sentence names all three packages in `[tool.coverage.run] source`. Also add `trips/` to the project-structure notes as the second feature app, and note the new project-level `templates/` directory introduced in Phase 2.

#### 2. Create the missing lessons file

**File**: `context/foundation/lessons.md`

**Intent**: `CLAUDE.md:48` advertises this file and `roadmap.md:146` has a "Lesson: —" placeholder for it, but it has never existed. The eight rules the S-01 review encoded currently live only inline in an archived review that nothing routinely reads.

**Contract**: The eight accumulated rules, each with its source citation and a one-line "why": a test whose name claims an assertion must make it; render `{{ form.non_field_errors }}` in every form template; a high coverage percentage can conceal the one uncovered line that matters; widen `[tool.coverage.run] source` whenever a new package ships; update `AGENTS.md` and roadmap status in the same slice that invalidates them; normalize on write and compare case-insensitively for user-supplied identifiers; never write to `context/archive/`; fix commits precede the commit recording the decisions describing them. Add one lesson this slice earns: **a migration's absence cannot be caught by CI — generate and commit it by hand, and verify with `makemigrations --check --dry-run`.**

#### 3. Engineering Backlog

**File**: `context/foundation/roadmap.md`

**Intent**: Give the queued non-feature work a durable home that is actually read. The roadmap's existing `## Parked` section is for PRD features; engineering debt needs its own table so it is not confused with deliberately deferred product scope.

**Contract**: A new `## Engineering Backlog` section with a table of `Item | Proposed fix | Trigger` — three columns, matching the table below. Every row's trigger must be a condition *this* slice does not already meet; anything already due gets done in Phase 1 (#9) instead of filed. Holding:

| Item | Proposed fix | Trigger |
|---|---|---|
| CI runs no tests, ruff, black, isort, or mypy — only `manage.py check` plus the migration guard Phase 1 added, and only on push to `master` | Add a `pull_request` trigger and a job running `uv run pytest --cov` plus the lint/type gates, before the `railway up` step | Before S-03 — the north star slice adds file upload and map rendering, where a silent regression is most costly |
| Tracker statuses never propagate — GitHub and Linear migrations are documented as one-way with no sync back | Decide whether trackers are authoritative or decorative, and either close them out per slice or note in the roadmap that they are a point-in-time snapshot | Before the next roadmap regeneration |
| `railway.json` must migrate to `.railway/railway.ts` before 2026-12-01 | Convert the start command to the TypeScript config format | By 2026-11-01, after the 2026-09-10 product deadline |
| The `/data/db.sqlite3` restore path has never been exercised | Restore a backup into a scratch environment once, to prove the runbook | Before the deploy following S-03, once real user data exists |
| No structured logging or error tracking — `/healthz/` is the whole observability story | Introduce `LOGGING` config; a trips view 500ing in production is diagnosed only via `railway logs` | When the first production incident is diagnosed by guesswork |
| The `$5` Railway spend alert is flagged un-reverified (`DEPLOY.md:43`) | Re-confirm the alert fires | Next time the Railway dashboard is open |
| `TripForm` accepts a future-dated trip with no validation (found during Phase 3 manual verification) | Decide product intent (block future dates? allow and label as "planned"?) then add `clean_date()` if blocking is the answer | When trip-date semantics are next revisited, e.g. alongside S-03/S-04 |

#### 4. Roadmap slice status

**File**: `context/foundation/roadmap.md`

**Intent**: S-02 still reads `proposed` in three places, and the `Ready for /10x-plan: no` / "Waiting on S-01" note is stale since S-01 is `done`. Status drift is the F7 defect class.

**Contract**: Update the `At a glance` row (`:31`), the slice body `- **Status:**` (`:76`), and the Backlog Handoff row (`:119`) to reflect reality. Bump the frontmatter `updated:` date.

#### 5. Change status

**File**: `context/changes/create-and-list-trips/change.md`

**Intent**: Reflect completion.

**Contract**: `status` advances and `updated` is stamped to the completion date.

#### 6. Deploy ritual

**File**: `DEPLOY.md`

**Intent**: This is the first slice to ship a schema migration to production, so the backup ritual is live for the first time. `infrastructure.md:93` states the rule: never treat "rollback the code" as equivalent to "undo the migration."

**Contract**: **Before** merging to `master`, run `railway service files download /data/db.sqlite3 ./backup-$(date +%Y%m%d-%H%M%S).sqlite3` (`DEPLOY.md:20-28`), keeping the file until `/healthz/` confirms health. Requires an SSH key registered via `railway ssh keys add`. **After** the deploy, append a row to the known-good deployment table (`DEPLOY.md:5-10`) with the deployment ID and commit sha, as S-01 did.

Also **after** the deploy, create the production superuser this environment has never had — no `createsuperuser` step exists in `railway.json`, `DEPLOY.md`, or `deployment-plan.md`, so the admin registered in Phase 1 #8 is currently unreachable in production. Run it once over `railway ssh`, with the credentials stored in the password manager and never in the repo, and add the step to `DEPLOY.md` as a documented one-time task so the next environment rebuild does not lose it.

### Success Criteria

#### Automated Verification

- Full suite passes: `uv run pytest`
- Coverage gate met: `uv run pytest --cov`
- Deploy-mode checks pass locally with `DEBUG=False` and a real `SECRET_KEY`: `uv run python manage.py check --deploy`
- No pending model changes: `uv run python manage.py makemigrations --check --dry-run`
- Quality gates pass: `/python-quality-gates`
- `context/foundation/lessons.md` exists and is non-empty

#### Manual Verification

- Pre-deploy SQLite backup downloaded and retained
- `railway logs` shows the migration ran and gunicorn is serving
- `/healthz/` over HTTPS returns `{"status": "ok"}`
- The full primary flow works in production: register → log in → create a trip → see it in the list
- A second production account sees only its own trips
- `DEPLOY.md`'s known-good table has a new row for this deploy
- A production superuser exists, the admin is reachable over HTTPS, and `DEPLOY.md` documents the one-time step

**Implementation Note**: This is the final phase. Confirm production verification succeeded before archiving the change.

---

## Testing Strategy

### Unit Tests

- **Model** (`tests/trips/test_trip_model.py`): persistence with an owner, optional description, `-date` ordering, deterministic same-date tiebreak. The repo's first tests that bypass `client`.
- **Form** validation is exercised through the view tests rather than in isolation, matching the existing convention where every `accounts` test goes through `client`.

### Integration Tests

- **Creation** (`tests/trips/test_trip_creation.py`): valid create → redirect + persisted with correct owner; empty description accepted; blank name rejected with a field error and nothing created; a POSTed `owner` field cannot override server-side assignment; unauthenticated POST redirects and creates nothing.
- **List** (`tests/trips/test_trip_list.py`): own trips shown; **another user's trips absent from both `object_list` and the rendered body**; empty state text for a user with no trips; unauthenticated GET redirects to login with `?next=`; success message renders after create.
- **Regression** (`tests/accounts/`): the existing 11 tests must pass unchanged through Phase 2's retrofit, then have their four landing references re-pointed in Phase 4.

The cross-user isolation test is the single most important test in this slice — it is the only PRD *guardrail* S-02 touches (`prd.md:43`), it has no precedent to copy, and S-03 and S-04 both build directly on the pattern it establishes.

### Manual Testing Steps

Set `DEBUG=True` in the local `.env` first — Secure-flagged cookies are dropped over plain HTTP and make login look broken (`settings.py:140-149`).

1. Register a new user; confirm the redirect lands on an empty trip list with its empty-state message.
2. Create a trip with all three fields; confirm the flash confirmation, the redirect to the list, and the trip's presence.
3. Create a trip with the description left blank; confirm it saves and displays.
4. Submit the form with a blank name; confirm the inline error and that nothing was created.
5. Create a second trip with an earlier date; confirm it sorts below the newer one.
6. Log out, register a second user, and confirm their list is empty — the first user's trips must not appear.
7. Log out and visit `/trips/` directly; confirm the login redirect and that logging in returns you there.
8. Visit `/` logged in and logged out; confirm both resolve sensibly.

## Performance Considerations

Negligible at this scale — the PRD describes a near-private app with a handful of trips per user, and its only NFR concerns the S-03 map view not failing silently. Two points worth noting anyway: the list view's `filter(owner=...)` hits an FK column that Django indexes automatically, so no explicit index is needed; and no pagination is added, consistent with FR-012 being parked. Should trip counts ever grow, pagination is the first thing to add, and `Meta.ordering`'s id tiebreak already makes it safe.

## Migration Notes

This is the repo's first schema migration against production, and the deploy path is unforgiving:

- `railway.json` chains `collectstatic --noinput && migrate && gunicorn`, so a failing migration aborts before gunicorn starts. A bad migration is a **hard outage**, not a degraded deploy.
- There is no atomic rollback. Recovery is redeploy-by-ID from `DEPLOY.md:5-10`, and `deployment-plan.md:112` calls that manual record "the actual mitigation."
- The pre-migration backup at `DEPLOY.md:20-28` is mandatory and human-triggered — it is the only real safety net.
- The restore path has never been exercised against production (`deployment-plan.md:150`). This deploy is the first that might need it, which is why exercising it is on the Engineering Backlog.
- `RAILWAY_RUN_UID=0` is required for the app to write the root-owned Volume mount, and misconfiguration **fails silently** (`infrastructure.md:59`).
- The migration is purely additive — one new table, no changes to existing tables — so there is no data backfill and no destructive step.

## References

- Internal research: `context/changes/create-and-list-trips/research.md`
- Roadmap slice S-02: `context/foundation/roadmap.md:66-76`
- PRD requirements: `context/foundation/prd.md:66` (FR-003), `:71` (FR-006), `:43` (isolation guardrail), `:96` (empty draft)
- Structural template for this plan: `context/archive/2026-08-22-user-registration-login/plan.md`
- Findings this slice must not repeat: `context/archive/2026-08-22-user-registration-login/reviews/impl-review.md`
- The CBV generic shim to copy: `accounts/views.py:21-24`
- The form-rendering block to mirror: `accounts/signup.html:9-20`
- The logout form to carry forward: `accounts/landing.html:9-12`
- Deploy ritual: `DEPLOY.md:20-28`, `DEPLOY.md:5-10`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Trip model, app scaffold, and the first migration

#### Automated

- [x] 1.1 Migration is generated and committed — 84256db
- [x] 1.2 No pending model changes (`makemigrations --check --dry-run`) — 84256db
- [x] 1.3 Migration applies cleanly to a fresh database — 84256db
- [x] 1.4 Model tests pass — 84256db
- [x] 1.5 Full suite still passes — 84256db
- [x] 1.6 `trips` appears in the coverage report — 84256db
- [x] 1.7 No `models.W042` or other system-check warnings — 84256db
- [x] 1.8 Quality gates pass — 84256db
- [x] 1.9 No `trips/tests.py` exists — 84256db
- [x] 1.10 CI gate carries the migration check — 84256db
- [x] 1.11 Lint passes with the `S608` ignore removed and `main.py` gone — 84256db

#### Manual

- [x] 1.12 Trip creates and reads back with expected ordering in the shell — 84256db
- [x] 1.13 Django admin loads and lists Trip — 84256db

### Phase 2: Base template and shared chrome

#### Automated

- [x] 2.1 Full suite passes with no test modifications — 5bd02ef
- [x] 2.2 The invalid-login error assertion still passes — 5bd02ef
- [x] 2.3 Templates resolve (`manage.py check`) — 5bd02ef
- [x] 2.4 Quality gates pass — 5bd02ef

#### Manual

- [x] 2.5 Login and signup pages render correctly with titles intact — 5bd02ef
- [x] 2.6 Logout button present on authenticated pages, absent on login — 5bd02ef
- [x] 2.7 Invalid login still displays the non-field error — 5bd02ef

### Phase 3: Create and list views

#### Automated

- [x] 3.1 All new trips tests pass — 670b789
- [x] 3.2 Full suite passes — 670b789
- [x] 3.3 Coverage gate met with `trips` in scope — 670b789
- [x] 3.4 Type checking passes, including both shim arities — 670b789
- [x] 3.5 No pending model changes — 670b789
- [x] 3.6 Quality gates pass — 670b789

#### Manual

- [x] 3.7 Empty state shows on a fresh account — 670b789
- [x] 3.8 Creating a trip redirects, confirms, and displays — 670b789
- [x] 3.9 Date field renders a native picker — 670b789
- [x] 3.10 Blank name shows an inline error and creates nothing — 670b789
- [x] 3.11 A second user sees only their own list — 670b789
- [x] 3.12 Logged-out access redirects to login and returns after auth — 670b789

### Phase 4: Retire the landing page and claim the site root

#### Automated

- [x] 4.1 Full suite passes — 5041b7a
- [x] 4.2 No dangling `accounts:landing` or `landing.html` references — 5041b7a
- [x] 4.3 No unused imports in `accounts/views.py` — 5041b7a
- [x] 4.4 URL configuration resolves — 5041b7a
- [x] 4.5 Coverage gate still met — 5041b7a
- [x] 4.6 Quality gates pass — 5041b7a

#### Manual

- [x] 4.7 Login lands on the trip list — 5041b7a
- [x] 4.8 Signup lands on the trip list with an empty state — 5041b7a
- [x] 4.9 `/` while logged in redirects to the trip list — 5041b7a
- [x] 4.10 `/` while logged out ends at login and returns after auth — 5041b7a
- [x] 4.11 Logout from the trip list clears the session — 5041b7a

### Phase 5: Documentation, deferred-work register, and deploy readiness

#### Automated

- [x] 5.1 Full suite passes — 9a5070b
- [x] 5.2 Coverage gate met — 9a5070b
- [x] 5.3 `manage.py check --deploy` passes with `DEBUG=False` — 9a5070b
- [x] 5.4 No pending model changes — 9a5070b
- [x] 5.5 Quality gates pass — 9a5070b
- [x] 5.6 `context/foundation/lessons.md` exists and is non-empty — 9a5070b

#### Manual

- [ ] 5.7 Pre-deploy SQLite backup downloaded and retained
- [ ] 5.8 `railway logs` shows migration ran and gunicorn serving
- [ ] 5.9 `/healthz/` returns `{"status": "ok"}` over HTTPS
- [ ] 5.10 Full primary flow works in production
- [ ] 5.11 A second production account sees only its own trips
- [ ] 5.12 `DEPLOY.md` known-good table has a new row
- [ ] 5.13 Production superuser exists, admin reachable, one-time step documented
