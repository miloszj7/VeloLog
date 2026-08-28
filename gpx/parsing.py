"""The single place untrusted GPX bytes are turned into coordinates.

Every interaction with attacker-controlled XML in this project happens in this module, so
the security surface is one reviewable file rather than logic spread through a form.
"""

import re
from dataclasses import dataclass

import gpxpy
from gpxpy.gpx import GPX, GPXException, GPXXMLSyntaxException

from gpx.constants import COORDINATE_DECIMAL_PLACES, MAX_GPX_POINTS, MIN_ELEVATED_POINTS
from gpx.exceptions import (
    GpxContentError,
    GpxEncodingError,
    GpxSyntaxError,
    GpxTooManyPointsError,
)

# A document type declaration anywhere in the text is disqualifying — see `parse_gpx`.
DOCTYPE_PATTERN = re.compile(r"<!DOCTYPE", re.IGNORECASE)

UPLOAD_ENCODING = "utf-8"

# An XML document may name its own encoding, and plenty of GPS units and desktop exporters
# still emit latin-1 or windows-1252. Read only from the head of the file: a declaration is
# only valid there, and the bytes are untrusted. The character class is deliberately narrow —
# the captured name goes straight to `bytes.decode`, so it may contain nothing that is not a
# codec name. (Python refuses non-text codecs such as `bz2_codec` in `decode` on its own, and
# an unknown name raises `LookupError`, which is handled at the call site.)
XML_DECLARATION_PATTERN = re.compile(
    rb"""<\?xml[^>]{0,200}?encoding\s*=\s*["']([A-Za-z][A-Za-z0-9._-]{0,40})["']""",
    re.IGNORECASE,
)
DECLARATION_SNIFF_BYTES = 256


@dataclass(frozen=True)
class TrackStatistics:
    """What a parsed track reports about itself, with absent inputs kept absent.

    Two gpxpy calls return `0` where a caller would read `None`, so the presence of each
    optional statistic is decided by a separate probe rather than by the value itself —
    see `track_statistics`. A `None` here means the file carried no such data; a `0.0`
    means the file carried the data and the answer is zero.
    """

    distance_meters: float
    duration_seconds: float | None
    elevation_gain_meters: float | None
    elevation_loss_meters: float | None


def _has_elevation_data(gpx: GPX) -> bool:
    """Report whether the file carries enough elevation to compute a climb from.

    Args:
        gpx: The object `gpxpy.parse` returned.

    Returns:
        Whether at least `MIN_ELEVATED_POINTS` points carry an `<ele>`. Short-circuits on
        reaching the threshold, so a fully elevated track stops after two points rather
        than walking all of them.
    """
    elevated = 0
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                if point.elevation is None:
                    continue
                elevated += 1
                if elevated >= MIN_ELEVATED_POINTS:
                    return True
    return False


