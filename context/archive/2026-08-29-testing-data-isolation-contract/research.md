---
date: 2026-08-29T14:53:46+02:00
researcher: Miłosz Jarzynka
git_commit: 2222a4181c034c423af0260e9edcbbbc8b34ff5e
branch: chore/testing-data-isolation-contract
repository: miloszj7/VeloLog
topic: "Data-isolation contract — route × actor × verb inventory for test-plan Phase 1 (Risk #2)"
tags: [research, codebase, authorization, ownership, trips, gpx, testing]
status: complete
last_updated: 2026-08-29
last_updated_by: Miłosz Jarzynka
---

# Research: Data-isolation contract (test-plan §3 Phase 1, Risk #2)

**Date**: 2026-08-29T14:53:46+02:00
**Researcher**: Miłosz Jarzynka
**Git Commit**: `2222a418` (equal to the pushed `origin/master` tip)
**Branch**: `chore/testing-data-isolation-contract`
**Repository**: miloszj7/VeloLog

## Research Question

From `context/changes/testing-data-isolation-contract/change.md` and `test-plan.md` §2
Risk Response Guidance, row #2. Research must ground three things:

1. **The full route inventory** — every trip and track route.
2. **Whether not-found or forbidden is the contract** (not-found avoids disclosing existence).
3. Which routes already have coverage, so the phase closes real gaps rather than
   re-proving what is proven.

The brief names the assumption to challenge — *"that anonymous-redirect coverage implies
ownership coverage"* — and the anti-pattern to avoid — *"testing three routes and
declaring the guardrail covered."*

## Summary

**The brief's stated assumption is already false in this repo, and that is the single most
important finding.** Every one of the five object-scoped routes already has a
second-user test that asserts 404 *plus* a no-leak or persistence assertion. The
anonymous-vs-ownership distinction the phase was opened to prove has been maintained
deliberately since S-02, is documented in view docstrings, and is enforced by a uniform
idiom. **`grep 403 tests/` still returns zero hits, and no route leaks.**

