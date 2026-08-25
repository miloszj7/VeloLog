"""Fixtures shared by the gpx test package."""

from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

GpxBytesReader = Callable[[str], bytes]


@pytest.fixture
def gpx_bytes() -> GpxBytesReader:
    """Return a reader for the sample files in `tests/gpx/fixtures/`.

    Bytes rather than text: everything downstream of the upload boundary takes bytes,
    and reading as text here would quietly repair an encoding the real path would not.
    """

    def _read(name: str) -> bytes:
        return (FIXTURE_DIR / name).read_bytes()

    return _read
