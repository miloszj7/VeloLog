import gpxpy
import gpxpy.parser
import pytest

from gpx.exceptions import (
    GpxContentError,
    GpxEncodingError,
    GpxParseError,
    GpxSyntaxError,
    GpxTooManyPointsError,
)
from gpx.parsing import parse_gpx, parse_gpx_bytes, track_statistics
from tests.gpx.conftest import GpxBytesReader

# Two bytes that are a valid UTF-16 BOM and never a valid UTF-8 sequence, kept as a
# named constant so the encoding tests below read as intent rather than as an escape.
UNDECODABLE = bytes([0xFF, 0xFE])

# `timed-track.gpx` runs 08:00 → 09:00 in one segment.
TIMED_TRACK_SECONDS = 3600.0
# `two-segment-track.gpx` records 08:00 → 09:00 and 15:00 → 16:00. The sum of the two
# segment spans is the recorded time; the span from its first point to its last is not.
TWO_SEGMENT_RECORDED_SECONDS = 2 * 3600.0
TWO_SEGMENT_WALL_CLOCK_SECONDS = 8 * 3600.0


def test_gpxpy_parses_with_the_stdlib_backend() -> None:
    """Pin the parser backend, because swapping it is a silent security change.

    Installing `lxml` anywhere in the dependency tree flips gpxpy from
    `xml.etree.ElementTree` to `lxml.etree` with no import of its own and no gate that
    would notice — and the two disagree about entity resolution. This project's XXE
    posture is inherited from the stdlib backend (see `gpx/parsing.py`), so the backend
    is part of the contract rather than an implementation detail.
    """
    assert gpxpy.parser.library() == "STDLIB"


def test_a_valid_track_yields_its_points_in_order(gpx_bytes: GpxBytesReader) -> None:
    parsed = parse_gpx_bytes(gpx_bytes("valid-track.gpx"))

    assert parsed.points == ((50.06, 19.94), (50.07, 19.95), (50.05, 19.96))


def test_bounds_are_the_box_containing_every_point(gpx_bytes: GpxBytesReader) -> None:
    """The bounds must come from the points that were kept, not from a parallel source.

    The fixture's last point is deliberately the southernmost *and* the easternmost, so
    bounds taken from the first and last point, or from the first segment alone, produce
    a box that does not contain the polyline.
    """
    parsed = parse_gpx_bytes(gpx_bytes("valid-track.gpx"))

    assert (parsed.min_latitude, parsed.max_latitude) == (50.05, 50.07)
    assert (parsed.min_longitude, parsed.max_longitude) == (19.94, 19.96)


def test_coordinates_are_rounded_to_the_stored_precision() -> None:
    """gpxpy hands back full float precision; what is stored keeps metre resolution.

    The bounds are asserted too: they are derived from the points that were kept, so the
    rounding must reach them as well or the box stops provably containing the polyline.
    """
    parsed = parse_gpx(
        '<?xml version="1.0"?><gpx version="1.1" creator="test"><trk><trkseg>'
        '<trkpt lat="50.061234567890123" lon="19.947654321098765"/>'
        "</trkseg></trk></gpx>"
    )

    assert parsed.points == ((50.06123, 19.94765),)
    assert parsed.min_latitude == 50.06123
    assert parsed.max_longitude == 19.94765


def test_json_points_are_lists_the_json_field_can_store(gpx_bytes: GpxBytesReader) -> None:
    parsed = parse_gpx_bytes(gpx_bytes("valid-track.gpx"))

    assert parsed.json_points() == [[50.06, 19.94], [50.07, 19.95], [50.05, 19.96]]


