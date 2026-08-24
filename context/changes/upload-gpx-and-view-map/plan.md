# Upload a GPX file and view the route as a map — Implementation Plan

## Overview

Deliver roadmap slice **S-03**, the product's north star: a logged-in user uploads a GPX
file to one of their trips and opens the trip detail view to see the route drawn on a
non-interactive Leaflet map — with a deliberate empty state when no file is attached and a
deliberate error state when a file cannot be parsed. Never a blank page, never a silent
failure.

Five pre-existing codebase blockers stand between the current repo and any upload at all,
and four of them pass every CI gate green. Removing them is the first half of this plan;
the feature is the second half.

## Current State Analysis

**Verified at runtime against this settings module (2026-08-24), not inferred:**

```
STORAGES        = {'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
MEDIA_ROOT      = ''
MEDIA_URL       = '/'
default_storage -> InvalidStorageError: Could not find config for 'default' in settings.STORAGES.
```

| # | Blocker | Caught by CI today? |
|---|---|---|
| B1 | `STORAGES` (`velo_log/settings.py:127-131`) has no `"default"` alias. Django overwrites the whole setting rather than merging, so `default_storage` raises. | ❌ 500s on the first upload in production |
| B2 | `MEDIA_ROOT` is `''`; `MEDIA_URL` resolves to `"/"`, colliding with the root `RedirectView` (`velo_log/urls.py:38`) | ❌ No |
| B3 | No media-serving mechanism. whitenoise is registered for `STATIC_ROOT` only, snapshots the file list at boot, and sits at `MIDDLEWARE` position 2 — *before* `AuthenticationMiddleware` | ❌ No |
| B4 | `collectstatic --noinput` runs inside `railway.json:4`'s `startCommand`, `&&`-chained before `migrate` and `gunicorn`. A non-zero exit means the app never boots. No CI step runs `collectstatic`. | ❌ No |
| B5 | `tests/test_coverage_scope.py:49-54` fails the build the moment a `gpx` app is installed without a matching `[tool.coverage.run] source` entry | ✅ Yes — a good failure |

What else exists today:

- **No trip detail view and no detail URL.** `trips/urls.py:8-9` defines only `trips:list`
  and `trips:create`; no pk-capturing route exists anywhere in the project.
  `trips/templates/trips/trip_list.html:9-16` has no per-trip link.
- **`Trip`** (`trips/models.py:5-21`): `name`, `date`, `description`, `owner` FK with
  `related_name="trips"`. No `clean()`, no validators, no `get_absolute_url()`.
- **Authorization is entirely the owner-scoped queryset** (`trips/views.py:27-29`,
  `:40-43`). There is no object-permission layer, so anything served outside the Django
  view stack is outside authorization by construction.
- **Zero `{% static %}`, zero `{% load static %}`, zero CSS, zero `class=` attributes,
  zero `enctype`, zero `FileField`** in the repo's history. `templates/base.html` has only
  `title` and `content` blocks and no `<meta name="viewport">`.
- **`gpxpy` is not in `uv.lock`** (30 packages, zero hits). `.github/workflows/deploy.yml:28`
  runs `uv sync --locked` and fails on lockfile drift.
- **Test fixtures** are exactly `_disable_ssl_redirect` (autouse), `rider`, `other_rider`,
  `auth_client` (`tests/conftest.py`). No `SimpleUploadedFile`, no `tmp_path`, no
  `MEDIA_ROOT` usage anywhere. Coverage baseline: 121 statements, 93.39%, 30 tests.

## Desired End State

A user logs in, opens a trip from their list, and lands on a trip detail page. If the trip
has no track, the page shows a clear empty state alongside an upload form. They choose a
`.gpx` file and submit; the file is validated and parsed server-side, persisted to the
Railway Volume, and the page re-renders with the route drawn as a polyline on an
OpenStreetMap tile layer, start and end marked, the view fitted to the track's bounds, and
all pan/zoom/drag interaction disabled. A link lets them download the original file back.
Uploading again replaces the track. A file that is too large, not `.gpx`, or not parseable
is rejected inline with a visible message and nothing is written.

**Verification**: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
passes with the new app in coverage scope; `uv run python manage.py collectstatic --noinput`
exits 0; the flow above completes end to end against a real browser on a deployed instance.

### Key Discoveries

- **B1 is invisible to every gate because the binding is lazy.** `FileField.__init__`
  assigns the unevaluated `LazyObject` (`django/db/models/fields/files.py:251`); it resolves
  only on `storage.save` or `storage.url`. The only STORAGES system check validates the
  *staticfiles* alias (`django/contrib/staticfiles/checks.py:24-29`). This is the same shape
  as `context/foundation/lessons.md` rule #9 and needs the same mitigation: a test that
  performs the real operation.
- **`leaflet.css` 1.9.4 contains `url(images/layers.png)`, `url(images/layers-2x.png)`, and
  `url(images/marker-icon.png)`.** `CompressedManifestStaticFilesStorage` raises
  `ValueError` on an unresolvable reference (`django/contrib/staticfiles/storage.py:144-147`),
  re-raised by the management command — which, given B4, is a boot outage.
  `WHITENOISE_MANIFEST_STRICT` does not relax this path.
- **Leaflet's JS builds `marker-icon-2x.png` / `marker-shadow.png` URLs at runtime**, which
  the hashed manifest never rewrites — silent 404s. Passing explicit `iconUrl`s through
  `{% static %}` sidesteps default-icon resolution entirely.
