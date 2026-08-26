from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils.formats import date_format

from tests.conftest import TrackFactory
from trips.models import Trip


@pytest.mark.django_db
def test_owner_sees_own_trip_detail(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(
        name="Alps Loop",
        date=date(2026, 6, 1),
        description="A week in the mountains.",
        owner=rider,
    )

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["trip"] == trip
    assert "Alps Loop" in body
    assert date_format(trip.date) in body
    assert "A week in the mountains." in body


@pytest.mark.django_db
def test_another_users_trip_returns_404_not_403(
    auth_client: Client, rider: User, other_rider: User
) -> None:
    other_trip = Trip.objects.create(name="Other Rider Trip", date="2026-06-01", owner=other_rider)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": other_trip.pk}))

    assert response.status_code == 404
    assert "Other Rider Trip" not in response.content.decode()


@pytest.mark.django_db
def test_unauthenticated_get_redirects_to_login_with_next(client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    detail_url = reverse("trips:detail", kwargs={"pk": trip.pk})

    response = client.get(detail_url)

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={detail_url}"


@pytest.mark.django_db
def test_trip_with_no_track_renders_the_empty_state_copy(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))

    assert response.status_code == 200
    assert response.context["track"] is None
    assert "No route yet" in response.content.decode()


@pytest.mark.django_db
def test_trip_with_a_track_renders_only_its_own_track(
    auth_client: Client, rider: User, make_gpx_track: TrackFactory
) -> None:
    """A second, newer track on another of the rider's trips must not leak onto this page.

    `GpxTrack.Meta.ordering` is newest-first, so an unscoped `GpxTrack.objects.first()`
    would return the Pyrenees track here — that is the wrong implementation this test
    exists to reject.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    track = make_gpx_track(trip, "alps-loop.gpx")
    other_trip = Trip.objects.create(name="Pyrenees Loop", date=date(2026, 7, 1), owner=rider)
    make_gpx_track(other_trip, "pyrenees-loop.gpx")

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["track"] == track
    assert "alps-loop.gpx" in body
    assert "pyrenees-loop.gpx" not in body
    assert "No route yet" not in body
