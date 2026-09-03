/* Draws an uploaded GPX route as an interactive pan/zoom Leaflet map.
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
 * The container ships with a "could not be loaded" paragraph inside it, and this file is
 * the only thing that takes it away — on the success path and nowhere else. That inverts
 * the default: the PRD's one NFR forbids a blank page, and every way this script fails to
 * draw (never loading at all, `L` undefined because Leaflet did not load, stored points it
 * chokes on) is a failure the server cannot see, so the message has to already be in the
 * HTML and be removed rather than added.
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

    // Read before Leaflet touches the container: initialising a map appends panes to
    // `#map` rather than emptying it, so the handle has to be taken while the container
    // is still only the fallback.
    var fallback = mapElement.querySelector(".map-fallback");

    try {
        var config = JSON.parse(configElement.textContent);

        // The deepest zoom OpenStreetMap serves tiles for. It has to reach `L.map` as
        // well as the tile layer below: a layer registers its own zoom limit from
        // `GridLayer.onAdd`, which Leaflet defers to the `load` event while the map still
        // has no view — and the only call that gives it one is `fitBounds` at the end of
        // this block. The map's `getMaxZoom()` is therefore still `Infinity` at that
        // point, so a track too small to fill the frame would be fitted past the last
        // zoom with tiles (route drawn over blank tiles), and a single-point track —
        // zero-size bounds, which `parse_gpx` accepts — to `Infinity`, which makes the
        // projection non-finite and draws nothing at all.
        var MAX_ZOOM = 19;

        var map = L.map("map", {
            maxZoom: MAX_ZOOM,
            // FR-015 (an interactive map) is live: dragging, touch/double-click zoom,
            // keyboard pan/zoom, and the zoom control are all on. `scrollWheelZoom`
            // stays off at init and is enabled by the click-to-enable control below —
            // the standard fix for the trap where scrolling the page over an embedded
            // map hijacks the scroll into a zoom. `boxZoom` and `tapHold` stay off;
            // out of scope per user decision.
            dragging: true,
            scrollWheelZoom: false,
            touchZoom: true,
            doubleClickZoom: true,
            keyboard: true,
            boxZoom: false,
            tapHold: false,
            zoomControl: true
        });

        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: MAX_ZOOM,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);

        // One polyline per stage segment, coloured server-side (`gpx/constants.py`'s
        // `STAGE_COLORS`) — never hardcoded here, which is also where the old literal
        // `#ff7800` (drifted from the design system's `#f97316` accent) is retired.
        config.segments.forEach(function (segment) {
            L.polyline(segment.points, {color: segment.color, weight: 5, opacity: 0.85}).addTo(map);
        });

        // One `L.icon` per marker kind ("start" / "finish" / "break"), built from the
        // server-resolved staticfiles URLs in `config.icons`. The upstream Leaflet
        // defaults below are restated because supplying `iconUrl` opts out of
        // `L.Icon.Default` entirely — omit them and the marker is anchored by its
        // top-left corner, so it points a few dozen metres off the route.
        var icons = {};
        Object.keys(config.icons).forEach(function (kind) {
            var iconConfig = config.icons[kind];
            icons[kind] = L.icon({
                iconUrl: iconConfig.iconUrl,
                iconRetinaUrl: iconConfig.iconRetinaUrl,
                shadowUrl: iconConfig.shadowUrl,
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                shadowSize: [41, 41],
                popupAnchor: [1, -34]
            });
        });
        config.markers.forEach(function (marker) {
            L.marker(marker.point, {icon: icons[marker.kind], title: marker.title}).addTo(map);
        });

        // Bounds come from the server rather than `polyline.getBounds()`. They are derived
        // from the same stored points at upload time, so the box provably contains the
        // line being drawn, and the client stays off an API surface the 1.x docs did not
        // confirm. The padding keeps the route off the edge of the frame.
        map.fitBounds(config.bounds, {padding: [20, 20]});

        // The map is fully drawn and functional at this point, so the fallback comes
        // down here rather than after the decorative hint control below. That keeps
        // fallback removal gated on "core map exists," not on the hint also
        // succeeding — a throw from the hint code would otherwise skip removal and
        // leave a fully rendered live map sitting behind the "could not be loaded"
        // message, contradicting this file's own contract (see header comment).
        if (fallback && fallback.parentNode) {
            fallback.parentNode.removeChild(fallback);
        }

        // Scroll-wheel zoom starts disabled (see the L.map options above); this hint
        // control tells the user how to turn it on, and the first interaction with the
        // map turns it on and removes itself. Leaflet's own controls (including the
        // zoom control enabled above) call L.DomEvent.disableClickPropagation on their
        // DOM element, so clicking them never reaches the map as a "click" event, and
        // Leaflet suppresses the synthetic "click" fired after a drag gesture — so
        // "click" alone would miss both. Binding to dragstart/zoomstart too means
        // panning or using the zoom control also enables scroll zoom, not only a
        // literal click on the map surface.
        var ScrollZoomHint = L.Control.extend({
            options: {position: "topright"},
            onAdd: function () {
                var el = L.DomUtil.create("div", "leaflet-control-scroll-zoom-hint leaflet-bar");
                el.textContent = "Click map to enable scroll zoom";
                return el;
            }
        });
        var scrollZoomHint = new ScrollZoomHint().addTo(map);
        map.once("dragstart zoomstart click", function () {
            map.scrollWheelZoom.enable();
            map.removeControl(scrollZoomHint);
        });
    } catch (error) {
        // Swallowed on purpose. The fallback paragraph is still in the container, and that
        // message is the entire user-visible contract for a failed draw; there is no error
        // reporting in this project to forward to. The console line is for a developer.
        //
        // All-or-nothing, and since the payload went multi-stage that is a whole *tour*
        // rather than one route: a throw in any of the three loops above — a malformed
        // `segment.points`, or an `icons[marker.kind]` miss handing Leaflet `undefined` —
        // lands here before the fallback is removed, so every stage falls back together,
        // not just the bad one. Deliberate: a partially drawn tour with no explanation is
        // worse than one honest sentence, and `gpx/map_config.py` is where a bad stage is
        // meant to be handled (it skips a point-less stage rather than aborting, emits
        // only the three marker kinds it also builds icons for, and derives bounds from
        // non-null columns). If a future payload can carry a stage this file cannot draw,
        // fix it there — or wrap the loop bodies individually — rather than widening what
        // this catch tolerates.
        if (window.console && window.console.error) {
            window.console.error("VeloLog: the route map could not be drawn.", error);
        }
        return;
    }
})();
