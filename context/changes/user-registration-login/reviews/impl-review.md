<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: User Registration, Login & Logout

- **Plan**: `context/changes/user-registration-login/plan.md`
- **Scope**: All phases (1–3 of 3), commits `c797e2e..f1bcbd8`
- **Date**: 2026-08-22
- **Verdict**: REJECTED
- **Findings**: 2 critical, 5 warnings, 3 observations

Verdict note: "REJECTED" here rests on a single blocking defect (F1) whose fix is one
template line, not on structural problems. Plan adherence and architecture are clean.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | FAIL |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

### Automated gates — all re-run and confirmed

| Gate | Result |
|---|---|
| `uv run python manage.py check` | exit 0 — no issues |
| `uv run pytest` | exit 0 — 9 passed |
| `uv run pytest --cov` | 97.73% (gate: 80%) |
| `uv run black --check .` | exit 0 — 18 files unchanged |
| `uv run isort --check-only .` | exit 0 |
| `uv run ruff check .` | exit 0 |
| `uv run mypy .` | exit 0 — 18 source files |

### Scope guardrails — all 7 respected

No custom `AUTH_USER_MODEL`; no `django-allauth`; no password reset; no email
verification; no CSS framework; no "remember me"; no admin UI changes. Verified against
the diff — no violations.

## Findings

### F1 — Invalid login renders no error at all; user sees a blank form

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `accounts/templates/accounts/login.html:9-19`
- **Detail**: `AuthenticationForm` raises its invalid-credentials error from `clean()`,
  so it lands in `non_field_errors`, not on any field. The template iterates
  `{% for field in form %}` and renders only `{{ field.errors }}`, so the error is
  never emitted. A user who mistypes their password gets HTTP 200, an empty form, and
  zero feedback — a blocking defect in FR-002's primary flow.

  Verified empirically by rendering an invalid login:
  ```
  STATUS: 200
  NON_FIELD_ERRORS: <ul class="errorlist nonfield"><li>Please enter a correct username
                    and password. Note that both fields may be case-sensitive.</li></ul>
  ERROR TEXT IN BODY: False
  ```
  The error exists on the form object and never reaches the HTML.

  `signup.html:11-17` has the identical structural gap. It is currently harmless only
  because every `UserCreationForm` error happens to be field-attached — a latent
  version of the same bug that will surface the first time a non-field validator is
  added.
- **Fix**: Add `{{ form.non_field_errors }}` immediately inside the `<form>` element in
  both `login.html` and `signup.html`.
  - Strength: Restores the error path Django already produces; two lines, no logic change.
  - Tradeoff: None meaningful.
  - Confidence: HIGH — reproduced directly against the running app.
  - Blind spot: None significant.
- **Decision**: FIXED — added `{{ form.non_field_errors }}` to login.html and signup.html.

### F2 — `test_login_with_invalid_credentials_shows_error` asserts nothing about the error

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `tests/accounts/test_login_logout.py:22-31`
- **Detail**: The test's name claims it verifies an error is shown, but its body only
  checks status and session:
  ```python
  assert response.status_code == 200
  assert "_auth_user_id" not in client.session
  ```
  That is exactly what a completely error-less re-render produces — which is the actual
  current behavior. Phase 3's plan contract said "invalid credentials show a form error
  and no session is created"; only the second half is verified. This is the specific
  gap that let F1 reach `master` with every gate green.
- **Fix**: Assert the rendered error, e.g.
  `assertContains(response, "Please enter a correct username and password")` or
  `assert response.context["form"].non_field_errors()`.
  - Strength: Turns the test into a real regression guard for F1.
  - Tradeoff: Will fail until F1 is fixed — which is the point.
  - Confidence: HIGH.
  - Blind spot: None significant.
- **Decision**: FIXED — asserts `form.non_field_errors()` and the rendered error text; verified passing after F1's fix.

### F3 — Duplicate-email check is case-sensitive and bypassable

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `accounts/forms.py:16`
- **Detail**: `User.objects.filter(email=email)` compiles to SQL `=`, case-sensitive on
  both SQLite and PostgreSQL. Registering `dup@example.com` then `DUP@example.com`
  produces two accounts on the same mailbox, defeating the check the plan added
  specifically to prevent that.

  Verified empirically:
  ```
  STATUS: 302 (302 == account created)
  SECOND ACCOUNT CREATED: True
  TOTAL USERS ON THAT MAILBOX: 2
  ```
  No test covers a case-varied duplicate, so the suite is green.

  This is not plan drift — the plan specified exactly this check. It is a limitation the
  plan did not anticipate.
