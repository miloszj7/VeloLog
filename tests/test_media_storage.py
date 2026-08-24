"""Prove the media storage foundation by performing the real operations.

`STORAGES["default"]` is resolved lazily — `FileField.__init__` stores an unevaluated
`LazyObject` and only `storage.save`/`storage.url` triggers the lookup. Nothing else in
the toolchain evaluates it: `manage.py check` validates only the *staticfiles* alias,
mypy sees a typed attribute, and a view test that asserts a status code never touches
storage. So a settings assertion here would be worthless — it would pass against a
`STORAGES` dict that still cannot resolve. Every test below does the real thing instead.
"""

from io import BytesIO
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

    Every method raises, starting at the opening `delete`, so the probe never writes and
    has nothing to clean up. `_CleanupFailsStorage` covers the other half — a store that
    accepts the write and then fails the closing delete.
    """

    def delete(self, name: str) -> None:
        raise OSError("media store unavailable")

    def save(self, name: str, content: ContentFile[Any]) -> str:
        raise OSError("media store unavailable")

    def open(self, name: str, mode: str) -> IO[bytes]:
        raise OSError("media store unavailable")


class _CleanupFailsStorage:
    """A store that takes the write and the read back, then fails the closing delete.

    That is the branch which decides whether a probe unable to clean up after itself
    produces a usable verdict or an opaque stack trace escaping `finally`.
    """

    def __init__(self) -> None:
        self._deletes = 0

    def delete(self, name: str) -> None:
        self._deletes += 1
        if self._deletes > 1:
            raise OSError("media store went away")

    def save(self, name: str, content: ContentFile[Any]) -> str:
        return name

    def open(self, name: str, mode: str) -> IO[bytes]:
        return BytesIO(velo_log_urls.HEALTHZ_MEDIA_PAYLOAD)


class _ConcurrentProbeStorage:
    """`default_storage` with the probe's opening delete lost to a concurrent probe.

    Models the one interleaving that matters: a second probe re-takes the fixed key in
    the window between this probe's delete and its save. Real threads cannot be asserted
    on deterministically, so the first `delete` is dropped instead — the key is still
    occupied when `save` runs, which is exactly the state the race leaves behind.
    """

    def __init__(self) -> None:
        self._deletes = 0

    def delete(self, name: str) -> None:
        self._deletes += 1
        if self._deletes == 1:
            return
        default_storage.delete(name)

    def save(self, name: str, content: ContentFile[Any]) -> str:
        return default_storage.save(name, content)

    def open(self, name: str, mode: str) -> IO[bytes]:
        return default_storage.open(name, mode)


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

    The root is a path guaranteed not to pre-exist rather than the settings default
    `BASE_DIR / "media"`. Any local `runserver` hit on `/healthz/` leaves that directory
    behind — `FileSystemStorage.save` creates the probe's parent and only the probe file
    is deleted — which both fails the last assertion below spuriously *and* hides a real
    regression, since a guard that stopped short-circuiting would write and then delete
    its probe file inside an already-existing directory, leaving nothing to detect.
    """
    settings.DEBUG = False
    in_container_media_root = Path(settings.BASE_DIR) / "media-misconfigured-probe"
    settings.MEDIA_ROOT = str(in_container_media_root)

    response = client.get(reverse("healthz"))

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert body["media"] == "error"
    assert body["media_root"] == str(in_container_media_root)
    assert "MEDIA_ROOT" in body["media_error"]
    # The location check must short-circuit before anything touches the misconfigured
    # root, so the probe must not have created it just to prove it was writable.
    assert not in_container_media_root.exists()


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


def test_healthz_reads_back_and_deletes_the_name_save_returned(
    client: Client, db: None, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe must report on, and clean up, the file it actually wrote.

    `Storage.save` always routes through `get_available_name`, so when the fixed key is
    occupied the write lands under a suffix. Held against the constant key instead, the
    probe reports on the other writer's bytes and leaves its own file behind for good —
    an orphan any anonymous caller can drive without limit, on the mounted Volume.
    """
    concurrent_key = default_storage.save(
        velo_log_urls.HEALTHZ_MEDIA_KEY, ContentFile(b"another-probes-bytes")
    )
    probe_dir = Path(settings.MEDIA_ROOT) / Path(velo_log_urls.HEALTHZ_MEDIA_KEY).parent
    monkeypatch.setattr(velo_log_urls, "default_storage", _ConcurrentProbeStorage())

    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.json()["media"] == "ok"
    # The other writer's file is not this probe's to remove; anything else left here is a
    # file this probe wrote and then failed to clean up.
    assert sorted(path.name for path in probe_dir.iterdir()) == [Path(concurrent_key).name]


def test_healthz_survives_a_cleanup_that_cannot_delete(
    client: Client, db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing cleanup must not escape `finally` and mask an otherwise passing probe."""
    monkeypatch.setattr(velo_log_urls, "default_storage", _CleanupFailsStorage())

    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.json()["media"] == "ok"


def test_repeated_probes_leave_no_files_behind(
    client: Client, db: None, settings: Settings
) -> None:
    """The fixed key bounds accumulation only if each probe removes what it wrote.

    `HEALTHZ_MEDIA_KEY`'s comment promises at most one stranded file on the Volume, but
    /healthz/ is unauthenticated — anyone can drive this loop. Several sequential probes
    must leave the directory as empty as they found it, not one file per call.
    """
    probe_dir = Path(settings.MEDIA_ROOT) / Path(velo_log_urls.HEALTHZ_MEDIA_KEY).parent

    for _ in range(3):
        assert client.get(reverse("healthz")).status_code == 200

    assert probe_dir.is_dir(), "the probe should have created its parent directory"
    assert list(probe_dir.iterdir()) == []
