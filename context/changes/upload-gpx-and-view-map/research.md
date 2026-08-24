---
date: 2026-08-24T14:05:00+02:00
researcher: Miłosz Jarzynka
git_commit: f0dfa38dc57ad884b1dfb4da24e67242f69dea13
branch: docs/upload-gpx-changelog-backlog-status
repository: miloszj7/VeloLog
topic: "Are the tech solutions selected in research/ compatible with this codebase, for implementing S-03 upload-gpx-and-view-map?"
tags: [research, codebase, compatibility, gpx, leaflet, gpxpy, media-storage, staticfiles, whitenoise, railway]
status: complete
last_updated: 2026-08-24
last_updated_by: Miłosz Jarzynka
last_updated_note: "Added the verified Context7 library ID that returns Leaflet 1.x docs, and the version tell-tale to check on every fetch"
---

# Research: compatibility of the S-03 library choices with the VeloLog codebase

**Date**: 2026-08-24T14:05:00+02:00
**Researcher**: Miłosz Jarzynka
**Git Commit**: `f0dfa38dc57ad884b1dfb4da24e67242f69dea13`
**Branch**: `docs/upload-gpx-changelog-backlog-status`
**Repository**: `miloszj7/VeloLog`

## Research Question

Analyze the codebase and determine whether the tech solutions selected during external
research in `context/changes/upload-gpx-and-view-map/research/` — `gpxpy`, Leaflet,
`leaflet-gpx`, and (addendum) `@raruto/leaflet-elevation` — are compatible with this
codebase, ahead of implementing roadmap slice **S-03** (`upload-gpx-and-view-map`).

## Summary

**Verdict: one of the four choices is cleanly compatible, one needs its version pinned
and its captured docs discarded, and two should not ship in S-03.**
Separately, **five codebase-level blockers** stand between the current repo and any GPX
upload at all — and the most severe of them passes every CI gate green and fails only in
production, on the first upload.