- **Fix A ⭐ Recommended**: Use `filter(email__iexact=email)` and normalize on return
  (`return email.strip().lower()` from `clean_email`), plus a test with `DUP@example.com`.
  - Strength: Closes the bypass and stops new mixed-case rows accumulating; ~3 lines.
  - Tradeoff: Still form-level only — see F5 for the concurrent-write hole.
  - Confidence: HIGH — standard Django idiom.
  - Blind spot: Does not normalize rows already in the database (none in production yet).
- **Fix B**: Fold into the custom-user-model decision in F5 and fix both at once.
  - Strength: One migration solves case-insensitivity and the missing DB constraint together.
  - Tradeoff: Larger change; blocks a cheap fix behind an architectural decision.
  - Confidence: MEDIUM — depends on the F5 outcome.
  - Blind spot: Delays closing an active bypass.
- **Decision**: FIXED via Fix A — `clean_email` now normalizes with `.strip().lower()` and checks with `filter(email__iexact=...)`; added a case-varied duplicate test (`DUP@Example.com` vs. `dup@example.com`). Chosen over Fix B (custom `AUTH_USER_MODEL`) because the app targets a small, near-private user base with low QPS — see F5's decision for the full reasoning shared by both findings.

### F4 — No test ever loads the landing page while authenticated

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `tests/accounts/` (missing test); uncovered line `accounts/views.py:17`
- **Detail**: The plan's Testing Strategy required "Landing page: authenticated access
  succeeds" and an integration flow ending "GET landing → assert 200 and username in
  response". Neither exists. Coverage confirms the hole:
  ```
  accounts\views.py     22     1    95%   17
  ```
  Line 17 is `return render(request, "accounts/landing.html")` — never executed. So
  `landing.html` is never rendered by the suite, and neither `{{ user.username }}` nor
  its `{% url 'logout' %}` form is covered. A broken landing template would ship green,
  and the 97.73% headline number conceals it.
- **Fix**: Add a test that logs a client in, GETs `accounts:landing`, and asserts 200
  plus the username in the response body.
  - Strength: Covers the one uncovered line and the only template the suite never renders.
  - Tradeoff: None — ~6 lines.
  - Confidence: HIGH.
  - Blind spot: None significant.
- **Decision**: FIXED — added `test_authenticated_landing_shows_username`; verified passing.

### F5 — Email uniqueness has no DB backstop; concurrent signups both commit

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Safety & Quality
- **Location**: `accounts/forms.py:14-18`, `accounts/views.py:31-34`
- **Detail**: `clean_email()` is a read; `form.save()` is a later write in a different
  transaction. `django.contrib.auth.models.User.email` carries no unique constraint
  (only `username` does), so two concurrent signups with the same address both pass
  validation and both commit. The form check is the sole enforcement.

  Likelihood is low for a single-user cycling diary; blast radius is a permanently
  duplicated identity the app cannot detect afterwards — and that matters more once
  email is used for recovery.

  The wider point: the app is now hard-wired to the stock `User` (`forms.py:3`,
  `views.py:6`), whose `email` is non-unique and non-required at the DB level — the root
  cause of both this and F3. Django's docs call swapping the user model after the first
  migration "significantly more difficult". The project is greenfield with no production
  data, so this is the last cheap moment to decide. Note the plan explicitly ruled out a
  custom `AUTH_USER_MODEL`, so revisiting it is a deliberate scope reversal, not a fix.
- **Fix A ⭐ Recommended**: Accept the race explicitly for now and record the decision;
  pair with F3's `__iexact` fix so the realistic (sequential) case is closed.
  - Strength: Matches actual scale (PRD `target_scale: users: small, qps: low`); keeps
    the plan's no-custom-user-model guardrail intact.
  - Tradeoff: Leaves a real, if unlikely, data-integrity hole.
  - Confidence: HIGH — the risk is genuinely proportional to this app's traffic.
  - Blind spot: If email later drives password reset, the cost of a duplicate rises.
- **Fix B**: Introduce `accounts.User(AbstractUser)` with `email = EmailField(unique=True)`
  and `AUTH_USER_MODEL`, plus its initial migration, now.
  - Strength: Solves F3 and F5 at the DB level permanently, and is far cheaper today
    than after the first real data lands.
  - Tradeoff: Reverses a stated scope decision; touches settings, forms, and every
    future model's FK target.
  - Confidence: MEDIUM — correct long-term, but out of this slice's agreed scope.
  - Blind spot: Whether S-02+ actually need per-user profile fields is still unknown.
