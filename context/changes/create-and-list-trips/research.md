---
date: 2026-08-23T11:59:16+02:00
researcher: Miłosz Jarzynka
git_commit: 9e84e5cec8c0f75d123d8763cbeb49a60650597b
branch: feat/create-and-list-trips
repository: VeloLog
topic: "Foundations for implementing S-02 create-and-list-trips, compliant with roadmap, foundation docs, and DEPLOY.md"
tags: [research, codebase, trips, models, migrations, authorization, deploy, coverage]
status: complete
last_updated: 2026-08-23
last_updated_by: Miłosz Jarzynka
---

# Research: Foundations for S-02 `create-and-list-trips`

**Date**: 2026-08-23T11:59:16+02:00
**Researcher**: Miłosz Jarzynka
**Git Commit**: `9e84e5cec8c0f75d123d8763cbeb49a60650597b`
**Branch**: `feat/create-and-list-trips` (no upstream — not pushed, so no GitHub permalinks in this document)
**Repository**: VeloLog

## Research Question

Give solid foundations to start planning the implementation of S-02 (`create-and-list-trips`), verified against `context/foundation/roadmap.md`, the rest of `context/foundation/`, and `DEPLOY.md` so the resulting plan is compliant.

## Summary

S-02 is a small feature with an outsized number of firsts. The user-visible scope is genuinely modest — one model, one form, one create view, one list view, two templates — and **every dependency it needs is already installed**; no `uv add` is required.

But S-02 is the first slice in this repo to cross five thresholds that nothing before it has crossed:

1. **The first Django model and the first migration.** `accounts/` has no `models.py` and no `migrations/` at all. The only migrations that have ever run against production are Django's contrib ones.
2. **The first real authorization surface.** The PRD's data-isolation guardrail has never been implemented or tested — no queryset in the repo is scoped to a user, and no test creates two users.
3. **The first production schema migration**, which triggers `DEPLOY.md`'s mandatory pre-migration backup ritual and runs unattended inside the Railway start command.
4. **The first list/empty-state UI**, in a repo with no base template, no CSS, and no `{% for %}`/`{% empty %}` anywhere.
5. **The moment the stock-`User` decision becomes permanent**, because `Trip.owner`'s FK is the first thing to point at the identity model.

Two compliance traps stand out. First, **CI cannot catch a missing migration**: `.github/workflows/deploy.yml` gates only on `manage.py check`, which passes with a model/schema mismatch, and `railway.json` then runs `migrate` before gunicorn — so a forgotten migration file ships green and surfaces as production 500s. Second, **`trips/` is invisible to the coverage gate** unless `"trips"` is added to `[tool.coverage.run] source` (`pyproject.toml:63`); as written, `fail_under = 80` would pass no matter how untested the new app is.

S-02 also inherits an explicit cleanup obligation: the `accounts.landing` page was built as a throwaway `LOGIN_REDIRECT_URL` target and the S-01 plan states it should be deleted once S-02 ships a real trip list. Retiring it moves the logout control, repoints one setting, and forces a decision about the currently-404 site root `/`.

## Detailed Findings

### 1. The contract — what S-02 must deliver

| Source | Requirement |
|---|---|
| `context/foundation/roadmap.md:68` | "User can create a trip with a name, date, and description, and see it appear in a list of their own trips." |
| `context/foundation/prd.md:66` | FR-003 create a trip with name, date, description — must-have |
| `context/foundation/prd.md:71` | FR-006 view a list of their own trips — must-have, **explicitly scoped to a minimal list, no filter/sort** (FR-012 is parked) |
| `context/foundation/prd.md:54` | US-01 acceptance: "The trip appears in the user's trip list after creation" |
| `context/foundation/prd.md:43` | Guardrail: "One authenticated user can never read, modify, or delete another user's private trips under any circumstance." |
| `context/foundation/prd.md:96` | Business logic: "A trip with no uploaded file is a valid empty draft" |
| `context/foundation/roadmap.md:75` | S-02 risk: the empty-draft state must be tolerated cleanly **before** S-03 builds upload/map on top |
| `context/foundation/prd.md:104` | All trips private in v1; the FR-009 visibility toggle is parked (`roadmap.md:133`) |

Prerequisite S-01 is `done` (`roadmap.md:30`, `:146`), so S-02 is unblocked. Deadline pressure is real: `prd.md:15` sets `hard_deadline: 2026-09-10` with `after_hours_only: true`, and S-02 is on the critical path to the S-03 north star.

Explicitly **out** of S-02 by roadmap decomposition: edit and delete are S-04 (`roadmap.md:33`), and any GPX/upload/map work is S-03 (`roadmap.md:32`).

