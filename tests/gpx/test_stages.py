"""Ordering and the chronology predicate — `gpx/stages.py`.

Ordering tests deliberately create the later-ridden stage first: an order that merely
agreed with upload order would prove nothing about `started_at` driving the sort.
"""

from datetime import UTC, datetime

import pytest

from gpx.constants import STAGE_COLORS
from gpx.models import GpxTrack
from gpx.stages import (
    build_stages,
    chronology_is_established,
    ordered_stage_tracks,
    trip_span,
)
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


@pytest.mark.django_db
def test_build_stages_numbers_from_one_and_cycles_the_palette(trip: Trip) -> None:
    """The only wraparound in the change, and the one arithmetic no other test reaches.

    `STAGE_COLORS` holds six hues and the deepest test elsewhere builds three stages
    (`tests/trips/test_trip_detail_map.py` asserts `STAGE_COLORS[:3]`), so nothing
    exercised the `% len(STAGE_COLORS)` that three separate docstrings promise. Replacing
    it with plain indexing would raise `IndexError` on a seventh stage with every other
    test still green.

    Seven stages rather than six: six only proves the palette is consumed in order, and
    it is the *seventh* that has to come back round to the first hue. Also the only direct
    unit test of `build_stages`' assembly — `number`, `color` and `file_available` are
    otherwise pinned only through the two views.
    """
    for day in range(1, 8):
        _track(
            trip,
            f"day-{day}.gpx",
            started_at=datetime(2026, 6, day, 8, 0, tzinfo=UTC),
            ended_at=datetime(2026, 6, day, 9, 0, tzinfo=UTC),
        )

    stages = build_stages(trip)

    assert [stage.number for stage in stages] == [1, 2, 3, 4, 5, 6, 7]
    assert [stage.color for stage in stages[:6]] == list(STAGE_COLORS)
    assert (
        stages[6].color == STAGE_COLORS[0]
    ), "the seventh stage did not come back round to the first palette hue"
    # `_track` assigns a storage key without writing bytes behind it, so every stage here
    # is the file-missing shape — which is the honest answer for these rows and pins that
    # `build_stages` reports availability per stage rather than defaulting it to True.
    assert [stage.file_available for stage in stages] == [False] * 7


@pytest.mark.django_db
def test_the_span_runs_from_the_first_stages_start_to_the_last_stages_end(trip: Trip) -> None:
    """Created out of ride order, so the result is `min`/`max` rather than insertion order.

    Three stages rather than two: with a pair, "first start to last end" and "the first
    row's start to the second row's end" are the same answer, and only one of them is the
    contract.
    """
    _track(
        trip,
        "day-2.gpx",
        started_at=datetime(2026, 6, 2, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 2, 17, 0, tzinfo=UTC),
    )
    _track(
        trip,
        "day-3.gpx",
        started_at=datetime(2026, 6, 3, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 3, 16, 30, tzinfo=UTC),
    )
    _track(
        trip,
        "day-1.gpx",
        started_at=datetime(2026, 6, 1, 7, 45, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
    )

    assert trip_span(list(ordered_stage_tracks(trip))) == (
        datetime(2026, 6, 1, 7, 45, tzinfo=UTC),
        datetime(2026, 6, 3, 16, 30, tzinfo=UTC),
    )


@pytest.mark.django_db
def test_there_is_no_span_when_any_stage_is_untimed(trip: Trip) -> None:
    """The gate, on the trip that makes the ungated answer look plausible.

    A span over the timed subset here would read 1 June to 1 June — a real-looking answer,
    and a lower bound presented as the whole tour. `None` is what sends the page back to
    the stored `Trip.date`.
    """
    timed = _track(
        trip,
        "day-1.gpx",
        started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )
    untimed = _track(trip, "day-2.gpx")

    assert trip_span([timed, untimed]) is None


@pytest.mark.django_db
def test_there_is_no_span_for_a_trip_with_no_stages() -> None:
    assert trip_span([]) is None


@pytest.mark.django_db
def test_a_stage_with_a_start_but_no_end_yields_no_span_rather_than_raising(
    trip: Trip,
) -> None:
    """The half-timed row `gpx/parsing.py` cannot produce and the admin can.

    Both instants are stored together or not at all at the parse boundary, so this shape
    only exists after a hand edit through the admin change form — the documented repair
    path, which exposes the two fields individually. `chronology_is_established` reads
    `started_at` alone and would pass it straight through, so without the second check
    `max()` is handed a `None` and the detail page raises `TypeError` for a row someone
    was in the middle of repairing.
    """
    half_edited = _track(
        trip, "day-1.gpx", started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC), ended_at=None
    )

    assert chronology_is_established([half_edited]) is True
    assert trip_span([half_edited]) is None
