"""Ordering and the chronology predicate — `gpx/stages.py`.

Ordering tests deliberately create the later-ridden stage first: an order that merely
agreed with upload order would prove nothing about `started_at` driving the sort.
"""

from datetime import UTC, datetime

import pytest

from gpx.models import GpxTrack
from gpx.stages import chronology_is_established, ordered_stage_tracks
from trips.models import Trip

BOUNDS = {
    "min_latitude": 50.0,
    "min_longitude": 19.0,
    "max_latitude": 50.1,
    "max_longitude": 19.1,
}


def _track(
    trip: Trip,
    filename: str,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> GpxTrack:
    return GpxTrack.objects.create(
        trip=trip,
        file=f"gpx/1/1/{filename}",
        points=[[50.0, 19.0]],
        original_filename=filename,
        started_at=started_at,
        ended_at=ended_at,
        **BOUNDS,
    )


@pytest.mark.django_db
def test_two_timed_stages_uploaded_in_reverse_ride_order_come_back_in_ride_order(
    trip: Trip,
) -> None:
    day_two = _track(
        trip,
        "day-2.gpx",
        started_at=datetime(2026, 6, 2, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
    )
    day_one = _track(
        trip,
        "day-1.gpx",
        started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )

    assert list(ordered_stage_tracks(trip)) == [day_one, day_two]


@pytest.mark.django_db
def test_two_untimed_stages_come_back_in_upload_order(trip: Trip) -> None:
    first = _track(trip, "first.gpx")
    second = _track(trip, "second.gpx")

    assert list(ordered_stage_tracks(trip)) == [first, second]


@pytest.mark.django_db
def test_a_mixed_pair_returns_the_timed_stage_first_and_the_untimed_one_appended(
    trip: Trip,
) -> None:
    untimed = _track(trip, "untimed.gpx")
    timed = _track(
        trip,
        "timed.gpx",
        started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )

    assert list(ordered_stage_tracks(trip)) == [timed, untimed]


@pytest.mark.django_db
def test_chronology_is_established_for_all_timed_stages(trip: Trip) -> None:
    tracks = [
        _track(
            trip,
            "a.gpx",
            started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
            ended_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        ),
        _track(
            trip,
            "b.gpx",
            started_at=datetime(2026, 6, 2, 8, 0, tzinfo=UTC),
            ended_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        ),
    ]

    assert chronology_is_established(tracks) is True


@pytest.mark.django_db
def test_chronology_is_established_is_false_when_any_stage_is_untimed(trip: Trip) -> None:
    tracks = [
        _track(
            trip,
            "a.gpx",
            started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
            ended_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        ),
        _track(trip, "b.gpx"),
    ]

    assert chronology_is_established(tracks) is False


@pytest.mark.django_db
def test_chronology_is_established_is_false_for_a_single_untimed_stage(trip: Trip) -> None:
    assert chronology_is_established([_track(trip, "a.gpx")]) is False


def test_chronology_is_established_is_false_for_no_stages() -> None:
    assert chronology_is_established([]) is False