### 2. Pattern template — the `accounts/` app

`accounts/` is the only feature app and therefore the house style. Its full file list is `__init__.py` (empty, no `__all__`), `apps.py`, `forms.py`, `urls.py`, `views.py`, and `templates/accounts/{landing,login,signup}.html`. There is **no `models.py`, no `admin.py`, no `migrations/`, no `services.py`** — and no service layer anywhere in the repo; logic lives in the form and the view.

**App config** — `accounts/apps.py:1-6` sets `default_auto_field = "django.db.models.BigAutoField"`. There is no project-level `DEFAULT_AUTO_FIELD`, so `trips/apps.py` must set it too or the new model silently gets an `AutoField` PK and triggers `models.W042`. Registration is the bare label `"accounts"` at `velo_log/settings.py:45`, relying on app-config auto-discovery.

**Forms** — `accounts/forms.py:16-21` establishes the validation idiom: a per-field `clean_<field>()` that normalizes, then checks, then returns the cleaned value; `ValidationError` imported from `django.core.exceptions`, not `forms`; plain-English capitalized messages with a terminating period; no i18n. `Meta.fields` is a tuple. **There is zero widget/attrs customization anywhere** — no `class=`, no `label=`, no `help_text=`. A `date` input on `TripForm` would be the first justified widget override in the repo.

**Views** — mixed style: a function view with the `@login_required` **decorator** (`accounts/views.py:15-18`) and a CBV (`accounts/views.py:27`). `LoginRequiredMixin` appears nowhere, so CBV protection has no in-repo precedent. Redirects use `success_url = reverse_lazy(settings.LOGIN_REDIRECT_URL)` (`accounts/views.py:32`) — a settings-sourced URL *name*, never a hardcoded path, and never `get_success_url()`. `get_absolute_url` does not exist (no models yet). The messages framework is fully wired (`settings.py:43`, `:55`, `:70`) but **has zero consumers** — S-02 could be the first, with no config change.

**mypy-strict CBV shim — the single most important pattern to copy** (`accounts/views.py:21-24`):

```python
if TYPE_CHECKING:
    _SignUpViewBase = CreateView[User, SignUpForm]
else:
    _SignUpViewBase = CreateView
```

Django's generic CBVs have no `__class_getitem__`, so subscripting them raises at import time; django-stubs needs the subscript. Arities differ: `CreateView[_M, _ModelFormT]` takes two parameters, **`ListView[_M]` takes one**. So S-02 needs `_TripListViewBase = ListView[Trip]` and `_TripCreateViewBase = CreateView[Trip, TripForm]` behind the same shim. Note `ModelForm`/`UserCreationForm` *can* be subscripted directly (`accounts/forms.py:7`) — the shim is only for the view classes.

The repo has **zero `# type: ignore` and zero `# noqa`**. Docstrings are one-line Google-style on every public callable (retro-fixed as review finding F8); there are no module-level docstrings in `accounts/*.py`. **There is no logging anywhere** — no `LOGGING` dict, no `config/logging.yaml`, no `config/` directory. The global standard's logging section is un-instantiated in this project, and `roadmap.md:46` acknowledges the gap.

**URLs** — `accounts/urls.py:5` sets `app_name = "accounts"`; imports are absolute (`from accounts import views`), patterns carry trailing slashes, and no `<int:pk>` converter exists anywhere yet (trip detail/edit in S-04 will be the first). Project wiring is `path("accounts/", include("accounts.urls"))` at `velo_log/urls.py:39`, with `login`/`logout` deliberately mounted unnamespaced at project level (`velo_log/urls.py:41-45`) because `LOGIN_URL = "login"` is a bare name.

Two hazards recorded in the S-01 review: **the site root `/` is unrouted and 404s**, and `include("accounts.urls")` at `:39` precedes the concrete `accounts/login/` route, so an app-level `login/` route would silently shadow the project-level `name="login"`.

### 3. Registration points and configuration constraints

