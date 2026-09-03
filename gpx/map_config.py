"""Assembles what `gpx/static/gpx/map.js` needs to draw a trip's stages.

Built here rather than in either view because two views render the trip detail page:
`TripDetailView` on a normal visit, and `GpxUploadView` when it re-renders that page with
a form error. A helper reachable from only one of them would leave the other rendering the
"route could not be displayed" branch over a perfectly healthy set of stages.

It lives in `gpx` rather than `trips` for two reasons: the tracks and the vendored Leaflet
assets whose URLs it resolves are both this app's, and `trips` already imports from `gpx`
— building it in `trips` would mean `gpx.views` importing `trips.views` back, which is a
second cross-app edge on top of the one the codebase already accepts.
"""

from collections.abc import Sequence
from typing import Any

from django.templatetags.static import static

from gpx.constants import (
    MARKER_SHADOW,
    MARKER_STAGE_BREAK,
    MARKER_STAGE_FINISH,
    MARKER_STAGE_START,
)
from gpx.stages import Stage, chronology_is_established


def build_map_config(stages: Sequence[Stage]) -> dict[str, Any] | None:
    """Return the blob the detail template serialises, or `None` if there is no map to draw.

    Args:
        stages: `trip`'s stages in ride order, from `gpx.stages.build_stages`.

    Returns:
        A JSON-serialisable dict of segments, bounds, markers and marker icon URLs, or
        `None` when no route can be drawn — either because there are no stages or because
        none of them carries any points.

    A stage with no points cannot happen through upload: `gpx.parsing.parse_gpx` rejects an
    empty track. The branch exists anyway because the PRD's only NFR forbids a blank page,
    and a row that predates that rule — or arrives through the admin — must still land on a
    deliberate message rather than on an empty map container. Such a stage is skipped for
    segments and markers rather than aborting the whole build, so its healthy siblings still
    draw.
    """
    drawable = [stage for stage in stages if stage.track.points]
    if not drawable:
        return None

    established = chronology_is_established([stage.track for stage in stages])

    segments = [
        {"number": stage.number, "color": stage.color, "points": stage.track.points}
        for stage in drawable
    ]

    # Aggregated from the stored scalar bounds columns, never from the points themselves —
    # the same reason a single stage's bounds were server-derived: the box provably contains
    # every line drawn, and it costs nothing per point.
    bounds = [
        [
            min(stage.track.min_latitude for stage in drawable),
            min(stage.track.min_longitude for stage in drawable),
        ],
        [
            max(stage.track.max_latitude for stage in drawable),
            max(stage.track.max_longitude for stage in drawable),
        ],
    ]

    markers = [
        {"kind": "start", "point": drawable[0].track.points[0], "title": "Start"},
        {"kind": "finish", "point": drawable[-1].track.points[-1], "title": "Finish"},
    ]
    # A break marker at the end of each stage but the last. Suppressed entirely unless
    # ride order is established for *every* stage in the trip — an upload-ordered boundary
    # asserts nothing about where the rider actually stopped and resumed.
    if established:
        for stage in drawable[:-1]:
            markers.append(
                {
                    "kind": "break",
                    "point": stage.track.points[-1],
                    "title": f"End of stage {stage.number}",
                }
            )

    return {
        "segments": segments,
        # The nested-pair form `[[lat, lng], [lat, lng]]` is what `map.fitBounds` takes.
        "bounds": bounds,
        "markers": markers,
        "icons": {
            "start": {
                "iconUrl": static(MARKER_STAGE_START),
                "iconRetinaUrl": static(MARKER_STAGE_START),
                "shadowUrl": static(MARKER_SHADOW),
            },
            "finish": {
                "iconUrl": static(MARKER_STAGE_FINISH),
                "iconRetinaUrl": static(MARKER_STAGE_FINISH),
                "shadowUrl": static(MARKER_SHADOW),
            },
            "break": {
                "iconUrl": static(MARKER_STAGE_BREAK),
                "iconRetinaUrl": static(MARKER_STAGE_BREAK),
                "shadowUrl": static(MARKER_SHADOW),
            },
        },
    }
