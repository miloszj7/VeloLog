"""Fixtures shared by the gpx test package."""

from collections.abc import Callable
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from gpx.models import GpxTrack
from tests.conftest import GPX_BOUNDS, GPX_POINTS
from trips.models import Trip

FIXTURE_DIR = Path(__file__).parent / "fixtures"

GpxBytesReader = Callable[[str], bytes]
StoredTrackFactory = Callable[..., GpxTrack]


@pytest.fixture
def gpx_bytes() -> GpxBytesReader:
    """Return a reader for the sample files in `tests/gpx/fixtures/`.

    Bytes rather than text: everything downstream of the upload boundary takes bytes,
    and reading as text here would quietly repair an encoding the real path would not.
    """

    def _read(name: str) -> bytes:
        return (FIXTURE_DIR / name).read_bytes()

    return _read


@pytest.fixture
def trip(rider: User) -> Trip:
    return Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)


@pytest.fixture
def make_stored_track() -> StoredTrackFactory:
    """Return a factory that persists a `GpxTrack` whose file holds real bytes.

    `make_gpx_track` in the root conftest assigns a file *name* and nothing else, which
    is all the read-side tests need. The download view opens the file, so these tests
    need bytes on disk — under `MEDIA_ROOT`, which the root conftest has already pointed
    at `tmp_path`.
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
