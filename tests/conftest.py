"""Shared pytest-django fixtures for the VeloLog test suite."""

from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client
from pytest_django.fixtures import Settings


@pytest.fixture(autouse=True)
def _disable_ssl_redirect(settings: Settings) -> None:
    """Keep the test client on plain HTTP regardless of whether `.env` supplies `DEBUG`.

    Without this, `SECURE_SSL_REDIRECT` (set when `DEBUG` resolves false, e.g. in CI
    with no `.env`) makes every test-client request 301 to `https://testserver/`.
    """
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture(autouse=True)
def _media_root_in_tmp_path(settings: Settings, tmp_path: Path) -> None:
    """Redirect `MEDIA_ROOT` at pytest's `tmp_path` so no test writes into the working tree.

    The suite must pass with no `.env` present, where `MEDIA_ROOT` falls back to
    `BASE_DIR / "media"` — inside the repo. Assigning through the `settings` fixture fires
    `setting_changed`, which resets the cached `default_storage` location.
    """
    settings.MEDIA_ROOT = str(tmp_path / "media")


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Keep `/healthz/`'s cached verdict from leaking between tests.

    The default backend is LocMem and the suite runs in one process, so without this the
    first test to hit `/healthz/` decides the verdict every later test sees — a broken
    store would read healthy because a passing test cached `ok` first.
    """
    cache.clear()


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
