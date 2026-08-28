"""What the trip detail page says about a route's distance, time and elevation.

The formatting itself is pinned in `tests/gpx/test_gpx_statistics.py`; these tests cover
the page's half of the contract — that the section appears where a track does, that a stat
the file never carried reads as a sentence rather than as a zero, that a row whose columns
were never computed says so in its own words, and that both views rendering this template
supply the blob.
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from tests.conftest import TrackFactory
from trips.models import Trip

STATS_HEADING = "<h2>Stats</h2>"
RE_UPLOAD_SENTENCE = "These stats have not been worked out for this route."
NO_TIMESTAMPS_NOTE = "Not recorded — the GPX file carried no usable timestamps."
NO_ELEVATION_NOTE = "Not recorded — the GPX file carried no usable elevation data."


def detail_url(trip: Trip) -> str:
    return reverse("trips:detail", kwargs={"pk": trip.pk})


@pytest.fixture
def trip(rider: User) -> Trip:
    return Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)


@pytest.mark.django_db
def test_a_track_with_every_statistic_renders_all_four_values(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(
        trip,
        distance_meters=42195.0,
        duration_seconds=8100.0,
        elevation_gain_meters=1240.4,
        elevation_loss_meters=1187.6,
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert STATS_HEADING in body
    assert "42.2 km" in body
    assert "2 h 15 min" in body
    assert "1240 m" in body
    assert "1188 m" in body
    assert RE_UPLOAD_SENTENCE not in body


@pytest.mark.django_db
def test_the_time_stat_is_labelled_recorded_time_not_elapsed_time(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The label is the semantic, so it is asserted rather than left to the template.

    `duration_seconds` is the sum of each GPX segment's own span — the overnight gaps on a
    multi-day tour are not in it. Calling the number "elapsed" would be wrong by days on
    exactly the kind of trip this product is for.
    """
    make_gpx_track(trip, duration_seconds=8100.0)

    body = auth_client.get(detail_url(trip)).content.decode()

    assert "Recorded time" in body
    assert "Elapsed" not in body


@pytest.mark.django_db
def test_a_track_with_no_timestamps_says_so_and_still_renders_its_distance(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """`valid-track.gpx`'s shape. One absent input may not cost the stats that are present.

    The note, not a zero: "0 min" would read as a ride that took no time rather than as a
    file that never said.
    """
    make_gpx_track(
        trip,
        distance_meters=3661.09,
        elevation_gain_meters=120.0,
        elevation_loss_meters=80.0,
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert "3.7 km" in body
    assert "120 m" in body
    assert NO_TIMESTAMPS_NOTE in body
    assert "<dd>0 min</dd>" not in body
    assert RE_UPLOAD_SENTENCE not in body


@pytest.mark.django_db
def test_a_track_with_no_elevation_says_so_for_both_elevation_stats(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """`second-track.gpx`'s shape, where only distance survives the parse."""
    make_gpx_track(trip, distance_meters=3661.09)

    body = auth_client.get(detail_url(trip)).content.decode()

    assert "3.7 km" in body
    assert body.count(NO_ELEVATION_NOTE) == 2
    assert NO_TIMESTAMPS_NOTE in body
    assert "<dd>0 m</dd>" not in body


@pytest.mark.django_db
def test_a_track_whose_statistics_were_never_computed_points_at_re_upload(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The legacy row: every column null, so the page owes a different sentence.

    Not the per-stat notes — those blame the file, and this row's file may well carry
    everything. What is missing is the computation, and re-uploading is the fix.
    """
    make_gpx_track(trip)

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["stats"] is None
    assert STATS_HEADING in body
    assert RE_UPLOAD_SENTENCE in body
    assert NO_TIMESTAMPS_NOTE not in body
    assert NO_ELEVATION_NOTE not in body


@pytest.mark.django_db
def test_a_trip_with_no_track_renders_no_stats_section_at_all(
    auth_client: Client, trip: Trip
) -> None:
    """No track, no statistics — and no heading either, exactly as there is no map.

    The section lives inside the template's `{% if track %}` branch precisely so this
    needs no second condition that could drift out of step with the map's.
    """
    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["stats"] is None
    assert STATS_HEADING not in body
    assert RE_UPLOAD_SENTENCE not in body
    assert "Recorded time" not in body


@pytest.mark.django_db
def test_a_rejected_upload_re_renders_the_stats_the_trip_already_had(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The parity both view docstrings warn about, asserted rather than commented.

    `GpxUploadView` renders this same template on a validation error, so it owes it the
    same `stats` key. Supplied on the GET path alone, a rider who picks the wrong file is
    told their route's figures were never worked out — a false report about intact data.
    The two responses are compared to each other, so the assertion cannot pass by both
    paths being equally wrong about the values.
    """
    make_gpx_track(
        trip,
        distance_meters=42195.0,
        duration_seconds=8100.0,
        elevation_gain_meters=1240.4,
        elevation_loss_meters=1187.6,
    )
    expected = auth_client.get(detail_url(trip)).context["stats"]

    response = auth_client.post(
        reverse("gpx:upload", kwargs={"pk": trip.pk}),
        {"file": SimpleUploadedFile("notes.txt", b"not a gpx file", content_type="text/plain")},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["stats"] == expected
    assert "42.2 km" in body
    assert "2 h 15 min" in body
    assert RE_UPLOAD_SENTENCE not in body


@pytest.mark.django_db
def test_a_stored_zero_renders_as_a_value_and_not_as_the_missing_note(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The other half of the zero-versus-null contract, asserted at the template.

    `build_trip_stats` distinguishes a null column from a legitimate zero, and the page has
    to preserve that distinction rather than re-collapse it. A one-point *timed* file
    genuinely stores `duration_seconds = 0.0`, so the falsy value here is reachable from a
    real upload and not a contrived one.

    Note what this does and does not pin. It passes under a truthiness gate too, because
    every zero formats to a non-empty string — that accident is precisely why the gate read
    as safe. What it pins is that invariant: if a formatter is ever changed to return `""`
    for a zero, this test fails, and the `is not None` gates in the template are what stop
    that change from silently relabelling a real zero as "Not recorded".
    """
    make_gpx_track(
        trip,
        distance_meters=0.0,
        duration_seconds=0.0,
        elevation_gain_meters=0.0,
        elevation_loss_meters=0.0,
    )

    body = auth_client.get(detail_url(trip)).content.decode()

    assert "0.0 km" in body
    assert "0 min" in body
    assert "0 m" in body
    assert NO_TIMESTAMPS_NOTE not in body
    assert NO_ELEVATION_NOTE not in body
    assert RE_UPLOAD_SENTENCE not in body