- **`INSTALLED_APPS`** (`velo_log/settings.py:38-46`): append `"trips"` after `"accounts"` (`:45`). Apps live at the repo root per `AGENTS.md`.
- **Templates** (`velo_log/settings.py:64-65`): `"DIRS": []` with `"APP_DIRS": True`. Templates go at `trips/templates/trips/*.html`. Django's `ListView`/`CreateView` defaults (`trips/trip_list.html`, `trips/trip_form.html`) match this layout for free.
- **Static** (`velo_log/settings.py:124-130`): no `STATICFILES_DIRS`, so a CSS file would go at `trips/static/trips/*.css`. `CompressedManifestStaticFilesStorage` is unforgiving — a `{% static %}` reference to a file missing from the manifest raises at render time in production, not at deploy time.
- **Database** (`velo_log/settings.py:85`): `env("DB_PATH", default=str(BASE_DIR / "db.sqlite3"))` — local repo-root SQLite, production `/data/db.sqlite3` on the Railway Volume.
- **Timezone**: `USE_TZ = True` (`settings.py:118`). A trip date should be a `DateField`, not `DateTimeField`, to avoid timezone ambiguity on a user-entered calendar date — and the PRD asks for a "date" (`prd.md:66`).
- **Auth redirects** (`velo_log/settings.py:136-138`): `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "accounts:landing"`, `LOGOUT_REDIRECT_URL = "login"` — all URL *names*.
- **Local-dev gotcha** (`settings.py:140-149`): `SECURE_SSL_REDIRECT` and Secure-flagged cookies activate whenever `DEBUG` is falsy. Browsers silently drop Secure cookies over the plain-HTTP dev server, making login look broken; manual verification requires `DEBUG=True` in the local `.env`. Django's test `Client` is unaffected, but note that any view test run in a `DEBUG=False` environment would get a 301 to `https://`.
- **`MEDIA_ROOT` / `MEDIA_URL` do not exist at all** — no media config, no `STORAGES["default"]`. Not S-02's problem, but worth knowing that S-03 starts from zero here and must land uploads under the Volume mount (`roadmap.md:87`).
- **Dependencies** (`pyproject.toml:7-12`): `django`, `django-environ`, `gunicorn`, `whitenoise`. **Everything S-02 needs is already present**; nothing GPX-, geo-, or image-related exists yet.

### 4. First-migration territory

S-02 is the repo's first model and first migration, and the S-01 review confirms the current absence is intentional, not an oversight: *"Missing `models.py` / `admin.py` / `migrations/` is correct, not a defect — the app declares no models"* (`context/archive/2026-08-22-user-registration-login/reviews/impl-review.md:361-363`). That same review names `makemigrations --check --dry-run` as the established verification command — S-02 inverts its meaning from "expect no changes" to "expect a committed migration that leaves no changes pending."

**The `AUTH_USER_MODEL` decision is now locked.** S-01 deliberately kept stock `django.contrib.auth.models.User` — decided in the plan (`plan.md:37`), re-litigated in review finding F5, and accepted as residual risk on the grounds that *"VeloLog is a near-private app for a very small number of known users at low QPS"* (`impl-review.md:196-207`). The review also flagged the closing window: *"Django's docs call swapping the user model after the first migration 'significantly more difficult'. The project is greenfield with no production data, so this is the last cheap moment to decide"* (`impl-review.md:178-180`). **S-02's migration is that first migration.** `Trip.owner` should be a `ForeignKey` to `settings.AUTH_USER_MODEL` (the portable form) against stock `auth.User`. A recorded blind spot remains: *"Whether S-02+ actually need per-user profile fields is still unknown"* (`impl-review.md:195`).

### 5. Data isolation — the first real authorization surface

This is the highest-risk part of S-02, because it is the only PRD *guardrail* the slice touches and it has **no precedent to copy**.

- The requirement is stated three times: `prd.md:43`, `prd.md:105`, and `context/foundation/shape-notes.md:44`.
- S-01's review dismissed authorization as trivially complete for its own scope: *"`landing` is the only view needing protection and has `@login_required`"* (`impl-review.md:353-355`).
- **No queryset anywhere in the repo is scoped to a user.** No `filter(owner=...)`, no `get_queryset()` override, no object-level permission check.
- **No test anywhere creates two users.** The suite has no `user2`/`other_user`, no 403/404-on-foreign-object assertion, and no assertion against a context queryset or `object_list`.

So S-02 must establish, from scratch: an owner FK, a `get_queryset()` scoped to `self.request.user` on the list view, owner assignment on create (`form_valid` setting `form.instance.owner`, so owner is never client-supplied), and the first cross-user negative test. Because S-03 and S-04 both build directly on this (`roadmap.md:84`, `:95`), a weak isolation pattern here propagates into every later slice.

### 6. Test conventions, and what has no precedent

Layout is `tests/` at the repo root with **one subpackage per app**, each a real package with an empty `__init__.py`: `tests/__init__.py`, `tests/conftest.py`, `tests/test_smoke.py`, `tests/accounts/{__init__.py,test_registration.py,test_login_logout.py}`. S-02 → `tests/trips/__init__.py` + `tests/trips/test_*.py`. Files are feature-scoped (`test_registration.py`), not module-mirroring (`test_views.py`).