def test_a_file_with_elevation_and_timestamps_populates_every_statistic(
    gpx_bytes: GpxBytesReader,
) -> None:
    """The fully-populated shape — no existing fixture carried both `<ele>` and `<time>`.

    Distance and duration are asserted against the fixture's own geometry and clock.
    The elevation figures are asserted as present and correctly signed rather than to a
    decimal: gpxpy smooths the elevation series before summing it, so pinning the exact
    metres would pin its smoothing constant rather than this module's behaviour. The
    fixture descends further than it climbs, which is what `loss > gain` encodes.
    """
    parsed = parse_gpx_bytes(gpx_bytes("timed-track.gpx"))

    assert parsed.distance_meters == pytest.approx(3661.09, abs=0.01)
    assert parsed.duration_seconds == TIMED_TRACK_SECONDS
    assert parsed.elevation_gain_meters is not None
    assert parsed.elevation_loss_meters is not None
    assert parsed.elevation_gain_meters > 0
    assert parsed.elevation_loss_meters > parsed.elevation_gain_meters


def test_a_file_with_elevation_but_no_timestamps_reports_no_duration(
    gpx_bytes: GpxBytesReader,
) -> None:
    """`is None`, never falsy: `0.0` is precisely the wrong value being pinned against."""
    parsed = parse_gpx_bytes(gpx_bytes("valid-track.gpx"))

    assert parsed.distance_meters == pytest.approx(3661.09, abs=0.01)
    assert parsed.duration_seconds is None
    assert parsed.elevation_gain_meters is not None
    assert parsed.elevation_loss_meters is not None


def test_a_file_with_neither_elevation_nor_timestamps_reports_only_distance(
    gpx_bytes: GpxBytesReader,
) -> None:
    parsed = parse_gpx_bytes(gpx_bytes("second-track.gpx"))

    assert parsed.distance_meters == pytest.approx(1829.71, abs=0.01)
    assert parsed.duration_seconds is None
    assert parsed.elevation_gain_meters is None
    assert parsed.elevation_loss_meters is None


def test_a_single_untimed_point_reports_no_duration_rather_than_zero(
    gpx_bytes: GpxBytesReader,
) -> None:
    """The case a `get_duration() is None` gate gets wrong, pinned so it cannot come back.

    `GPXTrackSegment.get_duration` returns `0.0` for any segment of fewer than two
    points *before* it reaches the timestamp check that returns `None`, and the file-level
    call sums those zeros — so `get_duration()` reports `0.0`, not `None`, for this file.
    `parse_gpx` accepts a one-point track, so this shape is reachable from a real upload.
    """
    raw = gpx_bytes("single-point-track.gpx")

    assert gpxpy.parse(raw.decode()).get_duration() == 0.0

    parsed = parse_gpx_bytes(raw)

    assert parsed.duration_seconds is None


def test_recorded_time_sums_the_segment_spans_and_excludes_the_gap_between_them(
    gpx_bytes: GpxBytesReader,
) -> None:
    """The recorded-time semantic, pinned rather than inherited.

    gpxpy sums each segment's own first-to-last span and never counts the gap between
    segments. On a multi-day tour that gap is every overnight, which is why the stat is
    labelled "recorded time" and not "elapsed time". The fixture's two spans are an hour
    each and sit six hours apart, so the two candidate numbers cannot be confused.
    """
    parsed = parse_gpx_bytes(gpx_bytes("two-segment-track.gpx"))

    assert parsed.duration_seconds == TWO_SEGMENT_RECORDED_SECONDS
    assert parsed.duration_seconds != TWO_SEGMENT_WALL_CLOCK_SECONDS


def test_absent_elevation_is_stored_as_absent_even_though_gpxpy_reports_zero(
    gpx_bytes: GpxBytesReader,
) -> None:
    """Assert the zero-versus-null gate at its helper, not only through `parse_gpx`.

    `get_uphill_downhill()` answers `(0, 0)` for a file that carries no `<ele>` at all —
    storing that would render "0 m climbed" for an Alpine tour whose exporter omitted
    elevation. The first assertion is what makes the second one mean something.
    """
    gpx = gpxpy.parse(gpx_bytes("second-track.gpx").decode())

    assert gpx.get_uphill_downhill() == (0, 0)

    statistics = track_statistics(gpx)

    assert statistics.elevation_gain_meters is None
    assert statistics.elevation_loss_meters is None


