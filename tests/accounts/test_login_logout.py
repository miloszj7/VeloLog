import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_login_with_valid_credentials_redirects_to_landing(client: Client) -> None:
    User.objects.create_user(username="rider", password="correct-horse-battery-staple")

    response = client.post(
        reverse("login"),
        {"username": "rider", "password": "correct-horse-battery-staple"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("accounts:landing")
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
def test_logout_clears_session_and_landing_requires_login_again(client: Client) -> None:
    User.objects.create_user(username="rider", password="correct-horse-battery-staple")
    client.login(username="rider", password="correct-horse-battery-staple")

    logout_response = client.post(reverse("logout"))

    assert logout_response.status_code == 302
    assert "_auth_user_id" not in client.session

    landing_response = client.get(reverse("accounts:landing"))
    assert landing_response.status_code == 302
    assert landing_response.headers["Location"].startswith(reverse("login"))


@pytest.mark.django_db
def test_unauthenticated_landing_redirects_to_login_with_next(client: Client) -> None:
    response = client.get(reverse("accounts:landing"))

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={reverse('accounts:landing')}"


@pytest.mark.django_db
def test_authenticated_landing_shows_username(client: Client) -> None:
    User.objects.create_user(username="rider", password="correct-horse-battery-staple")
    client.login(username="rider", password="correct-horse-battery-staple")

    response = client.get(reverse("accounts:landing"))

    assert response.status_code == 200
    assert "rider" in response.content.decode()