def track_statistics(gpx: GPX) -> TrackStatistics:
    """Derive distance, recorded time and elevation change from a parsed track.

    Args:
        gpx: The object `gpxpy.parse` returned. The only place elevation and per-point
            timestamps still exist — neither survives into `ParsedTrack.points`.

    Returns:
        The four statistics, with each optional one `None` when the file did not carry
        the input it is computed from.
    """
    # `length_2d` rather than `length_3d`: the 3D length varies with whether the export
    # happened to carry `<ele>`, so the same route would report two different distances
    # depending on the exporter. Horizontal distance is both stable and what a rider's
    # other tools report.
    distance_meters = gpx.length_2d()

    # `get_uphill_downhill()` returns `UphillDownhill(0, 0)` — not `None` — for a file
    # with no `<ele>` at all, which would render as "0 m climbed" for an Alpine tour.
    # Counting elevated points rather than probing `get_elevation_extremes().minimum`:
    # that probe is satisfied by a *single* elevated point, and one point yields no delta,
    # so gpxpy returns the same `(0, 0)` and the gate lets through exactly the value it was
    # built to stop. A partially elevated file is still accepted — its climb is understated
    # but real — and only the degenerate case below the threshold is refused.
    elevation_gain_meters: float | None = None
    elevation_loss_meters: float | None = None
    if _has_elevation_data(gpx):
        uphill_downhill = gpx.get_uphill_downhill()
        elevation_gain_meters = uphill_downhill.uphill
        elevation_loss_meters = uphill_downhill.downhill

    # The same trap, mirrored. `get_duration()` looks like the presence probe for time
    # and is not one: `GPXTrackSegment.get_duration` returns `0.0` for any segment of
    # fewer than two points *before* it reaches the timestamp check that returns `None`,
    # and the track- and file-level calls sum those zeros. `parse_gpx` accepts a
    # one-point file, so gating on `get_duration() is None` would store the exact zero
    # this gate exists to prevent. `get_time_bounds().start_time` is `None` exactly when
    # no point carried a `<time>`.
    duration_seconds: float | None = None
    if gpx.get_time_bounds().start_time is not None:
        duration_seconds = gpx.get_duration()

    return TrackStatistics(
        distance_meters=distance_meters,
        duration_seconds=duration_seconds,
        elevation_gain_meters=elevation_gain_meters,
        elevation_loss_meters=elevation_loss_meters,
    )


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
    distance_meters: float
    """Horizontal track length in metres. Never `None`: an empty track is rejected."""
    duration_seconds: float | None
    """Recorded time in seconds — **not** wall-clock elapsed time.

    gpxpy sums each *segment's* own first-to-last span and never counts the gaps between
    segments. On a multi-day tour those gaps include every overnight, so for a
    paused-and-resumed export this is riding time, not the span from the first point to
    the last. The two coincide only for a single-segment file.

    `None` when no point in the file carried a `<time>`.
    """
    elevation_gain_meters: float | None
    """Total ascent in metres, or `None` when the file carried no usable `<ele>`.

    "Usable" means at least `MIN_ELEVATED_POINTS` points carried one. A climb is a sum of
    deltas, so a lone elevated point yields zero rather than a figure, and storing that
    zero is indistinguishable from the fabricated zero this gate exists to reject.
    """
    elevation_loss_meters: float | None
    """Total descent in metres, or `None` on the same terms as `elevation_gain_meters`."""

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
        GpxEncodingError: The bytes are not UTF-8 and declare no encoding that decodes
            them.
        GpxSyntaxError: The text is not well-formed XML, or carries a document type
            declaration.
        GpxContentError: The XML is well-formed but is not a usable GPX track.
        GpxTooManyPointsError: The track carries more than `MAX_GPX_POINTS` points.
    """
    try:
        text = raw.decode(UPLOAD_ENCODING)
    except UnicodeDecodeError as e:
        # UTF-8 is the XML default and covers essentially every modern export, so it is
        # tried first and unconditionally. Only once it has failed is the document's own
        # declaration worth consulting — and only a declaration, never a guess: latin-1
        # decodes any byte sequence whatsoever, so falling back to it blindly would
        # replace an honest rejection with silent mojibake in every track name.
        declared = declared_encoding(raw)
        if declared is None:
            raise GpxEncodingError("The file is not UTF-8 and declares no encoding.") from e
        try:
            text = raw.decode(declared)
        except (UnicodeDecodeError, LookupError) as inner:
            raise GpxEncodingError(
                f"The file does not decode as the {declared} it declares."
            ) from inner
    return parse_gpx(text)


def declared_encoding(raw: bytes) -> str | None:
    """Return the encoding named in the document's XML declaration, if it names one.

    Args:
        raw: The exact bytes the user uploaded. Untrusted.

    Returns:
        The declared codec name, or `None` if the head of the file declares none.
    """
    match = XML_DECLARATION_PATTERN.search(raw[:DECLARATION_SNIFF_BYTES])
    if match is None:
        return None
    return match.group(1).decode("ascii")


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
        (
            round(point.latitude, COORDINATE_DECIMAL_PLACES),
            round(point.longitude, COORDINATE_DECIMAL_PLACES),
        )
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

    # Computed after both rejections, not before: a file that is about to be refused
    # should not pay for a full-track distance walk, and the rejection messages above
    # stay the first thing this function does.
    statistics = track_statistics(gpx)

    return ParsedTrack(
        points=tuple(points),
        min_latitude=min(latitudes),
        min_longitude=min(longitudes),
        max_latitude=max(latitudes),
        max_longitude=max(longitudes),
        distance_meters=statistics.distance_meters,
        duration_seconds=statistics.duration_seconds,
        elevation_gain_meters=statistics.elevation_gain_meters,
        elevation_loss_meters=statistics.elevation_loss_meters,
    )
