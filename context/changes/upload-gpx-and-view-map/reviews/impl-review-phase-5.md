<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Upload a GPX file and view the route as a map

- **Plan**: `context/changes/upload-gpx-and-view-map/plan.md`
- **Scope**: Phase 5 of 6 — Map rendering and the static pipeline (commits `a48a5d6`, `63bd6cf`, `2ae03d1`)
- **Date**: 2026-08-25
- **Verdict**: REJECTED — one critical finding, fixable in one line
- **Findings**: 1 critical, 5 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | FAIL |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

Scope Discipline is PASS rather than WARNING despite four unplanned files
(`gpx/map_config.py`, `gpx/views.py`, `.gitattributes`, the `tests/conftest.py` fixture):
each is required by the plan's own stated intent, none extends product surface, and all
four are argued in code and in their commit messages. The gap is documentary and is
carried as F5 under Plan Adherence rather than counted twice.

## Automated verification (re-run for this review)

| Gate | Result |
|---|---|
| `ruff check .` | pass |
| `black --check .` | pass — 55 files unchanged |
| `isort --check-only .` | pass |
| `mypy .` | pass — no issues in 55 source files |
| `manage.py check` | pass — 0 issues |
| `makemigrations --check --dry-run` | pass — no changes detected |
| `collectstatic --noinput` | pass — exit 0, 141 unmodified, 375 post-processed |
| `pytest --cov` (CI-equivalent env) | pass — 109 passed, coverage 99.78% (`fail_under = 80`) |
| `git status` after the above | clean — `staticfiles/` and `media/` both gitignored |

Progress rows 5.1 and 5.3–5.6 are supported by the above. 5.2 (the `gates` step observed
passing in CI) and 5.12 (deferred to 6.9) are correctly left open — the `collectstatic`
step is present and correctly positioned at `.github/workflows/deploy.yml:51-52`, with the
job-level `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` it needs, but no PR run has exercised it.

## Plan adherence detail

Seven of the eight "Changes Required" items are clean matches, several exceeding their
contract in ways the plan's own rationale asked for (`iconRetinaUrl` alongside the two
named icon URLs; the upstream icon anchors restated because supplying `iconUrl` opts out
of `L.Icon.Default`; a property-based inline-script test instead of a `|safe` grep; a
SHA-256 table in the vendor note). The single drift is §6 — see F5.

The security posture the plan set holds: `trips/templates/trips/trip_detail.html:30` uses
`{{ map_config|json_script:"map-config" }}` and nothing else, there is no inline `<script>`
on the page, and a repo-wide search for `|safe` / `mark_safe` / autoescape-off returns only
a comment and a docstring. `tests/trips/test_trip_detail_map.py:83-108` pins that as a
structural invariant — every `<script>` must be `src`-loaded with an empty body, or inert
`type="application/json"` — which is stronger than the contract asked for and is the best
thing in the slice.

## Findings

