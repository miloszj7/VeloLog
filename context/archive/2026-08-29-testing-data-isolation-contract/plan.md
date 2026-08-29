# Data-Isolation Contract Implementation Plan

## Overview

Rollout Phase 1 of `context/foundation/test-plan.md`, covering Risk #2: *"A logged-in user
reaches another user's trip, or downloads their track file."*

Research established that the phase's opening assumption is already false here — every one
of the five object-scoped routes has a foreign-actor test asserting 404 *plus* a no-leak or
persistence assertion, and `grep 403 tests/` returns zero hits. So this phase does **not**
re-prove ownership per route. It closes the four gaps the existing tests structurally
cannot reach, and adds a declared route inventory whose guard fails loudly when a sixth
object-scoped route appears without a classification.

## Current State Analysis

**The authorization model is one idiom, hand-copied five times, with no shared base.**
All five object-scoped views filter the queryset by owner rather than fetching and then
comparing, so another user's pk is indistinguishable from a nonexistent one:

- `trips/views.py:48-50` — `TripListView.get_queryset`
- `trips/views.py:74-82` — `TripDetailView.get_queryset` (carries the canonical rationale docstring)
- `trips/views.py:122-128` — `TripUpdateView.get_queryset`
- `trips/views.py:153-163` — `TripDeleteView.get_queryset`
- `gpx/views.py:56-65` — `GpxUploadView.get_trip`
- `gpx/views.py:138` — `GpxDownloadView`, the only `trip__owner` traversal (`GpxTrack` has no user FK)

The contract is therefore **404 for an authenticated non-owner** and **302 to
`settings.LOGIN_URL` with an exact `?next=<path>`** for anonymous. There is no
`PermissionDenied`, no `raise_exception`, no `UserPassesTestMixin`, no `handler403`.

**What is not covered**, and why the existing tests cannot reach it:

| ID | Gap | Why the existing tests miss it |
|---|---|---|
| G1 | No test ever issues an HTTP request to a `/media/…` path | Every download test goes through `gpx:download`. The "no URL is served from that prefix" decision is asserted only as a *settings value* (`tests/test_media_storage.py:106-107`) |
| G2 | Nothing asserts the route *inventory* | Ownership is hand-enumerated across five files; route #6 forgetting the idiom ships green |
| G3 | Foreign-actor verb coverage is GET/POST only | The verbs `http_method_names` narrows (`trips/views.py:63,120,151`, `gpx/views.py:42`) are tested for the **owner alone** |
| G4 | `/admin/` has zero non-staff and zero anonymous coverage | `tests/gpx/test_gpx_admin.py` uses `admin_client` throughout |
| G5 | The matrix is one-directional | `other_rider` (`tests/conftest.py:93-95`) is never logged in anywhere in the suite; there is no `other_auth_client` |

### Key Discoveries

- **`http_method_names` is a security control here, not a style preference.** `trips/views.py:151`
  left at the default means a raw `DELETE` destroys a trip and its file with no confirmation page.
- **`LoginRequiredMixin.dispatch` runs ahead of `View.dispatch`'s method check.** So anonymous +
  a disallowed verb yields **302**, while foreign-logged-in + a disallowed verb yields **405** —
  and the 405 fires *before* ownership is consulted, so it discloses nothing either. Both legs are
  contract, and neither is currently pinned for a non-owner.
- **`gpx:download` answers 404 for three distinct causes** — not yours, does not exist, and file
  missing from storage (`gpx/views.py:140-153`). A cell asserting only `== 404` cannot tell them
  apart; this is the structural reason every cell must pair status with a state/body assertion.
- **The storage key is unguessable** — `gpx/models.py:8-17` discards the user filename and uses
  `secrets.token_hex(16)`. G1's probe must therefore build its URL from the real `track.file.url`,
  not a hardcoded path, or it proves nothing about the route that would actually be exposed.
