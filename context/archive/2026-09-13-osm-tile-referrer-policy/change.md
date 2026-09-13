---
change_id: osm-tile-referrer-policy
title: Restore OSM tile loading by sending a Referer on cross-origin tile requests
status: archived
created: 2026-09-13
updated: 2026-09-13
archived_at: 2026-09-13T14:32:47Z
---

## Notes

Fix the OSM tile 403 block caused by Django's `same-origin` Referrer-Policy stripping the
Referer header on cross-origin tile requests; set `SECURE_REFERRER_POLICY` to
`strict-origin-when-cross-origin` and pass `referrerPolicy` on the Leaflet tileLayer.

### Symptom

On the Railway production deploy (`velolog-production.up.railway.app`), the trip detail map
renders its route but every OSM basemap tile comes back as a "403 / access blocked / app is
not following the tile usage policy — osm.wiki/Blocked" placeholder image.

### Evidence gathered during triage (2026-09-13)

- Live production response carries `referrer-policy: same-origin` (confirmed via
  `curl -I https://velolog-production.up.railway.app/healthz/`). It comes from
  `SecurityMiddleware` (`velo_log/settings.py:112`) using Django's default
  `SECURE_REFERRER_POLICY = "same-origin"`; the setting is never overridden in
  `velo_log/settings.py`.
- `same-origin` means the browser sends **no** `Referer` on cross-origin requests, so every
  tile request to `tile.openstreetmap.org` arrives unidentified.
- The OSM wiki's Referer page gives an explicit deny list: the policy-compliant values are
  `no-referrer-when-downgrade`, `origin`, `origin-when-cross-origin`, `strict-origin`,
  `strict-origin-when-cross-origin` — and it must **not** be `no-referrer` or `same-origin`.
- A member of the OSM Operations team names Django directly in the Leaflet discussion:
  "This is because django, by default, sets the `referrer-policy` header to `same-origin`
  unless configured otherwise."
- The vendored Leaflet is **1.9.4** (`gpx/static/gpx/vendor/leaflet/leaflet.js`), whose
  `TileLayer` defaults include `referrerPolicy: false` — i.e. it sets nothing on the tile
  `<img>` and inherits the page's global header. Leaflet PR #9897 changed that default to
  `strict-origin-when-cross-origin`, but only for releases after May 2026, so 1.9.4 is on
  the "older version — pass the option yourself" branch. The option *is* supported in 1.9.4.
- The tile layer URL and attribution in `gpx/static/gpx/map.js:71-73` are already
  policy-compliant; nothing about the map code itself is wrong.

### Open question to resolve during planning

OSM distinguishes two block messages: "Referer is required" (the referer-specific block,
which self-heals once the header is sent) versus the more general "not following the tile
usage policy". The symptom was reported using the general wording. Confirm the exact text on
the returned tile — if it is the general message, the referer violation is still real and
must be fixed, but there may be a second cause to chase.

### Outcome — verified on production (2026-09-13)

Phase 3 cleared. The fix shipped in `4cb0240` and the deploy for it was green end to end
(`gates` and `deploy` both success).

- The live response carries `referrer-policy: strict-origin-when-cross-origin`
  (`curl -I https://velolog-production.up.railway.app/healthz/`), replacing the `same-origin`
  recorded under *Evidence gathered during triage* above.
- The served `map.js` carries `referrerPolicy: "strict-origin-when-cross-origin"` on its
  `L.tileLayer` call, confirmed by fetching the asset from the deploy rather than inferring it
  from the repo.
- A trip detail page on production renders real OSM basemap imagery; tile requests return 200
  and carry `Referer: https://velolog-production.up.railway.app/` — the bare origin, no path and
  no trip pk, which is the disclosure `strict-origin-when-cross-origin` was chosen to bound.

**This resolves the open question above.** The block was reported with OSM's general "not
following the tile usage policy" wording rather than the self-healing "Referer is required"
variant, which left open whether a second cause was in play. There was not one: sending a
compliant `Referer` was sufficient, and the general wording is explained by the plan's reading —
a browser request arriving with no `Referer` is classified as an unidentified *application* and
judged on its generic `User-Agent`. No escalation to `operations@osmfoundation.org` was needed.

One thing that is **not** evidence, recorded so it is not re-run as if it were: fetching a tile
from `tile.openstreetmap.org` via `curl` with and without a `Referer` returns 200 either way.
OSM's block is applied by traffic pattern, not as a per-request header check, so it cannot be
probed from the command line — which is why this phase was written as a real-browser step.

### References

- OSM tile usage policy — https://operations.osmfoundation.org/policies/tiles/
- OSM wiki, Referer — https://wiki.openstreetmap.org/wiki/Referer
- OSM wiki, Blocked Tiles — https://wiki.openstreetmap.org/wiki/Blocked_Tiles
- Leaflet PR #9897 (TileLayer referrerPolicy default) — https://github.com/Leaflet/Leaflet/pull/9897
- Leaflet PR #9883 (OSM-specific referrerPolicy, the alternative) — https://github.com/Leaflet/Leaflet/pull/9883
- Django `SECURE_REFERRER_POLICY` — https://docs.djangoproject.com/en/6.0/ref/settings/#std-setting-SECURE_REFERRER_POLICY