| Choice | Verdict | Why |
|---|---|---|
| **`gpxpy` 1.6.2** | ✅ **Compatible — adopt as-is** | Pure-Python `py3-none-any` wheel, **zero dependencies**, Apache-2.0, ships `py.typed`. Verified *executing* on this repo's own CPython 3.14.5: `backend = STDLIB`, `length_2d()` correct. Clean under `mypy --strict` when installed normally. |
| **Leaflet** | ⚠️ **Compatible only if pinned to 1.9.4 — and `research/leaflet-context7-docs.md` must not be used as the implementation reference** | `leaflet@latest` on npm is still **1.9.4**. Leaflet 2.0 has been *alpha* since 2025-05-18 and its target release date was reset to "unknown" in Apr 2026. The snippets captured from Context7 (`new LeafletMap('map')`, `import {TileLayer} from 'leaflet'`) are the **2.0-alpha ESM API** and **do not run on 1.9.4**. |
| **`leaflet-gpx`** | ⚠️ **Defer — not needed, and its docs are split across two incompatible Leaflet majors** | Published version is **2.2.0** (2025-04-24), whose npm README documents Leaflet **1.9.4 + the `L.GPX` global**. The GitHub `master` README has since been rewritten for **Leaflet 2.0 ESM** and is ahead of any release. Context7 indexes neither (`research/leaflet-context7-docs.md:13`). Its value (parse + stats in the browser) is entirely redundant once `gpxpy` parses server-side. |
| **`@raruto/leaflet-elevation`** | ❌ **Do not ship in S-03; two research claims about it are wrong** | 2.6.0 declares `peerDependencies: leaflet ^1.7.0` → **cannot run on Leaflet 2** (contradicts the same doc's Leaflet-2 direction). License is **GPL-3.0**, not the "MIT-style" claimed at `research/map-library-research.md:41`. Also pulls `d3` 7.8.4, `@tmcw/togeojson`, `leaflet-i18n` as peers — not "no new dependency". And it serves a **parked, non-FR** feature. |

**Recommended path for S-03** — this is the "server-side parse" fallback that
`research/leaflet-context7-docs.md:68,96` and `research/python-gpx-libraries.md:34`
already point at, and it overrides the `leaflet-gpx` recommendation at
`research/map-library-research.md:26,30`:

1. Persist the uploaded `.gpx` file to the Railway Volume (`/data/...`) — required by the
   PRD "data never lost" guardrail (`context/foundation/prd.md:42`) regardless of how the
   map is drawn.
2. Parse it with `gpxpy` **server-side**, catching `GPXXMLSyntaxException` and
   `GPXException`, so the PRD's "no silent map failure" NFR
   (`context/foundation/prd.md:90`) is satisfied where an error state is natural.
3. Hand the point list to the template via `{{ ...|json_script }}` and draw it with
   **core Leaflet 1.9.4** `L.polyline` / `L.marker` / `fitBounds`. No GPX plugin, no d3,
   no unverified third-party API surface.
4. Do **not** expose the raw file on an unauthenticated `MEDIA_URL` path — see the
   data-isolation conflict below.

### The five codebase blockers

| # | Blocker | Caught by CI? |
|---|---|---|
| B1 | `STORAGES` has no `"default"` alias → `default_storage` raises `InvalidStorageError` | ❌ **No** — 500s on first upload in production |
| B2 | `MEDIA_ROOT` unset (`''`); `MEDIA_URL` resolves to `"/"`, colliding with the root redirect | ❌ No |
| B3 | No media-serving mechanism; whitenoise serves `STATIC_ROOT` only, and snapshots it at boot | ❌ No |
| B4 | `collectstatic` runs inside `railway.json`'s `startCommand`, `&&`-chained before gunicorn → a vendored-CSS mistake means **the app does not boot** | ❌ No — no CI step runs `collectstatic` |
| B5 | `tests/test_coverage_scope.py` fails the build the moment a `gpx` app is installed without being added to `[tool.coverage.run] source` | ✅ Yes (a good failure) |

## Detailed Findings

### 1. The Leaflet version fork — the single most consequential finding

The two external-research docs in `research/` were written against **two different,
mutually incompatible Leaflet majors**, and neither says so.

- `leaflet@latest` on the npm registry resolves to **1.9.4** (`dist/leaflet-src.js` as
  `main`, UMD, global `L`). Leaflet 2.0 exists only as `2.0.0-alpha.1` (2025-08-16); the
  tracking issue title was changed from "The targeted release date for Leaflet V2.0 is
  November 2025" to "**unknown**" in Apr 2026.
- Leaflet 2.0 is **ESM-only**: factory functions (`L.map()`, `L.marker()`) are removed in
  favour of constructors (`new LeafletMap()`, `new Marker()`), and the `L` global is gone
  from the core package (available only via the separate `leaflet-global.js` bundle).
- **`research/leaflet-context7-docs.md` captured the 2.0-alpha API.** Every snippet in it
  — `import {LeafletMap, TileLayer, LatLngBounds} from 'leaflet'`,
  `new LeafletMap('map')`, `new Polyline(latlngs, {...})` — is 2.0-alpha syntax
  (`research/leaflet-context7-docs.md:25-27,57-65`). Implementing from those lines against
  stable 1.9.4 fails immediately; implementing against 2.0-alpha means shipping the
  north-star slice on pre-release software, weeks before the 2026-09-10 deadline
  (`context/foundation/roadmap.md:111`).
- **`research/map-library-research.md` assumed 1.x.** Its recommendation
  `L.GPX(url).addTo(map)` (`research/map-library-research.md:20`) is the 1.x global-`L`
  form, which does not exist in Leaflet 2 core.

Consequence: the two docs cannot both be followed. **Pin Leaflet 1.9.4** — the plugin
ecosystem has not migrated, and the Leaflet team has committed to maintaining 1.9 — and
treat `research/leaflet-context7-docs.md` as *2.0-alpha reference material only*, not as
the implementation contract.

#### How to re-fetch Leaflet 1.x docs from Context7 (verified live, 2026-08-24)

Context7 splits Leaflet by **source, not by version** — and
`resolve-library-id` returns **no `Versions:` list** for it, so there is no
`/leaflet/leaflet/v1.9.4` to pin. Source selection is the only lever:

| Library ID | Snippets | What it actually returns |
|---|---|---|
| `/leaflet/leaflet` | 933 | The **GitHub repo**, default branch = 2.0 dev → the `new LeafletMap('map')` / `import {TileLayer} from 'leaflet'` ESM snippets in `research/leaflet-context7-docs.md`. **Not 1.9.4.** |
| `/websites/leafletjs` | 451 | The **docs site**, crawled as **1.x** ✅ — use this one for S-03 |
| `/websites/leafletjs_reference-2_0_0` | 509 | Explicitly the 2.0.0 reference |

Verified by querying `/websites/leafletjs` for map init + polyline + markers +
`fitBounds`; it returned the classic global-`L` factory API that runs on 1.9.4:

```javascript
var map = L.map('map').fitWorld();
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
}).addTo(map);
L.marker([51.5, -0.09]).addTo(map);
var travel = L.polyline([sol, deneb]).addTo(map);
map.fitBounds(latLngBounds);
```

**Caveat:** `/websites/leafletjs` is a crawl snapshot of `leafletjs.com`, and that site's
own quick-start page already carries the Leaflet 2.0 import-map instructions. This ID can
therefore flip to 2.0 syntax on a future re-crawl or when the site promotes 2.0 as stable.

**So the durable check is the returned syntax, not the ID:**

| Returned form | Leaflet major |
|---|---|
| `L.map(...)`, `L.tileLayer(...)`, `L.polyline(...)` | **1.x** — correct for S-03 |
| `new LeafletMap(...)`, `new Polyline(...)`, `import {…} from 'leaflet'` | **2.0** — reject |

That one-glance test is what would have caught the original mismatch, and it costs nothing
to apply on every fetch.

### 2. `leaflet-gpx` — split docs, and redundant under the recommended path

- Published: **2.2.0**, 2025-04-24, BSD-2-Clause, zero deps, ~2.5k weekly downloads. The
  README shipped with that release loads `leaflet@1.9.4` + `leaflet-gpx/2.1.2/gpx.min.js`
  from cdnjs and uses `L.GPX`.
- GitHub `master`'s README now opens with "As Leaflet 2.0 is an ESM-only library, you
  should use `leaflet-gpx` as an ES module", with an import-map example against
  `leaflet@2.0.0-alpha.1`. **Master is ahead of the last release** — so the installable
  artifact and the current documentation describe different Leaflet worlds.
- Context7 has no index for it at all: *"No match. Context7 does not index
  `mpetazzoni/leaflet-gpx` … implementation must rely on the library's own README/GitHub
  source"* (`research/leaflet-context7-docs.md:13,15`). That runs against the project's own
  library-selection quality signal at `CLAUDE.md:34` (agent-readable docs) and the stated
  preference at `research/python-gpx-libraries.md:25`.
- Its entire feature set — parse GPX, expose distance/time/elevation stats — duplicates
  what `gpxpy` gives us server-side, where S-05 (`trip-distance-duration-stats`) already
  plans to compute stats (`research/gpxpy-context7-docs.md:57-77`). Adding it buys nothing
  S-03 needs and costs an unverifiable API surface.

### 3. `@raruto/leaflet-elevation` — two factual corrections to the research

`research/map-library-research.md:36-48` recommends it for a parked elevation-chart idea.
Registry metadata for **2.6.0** (published 2026-07-26, actively maintained):

- `peerDependencies`: `leaflet ^1.7.0`, `d3 7.8.4`, `@tmcw/togeojson 5.6.2`,
  `leaflet-i18n ^0.3.1`.
  → It **pins Leaflet 1.x**. It cannot coexist with the Leaflet 2.0 direction that the
  same research set's Context7 doc and the current `leaflet-gpx` README point at. It also
  is not "no new backend dependency, same Leaflet map instance, nothing to hand-build" in
  cost terms — d3 alone is larger than Leaflet.
- **License is `GPL-3.0`**, not the "MIT-style license" asserted at
  `research/map-library-research.md:41`. GPL-3.0 JavaScript is delivered to every
  visitor's browser, so the copyleft obligation attaches to what is distributed. For a
  personal project that may well be acceptable — but it is a deliberate decision, and the
  research doc records it incorrectly.
- Scope: an elevation profile is **not an FR**. It is a parked idea
  (`research/map-library-research.md:36`). Building for it inside the north-star slice is
  the kind of scope creep this repo's reviews grade as a first-class verdict dimension.

### 4. `gpxpy` — the one unambiguous green light

- 1.6.2, Apache-2.0, `Requires-Python: >=3.6`, **zero `Requires-Dist`**, universal
  `py3-none-any` wheel, `Root-Is-Purelib: true`.
- Ships type information: `setup.py` carries `package_data={"gpxpy": ["py.typed"]}`, so
  `mypy --strict` checks *our* usage against real annotations rather than falling back to
  `Any` via `ignore_missing_imports` (`pyproject.toml:50`).
- **Executed on this repo's own interpreter** (CPython 3.14.5, per `.venv/pyvenv.cfg` and
  `.python-version`): parses correctly, reports `backend = STDLIB`, `length_2d()` correct.
  Python 3.14 poses no problem — `xml.etree.cElementTree` is still importable as a shim, so
  gpxpy's fallback chain (`gpxpy/parser.py:20-27`) resolves on the first two branches.
