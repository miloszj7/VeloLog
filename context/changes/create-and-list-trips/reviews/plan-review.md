<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Create and List Trips (S-02)

- **Plan**: `context/changes/create-and-list-trips/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-23
- **Verdict**: REVISE → **SOUND** after triage (all 7 findings fixed in `plan.md`, 2026-08-23)
- **Findings**: 2 critical, 3 warnings, 2 observations

## Verdicts

| Dimension | Verdict (as reviewed) | After triage |
|-----------|-----------|--------------|
| End-State Alignment | PASS | PASS |
| Lean Execution | WARNING | PASS — F3 fixed |
| Architectural Fitness | WARNING | PASS — F5 fixed |
| Blind Spots | WARNING | PASS — F4, F7 fixed |
| Plan Completeness | FAIL | PASS — F1, F2, F6 fixed |

## Grounding

17/17 paths ✓, 9/9 symbols ✓, brief↔plan ✓

Symbols verified: the `TYPE_CHECKING` CBV shim (`accounts/views.py:21-24`), the `ModelForm` direct-subscript pattern (`accounts/forms.py:7`), `LOGIN_REDIRECT_URL = "accounts:landing"` (`velo_log/settings.py:137`), `[tool.coverage.run] source` (`pyproject.toml:63`), `python_files` (`pyproject.toml:60`), the form-rendering block (`accounts/signup.html:9-20`), the logout form (`accounts/landing.html:9-12`), `default_auto_field` per AppConfig (`accounts/apps.py`), and zero `# type: ignore` / `# noqa` repo-wide.

Also confirmed accurate: exactly four tests reference `accounts:landing` (`tests/accounts/test_login_logout.py:17,46,53/56,64`); `tests/accounts/test_registration.py` asserts only `302`, never the redirect target, so Phase 4's `LOGIN_REDIRECT_URL` change does not touch it. The `## Progress` section conforms to the mechanical contract in `.claude/skills/10x-plan/references/progress-format.md` — one heading, phase titles matching the body, and every Success Criteria bullet backed by a numbered step (1.1–1.11, 2.1–2.7, 3.1–3.12, 4.1–4.11, 5.1–5.12).

One over-caution, harmless: Key Discoveries calls project route ordering "delicate" because `include("accounts.urls")` at `velo_log/urls.py:39` precedes the concrete `accounts/login/` route. `accounts/urls.py` has no catch-all and Django falls through an include whose sub-patterns do not match, so no hazard exists. It leads to no wrong action, so it is not filed as a finding.

## Findings

### F1 — SuccessMessageMixin needs the TYPE_CHECKING shim too

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 → Changes Required #2 (The views)
- **Detail**: Phase 3 enumerates exactly two shim aliases (`ListView[Trip]`, `CreateView[Trip, TripForm]`) and then puts `SuccessMessageMixin` bare into `TripCreateView`'s base list. But `SuccessMessageMixin` has the same split personality the shim exists for — `django-stubs/contrib/messages/views.pyi:10` declares `class SuccessMessageMixin(Generic[_F])` while `django/contrib/messages/views.py:4` is a plain `class SuccessMessageMixin:` with `__mro__ == (cls, object)`. Verified both halves against this repo's own config: `uv run mypy` on a probe view reports `error: Missing type arguments for generic type "SuccessMessageMixin"  [type-arg]`, and `SuccessMessageMixin[TripForm]` at runtime raises `TypeError: type 'SuccessMessageMixin' is not subscriptable`. So mypy `--strict` rejects the bare form and Python rejects the subscripted form — the exact condition documented at `accounts/views.py:21-24`. The repo has zero `# type: ignore`, so criteria 3.4 and 3.6 both fail as written.
- **Fix**: Add a third alias to the Phase 3 shim block — `_SuccessMessageMixinBase = SuccessMessageMixin[TripForm]` under `TYPE_CHECKING`, bare `SuccessMessageMixin` in the `else` branch — and use it in `TripCreateView`'s base list. `LoginRequiredMixin` is genuinely non-generic (`mixins.pyi:18`) and needs no shim.
- **Decision**: FIXED — Phase 3 → Changes Required #2 now enumerates three shim aliases with the stubs-vs-runtime rationale, and explicitly excludes `LoginRequiredMixin` from the shim.

