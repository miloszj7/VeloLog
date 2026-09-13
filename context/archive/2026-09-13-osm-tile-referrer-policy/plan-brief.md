# Restore OSM tile loading by sending a compliant Referer — Plan Brief

> Full plan: `context/changes/osm-tile-referrer-policy/plan.md`

## What & Why

The trip detail map on the Railway production deploy draws its route but every OpenStreetMap
basemap tile comes back as a "403 / access blocked" placeholder. Django's `SecurityMiddleware`
emits `Referrer-Policy: same-origin` by default, which stops the browser sending any `Referer`
on cross-origin requests — and OSM's tile usage policy names that exact value as
non-compliant, because for a web app the `Referer` is the only thing identifying who is asking.

## Starting Point

`SECURE_REFERRER_POLICY` is absent from `velo_log/settings.py`, so Django's `same-origin`
default applies and is live on the deploy (confirmed by `curl -I`). The map code itself is
already correct: `gpx/static/gpx/map.js:71-73` uses the right tile URL and passes the required
attribution. The vendored Leaflet is 1.9.4, whose `TileLayer` supports a `referrerPolicy`
option but leaves it unset — so tiles inherit the page's global header. `map.js` contents are
asserted nowhere in the suite; only its path is checked.

## Desired End State

Production responses carry `referrer-policy: strict-origin-when-cross-origin`, the trip detail
map shows real map imagery instead of block placeholders, and the tile layer carries its own
`referrerPolicy` so the map keeps working independently of the global header. Removing either
half turns the suite red.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
|---|---|---|
| Policy value | `strict-origin-when-cross-origin`, set globally | Modern browser default and on OSM's compliant list; the only cross-origin request the app makes is the tile fetch itself, so the bare origin is the sole new disclosure — to a party already receiving the ride's tile coordinates. |
| Where to set it | Module level, not inside `if not DEBUG:` | Tile behavior is identical in development; a prod-only difference is exactly how this shipped unnoticed. |
| Layers to fix | Both `settings.py` and `map.js` | The setting fixes it site-wide now; the layer option survives a later privacy-motivated tightening or a Leaflet upgrade. |
| Test depth | Settings assertion in both DEBUG modes + a `map.js` source pin | With no JS test runner, a source pin is the only cheap guard; e2e exists but is not wired into CI, so cover there would look stronger than it is. |
| Tile provider | Out of scope — stay on `tile.openstreetmap.org` | Personal-scale use is within what OSM permits once compliant; a commercial provider is an API-key and cost decision of its own. |
| Verification | Its own phase, not Phase 1 manual criteria | The observed block used OSM's general wording, not the self-healing "Referer is required" variant, so clearing it is a real open outcome. |

## Scope

**In scope:**
- `SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"` at module level in `velo_log/settings.py`
- `referrerPolicy` on the `L.tileLayer` options in `gpx/static/gpx/map.js`
- A settings assertion covering both DEBUG modes in `tests/test_settings_security.py`
- A new source-pin test under `tests/gpx/`
- Post-deploy verification against production, with an escalation path if it doesn't clear

**Out of scope:**
- Changing tile provider (Thunderforest / MapTiler / Carto)
- Upgrading Leaflet to pick up its new default
- Moving the tile config into `gpx/map_config.py` to make it Python-testable
- Adding a Playwright e2e check, or a `Content-Security-Policy`
- Any other production security setting

## Architecture / Approach

Two one-line production edits, each carrying a comment explaining why a non-default security
value is deliberate — otherwise the next reader reads it as someone weakening a Django default
and tightens it back. Belt-and-braces by design: the global header fixes every tile request
today, the layer option makes the map independent of that header tomorrow. Then one guard test
per half, then confirmation against the real deploy rather than inference from the diff.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Send a compliant Referer | The two production edits; tiles load locally | Setting drifts into the `if not DEBUG:` block, making the fix unobservable in dev |
| 2. Pin both halves | Two guard tests; neither half can be silently dropped | A source-pin test that overclaims — it proves a string is present, not that Leaflet honors it |
| 3. Verify and escalate | Confirmed production behavior, or captured evidence | The general block message admits a second cause; the fix may not clear it alone |

**Prerequisites:** Merge access to `master` and a Railway deploy; a trip with an uploaded GPX stage to view.
**Estimated effort:** ~1 session across 3 phases; Phase 3 gated on deploy turnaround.

## Open Risks & Assumptions

- **The block message is the general "not following the tile usage policy", not "Referer is
  required".** OSM documents only the latter as self-healing. The reading that supports this
  plan — a no-`Referer` browser request gets classified as an app, then judged on a generic
  browser `User-Agent`, drawing the general block — is consistent but unproven. Phase 3 exists
  because of this, and the referer violation is real and worth fixing regardless.
- The `map.js` pin asserts source text, not behavior. It catches deletion, not a Leaflet
  upgrade that stops honoring the option.
- Assumes no unblocking delay on OSM's side once compliant traffic resumes.

## Success Criteria (Summary)

- Opening a trip on the production deploy shows a real map, not grey "access blocked" tiles
- Tile requests carry `Referer: https://velolog-production.up.railway.app/` and return 200
- Deleting either half of the fix turns the suite red, for a reason the test names