`tests/conftest.py` is **one line — a module docstring, zero fixtures**. The S-01 plan sanctioned adding fixtures later: *"Keep it minimal; add fixtures as later phases need them"* (`plan.md:83`). So a logged-in-client fixture and a second-user fixture would be the file's first real contents — an addition the prior plan explicitly anticipated.

Style, from 11 existing tests: plain module-level functions (no classes), `@pytest.mark.django_db` **per test** (no module-level `pytestmark`, no autouse), the built-in `client: Client` fixture, `User` imported directly rather than the `django_user_model` fixture, URLs always via `reverse("namespace:name")`, full type annotations (`-> None`) for mypy strict, and an arrange/act/assert body separated by blank lines. Authentication is `User.objects.create_user(...)` then `client.login(username=..., password=...)` — **never `force_login`** — with `"correct-horse-battery-staple"` as the canonical test password. None of Django's `TestCase` assertion helpers are used; assertions inspect `response.status_code`, `response.headers["Location"]` compared against `reverse()`, `client.session`, `response.context["form"].errors[...]`, decoded body substrings, and `.count()`/`.exists()` on the DB.

Naming: `test_<subject>_<expected-outcome>`, long and explicit, verbs from `creates` / `rejects` / `redirects_to` / `shows` / `clears`. Happy path first, then error and edge cases.

**Coverage is the compliance trap.** `pyproject.toml:63` reads `source = ["accounts", "velo_log"]` with `fail_under = 80` at `:67`. `trips` is **not** in scope — without adding it, the new app's code is unmeasured and the gate passes regardless. Widening `source` was itself review finding F10 (`impl-review.md:308-321`), so the precedent for doing it is explicit. Also note `[tool.pytest.ini_options]` has `python_files = ["tests.py", "test_*.py"]` (`pyproject.toml:60`) — a `startapp`-generated `trips/tests.py` would be **collected**, and since the `S101` assert-exemption key is `"tests/**"` (`pyproject.toml:44`), an app-local `tests.py` would fail ruff. Delete it.

**No precedent exists for:** any conftest fixture; two-user isolation assertions; 404-on-foreign-object; asserting on `object_list` or a context queryset; and unit tests of a model or form in isolation (every existing test goes through `client`).

### 7. Templates and UI — mostly greenfield

Three templates exist, all under `accounts/templates/accounts/`, and **each is a complete standalone HTML5 document**: no `base.html`, no `{% extends %}`, no `{% block %}`, no `{% include %}`, no `{% load %}`. The `<head>` is two lines (charset + title); titles follow `"<Page> — VeloLog"` with an em dash. There is no `<nav>`, no `<header>`, no `<footer>`, and no viewport meta tag.

**There is no CSS of any kind** — no `<style>`, no stylesheet link, no framework, and not a single `class=` attribute in any template. Zero CSS/JS files exist in app source. The S-01 plan set this deliberately: *"No CSS framework or visual styling beyond minimal semantic HTML"* (`plan.md:41`).

The form-rendering block is identical in both form templates and must be mirrored (`accounts/signup.html:9-20`):

```django
<form method="post">
    {% csrf_token %}
    {{ form.non_field_errors }}
    {% for field in form %}
        <p>
            {{ field.label_tag }}
            {{ field }}
            {{ field.errors }}
        </p>
    {% endfor %}
    <button type="submit">Sign up</button>
</form>
```

`{{ form.non_field_errors }}` is **load-bearing** — its omission was critical review finding F1, which shipped to `master` with all gates green and rendered a blank form on invalid login. Its absence in `signup.html` was called *"a latent version of the same bug that will surface the first time a non-field validator is added"* (`impl-review.md:67-68`). Any new form template must include it.

Logout is a POST form with `{% csrf_token %}`, not a link (`accounts/landing.html:9-12`) — required by Django ≥4.1.

**No precedent exists for:** flash-message rendering (framework wired, never rendered); any `{% for %}` over data or any `{% empty %}` clause; any `<ul>`, `<ol>`, or `<table>`. The trip list's loop and its empty state are both new ground — and per `roadmap.md:75` the empty state is the specific thing S-03 depends on being handled cleanly.

### 8. Deploy compliance (`DEPLOY.md` + `infrastructure.md`)

S-02 is the first slice to ship a schema migration to production, so this ritual is live for the first time.