- Neither `gpxpy` nor `lxml` is currently in `uv.lock` (30 packages, zero hits) or in
  `.venv`. Add with `uv add gpxpy` per `AGENTS.md:8`; the regenerated `uv.lock` must land in
  the **same commit**, because `.github/workflows/deploy.yml:28` runs `uv sync --locked` and
  fails on lockfile drift at step 3 of 9.
- **On `lxml`** (the open question at `research/python-gpx-libraries.md:29`): binary wheels
  for cp314 exist on both targets — verified by a wheel-only resolution for
  `x86_64-manylinux2014` (`lxml==6.1.2`) and by a real 2.6-second no-compile install into a
  3.14 probe venv. So the *build* risk the doc worried about is not the issue. The real risk
  is **behavioural**: installing `lxml` silently switches gpxpy's parser backend and takes
  the `XMLParser(remove_comments=True)` branch (`gpxpy/parser.py:132`), changing
  entity-resolution defaults with no gate that would notice. **Recommendation: don't add
  `lxml`.** One small file per web request has no performance need.

### 5. Storage and media — B1/B2/B3, and why CI stays green

`velo_log/settings.py:127-131` sets:

```python
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

Django does **not** merge `STORAGES` key-by-key. `Settings.__init__` copies
`global_settings` and then overwrites whole attributes from the user module
(`django/conf/__init__.py:157`, then `:182`), so `settings.STORAGES` becomes exactly that
one-key dict — discarding `global_settings.py:274-281`'s `"default": FileSystemStorage`.
`StorageHandler.__getitem__` has no fallback (`django/core/files/storage/handler.py:29-33`):

```python
    params = self.backends[alias]
except KeyError:
    raise InvalidStorageError(f"Could not find config for '{alias}' in settings.STORAGES.")
