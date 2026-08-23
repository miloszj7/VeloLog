import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from trips.models import Trip


@pytest.mark.django_db
def test_valid_post_creates_trip_owned_by_requesting_user_and_redirects(
    auth_client: Client, rider: User
) -> None:
    response = auth_client.post(
        reverse("trips:create"),
        {"name": "Alps Loop", "date": "2026-06-01", "description": "A week in the mountains."},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("trips:list")
    trip = Trip.objects.get(name="Alps Loop")
    assert trip.owner == rider


@pytest.mark.django_db
def test_empty_description_creates_trip(auth_client: Client) -> None:
    response = auth_client.post(
        reverse("trips:create"),
        {"name": "Coastal Ride", "date": "2026-07-01", "description": ""},
    )

    assert response.status_code == 302
    trip = Trip.objects.get(name="Coastal Ride")
    assert trip.description == ""


@pytest.mark.django_db
def test_blank_name_rejects_and_creates_nothing(auth_client: Client) -> None:
    response = auth_client.post(
        reverse("trips:create"),
        {"name": "", "date": "2026-07-01", "description": ""},
    )

    assert response.status_code == 200
    assert response.context["form"].errors["name"]
    assert not Trip.objects.exists()


@pytest.mark.django_db
def test_posted_owner_field_cannot_override_server_side_assignment(
    auth_client: Client, rider: User, other_rider: User
) -> None:
    response = auth_client.post(
        reverse("trips:create"),
        {
            "name": "Alps Loop",
            "date": "2026-06-01",
            "description": "",
            "owner": other_rider.pk,
        },
    )

    assert response.status_code == 302
    trip = Trip.objects.get(name="Alps Loop")
    assert trip.owner == rider


@pytest.mark.django_db
def test_unauthenticated_post_redirects_to_login_and_creates_nothing(client: Client) -> None:
    response = client.post(
        reverse("trips:create"),
        {"name": "Alps Loop", "date": "2026-06-01", "description": ""},
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith(reverse("login"))
    assert not Trip.objects.exists()