- **WhiteNoise sits ahead of `AuthenticationMiddleware`** (`velo_log/settings.py:66,70`), so
  anything it serves is unauthenticated by construction. It is bound to `STATIC_ROOT` /
  `STATICFILES_DIRS`, and `MEDIA_ROOT` is in neither. `MEDIA_URL = "media/"`
  (`velo_log/settings.py:174`) exists solely so `FileField.url` is well-formed.
- **The only `parametrize` in the suite** is `tests/test_static_references.py:45-69` — a
  module-level uppercase tuple, a typed parameter, and an `assert ..., f"…"` message naming the
  production consequence. That is the template. `pytest.param(..., id=…)` is not yet used here.
- **Escape-free needles are mandatory.** `context/archive/2026-08-23-create-and-list-trips/reviews/impl-review.md:59-76`
  F1: a leak assertion on `"Other's Trip"` passed even while the trip rendered, because Django
  autoescaped the apostrophe. The suite standardized on `"Other Rider Trip"`.
- **An invalid POST against a foreign pk is an existence oracle.**
  `context/archive/2026-08-26-edit-and-delete-trip/research.md:104-107`: a malformed submission
  must 404, not re-render a 200 form-error page. `GpxUploadView.post` resolves the trip before
  touching the form for exactly this reason (`gpx/views.py:46-54`); the equivalent cell on
  `trips:edit` is not covered — `tests/trips/test_trip_edit.py:163-181` posts a *well-formed* body.
- **The project contract already exists in writing** and this phase extends rather than reinvents it:
  `context/archive/2026-08-26-edit-and-delete-trip/plan.md:146-148` — *"owner → 200; other user →
  404 plus a no-leak or persistence assertion; anonymous → 302 to login with `?next=`; wrong verb → 405."*
- **`AGENTS.md` has no access-control Hard Rule.** The owner-scoped-queryset invariant and the
  404-not-403 contract live only in a view docstring and archived research.
- **FR-009 (public/private toggle) is parked for v2** (`context/foundation/roadmap.md:133`). The
  invariant is unconditional today; naming it once, centrally, makes that a one-line change later.

## Desired End State

A single flat test module, `tests/test_ownership_matrix.py`, holds a declared inventory of every
object-scoped route and drives a parametrized route × actor × verb matrix from it. A sixth
object-scoped route added to `trips/urls.py` or `gpx/urls.py` without being classified turns the
suite red. Requesting a real stored track's `file.url` returns 404 for the owner, for a second
logged-in rider, and for an anonymous visitor, with the file's bytes absent from every response.
A logged-in non-staff rider is refused at an admin object route. `AGENTS.md` carries the
invariant as a Hard Rule, and test-plan §6.2 carries the ownership-denial pattern as the
project's answer to "how do I add an isolation test?"

Verified by: `uv run pytest tests/test_ownership_matrix.py -v` passing every cell, and the guard
test failing when a `<int:pk>` route is added to either URLconf without a matching tuple entry.

## What We're NOT Doing

- **Not consolidating the eight existing ownership tests.** They stay in their per-behavior files.
  Their bespoke leak and persistence assertions are the part carrying signal; moving them would
  churn five passing files to gain nothing. The matrix is a completeness layer beside them, and
  some cells will overlap deliberately.
- **Not testing admin as a product surface** (`test-plan.md` §7). Only the boundary cell — a
  non-staff and an anonymous actor are refused. No assertion that staff *can* read every user's data.
- **Not adding a shared `OwnerScopedQuerysetMixin` to the views.** Refactoring the five
  `get_queryset` overrides is production code, out of scope for a test-rollout phase; the guard
  is what protects against route #6 without touching the views.
- **Not opening any CI work.** The matrix is ordinary pytest, already run by
  `.github/workflows/deploy.yml:65`. §5's "ownership/isolation matrix — required after Phase 1"
  gate means the matrix exists in the suite, not a new job.