- **Decision**: ACCEPTED AS RISK via Fix A. VeloLog is a near-private app for a very
  small number of known users at low QPS (PRD `target_scale`). Closing F3
  (case-insensitive check) removes the realistic, sequential duplicate-signup path;
  what's left here is a true concurrent-write race — two signups for the exact same
  email landing in the same few-millisecond window — which is vanishingly unlikely at
  this scale and has no attacker incentive (a duplicate account on your own mailbox
  gains nothing). Fix B (custom `AUTH_USER_MODEL` with a DB-level unique constraint)
  would close the race permanently, but reverses the plan's explicit
  no-custom-user-model guardrail and touches the identity foundation every future
  model's FK will point at — not justified by a risk this small. Revisit if/when email
  starts driving password reset or any recovery flow, where a duplicate becomes a
  security-relevant ambiguity rather than a data-hygiene one.

### F6 — Production hardening stops short of redirect and HSTS

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `velo_log/settings.py:140-145`
- **Detail**: What the slice added is correct:
  ```python
  if not DEBUG:
      SESSION_COOKIE_SECURE = True
      CSRF_COOKIE_SECURE = True
      SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
  ```
  Missing from the same block: `SECURE_SSL_REDIRECT`, and `SECURE_HSTS_SECONDS`
  (with `SECURE_HSTS_INCLUDE_SUBDOMAINS` / `SECURE_HSTS_PRELOAD`). Without a redirect a
  plain-HTTP request to the Railway domain is served rather than upgraded; without HSTS
  the browser never remembers to prefer HTTPS. These are precisely `check --deploy`'s
  W008 and W004.

  This slice is the first to put credentials over that connection, which is what makes
  the gap worth raising now rather than at deploy time.
- **Fix**: Add `SECURE_SSL_REDIRECT = True` and `SECURE_HSTS_SECONDS` (start at `3600`,
  raise once verified) to the existing `if not DEBUG` block.
  - Strength: Completes the hardening the slice already started, in the block it created.
  - Tradeoff: A wrong HSTS value is sticky in browsers — start low deliberately.
  - Confidence: HIGH — standard Django-behind-a-proxy configuration.
  - Blind spot: Railway's own edge may already redirect HTTP→HTTPS; unverified against
    the live deployment.
- **Decision**: FIXED — added `SECURE_SSL_REDIRECT` and `SECURE_HSTS_SECONDS = 3600` to the `if not DEBUG` block; `check --deploy` confirms W008/W004 cleared.

### F7 — AGENTS.md now tells future agents two things that are false

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `AGENTS.md:34`, `AGENTS.md:38`; `context/foundation/roadmap.md:30,64`
- **Detail**: This slice configured the repo's linting and test infrastructure, but
  `AGENTS.md` was not touched by the diff and still states:
  - L34: "No linting tools are configured yet. Before writing business logic, wire
    `ruff`, `black`, and `mypy` into `pyproject.toml`…"
  - L38: "No test infrastructure exists yet. When adding tests: use `pytest` +
    `pytest-django`…"

  Both are now wrong. `AGENTS.md` is the agent-facing instruction file loaded every
  session, so the next agent is actively told to re-wire tooling that already exists —
  the highest-leverage doc in the repo pointing at a state that no longer holds.

  Separately, `roadmap.md` still shows S-01 as `in-progress` (table row and slice
  detail) while `change.md` says `implemented`.
- **Fix**: Rewrite `AGENTS.md:34` and `:38` to describe the configured tooling (ruff /
  black / isort / mypy strict + django-stubs; pytest + pytest-django, `tests/` at root,
  `fail_under = 80`), and flip both `roadmap.md` S-01 statuses to `done`.
  - Strength: Removes an active source of wrong instructions for every future session.
  - Tradeoff: None.
  - Confidence: HIGH.
  - Blind spot: None significant.
- **Decision**: FIXED — rewrote `AGENTS.md:34`/`:38` to describe the configured tooling; flipped both `roadmap.md` S-01 statuses to `done`.

### F8 — No docstrings on any new public callable, unlike the repo's own view

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `accounts/views.py:16,26,31`; `accounts/forms.py:7,14`
- **Detail**: Type hints are complete and correct throughout — including the neat
  `TYPE_CHECKING` generic-base shim at `views.py:20-23` — so only the docstring half of
  the global Python standard is missed. This is not an abstract nit: the pre-existing
  view in this same repo carries one —

  `velo_log/urls.py:26`: `"""Round-trip a write and read against the database to confirm it's reachable."""`

  — while `landing`, `SignUpView`, `SignUpView.form_valid`, `SignUpForm`, and
  `clean_email` have none. `form_valid`'s auto-login side effect
  (`login(self.request, self.object)`) is the one genuinely non-obvious behavior in the
  slice and is undocumented.
- **Fix**: Add one-line Google-style docstrings to the five callables; make
  `form_valid`'s state that it logs the new user in.
- **Decision**: FIXED — added docstrings to `landing`, `SignUpView`, `form_valid`, `SignUpForm`, and `clean_email`.