- **Leaflet 1.9.4 API verified against `leafletjs.com/reference.html`** (which states "This
  reference reflects Leaflet 1.9.4"), closing the two load-bearing gaps
  `research/leaflet-1.9.4-context7-docs.md:153-154` left open. Interaction options confirmed
  verbatim: `dragging`, `scrollWheelZoom`, `touchZoom`, `doubleClickZoom`, `keyboard`,
  `boxZoom`, `zoomControl`, `attributionControl` (all default `true`), plus `tapHold`.
  `fitBounds` options confirmed: `padding`, `paddingTopLeft`, `paddingBottomRight`,
  `maxZoom`, `animate`. The nested-array bounds expression `[[lat,lng],[lat,lng]]` is a
  documented 1.x form (`leafletjs.com/examples/crs-simple`).
- **`gpxpy` 1.6.2 is a clean adopt** — pure-Python, zero dependencies, Apache-2.0, ships
  `py.typed`, verified executing on this repo's CPython 3.14.5 with `backend = STDLIB`.
  Do **not** add `lxml`: it silently switches gpxpy's parser backend and changes
  entity-resolution defaults with no gate that would notice.
- **The stdlib backend rejects XXE but expands internal entities.** Measured on this venv's
  CPython 3.14: an *external* entity reference raises `ParseError: undefined entity`, while
  *internal nested* entity definitions expand — four levels reached 10,000 characters, and
  `xml.etree.ElementTree` is documented-vulnerable to billion laughs. So "XXE" and
  "entity expansion" are two different outcomes here, and only the first is free. A file
  well under the 10 MB cap can expand to gigabytes of memory at upload time on an endpoint
  any authenticated user can reach — which is why Phase 4 §3 rejects DTDs outright rather
  than relying on the backend (see Critical Implementation Details).
- **The `TYPE_CHECKING` base-alias idiom is mandatory** for every Django generic
  (`trips/views.py:14-21`, `trips/forms.py:7-10`, `trips/admin.py:7-10`) — django-stubs
  generics are not subscriptable at runtime.
- **Ownership yields 404, not 403** (`trips/views.py:27-29`). There is no object-permission
  mixin in the repo and this slice does not introduce one.

## What We're NOT Doing

- **No `leaflet-gpx`** — its value (parse + stats in the browser) is entirely redundant once
  `gpxpy` parses server-side, its published release and its GitHub README document two
  incompatible Leaflet majors, and Context7 does not index it at all.
- **No `@raruto/leaflet-elevation`, no d3, no elevation profile chart** — it serves a parked
  non-FR idea, is GPL-3.0 (not "MIT-style" as `research/map-library-research.md:41` claims),
  and pulls three peer dependencies.
- **No Leaflet 2.0** — still alpha, release date reset to "unknown" in Apr 2026. Pin 1.9.4.
- **No `lxml`.**
- **No CDN** — Leaflet is vendored. No SRI convention needs inventing.
- **No interactive map** (FR-015, parked v2). No public/private toggle (FR-009). No multiple
  tracks per trip in v1 behaviour (FR-011 parked) — though the schema supports it.
- **No trip stats** — distance/duration is S-05. This plan persists the parsed track in a
  shape S-05 can build on, and adds no second dependency for it.
- **No trip edit/delete** — that is S-04.
- **No point-count cap or downsampling.** Considered and declined. The 10 MB size cap is the
  only limit on point count in v1 — see Performance Considerations for what that does and
  does not bound. Recorded as an open risk in the brief.
- **No request-body size limit.** The 10 MB cap is a validation rule, not a resource bound:
  `clean_file()` runs only after Django has already received the whole request body and
  spooled it to a `TemporaryUploadedFile`. Nothing upstream caps body size — gunicorn has no
  body limit, and `DATA_UPLOAD_MAX_MEMORY_SIZE` does not apply to file-upload fields. A
  single multi-gigabyte POST therefore fills the container's temp disk before any validation
  code runs. Accepted for v1: the endpoint is behind `LoginRequiredMixin` on a near-private
  app, the same posture already recorded for the residual concurrent-signup race. It is
  accepted **explicitly**, not described as bounded — a reader who believes the cap is a
  resource bound will never revisit it.
- **No quarantine store for rejected uploads.**
- **No `LOGGING` configuration** — E-06 stays open; its trigger has not fired.
- **No branch protection change** — E-02 stays open.

## Implementation Approach

Six phases in dependency order, each leaving the repo working and committable.

Phases 1–2 remove the blockers and lay the data layer with no user-visible change. Phase 3
creates the trip detail surface (the entry point the whole slice hangs off) with no upload
and no map. Phase 4 makes upload work end to end without any frontend asset risk. Phase 5
introduces the repo's first static assets and its first CSS — the highest-risk change,
deliberately last and paired with the CI gate that catches its failure mode. Phase 6 makes
the foundation docs honest and closes the deploy runbook gap.

The architecture is the "server-side parse" path endorsed by `research.md`: persist the raw
file to the Volume, parse it once with `gpxpy` at upload time, store the derived point list
and bounds on the model, hand them to the template via `{{ ...|json_script }}`, and draw
them with core Leaflet 1.9.4. Parsing at upload — not at render — means a file that parsed
once can never fail on a page view, and the error reaches the user at the only moment they
can act on it.

## Critical Implementation Details

**Timing & lifecycle.** `default_storage` is bound lazily, so B1 cannot be caught by
`manage.py check`, `makemigrations`, `mypy`, or a test that only asserts a status code —
only by a test that performs a real `storage.save`. Phase 1 must include that test, not a
settings assertion.

**Ordering on replace.** When a re-upload supersedes an existing track, save the new row and
its file *first* inside `transaction.atomic()`, and delete the old file **outside** the
transaction via `transaction.on_commit(...)`. Both halves matter:

- *First save, then delete* — the reverse loses both if the new save fails.
- *Delete on commit, not inside the block* — storage deletes do not participate in the
  transaction. A delete performed inside `atomic()` is already gone if the block later raises
  or the commit fails: the database rolls the old `GpxTrack` row back into existence pointing
  at a file that no longer exists, so the detail page renders a map while the download view
  404s. That is exactly the silent-failure state `prd.md`'s NFR forbids, produced by the
  mitigation meant to prevent it. `on_commit` runs the delete only once the new row is
  durable.

**`clean_file()` must `seek(0)`.** Validation reads the uploaded file to parse it; without
rewinding, the subsequent `storage.save` persists an empty or truncated file. This is the
kind of bug that passes a status-code test and fails only a content test.

**Migration serialisation.** `upload_to` is written into the migration, so it must be a
module-level named function — never a lambda, never a closure. `FileField.max_length`
defaults to 100 and changing it later costs another migration; set it deliberately now.

**Settings must stay import-safe.** `tests/test_settings_security.py:25-45` re-executes
`velo_log/settings.py` via `spec_from_file_location` with only `DEBUG` in the environment.
No `mkdir`, no filesystem side effects at module level. Let Django's `FileSystemStorage`
create the media directory on first write.

**Tests must never write into the repo.** The suite runs with no `.env`, so `MEDIA_ROOT`
falls to its default. An autouse fixture must redirect `MEDIA_ROOT` at `tmp_path` before any
test can persist a file.

**mypy `--strict` + django-stubs rejects the naive shapes.** `request.FILES[...]` is
`UploadedFile[Any] | list[object]` and needs narrowing; a bare `UploadedFile` annotation
trips `disallow_any_generics` (write `UploadedFile[Any]`); `gpxpy.parse` is typed
`Union[AnyStr, IO[str]]` while Django's uploaded file is binary, so passing the file object
directly yields `[type-var]`, not `[arg-type]` — and `strict` enables
`warn_unused_ignores`, so a mis-coded `# type: ignore[arg-type]` produces two errors instead
of zero. Decode to `str` and pass the string.

**Entity expansion is mitigated by rejecting DTDs, not by the parser.** The stdlib backend
gives XXE protection for free and no billion-laughs protection at all, so the measure cannot
live inside `gpxpy`. `gpx/parsing.py` therefore rejects any `<!DOCTYPE` in the decoded text
*before* parsing. This is a deliberate text-level pre-check sitting outside the parser and
needs a comment saying so, or a later reader will read it as redundant with `gpxpy` and
remove it. A legitimate GPX file carries no internal DTD, so there is no false-positive cost.
Note what this does **not** bound: a plain, entity-free payload — see Performance
Considerations.

**ruff gives zero protection on this slice's security surface.** `gpxpy.parse` is opaque to
the `S3xx` rules (they key on resolved qualified names like `ET.parse`); `S320`/`S410` are
Removed in ruff 0.16.4 and inert; no S-rule covers `open()` on a user-supplied path,
`FileField`, or `UploadedFile`. Every upload-hardening measure here is deliberate and must
be tested, because nothing will prompt for it.

**Coverage guard traps** (both recorded from the `ci-quality-gates` slice): register the app
as the bare string `"gpx"` — a dotted `gpx.apps.GpxConfig` never string-matches
`tests/test_coverage_scope.py`'s check — and place it at the **repo root**; an app at
`src/gpx/` or `apps/gpx/` is silently exempted, a false pass.

---

## Phase 1: Storage and media foundation

### Overview

Remove B1, B2 and B3 and prove the fix with a test that performs a real storage write. No
model, no user-visible change. After this phase the repo can persist an uploaded file
without 500ing, and `/healthz/` reports where media is being written and whether that
location is actually writable.

### Changes Required:

#### 1. Storage and media settings

**File**: `velo_log/settings.py`

**Intent**: Restore the `"default"` storage alias Django's whole-attribute overwrite
discarded, and point media at the persistent Volume via the same env pattern the database
already uses — so uploads survive a redeploy instead of landing on ephemeral container disk.

**Contract**: `STORAGES` gains a `"default"` key backed by
`django.core.files.storage.FileSystemStorage`, alongside the existing `"staticfiles"` key.
`MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))`, mirroring the `DB_PATH`
idiom at `velo_log/settings.py:86`. `MEDIA_URL` is set to a non-root prefix (`"media/"`) so
it cannot collide with the root `RedirectView` at `velo_log/urls.py:38` — note that no URL is
ever served from it (see Phase 4 §5); it exists so `FileField.url` is well-formed.
`DATA_UPLOAD_MAX_MEMORY_SIZE` and `FILE_UPLOAD_MAX_MEMORY_SIZE` are set explicitly rather
than inherited — same values as the Django defaults they currently take, `2621440` (2.5 MB)
each, written out so a later change is a visible diff rather than a framework default nobody
looked at. They control different things and only one of them is about the upload:

- `FILE_UPLOAD_MAX_MEMORY_SIZE` is the in-memory vs `TemporaryUploadedFile` switchover for
  file fields. **Keep it at 2.5 MB — do not raise it to the 10 MB cap.** A real multi-day
  tour GPX is comfortably over 2.5 MB, so it spools to disk, which makes the Phase 4
  `seek(0)` contract the *tested* path rather than the rare one. Raising it to 10 MB would
  buffer every upload whole in RAM and quietly turn `seek(0)` into dead code that only
  breaks in production.
- `DATA_UPLOAD_MAX_MEMORY_SIZE` bounds non-file request data and does **not** apply to
  file-upload fields, so it is not a bound on the GPX upload at all (see "What We're NOT
  Doing").

All of it must be side-effect free at import.

#### 2. Env documentation

**File**: `.env.example`

**Intent**: Record `MEDIA_ROOT` as a recognised configuration key so a fresh checkout and the
Railway environment agree on what has to be set.

**Contract**: A commented `MEDIA_ROOT` entry alongside the existing keys, with no real value.
The production value (`/data/media`, on the mounted Volume) is documented in `DEPLOY.md` and
set in the Railway environment in Phase 4 §10 — the phase whose merge makes uploads live —
not committed here.

#### 3. Media round-trip in the health check

**File**: `velo_log/urls.py`

**Intent**: `infrastructure.md:59` records that a `RAILWAY_RUN_UID` regression makes Volume
writes **fail silently** — the pre-mortem's exact wording is "GPX upload records were quietly
lost". The existing `/healthz/` proves DB writes only; nothing proves a media write.
Writability alone is not enough: with `MEDIA_ROOT` unset, the §1 default is
`BASE_DIR / "media"` **inside the container**, where a write succeeds — so a writability-only
probe returns 200 while every uploaded file sits on ephemeral disk. The probe must therefore
assert *where* it wrote, not only that it could.

**Contract**: `healthz` gains a `default_storage` write → read-back → delete round-trip
against a throwaway key, mirroring the shape of the existing `SessionStore` round-trip.

The key is a **single fixed name**, and the write overwrites it rather than saving a new one
(`storage.delete()` then `save()`, or an equivalent that does not go through
`get_available_name`). The endpoint is unauthenticated (`velo_log/urls.py:39`), so every
anonymous probe runs this: with a generated key, a delete that starts failing would
accumulate collision-suffixed files silently, on the same Volume the app depends on. A fixed
key makes that failure mode bounded at one file. The delete runs in a `finally` block so a
failed read-back still cleans up.

The
response distinguishes which subsystem failed rather than collapsing both into one boolean,
and still returns 500 when either fails. The response body also reports the resolved
`MEDIA_ROOT`, and when `DEBUG=False` the check fails (500) unless that path is absolute and
outside `BASE_DIR` — the in-container default is treated as a misconfiguration in production,
not a pass. Under `DEBUG=True` the location assertion is skipped, so the local default stays
usable.

#### 4. Test fixtures for media

**File**: `tests/conftest.py`

**Intent**: Keep the suite from writing real files into the working tree, given it must pass
with no `.env` present.

**Contract**: A new autouse fixture redirects `settings.MEDIA_ROOT` at pytest's `tmp_path`
for every test, alongside the existing autouse `_disable_ssl_redirect`.

#### 5. Storage tests

**File**: `tests/test_media_storage.py` (new)

**Intent**: Catch B1 the only way it can be caught — by performing the real operation. A
settings assertion would pass against a `STORAGES` dict that still cannot resolve.

**Contract**: One test saves bytes through `default_storage`, reads them back, and asserts
content equality and that the file landed under `MEDIA_ROOT`. One test asserts `MEDIA_URL`
is not `"/"` and does not shadow the root redirect. One test asserts `/healthz/` returns 200
with both round-trips reporting ok. One test asserts that with `DEBUG=False` and a
`MEDIA_ROOT` inside `BASE_DIR`, `/healthz/` returns 500 and names the media root as the
reason — the guard added in §3, asserted as an outcome rather than a settings read.

**Superseded after implementation (impl review F5)**: the contract above is left as written,
but the last test no longer matches it. `/healthz/` is unauthenticated, so naming the media
root disclosed the absolute server path to any anonymous caller. The guard now returns a
stable code — `"inside_base_dir"` — and the test asserts that, plus that no absolute path
appears anywhere in the response. The intent is unchanged: still an outcome assertion, not a
settings read. The path reaches the log instead, and the body only under `DEBUG`.

#### 6. Working-tree ignore

**File**: `.gitignore`

**Intent**: The §1 local default is `BASE_DIR / "media"`, inside the repo. The §4 autouse
fixture redirects `MEDIA_ROOT` for the *test suite* only — a `runserver` upload lands in the
working tree, where the next `git add` would commit a user's GPX file.

**Contract**: `media/` is added alongside the existing `staticfiles/` and `backup/db/`
entries, with a comment pointing at the `MEDIA_ROOT` default that produces it.

### Success Criteria:

#### Automated Verification:

- Lint, format, import order pass: `uv run ruff check . && uv run black --check . && uv run isort --check-only .`
- Strict typing passes: `uv run mypy .`
- Django check passes: `uv run python manage.py check`
- Full CI-equivalent suite passes: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- `tests/test_media_storage.py` proves a real `default_storage` round-trip, not a settings assertion
- `tests/test_settings_security.py` still passes — settings remain import-safe with only `DEBUG` set
- A test asserts `/healthz/` returns 500 at `DEBUG=False` when `MEDIA_ROOT` resolves inside `BASE_DIR`

#### Manual Verification:

- No stray files appear under the repo working tree after a full test run
- `/healthz/` on a local runserver returns 200 and reports both the DB and media round-trips
- A write into the default local `media/` directory leaves `git status` clean — the autouse fixture covers the suite, `.gitignore` covers `runserver`

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation before proceeding.

---

## Phase 2: The `gpx` app and the `GpxTrack` model

### Overview

Create the sibling app `AGENTS.md:21` pre-blesses by name, and the model that holds both the
raw file and the coordinates derived from it. D1's forward-looking schema is the whole point:
an FK to `Trip` so FR-011 (multiple tracks per trip) never requires a migration rewrite,
while v1 behaviour stays one track per trip. No views, no forms, no parsing yet.

### Changes Required:

#### 1. App scaffold and registration

**Files**: `gpx/` (new, repo root), `velo_log/settings.py`, `pyproject.toml`

**Intent**: Register the app in the two places that must agree, and clear the `startapp`
scaffolding the repo's conventions don't use.

**Contract**: `INSTALLED_APPS` gains the **bare string** `"gpx"` — a dotted
`gpx.apps.GpxConfig` never string-matches `tests/test_coverage_scope.py`.
`[tool.coverage.run] source` in `pyproject.toml` gains `"gpx"`. The app lives at the **repo
root** beside `trips/`. `startapp`'s `tests.py` is deleted (tests live in `tests/`, per
`[tool.pytest.ini_options] testpaths`).

#### 2. The `GpxTrack` model

**File**: `gpx/models.py`

**Intent**: Persist the uploaded file durably (PRD "data never lost") and the coordinates
parsed from it once, so the detail view never re-parses and can never fail at render.

**Contract**: `GpxTrack` with `trip` FK to `trips.Trip` (`on_delete=CASCADE`,
`related_name="tracks"` — plural, because the schema supports many even though v1 stores
one); `file = FileField(upload_to=<module-level named function>, max_length=255)`;
`points` JSONField holding an ordered list of `[latitude, longitude]` pairs;
`min_latitude` / `min_longitude` / `max_latitude` / `max_longitude` FloatFields holding the
bounds computed at upload; `original_filename` CharField; `uploaded_at` with
`auto_now_add`. `Meta.ordering` newest-first, mirroring `Trip.Meta.ordering`'s shape.
`__str__` returns the original filename.

Bounds are stored as four explicit floats rather than a nested JSON blob so they are typed,
queryable, and unambiguous to the template.

#### 3. The upload path function

**File**: `gpx/models.py`

**Intent**: Keep the user-supplied filename out of the filesystem path entirely — the global
security baseline forbids building a path from unsanitised user input, and ruff has no rule
that would catch it here.

**Contract**: A **module-level named function** (not a lambda — it is serialised into the
migration) taking `(instance, filename)` and returning a path segmented by owner id and trip
id with a `secrets`-generated random basename and a fixed `.gpx` extension. The user's
original name is preserved only in the `original_filename` column, never on disk.

#### 4. Admin registration

**File**: `gpx/admin.py`

**Intent**: Give the same read/repair path `TripAdmin` provides, since there is no admin UI
in v1 beyond Django's own.

**Contract**: `GpxTrack` registered following the `TYPE_CHECKING` base-alias idiom at
`trips/admin.py:7-10`, with `list_select_related` on the trip to avoid an N+1 in the
changelist. `points` is excluded from the changelist display — it is unbounded data.

#### 5. Migration

**File**: `gpx/migrations/0001_initial.py` (generated)

**Intent**: `context/foundation/lessons.md` rule #9 — a missing migration passes every
automated gate and surfaces as a production outage after `railway.json`'s unattended
`migrate`.

**Contract**: Generated with `uv run python manage.py makemigrations gpx`, committed in the
same commit as the model, and verified with
`uv run python manage.py makemigrations --check --dry-run`.

#### 6. Model tests

**File**: `tests/gpx/test_gpx_track_model.py` (new, with `tests/gpx/__init__.py`)

**Intent**: Prove the relationship and lifecycle guarantees the later phases depend on.

**Contract**: A track is reachable from its trip via `related_name`; deleting the trip
cascades to its tracks; the upload path function produces a path that contains neither the
user-supplied filename nor any traversal segment; `__str__` returns the original filename.

The cascade test asserts the *rows* go, and deliberately does not assert anything about the
files: Django has not deleted `FileField` files on model delete since 1.3, and this slice
does not add that behaviour. Nothing leaks in v1 because no delete path is reachable — there
is no trip-delete UI until S-04 — so this is handed to S-04 rather than solved here (see
Migration Notes). Do not "fix" it by asserting the file is gone; that test would fail
correctly.

### Success Criteria:

#### Automated Verification:

- Migration guard is clean: `uv run python manage.py makemigrations --check --dry-run`
- Coverage guard passes with the new app: `uv run pytest tests/test_coverage_scope.py`
- Lint, format, import order, and strict typing pass on the new package
- Full CI-equivalent suite passes, and coverage stays at or above `fail_under = 80`

#### Manual Verification:

- `GpxTrack` appears in Django admin and a row can be inspected without error

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation before proceeding.

---

## Phase 3: Trip detail view

### Overview

Create the page the whole slice hangs off. Owner-scoped, 404 on someone else's trip, with a
clear empty state where the map will go. No upload, no static assets, no map.

### Changes Required:

#### 1. Detail route

**File**: `trips/urls.py`

**Intent**: Add the first pk-capturing route in the project.

**Contract**: A `<int:pk>` path named `detail` under the existing `trips` app namespace,
alongside `list` and `create`.

#### 2. Detail view

**File**: `trips/views.py`

**Intent**: Render one trip, and make cross-user access indistinguishable from a
non-existent trip — the repo's entire authorization story is the owner-scoped queryset.

**Contract**: `TripDetailView` with `LoginRequiredMixin` **first** in the base list and a
`get_queryset` scoped to `owner=<requesting user>`, exactly mirroring `trips/views.py:27-29`.
The `TYPE_CHECKING` base alias is `DetailView[Trip]`. Django's default template name
(`trips/templates/trips/trip_detail.html`) resolves for free given `APP_DIRS: True`. Context
is extended with the trip's current track, or `None`.

#### 3. Canonical URL on the model

**File**: `trips/models.py`

**Intent**: Give the redirect targets in Phase 4 one place to resolve, instead of repeating
`reverse()` calls across views.

**Contract**: `Trip.get_absolute_url()` returning the `trips:detail` URL for the instance.

#### 4. Detail template

**File**: `trips/templates/trips/trip_detail.html` (new)

**Intent**: Show the trip's own fields and a deliberate empty state — the PRD requires that
a trip with no uploaded file "does not show a broken map".

**Contract**: Extends `base.html`, fills `title` and `content`, renders name, date and
description, and branches on whether a track exists. The no-track branch renders explicit
empty-state copy. A placeholder region marks where the map lands in Phase 5.

#### 5. Link from the trip list

**File**: `trips/templates/trips/trip_list.html`

**Intent**: The list currently has no per-trip link — this is the navigation entry point to
the new page.

**Contract**: The trip name at `:11` becomes a link to `trips:detail`.

#### 6. Detail view tests

**File**: `tests/trips/test_trip_detail.py` (new)

**Intent**: Lock in the ownership boundary before any file data exists behind it.

**Contract**: Owner gets 200 and sees the trip's name; a different user gets **404** (not
403); an unauthenticated GET redirects to login with `?next=`; a trip with no track renders
the empty-state copy — asserted on the copy itself, not on a status code
(`context/foundation/lessons.md` rule #1); the list page contains a link to the detail URL.

### Success Criteria:

#### Automated Verification:

- All gates pass: ruff, black, isort, mypy, `manage.py check`, migration guard
- Full CI-equivalent suite passes with coverage at or above `fail_under = 80`
- Cross-user access is asserted to return 404, and unauthenticated access to redirect

#### Manual Verification:

- Clicking a trip in the list opens its detail page showing the trip's own fields
- The empty state reads as a deliberate message, not a missing element

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation before proceeding.

---

## Phase 4: Upload, validation, and download

### Overview

Make the upload path work end to end with no frontend asset risk in play. Add `gpxpy`,
validate and parse at upload, reject bad input inline, replace an existing track on
re-upload, and serve the original file back through an ownership-scoped view — never through
`MEDIA_URL`.

### Changes Required:

#### 1. Dependency

**Files**: `pyproject.toml`, `uv.lock`

**Intent**: Add the parser. `gpxpy` 1.6.2 is pure-Python with zero dependencies, ships
`py.typed`, and is verified running on this repo's CPython 3.14.5.

**Contract**: `uv add gpxpy` per `AGENTS.md:8`. The regenerated `uv.lock` must land in the
**same commit** — `.github/workflows/deploy.yml:28` runs `uv sync --locked` and fails on
lockfile drift at step 3 of 9. `lxml` is deliberately **not** added: installing it silently
switches gpxpy's parser backend and changes entity-resolution defaults with no gate that
would notice.

#### 2. Constants and exceptions

**Files**: `gpx/constants.py` (new), `gpx/exceptions.py` (new)

**Intent**: Name the magic values, and give the parsing layer its own failure type so the
form is not catching third-party exceptions directly.

**Contract**: A 10 MB upload ceiling in bytes and the allowed extension tuple as named
constants. A `GpxParseError` base exception for the app, raised by the parsing module — for
the rejected-DTD case as well as the parse failures, so the form has one exception type to
catch.

#### 3. Parsing module

**File**: `gpx/parsing.py` (new)

**Intent**: Isolate every interaction with untrusted XML in one tested module, so the
security surface is a single reviewable file rather than logic spread through a form.

**Contract**: One function taking GPX text and returning a small frozen dataclass carrying
the ordered `[lat, lon]` point list and the four bounds floats.

Before parsing, it rejects any document type declaration: if `<!DOCTYPE` appears in the
decoded text, raise `GpxParseError` without handing the text to `gpxpy`. This is the slice's
entity-expansion mitigation — the pinned stdlib backend rejects external entities on its own
but expands internal ones (see Key Discoveries), so the guard has to sit here. It carries a
comment saying why, since nothing in the toolchain would prompt for it and it reads as
redundant otherwise.

It catches
`gpxpy.gpx.GPXXMLSyntaxException` (malformed XML) and `gpxpy.gpx.GPXException` (valid XML,
invalid GPX) **separately** — they are two distinct user-facing failures — plus
`UnicodeDecodeError` from the decode step, and re-raises all three as `GpxParseError` with
`raise ... from e`. A track with zero points is itself a `GpxParseError`: it would produce
degenerate bounds and an unrenderable map, so it is rejected at the boundary rather than
guarded at every downstream consumer.

Bounds come from `gpx.get_bounds()`, which returns `GPXBounds | None` with `float | None`
members — narrow before use or mypy's `union-attr` fires.

#### 4. Upload form

**File**: `gpx/forms.py` (new)

**Intent**: Reject bad uploads at the moment the user can fix them, using the
`clean_<field>()` precedent at `accounts/forms.py:10-21`.

**Contract**: A `ModelForm[GpxTrack]` exposing only the file field, following the
`TYPE_CHECKING` base-alias idiom. `clean_file()` enforces, in order: size against the 10 MB
constant; extension against the allowed tuple, case-insensitively; then decode and parse via
`gpx/parsing.py`, converting `GpxParseError` into a `ValidationError` whose message
distinguishes "not valid XML" from "not valid GPX". A file rejected for carrying a DOCTYPE
falls in the "not valid XML" bucket for the user — the message stays about the file being
unusable and does not explain the mitigation. The parsed result is stashed on the form
for the view to persist without re-parsing.

**Critical**: `clean_file()` reads the upload to parse it and **must `seek(0)` before
returning**, or the subsequent storage write persists a truncated file — a bug that passes a
status-code test and fails only a content test.

Typing: annotate the uploaded file as `UploadedFile[Any]` (a bare `UploadedFile` trips
`disallow_any_generics`) and pass **decoded text** to `gpxpy.parse`, not the binary file
object — the latter yields `[type-var]` under strict mode, and a mis-coded
`# type: ignore[arg-type]` produces two errors instead of zero because `strict` enables
`warn_unused_ignores`.

#### 5. Upload and download views

**File**: `gpx/views.py`

**Intent**: Attach a track to a trip the requesting user owns, replacing any existing one;
and serve the original file back under the same authorization as everything else.

**Contract**: Two views, both with `LoginRequiredMixin` first in the base list.

The upload view resolves its target trip through an **owner-scoped queryset** so another
user's trip pk 404s exactly as the detail view does, then on valid input saves the new track
with its parsed points and bounds and removes the superseded one. Ordering is load-bearing:
inside `transaction.atomic()`, save the new row and file **first** and delete the superseded
row; register the old *file's* deletion with `transaction.on_commit(...)` so it happens only
after the new row is durable. A delete performed inside the block survives a rollback while
the row it belonged to comes back — see Critical Implementation Details, "Ordering on
replace". On success it redirects to the trip's
`get_absolute_url()` with a confirmation message via `SuccessMessageMixin`, matching
`TripCreateView`'s pattern. On invalid input it re-renders `trips/trip_detail.html` with the
bound form so errors appear in place.

The download view resolves the track through the same owner scoping and returns a
`FileResponse` opened in binary, as an attachment named by `original_filename`. This is
required by two separate PRD sentences: `prd.md:105` ("no user can access another user's
trips under any circumstances") drives the owner scoping, and `prd.md:104` ("unauthenticated
users cannot view any trip") drives the `LoginRequiredMixin`. A bare `MEDIA_URL` path breaks
both — whitenoise sits at `MIDDLEWARE` position 2, before `AuthenticationMiddleware`, so
anything it serves is outside authorization by construction.

Both views need the `TYPE_CHECKING` base-alias treatment.

*Design note*: the upload view lives in `gpx/` but renders a `trips/` template. That
cross-app reference is deliberate — the model, parsing, validation and assets belong to
`gpx/`, while the page a user looks at is a trip's detail page. Django resolves it fine; it
is recorded here so it reads as a decision rather than an accident.

#### 6. URLs

**Files**: `gpx/urls.py` (new), `velo_log/urls.py`

**Intent**: Wire the two views under their own namespace.

**Contract**: `app_name = "gpx"` with an upload route capturing the trip pk and a download
route capturing the track pk, included from the project URLconf under a `gpx/` prefix.

#### 7. Detail template — upload form and download link

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: Put the upload where the user already is, per US-01's flow.

**Contract**: A `<form method="post">` carrying **`enctype="multipart/form-data"`** —
`CreateView` passes `files=request.FILES` automatically, but the enctype attribute is manual
and appears nowhere in the repo today. It follows the error idiom copy-pasted across all
three existing form templates: `{% csrf_token %}`, `{{ form.non_field_errors }}`, then
per-field `label_tag` / field / `errors` (`context/foundation/lessons.md` rule #2 — omitting
`non_field_errors` renders a blank form with no feedback). When a track exists, a download
link to the `gpx` download route and the original filename are shown, and the submit copy
reads as a replacement rather than an addition.

#### 8. Detail view context

**File**: `trips/views.py`

**Intent**: The detail page now hosts a form it does not own.

**Contract**: `TripDetailView.get_context_data` supplies an unbound `GpxUploadForm`, so the
GET path and the upload view's re-render path present the same page.

#### 9. Upload and download tests

**Files**: `tests/gpx/test_gpx_upload.py`, `tests/gpx/test_gpx_download.py`,
`tests/gpx/test_gpx_parsing.py` (all new), `tests/gpx/fixtures/` (small GPX samples)

**Intent**: Every hardening measure in this phase is invisible to ruff. If it is not tested,
nothing in the pipeline knows it exists.

**Contract**:

*Parsing* — a valid track yields the expected point list and bounds; malformed XML raises
`GpxParseError`; well-formed XML that is not GPX raises `GpxParseError`; a GPX with zero
track points raises `GpxParseError`. Entity handling is **two** tests, not one, because the
two payloads behave differently against the pinned backend: an *external*-entity (XXE)
payload raises `GpxParseError`, and a *nested internal*-entity (billion laughs) payload also
raises `GpxParseError` — the second is the one that proves the §3 DTD guard exists, since
without it the backend expands rather than rejects. Assert the outcome, not the message. A
further test pins gpxpy's parser backend to the stdlib one, so adding `lxml` later cannot
silently change entity-resolution defaults without turning a gate red.

*Upload* — a valid upload creates exactly one track, persists a file whose bytes match what
was submitted (this is what catches a missing `seek(0)`), and redirects to the detail page;
an over-cap file is rejected with a visible message and creates nothing; a non-`.gpx`
extension is rejected; malformed XML is rejected and the **error text is asserted**, not just
a 200 (`lessons.md` rule #1); a second upload replaces the first, leaving exactly one track
with the old file gone from storage — and, since `on_commit` callbacks do not fire under
pytest-django's default transactional wrapping, one test asserts the replace path with
`django_capture_on_commit_callbacks` (or the `transaction=True` equivalent) so the deferred
delete is actually exercised rather than silently skipped; uploading to another user's trip returns 404 and creates
nothing; an unauthenticated POST redirects to login and creates nothing.

*Download* — the owner gets 200 with the original bytes and an attachment disposition; a
different user gets 404; an unauthenticated request redirects to login.

#### 10. Deploy gate — `MEDIA_ROOT` and the media backup procedure

**Files**: `DEPLOY.md` — plus one Railway environment change, made outside the repo

**Intent**: This is the merge that puts uploads in production, and `deploy.yml`'s deploy job
fires on every push to `master`. Two things must therefore be true **before** this phase
merges, not in Phase 6: `MEDIA_ROOT` actually points at the Volume, and the files it starts
collecting have a backup procedure. `DEPLOY.md:33-56` currently backs up
`/data/db.sqlite3` only.

**Contract**: `MEDIA_ROOT=/data/media` is set in the Railway environment and confirmed via
`railway variables`; the Phase 1 `/healthz/` location guard is what proves it took effect.
`DEPLOY.md`'s Backup and Restore sections extend to `/data/media`, using the same
`railway service files` mechanism and the same `MSYS_NO_PATHCONV=1` caveat already documented
for Git Bash, and record that a `RAILWAY_RUN_UID` regression makes Volume writes fail
**silently** (`infrastructure.md:59`) — which the `/healthz/` media round-trip now detects.
`backup/` is gitignored in full (`.gitignore:82`), so the media dump path needs no new
entry — that was widened from `backup/db/` ahead of this slice precisely so this step could
not leak a dump of another user's GPX files. Phase 6 keeps the known-good-deployments row and
the restore drill.

### Success Criteria:

#### Automated Verification:

- All gates pass: ruff, black, isort, mypy strict, `manage.py check`, migration guard
- `uv sync --locked` succeeds — `uv.lock` is committed with `pyproject.toml`
- Full CI-equivalent suite passes with coverage at or above `fail_under = 80`
- An upload test asserts persisted file **content**, not only a status code
- Two parsing tests assert an XXE payload and a nested-entity payload are each rejected, and a test pins the stdlib parser backend
- Cross-user upload and cross-user download are both asserted to return 404

#### Manual Verification:

- Uploading a real GPX from a tour attaches it to the trip and returns to the detail page with a confirmation
- Uploading a `.txt`, an oversized file, and a corrupted `.gpx` each show a readable inline error and leave the trip unchanged
- Uploading a second file replaces the first, and the download link returns the newest file
- The downloaded file opens correctly in another GPX viewer
- `MEDIA_ROOT=/data/media` is confirmed set in Railway via `railway variables`, and production `/healthz/` returns `"media": "ok"` — which is what proves the location guard accepted the root as absolute and outside `BASE_DIR`. The body no longer echoes the path: `/healthz/` is unauthenticated, so the absolute server layout is withheld from anonymous callers and the verdict carries the proof instead — **before** this phase is merged
- `DEPLOY.md`'s Backup and Restore sections cover `/data/media`

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation before proceeding.

---

## Phase 5: Map rendering and the static pipeline

### Overview

The highest-risk phase, deliberately last. This is the repo's first `{% static %}`
reference, first CSS, and first vendored asset — and `collectstatic` failure is a boot
outage, not a degraded deploy. The CI gate that catches that failure ships in the same phase
as the risk it guards.

### Changes Required:

#### 1. Vendored Leaflet 1.9.4

**Files**: `gpx/static/gpx/vendor/leaflet/` (new)

**Intent**: Pin the stable release and ship it in full. `leaflet@latest` is still 1.9.4;
Leaflet 2.0 has been alpha since 2025-05 with its release date reset to "unknown".

**Contract**: `leaflet.js`, `leaflet.js.map`, `leaflet.css`, and the **complete** sibling
`images/` directory — `layers.png`, `layers-2x.png`, `marker-icon.png`, `marker-icon-2x.png`,
`marker-shadow.png`.

The rule this list follows, stated once: **every reference a vendored asset makes to a
sibling file must be vendored alongside it, or the reference removed.**
`CompressedManifestStaticFilesStorage` rewrites and resolves those references at
`collectstatic` time and raises `MissingFileError` on any it cannot find — which given
`railway.json:4` means the container never starts. Two reference kinds apply here, both
verified to fail when unmet against this repo's actual storage class:

- `leaflet.css` contains `url(images/layers.png)`, `url(images/layers-2x.png)` and
  `url(images/marker-icon.png)` — hence the `images/` directory.
- `leaflet.js` ends with `//# sourceMappingURL=leaflet.js.map`, which Django 6.0.5 matches
  and resolves like any other reference
  (`django/contrib/staticfiles/storage.py:102`) — hence `leaflet.js.map`. Vendoring the map
  file is preferred over stripping the comment: it keeps the vendored bytes byte-identical to
  the upstream release, so a future upgrade is a straight file swap.

If `collectstatic` fails with `MissingFileError`, the fix is always to vendor the missing
sibling. Relaxing `WHITENOISE_MANIFEST_STRICT` or downgrading the storage class would trade a
loud build failure for silently broken asset URLs in production.

The pinned version and its download source are recorded in a sibling note file so a future
upgrade is traceable.

#### 2. Project-level static directory

**Files**: `static/css/style.css` (new), `velo_log/settings.py`

**Intent**: The map needs a sized container, and `base.html` is a project-level template —
so the stylesheet it loads belongs beside it, not inside an app. This slice explicitly
reverses the standing "no CSS, no stylesheet, no static asset" decision recorded in both
archived plans (`context/archive/2026-08-22-user-registration-login/plan.md:41`,
`context/archive/2026-08-23-create-and-list-trips/plan.md:50`), per
`context/foundation/lessons.md` rule #5.

**Contract**: `STATICFILES_DIRS = [BASE_DIR / "static"]` — currently unset, and without it
the directory is invisible to `collectstatic`. This mirrors the existing
`TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]` convention exactly: project-level
cross-cutting assets at the root, app-namespaced assets inside the app. `style.css` sizes
`#map` with relative units so it works on a mobile browser, per the PRD's responsive-web-app
scope.

#### 3. Base template blocks

**File**: `templates/base.html`

**Intent**: `leaflet.css` must land in `<head>` and `leaflet.js` before `</body>`; today
there is nowhere to put either.

**Contract**: Two new blocks — one in `<head>` after the stylesheet link, one before the
closing body tag. `base.html` gains `{% load static %}`, a `<link>` to `style.css`, and a
`<meta name="viewport" content="width=device-width, initial-scale=1">`, which is absent today
and without which the map is unusable on the mobile browsers the PRD targets.

#### 4. Map initialisation script

**File**: `gpx/static/gpx/map.js` (new)

**Intent**: Draw the route as a map that behaves like a static image, with no inline
JavaScript in the template.

**Contract**: Reads a single JSON configuration blob from the page (points, bounds, and the
marker icon URLs — a static file cannot call `{% static %}`, so the URLs must arrive from the
template) and builds the map.

Verified Leaflet 1.9.4 API, confirmed against `leafletjs.com/reference.html`:

```javascript
var map = L.map('map', {
    dragging: false, scrollWheelZoom: false, touchZoom: false,
    doubleClickZoom: false, keyboard: false, boxZoom: false,
    tapHold: false, zoomControl: false
});
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '© OpenStreetMap'
}).addTo(map);
L.polyline(points, {color: '#ff7800', weight: 5, opacity: 0.85}).addTo(map);
map.fitBounds([[minLat, minLon], [maxLat, maxLon]], {padding: [20, 20]});
```

`attribution` is passed explicitly — 1.9.4 does not add OSM attribution automatically
(2.0 does). Bounds come from the server-computed values rather than `polyline.getBounds()`,
which keeps the client off an API surface the 1.x docs did not confirm and keeps the
degenerate-bounds decision server-side where it was already made.

Start and end markers use `L.icon` with **explicit** `iconUrl` / `shadowUrl` values from the
config blob. This is deliberate: Leaflet's default icon builds `marker-icon-2x.png` and
`marker-shadow.png` URLs at runtime, which the hashed staticfiles manifest never rewrites —
silent 404s in production that pass every gate locally.

#### 5. Detail template — the map

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: Render the map where the Phase 3 placeholder is, and keep the coordinate payload
out of the HTML body.

**Contract**: The track branch emits a sized `#map` container and the configuration blob via
**`{{ ...|json_script:"..." }}`** — never `|safe`, never `mark_safe`. S-02's verified security
posture is zero occurrences of either, and this slice does not break it. `leaflet.css` goes in
the head block; `leaflet.js` then `map.js` in the scripts block. A defensive branch renders an
explicit "route could not be displayed" message if a track somehow carries no points — it
cannot happen given Phase 4 rejects that at upload, but the PRD's only NFR forbids a blank
page, so the branch is deliberate rather than assumed away.

#### 6. Map view context

**File**: `trips/views.py`

**Intent**: Assemble the configuration blob the template serialises.

**Contract**: `get_context_data` builds a dict of points, bounds, and the three
`static()`-resolved icon URLs. Building it in Python — rather than assembling JSON in the
template — keeps `json_script` fed with a single structure and keeps URL resolution on the
server where the staticfiles manifest is authoritative.

#### 7. CI `collectstatic` gate

**File**: `.github/workflows/deploy.yml`

**Intent**: Close B4. Today a broken static reference is caught only at container start,
after `gates` has gone green and `railway up` has run — and because `collectstatic` is
`&&`-chained ahead of `gunicorn` in `railway.json:4`, the result is a total outage whose
recovery is a manual redeploy by ID from `DEPLOY.md`.

**Contract**: A `collectstatic --noinput` step in the `gates` job, positioned with the other
`manage.py` checks and before the test step, so a manifest failure fails the PR rather than
the deploy. `staticfiles/` is already gitignored.

#### 8. Map rendering tests

**File**: `tests/trips/test_trip_detail_map.py` (new)

**Intent**: Prove the page renders what the map needs, and that the security posture holds.

**Contract**: A trip with a track renders the `#map` container and a `json_script` element
whose payload contains the track's coordinates; the same page contains no `|safe`-style raw
interpolation of that payload; a trip without a track renders the empty state and **no** map
container; the icon URLs in the payload resolve through the staticfiles storage rather than
being hardcoded.

### Success Criteria:

#### Automated Verification:

- `uv run python manage.py collectstatic --noinput` exits 0 with the manifest storage active
- The new `collectstatic` step is present in the `gates` job and passes in CI
- All gates pass: ruff, black, isort, mypy strict, `manage.py check`, migration guard
- Full CI-equivalent suite passes with coverage at or above `fail_under = 80`
- A test asserts the coordinate payload is delivered via `json_script`, not raw interpolation
- A test asserts a trackless trip renders no map container

#### Manual Verification:

- The route renders on the detail page, fitted to the track with visible margin
- The map does not pan, zoom on scroll, zoom on double-click, or respond to arrow keys, and shows no zoom control
- OpenStreetMap attribution is visible
- Start and end markers render with correct icons and shadows — no broken-image placeholders, and no 404s in the browser console
- The page is usable at a mobile viewport width
- After `collectstatic`, tiles, marker images, and the layers icon all load from hashed URLs with no console 404s

**Implementation Note**: After completing this phase and all automated verification passes,
pause here for manual confirmation before proceeding.

---

## Phase 6: Documentation and deploy hardening

### Overview

Make the foundation docs describe what actually shipped, and close the runbook gap before
the first deploy that carries real user files. `context/foundation/lessons.md` rule #5:
update the docs in the same slice that invalidates them — `AGENTS.md` loads every session, so
a stale claim actively misdirects the next agent.

### Changes Required:

#### 1. PRD amendments

**File**: `context/foundation/prd.md`

**Intent**: Two research findings (C3, C4) where what ships differs from what the PRD says,
neither previously written back.

**Contract**: FR-005's wording moves from "static map image" to a non-interactive map view,
keeping FR-015 (interactive, parked v2) as a coherent delta rather than a contradiction. The
Primary Success Criterion is reworded to match. Non-Goals gains an explicit note that OSM
raster tiles are in scope and why that is consistent with "no external platform integration"
— no import, no sync, no API key, no account. Both go in the PRD's Changelog section with a
version bump, per its existing convention.

#### 2. Roadmap amendments

**File**: `context/foundation/roadmap.md`

**Intent**: Keep the roadmap and the PRD from disagreeing with each other, and record the
engineering-backlog movement this slice causes.

**Contract**: The S-03 outcome wording tracks the FR-005 change in both the "At a glance"
table and the slice body. E-05's row is updated once the restore drill below is done. The
S-03 slice status itself is owned by the `/10x-plan` → `/10x-implement` → `/10x-archive`
chain and is not hand-edited here.

#### 3. Repository guide

**File**: `AGENTS.md`

**Intent**: Four claims in it become false during this slice.

**Contract**: The `gpx/` app is named in Project Structure alongside `accounts/` and
`trips/`; the project-level `static/` directory and `STATICFILES_DIRS` are described beside
the existing `templates/` note; the Testing section's coverage scope adds `gpx`; the Commits
section's gate list adds the `collectstatic` step; `MEDIA_ROOT` is documented as a required
environment variable in production.

#### 4. Deploy runbook

**File**: `DEPLOY.md`

**Intent**: The `/data/media` backup and restore procedure and the `MEDIA_ROOT` note landed
in Phase 4 §10 — they had to, since Phase 4 is the merge that puts uploads in production. What
is left here is verifying those commands against production and recording the deploy.

**Contract**: The Phase 4 §10 Backup and Restore additions are exercised against production
and corrected wherever the run contradicts them. The known-good deployments table gains a row
for this deploy.

#### 5. Restore drill

**Intent**: Discharge engineering-backlog row **E-05**, whose trigger is literally "before
the deploy following S-03". An unexercised runbook is what E-05 already records as the
problem; documenting a second unexercised path would make that debt bigger, not smaller.

**Contract**: Take a backup of both `/data/db.sqlite3` and `/data/media`, restore them into a
scratch target, and confirm the restored state serves a previously uploaded track. Correct
the runbook wherever the drill contradicts it, then mark E-05 done in the roadmap's
Engineering Backlog with the drill date.

### Success Criteria:

#### Automated Verification:

- No source change in this phase — the full CI-equivalent suite still passes unchanged
- No stale `gpx`-related claim remains: `AGENTS.md`'s coverage scope, app list, and gate list match `pyproject.toml` and `deploy.yml`

#### Manual Verification:

- `prd.md` FR-005, the Primary Success Criterion, and Non-Goals read consistently with what shipped, and the Changelog records the amendment
- `roadmap.md` and `prd.md` agree on the S-03 outcome wording
- The backup commands in `DEPLOY.md` run successfully against production for both the DB and the media directory
- The restore drill completes and a previously uploaded track is retrievable afterwards
- E-05 is marked done in the roadmap with the drill date

**Implementation Note**: This phase is manual-verification-heavy by nature; it cannot be
proven by CI and requires a live Railway session.

---

## Testing Strategy

### Unit Tests

- **Parsing** (`gpx/parsing.py`): valid track → expected points and bounds; malformed XML;
  well-formed non-GPX; zero-point track; XXE payload rejected; nested-entity payload
  rejected (proves the DTD guard); parser backend pinned to stdlib.
- **Form validation**: over-cap size; wrong extension (and case-insensitivity); unparseable
  content; the `seek(0)` contract, proven by asserting persisted file content.
- **Model**: `related_name` reachability; cascade on trip delete; upload path contains
  neither the user filename nor a traversal segment.
- **Storage**: a real `default_storage` write/read round-trip — the only thing that catches
  B1.

### Integration Tests

- Full upload → detail → map render flow for the owning user.
- Replace-on-re-upload: exactly one track survives, the old file is gone.
- Authorization matrix on all three new surfaces (detail, upload, download): owner 200,
  other user 404, unauthenticated redirect to login.
- `/healthz/` reports both the DB and media round-trips.

### Manual Testing Steps

1. Register a fresh user, log in, create a trip, open its detail page — confirm the empty state.
2. Upload a real multi-day tour GPX; confirm the route renders fitted with visible margin, start and end markers correct, and OSM attribution present.
3. Try to pan, scroll-zoom, double-click-zoom, and arrow-key the map — none should respond, and no zoom control should be visible.
4. Open the browser console and confirm zero 404s for tiles, marker images, or the layers icon.
5. Upload a `.txt`, a >10 MB file, and a truncated `.gpx` — each must show a readable inline error and leave the trip unchanged.
6. Upload a second valid GPX; confirm it replaces the first and the download link returns the newest file.
7. Download the file and open it in another GPX viewer to confirm byte fidelity.
8. Log in as a second user and request the first user's trip detail, upload, and download URLs directly — all must 404.
9. View the detail page at a mobile viewport width.
10. After deploy: hit `/healthz/`, upload a file in production, redeploy, and confirm the file survives — this is the Volume persistence proof.

## Performance Considerations

Parsing happens once, at upload, not per page view — so the detail view does no XML work and
cannot degrade as a track grows. The remaining cost is the coordinate array embedded in the
page: a 10 MB GPX can carry a very large number of points, and the size cap is the only limit
on it. That is an accepted v1 risk; a point cap or downsampling was considered and declined.
If the detail page ever feels slow, point count is the first thing to measure, and the
parse-on-upload design means downsampling can be added later without touching the render
path.

What the cap does **not** bound is upload-time resource use. It rejects an oversized file; it
does not prevent one being uploaded. `clean_file()` runs after the entire request body has
been received and spooled to a `TemporaryUploadedFile`, and no request-body limit exists
anywhere in front of it (see "What We're NOT Doing"). Two upload-time exposures therefore
remain in v1, both accepted rather than mitigated: an unbounded request body filling the
container's temp disk, and — for entity-free payloads — parse cost proportional to whatever
was received. The DTD rejection in Phase 4 §3 closes the *amplification* case, where a small
file expands to a large one; it does nothing about a genuinely large one.

Tile fetches go to `tile.openstreetmap.org` from the browser. There is no server-side
dependency on OSM, so an OSM outage degrades the map to a blank tile layer with the route
still drawn — it does not fail the page.

## Migration Notes

`gpx/migrations/0001_initial.py` is additive and creates one new table. It touches no
existing table and needs no backfill, so it is safe to apply on the unattended `migrate` in
`railway.json:4`. Per `DEPLOY.md`, take a database backup immediately before the deploy that
carries it.

There is no existing media data to migrate — this slice creates the media directory's first
contents. `MEDIA_ROOT` must be set to `/data/media` in the Railway environment **before** the
first upload, or files land on ephemeral container disk and are lost on the next redeploy.
Setting it is owned by Phase 4 §10, gated by Progress 4.11 — the phase whose merge makes
uploads live. Two distinct failures are then covered by the Phase 1 `/healthz/` probe: the
silent-write-failure mode that `infrastructure.md:59` records (caught by the write →
read-back → delete round-trip) and an unset or in-container `MEDIA_ROOT` (caught by the
location assertion, which only applies at `DEBUG=False`). A writability-only probe would pass
on the second one, because the in-container default is writable.

**Handoff to S-04 — orphan files on delete.** S-04 adds trip edit and delete. Deleting a
trip cascades its `GpxTrack` rows away, but Django does not delete the underlying files, so
every deleted trip will leave its GPX files on the Volume permanently. Nothing leaks in this
slice because no delete path is reachable, but S-04 must pair its delete with file cleanup —
whichever mechanism it chooses, on the same `transaction.on_commit` footing as the replace
path in Phase 4 §5. The Volume is single-region and 3,000 IOPS; an unbounded orphan set is
not a cost that stays invisible forever.

## References

- Internal research: `context/changes/upload-gpx-and-view-map/research.md`
- Settled decisions D1–D4: `context/changes/upload-gpx-and-view-map/change.md`
- Leaflet 1.9.4 API: `context/changes/upload-gpx-and-view-map/research/leaflet-1.9.4-context7-docs.md`
  (the two gaps at `:153-154` are closed in this plan's Key Discoveries)
- gpxpy API: `context/changes/upload-gpx-and-view-map/research/gpxpy-context7-docs.md`
- Superseded for implementation (Leaflet 2.0-alpha, keep for FR-015):
  `context/changes/upload-gpx-and-view-map/research/leaflet-context7-docs.md`
- Ownership pattern to copy: `trips/views.py:24-29,32-43`
- Form/error/CSRF idiom to copy: `trips/templates/trips/trip_form.html:7-18`
- Field validation precedent: `accounts/forms.py:10-21`
- Owner-cannot-be-posted test to mirror: `tests/trips/test_trip_creation.py:49-64`
- Recurring rules: `context/foundation/lessons.md` (#1, #2, #4, #5, #9 all apply here)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Storage and media foundation

#### Automated

- [x] 1.1 Lint, format, import order pass — 507ca9a
- [x] 1.2 Strict typing passes — 507ca9a
- [x] 1.3 Django check passes — 507ca9a
- [x] 1.4 Full CI-equivalent suite passes — 507ca9a
- [x] 1.5 `tests/test_media_storage.py` proves a real `default_storage` round-trip — 507ca9a
- [x] 1.6 `tests/test_settings_security.py` still passes — settings remain import-safe — 507ca9a
- [x] 1.7 `/healthz/` returns 500 at `DEBUG=False` when `MEDIA_ROOT` resolves inside `BASE_DIR` — 507ca9a

#### Manual

- [x] 1.8 No stray files appear under the repo working tree after a full test run — 507ca9a
- [x] 1.9 `/healthz/` returns 200 and reports both the DB and media round-trips — 507ca9a
- [x] 1.10 A `runserver` write into the default `media/` leaves `git status` clean — 507ca9a

### Phase 2: The `gpx` app and the `GpxTrack` model

#### Automated

- [x] 2.1 Migration guard is clean — 54b06a4
- [x] 2.2 Coverage guard passes with the new app — 54b06a4
- [x] 2.3 Lint, format, import order, and strict typing pass on the new package — 54b06a4
- [x] 2.4 Full CI-equivalent suite passes, coverage at or above `fail_under = 80` — 54b06a4

#### Manual

- [x] 2.5 `GpxTrack` appears in Django admin and a row can be inspected without error — 54b06a4

### Phase 3: Trip detail view

#### Automated

- [ ] 3.1 All gates pass: ruff, black, isort, mypy, `manage.py check`, migration guard
- [ ] 3.2 Full CI-equivalent suite passes with coverage at or above `fail_under = 80`
- [ ] 3.3 Cross-user access asserted 404, unauthenticated access asserted redirect

#### Manual

- [ ] 3.4 Clicking a trip in the list opens its detail page showing the trip's own fields
- [ ] 3.5 The empty state reads as a deliberate message, not a missing element

### Phase 4: Upload, validation, and download

#### Automated

- [ ] 4.1 All gates pass: ruff, black, isort, mypy strict, `manage.py check`, migration guard
- [ ] 4.2 `uv sync --locked` succeeds — `uv.lock` committed with `pyproject.toml`
- [ ] 4.3 Full CI-equivalent suite passes with coverage at or above `fail_under = 80`
- [ ] 4.4 An upload test asserts persisted file content, not only a status code
- [ ] 4.5 XXE and nested-entity payloads are each asserted rejected; a test pins the stdlib parser backend
- [ ] 4.6 Cross-user upload and cross-user download both asserted to return 404

#### Manual

- [ ] 4.7 Uploading a real GPX attaches it and returns to the detail page with a confirmation
- [ ] 4.8 `.txt`, oversized, and corrupted `.gpx` each show a readable inline error and change nothing
- [ ] 4.9 A second upload replaces the first; the download link returns the newest file
- [ ] 4.10 The downloaded file opens correctly in another GPX viewer
- [ ] 4.11 `MEDIA_ROOT=/data/media` confirmed in Railway via `railway variables`; production `/healthz/` returns `"media": "ok"` — before merge
- [ ] 4.12 `DEPLOY.md` Backup and Restore sections cover `/data/media`

### Phase 5: Map rendering and the static pipeline

#### Automated

- [ ] 5.1 `collectstatic --noinput` exits 0 with the manifest storage active
- [ ] 5.2 The new `collectstatic` step is present in the `gates` job and passes in CI
- [ ] 5.3 All gates pass: ruff, black, isort, mypy strict, `manage.py check`, migration guard
- [ ] 5.4 Full CI-equivalent suite passes with coverage at or above `fail_under = 80`
- [ ] 5.5 A test asserts the coordinate payload is delivered via `json_script`
- [ ] 5.6 A test asserts a trackless trip renders no map container

#### Manual

- [ ] 5.7 The route renders fitted to the track with visible margin
- [ ] 5.8 The map does not pan, scroll-zoom, double-click-zoom, or respond to arrow keys; no zoom control
- [ ] 5.9 OpenStreetMap attribution is visible
- [ ] 5.10 Start and end markers render correctly — no broken images, no console 404s
- [ ] 5.11 The page is usable at a mobile viewport width
- [ ] 5.12 After `collectstatic`, all assets load from hashed URLs with no console 404s

### Phase 6: Documentation and deploy hardening

#### Automated

- [ ] 6.1 Full CI-equivalent suite still passes unchanged
- [ ] 6.2 No stale `gpx`-related claim remains in `AGENTS.md` vs `pyproject.toml` and `deploy.yml`

#### Manual

- [ ] 6.3 `prd.md` FR-005, Primary Success Criterion, and Non-Goals read consistently; Changelog records the amendment
- [ ] 6.4 `roadmap.md` and `prd.md` agree on the S-03 outcome wording
- [ ] 6.5 `DEPLOY.md` backup commands run successfully for both the DB and the media directory
- [ ] 6.6 The restore drill completes and a previously uploaded track is retrievable afterwards
- [ ] 6.7 E-05 is marked done in the roadmap with the drill date