- **Not writing tests for Risks #1, #3–#7.** Those are §3 Phases 2–5.
- **Not adding an e2e layer.** §4 records that no phase proposes one.
- **Not touching `context/archive/`.**

## Implementation Approach

One flat module, built bottom-up: the declared inventory and its guard first (so the tuple exists
before anything reads it), then the cells the tuple drives, then the two boundary probes that sit
outside the view stack and therefore outside the tuple, then the docs that describe what now exists.

Each route descriptor carries the two things a cell needs and a URL string cannot supply: the verbs
the view accepts, and a **state probe** — a callable that asserts the foreign object was neither
leaked nor mutated. Without the probe half, a 404 passes against a view that did the work and
refused afterwards (`tests/trips/test_trip_edit.py:167`, verbatim house rule) and cannot
distinguish `gpx:download`'s three 404 causes.

## Critical Implementation Details

**Ordering: `LoginRequiredMixin` before the method check.** Anonymous + a disallowed verb is
**302**, not 405 — the login redirect fires first. Foreign-logged-in + a disallowed verb is **405**,
and it fires before `get_queryset` runs, so the response is identical for a real and a nonexistent
pk. Any cell that assumes 405 for an anonymous actor will fail, and any cell that assumes 404 for a
foreign actor on a disallowed verb will fail. Both legs are the contract.

**The media probe must not hardcode a path.** `gpx/models.py:8-17` generates the key with
`secrets.token_hex(16)`, so the only URL that proves anything is the one the model actually
produces: build it from a `make_stored_track` instance's `track.file.url`. A hardcoded
`/media/gpx/1/1/x.gpx` would 404 for the trivial reason that no such file exists, and would keep
passing after a `urlpatterns += static(...)` line was added.

**The media probe's owner cell is the load-bearing one.** The guarantee is that *no route serves
that prefix at all* — not that the prefix is owner-scoped. Omitting the owner actor would leave the
test passing against a media route that had been added and merely happened to be authenticated.

**`gpx_bytes` is package-local to `tests/gpx/`** (`tests/gpx/conftest.py`). A flat module cannot
import it; use `make_stored_track` from `tests/conftest.py:140-166` with inline bytes, which is the
cheaper setup anyway.

## Phase 1: Declared route inventory and URLconf guard

### Overview

Create the module and its descriptor tuple, the introspection guard that keeps the tuple honest,
and the reverse-direction client fixture. No ownership cells yet — this phase delivers the
skeleton and the one test that closes G2.

### Changes Required:

#### 1. Reverse-direction client fixture

**File**: `tests/conftest.py`

**Intent**: `other_rider` exists but is never logged in anywhere in the suite, so every "second
user" assertion runs in one direction only (G5). Add the mirror of `auth_client`.

**Contract**: `other_auth_client(client: Client, other_rider: User) -> Client`, sitting directly
below `auth_client` (`:98-101`) and following its shape exactly — `assert client.login(...)`, same
password constant. Note that `auth_client` and `other_auth_client` share the single `client`
fixture instance, so a test requesting both gets one client logged in twice, not two sessions;
the matrix must request exactly one per test.

#### 2. The route descriptor tuple

**File**: `tests/test_ownership_matrix.py` (new)

**Intent**: Declare, in one place, every object-scoped route and what a cell needs to know about
it. This tuple is both the matrix's parameter source and the thing the guard compares the URLconf
against.

**Contract**: A module-level frozen dataclass — typed, since the suite is `mypy --strict` — with
fields for: the `reverse()` route name; which object owns the pk (`Trip` vs `GpxTrack`, because
`gpx:download` takes a track pk while the other four take a trip pk); the verbs the view accepts;
and a `probe` callable taking the fixture objects plus the response and asserting no leak and no
mutation. The tuple is module-level uppercase, mirroring `STATIC_REFERENCES`
(`tests/test_static_references.py:45-53`).

The five rows and their accepted verbs, verified against the views:

| Route name | pk object | Accepted verbs | Source |
|---|---|---|---|
| `trips:detail` | Trip | GET, HEAD, OPTIONS | `trips/views.py:71` (no narrowing) |
| `trips:edit` | Trip | GET, POST, HEAD, OPTIONS | `trips/views.py:120` |
| `trips:delete` | Trip | GET, POST, HEAD, OPTIONS | `trips/views.py:151` |
| `gpx:upload` | Trip | POST | `gpx/views.py:42` |
| `gpx:download` | GpxTrack | GET, HEAD, OPTIONS | `gpx/views.py:122` (plain `View`, only `get` defined) |

Each row's `probe` asserts the state assertion appropriate to it: the foreign trip name absent
from the body for `trips:detail` / `trips:edit`; the trip still exists for `trips:delete`; no new
`GpxTrack` row for `gpx:upload`; the foreign file's bytes absent from the body for `gpx:download`.
Needles must be escape-free — use `"Other Rider Trip"`, never an apostrophe.

#### 3. The inventory guard

**File**: `tests/test_ownership_matrix.py`

**Intent**: Fail loudly when a `<int:pk>` route is added under `trips` or `gpx` without being
classified in the tuple. This is what closes the "route #6 forgets the idiom" vector — the
regression path research names as Risk #2's real exposure, since no present route is unfiltered.

**Contract**: Walk the resolver from `velo_log.urls`, collect every pattern under the `trips` and
`gpx` namespaces whose route string contains `<int:pk>`, and assert the resulting set of
namespaced route names equals the set declared in the tuple. The failure message must name the
production consequence and the required action — that an unclassified object-scoped route has no
proof it scopes its queryset by owner, and that it must be added to the tuple or explicitly
allowlisted as public. Compare namespaced names (`"trips:detail"`), not view classes, so the
comparison speaks the same vocabulary as the tuple and as `reverse()`.

A route that is genuinely public and pk-bearing would need an explicit allowlist constant; none
exists today, so introduce the constant only if and when one does — an empty allowlist is noise.

**Module docstring**: this file carries four different contracts (404 for a foreign actor, 302 for
anonymous, 405 for a narrowed verb, and — later — no-route-at-all for `/media/`). The docstring
must name all four and say why they cannot be collapsed, in the style of
`tests/test_static_references.py:1-22`.

### Success Criteria:

#### Automated Verification:

- New file imports and collects: `uv run pytest tests/test_ownership_matrix.py --collect-only`
- Guard test passes against the current URLconf: `uv run pytest tests/test_ownership_matrix.py -v`
- Full suite still green: `uv run pytest --cov`
- Strict typing, lint, format, import order pass: `/python-quality-gates`

#### Manual Verification:

- Temporarily add a `path("<int:pk>/share/", ...)` to `trips/urls.py`, confirm the guard fails
  with a message that names the action required, then revert
- The tuple reads as an inventory a future contributor would extend, not as test scaffolding

---

## Phase 2: The route × actor × verb matrix

### Overview

Drive the cells from the Phase 1 tuple. This is the bulk of the phase and closes G3 and G5.

### Changes Required:

#### 1. Foreign-actor cells across all accepted verbs

**File**: `tests/test_ownership_matrix.py`

**Intent**: Prove every object-scoped route answers 404 to a second logged-in user on every verb
it accepts — not just the GET/POST pairs the per-behavior files happen to cover.

**Contract**: Parametrized over (route descriptor × accepted verb). Fixtures build the object owned
by `other_rider`; the request is issued by `auth_client` (i.e. `rider`). Assert `404` **and** the
descriptor's `probe`. HEAD and OPTIONS accept a bodiless response, so their probe leg is the state
assertion (object survives / no row created) rather than a body search — the descriptor's probe
must tolerate an empty body rather than assert against it blindly.

#### 2. Anonymous cells across all accepted verbs

**File**: `tests/test_ownership_matrix.py`

**Intent**: Pin the second, distinct mechanism — `LoginRequiredMixin`, not the owner-scoped
queryset — on every verb.

