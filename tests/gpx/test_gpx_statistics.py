"""Both ends of the statistics columns: the backfill that fills them, and the display
builder that shapes them for the detail page.

Migration `0003` calls the same helper, but it cannot be tested through the migration:
migrations run against an empty in-memory database in this suite, so the data operation is
a no-op under `pytest` and would prove nothing. The helper is therefore exercised
directly, and these tests are the only thing standing behind `0003`.

Every `None` assertion is written `is None`, never as falsy. `0.0` is a legal stored value
— a track whose points are all identical has a real distance of zero — and it is precisely
the value the statistics layer exists to keep distinct from "the file did not carry this".
"""

import logging
from datetime import UTC, datetime
from importlib import import_module

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from gpx.models import GpxTrack
from gpx.statistics import (
    STATS_FIELDS,
    _writable_stats_fields,
    backfill_track_statistics,
    build_trip_stats,
    format_distance,
    format_duration,
    format_elevation,
)
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
# The same 08:00 → 09:00 span as `TIMED_TRACK_SECONDS`, read as the absolute instants
# rather than as a relative length. Both are `Z`-suffixed in the fixture, so the stored
# values must come back as UTC-aware.
TIMED_TRACK_STARTED_AT = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
TIMED_TRACK_ENDED_AT = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
# Imported by path because the module name starts with a digit, so it is not a legal
# dotted import. Reaching into the migration is deliberate: `STATS_COLUMNS_AT_0002` is a
# pin, and a pin nothing asserts against is just a comment.
STATS_COLUMNS_AT_0002 = import_module(
    "gpx.migrations.0003_backfill_gpxtrack_stats"
).STATS_COLUMNS_AT_0002
# `0005` pins its own list for the same reason and is asserted the same way. The two pins
# are deliberately not folded into one parametrized test: what each asserts is that a
# *different* migration's snapshot still matches the schema state that migration runs at,
# and the state is the interesting half.
STATS_COLUMNS_AT_0004 = import_module(
    "gpx.migrations.0005_backfill_gpxtrack_stage_instants"
).STATS_COLUMNS_AT_0004


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
def test_a_track_whose_stored_bytes_no_longer_parse_is_left_null_and_does_not_raise(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The other half of the best-effort contract: the file is there and is not a track.

    A missing file and unreadable bytes reach the helper as unrelated exception types —
    `FileNotFoundError` against `GpxParseError` — from different lines, which is why one
    test cannot stand for both. Both run unattended inside `migrate` at container boot,
    where either escaping fails the deploy over a row whose columns are allowed to stay
    null.
    """
    track = make_stored_track(trip, content=gpx_bytes("malformed.gpx"))
    GpxTrack.objects.filter(pk=track.pk).update(distance_meters=None)

    with caplog.at_level(logging.ERROR, logger="gpx.statistics"):
        assert backfill_track_statistics(track) is False

    track.refresh_from_db()
    assert track.distance_meters is None
    assert track.started_at is None
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
def test_backfilling_a_timed_track_fills_both_stage_instants(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    """A backfilled row and a freshly uploaded one must agree about the same file.

    The instants are what `gpx.stages.chronology_is_established` reads, so a row this
    helper leaves null can never take part in a chronological claim however many timed
    stages join it later. Asserted as exact UTC-aware values, not merely as non-null: a
    naive or offset-shifted instant is the failure this column's parse rule exists to
    prevent, and `is not None` would pass on one.
    """
    track = make_stored_track(trip, content=gpx_bytes("timed-track.gpx"))
    assert track.started_at is None

    assert backfill_track_statistics(track) is True

    track.refresh_from_db()
    assert track.started_at == TIMED_TRACK_STARTED_AT
    assert track.ended_at == TIMED_TRACK_ENDED_AT


@pytest.mark.django_db
def test_backfilling_an_untimed_track_leaves_both_stage_instants_null(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    """Both-or-neither, on the backfill path as at the parse boundary.

    `valid-track.gpx` carries `<ele>` but no `<time>`, so the three elevation/distance
    columns fill and both instants stay null — permanently, since nothing about that file
    will ever yield one. That permanence is why the management command's default filter
    stays on `distance_meters`: a filter on `started_at` would re-select this row forever.
    """
    track = make_stored_track(trip, content=gpx_bytes("valid-track.gpx"))

    assert backfill_track_statistics(track) is True

    track.refresh_from_db()
    assert track.distance_meters == pytest.approx(FIXTURE_DISTANCE_METERS, abs=0.01)
    assert track.started_at is None
    assert track.ended_at is None


@pytest.mark.django_db
def test_the_written_columns_narrow_to_the_ones_the_rows_own_model_carries() -> None:
    """The guard on migration `0003`, which no other test in this suite can reach.

    This module's own docstring explains why: migrations run against an empty database
    here, so `0003`'s data loop never executes and cannot be exercised end to end. What
    *is* reachable is the reason it would break — `STATS_FIELDS` tracks the current model
    and grew when `0004` added the instants, while `0003` runs at `0002`'s state, where
    those columns do not exist. Naming one in that row's `update_fields` raises
    `ValueError`, `0003`'s per-row guard swallows it, and `migrate` prints OK having
    filled nothing.

    The historical model comes from the real migration graph rather than a hand-built
    stand-in, so this stays true if the graph is reordered instead of asserting a
    yesterday's-shape snapshot.
    """
    executor = MigrationExecutor(connection)
    at_0002 = executor.loader.project_state(("gpx", "0002_gpxtrack_stats"))
    historical_track = at_0002.apps.get_model("gpx", "GpxTrack")

    assert _writable_stats_fields(historical_track()) == [
        "distance_meters",
        "duration_seconds",
        "elevation_gain_meters",
        "elevation_loss_meters",
    ]
    # The live model carries every one of them, so nothing is silently dropped in the
    # case that actually runs in production.
    assert _writable_stats_fields(GpxTrack()) == list(STATS_FIELDS)


@pytest.mark.django_db
def test_the_pinned_migration_columns_match_the_state_that_migration_runs_at() -> None:
    """`0003` pins its own field list; this is what keeps the pin honest.

    A pinned tuple solves the drift in one direction and invites it in the other — the
    names could rot against `0002`'s actual schema with nothing to say so. Asserting it
    against the migration graph's own state is what makes the pin a fact rather than a
    comment.
    """
    executor = MigrationExecutor(connection)
    at_0002 = executor.loader.project_state(("gpx", "0002_gpxtrack_stats"))
    historical_fields = {
        field.name for field in at_0002.apps.get_model("gpx", "GpxTrack")._meta.fields
    }

    assert set(STATS_COLUMNS_AT_0002) <= historical_fields
    assert "started_at" not in historical_fields


@pytest.mark.django_db
def test_the_instants_migrations_pinned_columns_match_the_state_it_runs_at() -> None:
    """`0005`'s pin, held to the same standard as `0003`'s.

    `0005` runs at `0004`'s state, where all six columns exist — so today its pin and the
    live `STATS_FIELDS` happen to agree, and the pin looks like duplication. It is not:
    the next column added to `STATS_FIELDS` is the one that would break `0005`'s `.only()`
    the way `0004`'s two instants broke `0003`'s, out of `pending.iterator()` and outside
    the per-row guard. Equality rather than a subset, because a name `0004`'s model does
    not carry is exactly that failure.
    """
    executor = MigrationExecutor(connection)
    at_0004 = executor.loader.project_state(("gpx", "0004_gpxtrack_stage_instants"))
    historical_track = at_0004.apps.get_model("gpx", "GpxTrack")
    historical_fields = {field.name for field in historical_track._meta.fields}

    assert set(STATS_COLUMNS_AT_0004) <= historical_fields
    # The helper writes what the row's own model carries, so at this state that is the
    # whole pin — the migration fills every column in one parse rather than by halves.
    assert _writable_stats_fields(historical_track()) == list(STATS_COLUMNS_AT_0004)


@pytest.mark.django_db
def test_the_command_fills_stage_instants_under_all(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
) -> None:
    """`--all` is the documented recovery for a row whose statistics are already present.

    The default filter cannot reach such a row — that is deliberate and load-bearing, so
    the pending count converges — which makes `--all` the only path that refills instants
    on a row that predates the columns and was caught by an earlier statistics backfill.
    """
    track = make_stored_track(trip, content=gpx_bytes("timed-track.gpx"))
    GpxTrack.objects.filter(pk=track.pk).update(distance_meters=FIXTURE_DISTANCE_METERS)

    call_command("backfill_gpx_stats", "--all")

    track.refresh_from_db()
    assert track.started_at == TIMED_TRACK_STARTED_AT
    assert track.ended_at == TIMED_TRACK_ENDED_AT


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
def test_a_second_default_run_finds_nothing_left_to_do_for_an_untimed_track(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    gpx_bytes: GpxBytesReader,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The convergence property the default filter exists to keep, on the row that tests it.

    An untimed file's instants are null for ever — that is the both-or-neither rule, not a
    gap — so the tempting widening of the default filter to "missing statistics *or*
    instants" would re-select this row on every invocation and the pending tally would
    never reach zero. That destroys the command's only signal for *nothing left to do*, on
    the one path documented for recovering a `0005` that ran against a misconfigured
    `MEDIA_ROOT`. `--all` covers that need instead, and converges by being finite rather
    than by being empty.

    Two runs rather than one: "the tally reaches zero" is a claim about the *second* run,
    and a single run cannot make it.
    """
    track = make_stored_track(trip, content=gpx_bytes("valid-track.gpx"))

    call_command("backfill_gpx_stats")
    assert "Filled 1, skipped 0." in capsys.readouterr().out

    call_command("backfill_gpx_stats")

    assert "Filled 0, skipped 0." in capsys.readouterr().out
    track.refresh_from_db()
    # Still filled by the first run, and still instant-less — the row converged with work
    # genuinely left undone, which is the case that makes the tally honest rather than
    # merely quiet.
    assert track.distance_meters == pytest.approx(FIXTURE_DISTANCE_METERS, abs=0.01)
    assert track.started_at is None


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


def test_distance_reads_in_kilometres_to_one_decimal_place() -> None:
    assert format_distance(3661.09) == "3.7 km"


def test_a_zero_distance_formats_as_a_number_rather_than_disappearing() -> None:
    """A track whose points are all identical has a real distance, and it is zero."""
    assert format_distance(0.0) == "0.0 km"


def test_a_missing_distance_formats_as_none() -> None:
    assert format_distance(None) is None


def test_a_sub_hour_duration_reads_in_minutes_alone() -> None:
    """No `0 h` prefix under an hour — a 45-minute ride is not a zero-hour ride."""
    assert format_duration(2700.0) == "45 min"


def test_a_multi_hour_duration_reads_as_hours_and_minutes() -> None:
    assert format_duration(8100.0) == "2 h 15 min"


def test_a_duration_a_breath_under_an_hour_rounds_up_to_the_hour_form() -> None:
    """Rounding happens before the hours/minutes split, never separately on each part.

    Split first and 3599.9 seconds renders as `"60 min"` — arithmetically defensible and
    obviously wrong on the page.
    """
    assert format_duration(3599.9) == "1 h 00 min"


def test_a_half_minute_rounds_up_rather_than_to_zero() -> None:
    """The half boundary, pinned in the direction that never prints a false nothing.

    Python's `round` is round-half-to-even, so it would send 30 seconds to "0 min" while
    sending 90 to "2 min". Both figures are trivial in magnitude, but "0 min" for a track
    that recorded half a minute is the same class of lie as "0 m" for an unclimbed hill,
    and this module exists to keep those strings off the page.
    """
    assert format_duration(30) == "1 min"
    assert format_duration(90) == "2 min"
    assert format_duration(0) == "0 min"


def test_a_half_metre_rounds_up_rather_than_to_zero() -> None:
    """The same boundary on the elevation formatter, which shares the rounding helper."""
    assert format_elevation(0.5) == "1 m"
    assert format_elevation(1.5) == "2 m"
    assert format_elevation(0.0) == "0 m"


def test_a_missing_duration_formats_as_none() -> None:
    assert format_duration(None) is None


def test_elevation_reads_in_whole_metres() -> None:
    assert format_elevation(1240.4) == "1240 m"


def test_a_missing_elevation_formats_as_none() -> None:
    assert format_elevation(None) is None


def test_no_track_has_no_stats_to_build() -> None:
    assert build_trip_stats(None) is None


@pytest.mark.django_db
def test_a_track_whose_every_statistic_is_null_builds_nothing(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The legacy-row shape: uploaded before the columns existed, missed by the backfill.

    `None` here is what makes the template render the re-upload sentence rather than four
    "the file did not carry this" notes — a different failure, told apart deliberately.
    """
    assert build_trip_stats(make_gpx_track(trip)) is None


@pytest.mark.django_db
def test_a_track_whose_only_value_is_a_zero_distance_still_builds_stats(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The falsy trap, pinned. `0.0` is stored, non-null and falsy all at once.

    A `not any(...)` all-null check would discard this perfectly parsed track into the
    re-upload sentence. Every other column is null here so that the zero is the *only*
    thing standing between the row and that branch.
    """
    track = make_gpx_track(trip, distance_meters=0.0)

    stats = build_trip_stats(track)

    assert stats is not None
    assert stats.distance == "0.0 km"
    assert stats.recorded_time is None
    assert stats.elevation_gain is None
    assert stats.elevation_loss is None


@pytest.mark.django_db
def test_a_fully_populated_track_builds_all_four_strings(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    track = make_gpx_track(
        trip,
        distance_meters=42195.0,
        duration_seconds=8100.0,
        elevation_gain_meters=1240.4,
        elevation_loss_meters=1187.6,
    )

    stats = build_trip_stats(track)

    assert stats is not None
    assert stats.distance == "42.2 km"
    assert stats.recorded_time == "2 h 15 min"
    assert stats.elevation_gain == "1240 m"
    assert stats.elevation_loss == "1188 m"


@pytest.mark.django_db
def test_an_untimed_track_builds_the_other_three_and_leaves_recorded_time_none(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """`valid-track.gpx`'s shape: `<ele>` but no `<time>`, so one field stays absent."""
    track = make_gpx_track(
        trip,
        distance_meters=3661.09,
        elevation_gain_meters=120.0,
        elevation_loss_meters=80.0,
    )

    stats = build_trip_stats(track)

    assert stats is not None
    assert stats.distance == "3.7 km"
    assert stats.recorded_time is None
    assert stats.elevation_gain == "120 m"
    assert stats.elevation_loss == "80 m"
