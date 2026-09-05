from datetime import UTC, datetime

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import DjangoAssertNumQueries

from gpx.models import GpxTrack
from tests.conftest import GPX_BOUNDS, GPX_POINTS
from trips.models import Trip


def timed_track(trip: Trip, filename: str, started_at: datetime) -> GpxTrack:
    """Persist a stage carrying a `started_at`, mirroring
    `tests/trips/test_trip_detail_span.py`'s local helper of the same shape.
    """
    return GpxTrack.objects.create(
        trip=trip,
        file=f"gpx/1/1/{filename}",
        points=GPX_POINTS,
        original_filename=filename,
        started_at=started_at,
        **GPX_BOUNDS,
    )


def untimed_track(trip: Trip, filename: str) -> GpxTrack:
    """Persist a stage with no `started_at` — an unestablished-chronology stage."""
    return GpxTrack.objects.create(
        trip=trip,
        file=f"gpx/1/1/{filename}",
        points=GPX_POINTS,
        original_filename=filename,
        **GPX_BOUNDS,
    )


@pytest.mark.django_db
def test_list_shows_own_trips(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)

    response = auth_client.get(reverse("trips:list"))

    assert response.status_code == 200
    assert trip in response.context["object_list"]
    assert "Alps Loop" in response.content.decode()


@pytest.mark.django_db
def test_list_does_not_show_another_users_trips(
    auth_client: Client, rider: User, other_rider: User
) -> None:
    other_trip = Trip.objects.create(name="Other Rider Trip", date="2026-06-01", owner=other_rider)

    response = auth_client.get(reverse("trips:list"))

    assert response.status_code == 200
    assert other_trip not in response.context["object_list"]
    assert "Other Rider Trip" not in response.content.decode()


@pytest.mark.django_db
def test_user_with_no_trips_sees_empty_state(auth_client: Client) -> None:
    response = auth_client.get(reverse("trips:list"))

    assert response.status_code == 200
    assert "haven't logged any trips" in response.content.decode()


@pytest.mark.django_db
def test_unauthenticated_get_redirects_to_login_with_next(client: Client) -> None:
    response = client.get(reverse("trips:list"))

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={reverse('trips:list')}"


@pytest.mark.django_db
def test_success_message_renders_on_list_page_after_create(auth_client: Client) -> None:
    auth_client.post(
        reverse("trips:create"),
        {"name": "Alps Loop", "date": "2026-06-01", "description": ""},
    )

    response = auth_client.get(reverse("trips:list"))

    assert "Trip saved." in response.content.decode()


@pytest.mark.django_db
def test_list_links_each_trip_to_its_own_detail_page(auth_client: Client, rider: User) -> None:
    first = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    second = Trip.objects.create(name="Pyrenees Loop", date="2026-07-01", owner=rider)

    response = auth_client.get(reverse("trips:list"))
    body = response.content.decode()

    assert response.status_code == 200
    assert f'href="{reverse("trips:detail", kwargs={"pk": first.pk})}"' in body
    assert f'href="{reverse("trips:detail", kwargs={"pk": second.pk})}"' in body


@pytest.mark.django_db
def test_a_diverging_trip_shows_the_indicator(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=datetime(2026, 1, 1).date(), owner=rider)
    timed_track(trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC))

    response = auth_client.get(reverse("trips:list"))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["diverging_trip_ids"] == {trip.pk}
    assert 'title="Logged date differs from the GPX-recorded ride date"' in body


@pytest.mark.django_db
def test_a_trip_with_no_stages_shows_no_indicator(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)

    response = auth_client.get(reverse("trips:list"))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["diverging_trip_ids"] == set()
    assert trip.pk not in response.context["diverging_trip_ids"]
    assert 'title="Logged date differs from the GPX-recorded ride date"' not in body


@pytest.mark.django_db
def test_a_trip_whose_stage_matches_its_date_shows_no_indicator(
    auth_client: Client, rider: User
) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    timed_track(trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC))

    response = auth_client.get(reverse("trips:list"))

    assert response.status_code == 200
    assert response.context["diverging_trip_ids"] == set()


@pytest.mark.django_db
def test_a_trip_with_an_untimed_stage_shows_no_indicator_even_when_the_timed_stage_diverges(
    auth_client: Client, rider: User
) -> None:
    """Matches `trip_span`'s own gate (`gpx/stages.py`'s `chronology_is_established`):
    a trip is flagged here only when every stage is timed. One untimed stage keeps this
    indicator silent even though the other, timed stage diverges wildly from `Trip.date`
    — the same trip's detail page shows no "Logged as ..." note for the same reason, so
    the two surfaces agree instead of contradicting each other.
    """
    trip = Trip.objects.create(name="Alps Loop", date=datetime(2026, 1, 1).date(), owner=rider)
    timed_track(trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC))
    untimed_track(trip, "day-2.gpx")

    response = auth_client.get(reverse("trips:list"))

    assert response.status_code == 200
    assert response.context["diverging_trip_ids"] == set()


@pytest.mark.django_db
def test_the_list_costs_a_fixed_small_number_of_queries_regardless_of_stage_count(
    auth_client: Client, rider: User, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    """Guards against a future N+1 on the divergence aggregate.

    Several trips, several stages each — the query count must not grow with either, since
    the aggregate is computed once for the whole list, not once per trip or per stage.
    """
    trips = [
        Trip.objects.create(name=f"Trip {i}", date="2026-06-01", owner=rider) for i in range(3)
    ]
    for trip in trips:
        timed_track(trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC))
        timed_track(trip, "day-2.gpx", datetime(2026, 6, 2, 8, tzinfo=UTC))

    # session lookup, auth user lookup, the trip list query, and one aggregate for the
    # whole list — fixed regardless of how many trips or stages exist.
    with django_assert_num_queries(4):
        response = auth_client.get(reverse("trips:list"))

    assert response.status_code == 200
