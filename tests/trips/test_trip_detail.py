import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gpx.models import GpxTrack
from trips.models import Trip


@pytest.mark.django_db
def test_owner_sees_own_trip_detail(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(
        name="Alps Loop", date="2026-06-01", description="A week in the mountains.", owner=rider
    )

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["trip"] == trip
    assert "Alps Loop" in body
    assert "June 1, 2026" in body
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
def test_trip_with_a_track_renders_the_track_branch_instead_of_the_empty_state(
    auth_client: Client, rider: User
) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    track = GpxTrack.objects.create(
        trip=trip,
        file="gpx/placeholder.gpx",
        points=[[46.0, 7.0], [46.1, 7.1]],
        min_latitude=46.0,
        min_longitude=7.0,
        max_latitude=46.1,
        max_longitude=7.1,
        original_filename="alps-loop.gpx",
    )

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.context["track"] == track
    assert "alps-loop.gpx" in body
    assert "No route yet" not in body


@pytest.mark.django_db
def test_list_page_links_each_trip_to_its_detail_page(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)

    response = auth_client.get(reverse("trips:list"))

    assert f'href="{reverse("trips:detail", kwargs={"pk": trip.pk})}"' in response.content.decode()