def test_a_lone_elevated_point_reports_no_elevation_rather_than_zero() -> None:
    """The zero-versus-null gate at its second degenerate case, alongside the first.

    An elevation *presence* probe — any point carrying an `<ele>` — passes on this file,
    but a climb is a sum of deltas and one point yields none, so `get_uphill_downhill()`
    answers the same `(0, 0)` it answers for a file with no elevation at all. The first
    assertion is what makes the second one mean something.
    """
    text = (
        '<?xml version="1.0"?><gpx version="1.1" creator="test"><trk><trkseg>'
        '<trkpt lat="50.06" lon="19.94"/>'
        '<trkpt lat="50.07" lon="19.95"><ele>250.0</ele></trkpt>'
        '<trkpt lat="50.05" lon="19.96"/>'
        "</trkseg></trk></gpx>"
    )

    gpx = gpxpy.parse(text)

    assert gpx.get_elevation_extremes().minimum == 250.0
    assert gpx.get_uphill_downhill() == (0, 0)

    parsed = parse_gpx(text)

    assert parsed.elevation_gain_meters is None
    assert parsed.elevation_loss_meters is None


def test_two_elevated_points_are_enough_to_report_a_climb() -> None:
    """The other side of the threshold: at two points a delta exists, so it is reported.

    Pinned as a pair with the test above so a future tightening of the gate cannot quietly
    refuse partially elevated files, which the design accepts deliberately — an understated
    real climb is not the same failure as a fabricated zero.
    """
    parsed = parse_gpx(
        '<?xml version="1.0"?><gpx version="1.1" creator="test"><trk><trkseg>'
        '<trkpt lat="50.06" lon="19.94"><ele>100.0</ele></trkpt>'
        '<trkpt lat="50.07" lon="19.95"><ele>250.0</ele></trkpt>'
        '<trkpt lat="50.05" lon="19.96"/>'
        "</trkseg></trk></gpx>"
    )

    assert parsed.elevation_gain_meters is not None
    assert parsed.elevation_loss_meters is not None


def test_malformed_xml_is_a_syntax_error(gpx_bytes: GpxBytesReader) -> None:
    with pytest.raises(GpxSyntaxError):
        parse_gpx_bytes(gpx_bytes("malformed.gpx"))


def test_an_empty_upload_is_a_syntax_error() -> None:
    """A genuinely 0-byte upload, not `empty-track.gpx`'s well-formed-but-pointless GPX.

    Pinned by name even though it resolves via the same `GpxSyntaxError` branch as
    `test_malformed_xml_is_a_syntax_error` above, so a future change that splits that
    branch is caught rather than silently passing on this scenario.
    """
    with pytest.raises(GpxSyntaxError):
        parse_gpx_bytes(b"")


def test_a_truncated_document_is_a_syntax_error() -> None:
    """Cut off mid-tag, distinct from the fully-malformed fixture above.

    Pinned by name for the same reason as the empty-upload test above: today it shares
    the syntax-error branch, but the phase's own intent names "truncated" as its own
    scenario and a future split of that branch should be caught here too.
    """
    with pytest.raises(GpxSyntaxError):
        parse_gpx_bytes(b'<?xml version="1.0"?><gpx><trk><trkseg><trkpt lat="50.06" lon=')


def test_well_formed_xml_that_is_not_gpx_is_a_content_error(gpx_bytes: GpxBytesReader) -> None:
    with pytest.raises(GpxContentError):
        parse_gpx_bytes(gpx_bytes("not-gpx.gpx"))


def test_gpx_with_an_unparseable_field_value_is_a_content_error(gpx_bytes: GpxBytesReader) -> None:
    """A `<ele>` that is not a number: valid XML, invalid GPX — the other content branch.

    `not-gpx.gpx` above reaches `GpxContentError` by parsing to zero points; this one
    reaches it through gpxpy's own `GPXException`. They are different code paths and a
    single test would leave one of them unexercised.
    """
    with pytest.raises(GpxContentError):
        parse_gpx_bytes(gpx_bytes("invalid-values.gpx"))


