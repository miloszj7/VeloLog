---
change_id: osm-tile-referrer-policy
title: Restore OSM tile loading by sending a Referer on cross-origin tile requests
status: planned
created: 2026-09-13
updated: 2026-09-13
archived_at: null
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

### References

- OSM tile usage policy — https://operations.osmfoundation.org/policies/tiles/
- OSM wiki, Referer — https://wiki.openstreetmap.org/wiki/Referer
- OSM wiki, Blocked Tiles — https://wiki.openstreetmap.org/wiki/Blocked_Tiles
- Leaflet PR #9897 (TileLayer referrerPolicy default) — https://github.com/Leaflet/Leaflet/pull/9897
- Leaflet PR #9883 (OSM-specific referrerPolicy, the alternative) — https://github.com/Leaflet/Leaflet/pull/9883
- Django `SECURE_REFERRER_POLICY` — https://docs.djangoproject.com/en/6.0/ref/settings/#std-setting-SECURE_REFERRER_POLICY
