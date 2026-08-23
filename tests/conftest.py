"""Shared pytest-django fixtures for the VeloLog test suite."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from pytest_django.fixtures import Settings


@pytest.fixture(autouse=True)
def _disable_ssl_redirect(settings: Settings) -> None:
    """Keep the test client on plain HTTP regardless of whether `.env` supplies `DEBUG`.

    Without this, `SECURE_SSL_REDIRECT` (set when `DEBUG` resolves false, e.g. in CI
    with no `.env`) makes every test-client request 301 to `https://testserver/`.
    """
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture
def rider(db: None) -> User:
    return User.objects.create_user(username="rider", password="correct-horse-battery-staple")


@pytest.fixture
def other_rider(db: None) -> User:
    return User.objects.create_user(username="other-rider", password="correct-horse-battery-staple")


@pytest.fixture
def auth_client(client: Client, rider: User) -> Client:
    assert client.login(username="rider", password="correct-horse-battery-staple")
    return client
