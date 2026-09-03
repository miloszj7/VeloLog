"""Prove that the static references this project emits resolve to real files.

`collectstatic` is the natural place to assume this is covered, and it is not: its
post-processing rewrites references found *inside* the CSS and JS it collects, and it
never reads a template or a Python module. A mistyped path in `templates/base.html`,
`trips/templates/trips/trip_detail.html` or `gpx/map_config.py` therefore passes
`collectstatic` (nothing looks at it) and passes the rest of the suite (the autouse
`_plain_staticfiles_storage` fixture resolves any name at all, by concatenation) — and
then raises `ValueError: Missing staticfiles manifest entry` in production, where
`whitenoise.storage.CompressedManifestStaticFilesStorage` is strict. Because `base.html`
links the stylesheet unconditionally, that failure is site-wide, not map-only.

Two layers, each covering what the other cannot:

- `finders.find` needs no manifest, so it runs on a fresh clone. It is what fails when an
  asset is renamed, moved or deleted. Its limit is that the names live here, so it cannot
  see a template that stops agreeing with them.
- The manifest render goes through the real templates and the real production backend, so
  it *does* catch a template drifting. Its limit is that it needs a `collectstatic` to
  have happened, so it skips locally and runs in CI, where the `gates` job collects before
  it tests.
"""

import re
from datetime import date
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from gpx.constants import (
    MARKER_ICON,
    MARKER_ICON_RETINA,
    MARKER_SHADOW,
    MARKER_STAGE_BREAK,
    MARKER_STAGE_FINISH,
    MARKER_STAGE_START,
)
from tests.conftest import TrackFactory
from trips.models import Trip
from velo_log.settings import STATIC_ROOT
from velo_log.settings import STORAGES as PRODUCTION_STORAGES

# The three marker paths are imported rather than restated so this cannot drift from the
# code it guards. The four below are literals because they are written in templates, where
# there is no constant to import; the manifest render at the bottom of this file is what
# covers a template that stops agreeing with them.
STATIC_REFERENCES = (
    MARKER_ICON,
    MARKER_ICON_RETINA,
    MARKER_SHADOW,
    MARKER_STAGE_START,
    MARKER_STAGE_FINISH,
    MARKER_STAGE_BREAK,
    "css/style.css",
    "css/theme.css",
    "gpx/map.js",
    "gpx/vendor/leaflet/leaflet.css",
    "gpx/vendor/leaflet/leaflet.js",
    "vendor/bootstrap/bootstrap.min.css",
    "vendor/bootstrap/bootstrap.bundle.min.js",
)

MANIFEST = Path(STATIC_ROOT) / "staticfiles.json"
HASHED_ASSET = re.compile(r"/static/css/style\.[0-9a-f]{8,}\.css")


@pytest.mark.parametrize("reference", STATIC_REFERENCES)
def test_every_static_reference_resolves_to_a_source_file(reference: str) -> None:
    """`finders.find` is the same lookup `collectstatic` uses to locate a source file.

    So a name that fails here is a name `collectstatic` will not collect, which is a name
    the manifest will not contain, which is a 500 on every page that references it.
    """
    assert finders.find(reference) is not None, (
        f"{reference!r} resolves to no file under STATICFILES_DIRS or any app's static/ "
        f"directory — it will be absent from the manifest and 500 the page that uses it"
    )


@pytest.mark.skipif(
    not MANIFEST.exists(),
    reason=f"no {MANIFEST.name} — run `manage.py collectstatic` (the CI gates job does)",
)
@pytest.mark.django_db
def test_the_trip_detail_page_renders_under_the_production_static_storage(
    auth_client: Client,
    rider: User,
    make_gpx_track: TrackFactory,
    settings: Settings,
) -> None:
    """The one page carrying every kind of static reference, rendered strictly.

    This is the assertion the suite otherwise lacks: under the real backend an unknown
    name raises during template rendering rather than resolving to a plausible-looking
    URL, so it covers the stylesheet in `base.html`, both Leaflet files and the map script
    in `trip_detail.html`, and the three marker paths resolved in `gpx/map_config.py` — as
    they are actually written, not as restated above.

    The hashed-name assertion is not decoration: without it a `STORAGES` override that
    silently failed to take effect would leave this test passing against plain storage,
    which is the exact blind spot it exists to close.
    """
    settings.STORAGES = PRODUCTION_STORAGES
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    make_gpx_track(trip)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))

    assert response.status_code == 200
    body = response.content.decode()
    assert HASHED_ASSET.search(body), (
        "the stylesheet URL carries no content hash, so this page did not render through "
        "the manifest backend and the test proved nothing"
    )
