"""What date the trip detail page prints under the trip's name.

The derivation itself is pinned in `tests/gpx/test_stages.py`; these tests cover the
page's half — that a fully timed tour shows its real span, that anything less shows the
stored `Trip.date` exactly as v1 did, and that both views rendering this template supply
the key.

Every trip here is stored with a date **outside** its stages' instants. That is what makes
the assertions sharp: with the fixture's usual 1 June, "the span rendered" and "the stored
date rendered" share a substring, and a test asserting the first would pass on the second.

One deliberate exception to "never share a substring": once the span diverges from
`STORED_TRIP_DATE` beyond `trips.constants.TRIP_DATE_DIVERGENCE_TOLERANCE`, the page's
"Logged as ..." note reintroduces the stored date on purpose, alongside the span rather
than instead of it. Tests covering that note assert the stored date *and* the "Logged as"
label together, and still assert the primary heading line shows the span, not the stored
date, exactly as before.
"""

from datetime import UTC, date, datetime

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils.formats import date_format

from gpx.models import GpxTrack
from tests.conftest import GPX_BOUNDS, GPX_POINTS
from trips.models import Trip

# Deliberately not any stage's date below — see the module docstring.
STORED_TRIP_DATE = date(2026, 5, 20)


@pytest.fixture
def trip(rider: User) -> Trip:
    return Trip.objects.create(name="Alps Loop", date=STORED_TRIP_DATE, owner=rider)


def detail_url(trip: Trip) -> str:
    return reverse("trips:detail", kwargs={"pk": trip.pk})


def timed_track(
    trip: Trip,
    filename: str,
    started_at: datetime | None,
    ended_at: datetime | None,
) -> GpxTrack:
    """Persist a stage carrying its own instants, or none.

    Local for the reason `tests/trips/test_trip_detail_stats.py`'s equivalent is:
    `make_gpx_track` in `tests/conftest.py` takes no instants, because every caller of it
    is indifferent to ride order and these tests are about nothing else.
    """
    return GpxTrack.objects.create(
        trip=trip,
        file=f"gpx/1/1/{filename}",
        points=GPX_POINTS,
        original_filename=filename,
        started_at=started_at,
        ended_at=ended_at,
        **GPX_BOUNDS,
    )