**Contract**: Same parametrization, unauthenticated `client`. Assert `302` and an exact
`Location` of `f"{reverse('login')}?next={url}"`, matching the established idiom at
`tests/trips/test_trip_delete.py:186`, plus the probe.

#### 3. Disallowed-verb cells for a foreign actor

**File**: `tests/test_ownership_matrix.py`

**Intent**: `http_method_names` is a security control here — `trips/views.py:151` left at the
default lets a raw `DELETE` destroy a trip and its file with no confirmation page. Only the owner
leg is currently pinned. Prove the narrowing also holds for a non-owner, and that it discloses
nothing.

**Contract**: Parametrized over (route descriptor × a verb the descriptor does **not** list),
issued by `auth_client` against `other_rider`-owned objects. Assert `405` **and** the probe.
The 405 is expected *because the method check precedes `get_queryset`* — say so in the docstring,
since a reader will otherwise expect 404 and "fix" the test. `PUT` and `DELETE` are the meaningful
picks; `gpx:upload` additionally excludes `GET`.

#### 4. The reverse direction

**File**: `tests/test_ownership_matrix.py`

**Intent**: Remove the unstated assumption that isolation was only ever tested with `rider` as the
intruder (G5).

**Contract**: One parametrized test over the tuple, roles swapped — objects owned by `rider`,
requested by `other_auth_client` — asserting the same 404 + probe on the route's primary verb.
Not a full verb sweep; the idiom is symmetric by construction and a second full matrix would buy
nothing.

#### 5. The malformed-body existence oracle

**File**: `tests/test_ownership_matrix.py`

**Intent**: A route that re-renders a 200 form-error page for an invalid submission against a
foreign pk confirms the object exists. `gpx:upload` is safe by construction (`gpx/views.py:46-54`
resolves the trip before the form runs); the equivalent cell on `trips:edit` is untested —
`tests/trips/test_trip_edit.py:163-181` posts a well-formed body.

**Contract**: POST a body that fails `TripForm` validation (e.g. a blank `name`, or a `date` that
will not coerce) to `trips:edit` against an `other_rider`-owned trip. Assert `404` — explicitly
**not** 200 — plus the foreign trip's name absent from the body and its stored fields unchanged.
Add the mirror cell on `gpx:upload` (a non-GPX payload against a foreign trip pk) so the
already-safe route is pinned rather than merely believed safe. The failure message must name what
a 200 would mean: that the response disclosed the trip's existence.

### Success Criteria:

#### Automated Verification:

- Every matrix cell passes: `uv run pytest tests/test_ownership_matrix.py -v`
- Cell count matches the declared inventory — no route silently absent from the parametrization
- Full suite green with coverage gate: `uv run pytest --cov`
- `/python-quality-gates` passes

#### Manual Verification:

