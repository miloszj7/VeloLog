# User Registration, Login & Logout — Plan Brief

> Full plan: `context/changes/user-registration-login/plan.md`

## What & Why

Implement roadmap slice S-01: a visitor can register with a username, email, and password, then log in and log out. This is the first vertical slice in VeloLog and the prerequisite for every other slice — nothing else can be built against a real authenticated user until this lands.

## Starting Point

The Django project is a clean scaffold: only Django's built-in apps are registered, no local app exists yet, no templates directory exists, and no auth-related settings (`LOGIN_URL`, cookie security) are configured. No linting/testing tooling (`ruff`, `black`, `mypy`, `pytest`) is wired either — this is genuinely the first business-logic change in the repo.

## Desired End State

A visitor can sign up at `/accounts/signup/`, land on a minimal "logged in as `<username>`" page, log out, and log back in at `/accounts/login/`. Duplicate username or email is rejected inline with no account created. The flow is covered by `pytest-django` tests, and `black`/`isort`/`ruff`/`mypy` all pass clean.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| User model | Default Django `User`, with `username` + `email` both required at signup | User's choice — most conventional Django pattern; PRD's "register with email" is satisfied by requiring email as a real field, without swapping `AUTH_USER_MODEL`. |
| Auth library | Built-in `django.contrib.auth` views/forms | Zero new dependencies; covers FR-001/FR-002 fully; `django-allauth`'s extra features (email verification, social login) aren't required. |
| Password reset | Out of scope | Neither FR-001 nor FR-002 mentions it; avoids adding an email backend nothing else in the project needs yet. |
| Email verification | Out of scope | Not required by any FR; adds token/email-backend complexity against a 2-week deadline. |
| Templates | Minimal semantic HTML, no CSS framework | No design system exists yet; visual polish is a separate later concern. |
| Test infrastructure | Set up `pytest-django` now | This is the first app in the repo — establishing the test pattern now means every later slice inherits a working convention instead of retrofitting one. |
| Cookie/HTTPS security | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER` added now, gated on `not DEBUG` | This is the first slice creating real authenticated sessions; Railway terminates TLS at a proxy, so without `SECURE_PROXY_SSL_HEADER` Django would never see itself as secure. |
| Duplicate username/email UX | Inline form error, no account created | Standard Django form-validation pattern; account-enumeration risk is acceptable for a small personal-use product. |
| Lint/type tooling | Wire `ruff`, `black`, `isort`, `mypy` (+ `django-stubs`) now | `AGENTS.md` mandates this "before writing business logic" — this is that first business-logic change. |

## Scope

**In scope:**
- Registration (username + email + password), login, logout
- Minimal post-login landing page (stand-in until S-02 ships a real trip list)
- Cookie/HTTPS security settings for production
- `ruff`/`black`/`isort`/`mypy`/`pytest-django` project setup

**Out of scope:**
- Custom `AUTH_USER_MODEL`
- `django-allauth`
- Password reset, email verification, "remember me"
- Any CSS framework or visual design

## Architecture / Approach

A new `accounts` Django app at the repo root, registered in `INSTALLED_APPS`, using Django's built-in `UserCreationForm` (extended for a required, unique `email` field) and built-in `LoginView`/`LogoutView`. URLs mount under `/accounts/`, except `login`/`logout` which stay at top-level names per Django convention (`LOGIN_URL`, `@login_required` resolve against the bare `login` name).

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Tooling, scaffolding & settings | `ruff`/`black`/`mypy`/`pytest-django` wired, `accounts` app skeleton, auth + cookie-security settings, URL wiring, minimal post-login landing page | `mypy --strict` against Django without `django-stubs` would be unworkable — mitigated by adding the plugin now. Landing page lives here (not Phase 3) so `LOGIN_REDIRECT_URL` already resolves before Phase 2's signup redirect needs it. |
| 2. Registration | Signup form/view/template with duplicate-username/email validation | Email has no DB-level uniqueness constraint on default `User` — must be enforced in form validation |
| 3. Login & logout | Built-in login/logout views | No home page exists yet — landing page (built in Phase 1) is a deliberate stand-in until S-02 |

**Prerequisites:** None — first slice, no dependencies.
**Estimated effort:** ~2-3 sessions across 3 phases.

## Open Risks & Assumptions

- Adding `django-stubs` + `mypy --strict` for the first time may surface friction beyond this slice's scope if Django's ORM patterns trigger unexpected strict-mode errors — budget some slack in Phase 1.
- The landing page is intentionally throwaway; it should be deleted once S-02 (`create-and-list-trips`) ships a real trip list as the login destination.

## Success Criteria (Summary)

- A new visitor can complete signup → land on the landing page → log out → log back in, entirely through the browser
- Duplicate username or email at signup is rejected without creating a second account
- `pytest`, `black`, `isort`, `ruff`, and `mypy` all pass clean
