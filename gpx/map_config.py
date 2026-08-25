"""Assembles what `gpx/static/gpx/map.js` needs to draw a track.

Built here rather than in either view because two views render the trip detail page:
`TripDetailView` on a normal visit, and `GpxUploadView` when it re-renders that page with
a form error. A helper reachable from only one of them would leave the other rendering the
"route could not be displayed" branch over a perfectly healthy track.

It lives in `gpx` rather than `trips` for two reasons: the track and the vendored Leaflet
assets whose URLs it resolves are both this app's, and `trips` already imports from `gpx`
— building it in `trips` would mean `gpx.views` importing `trips.views` back, which is a
second cross-app edge on top of the one the codebase already accepts.
"""

from typing import Any

from django.templatetags.static import static

from gpx.models import GpxTrack

# Resolved through `static()` — never written out as literal paths — because
# `CompressedManifestStaticFilesStorage` serves these under content-hashed names. A
# hardcoded URL 404s in production while resolving fine under DEBUG.
MARKER_ICON = "gpx/vendor/leaflet/images/marker-icon.png"
MARKER_ICON_RETINA = "gpx/vendor/leaflet/images/marker-icon-2x.png"
MARKER_SHADOW = "gpx/vendor/leaflet/images/marker-shadow.png"


def build_map_config(track: GpxTrack | None) -> dict[str, Any] | None:
    """Return the blob the detail template serialises, or `None` if there is no map to draw.

    Args:
        track: The trip's current track, or `None` when nothing has been uploaded.

    Returns:
        A JSON-serialisable dict of points, bounds and marker icon URLs, or `None` when
        no route can be drawn — either because there is no track or because the one
        stored carries no points.

    A track with no points cannot happen: `gpx.parsing.parse_gpx` rejects an empty track
    at upload. The branch exists anyway because the PRD's only NFR forbids a blank page,
    and a row that predates that rule — or arrives through the admin — must still land on
    a deliberate message rather than on an empty map container.
    """
    if track is None or not track.points:
        return None
    return {
        "points": track.points,
        # The nested-pair form `[[lat, lng], [lat, lng]]` is what `map.fitBounds` takes.
        # Derived at upload from the points actually stored, so the box provably contains
        # the line the map draws.
        "bounds": [
            [track.min_latitude, track.min_longitude],
            [track.max_latitude, track.max_longitude],
        ],
        "icons": {
            "iconUrl": static(MARKER_ICON),
            "iconRetinaUrl": static(MARKER_ICON_RETINA),
            "shadowUrl": static(MARKER_SHADOW),
        },
    }
