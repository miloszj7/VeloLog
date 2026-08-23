# Create and List Trips (S-02) — Plan Brief

> Full plan: `context/changes/create-and-list-trips/plan.md`
> Research: `context/changes/create-and-list-trips/research.md`

## What & Why

Roadmap slice S-02: a user can create a trip with a name, date, and description, and see it in a list of their own trips (FR-003, FR-006, US-01). It is the prerequisite for S-03, the north star slice where a GPX file gets uploaded and rendered as a map — nothing downstream can exist until a trip does.

## Starting Point

The repo has authentication and a working Railway deploy, and nothing else. `accounts/` is the only feature app; it has no `models.py` and no `migrations/`, so S-02's migration is the first this project has ever shipped to production. There is no queryset anywhere scoped to a user, no test that creates two users, no shared template, and no CSS. The site root 404s, and `accounts.landing` exists purely as a placeholder login destination that S-01 explicitly designated S-02 to delete.

## Desired End State

Logging in lands the user on their trip list — their own trips only, newest tour date first, with a clear empty state when they have none. A "New trip" form takes name, date, and description; saving redirects back to the list with a flash confirmation and the new trip visible. A second user's trips are never reachable. A trip with no attached file is a perfectly valid row, which is the state S-03 builds its upload path on top of.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Identity model | Stock `auth.User`, `owner` FK via `settings.AUTH_USER_MODEL` | S-01 accepted this as residual risk, and this migration is the moment it becomes permanent. | Research |
| Trip date type | `DateField`, not `DateTimeField` | `USE_TZ = True` makes a datetime ambiguous for a user-entered calendar date. | Research |
| Owner assignment | Excluded from the form, set in `form_valid` from `request.user` | A form field that merely defaults to the current user is bypassable by POSTing another user's ID. | Research |
| Template strategy | Project-level `templates/base.html`, auth templates retrofitted | Deleting `landing.html` removes the app's only logout control; a base fixes that structurally so S-03/S-04 inherit it. | Plan |
| Site root `/` | `RedirectView` to `trips:list`; canonical list stays at `/trips/` | Kills the 404 without breaking the app-namespace convention every other route follows. | Plan |
| CBV auth | `LoginRequiredMixin` | Deleting `landing` removes the decorator's only consumer, so the repo ends with exactly one idiom for later slices to copy. | Plan |
| Save confirmation | `SuccessMessageMixin`, rendered in `base.html` | PRD US-01 asks for it and the messages framework is already wired with zero consumers and zero config needed. | Plan |
| List ordering | `-date`, `-id` tiebreak | Matches how a touring diary is read; the id tiebreak keeps tests deterministic on same-date trips. | Plan |
| Styling | None this slice | Protects the 2026-09-10 deadline and avoids meeting manifest-storage's render-time failure mode on the same deploy as the first migration. | Plan |
| Deferred work | `lessons.md` + a roadmap Engineering Backlog table | Both are read every session; a register inside this change would be archived with it and stop being read. | Plan |

## Scope

**In scope:** the `trips` app and `Trip` model; the first migration; owner-scoped list view with empty state; create form and view; project-level base template with logout and flash messages; site root redirect; retirement of `accounts.landing`; `trips` added to coverage scope; the first cross-user isolation test; `AGENTS.md` and roadmap corrections; `lessons.md` creation; the Engineering Backlog; the pre-migration deploy ritual.

**Out of scope:** edit and delete (S-04); GPX upload, file storage, map rendering, and all media configuration (S-03); trip detail view; filtering, sorting, search, pagination (FR-012 parked); visibility toggle (FR-009 parked); CSS; custom `AUTH_USER_MODEL` or profile model; service layer; logging configuration; CI workflow changes; new dependencies.

## Architecture / Approach

Plain Django, no new abstractions — validation in the form, orchestration in the view, matching the only house style the repo has. `Trip` holds a non-nullable FK to the user. Isolation is enforced in two places that must both hold: `get_queryset()` filters the list to `request.user`, and `form_valid()` assigns the owner server-side so it is never client-supplied. Both trip CBVs sit behind the `TYPE_CHECKING` shim that django-stubs requires, with `ListView[Trip]` taking one type parameter where `CreateView[Trip, TripForm]` takes two. Templates converge onto a single project-level `base.html` that owns the document shell, the logout form, and the flash-message block.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Model, scaffold, migration | `trips` app, `Trip` model, the first committed migration, coverage scope widened | A missing migration file passes CI green and becomes a production 500 — `manage.py check` cannot detect it |
| 2. Base template | `templates/base.html` with logout and messages; auth templates retrofitted | Regressing `{{ form.non_field_errors }}`, which shipped broken once already (finding F1) |
| 3. Create and list views | Form, both CBVs, both templates, URLs, and the first cross-user isolation test | A weak isolation pattern here propagates into S-03 and S-04 |
| 4. Retire landing, claim root | `LOGIN_REDIRECT_URL` repointed, placeholder deleted, `/` routed, four tests re-pointed | Deleting `landing.html` before its logout form is safely in the base |
| 5. Docs, backlog, deploy | `AGENTS.md` fix, `lessons.md` created, Engineering Backlog, deploy ritual | The first production migration runs unattended with no atomic rollback |

**Prerequisites:** S-01 is `done`. All dependencies already installed — no `uv add` needed. A Railway SSH key registered via `railway ssh keys add` is required before Phase 5's backup step.

**Estimated effort:** ~2-3 sessions across 5 phases; Phases 1 and 3 carry most of the work, Phases 2 and 4 are small.

## Open Risks & Assumptions

- **The migration must be generated by hand and cannot be verified by CI.** `manage.py check` passes with a model/schema mismatch, and `railway.json` runs `migrate` before gunicorn — so a forgotten file ships green and takes production down. `makemigrations --check --dry-run` is the only gate.
- **There is no atomic rollback.** Recovery is redeploy-by-ID from `DEPLOY.md`, and the `/data/db.sqlite3` restore path has never been exercised against production. This deploy is the first that might need it.
- **Nothing but `manage.py check` runs in CI**, and only on push to `master` — so tests, lint, and types are local-only gates. Correctness has to be established before merge, because merge equals production.
- **The stock-`User` decision becomes permanent** with this migration. Whether later slices need per-user profile fields remains a recorded blind spot.
- **The 2026-09-10 hard deadline is after-hours-only work**, and S-02 sits on the critical path to the north star.

## Success Criteria (Summary)

- A logged-in user can create a trip and immediately see it in their own list, with a confirmation that it saved.
- A user with no trips sees a deliberate empty state, and a trip with no attached file is a valid row — the state S-03 depends on.
- One user's trips are provably unreachable by another, asserted against both the context queryset and the rendered page.
