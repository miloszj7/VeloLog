"""The backfill helper, and the command that re-runs it on demand.

Migration `0003` calls the same helper, but it cannot be tested through the migration:
migrations run against an empty in-memory database in this suite, so the data operation is
a no-op under `pytest` and would prove nothing. The helper is therefore exercised
directly, and these tests are the only thing standing behind `0003`.

Every `None` assertion is written `is None`, never as falsy. `0.0` is a legal stored value
— a track whose points are all identical has a real distance of zero — and it is precisely
the value the statistics layer exists to keep distinct from "the file did not carry this".
"""

import logging

import pytest
from django.core.management import call_command

from gpx.models import GpxTrack
from gpx.statistics import backfill_track_statistics
from tests.conftest import GPX_BOUNDS, GPX_POINTS, StoredTrackFactory, TrackFactory
from tests.gpx.conftest import GpxBytesReader
from trips.models import Trip

# Both timed-track.gpx and valid-track.gpx trace the same three coordinates, so the two
# report the same horizontal distance — which is the point: the pair differ only in
# whether `<time>` is present.
FIXTURE_DISTANCE_METERS = 3661.09
# timed-track.gpx runs 08:00 → 09:00 in a single segment.
TIMED_TRACK_SECONDS = 3600.0
# A value no fixture could ever produce, so a test asserting it survived is asserting that
# nothing recomputed the row rather than that a recomputation happened to agree.
SENTINEL_DISTANCE_METERS = 1.0


@pytest.mark.django_db
def test_backfilling_a_timed_track_fills_every_statistic(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    """The legacy-row shape: `make_stored_track` leaves all four columns null."""
    track = make_stored_track(trip, content=gpx_bytes("timed-track.gpx"))
    assert track.distance_meters is None

    assert backfill_track_statistics(track) is True

    track.refresh_from_db()
    assert track.distance_meters == pytest.approx(FIXTURE_DISTANCE_METERS, abs=0.01)
    assert track.duration_seconds == TIMED_TRACK_SECONDS
    assert track.elevation_gain_meters is not None
    assert track.elevation_loss_meters is not None


@pytest.mark.django_db
def test_backfilling_an_untimed_track_leaves_recorded_time_null(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    """`valid-track.gpx` carries `<ele>` but no `<time>`, so three of the four fill.

    The gates live in `gpx/parsing.py` and are pinned there; what this asserts is that the
    backfill path goes through them rather than around them — it would be entirely
    possible to write a helper that stored `get_duration()`'s `0.0` here.
    """
    track = make_stored_track(trip, content=gpx_bytes("valid-track.gpx"))

    assert backfill_track_statistics(track) is True

    track.refresh_from_db()
    assert track.distance_meters == pytest.approx(FIXTURE_DISTANCE_METERS, abs=0.01)
    assert track.duration_seconds is None
    assert track.elevation_gain_meters is not None
    assert track.elevation_loss_meters is not None


@pytest.mark.django_db
def test_a_track_whose_file_is_missing_is_left_null_and_does_not_raise(
    trip: Trip,
    make_gpx_track: TrackFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`make_gpx_track` assigns a storage key and never writes bytes behind it.

    This is the `MEDIA_ROOT`-misconfigured shape the whole best-effort contract exists
    for: `migrate` has to survive it unattended, so the helper may not raise. The log
    assertion is the other half — a failure that is absorbed *and* silent leaves an
    operator with null columns and nothing to chase.
    """
    track = make_gpx_track(trip)

    with caplog.at_level(logging.ERROR, logger="gpx.statistics"):
        assert backfill_track_statistics(track) is False

    track.refresh_from_db()
    assert track.distance_meters is None
    assert track.duration_seconds is None
    assert track.elevation_gain_meters is None
    assert track.elevation_loss_meters is None
    assert "Could not recompute track statistics" in caplog.text


@pytest.mark.django_db
def test_a_backfill_never_touches_the_points_or_the_bounds(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    """The safety property of `update_fields`, asserted rather than trusted.

    `make_stored_track` stores the conftest points and bounds, which do not describe the
    fixture file at all — so a helper that re-derived them from the parse would visibly
    overwrite these values. That mismatch is deliberate: it makes the assertion sharp
    instead of tautological.
    """
    track = make_stored_track(trip, content=gpx_bytes("timed-track.gpx"))

    assert backfill_track_statistics(track) is True

    track.refresh_from_db()
    assert track.points == GPX_POINTS
    assert track.min_latitude == GPX_BOUNDS["min_latitude"]
    assert track.min_longitude == GPX_BOUNDS["min_longitude"]
    assert track.max_latitude == GPX_BOUNDS["max_latitude"]
    assert track.max_longitude == GPX_BOUNDS["max_longitude"]


@pytest.mark.django_db
def test_the_command_fills_a_track_whose_statistics_are_null(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    track = make_stored_track(trip, content=gpx_bytes("timed-track.gpx"))

    call_command("backfill_gpx_stats")

    track.refresh_from_db()
    assert track.distance_meters == pytest.approx(FIXTURE_DISTANCE_METERS, abs=0.01)
    assert track.duration_seconds == TIMED_TRACK_SECONDS


@pytest.mark.django_db
def test_the_command_leaves_an_already_filled_track_alone(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    """Default selection is null-stats rows only, so a re-run is not a re-parse of everything."""
    track = make_stored_track(trip, content=gpx_bytes("timed-track.gpx"))
    GpxTrack.objects.filter(pk=track.pk).update(distance_meters=SENTINEL_DISTANCE_METERS)

    call_command("backfill_gpx_stats")

    track.refresh_from_db()
    assert track.distance_meters == SENTINEL_DISTANCE_METERS


@pytest.mark.django_db
def test_the_command_reprocesses_a_filled_track_with_all(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    """`--all` is the path for a track whose file was replaced or whose figures are stale."""
    track = make_stored_track(trip, content=gpx_bytes("timed-track.gpx"))
    GpxTrack.objects.filter(pk=track.pk).update(distance_meters=SENTINEL_DISTANCE_METERS)

    call_command("backfill_gpx_stats", "--all")

    track.refresh_from_db()
    assert track.distance_meters == pytest.approx(FIXTURE_DISTANCE_METERS, abs=0.01)


@pytest.mark.django_db
def test_the_command_reports_a_missing_file_and_keeps_going(
    trip: Trip,
    make_gpx_track: TrackFactory,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One unreadable row may not cost the readable ones, and may not fail the command.

    Two rows rather than one, because "does not raise" and "still fills the rest" are
    different claims and only the second one is what an operator running this after
    correcting `MEDIA_ROOT` actually needs.
    """
    missing = make_gpx_track(trip, original_filename="lost-day-2.gpx")
    readable = make_stored_track(trip, content=gpx_bytes("timed-track.gpx"))

    call_command("backfill_gpx_stats")

    captured = capsys.readouterr()
    assert f"Skipped track {missing.pk} (lost-day-2.gpx)." in captured.err
    assert "Filled 1, skipped 1." in captured.out
    readable.refresh_from_db()
    assert readable.distance_meters == pytest.approx(FIXTURE_DISTANCE_METERS, abs=0.01)
    missing.refresh_from_db()
    assert missing.distance_meters is None