### F9 — Rejection tests assert absence, never the reason

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `tests/accounts/test_registration.py:38-39,56-57,72-73`
- **Detail**: All three rejection tests share the shape:
  ```python
  assert response.status_code == 200
  assert not User.objects.filter(username="other").exists()
  ```
  Each would pass if the form rejected the POST for an entirely unrelated reason — a
  renamed field, a broken validator, a password-policy rejection. The duplicate-email
  test never touches `clean_email`'s message, so a regression in `forms.py:17` goes
  unnoticed as long as *something* rejects the submission. Less severe than F2 because
  the outcome being asserted (no row created) is at least the one that matters.
- **Fix**: Assert the specific error, e.g.
  `assert "already exists" in response.context["form"].errors["email"][0]`.
- **Decision**: FIXED — all three rejection tests now assert the specific validation error message.

### F10 — Coverage measures `accounts` only, so the login/logout wiring is unmeasured

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: `pyproject.toml:62-63`
- **Detail**: `[tool.coverage.run] source = ["accounts"]` (which the plan specified
  deliberately) excludes `velo_log/urls.py` — the file holding the `LoginView`/
  `LogoutView` wiring this slice added in Phase 3, plus `healthz` and every URL name the
  tests resolve. The `fail_under = 80` gate therefore says nothing about the project
  package, and Phase 3's own deliverable sits outside the measured set.
- **Fix**: `source = ["accounts", "velo_log"]`, with `omit` for `wsgi.py`, `asgi.py`,
  and `settings.py`.
- **Decision**: FIXED — coverage source widened to include `velo_log`; gate still passes at 87.93%.

## Minor notes — not tracked as findings

- `main.py` — the `uv init` placeholder was type-annotated (`def main() -> None`) rather
  than deleted; it still contains `print()`, which the global standard forbids. Deleting
  the file is probably right, since `manage.py` is the real entry point.
- Site root `/` is unrouted — `urlpatterns` covers `admin/`, `healthz/`, `accounts/…`
  only, so a visitor to the bare domain gets a 404.
- `velo_log/urls.py:39` mounts `include("accounts.urls")` *before* the concrete
  `accounts/login/` route. No shadowing today, but adding a `login/` route inside the app
  urlconf later would silently win over the project-level `name="login"`.
- `[tool.pytest.ini_options]` omits `testpaths = ["tests"]` despite the plan saying
  pytest is "pointed at `tests/`". Harmless in practice.
- `ruff` `ignore = ["S608"]` is inapplicable boilerplate — no SQL anywhere in the repo.
- The plan wrote `[tool.django_stubs]`; the implementation used `[tool.django-stubs]`,
  which is the key django-stubs actually reads. Deviation in the implementation's favor.
- `.github/workflows/deploy.yml:20-23` gates deploys on bare `manage.py check` only — no
  `pytest`, `ruff`, or `mypy`, despite all four now being configured, and it deploys to
  production on every push to `master`. Out of scope for this review (CLAUDE.md defers CI
  review to a later module) but worth queuing.

## Verified clear

- **No injection surface** — no raw SQL, `subprocess`, or `eval`; zero `|safe` or
  `{% autoescape off %}` in the three templates; `{{ user.username }}` is autoescaped.
- **No hardcoded secrets** — `SECRET_KEY = env("SECRET_KEY")` has no default and fails
  closed; `.env` is gitignored, `.env.example` is committed with empty values;
  `db.sqlite3` is untracked.
- **`DEBUG` defaults to `False`** and `ALLOWED_HOSTS` defaults to `[]` — both fail-closed.
- **`AUTH_PASSWORD_VALIDATORS` present and intact** — all four stock validators,
  untouched by the diff.
- **Authorization boundary correct** — `landing` is the only view needing protection and
  has `@login_required`, confirmed by the redirect tests. `signup`/`login` are
  intentionally public.
- **Logout is POST-correct** for Django 4.1+ — POST form with `{% csrf_token %}` in
  `landing.html:9-12`, `client.post` in the test. No GET logout link anywhere.
- **`CSRF_TRUSTED_ORIGINS` not needed** — `SECURE_PROXY_SSL_HEADER` makes
  `request.is_secure()` true behind Railway's proxy, so same-origin POSTs verify against
  `request.get_host()`. Only needed if a second domain is ever POSTed from.
- **Missing `models.py` / `admin.py` / `migrations/` is correct**, not a defect — the app
  declares no models; `manage.py check` reports 0 issues and
  `makemigrations --check --dry-run` reports no changes.
- **No N+1 or unbounded iteration** — `clean_email` issues one `EXISTS` query; no
  queryset is iterated anywhere in the diff.
- **Git workflow clean** — feature branch, four atomic phase commits in logical order,
  `--no-ff` merge with a PM-level body. Matches the project's git standard.