### F1 — A short or single-point track fits the map to an unbounded zoom

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/static/gpx/map.js:29-41`, `:69`
- **Detail**:
  `L.map("map", {...})` passes no `maxZoom`, and the tile layer's `maxZoom: 19`
  (`map.js:44`) has not reached the map by the time `fitBounds` runs. Verified against the
  vendored 1.9.4 bytes, not from memory:

  - `Map.addLayer` ends in `this.whenReady(t._layerAdd, t)`, and `whenReady` defers to the
    `load` event whenever `_loaded` is false.
  - `Map.initialize` calls `setView` only under `e.center && void 0!==e.zoom` — neither is
    passed here, so `_loaded` stays false and all four `addTo(map)` calls at `:46`, `:48`,
    `:62`, `:63` are queued.
  - The tile layer's limit registers via `_addZoomLimit(this)`, which is called from
    `GridLayer.onAdd` — inside the deferred `_layerAdd`.
  - `getMaxZoom` reads `void 0===this.options.maxZoom ? (void 0===this._layersMaxZoom ? 1/0 : ...)`.

  So `fitBounds` at `:69` — the first call that gives the map a view — sees
  `getMaxZoom() === Infinity`. Two consequences, both silent:

  1. **Degenerate bounds.** `gpx/parsing.py:162-163` rejects only a *zero*-point track, so a
     one-point GPX (or one whose points are all identical) is accepted and stored with
     `min == max` on both axes. `getBoundsZoom` then divides the container size by a
     zero-size box: `a = size.x/0 = Infinity`, `getScaleZoom(Infinity)` returns `Infinity`,
     zoom-snap preserves it, and `Math.max(0, Math.min(Infinity, Infinity))` is `Infinity`.
     `setView(center, Infinity)` makes `project()` non-finite, so the pixel origin is
     garbage: no tiles, no polyline, no markers, no error — an 18rem-to-60vh empty
     rectangle under a successful upload confirmation.
  2. **Short tracks.** Any track small enough to fit past zoom 19 is fitted there. The tile
     layer registers `maxZoom: 19` a moment later on `load`, but Leaflet does not
     retroactively clamp the current zoom, so the route draws over blank tiles.

  This is the exact failure `prd.md:90` forbids ("if the map cannot be rendered, the user
  receives a clear error state, not a blank page"), and it is the failure the whole
  parse-at-upload architecture was justified by. Nothing catches it: `map.js` has no
  automated test, and `tests/conftest.py:15`'s `GPX_POINTS` is two distinct points, so no
  fixture in the suite is degenerate. The plan asserted at §4 that the client "keeps the
  degenerate-bounds decision server-side where it was already made" — but that decision
  (`plan.md:638-640`) only ever covered the empty case.
- **Fix**: Pass `maxZoom` to `L.map` so the ceiling exists before `fitBounds` needs it —
  ideally as one shared constant used by both the map options and the tile layer, so the
  two cannot drift apart.
  - Strength: One line closes both manifestations at once. Degenerate bounds clamp to the
    tile layer's real maximum and render a valid z19 view of the point; short tracks stop
    at the deepest zoom OSM actually has tiles for. No change to the server, the payload,
    or the template.
  - Tradeoff: None material. It duplicates the number `19` unless a shared constant is
    introduced, which is why the fix names one.
  - Confidence: HIGH — the mechanism is confirmed line by line in the vendored bytes
    (`whenReady` deferral, `_addZoomLimit` inside `GridLayer.onAdd`, the `1/0` fallback in
    `getMaxZoom`, and the `size/0` path in `getBoundsZoom`), not inferred from upstream docs.
  - Blind spot: Not reproduced in a live browser — no browser automation was available in
    this review. A companion single-point rejection in `parse_gpx` would also close case 1
    but would leave case 2 open, so it is not a substitute; it is worth considering
    separately as a product question (is a one-point ride a trip at all?).
- **Decision**: PENDING

### F2 — The map container has no fallback, so every client-side failure renders a blank box

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `trips/templates/trips/trip_detail.html:24`, `gpx/static/gpx/map.js:18-29`
- **Detail**:
  `<div id="map"></div>` ships empty, and `static/css/style.css:16-21` gives it
  `height: 60vh; min-height: 18rem`. The server-side branch is handled properly —
  `gpx/map_config.py:44` returns `None` and `trip_detail.html:35` says so in words, tested
  at `tests/trips/test_trip_detail_map.py:149` — but nothing downstream of the HTML has any
  reserve. Four reachable paths all end in the same silent empty rectangle:
  JavaScript disabled; `leaflet.js` failing to load (a blocker, a future CSP, a bad deploy)
  so `map.js:29` throws `ReferenceError: L is not defined`; `style.css` failing to load, so
  `#map` collapses to zero height — the exact failure `style.css:9-15` documents in prose
  and nothing guards; or `JSON.parse` / `L.polyline` throwing on a malformed `points` value,
  which is a bare `JSONField` (`gpx/models.py:30`) excluded from the admin form
  (`gpx/admin.py:27`) and so reachable by shell or migration — the same class of row
  `build_map_config`'s empty-list branch already exists to defend against.
  F1 is one more entry on this list, which is why the two are worth fixing together.