- **Migrations run unattended on every deploy.** `railway.json` has a single `deploy.startCommand`: `collectstatic --noinput && migrate && gunicorn velo_log.wsgi`. Chained with `&&`, so a failing migration aborts before gunicorn starts — a bad migration is a **hard outage, not a degraded deploy**. There is no `healthcheckPath`, so Railway does not gate the deploy on `/healthz/`.
- **Backup before the migration is mandatory.** `DEPLOY.md:20-28`: `railway service files download /data/db.sqlite3 ./backup-$(date +%Y%m%d-%H%M%S).sqlite3`, to be run *"immediately before any deploy that includes a migration"*, keeping the file until `/healthz/` confirms health. Requires an SSH key registered via `railway ssh keys add`. `infrastructure.md:93` states the rule as: never treat "rollback the code" as equivalent to "undo the migration."
- **The restore path has never been exercised** — `context/changes/deployment/deployment-plan.md:150` records that upload/restore was deliberately not run against production. S-02's deploy is the first one that might need it.
- **There is no atomic rollback.** Recovery is redeploy-by-ID from the known-good table in `DEPLOY.md:5-10`; `deployment-plan.md:112` calls that manual record *"the actual mitigation."* After a successful deploy, append a row — as S-01 did (`DEPLOY.md:10`, commit `cf364ea`).
- **Verification** is `railway logs` (migration ran, gunicorn serving) plus `/healthz/` over HTTPS returning `{"status": "ok"}`. `/healthz/` (`velo_log/urls.py:25-33`) does a real DB write→read→delete round-trip via `SessionStore` — deliberately, as the mitigation for the silent-volume-write-failure risk (`infrastructure.md:89`). It takes no dependency on any app model, so a `trips` model does not affect it. Local pre-check: `manage.py check --deploy` with `DEBUG=False` and a real `SECRET_KEY`.
- **`RAILWAY_RUN_UID=0`** is required for the app to write the root-owned Volume mount, and misconfiguration **fails silently** (`infrastructure.md:59`, `deployment-plan.md:102`).
- Open deploy items to leave alone but not be surprised by: `railway.json` must migrate to `.railway/railway.ts` before 2026-12-01 (`deployment-plan.md:148`), and the $5 spend alert is flagged un-reverified (`DEPLOY.md:43`).

### 9. CI reality — the gate is weaker than it looks

`.github/workflows/deploy.yml` is the only workflow. It triggers on `push` to `master` **only** — no `pull_request`, no `workflow_dispatch` — so nothing runs on a feature branch, and the first CI execution of `trips` code is the same run that deploys it. Its steps are checkout → setup-uv → `uv sync --locked` → **"Django check (merge gate)"** running `uv run python manage.py check` with a throwaway `SECRET_KEY` → `railway up`.

Consequences for S-02:

- **Tests, ruff, black, isort, and mypy do not run in CI at all.** They are local-only gates via `/python-quality-gates`.
- **A missing migration file would pass CI.** `manage.py check` does not detect a model/schema mismatch, and there is no `makemigrations --check --dry-run` step. The migration would then not exist to run, and the app would 500 with `no such column`. Generating and committing the migration is entirely on the implementer.
- `models.W042` is a warning, so it would not fail the gate either — another reason `trips/apps.py` must set `default_auto_field` explicitly.
- `uv sync --locked` means any `uv add` must have its `uv.lock` change committed, or CI fails at install. (S-02 should need no new dependency.)

The S-01 review already queued this as out-of-scope-but-known: *"gates deploys on bare `manage.py check` only — no `pytest`, `ruff`, or `mypy`, despite all four now being configured"* (`impl-review.md:338-341`).

### 10. The disposable landing page, `LOGIN_REDIRECT_URL`, and the site root

The S-01 plan built `accounts.landing` purely to give `LOGIN_REDIRECT_URL` a target, and named S-02 as its executioner: *"The landing page is intentionally throwaway; it should be deleted once S-02 (`create-and-list-trips`) ships a real trip list as the login destination"* (`plan-brief.md:63`; same at `plan.md:57`).

Retiring it is a small but multi-file operation: repoint `LOGIN_REDIRECT_URL` (`settings.py:137`) at the trip list, and `SignUpView.success_url` follows automatically since it reads that setting (`accounts/views.py:32`). Then remove `accounts/urls.py:8`, `accounts/views.py:15-18`, `accounts/templates/accounts/landing.html`, and the tests referencing `accounts:landing` — including the `?next=` redirect test, which is the only existing assertion of that shape and should be re-pointed at a trips view rather than dropped.

Two consequential side effects: **deleting `landing.html` removes the only logout affordance in the app**, so the trip list must carry the POST logout form forward; and the currently-404 site root `/` (`impl-review.md:328-329`) is now plausibly the trip list's home. Whether S-02 claims `path("")` is a plan-level decision with no precedent to copy.

### 11. Documentation obligations S-02 inherits

Review finding F7 established that stale agent-facing docs are a defect class, not a nicety: *"`AGENTS.md` is the agent-facing instruction file loaded every session, so the next agent is actively told to re-wire tooling that already exists"* (`impl-review.md:253-254`). Live instances right now:

