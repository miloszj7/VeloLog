"""Shared pytest-django fixtures for the VeloLog test suite."""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import Client
from pytest_django.fixtures import Settings

from gpx.models import GpxTrack
from tests.mutations import MUTATION_SHAPES, apply_mutation_shape
from trips.models import Trip

GPX_POINTS = [[50.06, 19.94], [50.07, 19.95]]
GPX_BOUNDS = {
    "min_latitude": 50.06,
    "min_longitude": 19.94,
    "max_latitude": 50.07,
    "max_longitude": 19.95,
}

TrackFactory = Callable[..., GpxTrack]
StoredTrackFactory = Callable[..., GpxTrack]


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


@pytest.fixture(scope="session", autouse=True)
def _apply_mutation_shape() -> Iterator[None]:
    """Apply the mutation shape named by `VELOLOG_MUTATION`, or do nothing.

    Unset or empty — every normal run, local and CI — is a no-op: the `yield` below runs
    with no patch in place. Session-scoped rather than done in `pytest_configure`, because
    the patch must land *after* `pytest-django` has configured Django, and `pytest_configure`
    races that setup. An unrecognized name raises rather than skips, so a typo in
    `tests/mutations.py`'s registry (or in the `VELOLOG_MUTATION` value the harness passes)
    surfaces as an error instead of a silently vacuous run.
    """
    shape_name = os.environ.get("VELOLOG_MUTATION", "")
    if not shape_name:
        yield
        return

    shapes_by_name = {shape.name: shape for shape in MUTATION_SHAPES}
    if shape_name not in shapes_by_name:
        raise ValueError(
            f"VELOLOG_MUTATION={shape_name!r} does not match any shape registered in "
            "tests/mutations.py"
        )

    with pytest.MonkeyPatch.context() as monkeypatch:
        apply_mutation_shape(shapes_by_name[shape_name], monkeypatch)
        yield


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
def other_auth_client(other_rider: User) -> Client:
    """The mirror of `auth_client` above: the *second* rider, logged in, in its own session.

    `other_rider` existed only ever as the owner of data somebody else requested, so every
    cross-user assertion in the suite ran in one direction — `rider` as the intruder — and
    silently assumed the owner-scoped queryset is symmetric. It is, by construction, but
    that was an assumption rather than an assertion.

    A fresh `Client()` rather than the shared `client` fixture: a test requesting both this
    and `auth_client` needs two independent sessions, not one client logged in twice.
    """
    other_client = Client()
    assert other_client.login(username="other-rider", password="correct-horse-battery-staple")
    return other_client


@pytest.fixture
def make_gpx_track() -> TrackFactory:
    """Return a factory that persists a `GpxTrack` against a given trip.

    Both the `trips` and `gpx` test packages build tracks, and the columns Phase 5
    renders the map from (`points` plus the four bounds) have to stay identical
    across them — so the defaults live here rather than in a per-package helper.

    The four statistics default to `None` so every existing caller keeps producing the
    track it always did — which is also the shape of a row uploaded before the stats
    columns existed, and the one the detail page has to render deliberately.
    """

    def _make(
        trip: Trip,
        original_filename: str = "alps-day-1.gpx",
        distance_meters: float | None = None,
        duration_seconds: float | None = None,
        elevation_gain_meters: float | None = None,
        elevation_loss_meters: float | None = None,
    ) -> GpxTrack:
        return GpxTrack.objects.create(
            trip=trip,
            file="gpx/1/1/deadbeef.gpx",
            points=GPX_POINTS,
            original_filename=original_filename,
            distance_meters=distance_meters,
            duration_seconds=duration_seconds,
            elevation_gain_meters=elevation_gain_meters,
            elevation_loss_meters=elevation_loss_meters,
            **GPX_BOUNDS,
        )

    return _make


@pytest.fixture
def make_stored_track() -> StoredTrackFactory:
    """Return a factory that persists a `GpxTrack` whose file holds real bytes.

    `make_gpx_track` above assigns a file *name* and nothing else, which is all the
    read-side tests need. Anything that opens the file or asserts its removal needs bytes
    on disk — under `MEDIA_ROOT`, which `_media_root_in_tmp_path` has already pointed at
    `tmp_path`. Sits here rather than in `tests/gpx/conftest.py` for the same reason
    `make_gpx_track` does: `tests/trips/` builds stored tracks too, now that deleting a
    trip has to prove it took the file with it.
    """

    def _make(
        trip: Trip,
        content: bytes = b"<gpx/>",
        original_filename: str = "alps-day-1.gpx",
    ) -> GpxTrack:
        track = GpxTrack.objects.create(
            trip=trip,
            points=GPX_POINTS,
            original_filename=original_filename,
            **GPX_BOUNDS,
        )
        track.file.save(original_filename, ContentFile(content), save=True)
        return track

    return _make
