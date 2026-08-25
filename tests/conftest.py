"""Shared pytest-django fixtures for the VeloLog test suite."""

from collections.abc import Callable
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client
from pytest_django.fixtures import Settings

from gpx.models import GpxTrack
from trips.models import Trip

GPX_POINTS = [[50.06, 19.94], [50.07, 19.95]]
GPX_BOUNDS = {
    "min_latitude": 50.06,
    "min_longitude": 19.94,
    "max_latitude": 50.07,
    "max_longitude": 19.95,
}

TrackFactory = Callable[..., GpxTrack]


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
def _plain_staticfiles_storage(settings: Settings) -> None:
    """Resolve `{% static %}` without requiring a collected manifest.

    `base.html` loads a stylesheet, so every page in the suite now goes through the
    staticfiles storage. The configured one is
    `CompressedManifestStaticFilesStorage`, which resolves names against
    `staticfiles.json` and raises `ValueError: Missing staticfiles manifest entry` when
    that file has not been produced — so without this the whole suite would depend on a
    `collectstatic` having been run first, and `pytest` on a fresh clone would fail on
    every rendered page.

    What replaces the check is `tests/test_static_references.py`, not `collectstatic`:
    that command post-processes references found *inside* collected CSS and JS and never
    reads a template or a Python module, so it cannot tell whether `{% static %}` was
    handed a name that exists. Under this fixture nothing can — plain storage builds a URL
    for any name at all by concatenation. The references are therefore asserted directly
    there, once, rather than depended upon implicitly by every page-rendering test here.

    Spread rather than replaced — `STORAGES` is not merged by Django, and dropping the
    `"default"` alias here would break every upload test.
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


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


@pytest.fixture
def make_gpx_track() -> TrackFactory:
    """Return a factory that persists a `GpxTrack` against a given trip.

    Both the `trips` and `gpx` test packages build tracks, and the columns Phase 5
    renders the map from (`points` plus the four bounds) have to stay identical
    across them — so the defaults live here rather than in a per-package helper.
    """

    def _make(trip: Trip, original_filename: str = "alps-day-1.gpx") -> GpxTrack:
        return GpxTrack.objects.create(
            trip=trip,
            file="gpx/1/1/deadbeef.gpx",
            points=GPX_POINTS,
            original_filename=original_filename,
            **GPX_BOUNDS,
        )

    return _make