### F2 — TripCreateView resolves no template: ImproperlyConfigured

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 → Changes Required #2 and #5
- **Detail**: The plan's `TripCreateView` contract lists `form_class`, `success_url`, `success_message`, and `form_valid()` — no `model`, no `template_name`. It then creates `trips/templates/trips/trip_form.html` and never says how that file gets found. It does not get found: `BaseCreateView.get`/`post` set `self.object = None` (`django/views/generic/edit.py:176,180`); `ModelFormMixin.get_form_class()` returns `self.form_class` early and never assigns `self.model` (`edit.py:81-89`); `SingleObjectMixin.model = None` as a class attribute (`detail.py`). `SingleObjectTemplateResponseMixin.get_template_names()` therefore skips both the `isinstance(self.object, Model)` branch and the `getattr(self, "model", None)` branch, leaves `names` empty, and re-raises `ImproperlyConfigured`. The plan's reasoning that `trip_list.html` "matches the app-namespaced template layout for free" is correct for `ListView` — `MultipleObjectTemplateResponseMixin` derives the name from `self.object_list.model`, which `get_queryset()` supplies — but that mechanism does not exist on the `CreateView` side. The repo's own precedent agrees: `SignUpView` sets `template_name` explicitly (`accounts/views.py:31`). Worst part is the asymmetry: a *valid* POST redirects without rendering, so "a valid POST creates a trip and redirects" passes green while `GET /trips/new/` and every invalid-POST re-render 500.
- **Fix**: Set `model = Trip` on `TripCreateView` (`template_name_suffix = "_form"` then yields `trips/trip_form.html`), or set `template_name = "trips/trip_form.html"` explicitly to match `SignUpView`. Note in the phase that `ListView`'s implicit resolution does not generalize to `CreateView`.
- **Decision**: FIXED — Phase 3 contract now sets `template_name = "trips/trip_form.html"` explicitly (matching `SignUpView`), with a Caution recording why `ListView`'s implicit resolution does not generalize and why the failure hides from the happy path. `model = Trip` noted as the equivalent alternative.

### F3 — clean_name()'s guard is unreachable dead code

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Lean Execution
- **Location**: Phase 3 → Changes Required #1 (The trip form)
- **Detail**: The plan specifies "a `clean_name()` that strips whitespace and rejects a name that is empty after stripping, following the normalize-then-check-then-return idiom at `accounts/forms.py:16-21`." `forms.CharField` takes `strip=True` by default (`django/forms/fields.py:276`), and ModelForm's generated field inherits it. So whitespace-only input is stripped to `""` by `to_python`, then `validate()` raises the `required` error — `clean_name()` is never called. When it *is* called, its input is already stripped. Both the strip and the guard are inert. The cited idiom does not transfer: `clean_email()`'s guard (a duplicate-email query) is reachable; `clean_name()`'s is not. And Phase 1 has just put `trips` under `fail_under=80`, so this lands a permanently uncoverable branch in the newly measured package — the exact shape of lesson F4 the plan itself is carrying forward.
- **Fix**: Drop `clean_name()` from `TripForm`. Django's required+strip already delivers the behavior the plan wants, and the Phase 3 test "blank name re-renders with a field error and creates nothing" passes on the built-in validation unchanged.
  - Strength: Removes an unreachable branch from a coverage-gated package; one less concept for S-03/S-04 to copy.
  - Tradeoff: The form loses an explicit, greppable statement of the name rule — a future reader must know `CharField` strips.
  - Confidence: HIGH — verified `strip=True` at `fields.py:276` and traced `to_python` → `validate` → `clean_<field>` ordering.
  - Blind spot: If S-04's edit form ever needs a different name rule, the hook has to be reintroduced.
- **Decision**: FIXED — Phase 3 → Changes Required #1 now carries an explicit "**No `clean_name()`**" paragraph with the `strip=True` / `to_python` → `validate` reasoning and the coverage-gate rationale.

### F4 — The plan's #1 risk has a one-line CI guard it declines to take

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: What We're NOT Doing (plan.md:54) vs. Critical Implementation Details (plan.md:67) and Phase 5 Engineering Backlog
- **Detail**: The plan names one failure mode as a hard production outage: a forgotten migration file ships green because `manage.py check` cannot detect a model/schema mismatch, and `railway.json` then runs `migrate` before gunicorn. Its entire mitigation is a local command an implementer must remember to run. "No CI workflow changes" is justified on the grounds that adding a test/lint/type job "stacks two risky firsts." That reasoning covers a new *job* — it does not cover appending one flag-only command to the step that already exists. `.github/workflows/deploy.yml` already has a "Django check (merge gate)" step with `SECRET_KEY` injected, running before "Deploy to Railway"; `makemigrations --check --dry-run` needs no database (it compares files to models), so it runs there as-is. If it fails, the workflow fails and `railway up` never executes. The plan instead files all CI work in the backlog behind a "before S-03" trigger — deferring the cheap guard for its own stated worst case past the deploy that first exposes it.
- **Fix A ⭐ Recommended**: Append `uv run python manage.py makemigrations --check --dry-run` to `deploy.yml`'s existing "Django check (merge gate)" step in Phase 1, alongside the migration it protects.
  - Strength: Closes the exact hole the plan calls a hard outage, in the same step and env that already exist — no new job, no new secret, no DB. Blocks `railway up` on failure.
  - Tradeoff: Technically breaches the "no CI workflow changes" scope line, so that boundary needs rewording to "no new CI jobs."
  - Confidence: HIGH — read `deploy.yml`; step ordering puts the check before the deploy, and `--check --dry-run` touches no DB.
  - Blind spot: CI only fires on push to `master`, so this catches the mistake post-merge pre-deploy, not pre-merge.