```

Verified at runtime against this exact settings module:

```
STORAGES        = {'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
MEDIA_ROOT      = ''
MEDIA_URL       = '/'
default_storage -> InvalidStorageError: Could not find config for 'default' in settings.STORAGES.
```

Why no gate catches it (**B1**):

- The only STORAGES system check validates the *staticfiles* alias only
  (`django/contrib/staticfiles/checks.py:24-29`, `E005`). `manage.py check`
  (`.github/workflows/deploy.yml:43`) exits 0 today.
- `FileField.__init__` assigns the **unevaluated** `LazyObject`:
  `self.storage = storage if storage is not None else default_storage`
  (`django/db/models/fields/files.py:251`). It is not resolved at import, at
  `makemigrations`, or at `check` — only on `storage.save`
  (`django/db/models/fields/files.py:98`) or `storage.url` (`:69`).

So a `FileField` added today passes ruff, black, isort, `mypy`, `manage.py check`, the
migration guard, and `pytest --cov` — then 500s on the first real upload. This is the same
shape as `context/foundation/lessons.md` rule #9 (a missing migration ships green and
surfaces as a production outage) and deserves the same treatment: a test that exercises a
real save, not just a status code.

**B2** — `MEDIA_ROOT` is `''` and `MEDIA_URL` resolves to `"/"` (Django applies
`_add_script_prefix` to any non-`None` value, `django/conf/__init__.py:82-83`, over
`global_settings.py:289`'s `""`). A `FileField.url` would therefore return `/<name>`,
colliding with the root `RedirectView` at `velo_log/urls.py:38`. Both settings must be set
explicitly, and `MEDIA_ROOT` must point at the Volume — reuse the established env pattern
from `velo_log/settings.py:86` (`env("DB_PATH", default=str(BASE_DIR / "db.sqlite3"))`).
Anything under `BASE_DIR` is destroyed on every redeploy.

**B3** — whitenoise cannot serve uploads, for two independent reasons:

- It is configured by middleware only (`velo_log/settings.py:51`); no `WHITENOISE_*`
  setting exists anywhere in the repo, so `WHITENOISE_ROOT` falls to `None` and the only
  registered directory is `STATIC_ROOT` under `/static/`
  (`whitenoise/middleware.py:102-111`).
- With `DEBUG=False`, `autorefresh` is `False` (`whitenoise/middleware.py:40-42`), and the
  file dict is a **snapshot taken once at process start** (`whitenoise/base.py:112-118`;
  served via `self.files.get(...)` at `whitenoise/middleware.py:120`). A GPX uploaded at
  10:00 would 404 until the next redeploy even if the directory *were* registered.

There is also a design consequence: `WhiteNoiseMiddleware` sits at position 2 in
`MIDDLEWARE`, *before* `AuthenticationMiddleware` (`velo_log/settings.py:51` vs `:55`) and
before URL routing. Anything whitenoise serves is unauthenticated by construction.

### 6. Static asset pipeline — B4, a boot-failure path with no CI signal

`railway.json:4`:

```
collectstatic --noinput && migrate && gunicorn velo_log.wsgi --bind 0.0.0.0:$PORT
```

This is the **`startCommand`**, `&&`-chained. If `collectstatic` exits non-zero, `migrate`
never runs and **gunicorn never starts** — a total outage, not a degraded deploy. Recovery
is manual: Redeploy a known-good deployment ID from `DEPLOY.md:7-11`. And
`.github/workflows/deploy.yml` never runs `collectstatic`, so the gates job goes green and
the failure surfaces only at container start.

That matters here because **S-03 would be the first `{% static %}` reference in the repo's
history** — there are zero `{% load static %}` and zero `{% static %}` occurrences in
`templates/`, `trips/`, or `accounts/`. `CompressedManifestStaticFilesStorage`
post-processes `url(...)` references inside collected CSS, and a reference it cannot
resolve raises (`django/contrib/staticfiles/storage.py:144-147`):

```python
if not self.exists(filename):
    raise ValueError("The file '%s' could not be found with %r." % (filename, self))
```

which is yielded as an exception (`django/contrib/staticfiles/storage.py:380-383`) and
**re-raised by the management command**
(`django/contrib/staticfiles/management/commands/collectstatic.py:152-157`).

Concretely: **`leaflet.css` 1.9.4 contains `url(images/layers.png)`,
`url(images/layers-2x.png)` and `url(images/marker-icon.png)`** — all relative, no external
hosts. Vendoring `leaflet.css` without a complete sibling `images/` directory therefore
**breaks the deploy at boot**. `WHITENOISE_MANIFEST_STRICT` does *not* relax this path:
`manifest_strict` only guards `stored_name` lookups at template-render time
(`django/contrib/staticfiles/storage.py:462,517-527`), whereas this failure comes from
`hashed_name`'s `exists()` check. Note also that Leaflet's *JS* builds
`marker-icon-2x.png` / `marker-shadow.png` URLs at runtime, which the manifest never sees —
those would 404 silently rather than break the build.

Placement, given `STATICFILES_DIRS` is unset (verified `[]`) and no `static/` source
directory exists anywhere:

- **Zero-config option:** `trips/static/trips/vendor/leaflet/...`, found by
  `AppDirectoriesFinder`.
- **Project-level option:** create `static/` at the repo root **and** add
  `STATICFILES_DIRS = [BASE_DIR / "static"]` — without the setting the directory is
  invisible to `collectstatic`.

Two mitigations worth planning: ship Leaflet's `images/` directory in full, and add a
`collectstatic --noinput` step to the `gates` job so this class of failure is caught
pre-deploy rather than at boot.

### 7. Integration points in the `trips` app

- **`Trip`** (`trips/models.py:5-21`): `name` `CharField(max_length=200)`, `date`
  `DateField`, `description` `TextField(blank=True)`, `owner` FK to
  `settings.AUTH_USER_MODEL` with `related_name="trips"`,
  `Meta.ordering = ["-date", "-id"]`. No `clean()`, no validators, no
  `get_absolute_url()`.
- **There is no detail view and no detail URL.** `trips/urls.py:8-9` defines exactly
  `trips:list` and `trips:create`; no pk-capturing route exists anywhere in the project.
  `trips/templates/trips/trip_list.html:9-16` has no per-trip link — adding one is the
  entry point to the new page. Django's default `DetailView` template name
  (`trips/templates/trips/trip_detail.html`) resolves for free given `APP_DIRS: True`
  (`velo_log/settings.py:66`).
- **Ownership pattern to copy** (`trips/views.py:24-29`, `:32-43`): CBVs with
  `LoginRequiredMixin` **first** in the base list, queryset scoping via
  `Trip.objects.filter(owner=cast(User, self.request.user))`, and owner assigned in
  `form_valid` rather than accepted from the form
  (locked in by `tests/trips/test_trip_creation.py:49-64`). Ownership yields **404, not
  403** — there is no object-permission mixin in the repo.
- **The `TYPE_CHECKING` base-alias idiom is mandatory** for every Django generic, because
  django-stubs generics are not subscriptable at runtime (`trips/views.py:14-21`,
  `trips/forms.py:7-10`, `trips/admin.py:7-10`, `accounts/views.py:12-15`). A
  `DetailView[Trip]` or `UpdateView[Trip, GpxUploadForm]` must follow the same shape.
- **Form error idiom** is copy-pasted in all three form templates
  (`trips/templates/trips/trip_form.html:7-18`,
  `accounts/templates/accounts/signup.html:7-18`,
  `accounts/templates/accounts/login.html:7-19`): `{% csrf_token %}`,
  `{{ form.non_field_errors }}`, then per-field `label_tag` / field / `errors`. This is
  `context/foundation/lessons.md` rule #2 made concrete — a bad-GPX rejection is exactly a
  non-field error. Field-level validation precedent: `accounts/forms.py:10-21`'s
  `clean_email`, which is the natural home for a `clean_gpx_file()`.
- **`enctype` appears nowhere in the repo** (zero matches for
  `enctype|multipart|FileField|upload_to`). `CreateView`/`UpdateView` pass
  `files=request.FILES` automatically, but `enctype="multipart/form-data"` on the `<form>`
  is manual.
- **`templates/base.html` has only two blocks: `title` and `content`.** No `extra_head`,
  no `scripts` block, no `<meta name="viewport">`. Adding map CSS/JS on one page means
  either introducing a new block in the shared base or inlining `<link>`/`<script>` inside
  `{% block content %}`.
- **There is no CSS at all** in the repo — no stylesheet, no framework, no inline `style`,
  not one `class=` attribute. A map needs a sized `#map` container, so S-03 is the first
  breach of the standing "no CSS, no stylesheet, no static asset" decision
  (`context/archive/2026-08-22-user-registration-login/plan.md:41`,
  `context/archive/2026-08-23-create-and-list-trips/plan.md:50`). That reversal should be
  made explicitly in the plan, per `context/foundation/lessons.md` rule #5.
- Nothing in `trips/` anticipates GPX — zero matches for `gpx|GPX|detail|MEDIA_*|leaflet`.
  `AGENTS.md:21` pre-blesses a sibling **`gpx/`** app at the repo root.

### 8. Quality gates — what will actually fail

CI (`.github/workflows/deploy.yml:15-49`) runs, in order: `uv sync --locked`,
`ruff check .`, `black --check .`, `isort --check-only .`, `mypy .`, `manage.py check`,
`makemigrations --check --dry-run`, `pytest --cov`. Job env supplies `SECRET_KEY`,
`DEBUG=False`, `ALLOWED_HOSTS=""` and deliberately **no `DB_PATH`**.

*(Note: the `python-quality-gates` and `python-checklist` skills referenced in `AGENTS.md`
are advertised in the skill listing but have no backing files on disk. The authoritative
gate list is `deploy.yml:30-49`, mirrored by the CI-equivalence command at
`AGENTS.md:43-47`.)*

**`mypy --strict` + django-stubs will reject a naive upload view.** A realistic first draft
produced 9 errors. Root causes, from the stubs:

- `django-stubs/utils/datastructures.pyi:72` — `__getitem__` returns `_V | list[object]`,
  so `request.FILES["track"]` is `UploadedFile[Any] | list[object]` and needs narrowing.
- `django-stubs/core/files/uploadedfile.pyi:10` — `UploadedFile(File[_AnyStr])` is
  **generic**, so a bare `UploadedFile` annotation trips `disallow_any_generics`; write
  `UploadedFile[Any]`.
- gpxpy returns Optionals — `get_bounds() -> GPXBounds | None`,
  `min_latitude: float | None` — so `union-attr` fires without narrowing.
- `gpxpy.parse` is typed `Union[AnyStr, IO[str]]` (`gpxpy/__init__.py:21`), but Django's
  uploaded file is **binary** (`IO[bytes]`). Passing the file object directly yields
  `[type-var]`, *not* `[arg-type]` — and since `strict` enables `warn_unused_ignores`, a
  mis-coded `# type: ignore[arg-type]` produces two errors instead of zero.

A verified strict-clean shape:

```python
upload = request.FILES.get("track")
if not isinstance(upload, UploadedFile):
    return HttpResponse(status=400)
gpx = gpxpy.parse(upload.read().decode("utf-8"))
bounds = gpx.get_bounds()
if bounds is None:
    return HttpResponse(status=400)
```

**ruff gives zero protection on XML parsing** — verified by running the repo's own config
against a probe of all five call shapes:

- `gpxpy.parse(f)` → **no rule fires.** The `S3xx` rules key on the resolved qualified
  name of the call target (`ET.parse` → S314, `minidom.parse` → S318); `gpxpy.parse` is
  opaque to ruff.
- `S320`/`S410` (lxml) are marked **Removed** in ruff 0.16.4 and are inert under a blanket
  `S` select. `preview` is unset, so S401–S415 are off too.
- No S-rule covers `open()` on a user-supplied path, `FileField`, or `UploadedFile`. The
  only Django S-rules are `S610` and `S611`.
- `.venv` is in ruff's default exclude, so gpxpy's own `ET`/`minidom` usage is never
  linted.

So untrusted-GPX hardening — size cap, extension/content check, entity-expansion limits,
path sanitisation per the global security baseline — **must be designed and tested
deliberately.** The linter will not prompt for it, and the PRD, roadmap, and archive contain
no prior constraint on file size, MIME type, or XML hardening (a grep across `context/` for
`pillow|max.?size|DATA_UPLOAD|FILE_UPLOAD|content.?type|mime|xml.?bomb|sanitiz` returns zero
relevant hits). Related: `FILE_UPLOAD_MAX_MEMORY_SIZE` defaults to 2.5 MB
(`django/conf/global_settings.py:307`), above which the upload becomes a
`TemporaryUploadedFile` — `.read()` works for both, but `.temporary_file_path()` exists
only on the disk-backed one.

**Coverage.** Baseline measured at **121 statements, 8 missed, 93.39%**, 30 tests passing.
With `fail_under = 80` (`pyproject.toml:65`), a completely untested new app can add at most
~20 statements before the total drops below the gate; a realistic ~120-statement app needs
roughly 67% coverage on the new code. And `tests/test_coverage_scope.py:49-54` **fails the
build** if `gpx` is in `INSTALLED_APPS` but not in `[tool.coverage.run] source`
(`pyproject.toml:61`) — `context/foundation/lessons.md` rule #4, mechanised. Two traps
recorded from the `ci-quality-gates` slice: register the app as the **bare string `"gpx"`**
(a dotted `gpx.apps.GpxConfig` never string-matches the guard), and place it at the **repo
root** (an app at `src/gpx/` or `apps/gpx/` is silently exempted — a false pass).

**Migration guard** (`.github/workflows/deploy.yml:45-46`). A `FileField` needs a committed
migration. Details that bite: `upload_to` is serialised into the migration (a callable must
be a module-level named function, not a lambda); `max_length` defaults to 100 and changing
it later is another migration; non-default `storage` is serialised unless it is a callable.

**`tests/test_settings_security.py:25-45`** re-executes `velo_log/settings.py` via
`spec_from_file_location`, so any new settings code must be **import-safe with only `DEBUG`
in the environment** — no side effects, no `mkdir` at module level. It does not otherwise
constrain adding `MEDIA_*`.

**Test-fixture reality.** `tests/conftest.py` provides exactly `_disable_ssl_redirect`
(autouse), `rider`, `other_rider`, `auth_client`. There is no `SimpleUploadedFile`,
`tmp_path`, or `MEDIA_ROOT` usage anywhere — S-03 writes the first upload test. Because the
suite must pass with no `.env` (`AGENTS.md:43`), `MEDIA_ROOT` must be redirected per-test
via the `settings` fixture pointed at `tmp_path`, or the suite writes real files into the
repo.

### 9. Conflicts with the PRD and prior decisions

**C1 — data isolation rules out the shape `research/map-library-research.md` recommends.**
`context/foundation/prd.md:104-105`: *"All trips are private in v1. Unauthenticated users
cannot view any trip"* / *"No user can access another user's trips under any
circumstances"*, backed by the guardrail at `prd.md:43`. Serving the raw GPX from a
conventional `MEDIA_URL` path is unauthenticated static serving — any URL holder reads
another user's track. `research/map-library-research.md:20`'s *"Serves the GPX file directly
from Django media/static — no server-side transform needed"* is precisely the non-compliant
shape, and no doc in the corpus flags it. If the file is ever served, it must go through an
ownership-scoped `FileResponse` view behind `LoginRequiredMixin`, mirroring
`trips/views.py:28,40`.

**C2 — "via whitenoise/static" is mechanically impossible for the GPX file.**
`STATIC_ROOT = BASE_DIR / "staticfiles"` is inside the ephemeral container
(`velo_log/settings.py:126`), `CompressedManifestStaticFilesStorage` only knows files
present at `collectstatic` time, and `context/foundation/roadmap.md:87` requires uploads on
the **Volume**. `research/map-library-research.md:30`'s "served as a static JS asset (via
`whitenoise`/templates — no new backend dependency)" holds for the *library file* and is
false for the *GPX file*.

