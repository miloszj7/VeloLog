"""Prove the media storage foundation by performing the real operations.

`STORAGES["default"]` is resolved lazily — `FileField.__init__` stores an unevaluated
`LazyObject` and only `storage.save`/`storage.url` triggers the lookup. Nothing else in
the toolchain evaluates it: `manage.py check` validates only the *staticfiles* alias,
mypy sees a typed attribute, and a view test that asserts a status code never touches
storage. So a settings assertion here would be worthless — it would pass against a
`STORAGES` dict that still cannot resolve. Every test below does the real thing instead.
"""

from pathlib import Path
from typing import IO, Any, NoReturn

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.utils import OperationalError
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from velo_log import urls as velo_log_urls


class _BrokenStorage:
    """Stands in for `default_storage` when the media store is unreachable.

    Every method raises, including `delete`, so the `finally` cleanup path is exercised
    too — that is the branch which decides whether a failing store produces a diagnosable
    500 or an opaque stack trace.
    """

    def delete(self, name: str) -> None:
        raise OSError("media store unavailable")

    def save(self, name: str, content: ContentFile[Any]) -> str:
        raise OSError("media store unavailable")

    def open(self, name: str, mode: str) -> IO[bytes]:
        raise OSError("media store unavailable")


def test_default_storage_round_trips_real_bytes(settings: Settings) -> None:
    """A save through `default_storage` must persist readable bytes under `MEDIA_ROOT`."""
    name = default_storage.save("probe/round-trip.txt", ContentFile(b"velolog"))
    try:
        with default_storage.open(name, "rb") as handle:
            assert handle.read() == b"velolog"
        saved_path = Path(default_storage.path(name))
        assert saved_path.is_relative_to(Path(settings.MEDIA_ROOT))
    finally:
        default_storage.delete(name)


def test_media_url_does_not_shadow_the_root_redirect(client: Client, settings: Settings) -> None:
    """`MEDIA_URL` must not resolve to "/", which the root `RedirectView` already owns."""
    assert settings.MEDIA_URL != "/"
    assert settings.MEDIA_URL.startswith("/media/")

    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("trips:list")


def test_healthz_reports_both_round_trips_ok(client: Client, db: None) -> None:
    """The health check must prove the media write, not only the database write."""
    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["media"] == "ok"


def test_healthz_fails_when_media_root_is_inside_base_dir_and_debug_is_false(
    client: Client, settings: Settings, db: None
) -> None:
    """An in-container media root is a production misconfiguration, not a passing probe.

    A writability-only check would return 200 here — the directory is perfectly writable.
    It is just ephemeral, so every upload would be lost on the next redeploy.
    """
    settings.DEBUG = False
    in_container_media_root = Path(settings.BASE_DIR) / "media"
    settings.MEDIA_ROOT = str(in_container_media_root)

    response = client.get(reverse("healthz"))

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert body["media"] == "error"
    assert body["media_root"] == str(in_container_media_root)
    assert "MEDIA_ROOT" in body["media_error"]
    # The probe must not have created the misconfigured directory just to test it.
    assert not (in_container_media_root / "healthz").exists()


def test_media_root_location_check_is_skipped_under_debug(settings: Settings) -> None:
    """The in-repo default is the intended local arrangement, so DEBUG must not fail on it.

    Asserted against the check directly rather than through `/healthz/`: routing a request
    at a media root inside `BASE_DIR` would write the probe file into the working tree.
    """
    settings.DEBUG = True
    settings.MEDIA_ROOT = str(Path(settings.BASE_DIR) / "media")

    assert velo_log_urls._media_root_misconfigured() is None


def test_media_root_must_be_absolute_in_production(settings: Settings) -> None:
    """A relative media root is resolved against the process cwd, which nothing pins."""
    settings.DEBUG = False
    settings.MEDIA_ROOT = "media"

    reason = velo_log_urls._media_root_misconfigured()

    assert reason is not None
    assert "absolute" in reason


def test_healthz_blames_media_alone_when_the_store_is_unreachable(
    client: Client, db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead media store must fail the probe without implicating the database."""
    monkeypatch.setattr(velo_log_urls, "default_storage", _BrokenStorage())

    response = client.get(reverse("healthz"))

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert body["media"] == "error"
    assert body["database"] == "ok"


def test_healthz_blames_the_database_alone_when_it_is_unreachable(
    client: Client, db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead database must fail the probe without implicating the media store."""

    def _unreachable(*args: object, **kwargs: object) -> NoReturn:
        raise OperationalError("database is locked")

    monkeypatch.setattr(velo_log_urls, "SessionStore", _unreachable)

    response = client.get(reverse("healthz"))

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert body["database"] == "error"
    assert body["media"] == "ok"