- **`AGENTS.md` is already stale**: it says coverage runs against `accounts`, but `pyproject.toml:63` covers `accounts` + `velo_log` — and S-02 will change this line again.
- **`roadmap.md` still shows S-02 as `proposed`** (`:31`, `:76`) with `Ready for /10x-plan: no` / "Waiting on S-01" (`:119`), even though S-01 is `done`. The F7 precedent treats change.md-vs-roadmap status drift as a defect.
- **`context/foundation/lessons.md` does not exist**, despite being advertised at `CLAUDE.md:48` and having a "Lesson: —" placeholder at `roadmap.md:146`. The lessons below live only inline in the S-01 review.
- **Issue trackers**: GitHub `#2` and Linear `10X-2`, labelled `roadmap` + `type:slice` + `status:proposed`. Both migrations are documented as **one-way with no sync back** (`github-issues-migration.md:13-15`), and S-01's ship empirically did not touch either tracker. Propagating `status:done` is unowned manual work with no documented procedure. Landing S-02 also clears the `blockedBy` state on S-03 and S-04 in Linear (`linear-issues-migration.md:125`).

`change.md` was missing the `**Tracking:**` line that S-01's carried; it has been added as part of this research pass, along with `status: preparing`.

### 12. Plan-structure precedent (for `/10x-plan`)

S-01's `plan.md` (335 lines) ran: Overview → Current State Analysis (every bullet citing `file:line`) → Desired End State + "Verify via:" commands → Key Discoveries → **What We're NOT Doing** → Implementation Approach → Critical Implementation Details → 3 phases → Testing Strategy (unit / integration / manual steps) → Performance Considerations → Migration Notes → References → Progress checkbox ledger.

Each phase used the same inner skeleton: Overview → `Changes Required:` as numbered items each with **File / Intent / Contract** (+ optional **Caution**) → `Success Criteria:` split into `Automated Verification:` (exact shell commands) and `Manual Verification:` (browser steps) → and a verbatim closing note pausing for human confirmation of manual testing before the next phase.

The ledger convention (`plan.md:291`): `- [ ]` pending, `- [x]` done, append `" — <commit sha>"` when a step lands, never rename step titles. Steps are numbered `<phase>.<n>`. In practice **one commit per phase** (`c797e2e`, `1ea8d32`, `7b284c4`), then a close-out commit, then review fixes one-finding-one-commit on a separate branch.

A companion `plan-brief.md` carried a 9-row **decision / choice / one-sentence-why** table, scope in/out bullets, a phases-at-a-glance table with per-phase key risk, prerequisites, estimated effort, and open risks.

Worth reusing from S-01's ordering rationale (`plan.md:53`): put the piece with real validation logic before the pieces that are nearly configuration-only, and pull a later phase's dependency forward when an earlier phase's settings reference needs it to resolve.

## Code References