**C3 — the "static map image" reinterpretation is undocumented.** FR-005 and the Primary
Success Criterion both say *static map image* (`context/foundation/prd.md:36,69-70`);
FR-015 (interactive) is parked v2 (`prd.md:85-86`).
`research/map-library-research.md:12,14` reinterprets "static" as *an interactive library
with pan/zoom/drag disabled* — a defensible call, but it has never been reflected back into
`prd.md` or `roadmap.md`. Both candidate approaches inherit this; the plan should record the
reinterpretation explicitly.

**C4 — third-party tiles vs the Non-Goals paragraph.** `context/foundation/prd.md:109`
non-goals: *"No import from or sync with any external cycling, fitness, or mapping platform
… removes third-party API dependency"*. Both approaches fetch OSM raster tiles from
`tile.openstreetmap.org`. No import, no sync, no API key — defensible, but worth an explicit
note rather than silence.

**C5 — the raw file must be persisted either way.** `context/foundation/prd.md:42`: *"Every
uploaded GPX file is durably stored and always retrievable"*. A server-side-parse approach
that persists only the derived coordinates would violate this outright. Persist the file to
`/data/...` regardless of how the map is drawn.

**C6 — silent-write-failure on the Volume.** `context/foundation/infrastructure.md:59,67`
records that a `RAILWAY_RUN_UID=0` regression makes Volume writes **fail silently**, and the
pre-mortem's exact wording is *"GPX upload records were quietly lost, violating the 'data
never lost' guardrail"*. The existing `/healthz/` round-trip proves **DB** writes only;
nothing proves a media-directory write.

