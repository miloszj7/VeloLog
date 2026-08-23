import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_login_with_valid_credentials_redirects_to_trip_list(client: Client) -> None:
    User.objects.create_user(username="rider", password="correct-horse-battery-staple")

    response = client.post(
        reverse("login"),
        {"username": "rider", "password": "correct-horse-battery-staple"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("trips:list")
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_login_with_invalid_credentials_shows_error(client: Client) -> None:
    User.objects.create_user(username="rider", password="correct-horse-battery-staple")

    response = client.post(
        reverse("login"),
        {"username": "rider", "password": "wrong-password"},
    )

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert response.context["form"].non_field_errors()
    assert "Please enter a correct username and password" in response.content.decode()


@pytest.mark.django_db
def test_logout_clears_session_and_trip_list_requires_login_again(client: Client) -> None:
    User.objects.create_user(username="rider", password="correct-horse-battery-staple")
    client.login(username="rider", password="correct-horse-battery-staple")

    logout_response = client.post(reverse("logout"))

    assert logout_response.status_code == 302
    assert "_auth_user_id" not in client.session

    list_response = client.get(reverse("trips:list"))
    assert list_response.status_code == 302
    assert list_response.headers["Location"].startswith(reverse("login"))


@pytest.mark.django_db
def test_unauthenticated_trip_list_redirects_to_login_with_next(client: Client) -> None:
    response = client.get(reverse("trips:list"))

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={reverse('trips:list')}"


@pytest.mark.django_db
def test_authenticated_trip_list_shows_logout_control(client: Client) -> None:
    User.objects.create_user(username="rider", password="correct-horse-battery-staple")
    client.login(username="rider", password="correct-horse-battery-staple")

    response = client.get(reverse("trips:list"))

    assert response.status_code == 200
    assert reverse("logout") in response.content.decode()


@pytest.mark.django_db
def test_site_root_redirects_to_trip_list(client: Client) -> None:
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("trips:list")
