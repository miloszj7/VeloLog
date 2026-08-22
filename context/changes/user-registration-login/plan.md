# User Registration, Login & Logout Implementation Plan

## Overview

Implement Django's first user-facing app — `accounts` — covering FR-001 (register with email + password) and FR-002 (log in / log out). This is roadmap slice S-01, the prerequisite for every other slice: nothing else in VeloLog can be built against a real authenticated user until this lands.

## Current State Analysis

The Django project is a clean scaffold with no local apps registered yet:

- `INSTALLED_APPS` (`velo_log/settings.py:38-45`) contains only Django built-ins; `AuthenticationMiddleware` is present, `django.contrib.auth` context processor is wired into `TEMPLATES` (`velo_log/settings.py:66-70`), so `request.user` and `{{ user }}` are already usable once views exist.
- No `AUTH_USER_MODEL` override — default `auth.User` is in effect.
- `velo_log/urls.py:35-38` wires only `admin/` and `healthz/`; no `include()` pattern exists yet for an app urlconf.
- No templates directory exists anywhere in the project (`TEMPLATES[0]["DIRS"]` is empty, `APP_DIRS: True` — an app-level `templates/` dir will be picked up automatically).
- No `LOGIN_URL` / `LOGIN_REDIRECT_URL` / `LOGOUT_REDIRECT_URL`, and no cookie/HTTPS security settings (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER`) despite Railway terminating TLS at a proxy in front of the app.
- `pyproject.toml` has only a bare `[project]` table — no `django-allauth`, no test runner, no `ruff`/`black`/`mypy` config. `AGENTS.md` explicitly calls out wiring these three "before writing business logic" — this is the first business-logic change in the repo, so that setup belongs in this slice.
- No prior architectural decisions exist in `context/` for auth — this is genuinely greenfield.

## Desired End State

A visitor can open `/accounts/signup/`, register with a username, email, and password; they land on a minimal post-login page confirming they're authenticated. They can log out via `/accounts/logout/` and log back in via `/accounts/login/`. Duplicate username or email is rejected with an inline form error and no account is created. The whole flow is covered by `pytest-django` tests, and the repo's formatting/linting/type-checking gates (`black`, `isort`, `ruff`, `mypy`) are wired and passing.

Verify via:
- `uv run python manage.py runserver`, then manually walk signup → logout → login in a browser.
- `uv run pytest` — all accounts tests pass.
- `uv run black --check .`, `uv run isort --check-only .`, `uv run ruff check .`, `uv run mypy .` — all exit 0.

### Key Discoveries:

- `velo_log/urls.py:24-32` (`healthz`) is the only existing view — it's a plain function view with no template rendering and no `include()`, so the app-urlconf and template-rendering patterns are being established fresh here.
- `AGENTS.md:13,18` — new apps live at repo root alongside `velo_log/`, registered in `INSTALLED_APPS`.
- `AGENTS.md:34,38` — no linting or test tooling configured yet; both are meant to be wired "before writing business logic" / when adding the first tests.
- Django strict mypy against untyped `Model`/`Manager` attributes produces heavy false-positive noise without `django-stubs` — needed to make `mypy --strict` tractable per the global Python standard.

## What We're NOT Doing

- No custom `AUTH_USER_MODEL` — using Django's default `User` with both `username` and `email` required at signup (per user decision).
- No `django-allauth` — using Django's built-in `django.contrib.auth` views/forms.
- No password reset ("forgot password") flow.
- No email verification at registration.
- No CSS framework or visual styling beyond minimal semantic HTML.
- No "remember me" / persistent session option.
- No admin UI changes beyond what `django.contrib.admin` already provides.

## Implementation Approach

Three phases, each leaving the app in a working, testable state:

1. **Foundation** — tooling (`ruff`/`black`/`isort`/`mypy`/`pytest-django`), the `accounts` app skeleton, settings (auth redirects + cookie security), URL wiring, and the trivial post-login landing view. No signup/login views yet — the landing view is the one exception, added here (not in Phase 3) so `LOGIN_REDIRECT_URL` already resolves before Phase 2 needs it.
2. **Registration** — form, view, template, tests.
3. **Login & logout** — views, templates, tests. The landing page it redirects to already exists from Phase 1.

This ordering means every phase after the first has real config to build on, and registration (the piece with actual validation logic — uniqueness checks) is proven before login/logout (which are otherwise nearly configuration-only, since Django's `LoginView`/`LogoutView` need little custom code).

## Critical Implementation Details

**No home page exists yet.** S-02 (trip list) will eventually become the natural post-login landing page, but it doesn't exist yet and this slice can't depend on it. Phase 1 adds a minimal `accounts` "you're logged in as `<username>`" landing view solely to give `LOGIN_REDIRECT_URL` a valid target; it should be trivial enough to delete outright once S-02 ships a real trip list. It's added in Phase 1 (rather than alongside login/logout in Phase 3) specifically so `LOGIN_REDIRECT_URL = "accounts:landing"` already resolves by the time Phase 2's signup view needs to redirect there — see Phase 1 item 6.

**mypy strict + Django needs `django-stubs`.** Add `django-stubs[compatible-mypy]` as a dev dependency and enable its mypy plugin (`plugins = ["mypy_django_plugin.main"]`, `[tool.django_stubs] django_settings_module = "velo_log.settings"`) — otherwise `mypy --strict` floods on every `Model`/`Manager`/`request.user` access before any accounts-specific code is even written.

## Phase 1: Tooling, App Scaffolding & Settings

### Overview

Wire the repo's first quality-gate tooling and test runner, create the `accounts` app skeleton, and add the settings/URL plumbing the later phases build on. No signup/login views yet — only the trivial post-login landing stand-in, added here so Phase 2's redirect target already exists.

### Changes Required:

#### 1. Quality-gate & test tooling

**File**: `pyproject.toml`

**Intent**: Add `black`, `isort`, `ruff`, `mypy`, `django-stubs`, `pytest`, `pytest-django`, `pytest-cov` as dev dependencies (via `uv add --dev`), and configure each per the global Python standard (100-char line length, `mypy --strict` with the django-stubs plugin, `pytest` pointed at `tests/` with `DJANGO_SETTINGS_MODULE=velo_log.settings`, coverage `fail_under = 80`).

**Contract**: Adds `[tool.black]`, `[tool.isort]`, `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`, `[tool.mypy]`, `[tool.django_stubs]`, `[tool.pytest.ini_options]`, `[tool.coverage.run]`, `[tool.coverage.report]` sections. `[tool.pytest.ini_options]` needs `DJANGO_SETTINGS_MODULE = "velo_log.settings"` and `python_files = ["tests.py", "test_*.py"]` — `pytest-django` requires the settings module to be discoverable before any Django app is imported. `[tool.coverage.run]` needs `source = ["accounts"]` — without it, `pytest --cov` reports whole-repo coverage instead of the accounts-app-scoped number Phase 3's success criteria checks against.

#### 2. Test scaffolding

**File**: `tests/__init__.py`, `tests/conftest.py`

**Intent**: Establish the shared fixture pattern (`conftest.py`) that every later slice's tests will build on, per `AGENTS.md`'s "tests/ at the repo root" convention.

**Contract**: `conftest.py` provides a `django_user_model`-based fixture or relies on `pytest-django`'s built-in `client`/`db` fixtures — no custom fixtures are needed yet since Phase 1 has no views to test. Keep it minimal; add fixtures as later phases need them.

#### 3. `accounts` app skeleton

**File**: `accounts/__init__.py`, `accounts/apps.py`

**Intent**: Create the new Django app that will own registration/login/logout.

**Contract**: `apps.py` defines `AccountsConfig(AppConfig)` with `default_auto_field = "django.db.models.BigAutoField"` and `name = "accounts"`.

#### 4. Register app & auth settings

**File**: `velo_log/settings.py`

**Intent**: Register `accounts` in `INSTALLED_APPS`; add the auth redirect settings and production cookie/HTTPS security settings identified as missing during research.

**Contract**: Add `"accounts"` to `INSTALLED_APPS` (`velo_log/settings.py:38-45`). Add `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "accounts:landing"`, `LOGOUT_REDIRECT_URL = "login"` (named-URL references, not hardcoded paths). Add, gated on `not DEBUG`: `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` — the proxy header is required because Railway terminates TLS in front of the app, so Django would otherwise see every request as plain HTTP and never mark itself as secure.

**Caution**: `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` being gated on `not DEBUG` means they're also `True` for a local dev run with `DEBUG=False` — and browsers silently drop `Secure`-flagged cookies over the plain-HTTP dev server, making signup/login look broken during manual testing. Before running any manual verification step in this or later phases, confirm the local `.env` sets `DEBUG=True`. (Automated tests are unaffected — Django's test `Client` doesn't enforce this browser-side policy.)

#### 5. URL wiring

**File**: `velo_log/urls.py`, `accounts/urls.py`

**Intent**: Mount the accounts app's URLs under `/accounts/` and establish the `include()` pattern this project hasn't used yet.

**Contract**: `velo_log/urls.py` adds `path("accounts/", include("accounts.urls"))`. `accounts/urls.py` defines `app_name = "accounts"`; its `urlpatterns` gets the `landing` route from item 6 below — `signup` is added in Phase 2, `login`/`logout` in Phase 3.

#### 6. Post-login landing view

**File**: `accounts/views.py`, `accounts/urls.py`, `accounts/templates/accounts/landing.html`

**Intent**: A trivial authenticated-only page confirming login succeeded, serving as `LOGIN_REDIRECT_URL`'s target from this phase onward — moved ahead of login/logout (Phase 3) so `LOGIN_REDIRECT_URL = "accounts:landing"` resolves correctly as soon as it's set, instead of leaving Phase 2's signup redirect pointing at a URL name that doesn't exist yet.

**Contract**: A view decorated with `@login_required` (or `LoginRequiredMixin`) rendering `accounts/landing.html` with `{{ user.username }}`; registered as `path("landing/", ..., name="landing")` inside `accounts/urls.py` (namespaced `accounts:landing`). Note: until Phase 3 registers the bare `login` URL name, visiting `/accounts/landing/` while unauthenticated will itself raise `NoReverseMatch` (since `@login_required` resolves `settings.LOGIN_URL = "login"`) — this is expected and untested until Phase 3; no phase's success criteria exercise that path before then.

### Success Criteria:

#### Automated Verification:

- `uv run python manage.py check` exits 0
- `uv run pytest` exits 0 (no tests yet, but the runner and settings module resolve cleanly)
- `uv run black --check .` exits 0
- `uv run isort --check-only .` exits 0
- `uv run ruff check .` exits 0
- `uv run mypy .` exits 0

#### Manual Verification:

- Local `.env` has `DEBUG=True` — required for the Secure-flagged session/CSRF cookies (item 4 above) to work over the plain-HTTP dev server; this applies to every manual verification step through Phase 3
- `uv run python manage.py runserver` starts without error
- Visiting `/accounts/` returns a 404 (empty urlpatterns) rather than an error page, confirming the `include()` resolved correctly

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Registration

### Overview

Implement the signup form, view, and template, with uniqueness validation on both username and email.

### Changes Required:

#### 1. Signup form

**File**: `accounts/forms.py`

**Intent**: Extend Django's `UserCreationForm` to make `email` a required field with its own uniqueness validation, matching the FR-001 capability (register with email + password) while keeping the "separate username + email fields" shape the user chose.

**Contract**: `SignUpForm(UserCreationForm)` adds `email = forms.EmailField(required=True)` to `Meta.fields` (alongside `username`), and overrides `clean_email()` to raise `ValidationError` if `User.objects.filter(email=...).exists()` — this is the one place logic is non-obvious: `UserCreationForm` already validates username uniqueness via the model's `unique=True` constraint, but `email` on the default `User` model has no such constraint, so the duplicate-email check must be added explicitly in the form.

#### 2. Signup view

**File**: `accounts/views.py`

**Intent**: Render the signup form and, on success, log the new user in immediately (no email verification step, per scope decision) and redirect to the post-login landing page.

**Contract**: A `CreateView` (or equivalent class-based view) using `SignUpForm`, `template_name="accounts/signup.html"`, `success_url` resolving to `LOGIN_REDIRECT_URL`. On `form_valid`, call `login(self.request, self.object)` after `save()` so the new user doesn't have to log in separately right after registering.

#### 3. Signup template

**File**: `accounts/templates/accounts/signup.html`

**Intent**: Minimal semantic HTML form rendering `SignUpForm` with field errors displayed inline, per the "no CSS framework" decision.

**Contract**: A `<form method="post">` with `{% csrf_token %}`, rendering each form field's label, widget, and `errors` in sequence; a link to `{% url 'login' %}` for existing users.

#### 4. URL registration

**File**: `accounts/urls.py`

**Intent**: Wire the signup view into the app's urlconf.

**Contract**: Adds `path("signup/", SignUpView.as_view(), name="signup")`.

#### 5. Tests

**File**: `tests/accounts/test_registration.py`, `tests/accounts/__init__.py`

**Intent**: Cover the registration happy path and both duplicate-conflict edge cases.

**Contract**: Tests using `pytest-django`'s `client` fixture: successful signup creates a `User` and logs them in (session has `_auth_user_id`); duplicate username is rejected with a form error and no second `User` row is created; duplicate email (different username) is rejected the same way; password mismatch is rejected (exercises `UserCreationForm`'s existing validation).

### Success Criteria:

#### Automated Verification:

- `uv run pytest tests/accounts/test_registration.py` exits 0
- `uv run mypy .` exits 0
- `uv run ruff check .` exits 0

#### Manual Verification:

- Visiting `/accounts/signup/` in a browser, submitting valid data creates a `User` (verify via `manage.py shell` or admin) and lands on the post-login page
- Submitting a duplicate username or email shows an inline error and does not create a new row

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Login & Logout

### Overview

Wire Django's built-in `LoginView`/`LogoutView` and cover the flow with tests. The post-login landing page (added in Phase 1) already gives `LOGIN_REDIRECT_URL` a valid target, so this phase is close to configuration-only.

### Changes Required:

#### 1. Login/logout URLs

**File**: `velo_log/urls.py`, `accounts/urls.py`

**Intent**: Register the login and logout routes. `LOGIN_URL = "login"` (a bare name, not `"accounts:login"`) means the login URL must be reachable by that unnamespaced name — Django's convention (and what `@login_required` resolves against) expects `login`/`logout` at top level, so these two routes are mounted directly in the project urlconf rather than under the `accounts:` namespace, while `signup` and `landing` stay namespaced under `accounts/`.

**Contract**: `velo_log/urls.py` adds `path("accounts/login/", LoginView.as_view(template_name="accounts/login.html"), name="login")` and `path("accounts/logout/", LogoutView.as_view(), name="logout")`, using Django's built-in views directly (no custom view code needed for either).

#### 2. Login template

**File**: `accounts/templates/accounts/login.html`

**Intent**: Minimal semantic HTML form for Django's built-in `AuthenticationForm`, consistent with the signup template's structure.

**Contract**: Same shape as `signup.html` — `<form method="post">`, `{% csrf_token %}`, field errors inline, a link to `{% url 'accounts:signup' %}` for new users.

#### 3. Tests

**File**: `tests/accounts/test_login_logout.py`

**Intent**: Cover login, logout, and the redirect-when-unauthenticated behavior of the landing page.

**Contract**: Tests using the `client` fixture: valid credentials log in and redirect to the landing page; invalid credentials show a form error and no session is created; an authenticated client hitting `/accounts/logout/` clears the session and subsequent access to the landing page redirects to login; an unauthenticated client hitting the landing page redirects to `/accounts/login/?next=...`.

### Success Criteria:

#### Automated Verification:

- `uv run pytest` (full suite) exits 0
- `uv run pytest --cov` reports accounts app coverage ≥ 80%
- `uv run black --check .`, `uv run isort --check-only .`, `uv run ruff check .`, `uv run mypy .` all exit 0

#### Manual Verification:

- Full flow in a browser: signup → land on landing page showing username → logout → redirected → log back in with the same credentials → land on landing page again
- Attempting to visit `/accounts/landing/` while logged out redirects to `/accounts/login/`

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `SignUpForm` validation: valid data, duplicate username, duplicate email, password mismatch
- View-level: signup creates user + logs in, login succeeds/fails correctly, logout clears session
- Landing page: authenticated access succeeds, unauthenticated access redirects

### Integration Tests:

- Full client-driven flow: POST to signup → assert redirect to landing → GET landing → assert 200 and username in response → GET logout → GET landing → assert redirect to login

### Manual Testing Steps:

1. Register a new account via `/accounts/signup/`, confirm redirect to landing page showing the username
2. Attempt to register the same username again — confirm inline error, no duplicate created
3. Attempt to register the same email with a different username — confirm inline error
4. Log out, confirm redirect and that `/accounts/landing/` now redirects to login
5. Log back in with the registered credentials, confirm landing page reached again
6. Attempt login with a wrong password — confirm inline error, no session created

## Performance Considerations

None — this is low-traffic, single-user-scale auth (per PRD `target_scale: { users: small, qps: low }`). Django's default session/password-hashing configuration is sufficient.

## Migration Notes

The default `User` model already exists via Django's built-in `auth` migrations (already applied as part of any `manage.py migrate` run). This slice adds no new models, so no new migration is required.

## References

- Roadmap slice: `context/foundation/roadmap.md` (S-01, `user-registration-login`)
- PRD: `context/foundation/prd.md` (FR-001, FR-002, US-01)
- Existing view pattern: `velo_log/urls.py:24-32` (`healthz`)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Tooling, App Scaffolding & Settings

#### Automated

- [ ] 1.1 `uv run python manage.py check` exits 0
- [ ] 1.2 `uv run pytest` exits 0
- [ ] 1.3 `uv run black --check .` exits 0
- [ ] 1.4 `uv run isort --check-only .` exits 0
- [ ] 1.5 `uv run ruff check .` exits 0
- [ ] 1.6 `uv run mypy .` exits 0

#### Manual

- [ ] 1.7 Local `.env` has `DEBUG=True` for manual verification
- [ ] 1.8 `uv run python manage.py runserver` starts without error
- [ ] 1.9 Visiting `/accounts/` returns a 404, confirming `include()` resolved correctly

### Phase 2: Registration

#### Automated

- [ ] 2.1 `uv run pytest tests/accounts/test_registration.py` exits 0
- [ ] 2.2 `uv run mypy .` exits 0
- [ ] 2.3 `uv run ruff check .` exits 0

#### Manual

- [ ] 2.4 Valid signup creates a `User` and lands on the post-login page
- [ ] 2.5 Duplicate username/email shows an inline error and creates no new row

### Phase 3: Login & Logout

#### Automated

- [ ] 3.1 `uv run pytest` (full suite) exits 0
- [ ] 3.2 `uv run pytest --cov` reports accounts app coverage ≥ 80%
- [ ] 3.3 `uv run black --check .`, `uv run isort --check-only .`, `uv run ruff check .`, `uv run mypy .` all exit 0

#### Manual

- [ ] 3.4 Full flow: signup → landing page → logout → redirected → log back in → landing page again
- [ ] 3.5 Visiting `/accounts/landing/` while logged out redirects to `/accounts/login/`
