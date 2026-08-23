import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from trips.models import Trip


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
