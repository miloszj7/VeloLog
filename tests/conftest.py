"""Shared pytest-django fixtures for the VeloLog test suite."""

import pytest
from django.contrib.auth.models import User
from django.test import Client


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
