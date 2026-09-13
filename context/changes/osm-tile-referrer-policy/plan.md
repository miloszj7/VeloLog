# Restore OSM tile loading by sending a compliant Referer — Implementation Plan

## Overview

The trip detail map on the Railway production deploy renders its route polylines but every
OpenStreetMap basemap tile comes back as a "403 / access blocked" placeholder. The cause is
a Django default: `SecurityMiddleware` emits `Referrer-Policy: same-origin`, which stops the
browser sending any `Referer` on the cross-origin requests to `tile.openstreetmap.org` — a
value OSM's tile usage policy names explicitly as non-compliant.

This change sets a compliant policy globally, passes the equivalent option on the Leaflet
tile layer so the map survives a future tightening of that global value, pins both halves
against silent regression, and verifies the result against production.

## Current State Analysis

**The header.** `velo_log/settings.py:111` registers `django.middleware.security.SecurityMiddleware`
as the first middleware. `SECURE_REFERRER_POLICY` is never set anywhere in that file, so
Django's default applies. Confirmed against the installed source at
`.venv/Lib/site-packages/django/conf/global_settings.py:663`:

```
SECURE_REFERRER_POLICY = "same-origin"
```

Confirmed live on the deploy:

```
$ curl -sS -I https://velolog-production.up.railway.app/healthz/
HTTP/1.1 200 OK
referrer-policy: same-origin
```

`same-origin` instructs the browser to omit `Referer` entirely on any cross-origin request.
Every tile fetch therefore reaches OSM unidentified.

**The tile layer.** `gpx/static/gpx/map.js:71-73` requests tiles from
`https://tile.openstreetmap.org/{z}/{x}/{y}.png` and passes the required attribution. Both
are already policy-correct; nothing about the map code is wrong. The vendored Leaflet is
**1.9.4** (`gpx/static/gpx/vendor/leaflet/leaflet.js`), whose `TileLayer` defaults include
`referrerPolicy:!1` — the option exists and is read when creating each tile `<img>`, but
defaults to unset, so tiles inherit the page's global header.