- **Fix**: Put the error state *inside* the container as fallback content, and have
  `map.js` remove or clear it as its last successful step, with the IIFE body wrapped in
  `try/catch` so a throw leaves the fallback standing.
  - Strength: One mechanism covers all five paths including F1, needs no new template
    branch, and finally makes the NFR true for the client half rather than the server half.
    It also survives failures nobody has enumerated yet.
  - Tradeoff: The fallback text is briefly visible on a slow load — mitigable by hiding it
    behind a class the script toggles, at the cost of reintroducing a CSS dependency into
    the failure path.
  - Confidence: HIGH — the pattern is standard and the container already has a stable id.
  - Blind spot: Whether the fallback should offer the download link inline (the file is
    still attached, and `trip_detail.html:39` already links it a few lines below) is a copy
    decision, not verified with the user.
- **Decision**: PENDING

### F3 — Nothing verifies that a static reference resolves, and the fixture that removed the check says otherwise

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: `tests/conftest.py:47-69`
- **Detail**:
  The new autouse `_plain_staticfiles_storage` fixture swaps `CompressedManifestStaticFilesStorage`
  for plain `StaticFilesStorage` across the whole suite. The fixture is necessary — once
  `templates/base.html:11` links a stylesheet, every page-rendering test goes through
  staticfiles storage, and a fresh clone with no `staticfiles.json` would fail on all of
  them — and it correctly spreads `STORAGES` rather than replacing it, preserving the
  `"default"` alias the upload tests need.

  Its stated justification is wrong, though, and that matters more than the fixture:
  "the `gates` job runs `collectstatic --noinput`, which is what proves every reference
  resolves." `collectstatic` post-processing rewrites references found *inside collected
  CSS and JS* — that is what makes the vendor sibling-vendoring rule real. It never reads
  templates or Python. So a wrong path in `base.html:11`, `trip_detail.html:8,64,65`, or
  `gpx/map_config.py:23-25` would pass `collectstatic` (nothing looks at it), pass `pytest`
  (plain storage never raises on an unknown name, and
  `tests/trips/test_trip_detail_map.py:77-79` asserts only that the substring the template
  itself produced appears in the body), and then 500 the page in production —
  `WHITENOISE_MANIFEST_STRICT` defaults true, so a missing manifest entry is a `ValueError`.
  Since `base.html` loads the stylesheet unconditionally, that 500 is site-wide, not
  map-only.

  The paths are correct *today* — Progress 5.7–5.11 were confirmed by hand under the dev
  server, where a wrong path 404s and the map does not draw. What is missing is regression
  protection. Relatedly, `test_the_marker_icon_urls_come_from_the_staticfiles_storage`
  (`:112-131`) now proves only that `STATIC_URL` is prefixed, which plain storage does by
  concatenation; its docstring's claim to distinguish "a URL that was resolved from one
  that was written out" overreaches under the fixture (lessons rule #1, mildly).
- **Fix**: Keep the fixture, correct its docstring, and add one manifest-free test
  asserting `django.contrib.staticfiles.finders.find(...)` is not `None` for
  `css/style.css`, `gpx/map.js`, both vendored Leaflet files, and the three `MARKER_*`
  constants imported from `gpx.map_config`.
  - Strength: Catches the whole class — a renamed, moved, or mistyped asset — with no
    manifest and no `collectstatic` dependency, so it works on a fresh clone. Importing the
    constants rather than restating the paths means the test cannot drift from the code.
  - Tradeoff: It proves existence, not hashed resolution; that last link stays with
    Progress 6.9, where it is already recorded.
  - Confidence: HIGH — `finders.find` is exactly the lookup `collectstatic` itself uses to
    locate sources.
  - Blind spot: A detail-page render under the real manifest storage, `skipif`
    `staticfiles.json` is absent, would go further and *would* run in CI, since the `gates`
    job now collects before it tests. Not evaluated for flakiness here.
- **Decision**: PENDING