def test_a_track_with_no_points_is_rejected(gpx_bytes: GpxBytesReader) -> None:
    """An empty track is refused at the boundary rather than guarded downstream.

    It would otherwise persist happily and produce degenerate bounds — a map that cannot
    be fitted to anything, discovered on a page view rather than at upload.
    """
    with pytest.raises(GpxContentError):
        parse_gpx_bytes(gpx_bytes("empty-track.gpx"))


def test_a_track_with_too_many_points_is_rejected(
    gpx_bytes: GpxBytesReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The upper bound of the rule the empty-track test above pins the lower bound of.

    The cap is patched rather than met with a real payload: a genuine 100,001-point
    fixture costs seconds of parse time on every run to prove one comparison. What the
    cap is worth is measured elsewhere — 262,000 points is a 6 MB payload inlined into
    the detail page.
    """
    monkeypatch.setattr("gpx.parsing.MAX_GPX_POINTS", 2)

    with pytest.raises(GpxTooManyPointsError):
        parse_gpx_bytes(gpx_bytes("valid-track.gpx"))


def test_an_external_entity_payload_is_rejected(gpx_bytes: GpxBytesReader) -> None:
    """XXE: an entity pointing at a local file must never be resolved.

    This one is belt and braces — the pinned stdlib backend raises "undefined entity" on
    its own, so it passes with or without the DTD guard in `gpx/parsing.py`. It is here
    to pin the *outcome* against a future backend swap, which
    `test_gpxpy_parses_with_the_stdlib_backend` above would flag but not by itself
    prevent from mattering.
    """
    with pytest.raises(GpxParseError):
        parse_gpx_bytes(gpx_bytes("xxe.gpx"))


def test_a_nested_internal_entity_payload_is_rejected(gpx_bytes: GpxBytesReader) -> None:
    """Billion laughs: this is the test that proves the DTD guard exists.

    Unlike the XXE payload, the stdlib backend expands this one happily — with the guard
    removed, the fixture parses to a perfectly valid two-point track whose name has been
    inflated to 30,000 characters, and nothing raises. Four levels of nesting is a
    deliberately small ratio: enough to fail without the guard, small enough that a
    regression here does not exhaust the test runner's memory before reporting.
    """
    with pytest.raises(GpxParseError):
        parse_gpx_bytes(gpx_bytes("billion-laughs.gpx"))


def test_a_doctype_is_rejected_before_the_parser_sees_it() -> None:
    """The guard is textual and case-insensitive, and does not depend on a payload."""
    with pytest.raises(GpxSyntaxError):
        parse_gpx('<?xml version="1.0"?><!doctype gpx><gpx></gpx>')


def test_bytes_that_are_not_utf8_and_declare_nothing_are_rejected() -> None:
    with pytest.raises(GpxEncodingError):
        parse_gpx_bytes(UNDECODABLE + b"<gpx></gpx>")


def test_a_track_declaring_latin1_is_parsed_as_latin1(gpx_bytes: GpxBytesReader) -> None:
    """A valid GPX in a declared non-UTF-8 encoding is a real file, not a broken one.

    Older GPS units and several desktop exporters still emit latin-1. Decoding as UTF-8
    unconditionally refused these with a message about XML, which is untrue of the file
    and sends the rider looking for a fault that is not there. The accented character in
    the fixture's track name is what makes the bytes undecodable as UTF-8 at all.
    """
    parsed = parse_gpx_bytes(gpx_bytes("latin1-declared.gpx"))

    assert parsed.points == ((43.55, 7.02), (43.56, 7.03))


def test_a_file_that_does_not_decode_as_the_encoding_it_declares_is_rejected() -> None:
    """Declaring an encoding is not the same as being in it, and neither is a real codec.

    The declared name reaches `bytes.decode` directly, so an unknown one has to come
    back as a rejection rather than as an unhandled `LookupError`.
    """
    with pytest.raises(GpxEncodingError):
        parse_gpx_bytes(b'<?xml version="1.0" encoding="utf-8"?><gpx>' + UNDECODABLE)

    with pytest.raises(GpxEncodingError):
        parse_gpx_bytes(b'<?xml version="1.0" encoding="not-a-codec"?><gpx>' + UNDECODABLE)
