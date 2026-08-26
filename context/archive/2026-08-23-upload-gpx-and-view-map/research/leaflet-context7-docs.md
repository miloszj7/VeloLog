# Leaflet / leaflet-gpx — Context7 docs (S-03 `upload-gpx-and-view-map`)

- **Date:** 2026-08-24
- **Method:** External research (Context7 MCP) — live library documentation, per `AGENTS.md` research discipline.
- **Question:** Fetch current Leaflet and `leaflet-gpx` API docs needed to implement S-03 (upload GPX → render route as a static map).
- **Companion doc:** [`map-library-research.md`](./map-library-research.md) (exa.ai web search) already selected **Leaflet + `leaflet-gpx`** as the library choice; this doc captures the actual API surface from Context7.

## Library resolution

| Query | Result |
|---|---|
| "Leaflet" | `/leaflet/leaflet` — 933 snippets, High reputation, benchmark 76.96. Also indexed: `/websites/leafletjs`, `/websites/leafletjs_reference-2_0_0`, `/websites/react-leaflet_js` (not applicable — no React in this stack), `/nuxt-modules/leaflet` (not applicable), `/leaflet/leaflet.markercluster` (not needed for S-03). |
| "leaflet-gpx" (multiple query phrasings) | **No match.** Context7 does not index `mpetazzoni/leaflet-gpx` (or any GPX-specific Leaflet plugin) under any resolution attempted. Only `/javalent/obsidian-leaflet` surfaced as GPX-adjacent, and it's an Obsidian.md plugin — not applicable to a Django web app. |

**Implication:** `leaflet-gpx`'s own API (`L.GPX(url, options).addTo(map)`, `polyline_options`, marker/legend options) is **not verifiable via Context7** — implementation must rely on the library's own README/GitHub source at plan/implement time, not on Context7-sourced docs. The core Leaflet API below (map init, tile layer, polyline, markers, bounds) is fully Context7-verified and is what `leaflet-gpx` itself is built on, so it's the reliable foundation regardless of which GPX-loading approach is used.

## Core Leaflet API (verified via Context7, `/leaflet/leaflet`)

### Map init + tile layer + fit to bounds

```javascript
import {LeafletMap, TileLayer, LatLngBounds, LatLng} from 'leaflet';

const map = new LeafletMap('map');
const osm = new TileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 18});
map.addLayer(osm);

const bounds = new LatLngBounds(new LatLng(32, -126), new LatLng(50, -64));
map.fitBounds(bounds);
```

Source: `debug/map/wms.html`, `debug/map/tile-opacity.html` (github.com/leaflet/leaflet).

### `fitBounds` signature (from `src/map/Map.js`)

```javascript
fitBounds(bounds, options) {
  bounds = new LatLngBounds(bounds);
  if (!bounds.isValid()) {
    throw new Error('Bounds are not valid.');
  }
  const target = this._getBoundsCenterZoom(bounds, options);
  return this.setView(target.center, target.zoom, options);
}
```

- `options.padding` / `paddingTopLeft` / `paddingBottomRight` — `Point` offsets subtracted from the viewport.
- `options.maxZoom` — caps the computed zoom.
- Throws if bounds are invalid — relevant for the empty-state branch (no GPX points → don't call `fitBounds`).

### Route rendering: polyline + start/end markers, fit to route

```javascript
import {TileLayer, LeafletMap, LatLng, LatLngBounds, Marker, Polyline} from 'leaflet';
import route from './route.js';

const osm = new TileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 18});
const map = new LeafletMap('map', {layers: [osm]});

const latlngs = route.map(p => new LatLng(p[0], p[1]));
map.fitBounds(new LatLngBounds(latlngs));

map.addLayer(new Marker(latlngs[0]));
map.addLayer(new Marker(latlngs[latlngs.length - 1]));
map.addLayer(new Polyline(latlngs, {smoothFactor: 1}));
```

Source: `debug/vector/vector-mobile.html`, `debug/vector/vector.html` (github.com/leaflet/leaflet). This is the pattern to fall back on if `leaflet-gpx` proves unverifiable/unsuitable at plan time: parse the GPX server-side (e.g. `gpxpy`) into a plain `[lat, lon]` array, pass it to the template, and render with core `Polyline`/`Marker`/`fitBounds` only — no GPX-specific plugin dependency at all.

### Polyline styling options seen in the docs

```javascript
new Polyline(points, {
  weight: 10,
  opacity: 1,
  smoothFactor: 1,
  color: 'red',
  interactive: true
});
```

Source: `debug/tests/click-on-canvas.html`, `debug/tests/svg-clicks.html`.

### GeoJSON variant (not used for GPX, included for `getBounds()` pattern)

```javascript
const geojson = new GeoJSON(feature).addTo(map);
map.fitBounds(geojson.getBounds());
```

A layer's own `.getBounds()` can be passed directly to `fitBounds` — same pattern applies to whatever GPX-derived layer S-03 ends up using (a `leaflet-gpx` layer exposes `getBounds()` too, per its README, though that specific API is not Context7-verified — see resolution note above).

## Follow-up for `/10x-plan`

- Verify `leaflet-gpx`'s actual API (`L.GPX`, event names like `loaded`, `polyline_options`) directly from its GitHub README/source, since Context7 has no indexed docs for it.
- Decide, at plan time, between the `leaflet-gpx` plugin path and the "parse server-side with `gpxpy`, render with core Leaflet `Polyline`" fallback shown above — the latter has no unverified third-party API surface.