**C7 — the backup runbook covers half the durable state.** `DEPLOY.md:33-56` backs up and
restores only `/data/db.sqlite3`. Once uploads land on the Volume, media is uncovered — and
`context/foundation/roadmap.md:156` (E-05) records that even the DB restore path has never
been exercised, with trigger *"before the deploy following S-03"*.

**C8 — the research set is internally contradictory, and the plan must resolve it.**
`research/map-library-research.md:26,30` recommends `leaflet-gpx` serving the file;
`research/python-gpx-libraries.md:23,34` and `research/leaflet-context7-docs.md:68,96`
assume server-side `gpxpy` → JSON. Whichever wins, the plan should say so explicitly rather
than cite "research says".

**C9 — no `|safe`.** S-02's verified security posture is *zero* `|safe` / `mark_safe` /
`autoescape off`
(`context/archive/2026-08-23-create-and-list-trips/reviews/impl-review.md`, Security
posture). Embedding the coordinate array must use `{{ ...|json_script }}`, not `|safe`.

## Code References

- `velo_log/settings.py:127-131` — `STORAGES` with only `staticfiles`; the B1 blocker
- `velo_log/settings.py:86` — `env("DB_PATH", default=...)`, the env pattern to reuse for `MEDIA_ROOT`
- `velo_log/settings.py:51` — whitenoise middleware at position 2, before auth
- `velo_log/settings.py:125-126` — `STATIC_URL` / `STATIC_ROOT`; `STATICFILES_DIRS` absent
- `velo_log/urls.py:38` — root `RedirectView`, which `MEDIA_URL = "/"` would collide with
- `trips/models.py:5-21` — the `Trip` model; no file field, no `get_absolute_url()`
- `trips/urls.py:8-9` — only `trips:list` and `trips:create`; no detail route exists
- `trips/views.py:14-21` — the mandatory `TYPE_CHECKING` base-alias idiom
- `trips/views.py:24-29,32-43` — ownership scoping and server-side owner assignment
- `trips/templates/trips/trip_form.html:7-18` — the form/error/CSRF idiom to copy
- `trips/templates/trips/trip_list.html:9-16` — where a per-trip detail link belongs
- `accounts/forms.py:10-21` — `clean_<field>()` validation precedent
- `templates/base.html` — only `title` and `content` blocks; no head/scripts block
- `tests/conftest.py:19-33` — the only fixtures (`rider`, `other_rider`, `auth_client`)
- `tests/trips/test_trip_creation.py:49-64` — the owner-cannot-be-posted test to mirror
- `tests/test_coverage_scope.py:49-61` — the new-app gate
- `tests/test_settings_security.py:25-45` — settings re-exec; keep new settings side-effect-free
- `pyproject.toml:38` — `ruff select` includes `"S"`; `:49-50` mypy strict; `:61,65` coverage
- `railway.json:4` — `collectstatic && migrate && gunicorn` as the `startCommand`
- `.github/workflows/deploy.yml:28,45-46` — `uv sync --locked`; the migration guard
- `DEPLOY.md:35,49-56` — Volume at `/data/db.sqlite3`; restore covers the DB only
- `django/core/files/storage/handler.py:29-33` — `InvalidStorageError`, no fallback
- `django/db/models/fields/files.py:251` — `default_storage` bound lazily, hence no gate catches B1
- `django/contrib/staticfiles/storage.py:144-147` — the `collectstatic` hard failure
- `whitenoise/middleware.py:102-111`, `whitenoise/base.py:112-118` — static-only, boot snapshot

