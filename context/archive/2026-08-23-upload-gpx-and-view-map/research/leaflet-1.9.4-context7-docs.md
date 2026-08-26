# Leaflet 1.x (1.9.4) — Context7 docs (S-03 `upload-gpx-and-view-map`)

- **Date:** 2026-08-24
- **Method:** External research (Context7 MCP), library ID **`/websites/leafletjs`** — the
  source that `../research.md` §1 verified returns the **1.x** API. Three scoped queries
  plus one earlier verification query.
- **Question:** Fetch the *stable* Leaflet API needed to implement S-03, replacing the
  2.0-alpha capture in [`leaflet-context7-docs.md`](./leaflet-context7-docs.md).
- **Supersedes for implementation purposes:** `leaflet-context7-docs.md`, which was fetched
  from `/leaflet/leaflet` (the GitHub repo's 2.0 development branch) and documents
  ESM-only constructors that do not exist in 1.9.4.

## Why this file exists

`leaflet@latest` on npm is **1.9.4**; Leaflet 2.0 has been alpha since 2025-05 with no
release date. Context7 indexes Leaflet by **source, not version**, and offers no
`Versions:` list to pin, so the source ID is the only lever:

| Library ID | Snippets | Returns |
|---|---|---|
| `/leaflet/leaflet` | 933 | GitHub repo, default branch = 2.0 dev → **2.0-alpha ESM**. Used by `leaflet-context7-docs.md`. |
| **`/websites/leafletjs`** | 451 | Docs site, crawled as **1.x** ✅ — the source for this file |
| `/websites/leafletjs_reference-2_0_0` | 509 | Explicitly the 2.0.0 reference |

**Version tell-tale, to re-apply on every future fetch:** `L.map(...)` / `L.polyline(...)`
means 1.x; `new LeafletMap(...)` / `import {Polyline} from 'leaflet'` means 2.0. Every
snippet below passes that test.

> `/websites/leafletjs` is a **crawl snapshot** of `leafletjs.com`, and that site's own
> quick-start page already carries the 2.0 import-map instructions. This ID can flip to 2.0
> syntax on a re-crawl. Re-run the tell-tale test rather than trusting the ID.

## Captured from Context7

### Map init + OSM tile layer

```javascript
var map = L.map('map').fitWorld();

L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
}).addTo(map);
```

Source: `leafletjs.com/examples/mobile`.

Note the `attribution` option — OSM tile usage requires attribution, and this is where it
belongs. (Leaflet 2.0 adds automatic OSM attribution; **1.9.4 does not**, so it must be
passed explicitly.)

### Markers and a polyline from a coordinate array

```javascript
L.marker([51.5, -0.09]).addTo(map);

var travel = L.polyline([sol, deneb]).addTo(map);
```

Sources: `leafletjs.com/examples/quick-start`,
`leafletjs.com/examples/crs-simple/crs-simple.html`.

`L.polyline` accepts an array of `[lat, lng]` pairs directly — which is exactly the shape
`gpxpy` produces from `gpx.tracks[].segments[].points[]` (see
[`gpxpy-context7-docs.md`](./gpxpy-context7-docs.md)). No conversion layer is needed
between the two.

### Fitting the view to a route

```javascript
map.fitBounds(bounds);
```

```javascript
map.fitBounds(geojson.getBounds());
```

Sources: `leafletjs.com/examples/crs-simple/crs-simple.html`,
`leafletjs.com/examples/map-panes`.

The second form — passing a layer's own `getBounds()` — is the pattern to use with the
polyline layer, avoiding a separate bounds computation.

### Path styling

```javascript
var myStyle = {
    "color": "#ff7800",
    "weight": 5,
    "opacity": 0.65
};
```

Source: `leafletjs.com/examples/geojson.html`. Shown there as a GeoJSON `style` object, but
`color` / `weight` / `opacity` are `Path` options and apply to `L.polyline` too.

### Custom marker icons

```javascript
var greenIcon = L.icon({
    iconUrl: 'leaf-green.png',
    shadowUrl: 'leaf-shadow.png',

    iconSize:     [38, 95], // size of the icon
    shadowSize:   [50, 64], // size of the shadow
    iconAnchor:   [22, 94], // point of the icon which will correspond to marker's location
    shadowAnchor: [4, 62],  // the same for the shadow
    popupAnchor:  [-3, -76] // point from which the popup should open relative to the iconAnchor
});
```

A reusable class form is also documented:

```javascript
var LeafIcon = L.Icon.extend({
    options: {
        shadowUrl: 'leaf-shadow.png',
        iconSize:     [38, 95],
        shadowSize:   [50, 64],
        iconAnchor:   [22, 94],
        shadowAnchor: [4, 62],
        popupAnchor:  [-3, -76]
    }
});
```

Source: `leafletjs.com/examples/custom-icons.html`.

Relevant to the deploy risk in `../research.md` §6: supplying explicit `iconUrl`s through
`{% static %}` sidesteps Leaflet's built-in default-icon path resolution entirely, which is
one way to avoid the runtime 404s on `marker-icon-2x.png` / `marker-shadow.png` that the
staticfiles manifest never sees.

### Self-hosting the library files

```html
<link rel="stylesheet" href="/path/to/leaflet.css" />
<script src="/path/to/leaflet.js"></script>
```

Source: `leafletjs.com/download.html`. Two plain tags, no build step and no import map —
compatible with this project's plain-Django-templates frontend. In this repo these become
`{% static %}` references (the first in the codebase's history; see `../research.md` §6 for
the `collectstatic` boot-failure risk and the required sibling `images/` directory).

## NOT covered by these Context7 queries — verify at implement time

Recording the gaps explicitly, because the whole reason this file exists is that an
unverified capture was previously taken as a contract.

| Needed for S-03 | Status |
|---|---|
| `L.map` interaction options to make the map behave as a static image — `dragging`, `scrollWheelZoom`, `touchZoom`, `doubleClickZoom`, `keyboard`, `zoomControl` | **Not returned.** A targeted query came back with only `zoomSnap`/`zoomDelta`/`wheelPxPerZoomLevel` and a prose list of interaction features. The site's *tutorials* don't cover disabling them; these are `Map` **reference** options. Verify against `leafletjs.com/reference.html` (1.9.4) before relying on names. |
| `fitBounds` options — `padding`, `paddingTopLeft`, `paddingBottomRight`, `maxZoom` | **Not returned** by the 1.x source. (They *are* documented in the 2.0 capture at `leaflet-context7-docs.md:47-51`, and the option names are believed unchanged between 1.9.4 and 2.0 — but that is **inferred, not verified for 1.9.4**.) |
| `polyline.getBounds()` | **Not returned directly.** Only `geojson.getBounds()` was shown. `getBounds()` is a `Polyline` method in 1.x, but confirm before use. |
| `L.Icon.Default.imagePath` — the built-in default-icon path override | **Not returned.** Matters only if default markers are used instead of explicit `L.icon` URLs. |
| Behaviour when `fitBounds` receives invalid/empty bounds (the no-GPX-points empty-state branch) | **Not returned** for 1.x. The 2.0 source documents a throw (`leaflet-context7-docs.md:49`). Guard the empty case in application code regardless — per the PRD's no-silent-failure NFR, this must be a deliberate branch, not a caught exception. |

Two of these (static-map options, `fitBounds` padding) are load-bearing for the slice, so
the plan should either fetch `leafletjs.com/reference.html` directly or verify them against
the vendored `leaflet.js` at implement time.

## Follow-up for `/10x-plan`

- Pin **`leaflet@1.9.4`** explicitly, vendored under `trips/static/trips/vendor/leaflet/`
  (or a project-level `static/` with `STATICFILES_DIRS` added), shipping the complete
  `images/` directory — `leaflet.css` references `images/layers.png`,
  `images/layers-2x.png`, `images/marker-icon.png`, and an unresolvable reference **fails
  `collectstatic`, which fails the container boot** (`../research.md` §6).
- Pass OSM `attribution` explicitly — 1.9.4 does not add it automatically.
- Resolve the two load-bearing gaps above before writing the template.
- Use `L.polyline` + `L.marker` + `map.fitBounds(polyline.getBounds())` with the point array
  delivered via `{{ ...|json_script }}` — no GPX plugin, no d3 (`../research.md` §2, §3).