So Phase 1 is not a coverage-gap phase. Re-running it as one would produce eight
near-duplicate tests, land squarely on the anti-pattern the brief warns about in a new
form — *proving again what is proven while the actual holes stay open* — and inflate
coverage without catching a named regression (`lessons.md` #3, #4).

The real exposure for Risk #2 sits in four places the existing tests structurally cannot
reach:

| ID | Gap | Why it is the real risk | Cost |
|---|---|---|---|
| **G1** | **No test ever issues an HTTP request to a `/media/…` path.** The "files are never served outside the view stack" decision is asserted only as a *settings value* (`tests/test_media_storage.py:106-107`), never as a response. | This is the whole second half of Risk #2 — "downloads their track file". A future `urlpatterns += static(...)`, a `WHITENOISE_ROOT`, or a platform static handler would serve every rider's GPX to any URL holder, and **not one existing test would go red** — they all go through `gpx:download`. | ~1 test |
| **G2** | **Nothing asserts the route *inventory*.** Ownership coverage exists but is hand-enumerated across five files; there is no shared mixin (the idiom is copy-pasted five times) and no guard that a newly added object-scoped route is classified. | The live risk is not "a route is unfiltered today" — none is — but "route #6 forgets the idiom." Today that ships green. | ~1 guard + matrix |
| **G3** | **Verb coverage is asymmetric.** Foreign-actor cells exist for GET/POST only; the verbs the views deliberately narrow via `http_method_names` are tested for the *owner* alone. | `trips/views.py:151` is load-bearing, not stylistic — left at default, raw `DELETE` destroys a trip and its file with no confirmation page. Only the owner leg is pinned. | free inside a matrix |
| **G4** | **Django admin has zero non-staff and zero anonymous coverage.** Both `ModelAdmin`s are deliberately cross-user. | Admin is the *boundary* of the isolation guarantee. Nothing pins "a logged-in non-staff rider is refused." Needs an explicit in/out decision (see Open Questions). | ~2 tests |

G1 is the highest-value single test in this phase.

## Detailed Findings

### 1. Route inventory (complete)

Read in full: `velo_log/urls.py`, `accounts/urls.py`, `trips/urls.py`, `gpx/urls.py`.
These are the only four URLconfs in the repo.

**Object-scoped routes — the isolation matrix rows (5):**

| URL pattern | Name | View (file:line) | Methods accepted | Object |
|---|---|---|---|---|
| `/trips/<int:pk>/` | `trips:detail` | `trips/views.py:71` | GET (+HEAD/OPTIONS) | Trip |
| `/trips/<int:pk>/edit/` | `trips:edit` | `trips/views.py:103` | GET, POST, HEAD, OPTIONS (`:120`) | Trip |
| `/trips/<int:pk>/delete/` | `trips:delete` | `trips/views.py:131` | GET, POST, HEAD, OPTIONS (`:151`) | Trip |
| `/gpx/trips/<int:pk>/upload/` | `gpx:upload` | `gpx/views.py:28` | POST only (`:42`) | Trip (upload target) |
| `/gpx/tracks/<int:pk>/download/` | `gpx:download` | `gpx/views.py:122` | GET only | GpxTrack |

**Collection / global routes (no pk, but two carry ownership cells):**

- `/trips/` — `trips:list`, `trips/views.py:45`. Owner-scoped `get_queryset`; the isolation
  assertion is *absence from the list*, not a status code.
- `/trips/new/` — `trips:create`, `trips/views.py:53`. No pk, but carries the
  **owner-forging** cell (POST `owner=<other pk>`).
- `/` root redirect · `/accounts/signup/` · `/accounts/login/` · `/accounts/logout/` ·
  `/healthz/` — public by design.
- `/admin/` — `velo_log/urls.py:205`, see §5.

**Not routed, and load-bearing:** there is no `static(settings.MEDIA_URL, ...)` entry in
any URLconf, and no `DEBUG` branch adding one. `MEDIA_URL = "media/"`
(`velo_log/settings.py:174`) exists solely so `FileField.url` is well-formed. WhiteNoise
(`velo_log/settings.py:66`) sits *before* `AuthenticationMiddleware` (`:70`) — so anything
it serves is unauthenticated by construction — but it is bound to `STATIC_ROOT` /
`STATICFILES_DIRS`, and `MEDIA_ROOT` is in neither.

### 2. The contract is 404, uniformly, and deliberately

All five object-scoped views use the *filter-the-queryset* form. None uses the
*fetch-then-compare* form, so there is no post-fetch ownership comparison anywhere to get
wrong.

- `trips/views.py:48-50` — `TripListView.get_queryset` → `filter(owner=...)`
- `trips/views.py:74-82` — `TripDetailView.get_queryset`
- `trips/views.py:122-128` — `TripUpdateView.get_queryset`
- `trips/views.py:153-163` — `TripDeleteView.get_queryset`
- `gpx/views.py:56-65` — `GpxUploadView.get_trip` → `get_object_or_404` on an owner-filtered qs
- `gpx/views.py:138` — `GpxDownloadView` → `filter(trip__owner=...)`

The rationale is stated in-code at `trips/views.py:77-80`:

> Scoping here — rather than checking ownership after fetching — is what makes another
> user's trip 404 instead of 403, so a pk that exists is indistinguishable from one that
> does not. The owner-scoped queryset is the project's entire authorization story.

Repo-wide, there is **no** `PermissionDenied`, no `raise_exception`, no
`UserPassesTestMixin` / `PermissionRequiredMixin`, and no `handler403`/`handler404`.
Unauthenticated requests take `LoginRequiredMixin`'s redirect branch: **302** to
`settings.LOGIN_URL` (`velo_log/settings.py:278`) with an exact `?next=<path>`.

**Answer to research question 2: not-found, 404, for an authenticated non-owner; 302-to-login
for anonymous. A test asserting 403 would assert the wrong contract.**

One ambiguity worth carrying into the plan: `gpx:download` answers 404 for *three* distinct
causes — not yours, does not exist, and **file missing from storage**
(`gpx/views.py:140-153`). A cell asserting only `== 404` cannot tell them apart. This is
the structural reason the existing download test also asserts the foreign bytes are absent,
and why new cells must pair status with a body/state assertion.

### 3. Ownership traversal

- `Trip → User` is **direct**: `trips/models.py:12-16`, `owner = FK(AUTH_USER_MODEL, related_name="trips")`.
- `GpxTrack → User` is **indirect, via Trip only**: `gpx/models.py:28`, `trip = FK(Trip, related_name="tracks")`. **There is no user FK on `GpxTrack`.**

So every track-route check must traverse `trip__owner` — which `gpx/views.py:138` does as a
single JOIN, leaving no window where the track is loaded before ownership is known.

Owner is never client-supplied: `TripForm.Meta.fields = ("name", "date", "description")`
(`trips/forms.py:21`), and `form.instance.owner` is overwritten server-side
(`trips/views.py:67`). `GpxTrackForm.Meta.fields = ("file",)` (`gpx/forms.py:33`), so a
posted `trip=<foreign pk>` is not even a form field.

### 4. The download path is not an isolation hole — but its *absence of a media route* is untested

`gpx/views.py:141` opens through the storage API and `:154-158` returns a `FileResponse`.
No redirect, no `.url`, no `X-Accel-Redirect`. The storage key is unguessable:
`gpx/models.py:8-17` discards the user-supplied filename and uses
`f"gpx/{instance.trip.owner_id}/{instance.trip_id}/{secrets.token_hex(16)}.gpx"` — 128 bits
from `secrets`, not `random`. The user's filename survives only in `original_filename`.

**But (G1):** I verified directly that no test in the suite issues an HTTP request to a
`/media/...` path. The only matches are `tests/test_media_storage.py:106-107`, which assert
`settings.MEDIA_URL != "/"` and `.startswith("/media/")` — a settings value, not a response —
plus two comments in `tests/gpx/test_gpx_download.py:120` and `tests/gpx/test_gpx_upload.py:135`
that *describe* the hazard without asserting it. The archived decision
(`context/archive/2026-08-23-upload-gpx-and-view-map/plan.md:250-252`) says no URL is ever
served from that prefix; nothing enforces it.

### 5. Django admin — the boundary of the guarantee

Both `ModelAdmin`s are registered with **no `get_queryset()` override**:
`trips/admin.py:13-22` (`list_display` includes `owner`) and `gpx/admin.py:13-29`
(`raw_id_fields = ("trip",)` chosen precisely because a plain select "renders every Trip in
the database across all users"). Any `is_staff` user with model permissions reads, changes
and deletes **every** user's data. This is intentional — `TripAdmin.view_on_site = False`
(`trips/admin.py:22`) exists *because* the default link would send staff to the owner-scoped
route and 404, which neatly confirms the app-side scoping bites even for staff.

The isolation guarantee therefore reduces to: **no non-staff user reaches another user's
data.** The suite has no test of the non-staff or anonymous actor against `/admin/`
(`tests/gpx/test_gpx_admin.py` uses `admin_client` throughout). Note the admin's contract
differs — it redirects to the admin login rather than 404ing — so this cell cannot simply be
appended to the 404 matrix.

### 6. Existing coverage — the actual matrix as of `2222a418`

Legend: ✅ covered · ❌ absent · n/a not applicable.

| Route | Verb | Anonymous | Foreign logged-in | Evidence |
|---|---|---|---|---|
| `trips:list` | GET | ✅ | ✅ (exclusion + no leak) | `tests/trips/test_trip_list.py:20-30`, `:41-46` |
| `trips:create` | GET | ✅ | n/a | `tests/trips/test_trip_creation.py:83-88` |
| `trips:create` | POST | ✅ | owner-forge ✅ | `:71-80`, `:52-68` |
| `trips:detail` | GET | ✅ | ✅ 404 + no leak | `tests/trips/test_trip_detail.py:44-52`, `:32-41` |
| `trips:edit` | GET | ✅ | ✅ 404 + no leak | `tests/trips/test_trip_edit.py:184-192`, `:149-160` |
| `trips:edit` | POST | ✅ | ✅ 404 + unchanged | `:195-217`, `:163-181`; owner-forge `:123-146` |
| `trips:edit` | PUT | ❌ | ❌ | owner-only 405 at `:221` |
| `trips:delete` | GET | ✅ | ✅ 404 + survives | `tests/trips/test_trip_delete.py:178-186`, `:148-160` |
| `trips:delete` | POST | ✅ | ✅ 404 + survives | `:189-200`, `:163-175` |
| `trips:delete` | DELETE | ❌ | ❌ | owner-only 405 + survives at `:214` |
| `gpx:upload` | POST | ✅ | ✅ 404 + no row | `tests/gpx/test_gpx_upload.py:434-447`, `:419-431` |
| `gpx:upload` | GET | ❌ | ❌ | owner-only 405 at `:450-459` |
| `gpx:download` | GET | ✅ | ✅ 404 + bytes absent | `tests/gpx/test_gpx_download.py:116-132`, `:77-93` |
| **`/media/<key>.gpx`** | GET | **❌** | **❌** (and owner ❌) | **nothing — G1** |
| `admin:trips_trip_change` | GET | **❌** | **❌ non-staff** | only `admin_client` — G4 |

**One-way direction (G5).** Verified directly: `other_rider`
(`tests/conftest.py:93-95`) is *never logged in anywhere in the suite*. Every "second user"
test is `auth_client` (always `rider`, `tests/conftest.py:98-101`) requesting
`other_rider`-owned data. There is no `other_auth_client` fixture. Low intrinsic value —
the idiom is symmetric by construction — but free inside a parametrized matrix, and it
removes an unstated assumption.

### 7. Conventions the new tests must match

- **Fixtures**: `rider`, `other_rider`, `auth_client` (`tests/conftest.py:88-101`);
  `make_stored_track` writes real bytes under a per-test `MEDIA_ROOT`
  (`tests/conftest.py:140-166`, autouse override at `:38-46`). `trip` fixtures are
  *package-local* (`tests/gpx/conftest.py:30-32`) and duplicated per module — there is no
  project-wide trip factory.
- **`@pytest.mark.django_db` is written explicitly above every DB test.** No autouse, no
  module-level `pytestmark`.
- **URLs always via `reverse()`**, with a module-level helper for repeats
  (`tests/gpx/test_gpx_download.py:16-17`). Hardcoded paths appear twice, both for `/`.
- **Assertion style is the house rule**: status code **plus** a state/content assertion
  that would fail against a "did the work, then refused" implementation. Verbatim from
  `tests/trips/test_trip_edit.py:167`: *"The 404 alone would pass against a view that saved
  first and refused afterwards."*
- **`parametrize` is used exactly once** in the whole suite —
  `tests/test_static_references.py:45-69` — a module-level uppercase tuple, a typed
  parameter, and an `assert ..., f"..."` message naming the production consequence. That is
  the template for a route × actor matrix. `pytest.param(..., id=...)` is not yet used.
- **Fully typed** (`mypy --strict`), long prose test names, docstrings that name *the wrong
  implementation the test rejects*.
- Cross-cutting concerns live flat at `tests/test_*.py`; app-specific under `tests/<app>/`.
  A file spanning `trips:` and `gpx:` routes has **no precedent** — see Open Questions.

### 8. Two traps this phase must not walk into

1. **Vacuous needle (already burned here).**
   `context/archive/2026-08-23-create-and-list-trips/reviews/impl-review.md:59-76` F1: a
   cross-user test named the fixture trip `"Other's Trip"`; Django autoescapes the
   apostrophe, so `assert "Other's Trip" not in response.content.decode()` passed even when
   the trip *was* rendered. The suite standardized on the escape-free `"Other Rider Trip"`.
   Any new leak assertion must use an escape-free needle.
2. **Invalid POST against a foreign pk is an existence oracle.**
   `context/archive/2026-08-26-edit-and-delete-trip/research.md:104-107`: an invalid
   submission must 404, not re-render a 200 form-error page, or it confirms the trip exists.
   `GpxUploadView.post` resolves the trip before touching the form for exactly this reason
   (`gpx/views.py:46-54`). The equivalent cell on `trips:edit` — *malformed* body + foreign
   pk — is not obviously covered by `tests/trips/test_trip_edit.py:163-181`, which posts a
   well-formed body.

## Code References

Permalinks at `2222a418` (pushed): `https://github.com/miloszj7/VeloLog/blob/2222a4181c034c423af0260e9edcbbbc8b34ff5e/<path>#L<line>`

- `trips/views.py:74-82` — `TripDetailView.get_queryset`; the canonical 404-not-403 docstring
- `trips/views.py:120`, `trips/views.py:151` — `http_method_names` narrowing; `:151` prevents a confirmation-free `DELETE`
- `trips/views.py:122-128`, `trips/views.py:153-163` — edit/delete owner scoping, applies to POST via `get_object()`
- `gpx/views.py:46-54` — upload resolves the trip *before* the form runs
- `gpx/views.py:138` — `filter(trip__owner=...)`, the only track→user traversal
- `gpx/views.py:140-153` — the third 404 cause: file missing from storage
- `gpx/models.py:8-17` — storage key: discarded filename, `secrets.token_hex(16)`
- `velo_log/settings.py:66,70` — WhiteNoise ahead of `AuthenticationMiddleware`
- `velo_log/settings.py:171-174` — `MEDIA_URL` deliberately inert
- `velo_log/urls.py:203-216` — full `urlpatterns`; no media route in any branch
- `trips/admin.py:13-22`, `gpx/admin.py:13-29` — unscoped by design
- `tests/conftest.py:88-101` — `rider`, `other_rider`, `auth_client`
- `tests/test_static_references.py:45-69` — the only `parametrize` in the suite; matrix template
- `tests/test_media_storage.py:104-111` — asserts the `MEDIA_URL` *setting*, not a response

## Architecture Insights

- **The authorization model is one idiom, hand-copied five times, with no shared base.**
  `trips/views.py:48,74,122,153` and `gpx/views.py:56` are near-identical `get_queryset`
  overrides. Nothing structural forces a sixth view to follow. This — not any present
  defect — is the regression vector Risk #2 actually faces, and it is what argues for an
  inventory guard (G2) over more per-route duplicates.
- **404 as non-disclosure is a deliberate, load-bearing choice**, consistently applied, and
  it makes three different failures indistinguishable by status alone. Body/state
  assertions are therefore not optional decoration here; they are what makes a cell mean
  anything.
- **`http_method_names` is a security control in this codebase, not a style preference**
  (`trips/views.py:151`).
- **Everything outside the Django view stack is outside authorization by construction**
  (`context/archive/2026-08-23-upload-gpx-and-view-map/research.md:568-571`). The project's
  entire defense there is the *absence* of a route — the single least-tested kind of
  guarantee, and precisely G1.
- **`AGENTS.md` has no access-control hard rule.** Its Hard Rules cover `context/archive/`,
  `uv add`, the settings module, and `MEDIA_ROOT`. The owner-scoped-queryset invariant and
  the 404-not-403 contract live only in a view docstring and archived research — so nothing
  in the agent-facing onboarding doc would stop a future slice adding an unscoped view.
  `lessons.md` #5 says the doc fix belongs in the slice that invalidates it; this phase is
  the natural place.

## Historical Context (from prior changes)

- `context/foundation/prd.md:43` — Guardrail: *"One authenticated user can never **read,
  modify, or delete** another user's private trips under any circumstance."* Three verbs —
  a GET-only matrix does not cover this line.
- `context/foundation/prd.md:105-106` — two *distinct* requirements: unauthenticated
  visibility and cross-user isolation. They drive different mechanisms
  (`LoginRequiredMixin` vs. owner-scoped queryset), which is why both actor rows exist.
- `context/archive/2026-08-26-edit-and-delete-trip/plan.md:146-148` — the pre-existing
  project contract, already written down: *"Every new owner-scoped surface reproduces the
  fixed test matrix: owner → 200; other user → 404 plus a no-leak or persistence assertion;
  anonymous → 302 to login with `?next=`; wrong verb → 405."* This phase should **extend**
  that, not reinvent it.
- `context/archive/2026-08-23-create-and-list-trips/plan.md:69` — owner must never be
  client-supplied; the mass-assignment cells on create and edit exist because of this.
- `context/archive/2026-08-23-upload-gpx-and-view-map/research.md:469-478` (conflict C1) —
  data isolation is what *ruled out* serving GPX from a conventional `MEDIA_URL` path. The
  hazard was identified, the design changed, and the decision was never given a test.
- `context/archive/2026-08-23-upload-gpx-and-view-map/reviews/impl-review-phase-4.md:200-216`
  (F8) — the download route's cross-user test was *originally* status-code-only and was
  fixed to assert the foreign bytes are absent. Direct precedent for Risk #2's download half.
- `context/archive/2026-08-26-edit-and-delete-trip/reviews/impl-review.md:195-208` (F7) —
  a missing *unauthenticated-POST* test; the write leg is the one that matters. Evidence
  that the matrix must be routes × actors × **verbs**.
- `context/foundation/roadmap.md:133` — **FR-009 (public/private toggle) is parked for v2.**
  The invariant is unconditional *today* ("no trip is ever visible to a non-owner") and
  becomes conditional when FR-009 lands. Naming the invariant once, centrally, makes that a
  one-line change instead of a rewrite of every assertion.
- `context/changes/gpx-upload-orphan-file/reviews/` — checked; **no** authorization or
  ownership findings there (all four concern `reconcile_media`).

## Related Research

- `context/archive/2026-08-26-edit-and-delete-trip/research.md:83-101` — the prior route/authz
  inventory, superseded by §1 above but still the origin of the 404 rationale
- `context/archive/2026-08-23-upload-gpx-and-view-map/research.md:274-276,568-571` — media
  serving and the WhiteNoise-before-auth analysis
- `context/foundation/test-plan.md` §2, §3 Phase 1 — the brief this research answers

## Open Questions

These need a decision in `/10x-plan`; none blocks starting.

1. **Does Phase 1 keep the existing eight ownership tests where they are?**
   Recommendation: **yes** — leave them in their per-behavior files and add the matrix as a
   *completeness layer* beside them. Consolidating would churn five passing files and risk
   losing their bespoke leak/persistence assertions, which are the part that carries signal.
   The matrix's job is the inventory guard, not re-implementation.
2. **Is `/admin/` in scope (G4)?** `test-plan.md` §7 excludes "admin as a product surface,"
   but "a non-staff rider is refused at `/admin/`" is an *isolation boundary*, not an admin
   feature — the same reasoning §7 already uses to keep the admin's file-replacement path
   tested under Risk #1. Recommendation: in scope, two tests, with the differing contract
   (redirect to admin login, not 404) pinned explicitly.
3. **Where does a cross-app matrix file live?** No precedent exists for a file spanning
   `trips:` and `gpx:` routes. Flat `tests/test_ownership_matrix.py` matches how every other
   cross-cutting concern is filed; `tests/trips/` would misfile the gpx rows. Note
   `gpx_bytes` is package-local to `tests/gpx/`, so a flat file must use
   `make_stored_track` with inline bytes instead — which is also the cheaper setup.
4. **How far should the G2 inventory guard reach?** Options: (a) a declared tuple of
   object-scoped routes that the matrix drives, plus a test asserting the tuple matches the
   URLconf's `<int:pk>` patterns under `trips`/`gpx` — fails loudly when route #6 appears;
   (b) matrix only, no guard. (a) is what actually closes the "future route forgets the
   idiom" vector, and costs one introspection test.
5. **Does §5's "ownership/isolation matrix — required after Phase 1" gate need CI work?**
   It appears not: it is ordinary pytest, already run by `.github/workflows/deploy.yml:65`.
   Confirm the gate row means "the matrix exists in the suite" rather than a new job, so the
   plan does not open CI work this lesson explicitly excludes.
6. **Should this phase add the missing `AGENTS.md` access-control hard rule?** `lessons.md`
   #5 argues yes. It is a doc edit, not test code, so it does not cross the Lesson-2 boundary.