## Architecture Insights

- **The repo's gates are strong on shape and weak on runtime behaviour.** Lint, format,
  import order, strict typing, `check`, the migration guard, and 93% coverage all pass on a
  codebase whose `default_storage` cannot resolve. Every blocker in this slice that CI
  misses (B1–B4) is a *first-use* or *deploy-time* failure. The pattern already has a named
  precedent in `context/foundation/lessons.md` rule #9, and the mitigation is the same: a
  test that performs the real operation, plus a `collectstatic` step in `gates`.
- **`collectstatic` living in `startCommand` rather than a build step converts an asset
  mistake into an availability incident.** Worth an engineering-backlog row independent of
  S-03.
- **The `owner`-scoped-queryset pattern is the whole authorization story.** There is no
  object-permission layer, so anything served outside the Django view stack (whitenoise, a
  bare `MEDIA_URL`) is outside authorization entirely. That constrains the media design far
  more than the map-library choice does.
- **Preferring server-side parsing collapses three risks at once**: no unverified
  third-party JS API, no client-side silent failure (the PRD's only NFR), and no
  unauthenticated file endpoint. It also front-loads S-05's stats work onto the same `gpxpy`
  object model with no second dependency (`research/gpxpy-context7-docs.md:57-77`).
- **Context7 indexes a library per *source*, and each source is a point-in-time snapshot of
  whatever branch or site it crawled.** Here `/leaflet/leaflet` (the GitHub repo, default
  branch = 2.0 dev) returned pre-release 2.0-alpha docs for a library whose stable release
  is 1.9.4, with nothing in the response marking it as pre-release. Version pinning was not
  available as a remedy — `resolve-library-id` offered no `Versions:` list — so picking the
  right source ID (`/websites/leafletjs`) was the only lever, and even that can drift on a
  re-crawl. Candidate lesson: **cross-check the package registry for what "latest" actually
  resolves to, then verify the returned snippets use that version's syntax** — for Leaflet
  that is a one-glance `L.map(...)` vs `new LeafletMap(...)` test. Trusting a library ID is
  not the same as trusting a version.

## Historical Context (from prior changes)

- `context/archive/2026-08-23-create-and-list-trips/plan.md:46` — *"No GPX upload, file
  storage, map rendering, or `MEDIA_ROOT` configuration — that is S-03. No media config
  exists at all today and this slice does not add any."* The deferral was deliberate.
- `context/archive/2026-08-23-create-and-list-trips/research.md:97` — already recorded
  *"`MEDIA_ROOT` / `MEDIA_URL` do not exist at all — no media config, no
  `STORAGES["default"]`"*. This research confirms the consequence: it is not merely absent,
  it **raises** on use.
- `context/archive/2026-08-23-create-and-list-trips/research.md:92` — the
  `CompressedManifestStaticFilesStorage` warning ("unforgiving"), now traced to the exact
  exception and the boot-failure blast radius.
- `context/archive/2026-08-22-user-registration-login/plan.md:41` and
  `context/archive/2026-08-23-create-and-list-trips/plan.md:50` — the standing "no CSS, no
  static asset" decision that S-03 necessarily reverses.
- `context/archive/2026-08-22-user-registration-login/reviews/impl-review.md:44-73,77-101` —
  F1 (blank form, no feedback) and F2 (test asserting less than its name claims), now
  `context/foundation/lessons.md` rules #1 and #2. A bad-GPX rejection path is the same
  class of code.
- `context/changes/ci-quality-gates/plan.md:65,255-256` and
  `context/changes/ci-quality-gates/reviews/impl-review.md:197-198` — the coverage guard's
  two traps for the expected `gpx` app: dotted AppConfig paths, and non-root app locations.
- `context/changes/deployment/deployment-plan.md:101-102` — Volume mounted at `/data`;
  `RAILWAY_RUN_UID=0` required; builder is Railpack, with `RAILPACK_PYTHON_VERSION=3.14` set
  alongside `.python-version`.

## Related Research

- `context/changes/upload-gpx-and-view-map/research/python-gpx-libraries.md` — exa.ai
  library survey selecting `gpxpy`. **Confirmed.** Its open question on `lxml` is resolved
  above (wheels exist for cp314; skip it anyway, for behavioural reasons).
- `context/changes/upload-gpx-and-view-map/research/gpxpy-context7-docs.md` — Context7 API
  capture. **Accurate and usable as-is**; the exception pair to catch
  (`GPXXMLSyntaxException`, `GPXException`) is correct.
- `context/changes/upload-gpx-and-view-map/research/leaflet-1.9.4-context7-docs.md` —
  **the Leaflet reference to implement against.** Fetched from `/websites/leafletjs` per §1;
  every snippet passes the 1.x tell-tale test. It also records explicitly which S-03 needs
  Context7 did *not* cover (the `L.map` interaction options that make the map behave as a
  static image, and `fitBounds` padding/`maxZoom`) — both load-bearing, both to be verified
  against `leafletjs.com/reference.html` or the vendored `leaflet.js` at implement time.
- `context/changes/upload-gpx-and-view-map/research/leaflet-context7-docs.md` — **superseded
  for implementation purposes** by the file above. The snippets are Leaflet **2.0-alpha
  ESM**, not stable 1.9.4, because it was fetched from `/leaflet/leaflet`. Keep it as
  2.0 reference material for the eventual FR-015 upgrade. Its own recommendation at
  `:68,96` (server-side parse, core `Polyline`, no plugin) is the right call and is what
  this research endorses.
- `context/changes/upload-gpx-and-view-map/research/map-library-research.md` — **two
  corrections**: `@raruto/leaflet-elevation` is GPL-3.0 (not "MIT-style", `:41`) and pins
  `leaflet ^1.7.0`; and "serve the GPX file from Django media/static" (`:20,30`) conflicts
  with `context/foundation/prd.md:104-105` and is impossible in its `static/` form. Its core
  architectural call — a client-side JS map library over a server-rendered PNG, to avoid
  rebuilding for FR-015 — remains sound.
- `context/archive/2026-08-23-create-and-list-trips/research.md` — the S-02 codebase
  baseline this builds on.

## Open Questions

1. **Is the raw GPX file ever served to the browser?** Not needed for the recommended path,
   but "download my GPX" is a plausible want, and it forces the authenticated
   `FileResponse` view (C1). Decide now or explicitly defer.
2. **Upload validation limits.** No prior decision exists on max file size, extension
   allow-list, or content sniffing, and ruff will not prompt. What is the cap? (Suggestion:
   an explicit `clean_gpx_file()` in the form, mirroring `accounts/forms.py:10-21`.)
3. **Does `MEDIA_ROOT` get created at runtime, and how is a silent Volume-write failure
   detected?** C6 says a `/data/media` permission regression loses files quietly. Should
   `/healthz/` be extended to round-trip a media write, mirroring its DB round-trip?
4. **Should `collectstatic --noinput` be added to the `gates` job** (new engineering-backlog
   row) so B4 stops being a deploy-time-only failure mode?
5. **Vendored vs CDN for Leaflet.** No policy exists (zero hits for
   `cdn|unpkg|jsdelivr|integrity|CSP` across the repo). Vendoring costs the `images/`
   discipline of B4; a CDN costs an external runtime dependency and needs an SRI convention.
   Recommendation: vendor, ship `images/` in full, and add the `collectstatic` gate.
6. **Does the "static map image" reinterpretation (C3) get written back into `prd.md`?**
   Roadmap and PRD still say *image*.
7. **New app `gpx/` vs extending `trips/`.** `AGENTS.md:21` pre-blesses `gpx/`, but a
   one-`FileField`-on-`Trip` design (PRD v1: exactly one file per trip,
   `context/foundation/prd.md:96`) may not warrant a second app — and a new app triggers the
   coverage-source edit and the `startapp` `tests.py` cleanup. Plan-time call.