- Temporarily remove the `filter(trip__owner=…)` from `gpx/views.py:138` and confirm the
  `gpx:download` foreign cells go red — the matrix must actually bite, not merely run
  (`lessons.md` #1, #3)
- Temporarily drop `http_method_names` from `trips/views.py:151` and confirm the disallowed-verb
  cells go red
- Test IDs read legibly in `-v` output — a failure names which route and actor broke without
  opening the file

---

## Phase 3: Boundary probes outside the view stack

### Overview

The two cells that cannot be driven from the route tuple, because neither is a route the project
owns. Closes G1 — the highest-value single test in this phase — and G4.

### Changes Required:

#### 1. The `/media/` exposure probe

**File**: `tests/test_ownership_matrix.py`

**Intent**: The project's entire defense on the "downloads their track file" half of Risk #2 is the
*absence of a route*. A future `urlpatterns += static(settings.MEDIA_URL, …)`, a `WHITENOISE_ROOT`,
or a platform static handler would serve every rider's GPX to any URL holder, and not one existing
test would go red — they all go through `gpx:download`. The current assertion is a settings value
(`tests/test_media_storage.py:106-107`), never a response.

**Contract**: Create a stored track via `make_stored_track` with distinctive inline bytes, take
`track.file.url` (never a hardcoded path — the key is `secrets.token_hex(16)`), and request it as
three actors: the **owner**, a foreign logged-in rider, and an anonymous visitor. Assert `404` for
all three and the distinctive bytes absent from every body. The owner leg is the load-bearing one:
the guarantee is that nothing serves that prefix, not that the prefix is owner-scoped. The failure
message must name the consequence — that a URL under `MEDIA_URL` now resolves, placing every
rider's track outside `AuthenticationMiddleware`, which sits *after* WhiteNoise
(`velo_log/settings.py:66,70`).

Sanity-check the constructed URL starts with `/media/` before requesting it, so a change to
`MEDIA_URL` cannot quietly turn this into a probe of some unrelated path.

#### 2. Admin boundary cells

**File**: `tests/test_ownership_matrix.py`

**Intent**: Both `ModelAdmin`s are deliberately unscoped — any `is_staff` user with model
permissions reads every rider's data (`trips/admin.py:13-22`, `gpx/admin.py:13-29`). The isolation
guarantee therefore reduces to "no non-staff user reaches another user's data," and nothing pins
it. `test-plan.md` §7 excludes admin *as a product surface*; this is the boundary of the guarantee,
the same reasoning §7 already uses to keep the admin file-replacement path tested under Risk #1.

**Contract**: Two tests against an admin object route for an `other_rider`-owned trip
(`admin:trips_trip_change`, reversed like every other URL in the suite): one as a logged-in
non-staff rider, one as anonymous. Assert **302 to the admin login** with the object path in
`?next=` — explicitly not 404, because `AdminSite.admin_view` redirects rather than scoping a
queryset, and a cell copied from the 404 matrix would assert the wrong contract. Both must also
assert the foreign trip's name is absent from the response body. Add a comment stating the
deliberate omission: staff *can* read every user's data, and that is not asserted here because it
is admin-as-product-surface.

### Success Criteria:

#### Automated Verification:

- Media probe and admin cells pass: `uv run pytest tests/test_ownership_matrix.py -v`
- Full suite green: `uv run pytest --cov`
- CI-equivalence run passes with no `.env`:
  `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- `/python-quality-gates` passes

#### Manual Verification:

- Temporarily add `urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)`
  to `velo_log/urls.py` and confirm all three media cells go red — this is the single most
  important verification in the phase, because it is the only proof the probe watches the right thing
- Confirm the media probe fails for the right reason (the bytes are served), not merely because a
  status changed
- Confirm the admin cells' `?next=` carries the real object path

---

## Phase 4: Documentation and rollout state

### Overview

Record the invariant where a future agent will actually read it, and close out the rollout row.
No test code.

### Changes Required:

#### 1. `AGENTS.md` access-control Hard Rule

**File**: `AGENTS.md`

**Intent**: `AGENTS.md` loads every session, and its Hard Rules currently cover `context/archive/`,
`uv add`, the settings module and `MEDIA_ROOT` — nothing about access control. The owner-scoped
-queryset invariant and the 404-not-403 contract live only in a view docstring and archived
research, so nothing in the agent-facing onboarding would stop a future slice adding an unscoped
view (`lessons.md` #5).

**Contract**: One bullet appended to `## Hard Rules`, matching the density of the existing four.
It must state: every view exposing an object by pk scopes its queryset by owner rather than
fetching then comparing; the resulting contract is 404 for a non-owner (never 403 — a 403 discloses
that the pk exists) and 302-to-login for anonymous; and that a new object-scoped route must be
added to `tests/test_ownership_matrix.py`'s inventory, which is what fails when it is not. Note
that the invariant is unconditional only while FR-009 (public/private trips) stays parked for v2
(`context/foundation/roadmap.md:133`), so a reader landing here after FR-009 ships knows the rule
changed rather than assuming it was broken.