### F4 — `AGENTS.md` is stale in four places this slice invalidated

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `AGENTS.md`
- **Detail**:
  `AGENTS.md` loads every session and `README.md:9` delegates to it, so a stale claim
  misdirects the next agent rather than merely aging — this is lessons rule #5, which the
  plan itself cited (§2) as the reason to record the CSS reversal.
  - Project Structure documents `templates/` as the project-level shared directory that
    `TEMPLATES[0]["DIRS"]` points at, but not its exact twin — `static/` and
    `STATICFILES_DIRS` (`velo_log/settings.py:146`), whose own comment says it "mirrors the
    `TEMPLATES["DIRS"]` convention above exactly".
  - The app list is `accounts/`, `trips/`; `gpx/` has been installed since Phase 2
    (`settings.py:60`) and appears only as a parenthetical hypothetical.
  - "Coverage runs against `accounts`, `trips`, and `velo_log`" — `pyproject.toml:62` is
    `["accounts", "trips", "gpx", "velo_log"]`. The scope was widened correctly in `54b06a4`
    (lessons rule #4 satisfied); only the doc lagged.
  - The gates-job list omits the new `collectstatic` step, and the Development Commands
    table has no `collectstatic` row — now the command standing between the repo and a
    bootable deploy, since `railway.json` chains it ahead of gunicorn.
- **Fix**: Update all four in `AGENTS.md` in this slice. Phase 6's documentation work
  already owns doc reconciliation and Progress 6.2 already asserts no stale `gpx` claim
  remains — so the cleanest resolution is to fold these four into that row rather than open
  new work.
- **Decision**: PENDING

### F5 — Plan §6 was never amended, so four shipped files appear nowhere in the plan

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `context/changes/upload-gpx-and-view-map/plan.md`, Phase 5 §6 "Map view context"
- **Detail**:
  Plan §6 names `trips/views.py` as its only file and says `get_context_data` builds the
  config dict. What shipped is a new module, `gpx/map_config.py`, called from *both*
  `trips/views.py:80` and `gpx/views.py:100`.

  The drift is right, not wrong: `GpxUploadView` re-renders `trips/trip_detail.html` on a
  validation failure (`gpx/views.py:60`), so a helper reachable only from `TripDetailView`
  would have shown "route could not be displayed" over a perfectly good track after every
  rejected upload. That is a real defect latent in the plan's own wording. It is argued in
  the module docstring (`gpx/map_config.py:3-11`, including why it sits in `gpx` rather than
  `trips` — building it in `trips` would add a second cross-app edge), stated in the commit
  message, and pinned by `tests/trips/test_trip_detail_map.py:177-198`.

  The problem is only that the plan never recorded it. Searching the plan for `map_config`
  returns zero hits; the plan.md diff inside `63bd6cf` touches only Progress checkboxes.
  The same is true of the three other unplanned files — `gpx/views.py`, `.gitattributes`
  (`gpx/static/gpx/vendor/** -text`, load-bearing: `core.autocrlf=true` on this machine
  would otherwise change the vendored bytes on checkout and produce different content-hashed
  asset names locally than in CI), and the `tests/conftest.py` fixture, which is an
  unavoidable consequence of §3 that the plan should have anticipated. A future reader
  diffing the tree against the plan finds an unexplained module and three unlisted files.
- **Fix**: Amend Phase 5 §6 to name `gpx/map_config.py` and `gpx/views.py` with the
  two-render-paths reason, and add one line each for `.gitattributes` and the conftest
  fixture, marked as discovered during implementation.
  - Strength: The plan is the artifact every later review and `/10x-archive` diffs against;
    the reasoning already exists in the code and commits, so this is transcription, not
    rediscovery. Preserves work that is correct.
  - Tradeoff: The plan becomes a slightly moving target — acceptable, and already the
    convention here (Performance Considerations records a reversed decision the same way).
  - Confidence: HIGH — the addendum pattern is used twice already in this plan.
  - Blind spot: None significant.
- **Decision**: PENDING

### F6 — The coordinate payload ships uncompressed at full float precision

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `velo_log/settings.py:63-72`, `gpx/parsing.py:154-159`
- **Detail**:
  The cap itself is good work: `MAX_GPX_POINTS = 100_000` (`gpx/constants.py:22`) was
  reinstated on a real Phase 4 measurement and bounds the payload at roughly 2.4 MB. Two
  things it does not address, both on the render path this phase introduced:
  - **No compression on dynamic responses.** `MIDDLEWARE` has no `GZipMiddleware`, and
    whitenoise compresses collected static assets only — never the HTML the payload is
    inlined into. Coordinate JSON compresses to roughly a fifth of its size, which on a
    2.4 MB page is the difference the PRD's perceived-responsiveness NFR is about. Whether
    Railway's edge compresses is not recorded in `DEPLOY.md`, so today this is unverified
    in either direction.
  - **Full float precision.** `gpx/parsing.py:154-159` passes gpxpy's floats through
    untouched, so a coordinate serialises as e.g. `50.061234567890123`. Five decimals is
    about a metre — far finer than a z19 tile can show.
- **Fix A ⭐ Recommended**: Round coordinates at the parse boundary now; check and record
  whether Railway's edge already gzips before adding middleware.
  - Strength: Rounding is a one-line, purely additive change with no visible effect and no
    new middleware in the request path, and it shrinks both the stored column and the
    response. Checking the edge first avoids double compression and keeps a BREACH
    conversation from being opened for nothing.
  - Tradeoff: Rounding alone leaves most of the win on the table if the edge turns out not
    to compress, so this defers rather than closes half the finding.
  - Confidence: MEDIUM — the rounding effect is certain; the edge behaviour is genuinely
    unknown and needs the deployed instance, which Phase 6 will have.
  - Blind spot: Rounding changes stored values, so it applies to newly parsed tracks only —
    existing rows keep full precision unless backfilled. Nothing depends on that precision
    today, but S-05 (trip stats) will read the same column.
- **Fix B**: Enable `GZipMiddleware` and round, without waiting on the edge check.
  - Strength: Closes the whole finding inside this slice, independent of anything Railway
    does or later changes about.
  - Tradeoff: Possible double compression, and it puts a compression pass on every response
    for the sake of one page. Django masks the CSRF token per response so BREACH stays at
    the usual accepted level, but it is a security conversation this slice did not plan for.
  - Confidence: MEDIUM — the mechanism is standard; the interaction with Railway's proxy is
    the unverified part.
  - Blind spot: Neither option is measured against a real multi-day tour export — the only
    payload figure on record is the synthetic worst case from the Phase 4 review.
- **Decision**: PENDING

### F7 — The OSM tile dependency is recorded only in an artifact bound for the archive

- **Severity**: ⚪ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: `gpx/static/gpx/map.js:43`
- **Detail**:
  Every map view fetches raster tiles from `https://tile.openstreetmap.org`. The plan covers
  this correctly under Performance Considerations — browser-side only, so an OSM outage
  degrades to blank tiles with the route still drawn, and there is no server-side dependency
  — but `README.md`, `DEPLOY.md` and `AGENTS.md` say nothing, and `context/changes/` is
  headed for `context/archive/`. Three things an operator would lose with it: the OSM Tile
  Usage Policy now applies to this app and asks that the application be identifiable;
  each map view sends a viewer's IP and the tile coordinates of a private route to a third
  party, with the trip URL itself protected only by Django's `SECURE_REFERRER_POLICY`
  default of `same-origin` — an implicit dependency nobody chose deliberately; and there is
  still no CSP anywhere in `settings.py`, which is not a regression but is newly relevant
  now that a page loads remote images at all.
- **Fix**: Add a short third-party-dependency note to `DEPLOY.md` (or `AGENTS.md`) naming
  the tile host, the usage policy, and the referrer-policy dependency — and record that,
  because this page carries zero inline script, a `script-src 'self'` /
  `img-src 'self' https://tile.openstreetmap.org` / `style-src 'self'` policy would work
  today. Worth writing down before someone adds an inline handler and closes that door.
- **Decision**: PENDING

### F8 — The vendored SHA-256 table is documentation, not a control

- **Severity**: ⚪ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `gpx/static/gpx/vendor/README.md`
- **Detail**:
  The vendor note is above the usual bar: version, upstream URL, licence, a per-file
  "why it must be vendored" table, SHA-256 for all eight files, and a `.gitattributes`
  companion with a genuinely good rationale. But nothing verifies those hashes — there is no
  `SHA256SUMS` file and no CI step — so today they record what was downloaded rather than
  guaranteeing what is checked out.
- **Fix**: If the intent is a supply-chain guarantee rather than a note, add a `SHA256SUMS`
  beside the README and a `shasum -c` step in the `gates` job. If the intent is only
  traceability for a future upgrade, say so in the README so the table is not mistaken for
  a control.
- **Decision**: PENDING

### F9 — Marker path constants sit outside `gpx/constants.py`

- **Severity**: ⚪ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `gpx/map_config.py:23-25`
- **Detail**:
  `MARKER_ICON`, `MARKER_ICON_RETINA` and `MARKER_SHADOW` are module-level in
  `map_config.py`, while the project rule is that every magic string is a named constant in
  `constants.py` — where `MAX_GPX_POINTS` and `ALLOWED_GPX_EXTENSIONS` already live.
  Defensible as written: there is a single consumer, and `gpx/constants.py`'s docstring
  scopes itself to "the GPX upload boundary" while these are render-side. Everything else in
  the module matches house style exactly — full type hints, Google-style docstring, no
  `print`, and a module docstring explaining the cross-app placement in the same voice as
  `trips/views.py:11-15`. The `TYPE_CHECKING` base-alias idiom is correctly absent (no
  Django generic here) and untouched in both views.
- **Fix**: Either move the three to `gpx/constants.py` and widen its docstring to cover the
  render boundary, or add one line to `map_config.py` saying why render-side paths stay with
  their only consumer — so it reads as a decision rather than a drift.
- **Decision**: PENDING

### F10 — Static-asset blast radius widened from one page to every page

- **Severity**: ⚪ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: `templates/base.html:11`
- **Detail**:
  The stylesheet is linked unconditionally, so every page in the app now resolves through
  staticfiles storage; before this slice no page did. Under
  `CompressedManifestStaticFilesStorage` a missing or incomplete `staticfiles.json`
  therefore 500s the whole site rather than one map. `railway.json` chains `collectstatic`
  ahead of gunicorn, so the realistic outcome is a loud boot failure instead — which is the
  right call and is exactly what `deploy.yml:48-50`'s comment says — but the change in blast
  radius is not written down anywhere an operator would look.
- **Fix**: Add a line to `DEPLOY.md` beside the collectstatic note: a manifest failure is
  now site-wide, not map-only, and the boot-time chain is what converts it into a failed
  deploy rather than a broken site.
- **Decision**: PENDING

## Checked and clean

Authorization on both render paths, still the owner-scoped queryset with no object-permission
layer introduced (`trips/views.py:66`, `gpx/views.py:78-87`); the new context keys leak
nothing cross-user. No secrets, no injection. No N+1 — the detail render is two queries, and
`track` is reused for the context key and for `build_map_config` rather than re-fetched.
`GpxUploadView.get_context_data` supplies the same `map_config` key as `TripDetailView`, with
a test that names the real failure (`tests/trips/test_trip_detail_map.py:178`).
`{{ form.non_field_errors }}` is present at `trip_detail.html:50` (lessons rule #2). Coverage
`source` includes `gpx` (rule #4). No migration in this slice, so rule #9 is not engaged.
All eight Leaflet interaction options from the plan's snippet are present verbatim
(`map.js:33-40`); `attribution` is passed explicitly; bounds come from the server, not
`polyline.getBounds()`. `config.points[0]` and `points[length-1]` are safe because
`build_map_config` returns `None` for an empty list, and the `map_config` template guard is
unambiguous (`None` or a non-empty dict, never `{}`). `GpxTrack.Meta.ordering` makes
`tracks.first()` deterministic. `staticfiles/` and `media/` are gitignored and `git status`
is clean after a full run.
