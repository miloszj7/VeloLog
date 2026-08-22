import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_signup_creates_user_and_logs_in(client: Client) -> None:
    response = client.post(
        reverse("accounts:signup"),
        {
            "username": "newrider",
            "email": "newrider@example.com",
            "password1": "correct-horse-battery-staple",
            "password2": "correct-horse-battery-staple",
        },
    )

    assert response.status_code == 302
    assert User.objects.filter(username="newrider").count() == 1
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_signup_rejects_duplicate_username(client: Client) -> None:
    User.objects.create_user(username="existing", email="existing@example.com", password="x")

    response = client.post(
        reverse("accounts:signup"),
        {
            "username": "existing",
            "email": "other@example.com",
            "password1": "correct-horse-battery-staple",
            "password2": "correct-horse-battery-staple",
        },
    )

    assert response.status_code == 200
    assert User.objects.filter(username="existing").count() == 1


@pytest.mark.django_db
def test_signup_rejects_duplicate_email(client: Client) -> None:
    User.objects.create_user(username="existing", email="dup@example.com", password="x")

    response = client.post(
        reverse("accounts:signup"),
        {
            "username": "other",
            "email": "dup@example.com",
            "password1": "correct-horse-battery-staple",
            "password2": "correct-horse-battery-staple",
        },
    )

    assert response.status_code == 200
    assert not User.objects.filter(username="other").exists()


@pytest.mark.django_db
def test_signup_rejects_password_mismatch(client: Client) -> None:
    response = client.post(
        reverse("accounts:signup"),
        {
            "username": "newrider",
            "email": "newrider@example.com",
            "password1": "correct-horse-battery-staple",
            "password2": "different-password",
        },
    )

    assert response.status_code == 200
    assert not User.objects.filter(username="newrider").exists()