@pytest.mark.django_db
def test_a_fully_timed_multi_day_tour_shows_the_span_it_was_ridden_over(
    auth_client: Client, trip: Trip
) -> None:
    """E-10's whole outcome, on the page: the tour's real dates, derived and not stored.

    The stored date is asserted present via the "Logged as ..." note, not absent — this
    fixture's span (1-3 June) diverges from `STORED_TRIP_DATE` (20 May) well beyond
    tolerance. The primary heading line is still asserted to show the span, not the
    stored date: the divergence note is a secondary line, not a replacement.
    """
    timed_track(
        trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC), datetime(2026, 6, 1, 17, tzinfo=UTC)
    )
    timed_track(
        trip, "day-3.gpx", datetime(2026, 6, 3, 8, tzinfo=UTC), datetime(2026, 6, 3, 16, tzinfo=UTC)
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["trip_span"] == (
        datetime(2026, 6, 1, 8, tzinfo=UTC),
        datetime(2026, 6, 3, 16, tzinfo=UTC),
    )
    assert f"{date_format(date(2026, 6, 1))} &ndash; {date_format(date(2026, 6, 3))}" in body
    assert "Logged as" in body
    assert date_format(STORED_TRIP_DATE) in body


@pytest.mark.django_db
def test_a_single_day_span_prints_one_date_rather_than_a_range_repeating_itself(
    auth_client: Client, trip: Trip
) -> None:
    """A day ride is timed end to end and still spans one date, so the range form is wrong.

    Two stages, both on 1 June: this is a morning and an afternoon file, the ordinary
    shape of a single-day ride recorded in two sittings — not a contrived one.
    """
    timed_track(
        trip,
        "morning.gpx",
        datetime(2026, 6, 1, 8, tzinfo=UTC),
        datetime(2026, 6, 1, 11, tzinfo=UTC),
    )
    timed_track(
        trip,
        "afternoon.gpx",
        datetime(2026, 6, 1, 14, tzinfo=UTC),
        datetime(2026, 6, 1, 17, tzinfo=UTC),
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert date_format(date(2026, 6, 1)) in body
    assert "&ndash;" not in body
    assert "Logged as" in body
    assert date_format(STORED_TRIP_DATE) in body


@pytest.mark.django_db
def test_a_trip_with_any_untimed_stage_shows_the_stored_date_alone(
    auth_client: Client, trip: Trip
) -> None:
    """One untimed stage withdraws the span for the same reason it withdraws the wording.

    The timed stage here is on 1 June, so an ungated span would print a plausible-looking
    single date that is not the tour's — which is exactly why the stored date has to be
    asserted present, not just the range absent.
    """
    timed_track(
        trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC), datetime(2026, 6, 1, 17, tzinfo=UTC)
    )
    timed_track(trip, "day-2.gpx", None, None)

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["trip_span"] is None
    assert date_format(STORED_TRIP_DATE) in body
    assert date_format(date(2026, 6, 1)) not in body


@pytest.mark.django_db
def test_a_trip_with_no_stages_shows_the_stored_date_exactly_as_before(
    auth_client: Client, trip: Trip
) -> None:
    """The v1 page, unchanged — the case that must not regress while the span is added."""
    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["trip_span"] is None
    assert date_format(STORED_TRIP_DATE) in body


@pytest.mark.django_db
def test_no_note_when_span_start_is_exactly_at_the_tolerance_boundary(
    auth_client: Client, rider: User
) -> None:
    """One day apart equals `TRIP_DATE_DIVERGENCE_TOLERANCE` — strictly-greater-than
    means `date_diverges` stays False, so no "Logged as ..." note renders.
    """
    trip = Trip.objects.create(name="Boundary Trip", date=date(2026, 5, 31), owner=rider)
    timed_track(
        trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC), datetime(2026, 6, 1, 17, tzinfo=UTC)
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["date_diverges"] is False
    assert "Logged as" not in body


@pytest.mark.django_db
def test_note_renders_one_day_beyond_the_tolerance_boundary(
    auth_client: Client, rider: User
) -> None:
    """Two days apart is one day beyond tolerance — the note renders."""
    trip = Trip.objects.create(name="Beyond Boundary Trip", date=date(2026, 5, 31), owner=rider)
    timed_track(
        trip, "day-1.gpx", datetime(2026, 6, 2, 8, tzinfo=UTC), datetime(2026, 6, 2, 17, tzinfo=UTC)
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["date_diverges"] is True
    assert "Logged as" in body
    assert date_format(date(2026, 5, 31)) in body


@pytest.mark.django_db
def test_the_rejected_upload_re_render_keeps_the_span(auth_client: Client, trip: Trip) -> None:
    """The context-key parity both view docstrings claim, asserted on the second path.

    `GpxUploadView` re-renders this same template, so a `trip_span` supplied only by
    `TripDetailView` would make a multi-day tour appear to shrink to its start date the
    moment an upload was rejected — a wrong answer arriving at the exact moment the rider
    is already being told something went wrong. The same parity applies to
    `date_diverges`: this fixture's span diverges from `STORED_TRIP_DATE` just as in
    `test_a_fully_timed_multi_day_tour_shows_the_span_it_was_ridden_over`, so the note
    must render identically on this rejected-upload re-render path too.
    """
    timed_track(
        trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC), datetime(2026, 6, 1, 17, tzinfo=UTC)
    )
    timed_track(
        trip, "day-3.gpx", datetime(2026, 6, 3, 8, tzinfo=UTC), datetime(2026, 6, 3, 16, tzinfo=UTC)
    )

    response = auth_client.post(
        reverse("gpx:upload", kwargs={"pk": trip.pk}),
        {"file": SimpleUploadedFile("not-a-track.gpx", b"nonsense", content_type="text/xml")},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["trip_span"] == (
        datetime(2026, 6, 1, 8, tzinfo=UTC),
        datetime(2026, 6, 3, 16, tzinfo=UTC),
    )
    assert f"{date_format(date(2026, 6, 1))} &ndash; {date_format(date(2026, 6, 3))}" in body
    assert "Logged as" in body
    assert date_format(STORED_TRIP_DATE) in body