#### 2. Test-plan §6.2 cookbook entry

**File**: `context/foundation/test-plan.md`

**Intent**: §6.2 currently reads `TBD — see §3 Phase 1`. Filling it is this phase's contracted
cookbook deliverable, and is what `/10x-tdd` reads in Lesson 2.

**Contract**: Replace the TBD with the four-field entry the other §6 sub-sections use — location
(`tests/test_ownership_matrix.py` for inventory-driven cells; `tests/<app>/` for a route's bespoke
behavior), naming, reference test (name the matrix's foreign-actor cell), and run command. Add the
pattern itself in one line: **status code plus a state or no-leak probe, always** — a 404 alone
passes against a view that did the work and refused afterwards, and cannot distinguish
`gpx:download`'s three 404 causes.

#### 3. Rollout status and gate confirmation

**File**: `context/foundation/test-plan.md`

**Intent**: Advance the orchestrator's state and settle Open Question 5.

**Contract**: §3 Phase 1 row Status → `complete`. §5 "ownership/isolation matrix" row: confirm in
its Notes that the gate is satisfied by the matrix existing in the suite, since
`.github/workflows/deploy.yml` already runs `pytest --cov` on every PR — no new CI job, which
keeps the phase inside the lesson's stated boundary. Bump the "Last updated" line.

#### 4. Change record

**File**: `context/changes/testing-data-isolation-contract/change.md`

**Intent**: Close the change out.

**Contract**: `status: implemented`, `updated: <today>`. Add a Notes line recording the finding
that inverted the brief — ownership coverage already existed on all five routes; the phase closed
G1–G5 instead — so a future reader does not re-open this as a coverage gap.

### Success Criteria:

#### Automated Verification:

- Full suite green: `uv run pytest --cov`
- `/python-quality-gates` passes
- No `TBD` remains in test-plan §6.2: `grep -n "TBD" context/foundation/test-plan.md` shows only
  the entries owned by Phases 2–4

#### Manual Verification:

- The `AGENTS.md` bullet reads as a rule an agent would follow, not as a summary of this change
- §6.2 answers "how do I add an isolation test for a new route?" without the reader opening the plan
- The FR-009 caveat is present, so the rule does not read as broken when the toggle ships

---

## Testing Strategy

This phase *is* tests, so the strategy is what proves the tests themselves have signal
(`lessons.md` #1, #3, #4 — all three record a green gate concealing a real regression).

### Integration tests (the matrix):

- Every object-scoped route × {foreign logged-in, anonymous} × every accepted verb
- Every object-scoped route × foreign logged-in × a rejected verb
- The reverse direction on each route's primary verb
- Malformed-body-against-foreign-pk on `trips:edit` and `gpx:upload`
- `/media/<real key>.gpx` × {owner, foreign, anonymous}
- Admin object route × {non-staff, anonymous}

### Structural test:

- Declared inventory equals the `<int:pk>` routes under `trips` and `gpx`

### Manual mutation checks (per phase, above):

Each phase names a production line to temporarily break and the cells that must go red. These are
the phase's real acceptance criteria — a matrix that runs but does not bite is exactly the
anti-pattern §2 Risk #4 describes. Run them; do not reason about them.

### Explicitly not tested:

Staff access to cross-user data; admin CRUD, list columns and filters; the five views' happy paths
(already covered per behavior).

## Performance Considerations

The matrix multiplies fixtures across roughly 30–40 cells. Build objects per-cell rather than
per-module — the suite's `_media_root_in_tmp_path` autouse fixture (`tests/conftest.py:38-46`)
already scopes storage per test, and module-scoped DB objects would fight `django_db`. Only the
media probe and the `gpx:download` cells need `make_stored_track` (real bytes); everything else can
use the cheaper `make_gpx_track`, which assigns a name only.

## Migration Notes

None — no model, schema or settings change. `other_auth_client` is additive; no existing fixture
changes shape.

## References

- Research: `context/changes/testing-data-isolation-contract/research.md`
- Brief: `context/changes/testing-data-isolation-contract/change.md`
- Strategy: `context/foundation/test-plan.md` §2 (Risk #2), §3 Phase 1, §5, §6.2, §7
- Parametrize template: `tests/test_static_references.py:45-69`
- Assertion house rule: `tests/trips/test_trip_edit.py:167`
- Anonymous-redirect idiom: `tests/trips/test_trip_delete.py:178-200`
- Fixtures: `tests/conftest.py:88-101` (`rider`, `other_rider`, `auth_client`), `:140-166` (`make_stored_track`)
- Prior contract: `context/archive/2026-08-26-edit-and-delete-trip/plan.md:146-148`
- Escape-free-needle precedent: `context/archive/2026-08-23-create-and-list-trips/reviews/impl-review.md:59-76`
- Existence-oracle precedent: `context/archive/2026-08-26-edit-and-delete-trip/research.md:104-107`
- Media-serving decision: `context/archive/2026-08-23-upload-gpx-and-view-map/research.md:469-478`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Declared route inventory and URLconf guard

#### Automated

- [x] 1.1 New file imports and collects — 50b6abf
- [x] 1.2 Guard test passes against the current URLconf — 50b6abf
- [x] 1.3 Full suite still green — 50b6abf
- [x] 1.4 Strict typing, lint, format, import order pass — 50b6abf

#### Manual

- [x] 1.5 Temporary pk route makes the guard fail with an actionable message, then reverted — 50b6abf
- [x] 1.6 The tuple reads as an inventory a contributor would extend — 50b6abf

### Phase 2: The route × actor × verb matrix

#### Automated

- [x] 2.1 Every matrix cell passes — e7b684c
- [x] 2.2 Cell count matches the declared inventory — e7b684c
- [x] 2.3 Full suite green with coverage gate — e7b684c
- [x] 2.4 `/python-quality-gates` passes — e7b684c

#### Manual

- [x] 2.5 Removing `filter(trip__owner=…)` turns the `gpx:download` foreign cells red — e7b684c
- [x] 2.6 Dropping `http_method_names` turns the disallowed-verb cells red — e7b684c
- [x] 2.7 Test IDs name the failing route and actor in `-v` output — e7b684c

### Phase 3: Boundary probes outside the view stack

#### Automated

- [x] 3.1 Media probe and admin cells pass — 2efa865
- [x] 3.2 Full suite green — 2efa865
- [x] 3.3 CI-equivalence run passes with no `.env` — 2efa865
- [x] 3.4 `/python-quality-gates` passes — 2efa865

#### Manual

- [x] 3.5 Adding a `static(MEDIA_URL, …)` route turns all three media cells red — 2efa865
      (`static()` is itself a documented no-op at `DEBUG=False`, per test-plan.md §6.7; the
      mutation actually run substituted a `document_root`-based `re_path`, the closer analogue
      of a real platform static handler)
- [x] 3.6 The media probe fails because bytes are served, not merely on a status change — 2efa865
      (true only when the media test ran first in the process — `document_root` binds at
      URLconf import time while `MEDIA_ROOT` is rebound per test; the resolver-level assertion
      added in the impl review, `a7e3269`, is order-independent and supersedes this leg)
- [x] 3.7 The admin cells' `?next=` carries the real object path — 2efa865

### Phase 4: Documentation and rollout state

#### Automated

- [x] 4.1 Full suite green — 1f6857c
- [x] 4.2 `/python-quality-gates` passes — 1f6857c
- [x] 4.3 No `TBD` remains in test-plan §6.2 — 1f6857c

#### Manual

- [x] 4.4 The `AGENTS.md` bullet reads as a rule, not a change summary — 1f6857c
- [x] 4.5 §6.2 answers "how do I add an isolation test for a new route?" standalone — 1f6857c
- [x] 4.6 The FR-009 caveat is present — 1f6857c
