"""The single place untrusted GPX bytes are turned into coordinates.

Every interaction with attacker-controlled XML in this project happens in this module, so
the security surface is one reviewable file rather than logic spread through a form.
"""

import re
from dataclasses import dataclass

import gpxpy
from gpxpy.gpx import GPXException, GPXXMLSyntaxException

from gpx.constants import MAX_GPX_POINTS
from gpx.exceptions import (
    GpxContentError,
    GpxSyntaxError,
    GpxTooManyPointsError,
)

# A document type declaration anywhere in the text is disqualifying — see `parse_gpx`.
DOCTYPE_PATTERN = re.compile(r"<!DOCTYPE", re.IGNORECASE)

UPLOAD_ENCODING = "utf-8"


@dataclass(frozen=True)
class ParsedTrack:
    """An ordered route and the box that contains it, derived once at upload time.

    Parsing here — rather than at render time — means a file that parsed once can never
    fail on a page view, and the error reaches the user at the only moment they can act
    on it.
    """

    points: tuple[tuple[float, float], ...]
    min_latitude: float
    min_longitude: float
    max_latitude: float
    max_longitude: float

    def json_points(self) -> list[list[float]]:
        """Return the points in the shape `GpxTrack.points` stores and the map reads.

        `JSONField` serialises a tuple to a JSON array, so a tuple would round-trip
        through the database as a list anyway — converting here keeps the in-memory
        instance and the re-read row identical instead of only eventually equal.
        """
        return [[latitude, longitude] for latitude, longitude in self.points]


def parse_gpx_bytes(raw: bytes) -> ParsedTrack:
    """Decode uploaded bytes as UTF-8 and parse them as GPX.

    Args:
        raw: The exact bytes the user uploaded.

    Returns:
        The route and its bounds.

    Raises:
        GpxSyntaxError: The bytes are not UTF-8 text, are not well-formed XML, or carry
            a document type declaration.
        GpxContentError: The XML is well-formed but is not a usable GPX track.
        GpxTooManyPointsError: The track carries more than `MAX_GPX_POINTS` points.
    """
    try:
        text = raw.decode(UPLOAD_ENCODING)
    except UnicodeDecodeError as e:
        raise GpxSyntaxError("The file is not UTF-8 text.") from e
    return parse_gpx(text)


def parse_gpx(text: str) -> ParsedTrack:
    """Parse GPX text into an ordered point list and its bounds.

    Args:
        text: The decoded contents of an uploaded file. Untrusted.

    Returns:
        The route and its bounds.

    Raises:
        GpxSyntaxError: The text is not well-formed XML, or carries a document type
            declaration.
        GpxContentError: The XML is well-formed but is not a usable GPX track.
        GpxTooManyPointsError: The track carries more than `MAX_GPX_POINTS` points.
    """
    # Deliberate text-level pre-check, and NOT redundant with gpxpy: the pinned stdlib
    # ElementTree backend rejects *external* entity references on its own but happily
    # expands *internal* ones, so a few nested definitions in a file well under the size
    # cap expand to gigabytes at parse time (billion laughs). gpxpy exposes no switch for
    # that, and no ruff rule sees through `gpxpy.parse`, so the guard has nowhere to live
    # but here — before the text reaches a parser at all. A legitimate GPX file carries
    # no internal DTD, so there is no false-positive cost. Do not remove this as dead
    # weight; `tests/gpx/test_gpx_parsing.py` pins the behaviour it buys.
    if DOCTYPE_PATTERN.search(text):
        raise GpxSyntaxError("The file declares a document type and was not parsed.")

    try:
        gpx = gpxpy.parse(text)
    except GPXXMLSyntaxException as e:
        # Ordered first: gpxpy defines this as a subclass of GPXException, and the two
        # are distinct user-facing failures — broken file vs. wrong kind of file.
        raise GpxSyntaxError("The file is not well-formed XML.") from e
    except GPXException as e:
        raise GpxContentError("The file is not valid GPX.") from e

    # No guard against a point with missing coordinates: gpxpy rejects a `trkpt` with no
    # `lat`/`lon` with a `GPXException` of its own, caught above, and types both
    # attributes as plain floats. A local check here would be an unreachable branch.
    points = [
        (point.latitude, point.longitude)
        for track in gpx.tracks
        for segment in track.segments
        for point in segment.points
    ]

    # Rejected at the boundary rather than guarded at every downstream consumer: an empty
    # track yields degenerate bounds and an unrenderable map.
    if not points:
        raise GpxContentError("The file contains no track points.")

    # The upper bound of the same boundary rule: an empty track cannot be drawn, and one
    # this large cannot be drawn either — the detail page inlines every point stored here.
    # Refused at upload so the user learns of it while they can still act on it, rather
    # than on a page view of a trip that already accepted the file.
    if len(points) > MAX_GPX_POINTS:
        raise GpxTooManyPointsError(f"The file has more than {MAX_GPX_POINTS} track points.")

    # Derived from the points that were actually kept, rather than from
    # `gpx.get_bounds()`, so the box provably contains the polyline the map draws — and
    # so the four floats need no narrowing from `GPXBounds`' optional members.
    latitudes = [latitude for latitude, _ in points]
    longitudes = [longitude for _, longitude in points]
    return ParsedTrack(
        points=tuple(points),
        min_latitude=min(latitudes),
        min_longitude=min(longitudes),
        max_latitude=max(latitudes),
        max_longitude=max(longitudes),
    )