- `velo_log/settings.py:38-46` — `INSTALLED_APPS`; append `"trips"` after `:45`
- `velo_log/settings.py:64-65` — `"DIRS": []` + `"APP_DIRS": True` → app-namespaced templates only
- `velo_log/settings.py:85` — `DB_PATH` env resolution for the Volume-mounted SQLite
- `velo_log/settings.py:124-130` — static config; no `STATICFILES_DIRS`, manifest storage
- `velo_log/settings.py:136-138` — `LOGIN_URL` / `LOGIN_REDIRECT_URL` / `LOGOUT_REDIRECT_URL` as URL names
- `velo_log/settings.py:140-149` — prod-only HTTPS/cookie hardening; the `DEBUG=True` local-dev caveat
- `velo_log/urls.py:25-33` — `healthz` write/read/delete round-trip (deploy verification probe)
- `velo_log/urls.py:36-46` — URL wiring; no root route; the `include`-before-`login/` ordering hazard
- `accounts/apps.py:1-6` — `default_auto_field` per AppConfig (no project default exists)
- `accounts/forms.py:7-21` — `ModelForm` subscripting, `clean_<field>` normalize-check-return idiom
- `accounts/views.py:15-18` — `@login_required` FBV pattern
- `accounts/views.py:21-24` — **the `TYPE_CHECKING` CBV generic shim to copy**
- `accounts/views.py:32` — `success_url = reverse_lazy(settings.LOGIN_REDIRECT_URL)`
- `accounts/urls.py:5-10` — `app_name` namespace + absolute view import
- `accounts/signup.html:9-20` — the form-rendering block, including load-bearing `non_field_errors`
- `accounts/landing.html:9-12` — POST logout form (must survive the landing page's deletion)
- `pyproject.toml:58-60` — pytest config; `tests.py` is collected, no `testpaths`
- `pyproject.toml:62-67` — **`coverage source` excludes `trips`; `fail_under = 80`**
- `pyproject.toml:50-56` — `mypy strict` + django-stubs plugin
- `railway.json` — `collectstatic && migrate && gunicorn` start command
- `.github/workflows/deploy.yml:20-23` — the only merge gate: `manage.py check`
- `tests/conftest.py:1` — a single docstring; zero fixtures
- `tests/accounts/test_login_logout.py:8-17` — redirect-assertion idiom via `response.headers["Location"]`
- `tests/accounts/test_login_logout.py:60-67` — `create_user` + `client.login` auth idiom
- `DEPLOY.md:20-28` — mandatory pre-migration SQLite backup
- `DEPLOY.md:5-10` — known-good deployment table (the rollback mechanism)

## Architecture Insights

- **Convention over abstraction.** No service layer, no repository pattern, no custom base classes. Logic sits in forms (validation) and views (orchestration). S-02 should not introduce a `services.py` for a single-model CRUD slice.
- **Settings-as-indirection for URLs.** Redirect targets are settings-sourced URL names, so repointing the post-login destination is a one-line change that propagates to `SignUpView` automatically. This is why retiring the landing page is cheap.
- **Type-safety is enforced but locally.** `mypy --strict` with django-stubs, zero ignores in the tree — yet no type check runs in CI. Quality is real but depends entirely on the implementer running the local gates.
- **The deploy pipeline trades safety for simplicity.** Migrate-in-start-command plus a `manage.py check`-only gate plus no atomic rollback means correctness has to be established *before* merge, because merge equals production. `DEPLOY.md`'s manual backup ritual is the only real safety net, and it is human-triggered.
- **Observability is a single probe.** `/healthz/` is the whole observability story — no structured logging, no error tracking. If a trips view 500s in production, diagnosis is `railway logs`.
- **The empty-draft state is load-bearing architecture, not a UI nicety.** The PRD models a trip as a curated collection that legitimately holds zero files, and S-03's map/stats views hang off that state. Getting the empty state right in S-02 is what lets S-03 be additive.

## Historical Context (from prior changes)

- `context/archive/2026-08-22-user-registration-login/plan.md:37` — no custom `AUTH_USER_MODEL`, by explicit user decision
- `context/archive/2026-08-22-user-registration-login/plan.md:41` — no CSS framework or styling beyond semantic HTML
- `context/archive/2026-08-22-user-registration-login/plan.md:57` — the landing page is throwaway; S-02 deletes it
- `context/archive/2026-08-22-user-registration-login/plan.md:83` — conftest kept minimal deliberately; add fixtures when a later phase needs them
- `context/archive/2026-08-22-user-registration-login/reviews/impl-review.md:44-75` — F1: missing `non_field_errors` shipped green (critical)
- `.../impl-review.md:77-100` — F2: a test whose name claims an assertion must make it
- `.../impl-review.md:126-140` — F3: case-sensitive `filter()` is a bypass; normalize + `__iexact`
- `.../impl-review.md:143-155` — F4: a high coverage headline can hide the one uncovered line that matters
- `.../impl-review.md:188-207` — F5: stock `User` accepted as risk; revisit if email drives recovery flows
- `.../impl-review.md:239-265` — F7: stale `AGENTS.md`/roadmap status is a defect class
- `.../impl-review.md:308-321` — F10: widen `coverage source` whenever a new package ships
- `.../impl-review.md:361-363` — absent `models.py`/`migrations/` confirmed correct for S-01
- `context/changes/deployment/deployment-plan.md:101-112`, `:133`, `:143`, `:150` — Volume mount, `RAILWAY_RUN_UID=0`, backup requirement, verification steps, untested restore path
- `context/changes/deployment/deployment-plan.md:7-14` — five corrections to `infrastructure.md` (Railpack not Nixpacks, etc.); apply the newer names
- `context/foundation/README.md:7`, `:15` — edit foundation docs in place; change-scoped docs belong under `context/changes/<change-id>/`

**Accumulated lessons, restated** (there is no `lessons.md`; these are the rules the S-01 review encoded and S-02 should honor):

1. A test whose name claims an assertion must actually make it — assert the *reason*, not just the absence.
2. Render `{{ form.non_field_errors }}` in every form template.
3. A high coverage percentage can conceal the one uncovered line that matters; every template the suite never renders is unproven.
4. Widen `[tool.coverage.run] source` whenever a new package ships.
5. Update `AGENTS.md` (and roadmap status) in the same slice that invalidates it.
6. Normalize on write and compare case-insensitively for user-supplied identifiers.
7. Never write to `context/archive/` — S-01's plan and review are read-only.
8. Fix commits precede the commit that records the decisions describing them.

## Related Research

- `context/archive/2026-08-22-user-registration-login/plan.md` and `plan-brief.md` — the structural template for S-02's plan
- `context/archive/2026-08-22-user-registration-login/reviews/impl-review.md` — the findings catalogue this slice must not repeat
- `context/changes/deployment/deployment-plan.md` — Railway/Volume/migration operational decisions
- `context/foundation/infrastructure.md` — platform risk register, including the silent-write-failure and no-atomic-rollback risks
- No prior `research.md` exists in this repo; this is the first.

## Compliance Checklist for the S-02 Plan

Derived from `roadmap.md`, `context/foundation/*`, and `DEPLOY.md`:

- [ ] `trips/` at the repo root; `"trips"` appended to `INSTALLED_APPS` (`settings.py:45`)
- [ ] `trips/apps.py` sets `default_auto_field = "django.db.models.BigAutoField"`
- [ ] `Trip.owner` → `ForeignKey(settings.AUTH_USER_MODEL)`; stock `auth.User` confirmed as the locked choice
- [ ] Trip date is a `DateField` (calendar date, `USE_TZ = True` in play)
- [ ] Migration generated **and committed**; `makemigrations --check --dry-run` clean (CI will not catch this)
- [ ] List view queryset scoped to `request.user`; owner set server-side in `form_valid`, never from POST data
- [ ] A cross-user negative test proving user A cannot see user B's trips (PRD guardrail, `prd.md:43`)
- [ ] Empty-state rendering for a user with no trips, and a trip with no file treated as a valid draft (`roadmap.md:75`)
- [ ] `{{ form.non_field_errors }}` present in the trip form template
- [ ] `TYPE_CHECKING` shim for `ListView[Trip]` (one arg) and `CreateView[Trip, TripForm]` (two args)
- [ ] `trips/urls.py` with `app_name = "trips"`, included from `velo_log/urls.py`; decide on `path("")` for the site root
- [ ] `LOGIN_REDIRECT_URL` repointed at the trip list; `accounts.landing` view/URL/template/tests removed; logout form carried over
- [ ] `"trips"` added to `[tool.coverage.run] source` (`pyproject.toml:63`)
- [ ] Tests at `tests/trips/` with `__init__.py`; no app-local `trips/tests.py`
- [ ] `AGENTS.md` coverage claim corrected; `roadmap.md` S-02 status advanced
- [ ] `/python-quality-gates` run locally — nothing but `manage.py check` runs in CI
- [ ] **Pre-deploy**: `railway service files download /data/db.sqlite3 ./backup-<ts>.sqlite3` before merging to `master` (`DEPLOY.md:20-28`)
- [ ] **Post-deploy**: verify `railway logs` + `/healthz/`, then append a row to `DEPLOY.md`'s known-good table
- [ ] No new dependency needed; if one is added, commit the `uv.lock` change (CI runs `uv sync --locked`)

## Open Questions

These are plan-level decisions this research surfaced but cannot settle:

1. **Does the trip list claim the site root `/`?** It is currently a 404, and the trip list is the natural owner — but that adds a `path("")` with no precedent, and an unauthenticated visitor to `/` would redirect to login.
2. **Is a `base.html` introduced now, or does S-02 duplicate the standalone-document pattern?** Two new templates plus the surviving auth templates make four near-identical documents, and S-03/S-04 add more. Introducing one requires either a `templates/` dir added to `TEMPLATES["DIRS"]` or an app-hosted base — and it is scope S-01 explicitly deferred.
3. **Does S-02 introduce the first CSS?** The list view is the first screen where "no styling at all" becomes visible product surface. The PRD's only NFR is about not failing silently, not about looks.
4. **`LoginRequiredMixin` on CBVs, or `@login_required` via `.as_view()` wrapping?** The repo has only the decorator precedent; the mixin is the conventional CBV answer. Pick one and apply it consistently, since S-03/S-04 will copy it.
5. **Is the messages framework activated for "trip saved" confirmation?** US-01's acceptance criteria mention "a confirmation that the trip was saved" (`prd.md:51`). The plumbing is wired with zero consumers, and no render markup exists.
6. **Does the plan also fix the queued housekeeping** — dead `main.py` placeholder, missing `pytest testpaths`, inapplicable `S608` ruff ignore, CI not running tests — or leave them out of scope? All were explicitly queued as out-of-scope by S-01's review, and the deadline argues for leaving them.
7. **Ordering of trips in the list.** Neither the PRD nor the roadmap specifies it; `Meta.ordering` by date descending is the obvious default but is an unstated product decision.