**What OSM requires.** The [OSM wiki Referer page](https://wiki.openstreetmap.org/wiki/Referer)
gives an explicit allow/deny list: the policy must be one of `no-referrer-when-downgrade`,
`origin`, `origin-when-cross-origin`, `strict-origin`, `strict-origin-when-cross-origin` —
and must **not** be `no-referrer` or `same-origin`. A member of the OSM Operations team names
Django by name in the Leaflet discussion: *"This is because django, by default, sets the
`referrer-policy` header to `same-origin` unless configured otherwise."*

**Why the block message reads as the general one.** The observed tile says "not following the
tile usage policy" rather than "Referer is required". OSM treats these as different blocks,
and only the latter is documented as self-healing. The community thread on the September 2025
enforcement window explains the general wording for this case: a browser request arriving with
no `Referer` is classified as an *application* rather than a website, and is then judged on its
`User-Agent` — which for a browser is generic and identifies nothing. Unidentified-app traffic
draws the general policy block. This is consistent with the referer being the root cause, but
it is not proof, which is why Phase 3 exists.

**Blast radius of loosening the header.** Grepping `templates/`, `trips/templates/` and
`gpx/templates/` for `https://` hosts returns nothing, and there is no frontend Sentry SDK
(`sentry-sdk` is server-side only). The OSM tile fetch is the **only** cross-origin request
the application makes. Under `strict-origin-when-cross-origin` the sole new disclosure is the
bare origin `https://velolog-production.up.railway.app/` — sent to the one party that is
already receiving the tile coordinates of the user's rides. No path, no query, no trip pk.

**Existing test surface.**

- `tests/test_settings_security.py` loads `velo_log/settings.py` fresh via
  `spec_from_file_location` into a throwaway module (deliberately *not* `importlib.reload`,
  per its own module docstring) and pins `SECURE_SSL_REDIRECT`, both cookie-secure flags,
  `SECURE_PROXY_SSL_HEADER` and `SECURE_HSTS_SECONDS`. It is the natural home for the header
  assertion — but it only ever loads with `DEBUG=False`, and this setting is module-level.
- `map.js` **contents are asserted nowhere.** `tests/test_static_references.py:57` and
  `tests/trips/test_trip_detail_map.py:317` assert only that the path `gpx/map.js` resolves
  and is referenced. There is no JS test runner in the repo.
- `tests/e2e/` holds Playwright specs but `.github/workflows/deploy.yml` never invokes them,
  so e2e is local-only and cannot serve as a CI gate.
- `tests/test_assertion_strength.py` scopes its population to *request-cycle* tests — ones
  issuing a call through the Django test client. Neither test added here does, so both are
  out of population and need no `WAIVER_INVENTORY` entry.

### Key Discoveries:

- Django default is the banned value — `.venv/Lib/site-packages/django/conf/global_settings.py:663`
- `SecurityMiddleware` is active and first — `velo_log/settings.py:112`
- `SECURE_REFERRER_POLICY` is absent from `velo_log/settings.py` entirely (grep returns nothing)
- Leaflet 1.9.4 `TileLayer` default is `referrerPolicy:!1`, and the option **is** honored when
  set to a string — `gpx/static/gpx/vendor/leaflet/leaflet.js`
- Leaflet [PR #9897](https://github.com/Leaflet/Leaflet/pull/9897) changed that default to
  `strict-origin-when-cross-origin`, but only for releases after May 2026 — 1.9.4 (2023) is on
  the "pass it yourself" branch
- The settings probe helper already exists and is documented — `tests/test_settings_security.py:26-31`
- `lessons.md` #1 and #11: a test's name and docstring are claims its body must fully honor
- `lessons.md` #5: update `AGENTS.md` in the same slice that invalidates it

## Desired End State

The production response carries `referrer-policy: strict-origin-when-cross-origin`; the trip
detail map renders real OpenStreetMap tiles rather than block placeholders; the tile layer
carries its own `referrerPolicy` so the map keeps working independently of the global header;
and the suite fails if either half is removed.

Verified by: `curl -I` against the deploy showing the new header, a trip detail page in a real
browser showing map imagery, and `uv run pytest --cov` passing with the two new assertions.

## What We're NOT Doing

- **Not changing tile provider.** Staying on `tile.openstreetmap.org`. A personal-scale diary
  is within what OSM's donated infrastructure permits once compliant; moving to Thunderforest /
  MapTiler / Carto is an API-key, secrets-management and cost decision and belongs in its own
  change.
- **Not upgrading Leaflet.** 1.9.4 supports the option; upgrading to pick up PR #9897's new
  default would change the vendored asset and its `SHA256SUMS` for no behavioral gain here.
- **Not moving the tile URL into `gpx/map_config.py`.** Server-rendering the tile layer config
  the way `icons` and `segments` already are would make it testable in Python rather than by
  source pin, but that is a refactor of the map config contract, not a fix for this block.
- **Not adding a Playwright e2e check.** E2E is not wired into CI, so cover added there would
  look stronger than it is.
- **Not adding a `Content-Security-Policy`.** Out of scope; this change touches one header.
- **Not changing `SECURE_HSTS_SECONDS` or any other production security setting.**

## Implementation Approach

Two one-line production edits, each carrying a comment explaining why a non-default value is
deliberate — this codebase's settings and map JS are both heavily commented with rationale, and
a bare `SECURE_REFERRER_POLICY` line reads as someone weakening a security default for no
reason. The setting goes at **module level**, not inside the existing `if not DEBUG:` block:
the tile-fetching behavior is identical in development, and a dev-only difference here would
mean the failure can only ever be observed in production, which is exactly how it shipped.

The two guard tests then pin each half, and Phase 3 confirms against reality rather than
assuming the header change was sufficient.

## Critical Implementation Details

**The settings probe must not leak across DEBUG modes.** `tests/test_settings_security.py`
documents in its module docstring why it uses `spec_from_file_location` into a throwaway module
rather than `importlib.reload` — reloading re-executes into the existing namespace without
clearing it, so settings from the `if not DEBUG:` branch survive into a later DEBUG=True load.
Any new DEBUG=True assertion must go through the same `_load_settings()` helper for that reason,
not through `django.conf.settings` or a reload.

---

## Phase 1: Send a compliant Referer

### Overview

Make both the global response header and the tile layer itself send a `Referer` that OSM
accepts.

### Changes Required:

#### 1. Global response header

**File**: `velo_log/settings.py`

**Intent**: Override Django's `same-origin` default, which OSM names as non-compliant and which
is the reason every tile request arrives unidentified. Place it at module level near the other
security-relevant settings — not in the `if not DEBUG:` block — so development and production
behave identically. Carry a comment naming OSM's requirement, so the next reader does not
"tighten" it back to the Django default as a security improvement.

**Contract**: New module-level assignment `SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"`.
This is read by `SecurityMiddleware.__init__` and emitted as the `Referrer-Policy` response
header on every response. The value must remain one of OSM's five compliant values.

#### 2. Leaflet tile layer

**File**: `gpx/static/gpx/map.js`

**Intent**: Set the tile layer's own `referrerPolicy` so tile requests send a `Referer`
regardless of what the page's global header later becomes. This is what OSM Operations
recommends directly and what keeps the map working if the global policy is ever tightened for
privacy reasons. Extend the existing header comment block (which already explains the 1.9.4 API
surface and why attribution is passed explicitly) to cover why this option is passed too.

**Contract**: Add `referrerPolicy: "strict-origin-when-cross-origin"` to the options object of
the `L.tileLayer(...)` call at `gpx/static/gpx/map.js:71`. Leaflet 1.9.4 applies it to each tile
`<img>` only when the value is a string; its default is `false`.

### Success Criteria:

#### Automated Verification:

- Lint, format, import order and strict typing pass: `/python-quality-gates`
- Django system check passes: `uv run python manage.py check`
- No model drift introduced: `uv run python manage.py makemigrations --check --dry-run`
- Static manifest still builds and `gpx/map.js` resolves: `uv run python manage.py collectstatic --noinput`
- Existing suite stays green: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`

#### Manual Verification:

- A local `runserver` trip detail page renders OSM tiles, not block placeholders
- Browser devtools shows the tile request carrying a `Referer` header
- Browser devtools shows the document response carrying `referrer-policy: strict-origin-when-cross-origin`

**Implementation Note**: After completing this phase and all automated verification passes,
pause for manual confirmation before proceeding.

---

## Phase 2: Pin both halves against regression

### Overview

Make the suite fail if either the header or the tile-layer option is removed. Without this, the
map.js half can be deleted in a refactor with every gate green — the silent-regression shape
this repo's bite-proof harness exists to prevent.

### Changes Required:

#### 1. Settings assertion, both DEBUG modes

**File**: `tests/test_settings_security.py`

**Intent**: Assert `SECURE_REFERRER_POLICY` is a value OSM accepts. Because the setting is
module-level rather than production-only, prove it in **both** DEBUG modes — asserting only the
`DEBUG=False` load would leave a plan-violating move (dropping it into `if not DEBUG:`) passing.
The existing test function is named and documented for the production block specifically, so a
module-level setting needs its own function rather than an extra line in that one; per
`lessons.md` #11, widening that test's body past what its name claims is the failure mode.

**Contract**: New test function exercising `_load_settings()` under both `DEBUG=True` and
`DEBUG=False`, asserting `settings.SECURE_REFERRER_POLICY` is in OSM's compliant set — and
specifically is not `same-origin` or `no-referrer`. Must reuse the existing `_load_settings()`
helper (see Critical Implementation Details). The module docstring gains a sentence noting the
file now covers a module-level setting as well as the `if not DEBUG:` block.

#### 2. Tile-layer source pin

**File**: `tests/gpx/test_map_asset.py` (new)

**Intent**: Prove the shipped `map.js` passes `referrerPolicy` on its tile layer. With no JS
test runner in the repo, reading the asset and asserting on its source is the only cheap guard
available — and its docstring must say exactly that, claiming a source-text pin and not a
behavioral proof, per `lessons.md` #11.

**Contract**: New test module under `tests/gpx/`. Reads `gpx/static/gpx/map.js` from disk and
asserts the `referrerPolicy` option is present with a value in OSM's compliant set, and that
the tile URL it guards is still `tile.openstreetmap.org` — a pin on the option alone would go
vacuous if the provider ever changed. Issues no test-client call, so it is out of
`tests/test_assertion_strength.py`'s request-cycle population and needs no waiver.

### Success Criteria:

#### Automated Verification:

- Both new tests pass: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest --cov`
- Assertion-strength audit still passes with no new waiver entry (runs inside `pytest --cov`)
- Bite-proof harness still passes: `SECRET_KEY=ci-check-only-not-a-real-secret DEBUG=False ALLOWED_HOSTS= uv run pytest -m bite_proof`
- Quality gates pass: `/python-quality-gates`

#### Manual Verification:

- Temporarily reverting the `settings.py` line turns the settings test red, for the stated reason
- Temporarily reverting the `map.js` option turns the source pin red, for the stated reason
- Each new test's docstring claims exactly what its body asserts — no overclaim

**Implementation Note**: Pause for manual confirmation before proceeding.

---

## Phase 3: Verify against production and escalate if it doesn't clear

### Overview

Confirm the fix on the real deploy. The observed block used OSM's *general* "not following the
tile usage policy" wording rather than the self-healing "Referer is required" variant, so
clearing is a genuine open outcome rather than a formality.

### Changes Required:

#### 1. Post-deploy verification

**File**: none — operational

**Intent**: Confirm the header reaches production and that tiles actually render, rather than
inferring it from the code change.

**Contract**: `curl -sS -I https://velolog-production.up.railway.app/healthz/` reports
`referrer-policy: strict-origin-when-cross-origin`; a trip detail page loaded in a real browser
shows map imagery; devtools shows the tile request carrying `Referer: https://velolog-production.up.railway.app/`
and a `200` rather than a `403`.

#### 2. Escalation path, only if tiles stay blocked

**File**: `context/changes/osm-tile-referrer-policy/change.md`

**Intent**: If tiles remain blocked once a compliant `Referer` is demonstrably being sent, the
referer was not the only cause and the remaining candidates are in OSM's policy: cache-defeating
request headers, missing local caching, or volume. Record the outcome and the headers observed
so the follow-up has evidence rather than starting over.

**Contract**: Append an outcome note to the `## Notes` section recording the observed request and
response headers and the exact block text. The documented escalation is emailing
`operations@osmfoundation.org` with those headers, as directed in the Leaflet issue thread. Opening
a follow-up change is a `/10x-new` decision, not part of this one.

### Success Criteria:

#### Automated Verification:

- Deploy pipeline green end to end, including the `gates` job: check the GitHub Actions run for the merge commit
- Health probe still returns 200: `curl -sS https://velolog-production.up.railway.app/healthz/`

#### Manual Verification:

- Trip detail page on the production deploy renders OSM tiles
- Tile requests in devtools show a `Referer` header and HTTP 200
- If still blocked: exact block text and full request/response headers captured in `change.md`, and the OSM Operations contact path followed

---

## Testing Strategy

### Unit Tests:

- `SECURE_REFERRER_POLICY` is one of OSM's five compliant values, asserted under both `DEBUG=True`
  and `DEBUG=False` through the existing `_load_settings()` probe
- Explicit negative assertion that the value is neither `same-origin` nor `no-referrer` — the two
  values OSM names as blocking, and the one Django would silently restore if the line were deleted
- `gpx/static/gpx/map.js` passes a compliant `referrerPolicy` on its tile layer, and still points
  at `tile.openstreetmap.org`

### Integration Tests:

None. The behavior under test is a response header and a static asset's contents; there is no
integration seam between them that a test could exercise without a real browser, and e2e is not
in CI.

### Manual Testing Steps:

1. `uv run python manage.py runserver`, open a trip with an uploaded GPX stage
2. Devtools → Network → confirm the document response carries `referrer-policy: strict-origin-when-cross-origin`
3. Devtools → Network → pick a `tile.openstreetmap.org` request, confirm it carries a `Referer` and returns 200
4. Confirm tiles render as map imagery, not grey block placeholders
5. Revert each production edit in turn and confirm the matching test goes red
6. After deploy, repeat steps 2-4 against `https://velolog-production.up.railway.app`

## Performance Considerations

None. One additional response header of ~40 bytes, and one attribute on each tile `<img>`.
Tile caching behavior is unchanged, which matters because cache-defeating requests are
themselves a policy violation.

## Migration Notes

No data migration. The change is a response-header value and a static asset edit. Rollback is
reverting both commits; the only consequence of rollback is that tiles go back to being blocked.

Note that `map.js` is a project-owned asset, not a vendored one, so neither the Leaflet nor the
Bootstrap `SHA256SUMS` integrity check in the `gates` job is affected. `collectstatic` will emit
a new hashed filename for `map.js`, which is routine.

## References

- Change identity and triage evidence: `context/changes/osm-tile-referrer-policy/change.md`
- Existing settings probe pattern: `tests/test_settings_security.py:26-31`
- Tile layer under change: `gpx/static/gpx/map.js:71-73`
- Django default: `.venv/Lib/site-packages/django/conf/global_settings.py:663`
- OSM tile usage policy: https://operations.osmfoundation.org/policies/tiles/
- OSM wiki, Referer (compliant value list): https://wiki.openstreetmap.org/wiki/Referer
- Leaflet PR #9897 (TileLayer referrerPolicy default): https://github.com/Leaflet/Leaflet/pull/9897

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Send a compliant Referer

#### Automated

- [x] 1.1 Lint, format, import order and strict typing pass — eefe1da
- [x] 1.2 Django system check passes — eefe1da
- [x] 1.3 No model drift introduced — eefe1da
- [x] 1.4 Static manifest still builds and `gpx/map.js` resolves — eefe1da
- [x] 1.5 Existing suite stays green — eefe1da

#### Manual

- [x] 1.6 Local trip detail page renders OSM tiles, not block placeholders — eefe1da
- [x] 1.7 Tile request carries a `Referer` header — eefe1da
- [x] 1.8 Document response carries `referrer-policy: strict-origin-when-cross-origin` — eefe1da

### Phase 2: Pin both halves against regression

#### Automated

- [x] 2.1 Both new tests pass — 8f53919
- [x] 2.2 Assertion-strength audit passes with no new waiver entry — 8f53919
- [x] 2.3 Bite-proof harness still passes — 8f53919
- [x] 2.4 Quality gates pass — 8f53919

#### Manual

- [x] 2.5 Reverting the settings line turns the settings test red, for the stated reason — 8f53919
- [x] 2.6 Reverting the map.js option turns the source pin red, for the stated reason — 8f53919
- [x] 2.7 Each new test's docstring claims exactly what its body asserts — 8f53919

### Phase 3: Verify against production and escalate if it doesn't clear

#### Automated

- [ ] 3.1 Deploy pipeline green end to end, including the `gates` job
- [ ] 3.2 Health probe still returns 200

#### Manual

- [ ] 3.3 Trip detail page on the production deploy renders OSM tiles
- [ ] 3.4 Tile requests show a `Referer` header and HTTP 200
- [ ] 3.5 If still blocked: block text and headers captured in `change.md`, OSM Operations contacted