- **Fix B**: Keep CI untouched; rely on `/python-quality-gates` and the criteria at 1.2 / 3.5 / 5.4, and record the gap as accepted.
  - Strength: Holds the scope line exactly as written; zero risk added to the first-migration deploy.
  - Tradeoff: The only defense against the plan's worst outcome stays a human remembering a command.
  - Confidence: MEDIUM — it is what S-01 did, but S-01 shipped no migration, so the precedent does not cover this case.
  - Blind spot: Nothing verifies the ritual ran before merge.
- **Decision**: FIXED via Fix A — new Phase 1 → Changes Required #7 (CI migration guard) appends the command to the existing merge-gate step, with the post-merge/pre-deploy limitation recorded as a Caution. The scope line is reworded to "No new CI jobs" with the exception named, Critical Implementation Details now points at the CI gate, and the backlog's CI row notes the guard already landed. New criterion 1.10 tracks it (manual steps renumbered 1.11–1.12).

### F5 — testpaths deferred while the hazard it prevents recurs in S-03

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architectural Fitness
- **Location**: Phase 1 → #1 (App scaffold) vs. Phase 5 Engineering Backlog
- **Detail**: Key Discoveries correctly identifies that `python_files = ["tests.py", "test_*.py"]` (`pyproject.toml:60`) would collect a `startapp`-generated `trips/tests.py`, and that ruff would then fail it because the `S101` exemption is keyed to `"tests/**"`. The chosen mitigation is "Delete it" — a manual step every future app must repeat, starting with S-03's `gpx/` app. The structural fix (`testpaths = ["tests"]`) is deferred to the backlog behind an "alongside the CI job" trigger, even though Phase 1 already edits `pyproject.toml` for the coverage change two sections below.
- **Fix**: Add `testpaths = ["tests"]` to `[tool.pytest.ini_options]` in Phase 1's `pyproject.toml` edit, and drop the backlog row. Keep the delete-`tests.py` step — the two are complementary, not redundant.
- **Decision**: FIXED — Phase 1 → #5 is now "Coverage scope and test collection scope", adds `testpaths = ["tests"]`, and states why it complements rather than replaces the delete step. The backlog row is dropped.

### F6 — Two backlog rows whose triggers this slice already meets

- **Severity**: 📋 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 5 → #3 Engineering Backlog
- **Detail**: Two rows fire on their own stated triggers within this slice: "Dead `main.py` … Trigger: Any slice touching repo-root files" (Phase 1 edits `pyproject.toml`; Phase 5 edits `AGENTS.md` and `DEPLOY.md`), and "`S608` ruff ignore is inapplicable … Trigger: Any slice touching lint config" (lint config lives in the same `pyproject.toml` Phase 1 edits). A register whose first entries are already overdue on arrival trains the next reader to ignore the triggers. Also: the section text declares columns `Item | Why it matters | Proposed fix | Trigger`, but the table below it has three columns (no "Why it matters").
- **Fix**: Either do both one-line cleanups in Phase 1 and drop the rows, or retighten the triggers to something this slice does not meet. Reconcile the declared column list with the actual table.
- **Decision**: FIXED — new Phase 1 → #9 deletes `main.py` and removes the whole `[tool.ruff.lint] ignore` key (verified: `S608` is its only entry, `pyproject.toml:39-41`); both backlog rows dropped; the section's declared columns corrected to `Item | Proposed fix | Trigger` with a standing rule that no filed row may have an already-met trigger. New criterion 1.11 covers the lint check.

### F7 — No operational access to the first production data

- **Severity**: 📋 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 1 → #1 (App scaffold); Migration Notes
- **Detail**: Phase 1 deletes `admin.py` to mirror `accounts/`, and Phase 1 manual verification affirms "no `admin.py` registered" as correct. That was free for `accounts/` (no models). `Trip` is the repo's first persisted domain data, shipped onto a SQLite volume that Migration Notes describes as having no atomic rollback and a restore path never exercised against production. `django.contrib.admin` is already installed (`settings.py:39`) and routed (`velo_log/urls.py:37`), so the cost of an escape hatch is ~4 lines; without it, inspecting or repairing a bad row in production means `railway ssh` plus a shell session.
- **Fix**: Register `Trip` in `trips/admin.py` with `list_display` on `(name, date, owner)`. Requires a production superuser to exist — if none does, note that as the actual gap instead.
- **Decision**: FIXED — new Phase 1 → #8 keeps `admin.py` as a deliberate departure from `accounts/`'s shape and registers `TripAdmin(admin.ModelAdmin[Trip])` with `list_display`. The superuser half was confirmed as a real gap (no `createsuperuser` anywhere in `railway.json`, `DEPLOY.md`, or `deployment-plan.md`), so Phase 5's deploy ritual now creates one over `railway ssh` and documents it in `DEPLOY.md`; criterion 5.13 tracks it. Phase 1's manual criterion flipped from "no `admin.py` registered" to "admin loads and lists Trip" (1.13).
