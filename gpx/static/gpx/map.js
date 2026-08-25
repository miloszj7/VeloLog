/* Draws an uploaded GPX route as a map that behaves like a static image.
 *
 * Everything this file needs arrives in one JSON blob rendered by
 * `trips/trip_detail.html` via `{{ ...|json_script }}`. Nothing is interpolated into
 * JavaScript source and there is no inline script on the page: the coordinates are
 * untrusted user data, and `json_script` is what keeps them data rather than code.
 *
 * The icon URLs arrive in that blob for a second reason. A static file cannot call
 * `{% static %}`, and Leaflet's default icon builds `marker-icon-2x.png` and
 * `marker-shadow.png` URLs at runtime — paths the hashed staticfiles manifest never
 * rewrites, so they 404 in production while passing every check locally. Passing them
 * explicitly from the server, where the manifest is authoritative, is what avoids that.
 *
 * Written against Leaflet 1.9.4 (the vendored version). The interaction options and
 * `fitBounds`' `padding` are all documented 1.x API; 1.9.4 does *not* add OpenStreetMap
 * attribution on its own, which is why it is passed explicitly below.
 */
(function () {
    "use strict";

    var configElement = document.getElementById("map-config");
    var mapElement = document.getElementById("map");
    if (!configElement || !mapElement) {
        return;
    }

    var config = JSON.parse(configElement.textContent);

    // The deepest zoom OpenStreetMap serves tiles for. It has to reach `L.map` as well as
    // the tile layer below: a layer registers its own zoom limit from `GridLayer.onAdd`,
    // which Leaflet defers to the `load` event while the map still has no view — and the
    // only call that gives it one is `fitBounds` at the end of this file. The map's
    // `getMaxZoom()` is therefore still `Infinity` at that point, so a track too small to
    // fill the frame gets fitted past the last zoom with tiles (route over blank tiles),
    // and a single-point track — zero-size bounds, which `parse_gpx` accepts — fits to
    // `Infinity`, which makes the projection non-finite and draws nothing at all.
    var MAX_ZOOM = 19;

    var map = L.map("map", {
        maxZoom: MAX_ZOOM,
        // FR-015 (an interactive map) is parked for v2. Until then the map is a picture
        // of the route: every interaction handler is off, and the zoom control is hidden
        // rather than left visible and inert.
        dragging: false,
        scrollWheelZoom: false,
        touchZoom: false,
        doubleClickZoom: false,
        keyboard: false,
        boxZoom: false,
        tapHold: false,
        zoomControl: false
    });

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: MAX_ZOOM,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    L.polyline(config.points, {color: "#ff7800", weight: 5, opacity: 0.85}).addTo(map);

    var icon = L.icon({
        iconUrl: config.icons.iconUrl,
        iconRetinaUrl: config.icons.iconRetinaUrl,
        shadowUrl: config.icons.shadowUrl,
        // The upstream Leaflet defaults, restated because supplying `iconUrl` opts out
        // of `L.Icon.Default` entirely — omit them and the marker is anchored by its
        // top-left corner, so it points a few dozen metres off the route.
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        shadowSize: [41, 41],
        popupAnchor: [1, -34]
    });
    L.marker(config.points[0], {icon: icon, title: "Start"}).addTo(map);
    L.marker(config.points[config.points.length - 1], {icon: icon, title: "Finish"}).addTo(map);

    // Bounds come from the server rather than `polyline.getBounds()`. They are derived
    // from the same stored points at upload time, so the box provably contains the line
    // being drawn, and the client stays off an API surface the 1.x docs did not confirm.
    // The padding keeps the route off the edge of the frame.
    map.fitBounds(config.bounds, {padding: [20, 20]});
})();
